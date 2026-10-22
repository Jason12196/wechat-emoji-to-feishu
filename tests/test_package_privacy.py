import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.package_privacy import (
    PackagePrivacyError,
    audit_package,
    build_archive,
    sanitized_tarinfo,
)


class PackagePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.home = self.root / "private builder home"

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, value=b"public package resource"):
        path = self.package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def audit(self):
        return audit_package(self.package, private_prefixes=[self.home])

    def test_normal_dependency_sources_and_playwright_icon_are_allowed(self):
        self.write("README.md")
        self.write("_internal/playwright/_impl/_debug.py")
        self.write("_internal/playwright/driver/package/lib/server/cookies.js")
        self.write("_internal/playwright/driver/package/lib/server/chromium/appIcon.png")
        self.write("dependency-licenses/pillow/LICENSE")
        self.assertEqual(self.audit()["files"], 5)

    def test_private_state_names_are_rejected_without_exposing_values(self):
        for index, relative in enumerate((
            "_internal/emoticon_dbkey_wxid_private.txt",
            "_internal/profiles/profile/Default/Cookies",
            "_internal/debug/screenshot.png",
            "_internal/export-state.json",
            "_internal/.export-state/urls.json",
            "_internal/imports/ledger.json",
        )):
            with self.subTest(relative=relative):
                self.package = self.root / f"case-{index}"
                self.package.mkdir()
                self.write(relative, b"private fixture secret")
                with self.assertRaises(PackagePrivacyError) as error:
                    self.audit()
                self.assertIn("PRIVATE_STATE_FILE", error.exception.failures)
                self.assertNotIn("wxid_private", str(error.exception))
                self.assertNotIn("fixture secret", str(error.exception))

    def test_missing_or_empty_package_is_rejected(self):
        for directory, code in ((self.root / "missing", "MISSING_PACKAGE_DIRECTORY"), (self.package, "EMPTY_PACKAGE_DIRECTORY")):
            with self.subTest(code=code), self.assertRaisesRegex(PackagePrivacyError, code):
                audit_package(directory, private_prefixes=[self.home])

    def test_builder_path_is_rejected_in_raw_and_compressed_contents(self):
        raw = self.write("_internal/runtime/bin/engine", str(self.home).encode())
        with self.assertRaisesRegex(PackagePrivacyError, "BUILDER_PRIVATE_PATH"):
            self.audit()
        raw.unlink()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("source.pyc", str(self.home).encode())
        self.write("_internal/base_library.zip", output.getvalue())
        with self.assertRaisesRegex(PackagePrivacyError, "BUILDER_PRIVATE_PATH") as error:
            self.audit()
        self.assertNotIn(str(self.home), str(error.exception))

    def test_arbitrary_exported_images_and_extra_docs_are_blocked(self):
        self.write("picture.png")
        self.write("docs/private-notes.md")
        with self.assertRaises(PackagePrivacyError) as error:
            self.audit()
        self.assertIn("UNEXPECTED_USER_IMAGE", error.exception.failures)
        self.assertIn("UNEXPECTED_DOCUMENT", error.exception.failures)

    def test_package_symlink_cannot_reference_user_files(self):
        outside = self.root / "outside-private-file"
        outside.write_bytes(b"unread private fixture")
        link = self.package / "_internal/link"
        link.parent.mkdir()
        link.symlink_to(outside)
        with self.assertRaisesRegex(PackagePrivacyError, "OUTSIDE_PACKAGE_LINK"):
            self.audit()

    def test_tar_removes_owner_and_extended_metadata_preserving_relative_name(self):
        name = "wechat-emoji/" + "long-relative-name-" * 10 + ".txt"
        info = tarfile.TarInfo(name)
        info.uid, info.gid, info.uname, info.gname = 501, 20, "private-owner", "private-group"
        info.mtime = 123456789
        info.pax_headers = {"path": name, "uname": "private-owner", "atime": "123", "ctime": "456"}
        cleaned = sanitized_tarinfo(info)
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            archive.addfile(cleaned)
        with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r") as archive:
            result = archive.getmembers()[0]
        self.assertEqual((result.uid, result.gid, result.uname, result.gname, result.mtime), (0, 0, "", "", 0))
        self.assertEqual(result.name, name)
        self.assertEqual(result.pax_headers, {"path": name})
        self.assertNotIn(b"private-owner", output.getvalue())
        self.assertEqual(info.uname, "private-owner")

    def test_tar_rejects_outside_links_and_keeps_internal_framework_link(self):
        info = tarfile.TarInfo("wechat-emoji/_internal/Python")
        info.type = tarfile.SYMTYPE
        info.linkname = "Python.framework/Versions/Current/Python"
        self.assertEqual(sanitized_tarinfo(info).linkname, info.linkname)
        for name in ("../../../outside", "/private/builder/file"):
            info.linkname = name
            with self.assertRaisesRegex(PackagePrivacyError, "UNSAFE_ARCHIVE_LINK"):
                sanitized_tarinfo(info)

    def test_complete_archive_has_no_gzip_timestamp_or_builder_owner(self):
        self.write("README.md")
        destination = self.root / "distribution.tar.gz"
        result = build_archive(self.package, destination, private_prefixes=[self.home])
        self.assertEqual(result["files"], 1)
        content = destination.read_bytes()
        self.assertEqual(content[4:8], b"\0" * 4)
        self.assertEqual(content[3] & 8, 0)  # No gzip original filename field.
        with tarfile.open(destination, "r:gz") as archive:
            members = archive.getmembers()
        self.assertTrue(all((m.uid, m.gid, m.uname, m.gname, m.mtime) == (0, 0, "", "", 0) for m in members))
        self.assertEqual({member.name for member in members}, {"wechat-emoji", "wechat-emoji/README.md"})

    def test_blocked_archive_does_not_replace_an_existing_result(self):
        destination = self.root / "distribution.tar.gz"
        destination.write_bytes(b"existing result")
        self.write("_internal/Cookies")
        with self.assertRaisesRegex(PackagePrivacyError, "PRIVATE_STATE_FILE"):
            build_archive(self.package, destination, private_prefixes=[self.home])
        self.assertEqual(destination.read_bytes(), b"existing result")


class RustBuildPrivacyTests(unittest.TestCase):
    def run_build_script(self, environment):
        source = (Path(__file__).resolve().parents[1] / "scripts/build-engine.sh").read_text()
        embedded = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        project = Path("/private/build workspace/project with spaces")
        home = Path("/private/builder home")
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("sys.argv", ["-", str(project)]),
            patch("pathlib.Path.home", return_value=home),
            patch("subprocess.run") as cargo,
        ):
            exec(compile(embedded, "build-engine.sh", "exec"), {})
        arguments = cargo.call_args.args[0]
        flags = cargo.call_args.kwargs["env"]["CARGO_ENCODED_RUSTFLAGS"].split("\x1f")
        self.assertEqual(arguments[-1], str(project / "vendor/wxemoticon/cli/Cargo.toml"))
        self.assertIn(f"--remap-path-prefix={home}=/build/home", flags)
        self.assertIn(f"--remap-path-prefix={project}=/build/wechat-emoji-to-feishu", flags)
        return flags

    def test_encoded_flags_and_paths_with_spaces_remain_individual_arguments(self):
        flags = self.run_build_script({"CARGO_ENCODED_RUSTFLAGS": "--cfg\x1fflag=\"with spaces\""})
        self.assertEqual(flags[:2], ["--cfg", 'flag="with spaces"'])

    def test_legacy_flags_are_preserved_and_empty_encoded_flags_override_them(self):
        flags = self.run_build_script({"RUSTFLAGS": '-C opt-level=2 --cfg \'flag="with spaces"\''})
        self.assertEqual(flags[:4], ["-C", "opt-level=2", "--cfg", 'flag="with spaces"'])
        flags = self.run_build_script({"CARGO_ENCODED_RUSTFLAGS": "", "RUSTFLAGS": "--unused-flag"})
        self.assertNotIn("--unused-flag", flags)


if __name__ == "__main__":
    unittest.main()
