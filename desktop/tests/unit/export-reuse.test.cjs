const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { MigrationService } = require("../../electron/services/migration.cjs");

function setup(t) {
  const home = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "emoji-export-reuse-")),
  );
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const directory = path.join(home, "Downloads");
  fs.mkdirSync(directory);
  const calls = [];
  const state = {
    accounts: [{ wxid: "test-account", key_cached: false }],
    exports: [],
    statuses: new Map(),
    onExtract: () => {},
  };
  const runner = {
    home,
    run: async (args) => {
      calls.push(args);
      const [command, subcommand, target] = args;
      if (command === "accounts")
        return { data: { accounts: structuredClone(state.accounts) } };
      if (command === "doctor") return { data: { ready: true } };
      if (command === "exports" && subcommand === "discover")
        return { data: { exports: structuredClone(state.exports) } };
      if (command === "exports" && subcommand === "status") {
        if (fs.existsSync(path.join(target, "export-state.json"))) {
          const manifest = JSON.parse(
            fs.readFileSync(path.join(target, "export-state.json"), "utf8"),
          );
          return {
            data: {
              state: "partial",
              directory: target,
              wxid: manifest.wxid,
              ready: 0,
              expected: 0,
              remaining: 0,
              snapshot_ready: false,
            },
          };
        }
        return {
          data: structuredClone(
            state.statuses.get(target) || { state: "none", directory: target },
          ),
        };
      }
      if (command === "images" && subcommand === "inspect")
        return {
          data: {
            valid: 1,
            images: [
              {
                file: path.join(target, "a.png"),
                format: "PNG",
                frames: 1,
                bytes: 3,
              },
            ],
          },
        };
      if (command === "key") return { data: { key_cached: true } };
      if (command === "extract") {
        state.onExtract(args);
        return { data: { failed: 0 } };
      }
      throw new Error(`Unexpected call: ${args.join(" ")}`);
    },
  };
  const service = new MigrationService({
    runner,
    downloadsDirectory: directory,
    chooseDirectory: async () => null,
  });
  function exported(name, status = "complete", extras = {}) {
    const target = path.join(directory, name);
    fs.mkdirSync(target);
    fs.writeFileSync(path.join(target, "a.png"), "png");
    const item = {
      state: status,
      directory: target,
      wxid: "test-account",
      expected: 2,
      ready: status === "complete" ? 2 : 1,
      remaining: status === "complete" ? 0 : 1,
      snapshot_ready: status !== "unbound",
      ...extras,
    };
    state.exports.push(item);
    state.statuses.set(target, item);
    return item;
  }
  return { home, directory, state, calls, service, exported };
}

function rawExport(state) {
  const entry = state.exported("legacy-raw", "unbound", {
    wxid: undefined,
    legacy_raw: true,
    raw_count: 1,
    ready: 0,
    expected: 0,
    remaining: 0,
    snapshot_ready: false,
  });
  fs.unlinkSync(path.join(entry.directory, "a.png"));
  fs.mkdirSync(path.join(entry.directory, "originals"));
  fs.writeFileSync(
    path.join(entry.directory, "originals", "original.gif"),
    "old-original",
  );
  return entry;
}

test("A completed export opens its catalog without extraction or key capture", async (t) => {
  const { service, exported, calls, directory } = setup(t);
  const complete = exported("completed");
  const prepared = await service.prepareExport({ wxid: "test-account" });
  assert.equal(prepared.existing, "complete");
  assert.equal(prepared.catalog.directory, fs.realpathSync(complete.directory));
  assert.equal(prepared.catalog.items.length, 1);
  assert.equal(prepared.keyCached, false);
  assert.deepEqual(fs.readdirSync(directory), ["completed"]);
  assert.equal(
    calls.some(([name]) => ["extract", "key"].includes(name)),
    false,
  );
});

test("The latest partial export wins over an older completed export", async (t) => {
  const { service, exported, calls, state } = setup(t);
  const partial = exported("latest", "partial");
  exported("older", "complete");
  const first = await service.prepareExport({ wxid: "test-account" });
  const again = await service.prepareExport({ wxid: "test-account" });
  assert.equal(first.existing, "partial");
  assert.equal(first.directory, partial.directory);
  assert.equal(first.canResumeWithoutKey, true);
  assert.equal(first.remaining, 1);
  assert.equal(first.token, again.token);
  state.onExtract = () => {
    state.statuses.set(partial.directory, {
      ...partial,
      state: "complete",
      ready: 2,
      remaining: 0,
    });
  };
  const result = await service.extract({ token: first.token });
  assert.equal(result.exportState.state, "complete");
  assert.equal(result.remaining, 0);
  assert.equal(calls.filter(([name]) => name === "extract").length, 1);
  assert.equal(
    calls.find(([name]) => name === "extract").at(-1),
    partial.directory,
  );
  assert.equal(
    calls.some(([name]) => name === "key"),
    false,
  );
});

test("A token completed by another attempt never extracts a second time", async (t) => {
  const { service, exported, calls, state } = setup(t);
  const partial = exported("partial", "partial");
  const prepared = await service.prepareExport({ wxid: "test-account" });
  state.statuses.set(partial.directory, {
    ...partial,
    state: "complete",
    ready: 2,
    remaining: 0,
  });
  await service.extract({ token: prepared.token });
  assert.equal(
    calls.some(([name]) => name === "extract"),
    false,
  );
});

test("A partial export with no resource snapshot still needs key preparation", async (t) => {
  const { service, exported } = setup(t);
  exported("no-snapshot", "partial", { snapshot_ready: false });
  const prepared = await service.prepareExport({ wxid: "test-account" });
  assert.equal(prepared.existing, "partial");
  assert.equal(prepared.canResumeWithoutKey, false);
});

test("Fresh valid cache detection skips key capture despite stale page state", async (t) => {
  const { service, state, calls } = setup(t);
  await service.initialize();
  assert.equal(service.accounts[0].key_cached, false);
  state.accounts[0].key_cached = true;
  assert.deepEqual(await service.key({ wxid: "test-account" }), {
    keyCached: true,
    reused: true,
  });
  assert.equal(
    calls.some(([name]) => name === "key"),
    false,
  );
});

test("Preparation also refreshes cache availability before returning the next step", async (t) => {
  const { service, state } = setup(t);
  await service.initialize();
  state.accounts[0].key_cached = true;
  const prepared = await service.prepareExport({ wxid: "test-account" });
  assert.equal(prepared.keyCached, true);
});

test("Legacy unbound pictures require the explicit reuse entry point", async (t) => {
  const { service, exported, calls } = setup(t);
  const legacy = exported("legacy", "unbound", { wxid: undefined });
  await assert.rejects(
    service.useExistingExport({
      directory: legacy.directory,
      wxid: "test-account",
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  const found = await service.findExports({ wxid: "test-account" });
  assert.equal(found.exports[0].state, "unbound");
  assert.equal(found.keyCached, false);
  await assert.rejects(
    service.prepareExport({
      wxid: "test-account",
      directory: legacy.directory,
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  const catalog = await service.useExistingExport({
    directory: legacy.directory,
    wxid: "test-account",
  });
  assert.equal(catalog.items.length, 1);
  assert.equal(catalog.exportState.state, "unbound");
  assert.equal(
    calls.some(([name]) => ["extract", "key"].includes(name)),
    false,
  );
});

test("Other accounts and forged directory paths cannot be reused", async (t) => {
  const { service, exported, state, home } = setup(t);
  const other = exported("other", "complete", { wxid: "other-account" });
  assert.deepEqual(
    (await service.findExports({ wxid: "test-account" })).exports,
    [],
  );
  await assert.rejects(
    service.prepareExport({ wxid: "test-account", directory: other.directory }),
    (error) => error.code === "INVALID_REQUEST",
  );
  state.exports = [{ ...other, directory: path.join(home, "outside") }];
  await assert.rejects(
    service.findExports({ wxid: "test-account" }),
    (error) => error.code === "INVALID_REQUEST",
  );
});

test("A discovered directory is revalidated before loading its pictures", async (t) => {
  const { service, exported, state, calls } = setup(t);
  const complete = exported("changed", "complete");
  await service.findExports({ wxid: "test-account" });
  state.statuses.set(complete.directory, {
    ...complete,
    wxid: "other-account",
  });
  await assert.rejects(
    service.useExistingExport({
      directory: complete.directory,
      wxid: "test-account",
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  assert.equal(
    calls.some(([name]) => name === "images"),
    false,
  );
});

test("Changing the export location invalidates the prior discovery allowlist", async (t) => {
  const { service, exported, home } = setup(t);
  const complete = exported("old-location");
  await service.findExports({ wxid: "test-account" });
  service.chooseDirectory = async () => path.join(home, "changed");
  await service.chooseExportDirectory();
  await assert.rejects(
    service.useExistingExport({
      directory: complete.directory,
      wxid: "test-account",
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
});

test("Filesystem aliases still identify the same export without repeating it", async (t) => {
  const { service, exported, home, directory, calls } = setup(t);
  const complete = exported("completed");
  const alias = path.join(home, "downloads-alias");
  fs.symlinkSync(directory, alias, "dir");
  service.chooseDirectory = async () => alias;
  await service.chooseExportDirectory();
  const prepared = await service.prepareExport({
    wxid: "test-account",
    directory: path.join(alias, "completed"),
  });
  assert.equal(prepared.existing, "complete");
  assert.equal(prepared.catalog.directory, complete.directory);
  assert.equal(
    calls.some(([name]) => ["key", "extract"].includes(name)),
    false,
  );
});

test("Adopting legacy raw files requires explicit account confirmation", async (t) => {
  const state = setup(t);
  const legacy = rawExport(state);
  await state.service.findExports({ wxid: "test-account" });
  await assert.rejects(
    state.service.adoptExistingExport({
      directory: legacy.directory,
      wxid: "test-account",
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  assert.equal(
    fs.existsSync(path.join(legacy.directory, "export-state.json")),
    false,
  );
});

test("Confirmed legacy raw files continue in place with a private manifest", async (t) => {
  const state = setup(t);
  const legacy = rawExport(state);
  await state.service.findExports({ wxid: "test-account" });
  state.state.accounts[0].key_cached = true;
  const prepared = await state.service.adoptExistingExport({
    directory: legacy.directory,
    wxid: "test-account",
    confirmed: true,
  });
  assert.equal(prepared.existing, "partial");
  assert.equal(prepared.directory, legacy.directory);
  assert.equal(prepared.canResumeWithoutKey, false);
  assert.equal(prepared.keyCached, true);
  assert.equal(
    state.service.exports.get(prepared.token).directory,
    legacy.directory,
  );
  const manifest = path.join(legacy.directory, "export-state.json");
  assert.deepEqual(JSON.parse(fs.readFileSync(manifest, "utf8")), {
    version: 1,
    wxid: "test-account",
    resources: null,
  });
  assert.equal(fs.statSync(manifest).mode & 0o777, 0o600);
  assert.equal(
    fs.readFileSync(
      path.join(legacy.directory, "originals", "original.gif"),
      "utf8",
    ),
    "old-original",
  );
  assert.equal(
    state.calls.some(([name]) => ["key", "extract"].includes(name)),
    false,
  );
});

test("Legacy raw adoption refuses another account or a directory with a report", async (t) => {
  const state = setup(t);
  const legacy = rawExport(state);
  await state.service.findExports({ wxid: "test-account" });
  await assert.rejects(
    state.service.adoptExistingExport({
      directory: legacy.directory,
      wxid: "another-account",
      confirmed: true,
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  fs.writeFileSync(path.join(legacy.directory, "export-report.json"), "{}");
  await assert.rejects(
    state.service.adoptExistingExport({
      directory: legacy.directory,
      wxid: "test-account",
      confirmed: true,
    }),
    (error) => error.code === "INVALID_REQUEST",
  );
  assert.equal(
    fs.existsSync(path.join(legacy.directory, "export-state.json")),
    false,
  );
});
