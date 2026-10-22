import { useEffect, useRef, useState } from "react";

const bridge = window.migration;
export default function useRealMigration() {
  const [step, setStep] = useState(0),
    [items, setItems] = useState([]),
    [selected, setSelected] = useState(new Set());
  const [operation, setOperation] = useState(null),
    [done, setDone] = useState(0),
    [total, setTotal] = useState(0);
  const [message, setMessage] = useState(""),
    [error, setError] = useState(null),
    [result, setResult] = useState(null);
  const [accounts, setAccounts] = useState([]),
    [wxid, setWxid] = useState(""),
    [environment, setEnvironment] = useState(null);
  const [initializing, setInitializing] = useState(true),
    [keyReady, setKeyReady] = useState(false),
    [loggedIn, setLoggedIn] = useState(false);
  const [existing, setExisting] = useState(""),
    [account, setAccount] = useState("我的飞书");
  const [exportDirectory, setExportDirectory] = useState("");
  const [exportCandidates, setExportCandidates] = useState([]);
  const [exportState, setExportState] = useState(null);
  const discovery = useRef(0);
  const discoveryQueue = useRef(Promise.resolve());
  const [recoveryJob, setRecoveryJob] = useState(null);
  const [recoverySummary, setRecoverySummary] = useState(null);
  const [history, setHistory] = useState([]),
    [plan, setPlan] = useState(null);
  const initialization = useRef(null);
  const current = useRef(null),
    catalog = useRef(null),
    exportToken = useRef(null),
    locked = useRef(false);
  const validCount = /^\d+$/.test(existing) && Number(existing) <= 1000;
  const available = validCount ? 1000 - Number(existing) : null;
  const fits =
    validCount &&
    selected.size > 0 &&
    (Boolean(recoveryJob) || selected.size <= available);

  async function invoke(method, payload) {
    const response = await bridge[method](payload);
    if (!response.ok) throw response.error;
    return response.data;
  }
  async function perform(name, action) {
    if (locked.current) return null;
    locked.current = true;
    current.current = name;
    setOperation(name);
    setDone(0);
    setTotal(0);
    setMessage(
      name === "checking"
        ? "正在检查已有导出…"
        : name === "preparing"
          ? "正在核对账号与导出记录…"
          : "正在准备…",
    );
    setError(null);
    try {
      return await action();
    } catch (cause) {
      if (name === "import") {
        setPlan(null);
        setResult(
          cause.progress || {
            success: 0,
            unknown: selected.size,
            remaining: 0,
          },
        );
        setStep(3);
      }
      setError(
        cause?.code
          ? cause
          : {
              code: "BRIDGE_ERROR",
              stage: name,
              message: "应用通信没有完成",
              detail: String(cause),
              recovery: "保留错误信息后重新启动应用。",
            },
      );
      return null;
    } finally {
      locked.current = false;
      current.current = null;
      setOperation(null);
    }
  }
  useEffect(() => {
    let live = true;
    const stop = bridge.onEvent((event) => {
      if (!current.current) return;
      if (event.type === "progress") {
        setMessage(event.message || event.stage);
        if (Number.isFinite(event.current) && event.total > 0) {
          setDone(event.current);
          setTotal(event.total);
        }
      } else if (event.type === "action_required")
        setMessage(
          event.action === "wechat_login"
            ? "正在准备微信，如出现登录窗口请按提示登录…"
            : "等待飞书登录…",
        );
    });
    if (!initialization.current) initialization.current = invoke("initialize");
    initialization.current
      .then((data) => {
        if (!live) return;
        setAccounts(data.accounts);
        setWxid(data.accounts[0]?.wxid || "");
        setEnvironment(data.environment);
        setExportDirectory(data.exportDirectory);
      })
      .catch((cause) => {
        if (live) setError(cause);
      })
      .finally(() => {
        if (live) setInitializing(false);
      });
    return () => {
      live = false;
      stop();
    };
  }, []);
  useEffect(() => {
    if (initializing || !wxid || !exportDirectory || step !== 0) return;
    const request = ++discovery.current;
    setExportCandidates([]);
    discoveryQueue.current = discoveryQueue.current
      .catch(() => {})
      .then(() => {
        if (request !== discovery.current) return;
        return perform("checking", async () => {
          const value = await invoke("findExports", { wxid });
          if (request !== discovery.current) return;
          setExportCandidates(value.exports);
          if (value.accounts) setAccounts(value.accounts);
        });
      });
    return () => {
      discovery.current += 1;
    };
  }, [initializing, wxid, exportDirectory, step]);
  function loadCatalog(value) {
    if (!value) return;
    catalog.current = value.token;
    setItems(value.items);
    setSelected(new Set(value.items.map((item) => item.id)));
    setPlan(null);
    setStep(1);
    if (value.exportState) setExportState(value.exportState);
    if (value.failed && value.exportState?.state !== "partial")
      setError({
        code: "PARTIAL_EXPORT",
        stage: "准备表情",
        message: `有 ${value.failed} 张图片没有准备成功`,
        recovery: "可用图片已显示；原文件与导出报告保留在本机。",
        detail: value.directory,
      });
  }
  async function prepareExport(directory) {
    if (!wxid) {
      setError({
        code: "NO_ACCOUNTS",
        stage: "选择微信账号",
        message: "没有找到本机微信账号",
        recovery: "先在这台 Mac 登录微信，或选择本地图片。",
      });
      return null;
    }
    return perform("preparing", async () => {
      const value = await invoke("prepareExport", { wxid, directory });
      if (value) {
        exportToken.current = value.token;
        setKeyReady(value.keyCached);
        setExportState(value);
        if (value.existing === "complete") loadCatalog(value.catalog);
      }
      return value;
    });
  }
  async function adoptExistingExport(directory) {
    return perform("adopting", async () => {
      const value = await invoke("adoptExistingExport", {
        wxid,
        directory,
        confirmed: true,
      });
      exportToken.current = value.token;
      setKeyReady(value.keyCached);
      setExportState(value);
      if (value.catalog) loadCatalog(value.catalog);
      return value;
    });
  }
  async function useExistingExport(directory) {
    return perform("checking", async () => {
      const value = await invoke("useExistingExport", { wxid, directory });
      loadCatalog(value);
      setExportState(null);
      return value;
    });
  }
  async function chooseExportDirectory() {
    return perform("directory", async () => {
      const value = await invoke("chooseExportDirectory");
      if (value) setExportDirectory(value.directory);
      return value;
    });
  }
  async function quitWeChat() {
    return perform("quit", () => invoke("quitWeChat"));
  }
  async function startKey() {
    return perform("key", async () => {
      const value = await invoke("key", { wxid });
      setKeyReady(Boolean(value.keyCached));
      return value;
    });
  }
  async function startExport() {
    setRecoveryJob(null);
    return perform("export", async () => {
      const value = await invoke("extract", { token: exportToken.current });
      loadCatalog(value);
      return value;
    });
  }
  async function openLocal() {
    setRecoveryJob(null);
    return perform("export", async () => {
      const value = await invoke("openLocal");
      loadCatalog(value);
      return value;
    });
  }
  async function login() {
    setLoggedIn(false);
    return perform("login", async () => {
      const value = await invoke("login", { account });
      setLoggedIn(value.loggedIn);
      return value;
    });
  }
  async function preparePlan() {
    if (!fits) return null;
    return perform("planning", async () => {
      const value = await invoke("plan", {
        catalog: catalog.current,
        selected: Array.from(selected),
        account,
        existing: Number(existing),
      });
      setPlan(value);
      if (!value.fits)
        throw {
          code: "IMPORT_PLAN_INVALID",
          stage: "检查导入计划",
          message: "本次选择暂时不能导入",
          recovery: "检查容量、图片大小与文件校验结果。",
          detail: JSON.stringify({
            invalid: value.invalid,
            oversize: value.oversize,
            unresolved: value.unresolved,
          }),
        };
      return value;
    });
  }
  async function startImport() {
    if (!plan?.fits || !loggedIn) return null;
    return perform("import", async () => {
      const value = await invoke("importSelection", {
        token: plan.token,
        confirmed: true,
      });
      setResult(value);
      setStep(3);
      setPlan(null);
      return value;
    });
  }
  async function cancel() {
    setMessage("正在停止并保留任务记录…");
    return invoke("cancel");
  }
  async function refreshHistory() {
    try {
      const value = await invoke("history");
      setHistory(value);
      return value;
    } catch (cause) {
      setError(cause);
      return [];
    }
  }
  async function prepareRecovery(job) {
    return perform("preparing", async () => {
      const value = await invoke("restoreContext", { job });
      loadCatalog(value);
      setAccount(value.account);
      setExisting("");
      setLoggedIn(false);
      setRecoveryJob(value.recoveryJob);
      setRecoverySummary(value.recoverySummary);
      setStep(2);
      return value;
    });
  }
  async function resume(job) {
    if (!loggedIn || !validCount) return;
    return perform("import", async () => {
      const value = await invoke("resume", {
        job,
        existing: Number(existing),
        confirmed: true,
      });
      setResult(value);
      setStep(3);
      return value;
    });
  }
  function toggle(id) {
    setSelected((previous) => {
      const next = new Set(previous);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
    setPlan(null);
  }
  function reset() {
    setStep(0);
    setRecoveryJob(null);
    setRecoverySummary(null);
    setItems([]);
    setSelected(new Set());
    setDone(0);
    setTotal(0);
    setResult(null);
    setError(null);
    setPlan(null);
    exportToken.current = null;
    catalog.current = null;
  }
  return {
    real: true,
    step,
    setStep,
    items,
    selected,
    setSelected: (next) => {
      setSelected(next);
      setPlan(null);
    },
    operation,
    done,
    total,
    message,
    error,
    setError,
    accounts,
    wxid,
    setWxid,
    environment,
    initializing,
    keyReady,
    loggedIn,
    setLoggedIn,
    existing,
    setExisting: (value) => {
      setExisting(value);
      setPlan(null);
    },
    account,
    setAccount: (value) => {
      setAccount(value);
      setLoggedIn(false);
      setPlan(null);
    },
    validCount,
    available,
    fits,
    result,
    history,
    recoveryJob,
    recoverySummary,
    prepareRecovery,
    plan,
    prepareExport,
    startKey,
    quitWeChat,
    exportDirectory,
    exportCandidates,
    exportState,
    useExistingExport,
    adoptExistingExport,
    chooseExportDirectory,
    startExport,
    openLocal,
    login,
    preparePlan,
    startImport,
    cancel,
    refreshHistory,
    resume,
    toggle,
    reset,
    paused: false,
    uncertain: false,
  };
}
