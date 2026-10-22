import { test, expect, _electron as electron } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const cli = path.join(root, "tests/fixtures/cli.cjs");
let app, folder;
test.beforeEach(async () => {
  folder = fs.mkdtempSync(path.join(os.tmpdir(), "emoji-electron-"));
  const image = path.join(folder, "fixture.png");
  fs.writeFileSync(
    image,
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/q9kAAAAASUVORK5CYII=",
      "base64",
    ),
  );
  fs.chmodSync(cli, 0o700);
  app = await electron.launch({
    args: [root],
    env: {
      ...process.env,
      WECHAT_EMOJI_CLI: cli,
      WECHAT_EMOJI_HOME: path.join(folder, "state"),
      TEST_IMAGE: image,
      TEST_ACCOUNTS_DELAY: "700",
      TEST_CALLS: path.join(folder, "calls.jsonl"),
    },
  });
  await app.evaluate(({ dialog }, directory) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [directory],
    });
  }, folder);
});
test.afterEach(async () => {
  await app?.close();
  fs.rmSync(folder, { recursive: true, force: true });
});
test("Real Electron IPC: source, local assets, offline plan, login confirmation and import", async () => {
  const page = await app.firstWindow();
  // A single detected account advances without a second source-card click.
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
  await expect(page.locator(".sticker-tile")).toHaveCount(1);
  await expect
    .poll(() =>
      page
        .locator(".real-sticker")
        .evaluate((img) => img.complete && img.naturalWidth > 0),
    )
    .toBe(true);
  expect(await page.evaluate(() => typeof window.require)).toBe("undefined");
  await page.getByRole("button", { name: "准备导入", exact: true }).click();
  await page.getByLabel("飞书目前已有多少张个人表情？").fill("900");
  await page.getByRole("button", { name: "检查导入计划" }).click();
  await expect(
    page.getByRole("button", { name: "开始导入 1 张" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "登录飞书", exact: true }).click();
  await page.getByRole("button", { name: "打开浏览器登录" }).click();
  await page
    .getByRole("checkbox", { name: "我已核对，这是要接收表情的账号" })
    .check();
  await page.getByRole("button", { name: "已登录，继续" }).click();
  await page.getByRole("button", { name: "开始导入 1 张" }).click();
  await expect(
    page.getByRole("heading", { name: "换个地方，继续表达。" }),
  ).toBeVisible();
  const calls = fs
    .readFileSync(path.join(folder, "calls.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  expect(calls.findIndex((args) => args[1] === "plan")).toBeLessThan(
    calls.findIndex((args) => args[1] === "login"),
  );
  expect(calls.filter((args) => args[1] === "import")).toHaveLength(1);
});
test("Canceling automatic export preparation stays on the source page", async () => {
  await app.evaluate(({ dialog }) => {
    globalThis.pickerCalls = 0;
    dialog.showOpenDialog = async () => {
      globalThis.pickerCalls += 1;
      return { canceled: true, filePaths: [] };
    };
  });
  const page = await app.firstWindow();
  await expect(page.getByLabel("微信账号")).toHaveValue("wxid_fixture");
  await expect.poll(() => app.evaluate(() => globalThis.pickerCalls)).toBe(1);
  await expect(page.locator(".bottom-bar")).toHaveCount(0);
  await page.waitForTimeout(1000);
  expect(await app.evaluate(() => globalThis.pickerCalls)).toBe(1);
  await page
    .getByRole("button", { name: "从微信收藏导出", exact: true })
    .click();
  await expect.poll(() => app.evaluate(() => globalThis.pickerCalls)).toBe(2);
});
test("Real Electron: missing CLI exposes actionable diagnostics", async () => {
  await app.close();
  app = await electron.launch({
    args: [root],
    env: {
      ...process.env,
      WECHAT_EMOJI_CLI: path.join(folder, "missing"),
      WECHAT_EMOJI_HOME: path.join(folder, "failure"),
    },
  });
  // An explicit override must never silently fall back to another installed CLI.
  const page = await app.firstWindow();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByText("查看诊断详情", { exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("CLI_NOT_FOUND");
  await expect(page.getByRole("dialog")).toContainText("检测微信账号");
});
