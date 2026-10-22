"""Private, task-correlated exception diagnostics with share-safe text."""

import platform
import re
import sys
import time
import traceback
from pathlib import Path

from .state import write_private


def redact(text):
    text = re.sub(r"https?://[^\s\"'<>]+", "[resource URL hidden]", str(text))
    text = re.sub(r"\b[0-9a-fA-F]{64,}\b", "[key or digest hidden]", text)
    text = re.sub(r"\b(?:gh[pousr]_\w+|github_pat_\w+)\b", "[token hidden]", text)
    text = re.sub(
        r"((?:cookie|authorization|token|password|db_key|secret)\s*[=:]\s*)[^\r\n]+",
        r"\1[hidden]", text, flags=re.IGNORECASE,
    )
    return re.sub(r"wxid_[\w-]+", "[WeChat account]", text)


def record_exception(task, exc, command, debug):
    target = Path(debug) / f"{task.id}.json"
    value = {
        "task_id": task.id, "command": command, "time": time.time(),
        "exception_type": type(exc).__name__, "message": redact(exc),
        "traceback": redact(traceback.format_exc()), "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    native = Path(debug) / "mac-extraction.log"
    try:
        if command in {"extract", "key"} and native.is_file() and native.stat().st_mtime >= task.started:
            value["engine_log_tail"] = redact(native.read_text(errors="replace")[-32000:])
    except OSError as log_error:
        value["engine_log_read_error"] = redact(log_error)
    try:
        write_private(target, value)
        return str(target)
    except OSError:
        return None
