import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from wechat_emoji_cli.engines import macos_backend


class MacBackendDiagnosticsTests(unittest.TestCase):
    def test_failure_exposes_native_reason_and_redacts_secrets(self):
        def spawn(*args, **kwargs):
            kwargs["stdout"].write("Error: 微信仍在运行\n" + "ab" * 32 + "\n")
            kwargs["stdout"].flush()
            return Mock(poll=Mock(return_value=1), returncode=1)

        with tempfile.TemporaryDirectory() as folder:
            with patch.object(macos_backend, "cli_path", return_value="fixture"), \
                 patch.object(macos_backend.config, "DEBUG_DIR", folder), \
                 patch.object(macos_backend.subprocess, "Popen", side_effect=spawn):
                with self.assertRaises(RuntimeError) as caught:
                    macos_backend.run_cli(["key"])
            self.assertIn("微信仍在运行", str(caught.exception))
            self.assertIn("退出码 1", str(caught.exception))
            self.assertNotIn("ab" * 32, str(caught.exception))
            self.assertEqual((Path(folder) / "mac-extraction.log").stat().st_mode & 0o777, 0o600)
