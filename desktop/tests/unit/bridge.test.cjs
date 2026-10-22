const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { CliRunner } = require("../../electron/services/runner.cjs");
const { MigrationService } = require("../../electron/services/migration.cjs");
const { redact } = require("../../electron/services/errors.cjs");
const cli = path.resolve(__dirname, "../fixtures/cli.cjs");
fs.chmodSync(cli, 0o700);
function setup(t, mode) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "emoji-bridge-"));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  return new CliRunner({ cli, home, env: { TEST_CLI_MODE: mode || "" } });
}
test("Successful protocol has a final result, task identity and progress", async (t) => {
  const runner = setup(t);
  const result = await runner.run(["doctor"], "环境检查");
  assert.equal(result.data.ready, true);
  assert.match(result.taskId, /^[a-f0-9-]{36}$/);
});
test("Missing terminal event is an error, not success", async (t) => {
  const runner = setup(t, "missing-final");
  await assert.rejects(
    runner.run(["doctor"], "环境检查"),
    (error) =>
      error.code === "CLI_EXITED" &&
      error.stage === "环境检查" &&
      fs.existsSync(error.diagnostic),
  );
});
test("Malformed protocol stops with distinct diagnostics", async (t) => {
  const runner = setup(t, "protocol");
  await assert.rejects(
    runner.run(["doctor"], "解析事件"),
    (error) => error.code === "CLI_PROTOCOL_ERROR" && Boolean(error.taskId),
  );
});
test("Errors retain context and redact credentials and links", async (t) => {
  const runner = setup(t, "error");
  await assert.rejects(runner.run(["doctor"], "飞书登录"), (error) => {
    assert.equal(error.code, "LOGIN_TIMEOUT");
    const log = fs.readFileSync(error.diagnostic, "utf8");
    assert.ok(!log.includes("private-access-value"));
    assert.ok(!log.includes("resource.invalid"));
    assert.ok(!log.includes("ab".repeat(32)));
    assert.ok(log.includes("exitCode"));
    return true;
  });
});
test("Concurrent operations are rejected and cancellation keeps identity", async (t) => {
  const runner = setup(t, "wait");
  const first = runner.run(["doctor"], "等待测试");
  await assert.rejects(
    runner.run(["doctor"], "重复操作"),
    (error) => error.code === "OPERATION_BUSY",
  );
  runner.cancel();
  await assert.rejects(first, (error) => error.code === "CANCELLED");
});
test("Timeout differs from cancellation", async (t) => {
  const runner = setup(t, "wait");
  await assert.rejects(
    runner.run(["doctor"], "等待测试", 80),
    (error) => error.code === "CLI_TIMEOUT",
  );
});
test("Selection rejects unknown catalog before spawning", async (t) => {
  const runner = setup(t);
  const service = new MigrationService({
    runner,
    chooseDirectory: async () => null,
  });
  await assert.rejects(
    service.plan({
      catalog: "../outside",
      selected: [0],
      account: "test",
      existing: 0,
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
});
test("Unconfirmed account never starts an import", async (t) => {
  const runner = setup(t);
  const service = new MigrationService({
    runner,
    chooseDirectory: async () => null,
  });
  service.plans.set("test", {
    state: "planned",
    account: "test",
    plan: { fits: true },
  });
  await assert.rejects(
    service.importSelection({ token: "test", confirmed: false }),
    (error) => error.code === "ACCOUNT_UNCONFIRMED",
  );
});
test("Redaction removes whole authorization and cookie values", () => {
  const value = redact(
    "authorization: Bearer secret-value\ncookie: user=private; session=hidden\nstatus: failed",
  );
  assert.ok(!value.includes("secret-value"));
  assert.ok(!value.includes("session=hidden"));
  assert.ok(value.includes("status: failed"));
});

test("Partial results retain a diagnostic instead of claiming full success", async (t) => {
  const runner = setup(t, "partial");
  const result = await runner.run(["doctor"], "部分结果");
  assert.equal(result.status, "partial");
  assert.equal(result.data.diagnostic.code, "PARTIAL_RESULT");
  assert.ok(fs.existsSync(result.data.diagnostic.diagnostic));
});
test("A modified selection snapshot cannot be uploaded", async (t) => {
  const runner = setup(t);
  const service = new MigrationService({
    runner,
    chooseDirectory: async () => null,
  });
  const directory = path.join(runner.home, "source");
  fs.mkdirSync(directory);
  const file = path.join(directory, "a.png");
  fs.writeFileSync(file, "original");
  service.catalogs.set("catalog", {
    directory: fs.realpathSync(directory),
    items: [{ file, label: "test" }],
  });
  const planned = await service.plan({
    catalog: "catalog",
    selected: [0],
    account: "test",
    existing: 0,
  });
  const job = service.plans.get(planned.token);
  fs.writeFileSync(path.join(job.directory, job.selection[0].file), "changed");
  service.loginAccount = "test";
  await assert.rejects(
    service.importSelection({ token: planned.token, confirmed: true }),
    (error) => error.code === "SELECTION_CHANGED",
  );
  assert.equal(job.state, "planned");
});
test("Pending ledger records block automatic resume", async (t) => {
  const runner = setup(t);
  const service = new MigrationService({
    runner,
    chooseDirectory: async () => null,
  });
  const token = require("node:crypto").randomUUID();
  const ledger = path.join(runner.home, "ledger.json");
  fs.writeFileSync(ledger, JSON.stringify({ hash: { status: "pending" } }));
  await service.saveJob({
    token,
    account: "test",
    directory: runner.home,
    selection: [{ id: 0 }],
    state: "interrupted",
    ledger,
  });
  service.loginAccount = "test";
  await assert.rejects(
    service.resume({ job: token, existing: 100, confirmed: true }),
    (error) => error.code === "LEDGER_UNRESOLVED",
  );
});
