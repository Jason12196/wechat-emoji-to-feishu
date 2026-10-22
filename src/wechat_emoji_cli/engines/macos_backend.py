"""macOS adapter for the separately distributed wxemoticon CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import config


def data_root() -> Path:
    return Path(config.WECHAT_FILES_ROOT)


def cli_path() -> str:
    candidate = os.environ.get("WXEMOTICON_BIN")
    bundled = Path(config.APP_DIR) / "bin/wxemoticon"
    if not candidate and bundled.is_file():
        candidate = str(bundled)
    candidate = candidate or shutil.which("wxemoticon")
    if not candidate:
        raise RuntimeError("未找到 Mac 提取工具，请设置 WXEMOTICON_BIN 或安装 wxemoticon。")
    return candidate


def accounts() -> list[dict]:
    running = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True).returncode == 0
    root = data_root()
    return [
        dict(wxid=p.name, wx_dir=str(p), running=running, pid=0, nickname="", key="")
        for p in sorted(root.glob("wxid_*"))
        if (p / "db_storage/emoticon/emoticon.db").is_file()
    ]


def run_cli(arguments: list[str], report=None, pause_event=None) -> None:
    import signal
    import tempfile
    import time

    command = [cli_path(), "--no-interactive", "--wechat-data-dir", str(data_root()), *arguments]
    # Capture potentially private tool output in an anonymous temporary file.
    with tempfile.TemporaryFile(mode="w+t") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
        paused = False
        deadline = time.monotonic() + 3600
        try:
            while child.poll() is None:
                wants_pause = pause_event is not None and not pause_event.is_set()
                if wants_pause != paused:
                    os.kill(child.pid, signal.SIGSTOP if wants_pause else signal.SIGCONT)
                    paused = wants_pause
                if time.monotonic() > deadline:
                    raise TimeoutError("Mac 提取超时，请重试未完成资源。")
                time.sleep(0.2)
            if child.returncode:
                log.seek(0)
                directory = Path(config.DEBUG_DIR)
                directory.mkdir(parents=True, exist_ok=True)
                diagnostic = directory / "mac-extraction.log"
                fd = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(log.read())
                raise RuntimeError(
                    "Mac 提取失败；首次使用请退出微信后运行 wxemoticon key，详细原因已记录到本地诊断日志。"
                )
        finally:
            if child.poll() is None:
                if paused:
                    os.kill(child.pid, signal.SIGCONT)
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    if report:
        report("[Mac] 提取工具已完成，正在逐张验证图片。")


def extract(wxid=None, output_dir=None, process=True, progress_callback=None, **kwargs):
    import tempfile

    from .macos_resources import export_verified

    destination = Path(output_dir or config.EMOJI_OUTPUT_DIR)
    raw = destination / "originals"
    raw.mkdir(parents=True, exist_ok=True)

    def report(message):
        if progress_callback:
            progress_callback(0, 0, message)
        else:
            print(message)

    with tempfile.TemporaryDirectory(prefix="wxemoji_metadata_") as private:
        urls, metadata = Path(private) / "urls.txt", Path(private) / "metadata.json"
        args = ["urls", "--out", str(urls), "--metadata-out", str(metadata)]
        if wxid:
            args += ["--wxid", wxid]
        run_cli(args, pause_event=kwargs.get("pause_event"))
        run_cli(
            [
                "export",
                "--urls-file",
                str(urls),
                "--flat",
                "--skip-existing",
                "--out-dir",
                str(raw),
            ],
            report,
            kwargs.get("pause_event"),
        )
        valid = export_verified(
            raw,
            destination,
            urls.read_text().splitlines(),
            json.loads(metadata.read_text()),
            process,
            report,
            kwargs.get("pause_event"),
        )
    report(f"[Mac] 可导入图片 {len(valid)} 张；详情见 export-report.json。")
    return valid


def audit(wxid=None, sample_downloads=5, callback=None):
    import tempfile

    from .macos_resources import export_verified

    directory = Path(tempfile.mkdtemp(prefix="wxemoji_mac_audit_"))
    urls, metadata = directory / "urls.txt", directory / "metadata.json"
    args = ["urls", "--out", str(urls), "--metadata-out", str(metadata)]
    if wxid:
        args += ["--wxid", wxid]
    try:
        run_cli(args)
        lines = urls.read_text().splitlines()
        sample = directory / "sample.txt"
        sample.write_text("\n".join(lines[:sample_downloads]) + "\n")
        files = []
        if sample_downloads:
            raw = directory / "originals"
            run_cli(["export", "--urls-file", str(sample), "--out-dir", str(raw), "--flat"])
            files = export_verified(
                raw,
                directory / "verified",
                lines[:sample_downloads],
                json.loads(metadata.read_text()),
                False,
                callback,
            )
        return dict(
            ok=bool(lines)
            and (not sample_downloads or len(files) == min(sample_downloads, len(lines))),
            wxid=wxid or (accounts()[0]["wxid"] if len(accounts()) == 1 else ""),
            emoji_rows=len(lines),
            sample_downloaded=len(files),
            sample_dir=str(directory),
            message="Mac 数据库查询与样本解码完成",
        )
    except Exception as exc:
        return dict(ok=False, message=str(exc), emoji_rows=0, sample_downloaded=0)
    finally:
        metadata.unlink(missing_ok=True)
