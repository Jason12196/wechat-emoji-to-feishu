"""Validate, decrypt and prepare wxemoticon resources without changing originals."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
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
    raw, destination = Path(raw), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    lookup = {}
    for row in metadata:
        for name, value in row.items():
            if name.endswith("url") and value:
                lookup.setdefault(resource_id(value), []).append(row)
    sources = {
        p.stem: p
        for p in raw.iterdir()
        if p.is_file() and p.suffix.lower() in {".gif", ".jpg", ".jpeg", ".png", ".webp"}
    }

    def one(job):
        if pause_event is not None:
            pause_event.wait()
        index, url = job
        identity = resource_id(url, index)
        entry = {"resource": identity, "status": "failed"}
        source = sources.get(identity)
        data = source.read_bytes() if source else b""
        candidates = lookup.get(identity, [])

        def usable(value):
            try:
                decode(value)
                return value
            except Exception:
                return None

        result = usable(data)
        recovery = "original"
        if result is None:
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
        if result is None:
            seen = {url} if source else set()
            alternatives = [(url, None)] if not source else []
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
                    if result is None and key_hex and len(value) % 16 == 0:
                        key = bytes.fromhex(key_hex)
                        if len(key) == 16:
                            result = usable(AES.new(key, AES.MODE_CBC, key).decrypt(value))
                    if result is not None:
                        recovery = "alternate_download"
                        break
                except Exception:
                    continue
        if result is None:
            entry["reason"] = "No decodable resource after local decryption and alternate download"
            return entry
        fmt, size, frames = decode(result)
        ext = {"GIF": "gif", "PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
        verified = destination / "verified-originals"
        verified.mkdir(exist_ok=True)
        (verified / f"{identity}.{ext}").write_bytes(result)
        entry.update(
            recovery=recovery,
            original_bytes=len(result),
            frames=frames,
            width=size[0],
            height=size[1],
        )
        try:
            prepared = prepare(result) if process else result
            target = destination / f"{identity}.{ext}"
            target.write_bytes(prepared)
            out_fmt, out_size, out_frames = decode(prepared)
            entry.update(
                status="ready",
                file=target.name,
                bytes=len(prepared),
                output_frames=out_frames,
                output_width=out_size[0],
                output_height=out_size[1],
            )
        except Exception as exc:
            entry.update(status="preparation_failed", reason=str(exc))
        return entry

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entry in pool.map(one, enumerate(urls)):
            results.append(entry)
            if report and len(results) % 50 == 0:
                report(f"[Mac] 已验证 {len(results)}/{len(urls)}")
    summary = {
        "total": len(urls),
        "ready": sum(r["status"] == "ready" for r in results),
        "failed": sum(r["status"] != "ready" for r in results),
        "files": results,
    }
    (destination / "export-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    return [str(destination / r["file"]) for r in results if r["status"] == "ready"]
