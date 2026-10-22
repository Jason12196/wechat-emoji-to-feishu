# Local harness installation guide

For Codex, Claude Code and other local command-executing assistants. Follow the user's scope. A request to install authorizes installation and diagnostics, not WeChat login, key capture, export or Feishu upload.

## Preconditions

- Work on the user's Mac. Detect `uname -s` and `uname -m`; supported artifacts are Darwin arm64 and Darwin x86_64. Do not install Electron or attempt Windows/Linux setup.
- Read README. Check for an existing installation and its version before downloading another copy.
- Private repository: Jason12196/wechat-emoji-to-feishu. Prefer authenticated GitHub CLI if available. Check `gh auth status`; if access is missing, ask the user to complete GitHub authorization locally. Never request a token in chat, print tokens, or request workflow scope just to download.
- Install within a user-approved workspace, e.g. its `.tools/wechat-emoji` directory. Preserve existing versions and never overwrite unrelated files. Do not use sudo or silently edit shell startup files.

## Preferred route: prebuilt CLI

1. Inspect successful runs:

```sh
gh run list --repo Jason12196/wechat-emoji-to-feishu --workflow ci.yml --status success --limit 5 --json databaseId,headSha,conclusion
```

2. Pick the newest fully successful run that actually contains the required, unexpired artifact. Map arm64 to macos-cli-arm64, x86_64 to macos-cli-x86_64. Download to a fresh task-specific staging directory, replacing placeholders:

```sh
gh run download RUN_ID --repo Jason12196/wechat-emoji-to-feishu --name macos-cli-ARCH --dir /ABSOLUTE/STAGING/DIRECTORY
```

3. Verify the archive filename matches the architecture. Inspect the tar member list before extracting; reject absolute paths or traversal. Extract the entire archive, preserving executable permissions and companion `_internal` resources. Never install only the executable. Packages are test builds, not notarized releases; do not disable macOS security controls to make them run.
4. Move the extracted directory into the agreed installation location without clobbering an existing install. Record the absolute executable path. Do not claim cryptographic authenticity based only on a locally computed checksum; this project does not yet provide signed release verification.
5. Execute the installed binary using its absolute path:

```sh
/ABSOLUTE/PATH/wechat-emoji --version
/ABSOLUTE/PATH/wechat-emoji --json doctor
```

Global flags precede subcommands. doctor is read-only with respect to WeChat/Feishu and does not install Chromium. A false browser-ready field on first install is expected; report it clearly. If the user wants browser setup, run `browser install`; this downloads the matching runtime and tests a local headless launch, without visiting Feishu. Browser setup can also wait until first login/import.
6. Report architecture, source run ID/commit, installed path, version, diagnostic results and any remaining setup. Provide a ready-to-copy command using the absolute path. Do not silently change global PATH.

## When artifacts are missing

Inspect older successful runs for the same architecture. If all suitable artifacts expired, explain that a maintainer must rebuild, or offer source installation. Do not unexpectedly install Rust/Xcode or a whole developer toolchain. Source build instructions are in docs/installation.md; obtain the user's agreement if new prerequisites are needed. Do not create a CI workflow, expand OAuth permissions, publish a release or use mismatched architecture binaries as an installation workaround.

## Later migration requests

Read the installed command's --help. Use --json for structured progress. Verify the target local WeChat account, export location, Feishu account and user-selected range. Inspect an offline import plan before upload; --existing-count is user-provided, --limit is sorted-file selection. Login happens in local windows and needs user participation. Never delete existing stickers, bypass capacity checks, or automatically resubmit pending/unknown ledger entries. A local --account label is not remote identity proof. A request to install alone does not authorize any of these operations.
