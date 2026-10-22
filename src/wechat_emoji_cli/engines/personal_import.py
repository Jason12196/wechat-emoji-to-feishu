"""Batched personal sticker uploads with conservative, durable resume records."""

import hashlib
import json
import os
import time
from pathlib import Path


def upload(uploader, files, stop_check=None, batch_size=10, ledger_path=None):
    ledger_path = ledger_path or os.environ.get("WECHATEMOJI_IMPORT_LEDGER")
    if ledger_path is None:
        from . import config

        ledger_path = Path(config.DATA_DIR) / "imports" / f"{time.time_ns()}.json"
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}

    def save():
        tmp = ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        tmp.replace(ledger_path)

    jobs = []
    seen = set()
    prior_unknown = sum(r.get("status") in {"pending", "unknown"} for r in state.values())
    skipped = 0
    for name in files:
        p = Path(name)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in state or digest in seen:
            skipped += 1
            continue
        seen.add(digest)
        jobs.append((str(p), digest))
    success = 0
    for offset in range(0, len(jobs), batch_size):
        if stop_check and stop_check():
            break
        batch = jobs[offset : offset + batch_size]
        uploader._try_open_first_chat()
        if not uploader._open_emoji_panel():
            uploader._screenshot("import_panel_unavailable")
            uploader._report("[错误] 未找到个人表情添加入口；已停止，尚未提交本批文件。")
            return dict(
                success=success,
                failed=0,
                unknown=prior_unknown,
                remaining=len(jobs) - offset,
                skipped=skipped,
                ledger=str(ledger_path),
            )
        before = set(uploader._capture_custom_sticker_signature(limit=10000))
        try:
            with uploader._page.expect_file_chooser(timeout=5000) as event:
                uploader._try_click_add_emoji()
            chooser = event.value
            if len(batch) > 1 and not chooser.is_multiple():
                raise RuntimeError("当前上传入口仅支持单文件，请使用单文件批次")
            for path, digest in batch:
                state[digest] = {"file": Path(path).name, "status": "pending"}
            save()
            chooser.set_files([path for path, digest in batch])
            uploader._page.wait_for_timeout(800)
            uploader._try_confirm_upload()
            deadline = time.monotonic() + 60
            new = set()
            while time.monotonic() < deadline:
                uploader._page.wait_for_timeout(500)
                current = set(uploader._capture_custom_sticker_signature(limit=10000))
                new = current - before
                if len(new) >= len(batch):
                    break
            confirmed = len(new) >= len(batch)
            status = "confirmed" if confirmed else "unknown"
            for _, digest in batch:
                state[digest]["status"] = status
            save()
            if not confirmed:
                uploader._screenshot("import_batch_unconfirmed")
                uploader._report(
                    f"[警告] 本批 {len(batch)} 个结果不明确（可见新增 {len(new)} 个），已停止，禁止自动重试。"
                )
                return dict(
                    success=success,
                    failed=0,
                    unknown=prior_unknown + len(batch),
                    remaining=len(jobs) - offset - len(batch),
                    skipped=skipped,
                    ledger=str(ledger_path),
                )
            success += len(batch)
            uploader._report(f"[上传] 已确认 {success}/{len(jobs)} 个新增表情", success, len(jobs))
        except Exception as exc:
            # A recorded pending batch may have reached the server: never automatically resubmit it.
            uploader._screenshot("import_batch_error")
            uploader._report(f"[错误] 批次中断：{exc}")
            return dict(
                success=success,
                failed=0,
                unknown=prior_unknown
                + sum(state.get(d, {}).get("status") == "pending" for _, d in batch),
                remaining=len(jobs) - offset,
                skipped=skipped,
                ledger=str(ledger_path),
            )
    return dict(
        success=success,
        failed=0,
        unknown=prior_unknown,
        remaining=max(0, len(jobs) - success),
        skipped=skipped,
        ledger=str(ledger_path),
    )
