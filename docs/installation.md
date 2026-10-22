# 安装与分发

当前仅提供 Mac 源码开发版；下述完整 CLI、精简 CLI、Electron 是确定的分发方向，尚无可下载的安装包。Windows/Linux 保留后端扩展方向，暂不承诺支持。

## 版本选择

| 方式 | 包含内容 | 用户需要准备 | 当前状态 |
| --- | --- | --- | --- |
| 完整 CLI | Python 运行时、Python 模块、Rust 引擎、Playwright 与对应 Chromium | 微信、飞书账号、网络 | 待打包验证 |
| 精简 CLI | 与完整 CLI 相同，但不附带 Chromium | 首次联网下载与当前 Playwright 匹配的 Chromium | 待打包验证 |
| Electron App | 图形界面、完整 CLI 及其浏览器依赖 | 微信、飞书账号、网络 | 待开发 |
| Codex / Claude Code | 调用已安装 CLI 的说明；复用完整或精简 CLI | 本机可执行命令的 Codex / Claude Code 环境 | 可按源码版接入，专用 Skill 待提供 |

“精简”仍保留全部功能；不要求普通用户安装 Python、Rust 或 Xcode。首次浏览器下载的引导、失败恢复及打包后的资源定位仍需实现/验证。不将使用系统 Chrome 作为精简版能运行的前提。

完整包免开发依赖安装，但登录、下载微信表情和上传飞书仍需网络。Mac Apple Silicon 与 Intel 应分别构建、验证和发布；目前只有 Apple Silicon 的历史本机验证。

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

1. 先完成上述源码安装；未来也可选择完整或精简 CLI 包。
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

仓库 Settings → Actions → General 中确保允许 GitHub 官方 Actions。当前工作流只使用 actions/checkout、actions/setup-python，且只需 contents: read；不需要将 Workflow permissions 改成 Read and write。

配置提交后，即可在仓库 Actions 页查看运行。当前工作流检查 Python 与 Rust 测试，不执行真实微信提取或飞书上传，也尚未自动产出安装包。后续打包发布工作流另行增加。
