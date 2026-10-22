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
    "--name", "wechat-emoji", "--collect-data", "playwright", "--exclude-module", "Crypto.SelfTest",
    "--strip",
    "--add-binary", f"{engine}:runtime/bin", "--paths", str(root / "src"),
    "--specpath", str(root / "build"), str(root / "scripts/cli-entry.py"),
], cwd=root, check=True)
folder = root / "dist/wechat-emoji"
for name in ("LICENSE", "THIRD_PARTY.md"):
    shutil.copy2(root / name, folder / name)
(folder / "README.md").write_text("""# 表情迁移 CLI

将微信收藏表情导出到本机，或导入飞书个人自定义表情。目前支持 macOS。
本压缩包已包含 Python、提取引擎及运行依赖；首次登录飞书时会自动下载浏览器。

在终端进入本目录运行：

```sh
./wechat-emoji --help
./wechat-emoji doctor
```

请保留整个文件夹，不能只移动其中的 wechat-emoji 可执行文件。
本项目目前没有 Apple Developer ID 签名或公证；如系统阻止打开，请在尝试运行后到
系统设置 → 隐私与安全性查看“仍要打开”，或改用源码启动包。

完整安装说明、命令示例、Electron 和 Codex / Claude Code 使用方式：
[项目 README](https://github.com/Jason12196/wechat-emoji-to-feishu#readme)。

包内不包含使用者的登录状态、密钥、表情图片、导入记录或诊断日志。
开源许可保留在 LICENSE、THIRD_PARTY.md 和 dependency-licenses 中。
""", encoding="utf-8")
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
