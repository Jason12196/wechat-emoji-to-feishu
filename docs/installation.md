# 开发、打包与 CI

面向用户的下载、`pnpm dev` 启动、操作步骤、Codex / Claude Code 接入和常见问题，统一维护在[根 README](../README.md)。本文仅介绍维护者如何构建。

## 开发桌面界面

准备 Node.js 22.12+、pnpm 10，在仓库根目录运行：

```sh
pnpm dev
```

启动脚本安装锁定依赖、找到或下载本项目 CLI、构建前端并启动 Electron。含 CLI 的源码包不需要编译 Python/Rust；普通仓库需要可用的 GitHub 下载权限或 `WECHAT_EMOJI_CLI`。内部结构与本地诊断见 [desktop/README.md](../desktop/README.md)。

## 从源码构建 CLI

完整编译需要 Python 3.10+、Rust、Xcode Command Line Tools。以下命令在仓库根目录执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . pyinstaller
./scripts/build-engine.sh
python scripts/package-macos.py
```

结果在 `dist/wechat-emoji`，同时输出对应架构的 `wechat-emoji-macos-*.tar.gz`。构建必须在对应架构的 Mac 上执行；ARM 和 Intel 产物不可混装。

Rust 提取引擎位于 `runtime/bin`；开发时可用 `WXEMOTICON_BIN` 指定本项目修改版引擎。通用上游引擎没有本项目的 `--metadata-out` 参数。取密钥辅助 dylib 在 Rust 构建时编译并嵌入，用户运行分发包时不需要编译。

## 生成桌面包和源码包

先完成 CLI 构建，再安装桌面依赖并构建前端：

```sh
pnpm install --frozen-lockfile
pnpm --dir desktop build
python scripts/package-desktop.py
python scripts/package-source.py
```

| 产物 | 内容 |
| --- | --- |
| `wechat-emoji-desktop-macos-ARCH.zip` | `表情迁移.app`，Electron 运行时、构建后的界面、内置 CLI 和必要声明 |
| `wechat-emoji-source-macos-ARCH.zip` | 可编辑源码、锁文件、必要说明、预编译 CLI；用户在根目录运行 `pnpm dev` |
| `wechat-emoji-macos-ARCH.tar.gz` | 完整 CLI 运行目录 |

`ARCH` 为 `arm64` 或 `x86_64`。源码包不带 `node_modules`，首次启动按锁文件下载；应用包不包含开发依赖、测试、原始工程目录或本机状态。源码包按显式范围和 Git 跟踪文件生成，新增运行文件时需要同步检查打包清单。

图标源和生成方式由 `scripts/build-icons.mjs` 管理，成品位于 `desktop/assets`。修改图标后重新生成并打包。

应用包使用本地 ad-hoc 签名以满足修改后的 ARM64 可执行包要求，**这不是 Apple Developer ID 签名，也不包含公证**。下载后仍可能被 Gatekeeper 阻止；用户应能选择源码启动。不要将构建成功表述为签名、公证或干净机器验收成功。

## 打包隐私边界

打包脚本只收集必要运行文件和说明；源码包额外收集明确范围内的项目源码。`scripts/package_privacy.py` 检查实际包内容、嵌入归档和私人路径，发现密钥、浏览器状态、用户图片、任务或诊断文件等禁止内容时终止打包。归档不携带本机用户名等文件所有者信息。

运行状态在用户的 Application Support 中；导出图片在用户选择的位置。不要为了清理工程而删除这些目录。新的资源、缓存或入口加入打包流程时，应同时审查隐私规则和许可证范围。

## CI

`.github/workflows/ci.yml` 在 push、pull request 和手动触发时运行。检查代码并分别在 Apple Silicon / Intel runner 上构建 CLI、Electron 和源码包，上传 7 天有效的 Actions 产物。CI 使用隔离数据，不登录微信或飞书、不做真实导出和上传。

维护者首次通过 GitHub CLI 创建或修改 workflow，若凭据缺少权限，可在本机执行：

```sh
gh auth refresh --hostname github.com --scopes workflow
gh auth status --hostname github.com
```

授权由维护者本人在本机完成，勿分享 token 或验证码。下载产物不需要 workflow 写入权限。仓库 Settings → Actions → General 中允许所用官方 Actions 即可；当前工作流按最小权限配置，不需要改成仓库全局读写。

[GitHub CLI 授权说明](https://cli.github.com/manual/gh_auth_refresh)
