"""Version-matched browser provisioning shared by source and frozen builds."""

import os
import subprocess
from pathlib import Path

from .engines import config


def cache_root():
    return Path(os.environ.get("WECHAT_EMOJI_BROWSER_CACHE", config.PLAYWRIGHT_USER_DIR)).expanduser()


def activate():
    root = cache_root()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root)
    return root


def ready():
    activate()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        return Path(driver.chromium.executable_path).is_file()


def ensure(report=None, verify=False):
    root = activate()
    if not ready():
        from playwright._impl._driver import compute_driver_executable, get_driver_env

        root.mkdir(parents=True, exist_ok=True)
        node, cli = compute_driver_executable()
        for attempt in range(1, 3):
            if report:
                report(f"首次使用需要下载 Chromium，尝试 {attempt}/2；缓存：{root}")
            with subprocess.Popen(
                [str(node), str(cli), "install", "chromium"],
                env=get_driver_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace",
            ) as process:
                try:
                    for line in process.stdout:
                        if report:
                            report(line.rstrip())
                    code = process.wait()
                except BaseException:
                    process.terminate()
                    process.wait()
                    raise
            if code == 0 and ready():
                break
        else:
            raise RuntimeError(
                "Chromium 下载失败；请检查网络后重新运行 wechat-emoji browser install。"
                f"已下载缓存保留在 {root}"
            )
    if verify:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True, channel="chromium")
            browser.close()
    return {"ready": True, "cache": str(root), "launch_verified": verify}
