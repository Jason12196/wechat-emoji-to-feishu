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

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--json", "--home", str(self.root / "state"), *map(str, arguments)])
        return code, [json.loads(line) for line in out.getvalue().splitlines()], err.getvalue()

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
