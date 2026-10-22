import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testIgnore: ["**/unit/**", "**/fixtures/**"],
  timeout: 20000,
  fullyParallel: true,
  use: {
    baseURL: "http://127.0.0.1:5196",
    viewport: { width: 1200, height: 840 },
    headless: true,
    channel: "chromium",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5196",
    reuseExistingServer: !process.env.CI,
  },
});
