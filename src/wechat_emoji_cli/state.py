"""Atomic task records and the versioned stdout event protocol."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def write_private(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


class Task:
    def __init__(self, home, command, json_mode=False):
        self.id = str(uuid.uuid4())
        self.path = Path(home) / "tasks" / f"{self.id}.json"
        self.stream = sys.stdout
        self.json_mode = json_mode
        self.record = {"id": self.id, "command": command, "status": "running"}
        self.emit("started", command=command)

    def emit(self, kind, **data):
        event = {
            "protocol_version": 1,
            "task_id": self.id,
            "type": kind,
            "time": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        if self.json_mode:
            print(json.dumps(event, ensure_ascii=False), file=self.stream, flush=True)
        elif kind in {"progress", "action_required"}:
            print(data.get("message", kind), file=self.stream, flush=True)
        elif kind in {"result", "error"}:
            print(json.dumps(data, ensure_ascii=False, indent=2), file=self.stream, flush=True)

    def progress(self, current, total, message):
        # Do not forward raw URLs/keys from an upstream log as UI events.
        if "http://" in message or "https://" in message:
            message = "Upstream browser operation reported a diagnostic; see local logs."
        self.emit("progress", current=current, total=total, message=message)

    def finish(self, result, status="complete", code=None):
        self.record.update(status=status, result=result)
        if code:
            self.record["code"] = code
        write_private(self.path, self.record)
        self.emit(
            "result" if status in {"complete", "partial"} else "error",
            status=status,
            code=code,
            result=result,
        )
