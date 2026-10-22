"""Import readiness checks against fake pages only; no browser/profile is opened."""

import hashlib
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from wechat_emoji_cli.engines.feishu_uploader import (
    _SIDEBAR_CHAT_SELECTORS,
    FeishuUploader,
)
from wechat_emoji_cli.engines.personal_import import upload


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class Element:
    def __init__(self, page, kind, index=0):
        self.page, self.kind, self.index = page, kind, index

    def is_visible(self, **kwargs):
        if self.kind == "sidebar":
            return self.page.sidebar
        if self.kind == "editor":
            return self.page.editor
        return self.kind == "chat"

    def is_editable(self, **kwargs):
        return self.kind == "editor" and self.page.writable

    def click(self, *, timeout):
        self.page.clicks.append((self.kind, self.index, timeout))
        self.page.clock.now += min(timeout / 1000, 0.1)
        if self.kind == "chat" and self.index == self.page.writable_chat:
            self.page.editor = self.page.writable = True


class Locator:
    def __init__(self, page, kind, count):
        self.page, self.kind, self.amount = page, kind, count

    @property
    def first(self):
        return Element(self.page, self.kind if self.amount else "missing")

    def count(self):
        return self.amount

    def nth(self, index):
        return Element(self.page, self.kind, index)


class Page:
    url = "https://example.feishu.cn/messenger/"

    def __init__(self, clock):
        self.clock = clock
        self.sidebar = False
        self.editor = False
        self.writable = False
        self.rows = 0
        self.writable_chat = None
        self.rows_after = None
        self.clicks = []
        self.waited = 0

    def locator(self, selector):
        if selector == '[class*="sidebar"]':
            return Locator(self, "sidebar", int(self.sidebar))
        if selector == '[contenteditable="true"]':
            return Locator(self, "editor", int(self.editor))
        if selector in _SIDEBAR_CHAT_SELECTORS:
            return Locator(self, "chat", self.rows)
        return Locator(self, "missing", 0)

    def wait_for_timeout(self, milliseconds):
        self.waited += milliseconds
        self.clock.now += milliseconds / 1000
        if self.rows_after is not None and self.clock.now >= self.rows_after:
            self.rows = 3


class PersonalPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.files = []
        for index in range(3):
            path = self.root / f"{index}.png"
            path.write_bytes(f"synthetic-file-{index}".encode())
            self.files.append(str(path))
        self.ledger = self.root / "private" / "ledger.json"

    def tearDown(self):
        self.temporary.cleanup()

    def fake_uploader(self):
        # The fake chooser never reaches a browser, network, or user account.
        chooser = SimpleNamespace(is_multiple=Mock(return_value=True), set_files=Mock())
        page = SimpleNamespace(expect_file_chooser=Mock(return_value=nullcontext(SimpleNamespace(value=chooser))),
                               wait_for_timeout=Mock())
        return SimpleNamespace(
            _wait_for_messenger_ready=Mock(return_value=True),
            _try_open_first_chat=Mock(return_value=True),
            _open_emoji_panel=Mock(return_value=True),
            _has_personal_sticker_add_entry=Mock(return_value=True),
            _capture_custom_sticker_signature=Mock(return_value=[]),
            _try_click_add_emoji=Mock(), _try_confirm_upload=Mock(),
            _screenshot=Mock(), _report=Mock(), _page=page, chooser=chooser,
        )

    def assert_unsubmitted(self, result, code):
        self.assertEqual(result["blocked"]["code"], code)
        self.assertEqual((result["unknown"], result["remaining"], result["submitted"]), (0, 3, 0))
        self.assertEqual(json.loads(self.ledger.read_text()), {})
        self.assertEqual(self.ledger.stat().st_mode & 0o777, 0o600)

    def test_loading_timeout_has_empty_private_ledger_and_never_opens_chat_or_chooser(self):
        uploader = self.fake_uploader()
        uploader._wait_for_messenger_ready.return_value = False
        result = upload(uploader, self.files, ledger_path=self.ledger)
        self.assert_unsubmitted(result, "MESSENGER_LOADING_TIMEOUT")
        uploader._wait_for_messenger_ready.assert_called_once_with(timeout_ms=180000, stop_check=None)
        uploader._try_open_first_chat.assert_not_called()
        uploader._page.expect_file_chooser.assert_not_called()

    def test_no_writable_conversation_never_opens_personal_panel(self):
        uploader = self.fake_uploader()
        uploader._try_open_first_chat.return_value = False
        result = upload(uploader, self.files, ledger_path=self.ledger)
        self.assert_unsubmitted(result, "NO_WRITABLE_CONVERSATION")
        uploader._open_emoji_panel.assert_not_called()
        uploader._page.expect_file_chooser.assert_not_called()

    def test_missing_panel_or_add_entry_blocks_before_file_chooser(self):
        for method in ["_open_emoji_panel", "_has_personal_sticker_add_entry"]:
            with self.subTest(method=method):
                uploader = self.fake_uploader()
                getattr(uploader, method).return_value = False
                result = upload(uploader, self.files, ledger_path=self.ledger)
                self.assert_unsubmitted(result, "STICKER_PANEL_UNAVAILABLE")
                uploader._page.expect_file_chooser.assert_not_called()

    def test_cancelled_loading_preserves_all_files_as_unsubmitted(self):
        uploader = self.fake_uploader()
        uploader._wait_for_messenger_ready.return_value = False
        result = upload(uploader, self.files, stop_check=lambda: True, ledger_path=self.ledger)
        self.assert_unsubmitted(result, "CANCELLED")
        uploader._page.expect_file_chooser.assert_not_called()

    def test_pending_ledger_is_untouched_and_never_contacts_page(self):
        self.ledger.parent.mkdir()
        digest = hashlib.sha256(Path(self.files[0]).read_bytes()).hexdigest()
        before = json.dumps({digest: {"file": "0.png", "status": "pending"}})
        self.ledger.write_text(before)
        uploader = self.fake_uploader()
        result = upload(uploader, self.files[:1], ledger_path=self.ledger)
        self.assertEqual((result["unknown"], result["remaining"], result["submitted"]), (1, 0, 0))
        self.assertEqual(self.ledger.read_text(), before)
        uploader._wait_for_messenger_ready.assert_not_called()
        uploader._page.expect_file_chooser.assert_not_called()

    def test_exception_before_pending_does_not_claim_any_unknown_upload(self):
        uploader = self.fake_uploader()
        uploader._page.expect_file_chooser.side_effect = RuntimeError("fake chooser unavailable")
        result = upload(uploader, self.files, batch_size=1, ledger_path=self.ledger)
        self.assertEqual((result["unknown"], result["remaining"], result["submitted"]), (0, 3, 0))
        self.assertEqual(json.loads(self.ledger.read_text()), {})

    def test_pending_batch_exception_does_not_double_count_unknown_as_remaining(self):
        uploader = self.fake_uploader()
        uploader.chooser.set_files.side_effect = RuntimeError("fake interrupted chooser")
        result = upload(uploader, self.files, batch_size=1, ledger_path=self.ledger)
        self.assertEqual((result["unknown"], result["remaining"], result["submitted"]), (1, 2, 1))
        self.assertEqual(len(json.loads(self.ledger.read_text())), 1)
        self.assertEqual(result["unknown"] + result["remaining"] + result["success"], 3)

    def test_later_panel_failure_preserves_confirmed_batch_and_remaining(self):
        uploader = self.fake_uploader()
        uploader._open_emoji_panel.side_effect = [True, False]
        uploader._capture_custom_sticker_signature.side_effect = [[], ["synthetic-confirmed-signature"]]
        result = upload(uploader, self.files, batch_size=1, ledger_path=self.ledger)
        self.assertEqual(result["blocked"]["code"], "STICKER_PANEL_UNAVAILABLE")
        self.assertEqual((result["success"], result["unknown"], result["remaining"], result["submitted"]), (1, 0, 2, 1))
        self.assertEqual(next(iter(json.loads(self.ledger.read_text()).values()))["status"], "confirmed")

    def test_route_alone_is_not_login_but_visible_sidebar_is_auth_not_ready(self):
        clock = Clock()
        page = Page(clock)
        uploader = FeishuUploader()
        uploader._page = page
        self.assertFalse(uploader._is_logged_in())
        page.sidebar = True
        self.assertTrue(uploader._is_logged_in())
        with patch("wechat_emoji_cli.engines.feishu_uploader.time.monotonic", clock.monotonic):
            self.assertFalse(uploader._wait_for_messenger_ready(timeout_ms=45000))
        self.assertLessEqual(clock.now, 45.01)
        self.assertEqual(page.clicks, [])

    def test_real_conversation_rows_wait_then_open_writable_editor_without_typing(self):
        clock = Clock()
        page = Page(clock)
        page.rows_after = 1
        page.writable_chat = 2
        uploader = FeishuUploader()
        uploader._page = page
        with patch("wechat_emoji_cli.engines.feishu_uploader.time.monotonic", clock.monotonic):
            self.assertTrue(uploader._wait_for_messenger_ready(timeout_ms=45000))
            self.assertGreaterEqual(clock.now, 1)
            self.assertTrue(uploader._try_open_first_chat(timeout_ms=12000))
        self.assertTrue(page.editor)
        self.assertEqual([index for kind, index, _ in page.clicks], [0, 1, 2])
        self.assertTrue(all(timeout <= 700 for _, _, timeout in page.clicks))

    def test_chat_search_deadline_and_cancellation_are_bounded(self):
        clock = Clock()
        page = Page(clock)
        page.rows = 100
        uploader = FeishuUploader()
        uploader._page = page
        with patch("wechat_emoji_cli.engines.feishu_uploader.time.monotonic", clock.monotonic):
            self.assertFalse(uploader._try_open_first_chat(timeout_ms=1200))
        self.assertLessEqual(clock.now, 1.21)
        self.assertLessEqual(len(page.clicks), 10)
        page.clicks.clear()
        with patch("wechat_emoji_cli.engines.feishu_uploader.time.monotonic", clock.monotonic):
            self.assertFalse(uploader._wait_for_messenger_ready(stop_check=lambda: True))
            self.assertFalse(uploader._try_open_first_chat(stop_check=lambda: True))
        self.assertEqual(page.clicks, [])


if __name__ == "__main__":
    unittest.main()
