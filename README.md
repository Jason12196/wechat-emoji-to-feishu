# 微信表情导入飞书

面向 Mac 的统一 CLI：整合微信表情提取、资源还原、动画处理与飞书个人自定义表情导入。后续 Electron 前端只需调用本 CLI。

## 安装（源码开发版）

需要 Python 3.10+、Rust、macOS SDK / Xcode Command Line Tools。

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
./scripts/build-engine.sh
python -m playwright install chromium
wechat-emoji --version
wechat-emoji --json doctor
```

Rust 源码已保留在 vendor/wxemoticon。编译产物放在 runtime/bin，不提交到 Git；也可用 WXEMOTICON_BIN 指定已有的本项目修改版提取 CLI。通用上游 CLI 不包含本项目增加的 --metadata-out 接口。

## 使用

全局参数（--json、--home、--wechat-root）放在子命令之前。

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

新仓库验证使用隔离状态与合成图片，不继续上传用户的飞书。Intel、Windows、其他微信版本以及独立安装包未做端到端验证。

```sh
python -m unittest discover -s tests -v
cargo test --locked --release --manifest-path vendor/wxemoticon/cli/Cargo.toml
```

## 来源

见 [THIRD_PARTY.md](THIRD_PARTY.md) 和 [LICENSE](LICENSE)。保留上游版权、许可证和源码归属。
