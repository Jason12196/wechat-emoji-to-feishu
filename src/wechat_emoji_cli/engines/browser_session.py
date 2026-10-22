"""Attach to an account's independently running Chromium without owning its life."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

_BROWSER_PATH = re.compile(
    r"/devtools/browser/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_MESSENGER_PATH = re.compile(r"/(?:messenger|im)(?:/|$)")
_BLANK_PAGES = {"", "about:blank", "chrome://newtab/", "chrome://new-tab-page/"}


def _endpoint(profile: Path):
    active = profile / "DevToolsActivePort"
    if active.is_symlink() or not active.is_file():
        return None
    try:
        # Chromium writes two short lines. Reject unexpected files instead of
        # accepting arbitrary URLs, hosts, credentials, or websocket routes.
        with active.open("rb") as stream:
            value = stream.read(1025)
        if len(value) > 1024:
            return None
        lines = value.decode("ascii").splitlines()
        if len(lines) != 2 or not re.fullmatch(r"[0-9]{1,5}", lines[0]):
            return None
        port = int(lines[0])
        if not 1 <= port <= 65535 or not _BROWSER_PATH.fullmatch(lines[1]):
            return None
        # The UUID-bearing route also prevents attaching to a different browser
        # that later happens to reuse an old port.
        return f"ws://127.0.0.1:{port}{lines[1]}"
    except (OSError, UnicodeError, ValueError):
        return None


def _messenger_page(page) -> bool:
    try:
        if page.is_closed():
            return False
        address = urlsplit(page.url)
        host = (address.hostname or "").lower()
        trusted = any(host == domain or host.endswith("." + domain)
                      for domain in ("feishu.cn", "larksuite.com"))
        if address.scheme != "https" or not trusted:
            return False
        return bool(_MESSENGER_PATH.search(address.path)
                    or _MESSENGER_PATH.search(address.fragment))
    except Exception:
        return False


def _choose_page(browser):
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("未找到飞书专用浏览器会话，请关闭旧版飞书登录窗口后重试。")
    context = contexts[0]
    pages = context.pages
    for page in pages:
        if _messenger_page(page):
            return context, page
    for page in pages:
        try:
            if not page.is_closed() and page.url in _BLANK_PAGES:
                return context, page
        except Exception:
            continue
    return context, context.new_page()


def _connect(driver, profile, timeout=10000):
    endpoint = _endpoint(profile)
    if endpoint is None:
        return None
    try:
        browser = driver.chromium.connect_over_cdp(endpoint, timeout=timeout)
    except Exception:
        # CDP error text can include its private endpoint. Never surface it.
        return None
    try:
        context, page = _choose_page(browser)
    except Exception:
        raise RuntimeError(
            "已连接飞书专用浏览器，但无法访问其页面。请手动关闭专用窗口后重试；登录资料会保留。"
        ) from None
    return browser, context, page


def attach_or_launch(driver, profile, report=None):
    """Return ``(browser, context, page, reused)`` without closing Chromium.

    The caller may stop its Playwright driver when its command ends. It must
    leave this external browser and its persistent default context open so the
    following CLI command can attach to the same loaded Feishu page.
    """
    profile = Path(profile).expanduser().absolute()
    if profile.is_symlink() or (profile.exists() and not profile.is_dir()):
        raise RuntimeError("飞书专用浏览器目录无效，请检查本地配置后重试。")
    try:
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        profile.chmod(0o700)
    except OSError:
        raise RuntimeError("无法访问飞书专用浏览器目录，请检查目录权限后重试。") from None

    attached = _connect(driver, profile)
    if attached is not None:
        if report:
            report("[浏览器] 已复用飞书窗口，保留当前页面。")
        return (*attached, True)

    try:
        executable = Path(driver.chromium.executable_path)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise OSError("missing browser executable")
        process = subprocess.Popen(
            [
                str(executable),
                f"--user-data-dir={profile}",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                "--no-first-run",
                "--no-default-browser-check",
                # Match the original Playwright persistent context's macOS
                # credential backend so existing cookies stay readable.
                "--password-store=basic",
                "--use-mock-keychain",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        raise RuntimeError("无法启动飞书专用浏览器，请确认 Chromium 已安装且可以运行。") from None

    if report:
        report("[浏览器] 正在打开飞书专用窗口，窗口将在本次操作结束后保留…")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "飞书专用浏览器启动后已退出，可能仍有旧版窗口占用登录目录。"
                "请手动关闭旧版飞书登录窗口一次后重试；已有登录资料会保留。"
            )
        timeout = max(1, min(10000, int((deadline - time.monotonic()) * 1000)))
        attached = _connect(driver, profile, timeout)
        if attached is not None:
            return (*attached, False)
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    # Never kill the independently running browser or clear its profile/cookies.
    raise RuntimeError(
        "等待飞书专用浏览器连接超过 45 秒。请检查新窗口是否正常打开；"
        "如仍有旧版飞书登录窗口，请手动关闭一次后重试。已有登录资料会保留。"
    )
