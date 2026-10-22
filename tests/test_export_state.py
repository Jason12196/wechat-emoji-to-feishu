import hashlib
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from Crypto.Cipher import AES
from PIL import Image

from wechat_emoji_cli.engines import export_state, macos_backend, macos_resources


def png(color="red"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


class ExportStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.directory = self.root / "export"
        self.urls = ["https://example.invalid/image?m=first", "https://example.invalid/image?m=second"]
        self.image = png()

    def tearDown(self):
        self.temporary.cleanup()

    def snapshot(self):
        export_state.save_snapshot(self.directory, "wxid_fixture", self.urls, [{}])

    def complete(self):
        self.snapshot()
        raw = self.directory / "originals"
        raw.mkdir()
        for name in ["first", "second"]:
            (raw / f"{name}.png").write_bytes(self.image)
        with patch.object(macos_resources, "urlopen", side_effect=AssertionError("network")):
            return macos_resources.export_verified(raw, self.directory, self.urls, [{}])

    def test_initial_manifest_is_bound_partial_and_snapshot_is_private(self):
        export_state.begin(self.directory, "wxid_fixture")
        state = export_state.status(self.directory, "wxid_fixture")
        self.assertEqual(state["state"], "partial")
        self.assertEqual(state["expected"], 0)
        self.assertFalse(state["snapshotAvailable"])
        self.snapshot()
        state = export_state.status(self.directory, "wxid_fixture")
        self.assertEqual(state["remaining"], 2)
        self.assertTrue(state["snapshotAvailable"])
        self.assertEqual((self.directory / ".export-state").stat().st_mode & 0o777, 0o700)
        for filename in ["urls.json", "metadata.json"]:
            self.assertEqual((self.directory / ".export-state" / filename).stat().st_mode & 0o777, 0o600)
        self.assertNotIn("https://", (self.directory / "export-state.json").read_text())

    def test_complete_requires_hash_and_decodable_nonempty_expected_list(self):
        self.complete()
        self.assertEqual(export_state.status(self.directory)["state"], "complete")
        (self.directory / "first.png").write_bytes(png("blue"))
        state = export_state.status(self.directory)
        self.assertEqual((state["state"], state["ready"], state["remaining"]), ("partial", 1, 1))
        report = export_state.read_json(self.directory / "export-report.json")
        report["files"][0]["sha256"] = hashlib.sha256(b"not an image").hexdigest()
        (self.directory / "first.png").write_bytes(b"not an image")
        export_state.atomic_json(self.directory / "export-report.json", report)
        self.assertEqual(export_state.status(self.directory)["state"], "partial")
        export_state.atomic_json(self.directory / "export-state.json", {
            "version": 1, "wxid": "wxid_fixture", "resources": [],
        })
        self.assertNotEqual(export_state.status(self.directory)["state"], "complete")

    def test_wrong_account_excluded_and_cannot_overwrite_binding(self):
        self.complete()
        self.assertEqual(export_state.status(self.directory, "wxid_other")["state"], "none")
        self.assertEqual(export_state.discover(self.root, "wxid_other")["exports"], [])
        with self.assertRaisesRegex(ValueError, "其他微信账号"):
            export_state.begin(self.directory, "wxid_other")

    def test_legacy_unbound_visible_and_discovery_is_shallow_without_symlinks(self):
        self.directory.mkdir()
        (self.directory / "first.png").write_bytes(self.image)
        export_state.atomic_json(self.directory / "export-report.json", {
            "total": 1, "files": [{"resource": "first", "status": "ready", "file": "first.png"}],
        })
        state = export_state.status(self.directory, "wxid_fixture")
        self.assertEqual((state["state"], state["ready"]), ("unbound", 1))
        nested = self.directory / "deeper"
        export_state.begin(nested, "wxid_fixture")
        (self.root / "link").symlink_to(self.directory, target_is_directory=True)
        found = export_state.discover(self.root, "wxid_fixture")["exports"]
        self.assertEqual([row["directory"] for row in found], [str(self.directory)])
        self.assertEqual(export_state.status(self.root / "link")["state"], "none")
        export_state.begin(self.root, "wxid_fixture")
        os.utime(self.root / "export-state.json", (2000000000, 2000000000))
        found = export_state.discover(self.root, "wxid_fixture")["exports"]
        self.assertEqual(found[0]["directory"], str(self.root))

    def test_existing_complete_extract_never_invokes_engine_or_rewrites_images(self):
        expected = self.complete()
        times = {path: Path(path).stat().st_mtime_ns for path in expected}
        with patch.object(macos_backend, "run_cli", side_effect=AssertionError("engine")), \
             patch.object(macos_resources, "urlopen", side_effect=AssertionError("network")):
            actual = macos_backend.extract("wxid_fixture", self.directory)
        self.assertEqual(actual, expected)
        self.assertEqual(times, {path: Path(path).stat().st_mtime_ns for path in actual})

    def test_legacy_raw_only_export_is_discovered_without_claiming_account_or_total(self):
        raw = self.directory / "originals"
        raw.mkdir(parents=True)
        (raw / "first.png").write_bytes(self.image)
        (raw / "second.GIF").write_bytes(b"old encrypted or incomplete download")
        (raw / "notes.txt").write_text("not an image candidate")
        (raw / "link.png").symlink_to(raw / "first.png")
        (self.directory / "prepared.png").write_bytes(self.image)
        (self.directory / "broken.png").write_bytes(b"not decodable")
        (self.directory / "linked.png").symlink_to(self.directory / "prepared.png")
        state = export_state.status(self.directory, "wxid_fixture")
        self.assertEqual(state["state"], "unbound")
        self.assertTrue(state["legacy_raw"])
        self.assertEqual(state["raw_count"], 2)
        self.assertEqual((state["expected"], state["ready"], state["remaining"]), (0, 1, 0))
        self.assertNotIn("wxid", state)
        self.assertFalse(state["snapshotAvailable"])
        self.assertFalse((self.directory / "export-state.json").exists())
        found = export_state.discover(self.root, "wxid_fixture")["exports"]
        self.assertEqual([row["directory"] for row in found], [str(self.directory)])
        # Account binding happens only after explicit adoption, and still cannot
        # imply a complete expected list or turn unknown raw files into ready ones.
        export_state.begin(self.directory, "wxid_fixture")
        adopted = export_state.status(self.directory, "wxid_fixture")
        self.assertEqual((adopted["state"], adopted["expected"], adopted["ready"]), ("partial", 0, 0))
        self.assertEqual((raw / "second.GIF").read_bytes(), b"old encrypted or incomplete download")

    def test_legacy_raw_discovery_ignores_empty_or_linked_originals_directory(self):
        raw = self.directory / "originals"
        raw.mkdir(parents=True)
        self.assertEqual(export_state.status(self.directory)["state"], "none")
        outside = self.root / "download-cache"
        outside.mkdir()
        (outside / "first.png").write_bytes(self.image)
        (raw / "first.png").symlink_to(outside / "first.png")
        self.assertEqual(export_state.status(self.directory)["state"], "none")
        (raw / "first.png").unlink()
        raw.rmdir()
        raw.symlink_to(outside, target_is_directory=True)
        self.assertEqual(export_state.status(self.directory)["state"], "none")
        self.assertEqual(export_state.discover(self.root, "wxid_fixture")["exports"], [])

    def test_partial_recovers_only_missing_from_private_snapshot_without_engine(self):
        calls = []

        def engine(arguments, **kwargs):
            self.assertEqual(arguments[0], "urls")
            self.assertEqual(export_state.status(self.directory)["state"], "partial")
            Path(arguments[arguments.index("--out") + 1]).write_text("\n".join(self.urls))
            Path(arguments[arguments.index("--metadata-out") + 1]).write_text("[{}]")

        def first_download(request, **kwargs):
            calls.append(request.full_url)
            if "second" in request.full_url:
                raise OSError("interrupted download")
            return BytesIO(self.image)

        with patch.object(macos_backend, "run_cli", side_effect=engine) as engine_call, \
             patch.object(macos_resources, "urlopen", side_effect=first_download):
            files = macos_backend.extract("wxid_fixture", self.directory, progress_callback=lambda *_: None)
        self.assertEqual(engine_call.call_count, 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(export_state.status(self.directory)["state"], "partial")
        good = self.directory / "first.png"
        original = self.directory / "originals" / "first.png"
        times = good.stat().st_mtime_ns, original.stat().st_mtime_ns
        calls.clear()

        def resumed_download(request, **kwargs):
            calls.append(request.full_url)
            return BytesIO(self.image)

        with patch.object(macos_backend, "run_cli", side_effect=AssertionError("must not recapture key")), \
             patch.object(macos_resources, "urlopen", side_effect=resumed_download):
            files = macos_backend.extract("wxid_fixture", self.directory, progress_callback=lambda *_: None)
        self.assertEqual(len(files), 2)
        self.assertEqual(calls, [self.urls[1]])
        self.assertEqual(times, (good.stat().st_mtime_ns, original.stat().st_mtime_ns))
        self.assertEqual(export_state.status(self.directory)["state"], "complete")

    def test_corrupt_prepared_recovers_from_verified_original_without_network(self):
        self.complete()
        good = self.directory / "second.png"
        good_time = good.stat().st_mtime_ns
        (self.directory / "first.png").write_bytes(b"corrupt")
        (self.directory / "originals" / "first.png").unlink()
        with patch.object(macos_backend, "run_cli", side_effect=AssertionError("engine")), \
             patch.object(macos_resources, "urlopen", side_effect=AssertionError("network")):
            files = macos_backend.extract("wxid_fixture", self.directory, progress_callback=lambda *_: None)
        self.assertEqual(len(files), 2)
        self.assertEqual(good.stat().st_mtime_ns, good_time)
        self.assertEqual(export_state.status(self.directory)["state"], "complete")

    def test_first_download_decrypts_primary_url_and_keeps_encrypted_original(self):
        key = bytes.fromhex("00112233445566778899aabbccddeeff")
        padded = self.image + bytes([16 - len(self.image) % 16]) * (16 - len(self.image) % 16)
        encrypted = AES.new(key, AES.MODE_CBC, key).encrypt(padded)
        urls = self.urls[:1]
        metadata = [{"encrypt_url": urls[0], "aes_key": key.hex()}]
        export_state.save_snapshot(self.directory, "wxid_fixture", urls, metadata)
        with patch.object(macos_backend, "run_cli", side_effect=AssertionError("engine")), \
             patch.object(macos_resources, "urlopen", return_value=BytesIO(encrypted)) as download:
            files = macos_backend.extract("wxid_fixture", self.directory, progress_callback=lambda *_: None)
        self.assertEqual(len(files), 1)
        self.assertEqual(download.call_count, 1)
        self.assertEqual((self.directory / "originals" / "first.png").read_bytes(), encrypted)
        self.assertEqual(macos_resources.decode((self.directory / "verified-originals" / "first.png").read_bytes())[0], "PNG")
        self.assertEqual(export_state.status(self.directory)["state"], "complete")

    def test_recovery_never_overwrites_bad_original(self):
        export_state.save_snapshot(self.directory, "wxid_fixture", self.urls[:1], [{}])
        raw = self.directory / "originals"
        raw.mkdir()
        original = raw / "first.png"
        original.write_bytes(b"original-invalid-download")
        unchanged = original.stat().st_mtime_ns
        with patch.object(macos_resources, "urlopen", return_value=BytesIO(self.image)):
            files = macos_backend.extract("wxid_fixture", self.directory, progress_callback=lambda *_: None)
        self.assertEqual(len(files), 1)
        self.assertEqual(original.read_bytes(), b"original-invalid-download")
        self.assertEqual(original.stat().st_mtime_ns, unchanged)
        self.assertEqual(export_state.status(self.directory)["state"], "complete")

    def test_each_finished_file_checkpoints_expected_list(self):
        self.snapshot()
        raw = self.directory / "originals"
        raw.mkdir()
        for name in ["first", "second"]:
            (raw / f"{name}.png").write_bytes(self.image)
        checkpoints = []
        original_write = export_state.atomic_json

        def write(path, value):
            original_write(path, value)
            checkpoints.append(json.loads(path.read_text()))

        with patch.object(export_state, "atomic_json", side_effect=write):
            macos_resources.export_verified(raw, self.directory, self.urls, [{}])
        self.assertEqual([record["ready"] for record in checkpoints], [0, 1, 2])
        self.assertTrue(all(record["total"] == 2 for record in checkpoints))


if __name__ == "__main__":
    unittest.main()
