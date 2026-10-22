"""Build a self-contained directory archive; browsers download on first use."""

import importlib.metadata
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from package_privacy import build_archive

root = Path(__file__).resolve().parents[1]
if sys.platform != "darwin":
    raise SystemExit("Only macOS packaging is currently supported")
engine = root / "runtime/bin/wxemoticon"
if not engine.is_file():
    raise SystemExit("Run ./scripts/build-engine.sh first")
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "wechat-emoji", "--collect-all", "playwright", "--collect-all", "Crypto",
    "--add-binary", f"{engine}:runtime/bin", "--paths", str(root / "src"),
    "--specpath", str(root / "build"), str(root / "scripts/cli-entry.py"),
], cwd=root, check=True)
folder = root / "dist/wechat-emoji"
for name in ("LICENSE", "THIRD_PARTY.md", "README.md"):
    shutil.copy2(root / name, folder / name)
documentation = folder / "docs"
documentation.mkdir(exist_ok=True)
for name in ("installation.md", "protocol.md"):
    shutil.copy2(root / "docs" / name, documentation / name)
shutil.copy2(root / "src/wechat_emoji_cli/engines/LICENSE.wechatemoji", folder)
licenses = folder / "dependency-licenses"
for package in ("pillow", "pycryptodome", "playwright", "greenlet", "pyee", "typing_extensions", "pyinstaller"):
    distribution = importlib.metadata.distribution(package)
    for entry in distribution.files or []:
        if any(word in entry.name.lower() for word in ("license", "copying", "notice")):
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                target = licenses / package / entry
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
archive = root / f"dist/wechat-emoji-macos-{platform.machine()}.tar.gz"
audit = build_archive(folder, archive, private_prefixes=[Path.home(), root])
print(f"Package privacy check passed: {audit['files']} files and {audit['embedded_entries']} embedded entries.")
print(archive)
