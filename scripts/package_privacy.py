"""Fail closed when a CLI distribution contains local state or builder paths."""

from __future__ import annotations

import collections
import copy
import gzip
import hashlib
import io
import marshal
import os
import posixpath
import shutil
import stat
import struct
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath

_STATE_COMPONENTS = {
    ".export-state", ".git", "feishu-browser", "profiles", "browser-profile",
    "chromium-profile", "user-data", "user_data", "tasks", "imports", "diagnostics",
    "debug", "selections", "jobs", "originals", "verified-originals",
    "default", "local storage", "session storage", "indexeddb", "sessions",
}
_STATE_FILES = {
    "cookies", "cookies-journal", "login data", "login data-journal", "local state",
    "history", "history-journal", "web data", "web data-journal", "preferences",
    "secure preferences", "devtoolsactiveport", "export-report.json", "export-state.json", "ledger.json",
    "cookies.sqlite", "cookies.sqlite-wal", "storage-state.json", "storage_state.json",
    "auth.json", "session.json", "emoticon.db", "emoticon.db-wal", "emoticon.db-shm",
    ".ds_store", ".env",
}
_ROOT_FILES = {"wechat-emoji", "LICENSE", "THIRD_PARTY.md", "README.md", "LICENSE.wechatemoji"}
_ROOT_DIRECTORIES = {"_internal", "dependency-licenses", "docs"}
_DOC_FILES = {"installation.md", "protocol.md"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp"}
_PYINSTALLER_MAGIC = b"MEI\014\013\012\013\016"


class PackagePrivacyError(ValueError):
    """The message contains categories and counts, never private paths or values."""

    def __init__(self, failures, locations=()):
        self.failures = dict(failures)
        summary = ", ".join(f"{code}={count}" for code, count in sorted(failures.items()))
        self.locations = tuple(locations)
        suffix = " Package-relative locations: " + ", ".join(self.locations[:20]) if self.locations else ""
        super().__init__(f"Package privacy check failed ({summary}); distribution was blocked.{suffix}")


def _state_name(name):
    parts = PurePosixPath(name).parts
    lower = [part.casefold() for part in parts]
    return any(part in _STATE_COMPONENTS for part in lower) or any(
        part in _STATE_FILES
        or part.startswith(("emoticon_dbkey", "singleton", ".env.", "wxid_", "profile "))
        or part.endswith(".log")
        or part.endswith(".account.json")
        for part in lower
    )


def _inside_archive(name):
    value = PurePosixPath(name)
    return (
        not value.is_absolute()
        and ".." not in value.parts
        and bool(value.parts)
        and value.parts[0] == "wechat-emoji"
    )


def sanitized_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Keep relative member paths and executable modes; remove builder metadata."""
    if not _inside_archive(info.name):
        raise PackagePrivacyError({"UNSAFE_ARCHIVE_PATH": 1})
    if info.issym() or info.islnk():
        if PurePosixPath(info.linkname).is_absolute():
            raise PackagePrivacyError({"UNSAFE_ARCHIVE_LINK": 1})
        target = (
            posixpath.normpath(posixpath.join(posixpath.dirname(info.name), info.linkname))
            if info.issym()
            else posixpath.normpath(info.linkname)
        )
        if not _inside_archive(target):
            raise PackagePrivacyError({"UNSAFE_ARCHIVE_LINK": 1})
    value = copy.copy(info)
    value.uid = value.gid = 0
    value.uname = value.gname = ""
    value.mtime = 0
    # tarfile regenerates legal long relative path/linkpath headers as needed.
    # Discard extended timestamps, owner names and filesystem extended attributes.
    value.pax_headers = {}
    return value


def audit_package(folder, *, private_prefixes=None, resource_policy=None, image_policy=None):
    """Inspect actual package bytes, including compressed Python/ZIP contents."""
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise PackagePrivacyError({"MISSING_PACKAGE_DIRECTORY": 1})
    prefixes = private_prefixes if private_prefixes is not None else [Path.home()]
    forbidden = []
    for prefix in prefixes:
        expanded = Path(prefix).expanduser()
        for value in {str(expanded), str(expanded.resolve())}:
            if len(value) > 1:
                forbidden.extend(value.encode(encoding) for encoding in ("utf-8", "utf-16le", "utf-16be"))
    failures = collections.Counter()
    counts = {"files": 0, "embedded_entries": 0}
    locations = set()

    def check_bytes(data, label):
        if any(value in data for value in forbidden):
            failures["BUILDER_PRIVATE_PATH"] += 1
            # Report only safe package-relative module labels, never matched contents.
            if label and not label.startswith("/") and not _state_name(label) and not any(
                value in label.encode("utf-8") for value in forbidden
            ):
                locations.add("".join(character for character in label if character.isprintable())[:200])

    def check_zip(data, label):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in archive.infolist():
                    if _state_name(entry.filename):
                        failures["PRIVATE_STATE_FILE"] += 1
                    if not entry.is_dir():
                        counts["embedded_entries"] += 1
                        check_bytes(archive.read(entry), f"{label}!{entry.filename}")
        except (OSError, ValueError, zipfile.BadZipFile):
            failures["UNREADABLE_EMBEDDED_ARCHIVE"] += 1

    def check_pyinstaller(path, label):
        try:
            from PyInstaller.archive.readers import CArchiveReader

            archive = CArchiveReader(str(path))
            for name in archive.toc:
                if _state_name(name):
                    failures["PRIVATE_STATE_FILE"] += 1
                data = archive.extract(name)
                counts["embedded_entries"] += 1
                check_bytes(data, f"{label}!{name}")
                if data.startswith(b"PYZ\0"):
                    offset = struct.unpack("!i", data[8:12])[0]
                    modules = dict(marshal.loads(data[offset:]))
                    for module, (_, position, size) in modules.items():
                        if size:
                            payload = zlib.decompress(data[position:position + size])
                            counts["embedded_entries"] += 1
                            check_bytes(payload, f"{label}!{module}")
        except Exception:
            # Inspecting code archives must not execute their bytecode or silently skip errors.
            failures["UNREADABLE_EMBEDDED_ARCHIVE"] += 1

    for path in folder.rglob("*"):
        relative = path.relative_to(folder)
        if _state_name(relative.as_posix()):
            failures["PRIVATE_STATE_FILE"] += 1
        if resource_policy is None:
            if relative.parts[0] not in _ROOT_DIRECTORIES | _ROOT_FILES:
                failures["UNEXPECTED_PACKAGE_RESOURCE"] += 1
            if relative.parts[0] == "docs" and len(relative.parts) > 1 and relative.parts[1] not in _DOC_FILES:
                failures["UNEXPECTED_DOCUMENT"] += 1
        elif not resource_policy(relative):
            failures["UNEXPECTED_PACKAGE_RESOURCE"] += 1
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                if not path.resolve(strict=True).is_relative_to(folder):
                    failures["OUTSIDE_PACKAGE_LINK"] += 1
                continue
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                failures["UNEXPECTED_FILE_TYPE"] += 1
                continue
            counts["files"] += 1
            image_allowed = (
                image_policy(relative) if image_policy is not None
                else relative.parts[:2] == ("_internal", "playwright")
            )
            if path.suffix.casefold() in _IMAGE_SUFFIXES and not image_allowed:
                failures["UNEXPECTED_USER_IMAGE"] += 1
            data = path.read_bytes()
            check_bytes(data, relative.as_posix())
            if path.suffix.casefold() == ".zip":
                check_zip(data, relative.as_posix())
            if _PYINSTALLER_MAGIC in data[-65536:]:
                check_pyinstaller(path, relative.as_posix())
        except (OSError, ValueError):
            failures["UNREADABLE_PACKAGE_RESOURCE"] += 1
    if failures:
        raise PackagePrivacyError(failures, sorted(locations))
    if counts["files"] == 0:
        raise PackagePrivacyError({"EMPTY_PACKAGE_DIRECTORY": 1})
    return counts


def build_archive(folder, destination, *, private_prefixes=None):
    """Audit and atomically create an archive with anonymous, stable metadata."""
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    if destination.is_relative_to(folder):
        raise PackagePrivacyError({"UNSAFE_ARCHIVE_DESTINATION": 1})
    result = audit_package(folder, private_prefixes=private_prefixes)
    descriptor, temporary = tempfile.mkstemp(prefix=".wechat-emoji-archive-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as output:
                    output.add(folder, arcname="wechat-emoji", filter=sanitized_tarinfo)
        os.replace(temporary, destination)
        write_checksum(destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result


def build_zip(folder, destination, *, private_prefixes=None, resource_policy, image_policy):
    """Audit a source kit/app and write a portable ZIP without local owner metadata."""
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    if destination.is_relative_to(folder):
        raise PackagePrivacyError({"UNSAFE_ARCHIVE_DESTINATION": 1})
    result = audit_package(
        folder, private_prefixes=private_prefixes,
        resource_policy=resource_policy, image_policy=image_policy,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".wechat-emoji-zip-", dir=destination.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for source in [folder, *sorted(folder.rglob("*"))]:
                relative = source.relative_to(folder.parent).as_posix()
                mode = source.lstat().st_mode
                is_link = stat.S_ISLNK(mode)
                is_directory = stat.S_ISDIR(mode)
                name = relative + ("/" if is_directory else "")
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                if is_directory:
                    info.external_attr |= 0x10
                    archive.writestr(info, b"")
                elif is_link:
                    target = os.readlink(source)
                    if Path(target).is_absolute() or not source.resolve(strict=True).is_relative_to(folder):
                        raise PackagePrivacyError({"OUTSIDE_PACKAGE_LINK": 1})
                    archive.writestr(info, target.encode("utf-8"))
                elif stat.S_ISREG(mode):
                    with source.open("rb") as incoming, archive.open(info, "w", force_zip64=True) as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                else:
                    raise PackagePrivacyError({"UNEXPECTED_FILE_TYPE": 1})
        os.replace(temporary, destination)
        write_checksum(destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result


def write_checksum(archive):
    """Refresh a SHA256 sidecar only after the corresponding archive is complete."""
    archive = Path(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    destination = archive.with_name(archive.name + ".sha256")
    descriptor, temporary = tempfile.mkstemp(prefix=".wechat-emoji-sha256-", dir=archive.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(f"{digest.hexdigest()}  {archive.name}\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
