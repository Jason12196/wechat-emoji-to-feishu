const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { MigrationService } = require("../../electron/services/migration.cjs");

function setup(t, choices = []) {
  const home = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "emoji-export-directory-")),
  );
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const downloads = path.join(home, "Downloads");
  const calls = [];
  const service = new MigrationService({
    downloadsDirectory: downloads,
    runner: {
      home,
      run: async ([command, subcommand, directory]) => {
        if (command === "accounts")
          return {
            data: { accounts: [{ wxid: "test-account", key_cached: true }] },
          };
        if (command === "doctor") return { data: { ready: true } };
        if (command === "exports" && subcommand === "discover")
          return { data: { exports: [] } };
        if (command === "exports" && subcommand === "status")
          return { data: { state: "none", directory } };
        throw new Error(`Unexpected command: ${command}`);
      },
    },
    chooseDirectory: async (...args) => {
      calls.push(args);
      return choices.shift() || null;
    },
  });
  return { home, downloads, service, calls };
}

test("Export defaults to Downloads and preparation never opens a chooser", async (t) => {
  const { service, downloads, calls } = setup(t);
  const initialized = await service.initialize();
  assert.equal(initialized.exportDirectory, downloads);
  const first = await service.prepareExport({ wxid: "test-account" });
  const second = await service.prepareExport({ wxid: "test-account" });
  assert.deepEqual(calls, []);
  assert.equal(first.keyCached, true);
  const firstDirectory = service.exports.get(first.token).directory;
  const secondDirectory = service.exports.get(second.token).directory;
  assert.equal(path.dirname(firstDirectory), downloads);
  assert.match(path.basename(firstDirectory), /^微信表情-\d{4}-\d{2}-\d{2}T/);
  assert.ok(fs.statSync(firstDirectory).isDirectory());
  assert.ok(fs.statSync(secondDirectory).isDirectory());
  assert.equal(firstDirectory, secondDirectory);
  assert.equal(first.token, second.token);
});

test("Choosing a directory only changes future export preparations", async (t) => {
  const state = setup(t);
  const { service, downloads, calls, home } = state;
  await service.initialize();
  const first = await service.prepareExport({ wxid: "test-account" });
  const changed = path.join(home, "chosen-directory");
  service.chooseDirectory = async (...args) => {
    calls.push(args);
    return changed;
  };
  assert.deepEqual(await service.chooseExportDirectory(), {
    directory: changed,
  });
  assert.deepEqual(calls, [["选择表情导出位置", downloads]]);
  assert.equal(fs.existsSync(changed), false);
  const second = await service.prepareExport({ wxid: "test-account" });
  assert.equal(
    path.dirname(service.exports.get(first.token).directory),
    downloads,
  );
  assert.equal(
    path.dirname(service.exports.get(second.token).directory),
    changed,
  );
});

test("Cancelling the chooser preserves the current directory", async (t) => {
  const { service, downloads, calls, home } = setup(t);
  assert.deepEqual(await service.chooseExportDirectory(), {
    directory: downloads,
  });
  const changed = path.join(home, "chosen-directory");
  service.chooseDirectory = async () => changed;
  await service.chooseExportDirectory();
  service.chooseDirectory = async (...args) => {
    calls.push(args);
    return null;
  };
  assert.deepEqual(await service.chooseExportDirectory(), {
    directory: changed,
  });
  assert.equal(service.exportDirectory, changed);
  assert.deepEqual(calls.at(-1), ["选择表情导出位置", changed]);
  assert.equal(fs.existsSync(changed), false);
});

test("Services without a Downloads injection retain a platform fallback", () => {
  const service = new MigrationService({
    runner: { home: "/unused-test-home" },
    chooseDirectory: async () => null,
  });
  assert.equal(service.exportDirectory, path.join(os.homedir(), "Downloads"));
});

test("The chosen directory and empty preparations survive app restarts", async (t) => {
  const { service, home } = setup(t);
  const selected = path.join(home, "my-exports");
  service.chooseDirectory = async () => selected;
  await service.chooseExportDirectory();
  const first = await service.prepareExport({ wxid: "test-account" });
  const restarted = new MigrationService({
    runner: service.runner,
    downloadsDirectory: path.join(home, "Downloads"),
    chooseDirectory: async () => null,
  });
  const initialized = await restarted.initialize();
  assert.equal(initialized.exportDirectory, selected);
  const continued = await restarted.prepareExport({ wxid: "test-account" });
  assert.equal(continued.directory, first.directory);
  for (const file of ["preferences.json", "export-jobs.json"])
    assert.equal(
      fs.statSync(path.join(home, "desktop", file)).mode & 0o777,
      0o600,
    );
});
