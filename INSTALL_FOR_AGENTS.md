# Local assistant installation guide

For Codex, Claude Code and other assistants that can execute commands on the user's Mac. Read [README.md](README.md) first and follow the user's requested interface. A repository link plus “install” authorizes setup; it does not authorize WeChat shutdown, key capture, login, export or Feishu upload.

## Choose the right route

| User request | Preferred installation |
| --- | --- |
| Desktop app, Electron, graphical UI | Matching **source kit with bundled CLI**, then root `pnpm dev` |
| CLI, command-line, scripting | Matching prebuilt CLI archive |
| Explicitly asks for the application bundle | Matching unsigned Electron app ZIP; explain macOS may block it |
| Development or clone the repository | Repository source plus matching CLI, then root `pnpm dev` |

The source kit starts the Electron dependency installed on the user's machine instead of our redistributed unsigned `.app` bundle. Its bundled CLI is still a downloaded executable and may need macOS approval; this route does not bypass every system security check. It still needs Node.js 22.12+ and pnpm 10, and downloads dependencies on first launch. It does not require Python, Rust or Xcode. Do not silently install a full compiler toolchain as a fallback.

## Inspect first

1. Check `uname -s` and `uname -m`. Current deliverables support Darwin `arm64` and `x86_64`. Windows/Linux interfaces are reserved but not ready for installation.
2. Check for an existing install, its version and the user's desired directory. Reuse the existing installation when appropriate. Preserve older versions and unrelated files.
3. The repository is currently private: `Jason12196/wechat-emoji-to-feishu`. Prefer authenticated GitHub CLI. `gh auth status` checks access; authorization, if needed, is completed by the user locally. Never request or print a token, and do not request workflow permissions merely to download.
4. Use a task-specific staging directory and an agreed install location. Do not use `sudo` or silently modify shell startup files. The source kit needs its whole extracted directory to remain present.

## Find downloadable artifacts

```sh
gh run list --repo Jason12196/wechat-emoji-to-feishu \
  --workflow ci.yml --branch main --status success --limit 10 \
  --json databaseId,headSha,conclusion
```

Choose the newest successful run containing the required, unexpired artifact. Match the actual host architecture:

| Kind | Actions artifact | File inside |
| --- | --- | --- |
| Source kit | `macos-source-ARCH` | `wechat-emoji-source-macos-ARCH.zip` |
| Electron | `macos-desktop-ARCH` | `wechat-emoji-desktop-macos-ARCH.zip` |
| CLI | `macos-cli-ARCH` | `wechat-emoji-macos-ARCH.tar.gz` |

Replace `ARCH` with `arm64` or `x86_64`, and replace the other placeholders:

```sh
gh run download RUN_ID --repo Jason12196/wechat-emoji-to-feishu \
  --name macos-source-ARCH --dir /ABSOLUTE/STAGING/DIRECTORY
```

Artifacts expire after 7 days. Inspect the archive member list before extraction; reject absolute paths and traversal. Do not overwrite an existing installation. A checksum calculated locally is not proof of cryptographic authenticity; these packages are not Apple-signed or notarized releases.

If a suitable artifact is missing, check other successful runs. If all have expired, report the need for a maintainer rebuild or offer an explicitly scoped development build. Do not publish releases, change CI permissions or download the wrong architecture as a workaround.

## Desktop source kit

1. Extract the source kit. Its root is `wechat-emoji-to-feishu/`; the complete prebuilt CLI is at `dist/wechat-emoji/`.
2. Check `node --version` and `pnpm --version`. Required: Node.js 22.12+ and pnpm 10. Install missing prerequisites within the user's requested setup scope; avoid replacing unrelated Node installations. When Node is already available, pnpm can be installed with `npm install -g pnpm@10` or through the user's existing version manager.
3. Run **from the source root**:

```sh
pnpm dev
```

The script installs dependencies from the lockfile when needed, builds the UI and opens the actual Electron app. It can take time on first launch because npm packages and Electron are downloaded. Keep its terminal process available; do not kill it immediately after the window appears. This is not the Vite browser demonstration.

The bundled CLI is used automatically. A plain GitHub source ZIP or clone does not contain it: the startup script can use authenticated `gh` to fetch the matching CLI from the latest successful `main` build, or accept an existing full CLI installation:

```sh
WECHAT_EMOJI_CLI="/ABSOLUTE/CLI/DIRECTORY/wechat-emoji" pnpm dev
```

The override must point to this project's CLI, not an upstream extractor binary. It does not authorize copying browser profiles or private user state into the source folder.

4. Report install location, host architecture, artifact run/commit, command to launch next time, and whether the window was opened. Starting the app performs local environment/account detection; leave actual export/login/upload to the user unless separately requested.

## Prebuilt CLI only

1. Download `macos-cli-ARCH` and extract the full `wechat-emoji/` directory. Keep `_internal` and all companion files; never install only the executable.
2. Run the installed binary with its absolute path:

```sh
/ABSOLUTE/PATH/wechat-emoji --version
/ABSOLUTE/PATH/wechat-emoji --json doctor
```

Global flags precede subcommands. `doctor` is read-only with respect to WeChat/Feishu and does not install Chromium. A browser-not-ready result before first use is expected. `browser install` is optional preparation: it downloads the matching runtime and checks a local headless launch, without visiting Feishu. First login can also install it automatically.

3. Report the executable path, architecture, source run/commit, version, diagnostic result and any remaining setup. Provide a copyable command. Do not silently change global PATH or install Electron when the user only requested CLI.

## Unsigned Electron app

Extract `wechat-emoji-desktop-macos-ARCH.zip` to get `表情迁移.app`. The app includes the CLI. Install it where the user requested, preserving existing apps. If macOS blocks it, explain its unsigned/notarized status and offer the source-kit route; do not turn off system-wide security or automatically clear quarantine.

## Later migration requests

Read the installed command's `--help`, and use `--json` for structured CLI progress. Verify the WeChat account, export location, selected image range and the actual Feishu account visible in the browser. Inspect an offline import plan before uploading; `--existing-count` is user-provided, and `--limit` selects sorted files.

Login happens in local windows and requires user participation. The Mac Feishu window stays open and is reused across login/import. Never send chat messages, delete existing stickers, bypass capacity checks or automatically resubmit `pending` / `unknown` entries. Keep the original ledger and local account label; that label alone is not proof of remote identity.

## Data and diagnostics

Runtime state stays under `~/Library/Application Support/wechat-emoji-to-feishu`, separately from the source or application. User exports stay at the chosen destination. Preserve both when updating or replacing program files.

Share only the necessary redacted error summary: version, platform, stage, code and task ID. Do not attach keys, cookies, browser profiles, screenshots containing private conversations, complete exports or raw diagnostic files. Installation alone does not authorize clearing those files.
