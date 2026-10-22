"""Package editable source with the matching CLI, without local development data."""

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from package_privacy import audit_package, build_zip

ROOT_FILES = (
    "README.md", "INSTALL_FOR_AGENTS.md", "LICENSE", "THIRD_PARTY.md", "pyproject.toml",
    "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", ".gitignore", ".gitattributes",
)
DESKTOP_FILES = (
    "README.md", "package.json", "package-lock.json", "index.html", "vite.config.js", ".prettierignore",
    "assets/icon.png", "assets/icon.icns",
)
SCRIPTS = (
    "dev.mjs", "build-icons.mjs", "build-engine.sh", "cli-entry.py", "package-macos.py",
    "package-source.py", "package-desktop.py", "package_privacy.py",
)
SOURCE_TREES = {
    "src/wechat_emoji_cli": {".py", ".wechatemoji"},
    "desktop/src": {".js", ".jsx", ".css", ".svg", ".ico"},
    "desktop/electron": {".cjs"},
    "vendor/wxemoticon/cli": {".rs", ".toml", ".lock"},
    "vendor/wxemoticon/tools/wechat-key-dumper": {".sh", ".c"},
}


def main():
    root = Path(__file__).resolve().parents[1]
    if sys.platform != "darwin":
        raise SystemExit("Source kits currently bundle a macOS CLI; build on macOS.")
    architecture = platform.machine()
    cli = root / "dist/wechat-emoji"
    audit_package(cli, private_prefixes=[Path.home(), root])
    binary_arch = subprocess.check_output(["lipo", "-archs", str(cli / "wechat-emoji")], text=True).split()
    if architecture not in binary_arch:
        raise SystemExit("The bundled CLI does not match this machine's architecture.")

    required = [Path(name) for name in ROOT_FILES]
    required += [Path("desktop") / name for name in DESKTOP_FILES]
    required += [Path("scripts") / name for name in SCRIPTS]
    required += [Path("docs") / name for name in ("installation.md", "protocol.md")]
    missing = [str(path) for path in required if not (root / path).is_file()]
    if missing:
        raise SystemExit("Missing source kit inputs: " + ", ".join(missing))

    # The tracked file list prevents an untracked local scratch module from entering a kit.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    sources = set(required)
    for name in tracked:
        path = Path(name)
        if any(path.is_relative_to(base) and path.suffix in extensions for base, extensions in SOURCE_TREES.items()):
            sources.add(path)

    (root / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-kit-", dir=root / "build") as temporary:
        folder = Path(temporary) / "wechat-emoji-to-feishu"
        folder.mkdir()
        allowed = set()
        for relative in sorted(sources):
            source = root / relative
            if source.is_symlink() or not source.resolve(strict=True).is_relative_to(root):
                raise SystemExit("Source kit inputs must be regular files within the repository.")
            destination = folder / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
            allowed.add(relative)
            allowed.update(relative.parents)
        shutil.copytree(cli, folder / "dist/wechat-emoji", symlinks=True, copy_function=shutil.copyfile)
        # copyfile deliberately drops extended attributes; retain only executable permissions.
        for source in cli.rglob("*"):
            if source.is_file() and not source.is_symlink():
                (folder / "dist/wechat-emoji" / source.relative_to(cli)).chmod(
                    0o755 if source.stat().st_mode & 0o111 else 0o644
                )
        allowed.add(Path("dist"))
        archive = root / f"dist/wechat-emoji-source-macos-{architecture}.zip"
        result = build_zip(
            folder, archive, private_prefixes=[Path.home(), root],
            resource_policy=lambda path: path in allowed or path.is_relative_to("dist/wechat-emoji"),
            image_policy=lambda path: path == Path("desktop/assets/icon.png")
            or path.is_relative_to("dist/wechat-emoji/_internal/playwright"),
        )
        print(f"Source kit privacy check passed: {result['files']} files, {result['embedded_entries']} embedded entries.")
        print(archive)


if __name__ == "__main__":
    main()
