<div align="center">

# 微信表情 → 飞书

把收藏的微信表情，带到飞书。

**Mac（目前） · Apple Silicon / Intel · 个人自定义表情**

[开始安装](#安装) · [交给 AI 助手](#让-ai-助手帮你安装) · [开始迁移](#开始迁移) · [遇到问题](#常见问题)

</div>

---

导出微信收藏表情，保留原图与动图，再按你的选择添加到飞书个人表情面板。只安装 CLI 就能完成，不需要 Electron，也不需要安装飞书客户端。

- **表情留在本机**：本地提取与处理，导入时上传到你登录的飞书账号。
- **保留动图**：处理图片时校验动画，下载源文件与有效原图另外保留。
- **自己决定导入多少**：先看计划，再导入；支持指定文件夹和限制数量。
- **中断有记录**：保存每次任务与逐项导入结果，不盲目重传状态不明的表情。

> 当前为测试版，尚未发布正式 Release，安装包未完成签名、公证与干净机器验收。两种 Mac 架构均已通过云端构建与启动检查；真实微信提取和飞书导入目前在 Apple Silicon 上验证，Intel 仍待实机验证。Electron 界面已接入本机 CLI，目前提供[源码启动方式](desktop/README.md)，尚无桌面安装包；真实登录与上传仍待本轮实机验收。

## 安装

准备好 **Mac、已安装的微信、接收表情的飞书账号和网络**。安装包自带运行依赖，不用配置 Python、Rust 或 Xcode。仓库目前为私有，下载前需要仓库访问权限。

### 1. 选择你的 Mac 版本

苹果菜单 → **关于本机**：显示“芯片 Apple M…”选 Apple Silicon；显示“处理器 Intel…”选 Intel。

| 你的 Mac | 下载产物 | 压缩包内文件 |
| --- | --- | --- |
| Apple Silicon | `macos-cli-arm64` | `wechat-emoji-macos-arm64.tar.gz` |
| Intel | `macos-cli-x86_64` | `wechat-emoji-macos-x86_64.tar.gz` |

打开 [下载页面（Actions）](https://github.com/Jason12196/wechat-emoji-to-feishu/actions/workflows/ci.yml)，选择最近一次**全部检查成功**的运行，在底部 **Artifacts** 下载对应产物。下载记录保留 7 天；没有可用产物时请联系仓库维护者重新构建。

### 2. 解压并运行

先解压下载的 ZIP，再解压里面的 `.tar.gz`。**保留整个 `wechat-emoji` 文件夹**，不要只拖走其中的可执行文件。

打开终端，进入解压后的文件夹：

```sh
cd /你的解压位置/wechat-emoji
./wechat-emoji --version
./wechat-emoji doctor
export PATH="$PWD:$PATH"
```

最后一行让当前终端可以直接使用后文的 `wechat-emoji` 命令。重新打开终端时，需要再次设置，或者直接用可执行文件的完整路径。

### 3. 准备浏览器

首次登录飞书时会自动下载 Chromium，并保存到本机，后续无需重复下载。也可以提前准备：

```sh
wechat-emoji browser install
```

看到成功结果后即可开始。这个命令只下载并测试浏览器启动，不登录飞书、不上传表情。首次下载前 `doctor` 显示浏览器未就绪是正常的。

## 让 AI 助手帮你安装

在这台 Mac 的 **Codex、Claude Code（CC）或其他能执行本地命令的助手**中，复制下面这段话即可。无需提前知道安装路径或自己配置开发环境。

```text
请安装并使用这个仓库的 CLI：
https://github.com/Jason12196/wechat-emoji-to-feishu

先阅读 README 和 INSTALL_FOR_AGENTS.md，检测我的 Mac 架构，
优先下载最近一次成功构建的对应 CLI 安装包，不安装 Electron。
安装完成后检查版本和运行环境，把可执行文件位置告诉我。
本次只安装检查，不登录微信或飞书、不导出、不上传；
后续我要求迁移时，再按文档引导我核对账号和导入范围。
```

也可以直接把仓库链接交给助手并说“按 README 安装 CLI”；详细的助手执行指引在 [INSTALL_FOR_AGENTS.md](INSTALL_FOR_AGENTS.md)。私有仓库需要你的 GitHub 登录已有访问权限；涉及 GitHub 授权时，由你在本机完成。不要把访问令牌发给助手或粘贴到聊天里。

助手负责执行命令，扫码登录仍由你完成。请使用本机运行的环境；远程云端助手不能直接读取这台 Mac 的微信数据。

## 开始迁移

### 1. 找到微信账号并导出

```sh
wechat-emoji accounts
wechat-emoji extract --out ./exported
```

微信默认全量导出到你指定的目录。再次使用同一账号、同一导出目录时，会校验已有图片；完整导出直接复用，中断的导出只补缺失或损坏的图片。已有密钥通过校验后直接复用，不会重复抓取；确实需要获取或刷新密钥时，按终端提示退出原微信。如果副本显示登录界面，登录后等待即可，无需手动打开表情面板。

需要单独获取密钥时：

```sh
wechat-emoji key
```

导出后保留 `exported` 文件夹，可直接作为下一步输入。不要把里面保留原图的子目录重复加入导入范围。

### 2. 先看导入计划

例如：飞书已有 **900 张**，本次选择前 **50 张**：

```sh
wechat-emoji feishu plan ./exported \
  --account my-feishu --existing-count 900 --limit 50
```

- `my-feishu` 是你为这个飞书账号取的本地名字，后续保持一致。
- `--existing-count` 填飞书目前已有的个人表情数量，当前需要手动确认。
- `--limit 50` 选择排序后的前 50 张；去掉该参数会检查整个目录。
- 想挑选特定图片？先把它们复制到单独文件夹，再将命令中的 `./exported` 换成该文件夹。

这一步不打开浏览器、不上传。CLI 按 **1000 张**的个人表情上限检查剩余容量，超出时会停止，不会擅自截断任务或删除旧表情。

### 3. 登录飞书，开始导入

确认计划后，使用相同参数执行：

```sh
wechat-emoji feishu import ./exported \
  --account my-feishu --existing-count 900 --limit 50
```

独立浏览器窗口打开后，登录你要接收表情的账号。**核对窗口中的实际账号**，本地账号名字并不代表远端身份已核验。工具只添加个人自定义表情，不发送聊天消息。

登录状态会保存在本机，失效后需要重新登录。也可以提前登录：

```sh
wechat-emoji feishu login --account my-feishu
```

### 4. 查看结果

终端会显示进度和结果。需要回看历史任务时：

```sh
wechat-emoji tasks list
wechat-emoji tasks show 任务ID
```

保留原导出目录、任务记录和导入记录，以便核对失败或中断的项目。恢复前请先阅读下面的中断说明。

## 常见问题

### 安装与启动

<details>
<summary><strong>链接打不开、显示 404，或者没有下载按钮？</strong></summary>

仓库目前为私有。先在 GitHub 登录拥有仓库访问权限的账号，再打开链接；404 也可能表示当前账号没有权限。下载文件在一次成功运行详情页底部的 Artifacts，并不在源码文件列表里。产物保留 7 天，过期后需要维护者重新运行构建。AI 助手使用的 GitHub 登录也需要有访问权限。

</details>

<details>
<summary><strong>提示 command not found、Permission denied 或 Bad CPU type？</strong></summary>

- `command not found`：先进入解压目录，执行 `./wechat-emoji --version`。若这样能运行，说明只需重新设置 PATH，或使用完整路径。路径包含空格时用双引号包住。
- `Permission denied`：确认已完整解压压缩包，并尝试 `chmod +x ./wechat-emoji`。
- `Bad CPU type` / 架构不匹配：重新检查“关于本机”，下载 arm64 或 x86_64 对应包。
- 提示运行库或内置文件缺失：重新完整解压，不要只复制可执行文件。

</details>

<details>
<summary><strong>Mac 提示无法验证开发者、阻止启动或应用损坏？</strong></summary>

当前是未公证测试包，这类下载启动提示仍需发布验收。先确认文件来自本仓库成功构建、下载完整且架构正确。不要按不明来源指令关闭系统整体保护；若无法正常启动，联系维护者提供 macOS 版本、芯片及原始提示，也可由开发者按源码方式安装。不要把这类提示一概当成下载损坏。

</details>

<details>
<summary><strong>浏览器下载很慢、失败，或每次启动都要下载？</strong></summary>

首次需要下载浏览器，耗时取决于网络。失败会重试一次，仍失败时检查网络后运行 `wechat-emoji browser install`。缓存默认位于 `~/Library/Caches/ms-playwright`；清理缓存或升级到需要新浏览器版本的 CLI 后，会再次下载。

如需换到有空间、可写的位置，先设置：

```sh
export WECHAT_EMOJI_BROWSER_CACHE="/你选择的位置/wechat-emoji-browsers"
wechat-emoji browser install
```

后续命令也要使用相同设置。缓存成功后仍无法启动，请保留终端错误，向维护者说明系统版本和芯片；重复下载不能保证解决系统兼容问题。

</details>

### 微信导出

<details>
<summary><strong>没有找到微信账号，或找到的不是我要的账号？</strong></summary>

先确认这台 Mac 已安装微信，并至少登录过一次目标账号，再运行 `wechat-emoji accounts`。自定义或迁移过数据目录时，可显式指定：

```sh
wechat-emoji --wechat-root "/实际路径/xwechat_files" accounts
```

后续导出也要带相同参数。多账号可先用 `wechat-emoji extract --help` 查看账号选择参数；不要仅凭目录顺序认定账号身份。若系统阻止访问目录，核对终端或助手的系统访问权限，不要随意更改微信数据文件。

</details>

<details>
<summary><strong>为什么要退出微信，还要在另一个微信窗口登录？</strong></summary>

Mac 当前取密钥方案需要启动微信副本。已有密钥校验有效时会直接复用；需要重新获取时才按提示退出原微信。如果副本出现登录界面，登录后等待结果即可，无需手动打开表情面板。不要在操作过程中反复启动多个微信实例。

若副本闪退、等待超时或始终没有成功，不要连续重复扫码；保留错误和微信版本，联系维护者核对兼容性。当前历史验证版本为微信 4.1.15 (270135)，不保证所有版本表现相同。

</details>

<details>
<summary><strong>之前已经导出了一部分或全部，会重复导出吗？</strong></summary>

保留并选择原导出位置。Electron 会识别当前微信账号对应的导出：完整时直接进入图片挑选，未完成时显示“继续导出”；已有有效密钥直接复用。

CLI 可先离线检查指定目录，或在下载目录中查找该账号已有的导出；这两条命令不启动微信、不下载图片：

```sh
wechat-emoji exports status ./exported --wxid wxid_你的账号
wechat-emoji exports discover ~/Downloads --wxid wxid_你的账号
```

继续执行同一目录的 `extract --out ./exported --wxid wxid_你的账号`，会复用已校验的结果，只处理未完成项。不要把另一个账号的导出合并到这个目录。旧版导出如果没有账号关联记录，不能自动判断是否完整，可以通过“使用本地图片”打开已有图片。

</details>

<details>
<summary><strong>导出的数量不对、图片损坏，或者动图没有动？</strong></summary>

先确认导出的微信账号正确，并查看导出目录中的 `export-report.json`，核对成功与失败项。部分图片可能因网络、资源失效或当前版本兼容问题无法恢复，不能只看目录文件总数判断是否完整。

`originals` 保留下载源文件，`verified-originals` 保留有效原图，顶层是处理后的导入文件；这些副本不应重复计数。有些图片预览器只显示第一帧，可以运行以下命令检查图片，或换用支持 GIF 的查看器：

```sh
wechat-emoji images inspect ./exported
```

不要删除原图后再排查；图片校验成功也不代表飞书一定接受该文件。

</details>

### 飞书导入

<details>
<summary><strong>能导入企业表情吗？需要飞书管理员吗？</strong></summary>

目前只支持你登录账号的个人自定义表情，不需要企业管理员权限，不提供企业表情包导入。

</details>

<details>
<summary><strong>不知道已有多少张，或者提示容量不足？</strong></summary>

当前工具不会自动读取飞书已有数量，需要你先在个人表情面板核对，再填写 `--existing-count`。不要为了通过检查故意填小；预检查通过后飞书仍可能拒绝超额添加。

例如已有 980 张，按 1000 张上限只能再添加 20 张。用 `--limit 20` 缩小范围，或准备只含目标图片的文件夹。如果已经满了，需要你自行决定是否整理旧表情；工具不会替你删除。少于 1000 张仍被拒绝时，以飞书实际提示为准。

</details>

<details>
<summary><strong>为什么导入的不是我选的图片，或者数量少了？</strong></summary>

`--limit N` 选择文件排序后的前 N 张，不是按最近使用或微信收藏顺序选择。要精确挑选，请把图片复制到单独目录再做计划。

使用工具导出的目录时，`export-report.json` 会限定导入列表，避免把原图副本一起导入。自行增添的图片不会自动加入旧报告；请改用单独文件夹。无效、过大或状态待核对的文件也会使计划不能继续，先看计划结果再调整。

</details>

<details>
<summary><strong>登录错飞书账号、扫码后还是等待，怎么办？</strong></summary>

先停止当前任务并核对浏览器中的实际账号。`--account my-feishu` 只是本地配置名字，不会自动选中对应的飞书账号。可以用另一个名字建立独立登录目录：

```sh
wechat-emoji feishu login --account another-account
```

扫码后等待网页完成加载，确认网络可访问飞书。如果页面验证、登录超时或网页结构变化导致工具无法继续，请保留错误，避免反复执行导入。不同本地名字也可能登录同一远端账号，不应因此当作新账号重复上传。

</details>

<details>
<summary><strong>关掉窗口、断网、按 Ctrl+C 后，能直接再运行导入吗？</strong></summary>

先看任务结果，再决定恢复，避免重复添加。每次导入都有逐项记录：已确认成功的项目可跳过，`pending` / `unknown` 表示已经提交但结果尚未确认，需先在飞书里核对，不能直接自动重传。

有原始导入记录路径时，可使用同一本地账号标签恢复，并填写恢复时最新的已有数量：

```sh
wechat-emoji feishu plan ./exported \
  --account my-feishu --existing-count 当前已有数量 --ledger "/原导入记录.json"
```

先看计划；存在待核对或失败记录时工具可能拒绝继续，这时应保留记录并联系维护者。不要删除记录、换个账号标签或不带原记录重新全量提交来绕过检查。

</details>

<details>
<summary><strong>图片格式或大小不符合要求，能处理我已有的图片吗？</strong></summary>

可以，先处理到新目录，再检查和导入：

```sh
wechat-emoji images prepare ./pictures --out ./prepared
wechat-emoji images inspect ./prepared
wechat-emoji feishu plan ./prepared --account my-feishu --existing-count 当前已有数量
```

保留源目录。不能解码、处理失败或超出当前大小限制的文件需要单独处理；工具不会保证任何图片都能在保持原样的同时符合飞书要求。

</details>

### 数据与反馈

<details>
<summary><strong>密钥、登录状态和导出图片放在哪里？会发聊天消息吗？</strong></summary>

导出图片放在你通过 `--out` 指定的目录。任务与飞书登录目录默认位于 `~/Library/Application Support/wechat-emoji-to-feishu`，微信密钥由本机提取引擎缓存，浏览器另有下载缓存。

发布包只包含程序、运行依赖和说明文件，不包含微信密钥、飞书登录目录、导出图片、任务记录或诊断截图。打包流程会检查这些私人文件及本机构建路径，并清除压缩包中的本机用户名等所有者信息；检查不通过时停止打包。

导入时图片会上传到你登录的飞书账号，工具不发送聊天消息。备份或分享时不要把密钥、登录目录或整份私人导出目录一起上传到公开仓库。

</details>

<details>
<summary><strong>出了问题，反馈什么信息最有用？</strong></summary>

请提供 CLI 版本（`wechat-emoji --version`）、Mac 芯片和 macOS 版本、微信版本、执行到哪一步、原始错误及任务 ID。可以先运行 `wechat-emoji doctor` 查看环境，再通过 [Issues](https://github.com/Jason12196/wechat-emoji-to-feishu/issues) 反馈。

分享日志前遮盖账号、个人路径、资源链接等私人信息；不要上传密钥、Cookie、登录目录或 GitHub 令牌。不要只发送“失败了”，也不需要公开全部聊天或表情数据。

</details>

---

[开发与打包](docs/installation.md) · [CLI 协议](docs/protocol.md) · [第三方声明](THIRD_PARTY.md) · [许可证](LICENSE)
