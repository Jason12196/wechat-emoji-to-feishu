import { test, expect } from "@playwright/test";

async function exportDemo(page, cached = false) {
  if (cached) await page.getByLabel("演示场景").selectOption("cached-key");
  await page
    .getByRole("button", { name: "从微信收藏导出", exact: true })
    .click();
  if (!cached) {
    await expect(
      page.getByRole("button", { name: "退出微信并继续" }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "退出微信并继续" }).click();
    await expect(
      page.getByRole("button", { name: "开始读取表情" }),
    ).toBeDisabled();
    await page
      .getByRole("checkbox", { name: "我已登录，并打开了表情面板" })
      .check();
    await page.getByRole("button", { name: "开始读取表情" }).click();
  }
  await expect(
    page.getByRole("heading", { name: "每一张，都很有你。" }),
  ).toBeVisible();
}
async function loginDemo(page) {
  await page.getByRole("button", { name: "登录飞书", exact: true }).click();
  await page.getByRole("button", { name: "打开浏览器登录" }).click();
  await expect(
    page.getByRole("button", { name: "已登录，继续" }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "我已核对，这是要接收表情的账号" })
    .check();
  await page.getByRole("button", { name: "已登录，继续" }).click();
}
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("WeChat and Feishu confirmations, capacity and complete migration", async ({
  page,
}) => {
  await exportDemo(page);
  await page.getByRole("button", { name: "准备导入", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "开始导入 24 张" }),
  ).toBeDisabled();
  await page.getByLabel("飞书目前已有多少张个人表情？").fill("999");
  await expect(
    page.getByText("空间还差 23 张", { exact: false }),
  ).toBeVisible();
  await loginDemo(page);
  await expect(
    page.getByRole("button", { name: "开始导入 24 张" }),
  ).toBeDisabled();
  await page.getByLabel("飞书目前已有多少张个人表情？").fill("960");
  await page.getByRole("button", { name: "开始导入 24 张" }).click();
  await expect(
    page.getByRole("heading", { name: "换个地方，继续表达。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看本次记录" }).click();
  await expect(page.getByRole("dialog", { name: "迁移记录" })).toContainText(
    "24 张",
  );
});

test("Cached key bypasses quit dialog, selection and search remain usable", async ({
  page,
}) => {
  await exportDemo(page, true);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "取消全选", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "准备导入", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "选择好耶", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "准备导入", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("搜索表情").fill("不存在的表情");
  await expect(
    page.getByRole("heading", { name: "没有找到这张表情" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看全部", exact: true }).click();
  await expect(page.locator(".sticker-tile")).toHaveCount(24);
  await page.getByRole("button", { name: "预览好耶", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "好耶", exact: true }),
  ).toBeVisible();
});

test("Uncertain import pauses and requires acknowledgement before resuming", async ({
  page,
}) => {
  await page.getByLabel("演示场景").selectOption("import-uncertain");
  await exportDemo(page);
  await page.getByRole("button", { name: "准备导入", exact: true }).click();
  await loginDemo(page);
  await page.getByRole("button", { name: "开始导入 24 张" }).click();
  await expect(
    page.getByRole("heading", { name: "停一下，也没关系。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "核对后继续" }).click();
  await expect(
    page.getByRole("button", { name: "继续未提交的表情" }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "已在飞书核对，该项已经添加" })
    .check();
  await page.getByRole("button", { name: "继续未提交的表情" }).click();
  await expect(
    page.getByRole("heading", { name: "换个地方，继续表达。" }),
  ).toBeVisible();
});

test("Dialog escape returns focus and reduced motion disables entrance effects", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const trigger = page.getByRole("button", {
    name: "从微信收藏导出",
    exact: true,
  });
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.locator(".page-enter")).toHaveCSS("animation-name", "none");
});

test("Exit prompt provides a failure path without exporting", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "从微信收藏导出", exact: true })
    .click();
  await page.getByRole("button", { name: "退出微信并继续" }).click();
  await page.getByRole("button", { name: "窗口闪退或打不开？" }).click();
  await expect(
    page.getByRole("dialog", { name: "微信没有准备好" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重新准备微信" }).click();
  await expect(
    page.getByRole("button", { name: "退出微信并继续" }),
  ).toBeEnabled();
});
