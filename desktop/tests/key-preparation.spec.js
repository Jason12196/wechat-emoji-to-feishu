import { test, expect } from "@playwright/test";

async function initialize(page, fail = false) {
  await page.addInitScript(
    ({ fail }) => {
      window.fixtureCalls = [];
      window.migration = {
        initialize: async () => ({
          ok: true,
          data: {
            accounts: [
              { wxid: "fixture", nickname: "测试微信", key_cached: false },
            ],
            environment: {},
            exportDirectory: "/Downloads",
          },
        }),
        prepareExport: async () => ({
          ok: true,
          data: { token: "fixture", keyCached: false },
        }),
        quitWeChat: async () => ({ ok: true, data: { exited: true } }),
        key: async () => {
          window.fixtureCalls.push("key");
          await new Promise((resolve) =>
            window.addEventListener("fixture-key-complete", resolve, {
              once: true,
            }),
          );
          return fail
            ? {
                ok: false,
                error: {
                  code: "ENGINE_ERROR",
                  stage: "获取微信密钥",
                  message: "隔离测试：未能取得密钥",
                  detail: "fixture failure",
                },
              }
            : { ok: true, data: { keyCached: true } };
        },
        extract: async () => {
          window.fixtureCalls.push("extract");
          return { ok: true, data: { token: "catalog", items: [] } };
        },
        cancel: async () => ({ ok: true, data: { cancelled: true } }),
        onEvent: () => () => {},
      };
    },
    { fail },
  );
  await page.goto("/");
  await expect(page.getByLabel("微信账号")).toHaveValue("fixture");
  await page
    .getByRole("button", { name: "从微信收藏导出", exact: true })
    .click();
  await page
    .getByRole("button", { name: "退出微信并继续", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "正在准备微信", exact: true }),
  ).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => window.fixtureCalls.includes("key")))
    .toBe(true);
}

test("Key success automatically exports after loading without login confirmation", async ({
  page,
}) => {
  await initialize(page);
  await expect(page.locator(".preparing-spinner")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("checkbox")).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual(["key"]);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("fixture-key-complete")),
  );
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual([
    "key",
    "extract",
  ]);
});

test("A real key error displays diagnostics and never starts export", async ({
  page,
}) => {
  await initialize(page, true);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("fixture-key-complete")),
  );
  await expect(page.getByRole("dialog")).toContainText(
    "隔离测试：未能取得密钥",
  );
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual(["key"]);
});

test("Canceling preparation prevents a late success from starting export", async ({
  page,
}) => {
  await initialize(page);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.evaluate(() =>
    window.dispatchEvent(new Event("fixture-key-complete")),
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCalls)).toEqual(["key"]);
});
