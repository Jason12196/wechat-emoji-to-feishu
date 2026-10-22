# 开发、打包与 CI

用户安装、浏览器下载、操作步骤、Codex / Claude Code 接入和常见问题统一维护在 [README](../README.md)。

## 源码安装

需要 Git、Python 3.10+、Rust 和 Xcode Command Line Tools。

```sh
git clone https://github.com/Jason12196/wechat-emoji-to-feishu.git
cd wechat-emoji-to-feishu
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
./scripts/build-engine.sh
wechat-emoji --version
wechat-emoji doctor
```

用户使用与助手安装入口见 README 和 INSTALL_FOR_AGENTS.md。

## 开发者打包

按 README 完成源码安装后执行：

```sh
python -m pip install pyinstaller
python scripts/package-macos.py
```

产物位于 dist。构建需在对应架构的 Mac 上执行；脚本只打包项目资源，不收集用户密钥、图片或登录配置。Rust 提取引擎位于 runtime/bin；开发时可用 WXEMOTICON_BIN 指定本项目修改版引擎。通用上游引擎不含本项目新增的 --metadata-out 参数。

取密钥辅助 dylib 在 Rust 构建时编译并嵌入引擎，分发包运行时无需编译。应用签名、公证和干净机器验收仍需在正式发布前完成。

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

配置提交后，即可在仓库 Actions 页查看运行。当前工作流检查 Python 与 Rust 测试，并分别构建 Apple Silicon / Intel Mac CLI、检查启动和保留 7 天测试产物。不执行真实微信提取或飞书上传；CI 产物不等同于已签名公证的正式 Release。
