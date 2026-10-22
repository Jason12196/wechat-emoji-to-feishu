"""Validate, decrypt and prepare wxemoticon resources without changing originals."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from Crypto.Cipher import AES
from PIL import Image


def resource_id(url, index=0):
    identity = parse_qs(urlparse(url).query).get("m", [f"{index + 1:06}"])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity):
        raise ValueError("Invalid resource identifier")
    return identity


def decode(data):
    with Image.open(BytesIO(data)) as image:
        if image.format not in {"GIF", "PNG", "JPEG", "WEBP"}:
            raise ValueError("Unsupported format")
        for i in range(getattr(image, "n_frames", 1)):
            image.seek(i)
            image.load()
        return image.format, image.size, getattr(image, "n_frames", 1)


def prepare(data, max_bytes=800 * 1024, max_dimension=400):
    fmt, size, count = decode(data)
    if len(data) <= max_bytes:
        return data
    with Image.open(BytesIO(data)) as im:
        frames, durations = [], []
        for i in range(count):
            im.seek(i)
            frames.append(im.convert("RGBA").copy())
            durations.append(im.info.get("duration", 100))
        for dimension in [400, 320, 256, 200, 160, 128, 96, 64, 48, 32]:
            factor = min(1, dimension / max(size))
            resized = [
                f.resize(
                    (max(1, round(size[0] * factor)), max(1, round(size[1] * factor))),
                    Image.Resampling.LANCZOS,
                )
                for f in frames
            ]
            out = BytesIO()
            if fmt == "GIF":
                resized[0].save(
                    out,
                    format="GIF",
                    save_all=True,
                    append_images=resized[1:],
                    duration=durations,
                    loop=im.info.get("loop", 0),
                    disposal=2,
                    optimize=True,
                )
            elif fmt == "WEBP" and count > 1:
                resized[0].save(
                    out,
                    format="WEBP",
                    save_all=True,
                    append_images=resized[1:],
                    duration=durations,
                    loop=im.info.get("loop", 0),
                    quality=85,
                )
            elif count > 1:
                # Preserve animated PNG frames as APNG.
                resized[0].save(
                    out,
                    format="PNG",
                    save_all=True,
                    append_images=resized[1:],
                    duration=durations,
                    loop=im.info.get("loop", 0),
                )
            else:
                frame = resized[0].convert("RGB") if fmt == "JPEG" else resized[0]
                frame.save(out, format=fmt, optimize=True, quality=85)
            result = out.getvalue()
            if len(result) <= max_bytes:
                decode(result)
                return result
    raise ValueError("Cannot fit size limit while preserving animation")


def export_verified(raw, destination, urls, metadata, process=True, report=None, pause_event=None):
    from .export_state import atomic_json, read_json, valid_ready

    raw, destination = Path(raw), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if raw.is_symlink():
        raise ValueError("原始图片目录不能是符号链接。")
    raw.mkdir(parents=True, exist_ok=True)
    verified = destination / "verified-originals"
    if verified.is_symlink():
        raise ValueError("验证图片目录不能是符号链接。")
    verified.mkdir(exist_ok=True)
    lookup = {}
    for row in metadata:
        for name, value in row.items():
            if name.endswith("url") and value:
                lookup.setdefault(resource_id(value), []).append(row)
    sources = {}
    for folder in [raw, verified]:
        for source in sorted(folder.iterdir()):
            if (not source.is_symlink() and source.is_file()
                    and source.suffix.lower() in {".gif", ".jpg", ".jpeg", ".png", ".webp"}):
                sources.setdefault(source.stem, []).append(source)

    jobs = {}
    for index, url in enumerate(urls):
        jobs.setdefault(resource_id(url, index), (index, url))
    old = read_json(destination / "export-report.json")
    old_entries = {
        row["resource"]: row for row in old.get("files", [])
        if isinstance(row, dict) and isinstance(row.get("resource"), str)
    } if isinstance(old, dict) and isinstance(old.get("files"), list) else {}
    results = {
        identity: old_entries[identity]
        if valid_ready(destination, old_entries.get(identity))
        else {**old_entries.get(identity, {}), "resource": identity, "status": "pending"}
        for identity in jobs
    }

    def checkpoint():
        rows = list(results.values())
        atomic_json(destination / "export-report.json", {
            "total": len(jobs),
            "ready": sum(row["status"] == "ready" for row in rows),
            "failed": sum(row["status"] != "ready" for row in rows),
            "files": rows,
        })

    def write_bytes(path, value, *, replace=True):
        # A recovery run preserves good files, including their modification times.
        if not path.is_symlink() and path.is_file() and path.read_bytes() == value:
            return
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def one(job):
        if pause_event is not None:
            pause_event.wait()
        index, url = job
        identity = resource_id(url, index)
        entry = {"resource": identity, "status": "failed"}
        candidates = lookup.get(identity, [])
        original_hash = old_entries.get(identity, {}).get("original_sha256")
        if original_hash:
            entry["original_sha256"] = original_hash

        def usable(value):
            try:
                decode(value)
                if original_hash and hashlib.sha256(value).hexdigest() != original_hash:
                    return None
                return value
            except Exception:
                return None

        result, recovery, downloaded_original = None, "original", None
        for source in sources.get(identity, []):
            data = source.read_bytes()
            result = usable(data)
            if result is not None:
                break
            for row in candidates:
                key = row.get("aes_key") or ""
                try:
                    key = bytes.fromhex(key)
                except ValueError:
                    continue
                if len(key) != 16:
                    continue
                if data and len(data) % 16 == 0:
                    result = usable(AES.new(key, AES.MODE_CBC, key).decrypt(data))
                    if result is not None:
                        recovery = "local_aes"
                        break
            if result is not None:
                break
        if result is None:
            seen = {url}
            alternatives = [(url, None)]
            for row in candidates:
                for field in ["encrypt_url", "cdn_url", "tp_url", "extern_url"]:
                    address = row.get(field)
                    if address and address not in seen:
                        seen.add(address)
                        alternatives.append((address, row.get("aes_key")))
            for address, key_hex in alternatives:
                try:
                    req = Request(address, headers={"User-Agent": "Mozilla/5.0"})
                    with urlopen(req, timeout=20) as response:
                        value = response.read()
                    result = usable(value)
                    if result is None and value and len(value) % 16 == 0:
                        # The primary URL can itself be encrypted; its matching
                        # metadata must remain available even when URLs deduplicate.
                        keys = [key_hex, *(row.get("aes_key") for row in candidates)]
                        for candidate_key in dict.fromkeys(key for key in keys if key):
                            try:
                                key = bytes.fromhex(candidate_key)
                            except (ValueError, TypeError):
                                continue
                            if len(key) == 16:
                                result = usable(AES.new(key, AES.MODE_CBC, key).decrypt(value))
                                if result is not None:
                                    break
                    if result is not None:
                        recovery = "alternate_download"
                        downloaded_original = value
                        break
                except Exception:
                    continue
        if result is None:
            entry["reason"] = "No decodable resource after local decryption and alternate download"
            return entry
        fmt, size, frames = decode(result)
        ext = {"GIF": "gif", "PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
        if downloaded_original is not None and not any(
            source.parent == raw for source in sources.get(identity, [])
        ):
            # Preserve the exact bytes received, including encryption. Never
            # replace an existing original, even when that original is corrupt.
            write_bytes(raw / f"{identity}.{ext}", downloaded_original, replace=False)
        write_bytes(verified / f"{identity}.{ext}", result)
        entry.update(
            recovery=recovery,
            original_bytes=len(result),
            original_sha256=hashlib.sha256(result).hexdigest(),
            frames=frames,
            width=size[0],
            height=size[1],
        )
        try:
            prepared = prepare(result) if process else result
            target = destination / f"{identity}.{ext}"
            write_bytes(target, prepared)
            out_fmt, out_size, out_frames = decode(prepared)
            entry.update(
                status="ready",
                file=target.name,
                sha256=hashlib.sha256(prepared).hexdigest(),
                bytes=len(prepared),
                output_frames=out_frames,
                output_width=out_size[0],
                output_height=out_size[1],
            )
        except Exception as exc:
            entry.update(status="preparation_failed", reason=str(exc))
        return entry

    checkpoint()
    pending = [job for identity, job in jobs.items() if results[identity]["status"] != "ready"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(one, job): resource_id(job[1], job[0]) for job in pending}
        for completed, future in enumerate(as_completed(futures), 1):
            identity = futures[future]
            try:
                results[identity] = future.result()
            except Exception as exc:
                results[identity] = {"resource": identity, "status": "failed", "reason": type(exc).__name__}
            # Each finished image survives interruption, rather than only the final batch.
            checkpoint()
            if report and (completed % 50 == 0 or completed == len(pending)):
                report(f"[Mac] 已验证 {sum(row['status'] == 'ready' for row in results.values())}/{len(jobs)}")
    return [str(destination / row["file"]) for row in results.values() if row["status"] == "ready"]
