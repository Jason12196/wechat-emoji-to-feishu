"""飞书表情上传模块。

策略：
- 优先全自动：通过 Playwright 模拟点击表情面板，自动注入文件
- 自动失败时退回半自动：浏览器打开飞书后引导用户手动点到上传对话框，
  工具监控到 file-input 出现后自动注入文件，不需要用户选文件
- 截图调试：每次操作失败都保存截图到 config.DEBUG_DIR 便于排查
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import config

ProgressCallback = Optional[Callable[[int, int, str], None]]
StopCheck = Optional[Callable[[], bool]]

# ── 聊天侧边栏会话项（点进去触发输入框）──
_SIDEBAR_CHAT_SELECTORS = (
    ".feed-main-list .a11y_feed_card_item",
    ".a11y_feed_card_item",
    ".a11y_feed_card_main",
    '[class*="feed_card_item"]',
    # 飞书 2024/2025 web 常见结构
    '[data-testid="im-message-list-item"]',
    '[class*="chat-item--"]',
    '[class*="session-item"]',
    '[class*="conversation-item"]',
    '[class*="im-list"] [class*="item"]',
    # 通用回退
    '[role="listitem"]',
)

# ── 消息输入框工具栏里的表情/贴纸按钮 ──
# 2025/04 实测：飞书工具栏容器类为 .lark__editor--toolbar，
# 表情/贴纸是第2个 div 里的按钮（tooltip="表情"）。
# 点击后直接显示自定义贴纸面板，无需切换 tab。
_EMOJI_BTN_SELECTORS = (
    ".lark__editor--toolbar > div:nth-child(2) button",
    ".lark__editor--toolbar > div:nth-child(2) > div > .ud__button",
    '[class*="lark__editor--toolbar"] > div:nth-child(2) button',
    # 宽松回退
    '[class*="lark__editor"] button:nth-of-type(2)',
    '[class*="toolbar"] button:nth-of-type(2)',
)

# ── 表情面板里"自定义"tab（飞书点击表情按钮直接进自定义面板，通常不需要）──
_CUSTOM_TAB_SELECTORS = (
    ".emoji button.ud__button--icon.ud__button--icon-size-md",
    '[role="tab"]:has-text("自定义")',
    '[role="tab"]:has-text("贴纸")',
    'div[class*="tab"]:has-text("自定义")',
    'button:has-text("自定义")',
)

# ── 自定义贴纸面板里的"添加"按钮 ──
# 2025/04 实测：添加贴纸按钮稳定类名为 add-sticker-btn
_ADD_BTN_SELECTORS = (
    ".add-sticker-btn",
    '[class*="add-sticker-btn"]',
    ".customized-sticker-item.add-sticker-btn",
    '.emoji [class*="add-btn"]',
    '.customized-sticker-panel button:has-text("+")',
)

# ── 上传后的确认按钮 ──
_CONFIRM_SELECTORS = (
    'button:has-text("确定")',
    'button:has-text("完成")',
    'button:has-text("确认")',
    'button:has-text("保存")',
    'button:has-text("上传")',
    'button:has-text("发布")',
    'button[type="submit"]',
)

_SUCCESS_TEXTS = ("上传成功", "添加成功", "已添加", "已上传", "保存成功", "创建成功", "发布成功")
_ERROR_TEXTS = (
    "上传失败",
    "添加失败",
    "格式不支持",
    "上传出错",
    "大小超限",
    "数量超限",
    "格式错误",
)

BROWSER_CANDIDATES = (
    {
        "name": "edge",
        "exe": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "user_data": str(Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"),
    },
    {
        "name": "chrome",
        "exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "user_data": str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"),
    },
)


def _activate_browser_runtime_env():
    from ..browser import activate

    return activate()


def _load_playwright() -> tuple[Any, Any]:
    _activate_browser_runtime_env()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "This build is missing the Playwright Python package. "
            "The packaged desktop app should include it already."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


class FeishuUploader:
    """飞书表情上传器。支持全自动和半自动两种模式。"""

    def __init__(self, headless: bool = False, progress_callback: ProgressCallback = None):
        self.headless = headless
        self.progress_callback = progress_callback
        self._playwright_driver = None
        self._browser = None
        self._context = None
        self._page = None
        self._timeout_error = Exception
        self._profile_clone_dir: Optional[str] = None
        self._launch_mode = "playwright"
        self._keep_browser_open = False
        self._debug_dir = config.DEBUG_DIR

    def _report(self, message: str, current: int = 0, total: int = 0) -> None:
        print(message)
        if self.progress_callback:
            self.progress_callback(current, total, message)

    def _screenshot(self, name: str) -> None:
        """保存调试截图到 config.DEBUG_DIR。"""
        if not self._page:
            return
        try:
            os.makedirs(self._debug_dir, exist_ok=True)
            path = os.path.join(self._debug_dir, f"{name}_{int(time.time())}.png")
            self._page.screenshot(path=path)
            self._report(f"[调试] 截图已保存: {path}")
        except Exception:
            pass

    def _stop_requested(self, stop_check: StopCheck) -> bool:
        try:
            return bool(stop_check and stop_check())
        except Exception:
            return False

    # ─────────────────── 浏览器启动 ───────────────────

    def start(self):
        """启动浏览器。优先复用本机 Edge/Chrome 登录态。"""
        from ..browser import ensure

        ensure(report=self._report)
        sync_playwright, timeout_error = _load_playwright()
        self._timeout_error = timeout_error
        self._playwright_driver = sync_playwright().start()
        if sys.platform == "darwin" and not self.headless:
            from .browser_session import attach_or_launch

            profile = Path(config.DATA_DIR) / "feishu-browser"
            try:
                self._browser, self._context, self._page, reused = attach_or_launch(
                    self._playwright_driver, profile, self._report,
                )
            except Exception:
                try:
                    self._playwright_driver.stop()
                except Exception:
                    pass
                self._playwright_driver = None
                raise
            self._keep_browser_open = True
            self._page.set_default_timeout(config.PAGE_TIMEOUT)
            self._launch_mode = "mac-shared-chromium"
            self._report("[浏览器] 已复用当前飞书窗口" if reused else "[浏览器] 飞书窗口已打开，登录后会一直保留")
            return
        if sys.platform == "darwin":
            profile = Path(config.DATA_DIR) / "feishu-browser"
            self._context = self._playwright_driver.chromium.launch_persistent_context(
                str(profile), headless=self.headless, viewport={"width": 1440, "height": 900}
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._page.set_default_timeout(config.PAGE_TIMEOUT)
            self._launch_mode = "mac-persistent-chromium"
            return
        if not self._try_start_with_system_profile():
            self._browser = self._playwright_driver.chromium.launch(headless=self.headless)
            ctx_args: dict = {"viewport": {"width": 1440, "height": 900}}
            self._context = self._browser.new_context(**ctx_args)
            self._page = self._context.new_page()
            self._page.set_default_timeout(config.PAGE_TIMEOUT)
            self._launch_mode = "playwright-chromium"

    def _try_start_with_system_profile(self) -> bool:
        if self.headless:
            return False
        for browser in BROWSER_CANDIDATES:
            executable = Path(browser["exe"])
            user_data_root = Path(browser["user_data"])
            default_profile = user_data_root / "Default"
            local_state = user_data_root / "Local State"
            if not executable.exists() or not default_profile.exists() or not local_state.exists():
                continue
            if _is_browser_running(browser["name"]):
                self._report(
                    f"[信息] {browser['name']} 正在运行中，无法复用配置，改用独立 Chromium 浏览器"
                )
                continue
            clone_dir = Path(tempfile.mkdtemp(prefix=f"{browser['name']}_clone_"))
            try:
                shutil.copy2(local_state, clone_dir / "Local State")
                shutil.copytree(
                    default_profile,
                    clone_dir / "Default",
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(
                        "Cache",
                        "Code Cache",
                        "GPUCache",
                        "DawnCache",
                        "GrShaderCache",
                        "ShaderCache",
                        "Service Worker",
                    ),
                )
                self._context = self._playwright_driver.chromium.launch_persistent_context(
                    str(clone_dir),
                    executable_path=str(executable),
                    headless=False,
                    args=["--profile-directory=Default"],
                    viewport={"width": 1440, "height": 900},
                )
                self._page = (
                    self._context.pages[0] if self._context.pages else self._context.new_page()
                )
                self._page.set_default_timeout(config.PAGE_TIMEOUT)
                self._profile_clone_dir = str(clone_dir)
                self._launch_mode = f"system-profile:{browser['name']}"
                self._report(f"[信息] 已复用 {browser['name']} 登录态（副本）")
                return True
            except Exception as exc:
                self._report(f"[警告] 复用 {browser['name']} 失败: {exc}")
                try:
                    shutil.rmtree(clone_dir, ignore_errors=True)
                except Exception:
                    pass
        return False

    # ─────────────────── 登录检测 ───────────────────

    def login(self, stop_check: StopCheck = None) -> bool:
        """打开飞书，等待用户扫码或检测已有登录态。"""
        self._report(f"[登录] 正在打开飞书…（模式: {self._launch_mode}）")
        if self._keep_browser_open and self._is_logged_in():
            self._report("[登录] 当前窗口已登录，保留当前页面并继续")
            return True
        try:
            self._page.goto(config.FEISHU_MESSENGER_URL, wait_until="domcontentloaded")
            self._page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        self._page.wait_for_timeout(1500)

        if self._is_logged_in():
            self._report("[登录] 已检测到登录态，无需扫码")
            return True

        self._report(
            "[登录] 请在弹出的浏览器窗口中扫码登录飞书，"
            f"登录完成后工具会自动继续（最多等待 {config.LOGIN_TIMEOUT // 1000} 秒）"
        )
        deadline = time.time() + config.LOGIN_TIMEOUT / 1000
        while time.time() < deadline:
            if self._stop_requested(stop_check):
                self._report("[信息] 登录等待已由用户中止")
                return False
            if self._is_logged_in():
                self._report("[登录] 登录成功")
                return True
            self._page.wait_for_timeout(1500)

        self._report("[错误] 登录超时，请重试")
        return False

    def _is_logged_in(self) -> bool:
        if not self._page:
            return False
        try:
            url = self._page.url or ""
            if any(k in url for k in ("accounts.feishu.cn", "/login", "passport", "sso")):
                return False
            if "/messenger/" in url or "/im/" in url:
                # 页面上能找到侧边栏或输入框即视为已登录
                for sel in (
                    '[class*="sidebar"]',
                    '[class*="im-left"]',
                    '[class*="conversation"]',
                    '[contenteditable="true"]',
                ):
                    try:
                        if self._page.locator(sel).first.is_visible():
                            return True
                    except Exception:
                        pass
                # A messenger route alone can still be a blank loading shell.
                return False
        except Exception:
            pass
        return False

    # ─────────────────── 个人表情上传 ───────────────────

    def upload_personal_emojis(self, emoji_files: list[str], stop_check: StopCheck = None) -> dict:
        """Upload batches and stop on any ambiguous outcome."""
        from .personal_import import upload

        return upload(self, emoji_files, stop_check)

    def _writable_editor_visible(self) -> bool:
        if not self._page:
            return False
        try:
            editors = self._page.locator('[contenteditable="true"]')
            for index in range(min(editors.count(), 8)):
                editor = editors.nth(index)
                if editor.is_visible() and editor.is_editable(timeout=150):
                    return True
        except Exception:
            pass
        return False

    def _try_open_first_chat(
        self, timeout_ms: int = config.WRITABLE_CHAT_TIMEOUT, stop_check: StopCheck = None
    ) -> bool:
        """Wait for a writable conversation without rapidly switching chats."""
        if not self._page:
            return False
        deadline = time.monotonic() + timeout_ms / 1000
        attempted = set()
        clicked = 0
        next_attempt = 0.0
        next_report = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self._stop_requested(stop_check):
                return False
            if self._writable_editor_visible():
                return True
            if time.monotonic() >= next_report:
                self._report("[准备] 聊天输入框仍在加载，继续等待；可随时取消。")
                next_report = time.monotonic() + 15
            if clicked < 6 and time.monotonic() >= next_attempt:
                opened = False
                for selector in _SIDEBAR_CHAT_SELECTORS:
                    if opened or time.monotonic() >= deadline or self._stop_requested(stop_check):
                        break
                    try:
                        items = self._page.locator(selector)
                        for index in range(min(items.count(), 10)):
                            identity = (selector, index)
                            if identity in attempted:
                                continue
                            item = items.nth(index)
                            if not item.is_visible():
                                continue
                            attempted.add(identity)
                            item.click(timeout=max(1, min(1000, int((deadline-time.monotonic())*1000))))
                            clicked += 1
                            # Let the selected conversation finish loading before choosing another.
                            next_attempt = time.monotonic() + 15
                            opened = True
                            break
                    except Exception:
                        continue
            try:
                self._page.wait_for_timeout(max(1, min(250, int((deadline-time.monotonic())*1000))))
            except Exception:
                return False
        return False

    def _wait_for_messenger_ready(
        self, timeout_ms: int = config.MESSENGER_READY_TIMEOUT, stop_check: StopCheck = None
    ) -> bool:
        """Wait for real conversation rows or an editor, not a route or avatar."""
        if not self._page:
            return False
        deadline = time.monotonic() + timeout_ms / 1000
        selectors = ('[contenteditable="true"]', *_SIDEBAR_CHAT_SELECTORS[:-1])
        next_report = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self._stop_requested(stop_check):
                return False
            if time.monotonic() >= next_report:
                self._report("[准备] 飞书会话列表仍在加载，继续等待；可随时取消。")
                next_report = time.monotonic() + 15
            for selector in selectors:
                try:
                    if self._page.locator(selector).first.is_visible():
                        return True
                except Exception:
                    pass
            try:
                self._page.wait_for_timeout(max(1, min(200, int((deadline - time.monotonic()) * 1000))))
            except Exception:
                return False
        return False

    def _open_emoji_panel(
        self, timeout_ms: int = config.STICKER_PANEL_TIMEOUT, stop_check: StopCheck = None
    ) -> bool:
        """Wait for the actual add entry, preserving an already open popup."""
        if not self._page:
            return False
        deadline = time.monotonic() + timeout_ms / 1000
        next_report = time.monotonic() + 15
        next_open_attempt = 0.0
        next_tab_attempt = 0.0
        editor_focused = False
        while time.monotonic() < deadline:
            if self._stop_requested(stop_check):
                return False
            if self._has_personal_sticker_add_entry():
                return True
            popup_open = self._is_emoji_popup_visible()
            personal_open = self._is_sticker_panel_visible()
            now = time.monotonic()
            if now >= next_report:
                self._report("[准备] 正在等待个人表情添加入口加载，尚未提交图片；可随时取消。")
                next_report = now + 15
            if personal_open:
                # The panel shell can appear before its contents. Do not close it.
                pass
            elif popup_open:
                if now >= next_tab_attempt:
                    self._switch_personal_sticker_tab(deadline, stop_check)
                    next_tab_attempt = time.monotonic() + 10
            elif now >= next_open_attempt:
                # Only focus/click the toolbar while no emoji popup is visible.
                if not editor_focused:
                    try:
                        editor = self._page.locator('[contenteditable="true"]').first
                        if editor.is_visible():
                            editor.click(timeout=max(1, min(500, int((deadline-time.monotonic())*1000))))
                            editor_focused = True
                    except Exception:
                        pass
                clicked_opener = False
                for selector in _EMOJI_BTN_SELECTORS:
                    if time.monotonic() >= deadline or self._stop_requested(stop_check):
                        return False
                    try:
                        button = self._page.locator(selector).first
                        if not button.is_visible():
                            continue
                        button.click(timeout=max(1, min(1000, int((deadline-time.monotonic())*1000))))
                        clicked_opener = True
                        break
                    except Exception:
                        continue
                # Several selectors may identify the same toggle. Never click them in a burst.
                next_open_attempt = time.monotonic() + (15 if clicked_opener else 0.5)
            try:
                self._page.wait_for_timeout(max(1, min(250, int((deadline-time.monotonic())*1000))))
            except Exception:
                return False
        return False

    def _is_sticker_panel_visible(self) -> bool:
        """检查自定义贴纸面板是否可见。"""
        for sel in (
            ".add-sticker-btn",
            ".customized-sticker-panel",
            '[class*="customized-sticker"]',
        ):
            try:
                if self._page.locator(sel).first.is_visible(timeout=400):
                    return True
            except Exception:
                pass
        return False

    def _is_emoji_popup_visible(self) -> bool:
        for sel in (".emoji", ".emoji-panel-scroller", ".baseEmojiPanel__emojiSets"):
            try:
                if self._page.locator(sel).first.is_visible(timeout=400):
                    return True
            except Exception:
                pass
        return False

    def _switch_personal_sticker_tab(self, deadline=None, stop_check: StopCheck = None) -> bool:
        deadline = deadline if deadline is not None else time.monotonic() + 5
        if time.monotonic() >= deadline or self._stop_requested(stop_check):
            return False
        if self._is_sticker_panel_visible():
            return True
        if not self._is_emoji_popup_visible():
            return False
        try:
            buttons = self._page.locator(".emoji button.ud__button--icon.ud__button--icon-size-md")
            if buttons.count() >= 3:
                buttons.nth(2).click(timeout=max(1, min(700, int((deadline-time.monotonic())*1000))))
                self._page.wait_for_timeout(max(1, min(200, int((deadline-time.monotonic())*1000))))
                if self._is_sticker_panel_visible():
                    return True
        except Exception:
            pass
        self._try_switch_custom_tab(deadline, stop_check)
        return self._is_sticker_panel_visible()

    def _try_switch_custom_tab(self, deadline=None, stop_check: StopCheck = None):
        deadline = deadline if deadline is not None else time.monotonic() + 5
        for selector in _CUSTOM_TAB_SELECTORS:
            if time.monotonic() >= deadline or self._stop_requested(stop_check):
                return
            try:
                buttons = self._page.locator(selector)
                button = buttons.nth(2) if selector.startswith(".emoji button") and buttons.count() >= 3 else buttons.first
                if button.is_visible():
                    button.click(timeout=max(1, min(700, int((deadline-time.monotonic())*1000))))
                    self._page.wait_for_timeout(max(1, min(200, int((deadline-time.monotonic())*1000))))
                    return
            except Exception:
                continue

    def _has_personal_sticker_add_entry(self) -> bool:
        for selector in _ADD_BTN_SELECTORS:
            try:
                if self._page.locator(selector).first.is_visible():
                    return True
            except Exception:
                pass
        return False

    def _try_click_add_emoji(self):
        for sel in _ADD_BTN_SELECTORS:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible():
                    loc.click(timeout=700)
                    return True
            except Exception:
                continue
        return False

    def _try_confirm_upload(self):
        for sel in _CONFIRM_SELECTORS:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click()
                    time.sleep(0.4)
                    return
            except Exception:
                continue

    def _find_file_input(self, timeout: int = 4000, stop_check: StopCheck = None):
        """轮询等待 `input[type=file]` 出现并返回。"""
        if not self._page:
            return None
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            if self._stop_requested(stop_check):
                return None
            try:
                loc = self._page.locator('input[type="file"]')
                if loc.count() > 0:
                    return loc.last
            except Exception:
                pass
            time.sleep(0.3)
        return None

    def _wait_feedback(
        self,
        timeout_ms: int = 8000,
        stop_check: StopCheck = None,
        fail_on_timeout: bool = True,
    ) -> tuple[Optional[bool], str]:
        """等待页面出现成功/失败提示文字。"""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._stop_requested(stop_check):
                return False, "上传已中止"
            try:
                body = self._page.locator("body").inner_text(timeout=1000)
            except Exception:
                body = ""
            if any(t in body for t in _ERROR_TEXTS):
                return False, "检测到上传失败提示，请检查文件格式、大小或飞书权限"
            if any(t in body for t in _SUCCESS_TEXTS):
                return True, "检测到上传成功提示"
            time.sleep(0.4)
        if fail_on_timeout:
            return False, "未检测到明确成功提示，已按失败处理"
        return None, ""

    def _capture_custom_sticker_signature(self, limit: int = 12) -> list[str]:
        if not self._page:
            return []
        try:
            return self._page.evaluate(
                """(limit) => Array
                    .from(document.querySelectorAll('.customized-sticker-item img'))
                    .slice(0, limit)
                    .map(img => img.getAttribute('src') || '')""",
                limit,
            )
        except Exception:
            return []

    def close(self):
        """Detach from shared windows; close only browsers owned by this command."""
        targets = (
            ((self._playwright_driver, "stop"),)
            if self._keep_browser_open
            else (
                (self._context, "close"),
                (self._browser, "close"),
                (self._playwright_driver, "stop"),
            )
        )
        for obj, method in targets:
            if obj:
                try:
                    getattr(obj, method)()
                except Exception:
                    pass
        if self._profile_clone_dir:
            try:
                shutil.rmtree(self._profile_clone_dir, ignore_errors=True)
            except Exception:
                pass
            self._profile_clone_dir = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()


def _is_browser_running(name: str) -> bool:
    try:
        import subprocess

        names = {"edge": "msedge.exe", "chrome": "chrome.exe"}
        exe = names.get(name)
        if not exe:
            return False
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        return exe.lower() in r.stdout.lower()
    except Exception:
        return False
