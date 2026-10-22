"""Read-only export discovery and private, account-bound recovery snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

VERSION = 1
MANIFEST = "export-state.json"
PRIVATE = ".export-state"
REPORT = "export-report.json"


def atomic_json(path: Path, value) -> None:
    """Replace a checkpoint atomically; never expose download credentials."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def _manifest(directory: Path):
    value = read_json(directory / MANIFEST)
    if not isinstance(value, dict) or value.get("version") != VERSION:
        return None
    if not isinstance(value.get("wxid"), str) or not value["wxid"].strip():
        return None
    resources = value.get("resources")
    if resources is not None:
        if not isinstance(resources, list) or not resources:
            return None
        from .macos_resources import resource_id

        identities = []
        for row in resources:
            if not isinstance(row, dict) or not isinstance(row.get("resource"), str):
                return None
            identity = row["resource"]
            try:
                if resource_id(f"https://invalid.local/?m={identity}") != identity:
                    return None
            except ValueError:
                return None
            identities.append(identity)
        if len(set(identities)) != len(identities):
            return None
    return value


def _identities(urls):
    from .macos_resources import resource_id

    return list(dict.fromkeys(resource_id(url, index) for index, url in enumerate(urls)))


def begin(directory, wxid: str) -> None:
    directory = Path(directory)
    if not wxid or not isinstance(wxid, str):
        raise ValueError("导出恢复记录必须绑定明确的微信账号。")
    if directory.is_symlink():
        raise ValueError("导出目录不能是符号链接。")
    directory.mkdir(parents=True, exist_ok=True)
    current = _manifest(directory)
    if current and current["wxid"] != wxid:
        raise ValueError("此导出目录属于其他微信账号，请选择其他目录。")
    if current is None:
        if (directory / MANIFEST).exists() or (directory / MANIFEST).is_symlink():
            raise ValueError("此目录的账号恢复记录无效，请选择其他导出目录。")
        if (directory / REPORT).exists():
            raise ValueError("此目录有未绑定账号的旧导出，请先确认旧图片或选择其他导出目录。")
        # This exists before metadata extraction, even if extraction is interrupted.
        atomic_json(directory / MANIFEST, {"version": VERSION, "wxid": wxid, "resources": None})


def save_snapshot(directory, wxid, urls, metadata) -> None:
    directory = Path(directory)
    begin(directory, wxid)
    urls = [value for value in urls if value.strip()]
    identities = _identities(urls)
    if not identities:
        raise ValueError("没有读取到表情清单，不能标记导出完成。")
    if not isinstance(metadata, list) or not all(isinstance(row, dict) for row in metadata):
        raise ValueError("表情元数据格式无效。")
    private = directory / PRIVATE
    if private.is_symlink():
        raise ValueError("导出恢复快照目录不能是符号链接。")
    private.mkdir(mode=0o700, exist_ok=True)
    private.chmod(0o700)
    atomic_json(private / "urls.json", urls)
    atomic_json(private / "metadata.json", metadata)
    # Publish the expected list only after both private snapshot files are durable.
    atomic_json(directory / MANIFEST, {
        "version": VERSION, "wxid": wxid,
        "resources": [{"resource": identity} for identity in identities],
    })


def load_snapshot(directory, wxid=None):
    directory = Path(directory)
    manifest = _manifest(directory)
    if not manifest or (wxid and manifest["wxid"] != wxid) or not manifest["resources"]:
        return None
    private = directory / PRIVATE
    if private.is_symlink():
        return None
    urls, metadata = read_json(private / "urls.json"), read_json(private / "metadata.json")
    if not isinstance(urls, list) or not urls or not all(isinstance(url, str) for url in urls):
        return None
    if not isinstance(metadata, list) or not all(isinstance(row, dict) for row in metadata):
        return None
    try:
        if _identities(urls) != [row["resource"] for row in manifest["resources"]]:
            return None
    except (ValueError, TypeError):
        return None
    return urls, metadata


def valid_ready(directory, entry, *, require_hash=True) -> bool:
    """A ready filename alone is insufficient: verify its bytes and every frame."""
    if not isinstance(entry, dict) or entry.get("status") != "ready":
        return False
    filename = entry.get("file")
    if not isinstance(filename, str) or Path(filename).name != filename:
        return False
    target = Path(directory) / filename
    if target.is_symlink() or not target.is_file():
        return False
    try:
        data = target.read_bytes()
        digest = entry.get("sha256")
        if require_hash and (not isinstance(digest, str) or len(digest) != 64):
            return False
        if digest and hashlib.sha256(data).hexdigest() != digest:
            return False
        from .macos_resources import decode

        decode(data)
        return True
    except Exception:
        return False


def _image_files(directory):
    """List only this directory's regular image candidates, without following links."""
    if directory.is_symlink() or not directory.is_dir():
        return []
    try:
        return [
            child for child in directory.iterdir()
            if not child.is_symlink() and child.is_file()
            and child.suffix.lower() in {".png", ".gif", ".jpg", ".jpeg", ".webp"}
        ]
    except OSError:
        return []


def status(directory, wxid=None) -> dict:
    directory = Path(directory).expanduser().absolute()
    result = dict(state="none", directory=str(directory), expected=0, ready=0, remaining=0,
                  snapshotAvailable=False, snapshot_ready=False)
    if directory.is_symlink() or not directory.is_dir():
        return result
    manifest = _manifest(directory)
    report = read_json(directory / REPORT)
    if manifest and wxid and manifest["wxid"] != wxid:
        return result
    if manifest:
        result["wxid"] = manifest["wxid"]
        identities = [row["resource"] for row in manifest["resources"] or []]
        rows = report.get("files", []) if isinstance(report, dict) else []
        rows = rows if isinstance(rows, list) else []
        entries = {
            row["resource"]: row for row in rows
            if isinstance(row, dict) and isinstance(row.get("resource"), str)
        }
        ready = sum(valid_ready(directory, entries.get(identity)) for identity in identities)
        available = load_snapshot(directory, manifest["wxid"]) is not None
        result.update(state="complete" if identities and ready == len(identities) else "partial",
                      expected=len(identities), ready=ready, remaining=len(identities) - ready,
                      snapshotAvailable=available, snapshot_ready=available)
    elif isinstance(report, dict) or (directory / MANIFEST).exists():
        # Legacy data is visible for explicit user adoption, never auto-bound to an account.
        entries = report.get("files", []) if isinstance(report, dict) else []
        entries = entries if isinstance(entries, list) else []
        expected = max(len(entries), report.get("total", 0)) if isinstance(report, dict) and isinstance(report.get("total", 0), int) else len(entries)
        ready = sum(valid_ready(directory, row, require_hash=False) for row in entries)
        result.update(state="unbound", expected=expected, ready=ready, remaining=max(0, expected-ready))
    else:
        # Older interrupted exports can contain only downloaded originals: their
        # total and account are unknown until the user explicitly adopts them.
        originals = _image_files(directory / "originals")
        if originals:
            ready = sum(valid_ready(directory, {"status": "ready", "file": child.name},
                                    require_hash=False) for child in _image_files(directory))
            result.update(state="unbound", legacy_raw=True, raw_count=len(originals), ready=ready)
    return result


def discover(parent, wxid) -> dict:
    parent = Path(parent).expanduser().absolute()
    if parent.is_symlink() or not parent.is_dir():
        return {"exports": []}
    candidates = [parent]
    try:
        candidates.extend(child for child in parent.iterdir() if not child.is_symlink() and child.is_dir())
    except OSError:
        pass
    found = []
    for directory in candidates:
        item = status(directory, wxid)
        if item["state"] != "none":
            try:
                changed = max(p.stat().st_mtime for p in [directory, directory / MANIFEST, directory / REPORT] if p.exists() and not p.is_symlink())
            except OSError:
                changed = 0
            found.append((changed, item))
    return {"exports": [item for _, item in sorted(found, key=lambda value: value[0], reverse=True)]}
