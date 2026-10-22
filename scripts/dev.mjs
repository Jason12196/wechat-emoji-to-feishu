/** Start the real Electron app from a clean source checkout or source kit. */
import fs from "node:fs/promises";
import { constants as fsConstants, createReadStream } from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repo = "Jason12196/wechat-emoji-to-feishu";
const arch = { arm64: "arm64", x64: "x86_64" }[process.arch];
const pnpmPath = process.env.npm_execpath;
let activeChild;
let stopping = false;

function continueStarting() {
  if (stopping) throw new Error("启动已取消。");
}

function log(message) {
  console.log(`[启动] ${message}`);
}

function run(
  command,
  args,
  { capture = false, env = process.env, cwd = root } = {},
) {
  return new Promise((resolve, reject) => {
    if (stopping) {
      reject(new Error("启动已取消。"));
      return;
    }
    const child = spawn(command, args, {
      cwd,
      env,
      shell: false,
      stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    });
    activeChild = child;
    let stdout = "";
    let stderr = "";
    if (capture) {
      child.stdout.on("data", (chunk) => {
        stdout = (stdout + chunk).slice(-1024 * 1024);
      });
      child.stderr.on("data", (chunk) => {
        stderr = (stderr + chunk).slice(-8192);
      });
    }
    child.once("error", (error) => {
      if (activeChild === child) activeChild = undefined;
      reject(error);
    });
    child.once("close", (code, signal) => {
      if (activeChild === child) activeChild = undefined;
      if (stopping) reject(new Error("启动已取消。"));
      else if (code === 0) resolve(stdout);
      else
        reject(
          new Error(
            `${path.basename(command)} 退出：${signal || code}${capture && stderr ? `\n${stderr.trim()}` : ""}`,
          ),
        );
    });
  });
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    stopping = true;
    activeChild?.kill(signal);
    process.exitCode = signal === "SIGINT" ? 130 : 143;
  });
}

async function exists(file) {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

async function ensureDependencies() {
  if (!pnpmPath || !path.isAbsolute(pnpmPath)) {
    throw new Error("请在源码根目录运行 pnpm dev（需要 pnpm 10）。");
  }
  const inputs = [
    "package.json",
    "desktop/package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
  ];
  const hash = createHash("sha256");
  for (const name of inputs)
    hash.update(await fs.readFile(path.join(root, name)));
  hash.update(
    `${process.platform}/${process.arch}/${process.versions.node.split(".")[0]}`,
  );
  const digest = hash.digest("hex");
  const stamp = path.join(root, "node_modules/.wechat-emoji-dev-dependencies");
  let previous;
  try {
    previous = await fs.readFile(stamp, "utf8");
  } catch {
    /* First start. */
  }
  let runtimeReady = false;
  try {
    await electronRuntime();
    runtimeReady = true;
  } catch {
    /* Electron needs its explicit installer after a fresh dependency install. */
  }
  const ready =
    previous === digest &&
    (await exists(path.join(root, "node_modules/tar/package.json"))) &&
    runtimeReady &&
    (await exists(path.join(root, "desktop/node_modules/.bin/vite")));
  if (ready) return;
  log("首次启动或依赖已更新，正在安装固定版本依赖和 Electron…");
  await run(process.execPath, [pnpmPath, "install", "--frozen-lockfile"]);
  try {
    await electronRuntime();
  } catch {
    log("正在下载 Electron 运行环境…");
    await run(process.execPath, [
      pnpmPath,
      "--dir",
      "desktop",
      "exec",
      "install-electron",
    ]);
    try {
      await electronRuntime();
    } catch {
      throw new Error(
        "Electron 尚未下载完成。请检查网络，然后重新运行 pnpm dev。",
      );
    }
  }
  await fs.writeFile(stamp, digest);
}

async function executable(file) {
  if (!(await fs.stat(file)).isFile()) throw new Error("CLI 路径不是文件。");
  await fs.access(file, fsConstants.X_OK);
  return file;
}

async function electronRuntime() {
  const installation = path.join(root, "desktop/node_modules/electron");
  const distribution = await fs.realpath(path.join(installation, "dist"));
  const relative = (
    await fs.readFile(path.join(installation, "path.txt"), "utf8")
  ).trim();
  if (!relative || path.isAbsolute(relative))
    throw new Error("Electron 运行环境路径无效。");
  const candidate = await fs.realpath(path.resolve(distribution, relative));
  const inside = path.relative(distribution, candidate);
  if (
    !inside ||
    inside.split(path.sep).includes("..") ||
    path.isAbsolute(inside)
  ) {
    throw new Error("Electron 可执行文件不在安装目录内。");
  }
  return executable(candidate);
}

async function packagedCli(file) {
  await executable(file);
  if (
    !(await fs.stat(path.join(path.dirname(file), "_internal"))).isDirectory()
  ) {
    throw new Error("CLI 缺少 _internal 运行库。请保留完整解压目录。");
  }
  const handle = await fs.open(file, "r");
  try {
    const header = Buffer.alloc(4096);
    const { bytesRead } = await handle.read(header, 0, header.length, 0);
    const cpu = process.arch === "arm64" ? 0x0100000c : 0x01000007;
    let compatible =
      bytesRead >= 8 &&
      header.readUInt32LE(0) === 0xfeedfacf &&
      header.readUInt32LE(4) === cpu;
    if (
      bytesRead >= 8 &&
      [0xcafebabe, 0xcafebabf].includes(header.readUInt32BE(0))
    ) {
      const count = header.readUInt32BE(4);
      const stride = header.readUInt32BE(0) === 0xcafebabe ? 20 : 32;
      for (
        let index = 0;
        index < count && 8 + index * stride + 4 <= bytesRead;
        index++
      ) {
        compatible ||= header.readUInt32BE(8 + index * stride) === cpu;
      }
    }
    if (!compatible)
      throw new Error(
        `CLI 与当前 Node.js 架构不匹配，请下载 ${arch} 源码包（Apple Silicon 推荐原生 arm64 Node.js）。`,
      );
  } finally {
    await handle.close();
  }
  return file;
}

function safeMember(name) {
  if (
    typeof name !== "string" ||
    name.includes("\\") ||
    /[\x00-\x1f\x7f]/.test(name) ||
    path.posix.isAbsolute(name) ||
    path.posix.normalize(name) !== name
  )
    return false;
  const parts = name.split("/").filter(Boolean);
  return (
    parts.length > 0 &&
    parts[0] === "wechat-emoji" &&
    !parts.includes("..") &&
    !parts.includes(".")
  );
}

async function extractCli(archive, destination) {
  const { t, x } = await import("tar");
  const metadata = new Map();
  let expandedBytes = 0;
  let issue;
  const rejectEntry = (message) => {
    issue ||= message;
  };
  if ((await fs.stat(archive)).size > 1024 * 1024 * 1024)
    throw new Error("CLI 下载包大小异常，已停止解压。");
  await t({
    file: archive,
    strict: true,
    onReadEntry(entry) {
      const name = entry.path.replace(/\/$/, "");
      if (!safeMember(name)) {
        rejectEntry("归档包含不安全路径");
        return;
      }
      if (!["File", "Directory", "SymbolicLink", "Link"].includes(entry.type))
        rejectEntry("归档包含不支持的文件类型");
      if (metadata.has(name)) rejectEntry("归档包含重复路径");
      metadata.set(name, entry.type);
      expandedBytes += entry.size || 0;
      if (expandedBytes > 4 * 1024 ** 3 || metadata.size > 50000)
        rejectEntry("归档大小异常");
      if (entry.type === "SymbolicLink" || entry.type === "Link") {
        if (
          path.posix.isAbsolute(entry.linkpath) ||
          entry.linkpath.includes("\\") ||
          /[\x00-\x1f\x7f]/.test(entry.linkpath)
        )
          rejectEntry("归档包含不安全链接");
        const target =
          entry.type === "SymbolicLink"
            ? path.posix.normalize(
                path.posix.join(path.posix.dirname(name), entry.linkpath),
              )
            : entry.linkpath;
        if (!safeMember(target)) rejectEntry("归档链接超出 CLI 目录");
      }
    },
  });
  for (const name of metadata.keys()) {
    let parent = path.posix.dirname(name);
    while (parent !== ".") {
      if (metadata.has(parent) && metadata.get(parent) !== "Directory")
        rejectEntry("归档路径穿过非目录条目");
      parent = path.posix.dirname(parent);
    }
  }
  if (
    metadata.get("wechat-emoji/wechat-emoji") !== "File" ||
    metadata.get("wechat-emoji/_internal") !== "Directory"
  )
    rejectEntry("下载包缺少完整 CLI");
  if (issue) throw new Error(`${issue}，已停止解压。`);
  await fs.mkdir(destination, { mode: 0o700 });
  await x({
    file: archive,
    cwd: destination,
    strict: true,
    preservePaths: false,
    noChmod: false,
    noMtime: true,
  });
  return packagedCli(path.join(destination, "wechat-emoji/wechat-emoji"));
}

async function hashFile(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function downloadCli() {
  continueStarting();
  const cache = path.join(
    os.homedir(),
    "Library/Caches/wechat-emoji-to-feishu/cli",
  );
  await fs.mkdir(cache, { recursive: true, mode: 0o700 });
  const pointer = path.join(cache, `current-${arch}.json`);
  try {
    const saved = JSON.parse(await fs.readFile(pointer, "utf8"));
    if (
      /^run-[0-9]+-(arm64|x86_64)$/.test(saved.directory) &&
      saved.directory.endsWith(`-${arch}`)
    ) {
      const cli = await packagedCli(
        path.join(cache, saved.directory, "wechat-emoji/wechat-emoji"),
      );
      log("复用已下载的 CLI。");
      return cli;
    }
  } catch {
    /* A missing/incomplete cache is safe to replace with a new download. */
  }
  try {
    await run("gh", ["auth", "status", "--hostname", "github.com"], {
      capture: true,
    });
  } catch {
    throw new Error(
      "源码中没有编译好的 CLI。请下载 README 中对应芯片的完整源码包；或安装 GitHub CLI 并运行 gh auth login 后重试。已有 CLI 可通过 WECHAT_EMOJI_CLI=/绝对路径/wechat-emoji pnpm dev 指定。",
    );
  }
  log("正在获取本仓库 main 分支最近成功构建的 CLI…");
  const runs = JSON.parse(
    await run(
      "gh",
      [
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        "ci.yml",
        "--branch",
        "main",
        "--status",
        "success",
        "--limit",
        "10",
        "--json",
        "databaseId,headSha,event",
      ],
      { capture: true },
    ),
  );
  let selected;
  if (Array.isArray(runs)) {
    for (const runInfo of runs) {
      if (
        !["push", "workflow_dispatch"].includes(runInfo.event) ||
        !Number.isSafeInteger(runInfo.databaseId) ||
        !/^[a-f0-9]{40}$/.test(runInfo.headSha || "")
      )
        continue;
      const result = JSON.parse(
        await run(
          "gh",
          ["api", `repos/${repo}/actions/runs/${runInfo.databaseId}/artifacts`],
          { capture: true },
        ),
      );
      if (
        result.artifacts?.some(
          (artifact) =>
            artifact.name === `macos-cli-${arch}` && artifact.expired === false,
        )
      ) {
        selected = runInfo;
        break;
      }
    }
  }
  if (!selected) {
    throw new Error(
      "最近成功构建中没有仍在保留期内的 CLI 产物。请等待新构建、手动运行 Actions，或下载完整源码包。",
    );
  }
  const { databaseId, headSha } = selected;
  const temp = await fs.mkdtemp(path.join(cache, ".download-"));
  try {
    log(`下载 ${arch} CLI（构建 ${databaseId}）…`);
    await run("gh", [
      "run",
      "download",
      String(databaseId),
      "--repo",
      repo,
      "--name",
      `macos-cli-${arch}`,
      "--dir",
      temp,
    ]);
    const archive = path.join(temp, `wechat-emoji-macos-${arch}.tar.gz`);
    if (!(await exists(archive)))
      throw new Error("构建产物中缺少对应架构的 CLI 压缩包。");
    const stage = path.join(temp, "unpacked");
    await extractCli(archive, stage);
    continueStarting();
    const directory = `run-${databaseId}-${arch}`;
    const target = path.join(cache, directory);
    if (await exists(target)) {
      // Never replace a previously downloaded directory or a user-supplied path.
      await packagedCli(path.join(target, "wechat-emoji/wechat-emoji"));
    } else {
      await fs.rename(stage, target);
    }
    await fs.writeFile(
      pointer,
      JSON.stringify(
        { directory, headSha, sha256: await hashFile(archive) },
        null,
        2,
      ),
      { mode: 0o600 },
    );
    return packagedCli(path.join(target, "wechat-emoji/wechat-emoji"));
  } finally {
    await fs.rm(temp, { recursive: true, force: true });
  }
}

async function resolveCli() {
  if (process.env.WECHAT_EMOJI_CLI) {
    const cli = process.env.WECHAT_EMOJI_CLI;
    if (!path.isAbsolute(cli))
      throw new Error("WECHAT_EMOJI_CLI 必须是可执行文件的绝对路径。");
    try {
      return await executable(cli);
    } catch {
      throw new Error(
        "WECHAT_EMOJI_CLI 指向的文件不存在或不可执行，请检查完整路径和权限。",
      );
    }
  }
  const bundled = path.join(root, "dist/wechat-emoji/wechat-emoji");
  if (await exists(bundled)) {
    try {
      return await packagedCli(bundled);
    } catch (error) {
      throw new Error(
        `源码包中的 CLI 不完整、架构不匹配或不可执行。${error.message}`,
      );
    }
  }
  return downloadCli();
}

async function main() {
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major < 22 || (major === 22 && minor < 12))
    throw new Error("请安装 Node.js 22.12 或更新版本。");
  if (process.platform !== "darwin" || !arch)
    throw new Error("目前支持 macOS（Apple Silicon 和 Intel）。");
  await ensureDependencies();
  continueStarting();
  const cli = await resolveCli();
  continueStarting();
  log("正在构建界面…");
  await run(process.execPath, [pnpmPath, "--dir", "desktop", "build"]);
  continueStarting();
  log("正在打开 Electron。关闭应用或在终端按 Control+C 即可退出。");
  const env = { ...process.env, WECHAT_EMOJI_CLI: cli };
  delete env.ELECTRON_RUN_AS_NODE;
  await run(await electronRuntime(), [path.join(root, "desktop")], {
    env,
    cwd: path.join(root, "desktop"),
  });
}

main().catch((error) => {
  console.error(`\n[启动失败] ${error.message}`);
  process.exitCode ||= 1;
});
