const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { failure } = require("./errors.cjs");
const execute = promisify(execFile);
// NSRunningApplication.terminate requests a normal quit; never sends a kill signal.
const quitScript = `
ObjC.import('AppKit');
function targets() {
  return $.NSRunningApplication.runningApplicationsWithBundleIdentifier('com.tencent.xinWeChat');
}
const apps = targets();
let refused = false;
for (let i = 0; i < Number(apps.count); i++) {
  if (!Number(apps.objectAtIndex(i).terminate)) refused = true;
}
if (refused) 'refused';
else {
  const deadline = Date.now() + 20000;
  while (Number(targets().count) > 0 && Date.now() < deadline) delay(0.25);
  Number(targets().count) === 0 ? 'exited' : 'timeout';
}
`;
async function quitWeChat({ run = execute, platform = process.platform } = {}) {
  if (platform !== "darwin")
    throw failure(
      "WECHAT_QUIT_FAILED",
      "退出微信",
      "Automatic quit is supported on macOS only.",
    );
  let result;
  try {
    result = await run(
      "/usr/bin/osascript",
      ["-l", "JavaScript", "-e", quitScript],
      {
        timeout: 25000,
        maxBuffer: 16384,
      },
    );
  } catch (cause) {
    throw failure(
      "WECHAT_QUIT_FAILED",
      "退出微信",
      cause.stderr || cause.message,
    );
  }
  const status = result.stdout.trim();
  if (status === "exited") return { exited: true };
  throw failure(
    status === "timeout" ? "WECHAT_QUIT_TIMEOUT" : "WECHAT_QUIT_FAILED",
    "退出微信",
    `Quit status: ${status}`,
  );
}
module.exports = { quitWeChat };
