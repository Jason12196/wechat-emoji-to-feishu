# 微信表情导入飞书

面向 Mac 的统一 CLI：整合微信表情提取、资源还原、动画处理与飞书个人自定义表情导入。后续 Electron 前端只需调用本 CLI。

## 安装与版本选择

只安装 CLI 就能导出微信表情、处理图片和导入飞书个人自定义表情，无需 Electron。Electron 图形界面尚未开发。

| Mac 芯片 | 下载文件 |
| --- | --- |
| Apple Silicon（M1/M2/M3/M4 等） | `wechat-emoji-macos-arm64.tar.gz` |
| Intel | `wechat-emoji-macos-x86_64.tar.gz` |

在苹果菜单 → 关于本机中查看芯片。两种包使用相同命令，分别构建，不要混用。目前提供 CI 测试产物，尚未发布正式 Release；签名、公证和干净机器验收仍需完成。Windows/Linux 暂不提供支持。

### 下载 CLI 安装包

仓库目前为私有，需要获得仓库访问权限并登录 GitHub。

1. 打开仓库的 [Actions 页面](https://github.com/Jason12196/wechat-emoji-to-feishu/actions)，选择最新一次成功完成的 **CLI checks**。
2. 在运行详情底部的 **Artifacts** 下载 `macos-cli-arm64` 或 `macos-cli-x86_64`。产物保留 7 天；若需要的架构尚未构建成功，先等待检查完成。
3. 解压 GitHub 下载的 ZIP，再解压里面的 `.tar.gz`，得到 `wechat-emoji` 文件夹。保留整个文件夹，不要只拷贝可执行文件。
4. 在终端进入解压目录，执行：

```sh
cd /你的解压位置/wechat-emoji
./wechat-emoji --version
./wechat-emoji doctor
# 让当前终端可以直接使用后文的 wechat-emoji 命令
export PATH="$PWD:$PATH"
```

包内包含 Python、Python 模块、Rust 提取引擎和 Playwright，无需自行安装 Python、Rust 或 Xcode。微信需要自行安装；飞书使用浏览器登录，无需安装飞书客户端。

`doctor` 检测通过不代表微信密钥或飞书登录已经可用。第一次使用尚无 Chromium 时，`chromium_ready` 和 `ready` 会为 false，按下一节准备浏览器即可。

### 首次下载浏览器

首次飞书登录或导入会自动下载匹配版本的 Chromium，显示下载进度；也可提前执行：

```sh
wechat-emoji browser install
```

该命令下载并验证本地浏览器启动，不访问飞书。下载失败会自动重试一次；仍失败时，检查网络后重新执行同一命令。后续复用缓存，升级 CLI 后可能需要下载新的浏览器版本。下载、微信登录和飞书导入均需要网络。

默认缓存：`~/Library/Caches/ms-playwright`。如需更换位置，在运行 CLI 前设置：

```sh
export WECHAT_EMOJI_BROWSER_CACHE="/你选择的位置/wechat-emoji-browsers"
wechat-emoji browser install
```

浏览器缓存与账号登录目录分开，重新下载浏览器不会主动清除登录状态。

### 从源码安装（开发者）

需要 Git、Python 3.10+、Rust、macOS SDK / Xcode Command Line Tools。

```sh
git clone https://github.com/Jason12196/wechat-emoji-to-feishu.git
cd wechat-emoji-to-feishu
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
./scripts/build-engine.sh
wechat-emoji --version
wechat-emoji doctor
# 可选：提前准备浏览器
wechat-emoji browser install
```

### 在 Codex / Claude Code 中使用

先按上面任一方式安装 CLI，再在同一台 Mac 的本地 Codex 或 Claude Code 中使用。不需要安装 Electron，也不需要另建 MCP 服务；助手必须能执行本地命令，云端环境不能直接读取这台 Mac 的微信数据。

将以下提示词中的路径替换为实际路径，发送给助手：

```text
使用 /实际解压目录/wechat-emoji/wechat-emoji。
先运行 --version 和 --json doctor，其他参数先查 --help。
仅处理本机微信表情与飞书个人自定义表情。
导出后先展示导入计划，询问我飞书已有表情数量和本次选择范围。
实际导入前让我核对接收账号并确认；需要扫码登录时提示我操作窗口。
不要自动删除既有表情，不要自动重传 pending/unknown 项。
```

源码安装时，将可执行文件路径换成 `/实际克隆目录/.venv/bin/wechat-emoji`。`--json` 必须放在子命令之前，便于助手读取进度与结果。微信和飞书登录仍由用户完成。目前提供命令接入方式，尚无专用 Skill 或一键安装器。

## 使用

微信默认全量导出。飞书可导入整个目录，或用 `--limit N` 选择排序后的前 N 张；若要挑选特定图片，可先复制到单独目录再导入。CLI 目前没有逐张勾选界面。

普通终端使用可省略 `--json`；需要逐行 JSON 输出时再加上。全局参数（--json、--home、--wechat-root）放在子命令之前。

```sh
# 只读检测
wechat-emoji --json doctor
wechat-emoji --json accounts

# 显式获取密钥：先退出微信，在工具启动的副本里登录并打开一次表情面板
wechat-emoji --json key

# 提取、备用下载、AES 还原、逐帧校验、按需压缩；保留原图与动图
wechat-emoji --json extract --out ./exported

# 已有图片的校验与处理
wechat-emoji --json images inspect ./exported
wechat-emoji --json images prepare ./pictures --out ./prepared

# 离线导入计划；个人表情按 1000 上限预检查，不启动浏览器
wechat-emoji --json feishu plan ./exported --account my-account --existing-count 900 --limit 50

# 登录与实际导入；请核对浏览器登录身份与命名账号一致
wechat-emoji --json feishu login --account my-account
wechat-emoji --json feishu import ./exported --account my-account --existing-count 900 --limit 50

# 任务记录
wechat-emoji --json tasks list
wechat-emoji --json tasks show TASK_UUID
```

个人模式必须明确提供当前已有数量。超出可用容量时直接返回 CAPACITY_EXCEEDED，不启动浏览器，不删除任何既有表情。--limit 明确选择排序后的前 N 张，不会自动截断整个任务。仅支持个人自定义表情，无需企业管理员权限。

## 前端调用协议

--json 下 stdout 是逐行 JSON（NDJSON）。每行包含 protocol_version=1、task_id、type、time；type 为 started、progress、action_required、result 或 error。旧模块日志送往 stderr，密钥不出现在协议中。示例与约定见 [docs/protocol.md](docs/protocol.md)。

退出码：0 完成；1 引擎错误；2 参数/计划不成立；3 部分完成；130 用户中断。取消可向进程发送 SIGINT。中断时已提交的 pending/unknown 项不能自动重传。

## 数据与恢复

默认私有状态目录：~/Library/Application Support/wechat-emoji-to-feishu；可用 --home 或 WECHAT_EMOJI_HOME 覆盖。

- 每个 --account 标签有独立 Chromium 登录目录；标签不是远端身份验证，用户仍须核对实际登录账号。
- 每个任务记录最终结果；个人导入另有逐项 ledger。恢复使用 --ledger PATH，且必须与原命名账号相同。pending/unknown 项先人工核对，不自动重新提交。
- originals 保留下载源文件，verified-originals 保留有效原图，顶层保存可导入副本。export-report.json 决定导入列表，避免重复导入原图。
- 密钥由提取引擎保留在本机私有缓存；资源元数据临时文件结束后删除。
- 导入只添加自定义表情，不发送聊天消息。

## 验证边界

历史本机验证：微信 4.1.15 (270135)、Apple Silicon；996 条记录成功导出、全部逐帧解码；个人导入链路已部分验证。受飞书个人表情容量约束，未声称 996 张全部导入成功。

新仓库验证使用隔离状态与合成图片，不继续上传用户的飞书。CLI 已在 Apple Silicon 本机验证打包、换目录启动、首次浏览器下载、缓存复用与合成图片处理。CI 对 Apple Silicon 和 Intel 分别检查构建与启动；Intel 真实微信取密钥及飞书导入、其他微信版本尚未完成端到端验证。

```sh
python -m unittest discover -s tests -v
cargo test --locked --release --manifest-path vendor/wxemoticon/cli/Cargo.toml
```

## 常见问题

- **提示找不到命令**：在解压目录使用 `./wechat-emoji`，或重新执行上面的 PATH 设置。该设置只对当前终端有效。
- **微信需要重新登录吗？** 已有密钥有效时通常可复用；获取或刷新密钥时按提示退出原微信，在工具启动的副本中登录并打开一次表情面板。
- **飞书需要重新登录吗？** 首次在独立 Chromium 窗口登录；登录状态在本机保存，失效后重新登录。`--account` 是本地标签，务必核对窗口中的实际账号。
- **飞书已有数量怎么填？** 当前需要用户手动提供，不会自动读取。按个人自定义表情上限 1000 预检查；已满时不会继续上传。
- **导入中断怎么办？** 查看任务记录及 ledger；成功项可跳过，pending/unknown 项需先人工核对，避免重复添加。
- **Mac 阻止启动怎么办？** 当前是未公证的测试包，可使用源码安装；正式安装包的签名、公证与下载启动体验仍待验收。

## 开发与 CI

每次提交会自动检查 Python 和 Rust，并分别构建两种 Mac 架构的 CLI 测试包。CI 不会登录微信、飞书或上传表情。打包与维护者授权步骤见 [开发与 CI 说明](docs/installation.md)。

## 来源

见 [THIRD_PARTY.md](THIRD_PARTY.md) 和 [LICENSE](LICENSE)。保留上游版权、许可证和源码归属。
