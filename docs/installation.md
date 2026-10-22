# 安装与分发

当前面向 Mac，提供单一 CLI 分发方案：内置运行依赖，Chromium 首次使用自动下载并缓存。Windows/Linux 保留后端扩展方向，暂不承诺支持。

## 版本选择

| 方式 | 包含内容 | 用户需要准备 | 当前状态 |
| --- | --- | --- | --- |
| CLI | Python 运行时、Python 模块、Rust 引擎、Playwright；Chromium 首次自动下载 | 微信、飞书账号、网络 | Apple Silicon 本机打包与启动验证通过 |
| Electron App | 图形界面与同一套 CLI 核心 | 微信、飞书账号、网络 | 待开发 |
| Codex / Claude Code | 调用同一套 CLI 的说明 | 本机可执行命令的助手环境 | 接入步骤见下文 |

不再单独维护预带 Chromium 的大包。CLI 下载与登录仍需要网络；浏览器下载失败会重试一次，之后可重新运行 `wechat-emoji browser install`。下载进度通过日志/JSON progress 事件提供，缓存保留供 Playwright 安装器再次检查。浏览器版本跟随内置 Playwright，升级后必要时会下载对应版本。

默认浏览器缓存使用 `~/Library/Caches/ms-playwright`；可用 `WECHAT_EMOJI_BROWSER_CACHE` 覆盖。账号登录目录与缓存分开，不随浏览器重装清除。`doctor` 仅检查，不自动下载；`browser install` 下载并验证无头浏览器启动，不访问飞书。首次登录或导入也会自动准备浏览器。

## Mac CLI 分发包

解压 `wechat-emoji-macos-arm64.tar.gz`（Apple Silicon）后，保留整个目录，不要只拷贝其中的可执行文件：

```sh
cd wechat-emoji
./wechat-emoji --version
./wechat-emoji doctor
# 可提前下载；也可等首次飞书登录/导入时自动下载
./wechat-emoji browser install
```

无需安装 Python、Rust 或 Xcode。当前包是本机测试产物，尚未作为 GitHub Release 发布；签名、公证与干净机器验收仍需完成。Intel 需要在对应架构另行构建验证，不能使用 arm64 包。

开发者打包：完成下方源码安装后，执行 `python -m pip install pyinstaller`，再执行 `python scripts/package-macos.py`，产物位于 dist。脚本只打包项目资源，不收集用户密钥、图片或登录配置。

取密钥辅助 dylib 已由 Rust build.rs 编译并嵌入引擎，开发者构建时需要 Xcode Command Line Tools，预编译包运行时不再现场编译。应用签名、Mac 下载后的启动体验和干净机器验收属于发布前工作。

## 当前可用：源码版

先安装 Git、Python 3.10+、Rust 和 Xcode Command Line Tools。在有仓库访问权限的 Mac 上执行：

```sh
git clone https://github.com/Jason12196/wechat-emoji-to-feishu.git
cd wechat-emoji-to-feishu
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
./scripts/build-engine.sh
python -m playwright install chromium
wechat-emoji --version
wechat-emoji doctor
```

仓库目前为私有，克隆需要 GitHub 账号已获授权。doctor 检测通过不代表微信密钥或飞书登录已经可用；继续按 README 的导出与导入步骤操作。

## Codex / Claude Code 接入

1. 先完成上述源码安装；也可使用上述 CLI 分发包。
2. 在相同 Mac 的本地项目中打开 Codex 或 Claude Code，确保该工具有本地命令执行能力。云端环境无法直接访问用户 Mac 的微信数据与登录窗口。
3. 告诉助手 CLI 的绝对路径。源码版为克隆目录下的 `.venv/bin/wechat-emoji`，无需修改全局 PATH，也无需添加虚构的 MCP 服务配置。
4. 可以使用下面的提示词，替换实际路径：

```text
使用 /实际克隆目录/.venv/bin/wechat-emoji，先运行 --version 和 --json doctor。
需要读取命令说明时使用 --help；全局 --json 放在子命令之前。
仅处理本机微信表情与飞书个人自定义表情。
导出后先展示导入计划，询问我飞书已有表情数量和本次选择范围。
实际导入前让我核对接收账号并确认；需要扫码登录时提示我操作窗口。
不要自动删除既有表情，不要自动重传 pending/unknown 项。
```

登录仍由用户在本机窗口完成，接入 AI 助手不会绕过微信或飞书登录。`--json` 是逐行事件协议，可展示进度与结果；它不是 MCP 服务。专用 Skill 和一键安装命令将随可分发包提供，目前不宣称已经存在。

## CI 授权与启用

CI 配置位于 `.github/workflows/ci.yml`，在 push、pull request 或手动触发时运行。维护者创建/更新 workflow 文件所用凭据需要 workflow scope；首次授权步骤如下。

在本机终端执行：

```sh
gh auth refresh --hostname github.com --scopes workflow
```

按终端提示打开 GitHub 授权页面、输入设备验证码（如有），确认账号是 Jason12196，然后批准 GitHub CLI 请求的权限。不要发送 token 或验证码给他人。完成后执行：

```sh
gh auth status --hostname github.com
```

确认 Token scopes 包含 workflow。官方说明：https://cli.github.com/manual/gh_auth_refresh

仓库 Settings → Actions → General 中确保允许 GitHub 官方 Actions。当前工作流只使用 actions/checkout、actions/setup-python、actions/upload-artifact，且只需 contents: read；不需要将 Workflow permissions 改成 Read and write。

配置提交后，即可在仓库 Actions 页查看运行。当前工作流检查 Python 与 Rust 测试，并构建 Mac CLI、检查启动和保留 7 天测试产物。不执行真实微信提取或飞书上传；CI 产物不等同于已签名公证的正式 Release。
