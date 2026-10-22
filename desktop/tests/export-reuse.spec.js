import { test, expect } from "@playwright/test";

async function fixture(
  page,
  state,
  snapshot = false,
  cached = false,
  legacy = false,
) {
  await page.addInitScript(
    ({ state, snapshot, cached, legacy }) => {
      const record = {
        state,
        directory: "/Downloads/previous",
        wxid: state === "unbound" ? undefined : "fixture",
        expected: 2,
        ready: state === "partial" ? 1 : 2,
        remaining: state === "partial" ? 1 : 0,
        snapshot_ready: snapshot,
        legacy_raw: legacy,
        raw_count: legacy ? 208 : 0,
      };
      window.fixtureCalls = [];
      const catalog = {
        token: "catalog",
        items: [],
        directory: record.directory,
      };
      window.migration = {
        initialize: async () => ({
          ok: true,
          data: {
            accounts: [{ wxid: "fixture", key_cached: cached }],
            environment: {},
            exportDirectory: "/Downloads",
          },
        }),
        findExports: async () => ({ ok: true, data: { exports: [record] } }),
        prepareExport: async () => {
          window.fixtureCalls.push("prepare");
          return {
            ok: true,
            data: {
              ...record,
              existing: state,
              token: "export",
              keyCached: cached,
              canResumeWithoutKey: snapshot,
              catalog,
            },
          };
        },
        adoptExistingExport: async ({ confirmed }) => {
          if (!confirmed) throw new Error("Account confirmation missing");
          window.fixtureCalls.push("adopt");
          return {
            ok: true,
            data: {
              ...record,
              state: "partial",
              existing: "partial",
              token: "export",
              keyCached: cached,
            },
          };
        },
        useExistingExport: async () => {
          window.fixtureCalls.push("use-existing");
          return { ok: true, data: catalog };
        },
        extract: async () => {
          window.fixtureCalls.push("extract");
          return {
            ok: true,
            data: {
              ...catalog,
              exportState: {
                ...record,
                state: "complete",
                ready: 2,
                remaining: 0,
              },
            },
          };
        },
        key: async () => {
          window.fixtureCalls.push("key");
          throw new Error("Should not capture key");
        },
        quitWeChat: async () => {
          window.fixtureCalls.push("quit");
          return { ok: true, data: { exited: false } };
        },
        onEvent: () => () => {},
      };
    },
    { state, snapshot, cached, legacy },
  );
  await page.goto("/");
  await expect(page.locator(".export-reuse-note")).toBeVisible();
  await page.locator(".wechat-source").click();
}

test("Complete export enters selection without extraction or key capture", async ({
  page,
}) => {
  await fixture(page, "complete");
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual(["prepare"]);
});

test("Partial export offers Continue and resumes its snapshot without a key", async ({
  page,
}) => {
  await fixture(page, "partial", true, false);
  await expect(
    page.getByRole("dialog", { name: "继续上次导出" }),
  ).toContainText("已完成 1 / 2 张");
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual(["prepare"]);
  await page.getByRole("button", { name: "继续导出", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([
    "prepare",
    "extract",
  ]);
});

test("A valid cached key avoids WeChat preparation when continuing without a snapshot", async ({
  page,
}) => {
  await fixture(page, "partial", false, true);
  await page.getByRole("button", { name: "继续导出", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([
    "prepare",
    "extract",
  ]);
});

test("Legacy images require explicit account confirmation and are reused without extraction", async ({
  page,
}) => {
  await fixture(page, "unbound");
  await expect(
    page.getByRole("dialog", { name: "发现已有导出" }),
  ).toContainText("未保存微信账号");
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([]);
  await page.getByRole("button", { name: "使用已有图片", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([
    "use-existing",
  ]);
});

test("Legacy interrupted raw files stay in their folder after explicit account confirmation", async ({
  page,
}) => {
  await fixture(page, "unbound", false, true, true);
  await expect(
    page.getByRole("dialog", { name: "继续旧版导出" }),
  ).toContainText("208 个原始文件");
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([]);
  await page
    .getByRole("button", { name: "确认账号并继续", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([
    "adopt",
    "extract",
  ]);
});
