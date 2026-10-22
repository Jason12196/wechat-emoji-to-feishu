const {
  app,
  BrowserWindow,
  Menu,
  ipcMain,
  dialog,
  protocol,
  net,
  shell,
  clipboard,
} = require("electron");
const { quitWeChat } = require("./services/wechat.cjs");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { CliRunner } = require("./services/runner.cjs");
const { MigrationService } = require("./services/migration.cjs");
const { failure, redact } = require("./services/errors.cjs");
protocol.registerSchemesAsPrivileged([
  {
    scheme: "emoji",
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  },
]);
let window, runner, service;
const uiPath = path.join(__dirname, "../dist/index.html");
function resolveCli() {
  if (process.env.WECHAT_EMOJI_CLI) return process.env.WECHAT_EMOJI_CLI;
  return [
    process.env.WECHAT_EMOJI_CLI,
    path.join(process.resourcesPath, "cli/wechat-emoji"),
    path.join(__dirname, "../../dist/wechat-emoji/wechat-emoji"),
  ].find((file) => file && path.isAbsolute(file) && fs.existsSync(file));
}
function createWindow() {
  window = new BrowserWindow({
    width: 1200,
    height: 840,
    minWidth: 920,
    minHeight: 680,
    title: "表情迁移",
    backgroundColor: "#fafafa",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 22, y: 22 },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler(
    (_contents, _permission, callback) => callback(false),
  );
  window.on("close", (event) => {
    if (runner.active) {
      event.preventDefault();
      dialog
        .showMessageBox(window, {
          type: "question",
          message: "任务还在进行中",
          detail:
            "退出会停止当前操作。已提交的表情需要在飞书核对，不会自动重新上传。",
          buttons: ["继续等待", "停止并退出"],
          defaultId: 0,
          cancelId: 0,
        })
        .then(({ response }) => {
          if (response === 1) {
            runner.cancel();
            window.destroy();
          }
        });
    }
  });
  window.loadFile(uiPath);
}
app.whenReady().then(() => {
  const home =
    process.env.WECHAT_EMOJI_HOME ||
    path.join(app.getPath("appData"), "wechat-emoji-to-feishu");
  runner = new CliRunner({
    cli: resolveCli(),
    home,
    emit: (event) => {
      if (window && !window.isDestroyed())
        window.webContents.send("migration:event", event);
    },
  });
  service = new MigrationService({
    runner,
    chooseDirectory: async (title) => {
      const result = await dialog.showOpenDialog(window, {
        title,
        defaultPath: app.getPath("downloads"),
        properties: ["openDirectory", "createDirectory"],
      });
      return result.canceled ? null : result.filePaths[0];
    },
  });
  protocol.handle("emoji", (request) => {
    const url = new URL(request.url);
    const id = url.pathname.slice(1);
    const file =
      url.hostname === "asset" &&
      /^[a-f0-9-]{36}$/.test(id) &&
      service.assets.get(id);
    return file
      ? net.fetch(pathToFileURL(file).href)
      : new Response("Not found", { status: 404 });
  });
  ipcMain.handle("migration:call", async (event, method, payload) => {
    if (
      event.sender !== window?.webContents ||
      event.senderFrame !== window.webContents.mainFrame ||
      event.senderFrame.url !== pathToFileURL(uiPath).href
    )
      return { ok: false, error: failure("INVALID_REQUEST", "访问检查") };
    try {
      let data;
      if (
        [
          "initialize",
          "prepareExport",
          "key",
          "extract",
          "openLocal",
          "plan",
          "login",
          "importSelection",
          "history",
          "restoreContext",
          "resume",
        ].includes(method)
      )
        data = await service[method](payload || {});
      else if (method === "quitWeChat") {
        if (runner.active) throw failure("OPERATION_BUSY", "退出微信");
        const { response } = await dialog.showMessageBox(window, {
          type: "question",
          title: "退出微信并继续？",
          message: "将退出正在运行的微信",
          detail:
            "请先完成正在进行的聊天、通话或文件传输。退出成功后会打开微信副本，用于读取表情。",
          buttons: ["取消", "退出微信并继续"],
          defaultId: 0,
          cancelId: 0,
          noLink: true,
        });
        data = response === 1 ? await quitWeChat() : { exited: false };
      } else if (method === "cancel") data = { cancelled: runner.cancel() };
      else if (method === "diagnostic") {
        if (!/^[a-f0-9-]{36}$/.test(payload?.id || ""))
          throw failure("INVALID_REQUEST", "读取诊断");
        let error = runner.problems.get(payload.id);
        if (!error)
          error = JSON.parse(
            fs.readFileSync(
              path.join(runner.diagnostics, `${payload.id}.json`),
              "utf8",
            ),
          );
        const summary = JSON.stringify(
          {
            code: error.code,
            stage: error.stage,
            taskId: error.taskId,
            id: error.id,
            time: error.time,
            detail: redact(error.detail),
            exitCode: error.exitCode,
            signal: error.signal,
            lastEvent: error.lastEvent,
            stderr: redact(error.stderr),
            engineDiagnostic: error.engineDiagnostic,
            platform: process.platform,
            arch: process.arch,
          },
          null,
          2,
        );
        if (payload.copy === true) clipboard.writeText(summary);
        data = { summary };
      } else if (method === "openDiagnostics") {
        await shell.openPath(runner.diagnostics);
        data = { opened: true };
      } else throw failure("INVALID_REQUEST", "接口检查", "不支持的操作");
      return { ok: true, data };
    } catch (cause) {
      const error = runner.problems.has(cause?.id)
        ? cause
        : runner.record(
            cause?.code && cause?.id
              ? cause
              : failure("ENGINE_ERROR", method, cause?.message || cause),
          );
      return { ok: false, error };
    }
  });
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      { role: "appMenu" },
      { role: "editMenu" },
      { role: "viewMenu" },
      { role: "windowMenu" },
    ]),
  );
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
app.on("before-quit", () => runner?.cancel());
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
