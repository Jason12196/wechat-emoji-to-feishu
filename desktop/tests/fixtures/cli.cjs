#!/usr/bin/env node
// Isolated protocol fixture: never starts WeChat, a browser, or an upload.
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const id = randomUUID();
const argv = process.argv.slice(2);
const args = argv.slice(argv.indexOf("--home") + 2);
const mode = process.env.TEST_CLI_MODE;
if (args[0] === "accounts" && process.env.TEST_ACCOUNTS_DELAY)
  Atomics.wait(
    new Int32Array(new SharedArrayBuffer(4)),
    0,
    0,
    Number(process.env.TEST_ACCOUNTS_DELAY),
  );
if (process.env.TEST_CALLS)
  fs.appendFileSync(process.env.TEST_CALLS, JSON.stringify(args) + "\n");
function emit(type, extra = {}) {
  console.log(
    JSON.stringify({
      protocol_version: 1,
      task_id: id,
      type,
      time: new Date().toISOString(),
      ...extra,
    }),
  );
}
emit("started");
if (mode === "protocol") {
  console.log("not json");
  process.exit(1);
}
if (mode === "missing-final") process.exit(0);
if (mode === "wait") {
  setTimeout(() => {}, 60000);
  return;
}
if (mode === "error") {
  process.stderr.write(
    "authorization: Bearer private-access-value\nhttps://resource.invalid/secret\n" +
      "ab".repeat(32),
  );
  emit("error", {
    code: "LOGIN_TIMEOUT",
    result: { message: "Login timeout https://resource.invalid/secret" },
  });
  process.exit(2);
}
const find = (name) =>
  args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
let data = {};
if (args[0] === "accounts")
  data = {
    accounts: [
      {
        wxid: "wxid_fixture",
        nickname: "测试微信",
        key_cached: !process.env.TEST_KEY_MISSING,
        running: false,
      },
    ],
  };
else if (args[0] === "doctor")
  data = { ready: true, rust_cli_ready: true, chromium_ready: true };
else if (args[0] === "key") data = { key_cached: true };
else if (args[0] === "exports") {
  data =
    args[1] === "discover"
      ? { exports: [] }
      : {
          state: "none",
          directory: args[2],
          expected: 0,
          ready: 0,
          remaining: 0,
          snapshot_ready: false,
        };
} else if (
  args[0] === "extract" ||
  (args[0] === "images" && args[1] === "prepare")
) {
  const out = find("--out");
  fs.mkdirSync(out, { recursive: true });
  fs.copyFileSync(process.env.TEST_IMAGE, path.join(out, "sample.png"));
  data = { exported: 1, ready: 1, failed: 0 };
} else if (args[0] === "images" && args[1] === "inspect") {
  const file = path.join(args[2], "sample.png");
  data = {
    valid: 1,
    invalid: 0,
    images: [
      {
        file,
        format: "PNG",
        frames: 1,
        bytes: fs.statSync(file).size,
        width: 20,
        height: 20,
      },
    ],
  };
} else if (args[0] === "feishu" && args[1] === "login")
  data = { logged_in: true };
else if (args[0] === "feishu" && args[1] === "plan") {
  let unresolved = [];
  if (args.includes("--ledger"))
    unresolved = Object.values(
      JSON.parse(fs.readFileSync(find("--ledger"), "utf8")),
    ).filter((item) => item.status !== "confirmed");
  data = {
    fits: unresolved.length === 0,
    selected: 1,
    available: 1000 - Number(find("--existing-count")),
    invalid: [],
    oversize: [],
    unresolved,
    files: [],
  };
} else if (args[0] === "feishu" && args[1] === "import") {
  const ledger =
    find("--ledger") ||
    path.join(
      find("--home") || argv[argv.indexOf("--home") + 1],
      "imports",
      `${id}.json`,
    );
  fs.mkdirSync(path.dirname(ledger), { recursive: true });
  fs.writeFileSync(
    ledger,
    JSON.stringify({ fixture: { status: "confirmed" } }),
  );
  data = { success: 1, unknown: 0, remaining: 0, ledger };
} else {
  emit("error", {
    code: "INVALID_REQUEST",
    result: { message: "Unsupported fixture command" },
  });
  process.exit(2);
}
emit("progress", { current: 1, total: 1, message: "隔离测试步骤完成" });
emit("result", {
  status: mode === "partial" ? "partial" : "complete",
  result: mode === "partial" ? { ...data, unknown: 1 } : data,
});
if (mode === "partial") process.exitCode = 3;
