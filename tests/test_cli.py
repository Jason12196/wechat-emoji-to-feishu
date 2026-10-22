import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from wechat_emoji_cli.cli import main
from wechat_emoji_cli.engines.macos_resources import decode, prepare, resource_id
from wechat_emoji_cli.engines.personal_import import upload


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.images = self.root / "images"
        self.images.mkdir()
        self.image = self.images / "a.png"
        Image.new("RGB", (20, 20), "red").save(self.image)
        self.wechat = self.root / "wechat"
        self.wechat.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([
                "--json", "--home", str(self.root / "state"),
                "--wechat-root", str(self.wechat), *map(str, arguments),
            ])
        return code, [json.loads(line) for line in out.getvalue().splitlines()], err.getvalue()

    def account(self, wxid="wxid_fixture"):
        database = self.wechat / wxid / "db_storage/emoticon/emoticon.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"isolated database fixture")
        return database

    def test_key_reuses_valid_account_cache_without_helper_or_login_prompt(self):
        database = self.account()
        with (
            patch("wechat_emoji_cli.engines.key_status.cached_key_valid", return_value=True) as cache,
            patch("wechat_emoji_cli.engines.macos_backend.run_cli") as helper,
        ):
            code, events, _ = self.call("key", "--wxid", "wxid_fixture")
        self.assertEqual(code, 0)
        cache.assert_called_once_with(database.resolve(), "wxid_fixture")
        helper.assert_not_called()
        self.assertEqual([event["type"] for event in events], ["started", "result"])
        self.assertEqual(events[-1]["result"], {
            "key_cached": True, "reused": True, "wxid": "wxid_fixture",
        })

    def test_key_uses_helper_only_for_missing_cache_or_explicit_force(self):
        self.account()
        for force in (False, True):
            with (
                self.subTest(force=force),
                patch("wechat_emoji_cli.engines.key_status.cached_key_valid", return_value=force) as cache,
                patch("wechat_emoji_cli.engines.macos_backend.run_cli") as helper,
            ):
                arguments = ["key", "--wxid", "wxid_fixture"]
                if force:
                    arguments += ["--force"]
                code, events, _ = self.call(*arguments)
                self.assertEqual(code, 0)
                expected = ["key", "--timeout", "180", "--wxid", "wxid_fixture"]
                if force:
                    expected += ["--force"]
                    cache.assert_not_called()
                helper.assert_called_once_with(expected)
                self.assertFalse(events[-1]["result"]["reused"])
                prompt = next(event for event in events if event["type"] == "action_required")
                self.assertIn("无需手动打开表情面板", prompt["message"])

    def test_key_rejects_account_paths_and_symlink_escape_before_cache_lookup(self):
        outside = self.root / "wxid_outside"
        database = outside / "db_storage/emoticon/emoticon.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"fixture")
        (self.wechat / "wxid_symlink").symlink_to(outside, target_is_directory=True)
        with (
            patch("wechat_emoji_cli.engines.key_status.cached_key_valid") as cache,
            patch("wechat_emoji_cli.engines.macos_backend.run_cli") as helper,
        ):
            for account in ("../wxid_outside", "wxid_symlink"):
                with self.subTest(account=account):
                    code, events, _ = self.call("key", "--wxid", account)
                    self.assertEqual(code, 2)
                    self.assertIn(events[-1]["code"], ("INVALID_ACCOUNT", "ACCOUNT_NOT_FOUND"))
        cache.assert_not_called()
        helper.assert_not_called()

    def test_key_requires_account_selection_when_multiple_accounts_exist(self):
        self.account("wxid_first")
        self.account("wxid_second")
        with patch("wechat_emoji_cli.engines.macos_backend.run_cli") as helper:
            code, events, _ = self.call("key")
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["code"], "ACCOUNT_REQUIRED")
        helper.assert_not_called()

    def test_exports_commands_preserve_read_only_status_and_discovery_results(self):
        status = {
            "state": "partial", "directory": str(self.images.resolve()),
            "expected": 3, "ready": 1, "remaining": 2,
            "wxid": "wxid_fixture", "snapshot_ready": True,
        }
        for action, expected in (("status", status), ("discover", {"exports": [status]})):
            with (
                self.subTest(action=action),
                patch(f"wechat_emoji_cli.engines.export_state.{action}", return_value=expected) as inspect,
                patch("wechat_emoji_cli.engines.macos_backend.run_cli") as helper,
            ):
                code, events, _ = self.call("exports", action, self.images, "--wxid", "wxid_fixture")
                # A partial local export is a successful read-only inspection, not a failed export.
                self.assertEqual(code, 0)
                self.assertEqual(events[-1]["result"], expected)
                inspect.assert_called_once_with(self.images.resolve(), "wxid_fixture")
                helper.assert_not_called()

    def test_partial_export_remains_partial_when_some_images_were_written(self):
        (self.images / "export-report.json").write_text(json.dumps({"ready": 1, "failed": 2}))
        with patch("wechat_emoji_cli.engines.macos_backend.extract", return_value=[str(self.image)]):
            code, events, _ = self.call("extract", "--wxid", "wxid_fixture", "--out", self.images)
        self.assertEqual(code, 3)
        self.assertEqual(events[-1]["status"], "partial")
        self.assertEqual(events[-1]["result"]["exported"], 1)
        self.assertEqual(events[-1]["result"]["failed"], 2)

    def test_stdout_is_ndjson_even_when_engine_prints(self):
        def dispatch(*args):
            print("legacy engine output")
            return {"ok": True}

        with patch("wechat_emoji_cli.cli.dispatch", dispatch):
            code, events, errors = self.call("doctor")
        self.assertEqual(code, 0)
        self.assertEqual([x["type"] for x in events], ["started", "result"])
        self.assertTrue(all(x["protocol_version"] == 1 for x in events))
        self.assertIn("legacy engine output", errors)

    def test_full_capacity_rejects_before_browser_start(self):
        with patch("wechat_emoji_cli.engines.feishu_uploader.FeishuUploader") as browser:
            code, events, _ = self.call(
                "feishu", "import", self.images, "--account", "test", "--existing-count", "1000"
            )
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["code"], "CAPACITY_EXCEEDED")
        browser.assert_not_called()

    def test_plan_does_not_silently_truncate(self):
        code, events, _ = self.call(
            "feishu", "plan", self.images, "--account", "test", "--existing-count", "1000"
        )
        self.assertEqual(code, 0)
        self.assertFalse(events[-1]["result"]["fits"])
        self.assertEqual(events[-1]["result"]["selected"], 1)

    def test_capacity_count_is_required(self):
        code, events, _ = self.call("feishu", "plan", self.images, "--account", "test")
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["code"], "CAPACITY_REQUIRED")

    def test_manifest_excludes_originals_and_unlisted_files(self):
        nested = self.images / "originals"
        nested.mkdir()
        Image.new("RGB", (10, 10)).save(nested / "extra.png")
        Image.new("RGB", (10, 10)).save(self.images / "unlisted.png")
        (self.images / "export-report.json").write_text(
            json.dumps({"files": [{"file": "a.png", "status": "ready"}]})
        )
        code, events, _ = self.call("images", "inspect", self.images)
        self.assertEqual(code, 0)
        self.assertEqual(events[-1]["result"]["valid"], 1)

    def test_small_animation_is_not_flattened(self):
        frames = [Image.new("RGB", (32, 32), c) for c in ("red", "green", "blue")]
        value = io.BytesIO()
        frames[0].save(
            value, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0
        )
        data = prepare(value.getvalue())
        self.assertEqual(decode(data)[2], 3)

    def test_pending_ledger_is_not_resubmitted(self):
        ledger = self.root / "ledger.json"
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        ledger.write_text(json.dumps({digest: {"file": self.image.name, "status": "pending"}}))

        class NoBrowser:
            def __getattr__(self, name):
                raise AssertionError("A recorded file must not be submitted again")

        result = upload(NoBrowser(), [str(self.image)], ledger_path=ledger)
        self.assertEqual(result["unknown"], 1)
        self.assertEqual(result["skipped"], 1)

    def test_wrong_account_resume_is_rejected_before_browser(self):
        ledger = self.root / "ledger.json"
        ledger.write_text("{}")
        ledger.with_suffix(".account.json").write_text(json.dumps({"account": "other"}))
        with patch("wechat_emoji_cli.engines.feishu_uploader.FeishuUploader") as browser:
            code, events, _ = self.call(
                "feishu",
                "import",
                self.images,
                "--account",
                "test",
                "--existing-count",
                "0",
                "--ledger",
                ledger,
            )
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["code"], "LEDGER_ACCOUNT_MISMATCH")
        browser.assert_not_called()

    def test_resume_capacity_counts_only_new_files(self):
        ledger = self.root / "ledger.json"
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        ledger.write_text(json.dumps({digest: {"file": self.image.name, "status": "confirmed"}}))
        ledger.with_suffix(".account.json").write_text(json.dumps({"account": "test"}))
        code, events, _ = self.call(
            "feishu",
            "plan",
            self.images,
            "--account",
            "test",
            "--existing-count",
            "1000",
            "--ledger",
            ledger,
        )
        self.assertEqual(code, 0)
        self.assertTrue(events[-1]["result"]["fits"])
        self.assertEqual(events[-1]["result"]["selected"], 0)

    def test_exception_has_private_redacted_traceback(self):
        with patch("wechat_emoji_cli.engines.macos_backend.accounts", side_effect=RuntimeError("authorization: Bearer hidden-value")):
            code, events, _ = self.call("accounts")
        self.assertEqual(code, 1)
        diagnostic = Path(events[-1]["result"]["diagnostic"])
        self.assertTrue(diagnostic.exists())
        value = json.loads(diagnostic.read_text())
        self.assertEqual(value["exception_type"], "RuntimeError")
        self.assertIn("in dispatch", value["traceback"])
        self.assertNotIn("hidden-value", diagnostic.read_text())
        self.assertEqual(diagnostic.stat().st_mode & 0o777, 0o600)

    def test_browser_progress_uses_protocol(self):
        def provision(report, verify):
            report("download progress")
            return {"ready": True, "launch_verified": verify}

        with patch("wechat_emoji_cli.browser.ensure", side_effect=provision):
            code, events, _ = self.call("browser", "install")
        self.assertEqual(code, 0)
        self.assertTrue(any(event["type"] == "progress" for event in events))
        self.assertTrue(events[-1]["result"]["launch_verified"])

    def test_single_personal_sticker_is_valid(self):
        code, events, _ = self.call(
            "feishu", "plan", self.images, "--account", "test", "--existing-count", "0"
        )
        self.assertEqual(code, 0)
        self.assertTrue(events[-1]["result"]["fits"])
        self.assertEqual(events[-1]["result"]["mode"], "personal")

    def test_enterprise_option_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.call("feishu", "plan", self.images, "--account", "test", "--mode", "enterprise")
        self.assertEqual(error.exception.code, 2)

    def test_task_id_cannot_escape_state_directory(self):
        code, events, _ = self.call("tasks", "show", "../../outside")
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["code"], "INVALID_TASK_ID")

    def test_prepare_preserves_input_and_writes_manifest(self):
        original = self.image.read_bytes()
        code, events, _ = self.call(
            "images", "prepare", self.images, "--out", self.root / "prepared"
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.image.read_bytes(), original)
        self.assertEqual(events[-1]["result"]["ready"], 1)

    def test_resource_id_cannot_escape_export_directory(self):
        with self.assertRaises(ValueError):
            resource_id("https://example.com/?m=../escape")


if __name__ == "__main__":
    unittest.main()
