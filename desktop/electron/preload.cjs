const { contextBridge, ipcRenderer } = require("electron");
const call = (method, payload) =>
  ipcRenderer.invoke("migration:call", method, payload);
contextBridge.exposeInMainWorld("migration", {
  initialize: () => call("initialize"),
  chooseExportDirectory: () => call("chooseExportDirectory"),
  prepareExport: (payload) => call("prepareExport", payload),
  quitWeChat: () => call("quitWeChat"),
  key: (payload) => call("key", payload),
  extract: (payload) => call("extract", payload),
  openLocal: () => call("openLocal"),
  plan: (payload) => call("plan", payload),
  login: (payload) => call("login", payload),
  importSelection: (payload) => call("importSelection", payload),
  history: () => call("history"),
  restoreContext: (payload) => call("restoreContext", payload),
  resume: (payload) => call("resume", payload),
  cancel: () => call("cancel"),
  diagnostic: (payload) => call("diagnostic", payload),
  openDiagnostics: () => call("openDiagnostics"),
  onEvent: (listener) => {
    const handler = (_event, value) => listener(value);
    ipcRenderer.on("migration:event", handler);
    return () => ipcRenderer.removeListener("migration:event", handler);
  },
});
