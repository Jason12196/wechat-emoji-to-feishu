<div align="center">

<img src="desktop/assets/icon.png" alt="表情迁移" width="112" height="112">

# 表情迁移

**把喜欢的微信表情，带到飞书。**

Mac（目前） · Apple Silicon / Intel · 个人自定义表情

[下载与启动](#下载与启动) &nbsp;·&nbsp; [使用方式](#使用方式) &nbsp;·&nbsp; [交给 AI 助手](#交给-ai-助手) &nbsp;·&nbsp; [常见问题](#常见问题)

</div>

<br>

导出微信收藏，挑选想带走的图片，再添加到飞书个人表情面板。提供 **Electron 桌面应用**和 **CLI**，也可以把仓库链接交给 Codex、Claude Code 等本地助手完成安装。

| 留住原图和动图 | 接着上次继续 | 由你决定导入范围 |
| :--- | :--- | :--- |
| 本地处理，保留下载源文件与有效原图 | 已导出不重做，有效密钥直接复用 | 勾选图片、核对账号与容量，再开始 |

> 当前为测试版，**没有 Apple 开发者签名或公证**。推荐下载含 CLI 的源码包，在本机运行 `pnpm dev` 启动 Electron。Apple Silicon 已完成真实导出和导入验证；Intel 提供对应构建，仍待实机验证。新打包方式尚待干净机器验收。

## 下载与启动

准备好 **Mac、已安装且登录过的微信、接收表情的飞书账号和网络**。无需安装飞书客户端。

点击下表直接下载对应版本。当前为成功构建的测试包，尚未发布正式 Release。

“关于本机”显示 **Apple M 系列芯片**选 `arm64`；显示 **Intel 处理器**选 `x86_64`。

| 使用方式 | Apple Silicon | Intel | 适合谁 |
| :--- | :--- | :--- | :--- |
| **源码包 + Electron（推荐）** | [Apple Silicon 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12412757437) | [Intel 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12412549176) | 希望从源码在本机运行图形界面 |
| Electron 应用包 | [Apple Silicon 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12412552795) | [Intel 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12413630227) | 想直接打开桌面应用 |
| CLI | [Apple Silicon 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12412807186) | [Intel 下载](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/runs/39748947454/artifacts/12412359269) | 终端用户、脚本和本地 AI 助手 |

### 方式一：源码包，`pnpm dev` 启动 Electron

安装 [Node.js 22.12 或更新版本](https://nodejs.org/en/download)，并准备 pnpm 10；已有 pnpm 10 可跳过这一步：

```sh
npm install -g pnpm@10
```

在上表下载对应芯片的源码包，解压下载的 ZIP，再解压其中的 `wechat-emoji-source-macos-*.zip`，得到 `wechat-emoji-to-feishu` 文件夹。进入这个文件夹执行：

```sh
cd /你的解压位置/wechat-emoji-to-feishu
pnpm dev
```

**就这一个启动命令。** 首次会自动安装前端依赖、下载 Electron、构建界面并打开应用，之后可以再次执行相同命令启动。安装过程需要联网，终端会显示进度。保留该文件夹以及启动它的终端。

这个源码包已经带好对应架构的 CLI，**不用安装 Python、Rust 或 Xcode**。飞书所需的 Chromium 会在首次登录时自动下载，后续复用本机缓存。

<details>
<summary><strong>我下载的是 GitHub「Code → Download ZIP」或直接 git clone，可以启动吗？</strong></summary>

可以直接[下载仓库源码 ZIP](https://github.com/Jason12196/wechat-emoji-to-feishu/archive/refs/heads/main.zip)，在仓库根目录运行 `pnpm dev`。普通源码 ZIP 不含编译好的 CLI；请同时从上表下载对应芯片的 CLI，解压后按下面的方式指定。已有 GitHub CLI 的用户也可以让启动脚本自动获取成功构建的 CLI。

如果已经下载过本项目 CLI，也可以直接指定它，保留完整 CLI 文件夹：

```sh
WECHAT_EMOJI_CLI="/实际位置/wechat-emoji/wechat-emoji" pnpm dev
```

想省去单独准备 CLI 的步骤，直接选择上表的“源码包 + Electron”。

</details>

### 方式二：直接打开 Electron 应用包

在上表下载对应芯片的 Electron 应用包，解压下载的 ZIP，再解压其中的 `wechat-emoji-desktop-macos-*.zip`，得到 **表情迁移.app**，可以移入“应用程序”后打开。应用自带 CLI，首次登录飞书时下载浏览器。

这个包未签名、未公证，macOS 可能阻止启动。确认来源后可查看“系统设置 → 隐私与安全性”中的允许打开选项；如果仍无法打开，可以改用上面的源码包。**不需要关闭系统整体安全保护。**

### 方式三：仅使用 CLI

在上表下载对应芯片的 CLI，解压下载的 ZIP，再解压其中的 `wechat-emoji-macos-*.tar.gz`，保留整个 `wechat-emoji` 文件夹。打开终端：

```sh
cd /你的解压位置/wechat-emoji
./wechat-emoji --version
./wechat-emoji doctor
export PATH="$PWD:$PATH"
```

最后一行让当前终端能直接运行后文的 `wechat-emoji` 命令；新终端需要重新设置，或改用可执行文件完整路径。不要只复制可执行文件，它需要旁边的运行依赖。

首次登录飞书会自动下载 Chromium；也可以提前运行 `wechat-emoji browser install`。首次下载前 `doctor` 显示浏览器未就绪是正常的。

## 使用方式

### 在桌面应用里

1. **选择来源**：默认从微信收藏导出；导出位置默认“下载”，可以在绿色卡片外更改。已有图片也可以直接导入。
2. **读取微信表情**：点击绿色微信卡片，识别账号并准备导出。已有完整导出直接进入挑选，未完成的可以继续。
3. **挑选图片**：查看图片和动图，保留要导入的项目。
4. **准备飞书**：在独立浏览器登录并核对接收账号，填写已有个人表情数量，检查容量和计划。
5. **确认导入**：查看进度与结果；若中断，保留记录，按提示继续或核对未确认的项目。

只有需要获取微信密钥时，应用才会提示退出微信；点击确认后正常退出，并启动微信副本。如果副本出现登录界面，登录后等待即可。密钥获取完成后副本可能自动关闭，以应用显示的结果为准。飞书浏览器在登录后保持打开，下一步复用同一窗口。

### 在终端里

先找到本机微信账号并导出：

```sh
wechat-emoji accounts
wechat-emoji extract --out ./exported
```

默认全量导出。再次使用同一账号和同一目录时，完整结果直接复用，部分结果只补缺失或损坏的图片。有效密钥直接复用；需要重新获取时，按终端提示退出原微信。如果副本要求登录，登录后等待，无需手动打开表情面板。

然后先查看导入计划。例如飞书已有 **900 张**，本次选择排序后的前 **50 张**：

```sh
wechat-emoji feishu plan ./exported \
  --account my-feishu --existing-count 900 --limit 50
```

这一步不打开浏览器、不上传。`my-feishu` 是你给飞书账号取的本地名字，后续保持一致；`--existing-count` 需要手动核对。去掉 `--limit` 会检查整个目录，精确挑选可使用桌面应用或把目标图片复制到单独文件夹。

确认计划后，用相同参数开始导入：

```sh
wechat-emoji feishu import ./exported \
  --account my-feishu --existing-count 900 --limit 50
```

独立浏览器打开后，登录并核对实际飞书账号。本地名字不代表远端身份已核验。工具只添加个人自定义表情，不发送聊天消息。

需要提前登录或回看结果时：

```sh
wechat-emoji feishu login --account my-feishu
wechat-emoji tasks list
wechat-emoji tasks show 任务ID
```

## 交给 AI 助手

适用于在你 Mac 上执行命令的 **Codex、Claude Code（CC）和其他 harness**。把仓库链接连同下面一段话交给助手即可。

**安装并打开图形界面：**

```text
请帮我在这台 Mac 安装并启动这个项目的 Electron 桌面界面：
https://github.com/Jason12196/wechat-emoji-to-feishu

先阅读 README 和 INSTALL_FOR_AGENTS.md，检查本机架构和现有安装。
优先使用对应架构、包含 CLI 的源码包，准备 Node.js 22.12+ 和 pnpm 10，
在源码根目录用 pnpm dev 启动。若源码包不可用，再按文档下载源码和 CLI。
不要关闭 macOS 安全保护。把安装位置、启动命令和结果告诉我。
本次只安装和启动界面，微信退出、登录、导出和飞书上传由我随后操作。
```

**仅安装 CLI：**

```text
请按 README 和 INSTALL_FOR_AGENTS.md 安装这个项目的 CLI：
https://github.com/Jason12196/wechat-emoji-to-feishu

检测 Mac 架构，使用 README 下载表格中的对应链接，保留完整运行目录。
只检查版本和运行环境，告诉我可执行文件位置和使用命令。
本次不登录、不导出、不上传；等我明确要求迁移时再继续。
```

助手按上方下载链接安装，微信和飞书扫码登录由你操作。远程云端助手无法直接读取你 Mac 上的微信数据。

## 常见问题

### 下载与启动

<details>
<summary><strong>点击下载后需要登录，或者提示文件已过期？</strong></summary>

上方链接直接指向已构建的下载包。GitHub 可能要求登录普通账号，无需额外的仓库访问授权。当前测试包保留 7 天，过期时请通过 [Issues](https://github.com/Jason12196/wechat-emoji-to-feishu/issues) 告知维护者更新下载链接。

下载包外面有一层 ZIP，解开后再解压里面的源码 ZIP、应用 ZIP 或 CLI 的 `.tar.gz`。

</details>

<details>
<summary><strong>pnpm 找不到、Node 版本太旧，或 pnpm dev 运行失败？</strong></summary>

先运行 `node --version` 和 `pnpm --version`。需要 Node.js 22.12 或更新版本、pnpm 10；没有 pnpm 时可运行 `npm install -g pnpm@10`。在解压后含根 `package.json` 的 `wechat-emoji-to-feishu` 目录运行 `pnpm dev`，不要进入 `desktop` 子目录。

第一次启动需要下载依赖和 Electron，网络慢时请留意终端进度。若网络失败，修复网络后重试同一个 `pnpm dev`，保留完整错误。提示缺少 CLI 时，确认下载的是**含 CLI 的源码包**，或按安装章节设置 `WECHAT_EMOJI_CLI`。

</details>

<details>
<summary><strong>Mac 提示无法验证开发者、阻止启动或应用损坏？</strong></summary>

当前包没有 Apple 签名或公证。先确认文件来自本仓库成功构建、下载完整且架构正确；“无法验证”不一定意味着文件损坏。系统提供允许打开选项时，可以在核对来源后使用；否则下载源码包，用 `pnpm dev` 启动 Electron。

源码启动使用本机下载的 Electron，但内置 CLI 仍是下载的程序，也可能需要系统允许打开；它不是绕过所有系统检查的方式。可参考 [Apple 的安全打开说明](https://support.apple.com/en-us/102445)。仍有问题时，提供 macOS 版本、芯片及完整提示，不需要关闭系统整体保护。

</details>

<details>
<summary><strong>CLI 提示 command not found、Permission denied 或 Bad CPU type？</strong></summary>

- `command not found`：先进入 CLI 文件夹执行 `./wechat-emoji --version`。若能运行，重新设置 PATH，或用完整路径；路径含空格时加双引号。
- `Permission denied`：确认已完整解压，并尝试 `chmod +x ./wechat-emoji`。
- `Bad CPU type`：在“关于本机”核对芯片，重新下载 `arm64` 或 `x86_64` 对应包。
- 运行库缺失：重新完整解压，保留可执行文件旁的 `_internal` 等文件。

</details>

<details>
<summary><strong>浏览器下载很慢、失败，或者每次都重新下载？</strong></summary>

首次登录飞书需要下载 Chromium，之后使用本机缓存。失败后检查网络，可以用 `wechat-emoji browser install` 提前准备。默认缓存为 `~/Library/Caches/ms-playwright`；清理缓存或升级所需浏览器版本后会再次下载。

需要更换缓存位置时，在启动 CLI 或 Electron 的同一个终端设置：

```sh
export WECHAT_EMOJI_BROWSER_CACHE="/你选择的位置/wechat-emoji-browsers"
```

后续启动保持相同设置。下载完成仍不能启动时，保留系统版本、芯片和原始错误，重复下载不一定能解决兼容性问题。

</details>

### 微信导出

<details>
<summary><strong>没有找到微信账号，或识别的不是我要的账号？</strong></summary>

先确认这台 Mac 安装了微信，且目标账号至少登录过一次；多账号时核对实际选择，不要仅凭目录顺序判断。CLI 可运行 `wechat-emoji accounts`。使用迁移过的数据目录时，可显式指定：

```sh
wechat-emoji --wechat-root "/实际路径/xwechat_files" accounts
```

后续命令保持相同设置。系统阻止目录访问时，核对终端或助手的系统权限，不要随意修改微信数据文件。

</details>

<details>
<summary><strong>为什么需要退出微信？副本关闭了算失败吗？</strong></summary>

Mac 当前取密钥方案需要启动微信副本。已有密钥校验有效时直接复用，需要重新获取时才提示退出原微信。桌面应用会先征求确认，再正常退出；CLI 按终端提示操作。

如果副本出现登录界面，登录后等待结果，无需手动打开表情面板。**取到密钥后副本自动关闭是可能的正常行为，以任务结果为准。** 如果明确报错或超时，保留错误码、任务 ID 和微信版本，不要连续重复扫码。当前历史验证版本为微信 4.1.15 (270135)，其他版本可能需要适配。

</details>

<details>
<summary><strong>之前已经导出了一部分或全部，会重复导出吗？</strong></summary>

选择原导出位置。桌面应用识别账号对应的导出：完整时直接进入挑选，未完成时显示“继续导出”。有效密钥直接复用。

CLI 可以先离线检查目录，这些命令不启动微信、不下载图片：

```sh
wechat-emoji exports status ./exported --wxid wxid_你的账号
wechat-emoji exports discover ~/Downloads --wxid wxid_你的账号
```

继续执行 `wechat-emoji extract --out ./exported --wxid wxid_你的账号`，会复用已校验结果。不要混入其他账号的导出；旧目录如果没有账号关联记录，需要先确认归属，不能仅凭图片存在就认定导出完整。

</details>

<details>
<summary><strong>数量对不上、图片损坏，或者动图没有动？</strong></summary>

先核对微信账号，再查看导出目录中的 `export-report.json`。网络、资源失效或兼容问题可能导致部分恢复失败；不要用文件夹内所有文件的数量判断结果。

`originals` 保存下载源文件，`verified-originals` 保存有效原图，顶层是准备导入的图片，不应把这些副本重复计数。有些预览器只显示动图第一帧，可以换用支持 GIF 的查看器，或执行 `wechat-emoji images inspect ./exported`。

保留原图和报告再排查。图片校验通过也不代表飞书一定接受该文件。

</details>

### 飞书导入

<details>
<summary><strong>能导入企业表情吗？需要管理员吗？</strong></summary>

只支持当前登录账号的个人自定义表情，不需要企业管理员权限，不提供企业表情包导入。

</details>

<details>
<summary><strong>飞书已经登录，为什么仍在等待？窗口可以留着吗？</strong></summary>

可以保留窗口。Mac 上登录和导入复用同一独立浏览器，命令结束或报错后窗口也保持打开。

扫码成功和聊天界面加载完成是两件事。会话列表和表情面板分别最多等待 3 分钟，期间显示准备进度；还在等待时，不必反复重开任务。浏览器必须能显示可使用表情面板的会话。

如果出现 `MESSENGER_LOADING_TIMEOUT`、`NO_WRITABLE_CONVERSATION` 或 `STICKER_PANEL_UNAVAILABLE`，根据提示检查网络、打开可用会话或个人表情面板，再核对本次结果后继续。不要把“已登录”当成“已经上传成功”。

</details>

<details>
<summary><strong>不知道已有多少张，或提示容量不足？</strong></summary>

目前需要在飞书个人表情面板核对已有数量，再填写到应用或 `--existing-count`。工具按 **1000 张**上限预检查，不自动读取数量，也不会删除旧表情或擅自截断任务。

例如已有 980 张，本次最多选 20 张。若已经满了，由你决定是否整理旧表情。不要故意填小通过检查；最终以飞书实际接受结果为准。

</details>

<details>
<summary><strong>导入的图片和预期不同，或数量少了？</strong></summary>

桌面应用只导入勾选项。CLI 的 `--limit N` 则选文件排序后的前 N 张，不是最近使用顺序；精确选择请准备单独目录。

工具导出的目录通过 `export-report.json` 限定列表，防止重复导入原图副本。后来手动加进旧导出目录的图片不会自动进入报告，可以改放到新目录。无效、过大或状态待核对的图片会阻止相应计划，先查看结果再调整。

</details>

<details>
<summary><strong>登录错了飞书账号，或者换了本地账号名字？</strong></summary>

先停止任务并核对浏览器里的实际账号。`--account my-feishu` 只是本地配置名字，不会自动选中对应的远端账号；不同本地名字也可能登录同一飞书账号，不能因此重新全量上传。

需要独立登录配置时，可运行 `wechat-emoji feishu login --account another-account`。已有导入记录应继续与原账号标签配套使用。

</details>

<details>
<summary><strong>断网、关闭窗口或中断后，可以直接重新导入吗？</strong></summary>

先看任务结果。已确认成功的项目可跳过；`pending` / `unknown` 表示已经提交但结果未确认，需要先在飞书中核对，不能自动重传。

桌面应用保留任务记录。CLI 有原始导入记录时，可使用原账号标签和最新已有数量先做计划：

```sh
wechat-emoji feishu plan ./exported \
  --account my-feishu --existing-count 当前已有数量 --ledger "/原导入记录.json"
```

存在待核对或失败项时，保留记录并按诊断处理。不要删除记录、换账号标签或省略原记录，绕过检查重新全量上传。

</details>

<details>
<summary><strong>可以使用已有图片吗？图片格式或大小不合适怎么办？</strong></summary>

桌面应用选择“使用本地图片”，处理到独立目录；CLI 可运行：

```sh
wechat-emoji images prepare ./pictures --out ./prepared
wechat-emoji images inspect ./prepared
wechat-emoji feishu plan ./prepared --account my-feishu --existing-count 当前已有数量
```

保留源目录。无法解码或处理失败的文件需单独处理，不能保证任意图片都可以保持原样并符合飞书要求。

</details>

### 数据与反馈

<details>
<summary><strong>密钥、登录状态、表情会被打包或上传到别处吗？</strong></summary>

导出图片保存在你选的目录。任务与飞书登录状态默认位于 `~/Library/Application Support/wechat-emoji-to-feishu`；微信密钥由本机提取引擎缓存，浏览器另有下载缓存。卸载应用或删除源码文件夹不会自动删除这些本机记录。

发布包只包含程序、运行依赖与必要说明；源码包另外包含项目源码。**不包含维护者的密钥、Cookie、登录目录、表情图片、任务记录或诊断截图。** 打包使用明确文件范围，并检查私人文件和本机构建路径；检查失败会停止打包。

提取与处理在本机完成。导入时选中图片上传到你登录的飞书账号，工具不发送聊天消息。不要把私人导出目录或登录数据一起分享给他人。

</details>

<details>
<summary><strong>出了问题，反馈哪些信息最有用？</strong></summary>

提供版本、Mac 芯片、macOS 与微信版本、出错步骤、错误码和任务 ID。桌面应用中点击“查看诊断详情”，复制脱敏摘要；CLI 可用 `wechat-emoji --version`、`wechat-emoji doctor` 和 `wechat-emoji tasks show 任务ID` 查看信息，再通过 [Issues](https://github.com/Jason12196/wechat-emoji-to-feishu/issues) 反馈。

分享前再次检查账号、个人路径和截图内容。不要公开密钥、Cookie、登录目录、GitHub 令牌或原始诊断文件；无需上传全部表情或聊天内容。

</details>

<br>

---

<div align="center">

[开发与打包](docs/installation.md) · [助手执行指引](INSTALL_FOR_AGENTS.md) · [CLI 协议](docs/protocol.md) · [第三方声明](THIRD_PARTY.md) · [MIT 许可证](LICENSE)

<sub>README 编排参考开源项目 <a href="https://github.com/othneildrew/Best-README-Template">Best-README-Template</a>（Unlicense）。本项目非微信或飞书官方产品。</sub>

</div>
