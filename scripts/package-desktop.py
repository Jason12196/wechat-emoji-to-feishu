"""Build a minimal macOS Electron app with an embedded CLI and no Developer ID."""

import json
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from package_privacy import audit_package, build_zip


def copy_tree(source, destination):
    """Copy runtime bytes and modes, never local filesystem extended attributes."""
    shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copyfile)
    for path in source.rglob("*"):
        if path.is_file() and not path.is_symlink():
            (destination / path.relative_to(source)).chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def main():
    root = Path(__file__).resolve().parents[1]
    if sys.platform != "darwin":
        raise SystemExit("Electron app bundles must currently be built on macOS.")
    desktop = root / "desktop"
    electron = desktop / "node_modules/electron/dist"
    cli = root / "dist/wechat-emoji"
    architecture = platform.machine()
    for binary in (electron / "Electron.app/Contents/MacOS/Electron", cli / "wechat-emoji"):
        if not binary.is_file():
            raise SystemExit("Install desktop dependencies and build the CLI before packaging.")
        if architecture not in subprocess.check_output(["lipo", "-archs", str(binary)], text=True).split():
            raise SystemExit("Electron and the bundled CLI must match this machine's architecture.")
    for name in ("dist/index.html", "assets/icon.icns", "assets/icon.png"):
        if not (desktop / name).is_file():
            raise SystemExit("Build the desktop renderer and icons before packaging.")
    audit_package(cli, private_prefixes=[Path.home(), root])
    (root / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-app-", dir=root / "build") as temporary:
        bundle = Path(temporary) / "表情迁移.app"
        copy_tree(electron / "Electron.app", bundle)
        contents = bundle / "Contents"
        resources = contents / "Resources"
        # Remove Electron's demo app and replace its default brand assets.
        for name in ("default_app.asar", "electron.icns"):
            (resources / name).unlink(missing_ok=True)
        shutil.copyfile(desktop / "assets/icon.icns", resources / "icon.icns")
        app = resources / "app"
        app.mkdir()
        copy_tree(desktop / "dist", app / "dist")
        copy_tree(desktop / "electron", app / "electron")
        (app / "assets").mkdir()
        shutil.copyfile(desktop / "assets/icon.png", app / "assets/icon.png")
        manifest = json.loads((desktop / "package.json").read_text())
        (app / "package.json").write_text(json.dumps({
            "name": "wechat-emoji-to-feishu", "productName": "表情迁移",
            "version": manifest["version"], "main": "electron/main.cjs",
        }, ensure_ascii=False, indent=2) + "\n")
        copy_tree(cli, resources / "cli")
        licenses = resources / "licenses"
        licenses.mkdir()
        for source, name in (
            (root / "LICENSE", "LICENSE"), (root / "THIRD_PARTY.md", "THIRD_PARTY.md"),
            (electron / "LICENSE", "LICENSE.electron"),
            (electron / "LICENSES.chromium.html", "LICENSES.chromium.html"),
            (desktop / "node_modules/react/LICENSE", "LICENSE.react"),
            (desktop / "node_modules/react-dom/LICENSE", "LICENSE.react-dom"),
            (desktop / "node_modules/lucide-react/LICENSE", "LICENSE.lucide-react"),
        ):
            shutil.copyfile(source, licenses / name)
        scheduler = Path(subprocess.check_output([
            "node", "-e",
            "process.stdout.write(require.resolve('scheduler/package.json', {paths: [require.resolve('react-dom/package.json')]}))",
        ], cwd=desktop, text=True)).parent
        shutil.copyfile(scheduler / "LICENSE", licenses / "LICENSE.scheduler")
        info_file = contents / "Info.plist"
        info = plistlib.loads(info_file.read_bytes())
        info.update({
            "CFBundleDisplayName": "表情迁移", "CFBundleName": "表情迁移",
            "CFBundleIdentifier": "com.jason12196.wechat-emoji-to-feishu",
            "CFBundleIconFile": "icon.icns", "CFBundleShortVersionString": manifest["version"],
            "CFBundleVersion": manifest["version"], "CFBundleExecutable": "WechatEmoji",
        })
        info_file.write_bytes(plistlib.dumps(info))
        (contents / "MacOS/Electron").rename(contents / "MacOS/WechatEmoji")
        # Ad-hoc signing permits modified ARM64 bundles to launch; it is not Apple
        # Developer ID signing or notarization, and Gatekeeper may still block them.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
        archive = root / f"dist/wechat-emoji-desktop-macos-{architecture}.zip"
        result = build_zip(
            bundle, archive, private_prefixes=[Path.home(), root],
            resource_policy=lambda path: path.parts[0] == "Contents",
            image_policy=lambda path: path == Path("Contents/Resources/app/assets/icon.png")
            or path.is_relative_to("Contents/Resources/cli/_internal/playwright"),
        )
        print(f"Electron privacy check passed: {result['files']} files, {result['embedded_entries']} embedded entries.")
        print(archive)


if __name__ == "__main__":
    main()
