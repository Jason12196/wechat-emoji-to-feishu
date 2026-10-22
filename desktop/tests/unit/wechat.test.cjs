const test = require("node:test");
const assert = require("node:assert/strict");
const { quitWeChat } = require("../../electron/services/wechat.cjs");
for (const [status, code] of [
  ["exited", null],
  ["timeout", "WECHAT_QUIT_TIMEOUT"],
  ["refused", "WECHAT_QUIT_FAILED"],
]) {
  test(`Normal WeChat quit: ${status}`, async () => {
    const action = quitWeChat({
      platform: "darwin",
      run: async (file, args, options) => {
        assert.equal(file, "/usr/bin/osascript");
        assert.match(args[3], /com.tencent.xinWeChat/);
        assert.doesNotMatch(args[3], /forceTerminate|kill/);
        assert.equal(options.timeout, 25000);
        return { stdout: status };
      },
    });
    if (code)
      await assert.rejects(
        action,
        (error) => error.code === code && error.recovery.includes("手动"),
      );
    else assert.deepEqual(await action, { exited: true });
  });
}
test("Quit diagnostics retain execution error", async () => {
  await assert.rejects(
    quitWeChat({
      platform: "darwin",
      run: async () => {
        throw new Error("Permission denied");
      },
    }),
    (e) =>
      e.code === "WECHAT_QUIT_FAILED" && e.detail.includes("Permission denied"),
  );
});
