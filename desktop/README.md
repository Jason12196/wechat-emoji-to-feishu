# Electron 桌面界面

用户下载、源码启动、使用流程、常见问题和 AI 助手安装统一维护在[根 README](../README.md)。

## 开发入口

需要 Node.js 22.12+、pnpm 10。在**仓库根目录**运行：

```sh
pnpm dev
```

入口会安装锁定依赖、准备本项目 CLI、构建前端并启动真实 Electron。含 CLI 的源码包直接使用 `dist/wechat-emoji/wechat-emoji`；普通源码可通过已授权的 GitHub CLI 下载成功构建，或指定已有程序：

```sh
WECHAT_EMOJI_CLI="/实际位置/wechat-emoji/wechat-emoji" pnpm dev
```

仅查看浏览器演示可在本目录运行 `npm run dev`，地址为 `http://127.0.0.1:5196`。浏览器演示不读取本机文件、不调用真实 CLI；它不同于仓库根目录的 `pnpm dev`。

## 运行与诊断

真实应用启动时检测本机环境与账号。导出默认位于“下载”，可在绿色入口外更改；账号已有完整导出直接复用，未完成的继续处理。只有缺少有效密钥时才经用户确认正常退出微信、启动副本。

飞书使用独立浏览器，登录完成后保留窗口并在后续命令中复用。导入先检查选中清单和容量，由用户核对账号并确认上传。修改选择或已有数量后重新检查计划。

状态与 CLI 共用 `~/Library/Application Support/wechat-emoji-to-feishu`，可用 `WECHAT_EMOJI_HOME` 指定隔离位置：

- `desktop/jobs`：选择快照、账号绑定、任务 ID、结果与恢复依据。
- `desktop/selections`：选中项目的独立副本，上传前校验摘要。
- `diagnostics`：主进程阶段、错误码、时间线、退出码、信号及脱敏 stderr。
- `debug`：CLI 异常与引擎日志，原始内容仍可能含私人信息。

“查看诊断详情”支持复制脱敏摘要与打开目录。部分结果也会保留诊断，不将正常退出等同于全部成功。取消发送 SIGINT 并保留记录；`pending` / `unknown` 项需要实际核验，不能用勾选确认或删除记录绕过重传保护。

## 工程检查

以下命令在本目录执行，用于开发验证：

```sh
npm run check
npm run build
npm run test:bridge
npx playwright install chromium
npm test
```

桥接测试覆盖协议、错误、取消、并发、脱敏、选择变化和恢复；Electron 测试使用本地协议替身，浏览器测试覆盖演示流程。这些检查不代表真实账号、全量上传或所有 Mac 型号完成验收。

## 结构

- `electron/main.cjs`：应用与窗口生命周期、有限 IPC。
- `electron/services/runner.cjs`：CLI 子进程、NDJSON、取消和诊断。
- `electron/services/migration.cjs`：目录授权、图片资产、选择和任务恢复。
- `electron/preload.cjs`：有限接口，不开放任意命令或文件读写。
- `src/useRealMigration.js`：真实交互；`src/useMigration.js`：浏览器演示状态。
- `assets/icon.png`、`assets/icon.icns`：本项目应用图标。

渲染进程不开启 Node，图片通过仅映射已授权文件的 `emoji` 协议读取。打包说明见[开发与打包](../docs/installation.md)。

微信标志来自 [Simple Icons（CC0）](https://github.com/simple-icons/simple-icons/blob/develop/icons/wechat.svg)，飞书标志取自[官网 favicon](https://www.feishu.cn/favicon.ico)。品牌标志用于说明登录与迁移目标，不表示官方出品或关联。
