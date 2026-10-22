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
import subprocess
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
    '[class*="add-btn"]',
    'button:has-text("+")',
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

# ── 企业管理后台：自定义表情导航 ──
_ADMIN_EMOJI_NAV = (
    # 左侧导航文字
    'a:has-text("自定义表情")',
    'a:has-text("企业表情")',
    'li:has-text("自定义表情")',
    'li:has-text("企业表情")',
    '[class*="nav"] :has-text("自定义表情")',
    '[class*="nav"] :has-text("企业文化")',
    # 通用
    "text=自定义表情",
    "text=企业表情",
    "text=企业文化",
)

_ADMIN_CREATE_PACK = (
    'button:has-text("添加表情包")',
    'button:has-text("新建表情包")',
    'button:has-text("创建表情包")',
    'button:has-text("上传表情")',
    'button:has-text("新增")',
    '[class*="create"] button',
    '[class*="add-pack"]',
)

_ADMIN_PACK_NAME_INPUT = (
    'input[placeholder*="表情包名称"]',
    'input[placeholder*="名称"]',
    'input[placeholder*="名字"]',
    'input[name*="name"]',
    'input[name*="title"]',
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


def _candidate_browser_roots() -> list[Path]:
    roots = [
        Path(config.PLAYWRIGHT_BUNDLE_DIR),
        Path(config.PLAYWRIGHT_VENDOR_DIR),
        Path(config.PLAYWRIGHT_USER_DIR),
    ]
    ordered: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(root)
    return ordered


def _has_browser_runtime(root: Path) -> bool:
    if not root.exists():
        return False
    required = ("chromium-*", "chromium_headless_shell-*", "ffmpeg-*")
    if sys.platform == "win32":
        required += ("winldd-*",)
    return all(any(root.glob(pattern)) for pattern in required)


def _configured_browser_root() -> Optional[Path]:
    for root in _candidate_browser_roots():
        if _has_browser_runtime(root):
            return root
    return None


def _activate_browser_runtime_env(root: Optional[Path] = None) -> Optional[Path]:
    chosen = root or _configured_browser_root()
    if chosen:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(chosen)
    return chosen


def _install_browser_runtime(target_root: Path) -> tuple[bool, str]:
    if getattr(sys, "frozen", False):
        return False, "打包模式下无法自动安装 Chromium，请确认已内置运行时。"
    target_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(target_root)
    commands = [
        [sys.executable, "-m", "playwright", "install", "chromium"],
        ["python", "-m", "playwright", "install", "chromium"],
        ["py", "-3", "-m", "playwright", "install", "chromium"],
    ]
    last_error = ""
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        if result.returncode == 0 and _has_browser_runtime(target_root):
            return True, f"Chromium runtime is ready at {target_root}"
        last_error = (result.stderr or result.stdout or "").strip() or f"exit={result.returncode}"
    return False, last_error or "unknown install error"


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


def check_upload_environment() -> dict:
    """Check whether Playwright and a Chromium runtime are ready for Feishu upload."""
    result = {
        "ok": False,
        "python_package": False,
        "browser_runtime": False,
        "message": "",
    }

    try:
        sync_playwright, _ = _load_playwright()
    except RuntimeError as exc:
        result["message"] = str(exc)
        return result

    result["python_package"] = True
    browser_root = _configured_browser_root()
    if browser_root:
        result["browser_root"] = str(browser_root)

    playwright = None
    browser = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        result["browser_runtime"] = True
        result["ok"] = True
        if browser_root:
            result["message"] = f"Bundled Chromium runtime is ready: {browser_root}"
        else:
            result["message"] = "Playwright and Chromium runtime are ready."
        return result
    except Exception as exc:
        target_root = Path(
            config.PLAYWRIGHT_BUNDLE_DIR
            if getattr(sys, "frozen", False)
            else config.PLAYWRIGHT_VENDOR_DIR
        )
        ok, install_msg = _install_browser_runtime(target_root)
        if ok:
            result["browser_runtime"] = True
            result["ok"] = True
            result["browser_root"] = str(target_root)
            result["message"] = install_msg
        else:
            if getattr(sys, "frozen", False):
                result["message"] = (
                    "Chromium 运行时未找到，打包应用应已内置 Chromium。"
                    f"请确认 exe 旁存在 runtime/ms-playwright 文件夹。原始错误: {exc}"
                )
            else:
                result["message"] = (
                    "Playwright 已安装，但 Chromium 运行时缺失。"
                    f"请执行：python -m playwright install chromium\n原始错误: {exc}"
                )
        return result
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


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
        sync_playwright, timeout_error = _load_playwright()
        self._timeout_error = timeout_error
        self._playwright_driver = sync_playwright().start()
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
                    '[role="main"]',
                ):
                    try:
                        if self._page.locator(sel).count() > 0:
                            return True
                    except Exception:
                        pass
                return True
        except Exception:
            pass
        return False

    # ─────────────────── 个人表情上传 ───────────────────

    def upload_personal_emojis(self, emoji_files: list[str], stop_check: StopCheck = None) -> dict:
        """Upload batches and stop on any ambiguous outcome."""
        from .personal_import import upload

        return upload(self, emoji_files, stop_check)

    def _try_open_first_chat(self):
        """Keep a writable conversation, or find one without typing/sending messages."""
        editor = self._page.locator('[contenteditable="true"]').first
        if editor.is_visible():
            return
        for selector in _SIDEBAR_CHAT_SELECTORS:
            items = self._page.locator(selector)
            for index in range(min(items.count(), 20)):
                try:
                    item = items.nth(index)
                    if not item.is_visible():
                        continue
                    item.click()
                    editor.wait_for(state="visible", timeout=1800)
                    return
                except Exception:
                    continue

    def _wait_for_messenger_ready(
        self, timeout_ms: int = 12000, stop_check: StopCheck = None
    ) -> bool:
        if not self._page:
            return False
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._stop_requested(stop_check):
                return False
            for sel in (
                '[contenteditable="true"]',
                ".lark__editor--toolbar",
            ):
                try:
                    if self._page.locator(sel).first.is_visible():
                        return True
                except Exception:
                    pass
            time.sleep(0.4)
        return False

    def _open_emoji_panel(self) -> bool:
        """点击表情按钮，并切换到“爱心”自定义贴纸面板。"""
        # 先点击输入框以确保焦点
        for sel in ('[contenteditable="true"]', '[role="textbox"]', '[class*="input-editor"]'):
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=800):
                    loc.click()
                    time.sleep(0.3)
                    break
            except Exception:
                pass

        # 如果贴纸面板已经打开，直接返回
        if self._is_sticker_panel_visible():
            return True

        for sel in _EMOJI_BTN_SELECTORS:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=1200):
                    loc.click()
                    time.sleep(0.8)
                    if self._switch_personal_sticker_tab():
                        return True
            except Exception:
                continue
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

    def _switch_personal_sticker_tab(self) -> bool:
        if self._is_sticker_panel_visible():
            return True
        if not self._is_emoji_popup_visible():
            return False

        # The real user path is: emoji popup -> heart tab -> add button.
        try:
            buttons = self._page.locator(".emoji button.ud__button--icon.ud__button--icon-size-md")
            if buttons.count() >= 3:
                buttons.nth(2).click()
                time.sleep(0.8)
                if self._is_sticker_panel_visible():
                    return True
        except Exception:
            pass

        self._try_switch_custom_tab()
        return self._is_sticker_panel_visible()

    def _try_switch_custom_tab(self):
        for sel in _CUSTOM_TAB_SELECTORS:
            try:
                loc = self._page.locator(sel)
                if sel.startswith(".emoji button") and loc.count() >= 3:
                    loc.nth(2).click()
                    time.sleep(0.5)
                    return
                first = loc.first
                if first.is_visible(timeout=1500):
                    first.click()
                    time.sleep(0.5)
                    return
            except Exception:
                continue

    def _try_click_add_emoji(self):
        for sel in _ADD_BTN_SELECTORS:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    time.sleep(0.5)
                    return
            except Exception:
                continue

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

    # ─────────────────── 企业表情包上传 ───────────────────

    def upload_enterprise_emojis(
        self,
        emoji_files: list[str],
        pack_name: str = "微信表情包",
        stop_check: StopCheck = None,
    ) -> dict:
        """上传企业自定义表情包（需要管理员权限）。"""
        if not emoji_files:
            self._report("[警告] 没有要上传的表情文件")
            return {"success": 0, "failed": 0}

        # 按 FEISHU_EMOJI_PACK_MAX 分组
        groups: list[list[str]] = []
        for i in range(0, len(emoji_files), config.FEISHU_EMOJI_PACK_MAX):
            group = emoji_files[i : i + config.FEISHU_EMOJI_PACK_MAX]
            if len(group) >= config.FEISHU_EMOJI_PACK_MIN:
                groups.append(group)
            else:
                self._report(
                    f"[警告] 最后 {len(group)} 个不足 {config.FEISHU_EMOJI_PACK_MIN} 个，已跳过"
                )

        if not groups:
            self._report("[错误] 没有足够的表情组成企业表情包（至少 6 个）")
            return {"success": 0, "failed": len(emoji_files)}

        self._report(f"[上传] 分 {len(groups)} 组上传企业表情包")

        total_success = 0
        total_failed = 0
        for gi, group in enumerate(groups, start=1):
            if self._stop_requested(stop_check):
                self._report(f"[信息] 用户中止上传，已上传 {total_success} 个，跳过剩余分组")
                break
            gname = f"{pack_name}" if len(groups) == 1 else f"{pack_name}_{gi}"
            self._report(f"[上传] 第 {gi}/{len(groups)} 组：{gname}（{len(group)} 个）")
            result = self._upload_one_enterprise_pack(group, gname, stop_check=stop_check)
            total_success += result["success"]
            total_failed += result["failed"]

        self._report(f"[完成] 企业表情包上传结束: 成功 {total_success}，失败 {total_failed}")
        return {"success": total_success, "failed": total_failed}

    def _upload_one_enterprise_pack(
        self,
        emoji_files: list[str],
        pack_name: str,
        stop_check: StopCheck = None,
    ) -> dict:
        # ── 打开管理后台 ──
        self._report(f"[信息] 打开飞书管理后台: {config.FEISHU_ADMIN_URL}")
        try:
            self._page.goto(config.FEISHU_ADMIN_URL, wait_until="domcontentloaded")
            self._page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        time.sleep(2)

        # ── 检查是否需要管理员登录 ──
        url = self._page.url or ""
        if "login" in url or "passport" in url:
            self._report(
                "[警告] 管理后台需要重新登录。请在浏览器中完成登录后，工具会自动继续（等待 60 秒）"
            )
            deadline = time.time() + 60
            while time.time() < deadline:
                if self._stop_requested(stop_check):
                    self._report("[信息] 上传已中止")
                    return {"success": 0, "failed": len(emoji_files)}
                if config.FEISHU_ADMIN_URL.split("/")[2] in (self._page.url or ""):
                    break
                time.sleep(2)

        # ── 导航到企业自定义表情页面 ──
        self._report("[信息] 尝试导航到自定义表情管理页面…")
        navigated = False
        for sel in _ADMIN_EMOJI_NAV:
            if self._stop_requested(stop_check):
                self._report("[信息] 上传已中止")
                return {"success": 0, "failed": len(emoji_files)}
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    time.sleep(1.5)
                    navigated = True
                    break
            except Exception:
                continue

        if not navigated:
            # 尝试直接访问常见路径
            for path in ("/admin/emoji", "/admin/customEmoji", "/admin/culture/emoji"):
                try:
                    self._page.goto(f"https://www.feishu.cn{path}", wait_until="domcontentloaded")
                    time.sleep(1.5)
                    break
                except Exception:
                    pass

        # ── 点击"添加表情包" ──
        for sel in _ADMIN_CREATE_PACK:
            if self._stop_requested(stop_check):
                self._report("[信息] 上传已中止")
                return {"success": 0, "failed": len(emoji_files)}
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=2500):
                    loc.click()
                    time.sleep(1.2)
                    break
            except Exception:
                continue

        # ── 填写表情包名称 ──
        for sel in _ADMIN_PACK_NAME_INPUT:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.fill(pack_name)
                    time.sleep(0.4)
                    break
            except Exception:
                continue

        # ── 找到文件 input，注入文件 ──
        file_input = self._find_file_input(timeout=6000, stop_check=stop_check)
        if not file_input:
            self._screenshot("fail_enterprise_file_input")
            self._report(
                "[半自动] 未自动找到上传按钮。请在浏览器中手动点击「上传」按钮，"
                "工具等待 60 秒后自动注入文件"
            )
            file_input = self._find_file_input(timeout=60000, stop_check=stop_check)

        if not file_input:
            if self._stop_requested(stop_check):
                self._report("[信息] 上传已中止")
                return {"success": 0, "failed": len(emoji_files)}
            self._report("[错误] 未能找到企业表情包文件上传框，跳过本组")
            return {"success": 0, "failed": len(emoji_files)}

        # 判断是否支持 multiple
        try:
            multi = bool(file_input.evaluate("el => el.multiple || el.hasAttribute('multiple')"))
        except Exception:
            multi = True

        try:
            if self._stop_requested(stop_check):
                self._report("[信息] 上传已中止")
                return {"success": 0, "failed": len(emoji_files)}
            if multi:
                file_input.set_input_files(emoji_files)
            else:
                for fp in emoji_files:
                    if self._stop_requested(stop_check):
                        self._report("[信息] 上传已中止")
                        return {"success": 0, "failed": len(emoji_files)}
                    file_input.set_input_files(fp)
                    time.sleep(0.3)
        except Exception as exc:
            self._report(f"[错误] 文件注入失败: {exc}")
            self._screenshot("fail_enterprise_inject")
            return {"success": 0, "failed": len(emoji_files)}

        time.sleep(1.5)
        self._try_confirm_upload()
        ok, msg = self._wait_feedback(timeout_ms=12000, stop_check=stop_check)
        self._report(f"[信息] {msg}")
        if ok:
            return {"success": len(emoji_files), "failed": 0}
        return {"success": 0, "failed": len(emoji_files)}

    # ─────────────────── 工具方法 ───────────────────

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
        """关闭浏览器，保存登录态。"""
        for obj, method in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright_driver, "stop"),
        ):
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


def upload_emojis(
    emoji_dir: str,
    mode: str = "personal",
    headless: bool = False,
    pack_name: str = "微信表情包",
    progress_callback: ProgressCallback = None,
) -> dict:
    """便捷函数：上传表情到飞书。"""
    from .files import collect_emoji_files

    emoji_files = collect_emoji_files(emoji_dir)
    if not emoji_files:
        msg = f"[错误] 目录 {emoji_dir} 中没有找到表情文件"
        print(msg)
        if progress_callback:
            progress_callback(0, 0, msg)
        return {"success": 0, "failed": 0}

    with FeishuUploader(headless=headless, progress_callback=progress_callback) as uploader:
        if not uploader.login():
            return {"success": 0, "failed": len(emoji_files)}
        if mode == "personal":
            return uploader.upload_personal_emojis(emoji_files)
        if mode == "enterprise":
            return uploader.upload_enterprise_emojis(emoji_files, pack_name=pack_name)
        msg = f"[错误] 未知模式: {mode}"
        print(msg)
        if progress_callback:
            progress_callback(0, 0, msg)
        return {"success": 0, "failed": len(emoji_files)}


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
