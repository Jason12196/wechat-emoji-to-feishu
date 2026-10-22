"""Batched personal sticker uploads with conservative, durable resume records."""

import hashlib
import json
import os
import time
from pathlib import Path

from ..state import write_private
from . import config


def upload(uploader, files, stop_check=None, batch_size=10, ledger_path=None):
    ledger_path = ledger_path or os.environ.get("WECHATEMOJI_IMPORT_LEDGER")
    if ledger_path is None:
        ledger_path = Path(config.DATA_DIR) / "imports" / f"{time.time_ns()}.json"
    ledger_path = Path(ledger_path)
    state = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    if not isinstance(state, dict):
        raise ValueError("导入记录格式无效，请保留原记录并检查诊断信息。")
    # Even a failed preflight must leave an explicit empty ledger: no browser
    # readiness failure can then be mistaken for an upload with unknown results.
    if not ledger_path.exists():
        write_private(ledger_path, state)

    def save():
        write_private(ledger_path, state)

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
    submitted = 0

    def stopped():
        return bool(stop_check and stop_check())

    def result(blocked=None):
        statuses = [state.get(digest, {}).get("status") for _, digest in jobs]
        value = dict(
            success=sum(status == "confirmed" for status in statuses),
            failed=0,
            unknown=prior_unknown + sum(status in {"pending", "unknown"} for status in statuses),
            remaining=sum(status is None for status in statuses),
            skipped=skipped,
            submitted=submitted,
            ledger=str(ledger_path),
        )
        if blocked:
            value["blocked"] = blocked
        return value

    def block(code, message, screenshot):
        uploader._screenshot(screenshot)
        uploader._report(f"[错误] {message} 尚未提交的文件可在页面恢复后继续。")
        return result({"code": code, "message": message})

    if not jobs:
        return result()
    uploader._report("[准备] 正在等待飞书会话列表加载（最多 3 分钟），尚未提交任何图片…")
    if not uploader._wait_for_messenger_ready(timeout_ms=config.MESSENGER_READY_TIMEOUT, stop_check=stop_check):
        if stopped():
            return result({"code": "CANCELLED", "message": "已取消等待飞书页面，尚未提交图片。"})
        return block("MESSENGER_LOADING_TIMEOUT",
                     "飞书已登录，但会话列表或聊天编辑器在 3 分钟内仍未加载。请在浏览器中确认页面已正常显示后继续。",
                     "messenger_loading_timeout")
    uploader._report("[准备] 正在等待聊天输入框加载（最多 90 秒），不会发送聊天消息…")
    if not uploader._try_open_first_chat(timeout_ms=config.WRITABLE_CHAT_TIMEOUT, stop_check=stop_check):
        if stopped():
            return result({"code": "CANCELLED", "message": "已取消查找可用会话，尚未提交图片。"})
        return block("NO_WRITABLE_CONVERSATION",
                     "飞书会话列表已加载，但未找到可输入消息的会话。请在浏览器中打开一个正常会话后继续；工具不会发送消息。",
                     "no_writable_conversation")
    for offset in range(0, len(jobs), batch_size):
        if stopped():
            return result({"code": "CANCELLED", "message": "已取消导入，未提交文件保留为待继续。"})
        batch = jobs[offset : offset + batch_size]
        if not uploader._open_emoji_panel(timeout_ms=config.STICKER_PANEL_TIMEOUT, stop_check=stop_check) or not uploader._has_personal_sticker_add_entry():
            if stopped():
                return result({"code": "CANCELLED", "message": "已取消等待个人表情面板，尚未提交图片。"})
            return block("STICKER_PANEL_UNAVAILABLE",
                         "聊天编辑器已就绪，但等待 3 分钟后仍未找到个人表情添加入口。请在浏览器中展开个人表情面板后继续。",
                         "import_panel_unavailable")
        if stopped():
            return result({"code": "CANCELLED", "message": "已取消导入，尚未提交本批图片。"})
        before = set(uploader._capture_custom_sticker_signature(limit=10000))
        try:
            with uploader._page.expect_file_chooser(timeout=5000) as event:
                uploader._try_click_add_emoji()
            chooser = event.value
            if len(batch) > 1 and not chooser.is_multiple():
                raise RuntimeError("当前上传入口仅支持单文件，请使用单文件批次")
            if stopped():
                return result({"code": "CANCELLED", "message": "已取消导入，尚未提交本批图片。"})
            for path, digest in batch:
                state[digest] = {"file": Path(path).name, "status": "pending"}
            save()
            submitted += len(batch)
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
                return result()
            success = result()["success"]
            uploader._report(f"[上传] 已确认 {success}/{len(jobs)} 个新增表情", success, len(jobs))
        except Exception as exc:
            # Only the persisted pending batch is ambiguous. Unsubmitted files
            # remain resumable and must not also be included in unknown counts.
            uploader._screenshot("import_batch_error")
            uploader._report(f"[错误] 批次中断：{exc}")
            return result()
    return result()
