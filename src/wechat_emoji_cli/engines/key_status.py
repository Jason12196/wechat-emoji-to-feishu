"""Read-only cached-key verification; never expose key material to callers."""

import hashlib
import hmac
import re
from pathlib import Path


def cached_key_valid(database: Path, wxid: str, cache: Path | None = None) -> bool:
    cache = cache or (
        Path.home()
        / "Library/Containers/com.tencent.xinWeChat/Data/Documents/export-wechat-emoji"
    )
    try:
        with database.open("rb") as stream:
            page = stream.read(4096)
        if len(page) != 4096:
            return False
        if page.startswith(b"SQLite format 3"):
            return True
        for name in (f"emoticon_dbkey_{wxid}.txt", "emoticon_dbkey.txt"):
            path = cache / name
            if not path.is_file():
                continue
            value = path.read_text().splitlines()[0].strip()
            match = re.fullmatch(r"(?:x')?([0-9a-fA-F]{64})(?:')?", value)
            if not match:
                continue
            raw = bytes.fromhex(match[1])
            salt = page[:16]
            mac_salt = bytes(byte ^ 0x3A for byte in salt)
            for key in (raw, hashlib.pbkdf2_hmac("sha512", raw, salt, 256000, 32)):
                mac_key = hashlib.pbkdf2_hmac("sha512", key, mac_salt, 2, 32)
                actual = hmac.new(mac_key, page[16:4032] + b"\x01\0\0\0", "sha512").digest()
                if hmac.compare_digest(actual, page[4032:]):
                    return True
    except (OSError, ValueError, IndexError):
        return False
    return False
