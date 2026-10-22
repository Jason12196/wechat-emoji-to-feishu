# Electron 桌面界面

黑白灰主体、无描边无阴影。微信入口使用品牌绿，飞书登录使用品牌蓝，示例插画为高饱和彩色。

## 本地运行

需要 Node.js 22.12+。先提供本项目的 CLI，再启动 Electron：

```sh
npm ci
npm start
```

默认使用仓库 `dist/wechat-emoji/wechat-emoji` 下打包的 CLI；也可以设置绝对路径：

```sh
WECHAT_EMOJI_CLI="/实际位置/wechat-emoji" npm start
```

这只是源码启动方式，目前没有 Electron 安装包。后续发行版将从应用资源目录的 cli/wechat-emoji 加载内置 CLI。

Electron 进入真实模式，只在启动时检测本机环境与微信账号。点击绿色微信卡片后选择导出位置；有有效缓存密钥时直接导出，否则提示完全退出微信并在副本中登录。选择本地图片会处理到独立目录，不覆盖原图。

导入时先检查本次勾选的图片清单与容量，再登录独立浏览器、由用户核对接收账号并开始上传。修改选择或已有数量后需重新检查计划。应用不会自动关闭微信、自动登录、自动整理飞书旧表情。

浏览器预览仍是明确标记的演示模式，不读取本机文件或调用真实 CLI：

```sh
npm run dev # http://127.0.0.1:5196
```

## 记录与诊断

默认状态与 CLI 共用 `~/Library/Application Support/wechat-emoji-to-feishu`，可用 WECHAT_EMOJI_HOME 指定隔离位置。

- `desktop/jobs`：本次选择、账号绑定、CLI 任务 ID、结果和恢复依据。
- `desktop/selections`：按选中项目复制的独立快照，上传前校验摘要，原图不受影响。
- `diagnostics`：主进程诊断，包含操作阶段、错误码、任务 ID、事件时间线、退出码、信号和脱敏 stderr。
- `debug`：CLI 的异常类型、调用栈和相关引擎日志。原始引擎日志仍可能含私人信息，不直接分享原文件。

界面通过“查看诊断详情”展示信息，支持复制脱敏摘要与打开诊断目录。密钥、Cookie、令牌和资源 URL 不进入分享摘要。部分结果也有诊断记录，不将 CLI 正常退出等同于全量成功。

停止导入会向 CLI 发送 SIGINT，保留记录。恢复从原 ledger 检查，pending/unknown 项仍会阻止自动重传，不能用勾选确认代替实际结果核验。重新启动后可以查看任务记录；恢复前需登录原本地账号标签并更新已有数量。

## 验证

```sh
npm run check
npm run build
npm run test:bridge
npx playwright install chromium
npm test
```

桥接测试覆盖协议、异常、超时、取消、并发、脱敏、选择变化和待核对恢复。Electron 测试通过本地协议替身验证完整 IPC/UI 路径，不登录微信或飞书；浏览器测试覆盖演示交互。真实 CLI 已另用合成图片验证处理、动图保留和单张计划，不能据此宣称真实登录/上传端到端验收完成。

## 结构

- electron/services/runner.cjs：CLI 子进程与 NDJSON、取消和诊断。
- electron/services/migration.cjs：目录授权、图片资产、本次选择与任务恢复。
- electron/preload.cjs：有限接口，不开放任意命令或文件读写。
- src/useRealMigration.js：真实状态；src/useMigration.js：浏览器演示状态。

渲染进程不开启 Node；图片通过仅映射已授权文件的 emoji 协议读取。

微信标志来自 Simple Icons（CC0）：https://github.com/simple-icons/simple-icons/blob/develop/icons/wechat.svg 。飞书标志取自其官网 favicon：https://www.feishu.cn/favicon.ico 。品牌标志用于说明登录与迁移目标，不表示官方出品或关联。
