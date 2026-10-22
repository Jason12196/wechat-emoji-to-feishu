"""Select importable files without recursively importing preserved originals."""

import json
from pathlib import Path

from . import config


def collect_emoji_files(folder):
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("Image directory does not exist")
    report = root / "export-report.json"
    if report.is_file():
        rows = json.loads(report.read_text()).get("files", [])
        return sorted(
            str(root / row["file"])
            for row in rows
            if row.get("status") == "ready"
            and Path(row["file"]).name == row["file"]
            and (root / row["file"]).is_file()
        )
    return sorted(
        str(p)
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in config.FEISHU_EMOJI_FORMATS
    )
