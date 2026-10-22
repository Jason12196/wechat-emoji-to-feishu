import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wechat_emoji_cli import browser


class BrowserTests(unittest.TestCase):
    def test_cache_hit_does_not_download(self):
        with patch.object(browser, "ready", return_value=True), patch.object(
            browser.subprocess, "Popen"
        ) as process:
            self.assertTrue(browser.ensure()["ready"])
            process.assert_not_called()

    def test_frozen_install_uses_bundled_node_and_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            process = MagicMock()
            process.__enter__.return_value = process
            process.stdout = ["download progress\n"]
            process.wait.side_effect = [1, 0]
            with patch.object(browser, "cache_root", return_value=Path(folder)), patch.object(
                browser, "ready", side_effect=[False, True]
            ), patch.object(browser.subprocess, "Popen", return_value=process) as spawn, patch(
                "playwright._impl._driver.compute_driver_executable",
                return_value=("bundled-node", "bundled-cli.js"),
            ):
                self.assertTrue(browser.ensure()["ready"])
                self.assertEqual(spawn.call_count, 2)
                self.assertEqual(spawn.call_args.args[0], [
                    "bundled-node", "bundled-cli.js", "install", "chromium"
                ])

    def test_failed_download_has_recovery_command(self):
        with tempfile.TemporaryDirectory() as folder:
            process = MagicMock()
            process.__enter__.return_value = process
            process.stdout = []
            process.wait.return_value = 1
            with patch.object(browser, "cache_root", return_value=Path(folder)), patch.object(
                browser, "ready", return_value=False
            ), patch.object(browser.subprocess, "Popen", return_value=process):
                with self.assertRaisesRegex(RuntimeError, "browser install"):
                    browser.ensure()
