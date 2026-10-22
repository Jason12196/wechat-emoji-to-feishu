import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  CircleHelp,
  Clock3,
  FolderOpen,
  LockKeyhole,
  LoaderCircle,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Smile,
  X,
} from "lucide-react";
import Modal from "./Modal";
import Sticker from "./Sticker";
import BrandLogo from "./BrandLogo";
import useMigration from "./useMigration";
import useRealMigration from "./useRealMigration";
import Diagnostics from "./Diagnostics";
import { stickers as demoStickers, steps } from "./data";
const useController = window.migration ? useRealMigration : useMigration;

function Button({ children, secondary = false, className = "", ...props }) {
  return (
    <button
      className={`button ${secondary ? "secondary" : "primary"} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
function CheckLine({ checked, onChange, children }) {
  return (
    <label className="check-line">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{children}</span>
    </label>
  );
}
function GuideRow({ number, title, children }) {
  return (
    <div className="guide-row">
      <span className="guide-number">{number}</span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}
function Progress({ value, label }) {
  return (
    <div
      className="progress-track"
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className="progress-fill"
        style={{ transform: `scaleX(${value / 100})` }}
      />
    </div>
  );
}

export default function App() {
  const [scenario, setScenario] = useState("normal");
  const m = useController(scenario);
  const stickers = m.items;
  const account = m.real
    ? m.accounts.find((item) => item.wxid === m.wxid)
    : null;
  const [source, setSource] = useState("wechat");
  const [dialog, setDialog] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [preview, setPreview] = useState(null);
  const heading = useRef(null);
  const keyPreparation = useRef(0);
  const busy = Boolean(m.operation);
  const existingExport = m.real
    ? m.exportCandidates?.find((item) => item.state !== "unbound") ||
      m.exportCandidates?.[0]
    : null;
  const visible = stickers.filter(
    (item) =>
      (!query || item.label.includes(query)) &&
      (filter !== "animated" || item.animated),
  );
  function open(name) {
    setConfirmed(false);
    setDialog(name);
  }
  function close() {
    setDialog(null);
    setConfirmed(false);
    setPreview(null);
  }
  async function begin(nextSource = source, directory) {
    setSource(nextSource);
    if (m.real) {
      if (nextSource === "folder") {
        await m.openLocal();
        return;
      }
      if (!directory && existingExport?.state === "unbound") {
        open("existing-export");
        return;
      }
      const prepared = await m.prepareExport(
        directory || existingExport?.directory,
      );
      if (!prepared || prepared.existing === "complete") return;
      if (prepared.existing === "partial") {
        open("resume-export");
        return;
      }
      if (prepared.keyCached || prepared.canResumeWithoutKey)
        await m.startExport();
      else open("wechat-quit");
    } else if (nextSource === "folder" || scenario === "cached-key")
      m.startExport();
    else open("wechat-quit");
  }
  async function continueExport() {
    if (
      m.keyReady ||
      m.exportState?.canResumeWithoutKey ||
      m.exportState?.snapshot_ready
    ) {
      close();
      await m.startExport();
    } else open("wechat-quit");
  }
  async function prepareWeChat() {
    if (m.real) {
      const result = await m.quitWeChat();
      if (!result?.exited) return;
    }
    const attempt = ++keyPreparation.current;
    open("wechat-login");
    const result = m.real
      ? await m.startKey()
      : await new Promise((resolve) =>
          setTimeout(() => resolve({ keyCached: true }), 1400),
        );
    if (attempt !== keyPreparation.current || !result?.keyCached) return;
    close();
    await m.startExport();
  }
  function dismissLogin() {
    keyPreparation.current += 1;
    if (m.real && m.operation === "key") m.cancel();
    close();
  }
  async function openHistory() {
    if (m.real) await m.refreshHistory();
    open("history");
  }
  useEffect(() => {
    heading.current?.focus();
  }, [m.step]);
  useEffect(() => {
    if (m.error) {
      setConfirmed(false);
      setDialog(m.real ? "real-error" : "export-error");
    }
  }, [m.error]);
  function changeScenario(value) {
    setScenario(value);
    m.reset();
    close();
    setQuery("");
    setFilter("all");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="titlebar-space" />
        <div className="brand">
          <span className="brand-symbol">
            <Smile size={22} strokeWidth={2.2} />
          </span>
          <div>
            表情迁移<span>微信到飞书</span>
          </div>
        </div>
        <div className="sidebar-section-label">这一次迁移</div>
        <nav aria-label="迁移步骤">
          {steps.map((label, index) => (
            <button
              key={label}
              className={`step-link ${m.step === index ? "active" : ""}`}
              disabled={index > m.step || busy || m.step === 3}
              onClick={() => m.setStep(index)}
              aria-current={m.step === index ? "step" : undefined}
            >
              <span className="step-number">
                {m.step > index ? <Check size={13} /> : `0${index + 1}`}
              </span>
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="utility-link" onClick={openHistory}>
            <Clock3 size={17} />
            迁移记录
          </button>
          <button className="utility-link" onClick={() => open("help")}>
            <CircleHelp size={17} />
            使用帮助
          </button>
          <div className="privacy-note">
            <LockKeyhole size={13} />
            <span>本地处理，安心迁移</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          {m.real ? (
            <div className="runtime-status">
              <span className="status-dot" />
              {m.initializing
                ? "正在检测环境…"
                : busy
                  ? m.message || "正在处理…"
                  : "本机运行"}
            </div>
          ) : (
            <div className="prototype-badge">
              <span className="status-dot" />
              交互预览<span className="preview-divider">/</span>
              <select
                aria-label="演示场景"
                value={scenario}
                disabled={busy}
                onChange={(event) => changeScenario(event.target.value)}
              >
                <option value="normal">正常流程</option>
                <option value="cached-key">已有可用密钥</option>
                <option value="export-error">微信副本闪退</option>
                <option value="import-uncertain">导入结果待核对</option>
              </select>
              <ChevronDown size={12} />
            </div>
          )}
        </header>
        <main
          className={`main-content ${m.step === 0 ? "source-content" : ""} ${m.step === 1 ? "library-content" : ""}`}
        >
          <section className="page-enter" key={m.step}>
            {m.step === 0 && (
              <>
                <h1 ref={heading} tabIndex={-1}>
                  把微信表情
                  <br />
                  带到飞书。
                </h1>
                {m.real && (
                  <div className="source-account-picker">
                    <label htmlFor="wechat-account">微信账号</label>
                    <select
                      id="wechat-account"
                      value={m.wxid}
                      disabled={busy || m.initializing}
                      onChange={(event) => m.setWxid(event.target.value)}
                    >
                      {!m.accounts.length && (
                        <option value="">
                          {m.initializing ? "正在检测…" : "未找到本机账号"}
                        </option>
                      )}
                      {m.accounts.map((item) => (
                        <option value={item.wxid} key={item.wxid}>
                          {item.nickname || item.wxid}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="source-layout">
                  <div className="source-options">
                    <button
                      className={`source-card wechat-source ${source === "wechat" ? "chosen" : ""}`}
                      onClick={() => begin("wechat")}
                      disabled={busy || (m.real && m.initializing)}
                      aria-label={
                        existingExport?.state === "complete"
                          ? "挑选已导出的表情"
                          : existingExport?.state === "partial"
                            ? "继续导出微信表情"
                            : "从微信收藏导出"
                      }
                    >
                      <div className="wechat-card-top">
                        <BrandLogo brand="wechat" />
                        <span className="wechat-card-check">
                          {source === "wechat" ? (
                            <Check size={17} />
                          ) : (
                            <ArrowUpRight size={18} />
                          )}
                        </span>
                      </div>
                      <div className="wechat-card-title">
                        {existingExport?.state === "complete"
                          ? "挑选已导出的表情"
                          : existingExport?.state === "partial"
                            ? "继续导出微信表情"
                            : "从微信收藏导出"}
                      </div>
                      <div className="wechat-card-account">
                        <span>
                          {m.real
                            ? account?.nickname ||
                              account?.wxid ||
                              "先登录本机微信，或使用本地图片"
                            : "我的微信 · 本机账号（演示）"}
                        </span>
                        {(m.real
                          ? account?.key_cached
                          : scenario === "cached-key") && (
                          <span>密钥可复用</span>
                        )}
                      </div>
                    </button>
                    {existingExport && (
                      <div className="export-reuse-note" role="status">
                        <Check size={14} aria-hidden="true" />
                        <span>
                          {existingExport.state === "complete"
                            ? `已导出 ${existingExport.ready} 张，直接挑选`
                            : existingExport.state === "unbound"
                              ? `发现 ${existingExport.ready} 张已有图片`
                              : existingExport.expected
                                ? `已完成 ${existingExport.ready} / ${existingExport.expected} 张，继续未完成部分`
                                : "发现未完成的导出，可继续上次任务"}
                        </span>
                      </div>
                    )}
                    <div className="export-directory">
                      <FolderOpen size={15} aria-hidden="true" />
                      <span className="export-directory-label">导出到</span>
                      <span
                        className="export-directory-path"
                        title={m.real ? m.exportDirectory : "Downloads"}
                      >
                        {m.real && m.exportDirectory
                          ? m.exportDirectory
                              .split("/")
                              .filter(Boolean)
                              .at(-1) || m.exportDirectory
                          : "Downloads"}
                      </span>
                      <button
                        className="text-button"
                        disabled={busy || (m.real && m.initializing)}
                        onClick={
                          m.real
                            ? m.chooseExportDirectory
                            : () => open("export-directory")
                        }
                      >
                        更改
                      </button>
                    </div>
                    <button
                      className={`local-source ${source === "folder" ? "chosen" : ""}`}
                      onClick={() => begin("folder")}
                      disabled={busy}
                      aria-label="使用本地图片"
                    >
                      <FolderOpen size={15} />
                      <span>使用本地图片</span>
                      <ArrowUpRight size={13} />
                    </button>
                  </div>
                  <div className="sticker-composition" aria-hidden="true">
                    {[0, 1, 2, 3].map((id, index) => (
                      <div
                        className={`floating-sticker sticker-${index}`}
                        key={id}
                      >
                        <Sticker item={demoStickers[id]} />
                      </div>
                    ))}
                  </div>
                </div>
                {m.operation === "export" && (
                  <div className="export-progress">
                    <div>
                      <span>
                        {m.real
                          ? m.message || "正在处理…"
                          : `正在${source === "wechat" ? "导出表情" : "读取演示图片"}…`}
                      </span>
                      <span>
                        {m.real && !m.total
                          ? "处理中"
                          : `${m.done} / ${m.real ? m.total : 24}`}
                      </span>
                    </div>
                    <Progress
                      value={
                        m.real
                          ? m.total
                            ? (m.done / m.total) * 100
                            : 0
                          : (m.done / 24) * 100
                      }
                      label="导出演示进度"
                    />
                    <p>原图和动图都会保留，这个过程不会修改微信数据。</p>
                  </div>
                )}
              </>
            )}
            {m.step === 1 && (
              <>
                <div className="page-heading">
                  <div>
                    <div className="eyebrow">
                      {m.real ? "本机图片" : "微信收藏 · 演示图片"}
                    </div>
                    <h1 ref={heading} tabIndex={-1}>
                      每一张，都很有你。
                    </h1>
                    <p className="intro">挑选想带走的表情，原图会一直保留。</p>
                  </div>
                  <span className="count-display">
                    {stickers.length}
                    <span>张表情</span>
                  </span>
                </div>
                {m.real && m.exportState?.state === "partial" && (
                  <div className="partial-export-notice">
                    <span>
                      已保留 {m.exportState.ready} 张，还有{" "}
                      {m.exportState.remaining} 张待完成。
                    </span>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => begin("wechat", m.exportState.directory)}
                    >
                      继续导出 <ArrowRight size={14} />
                    </button>
                  </div>
                )}
                <div className="library-toolbar">
                  <div className="segmented" aria-label="表情类型">
                    <button
                      className={filter === "all" ? "selected" : ""}
                      onClick={() => setFilter("all")}
                    >
                      全部 <span>{stickers.length}</span>
                    </button>
                    <button
                      className={filter === "animated" ? "selected" : ""}
                      onClick={() => setFilter("animated")}
                    >
                      动图{" "}
                      <span>
                        {stickers.filter((item) => item.animated).length}
                      </span>
                    </button>
                  </div>
                  <div className="library-actions">
                    <label className="search-field">
                      <Search size={15} />
                      <input
                        aria-label="搜索表情"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="搜索表情"
                      />
                      {query && (
                        <button
                          aria-label="清除搜索"
                          onClick={() => setQuery("")}
                        >
                          <X size={13} />
                        </button>
                      )}
                    </label>
                    <button
                      className="text-button"
                      onClick={() =>
                        m.setSelected(
                          m.selected.size === stickers.length
                            ? new Set()
                            : new Set(stickers.map((item) => item.id)),
                        )
                      }
                    >
                      {m.selected.size === stickers.length
                        ? "取消全选"
                        : "全选"}
                    </button>
                  </div>
                </div>
                {visible.length ? (
                  <div className="sticker-grid">
                    {visible.map((item, index) => (
                      <div
                        className={`sticker-tile ${m.selected.has(item.id) ? "is-selected" : ""}`}
                        style={{ "--index": Math.min(index, 11) }}
                        key={item.id}
                      >
                        <button
                          className="sticker-select"
                          aria-label={`选择${item.label}`}
                          aria-pressed={m.selected.has(item.id)}
                          onClick={() => m.toggle(item.id)}
                        >
                          <span
                            className={`selection-mark ${m.selected.has(item.id) ? "checked" : ""}`}
                          >
                            {m.selected.has(item.id) && (
                              <Check size={12} strokeWidth={3} />
                            )}
                          </span>
                          <Sticker item={item} />
                        </button>
                        <div className="tile-caption">
                          <span>
                            {item.format || (item.animated ? "GIF" : "PNG")}
                          </span>
                          <button
                            aria-label={`预览${item.label}`}
                            className="tile-preview"
                            onClick={() => {
                              setPreview(item);
                              open("preview");
                            }}
                          >
                            <MoreHorizontal size={16} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <Search size={28} />
                    <h3>没有找到这张表情</h3>
                    <p>试试其他关键词，或查看全部表情。</p>
                    <Button
                      secondary
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                      }}
                    >
                      查看全部
                    </Button>
                  </div>
                )}
              </>
            )}
            {m.step === 2 && (
              <>
                {m.operation === "import" ? (
                  <div className="transfer-state">
                    <div
                      className={`transfer-orbit ${m.paused ? "is-paused" : ""}`}
                    >
                      <div className="orbit-icon">
                        <Smile size={39} />
                      </div>
                      <span className="orbit-dot dot-one" />
                      <span className="orbit-dot dot-two" />
                      <span className="orbit-dot dot-three" />
                    </div>
                    <div className="eyebrow">
                      {m.paused ? "进度已保留" : "正在添加到飞书"}
                    </div>
                    <h1 ref={heading} tabIndex={-1}>
                      {m.paused
                        ? "停一下，也没关系。"
                        : "熟悉的表情，正在就位。"}
                    </h1>
                    <p className="intro">
                      {m.paused
                        ? "已提交但未确认的项目需要核对，避免重复添加。"
                        : "请保持浏览器窗口打开，不用逐张操作。"}
                    </p>
                    <div className="transfer-progress">
                      <div>
                        <span>{m.paused ? "已暂停" : "导入中"}</span>
                        <strong>
                          {m.done}
                          <span> / {m.total} 张</span>
                        </strong>
                      </div>
                      <Progress
                        value={m.total ? (m.done / m.total) * 100 : 0}
                        label="导入演示进度"
                      />
                    </div>
                    {m.paused ? (
                      <div className="center-actions">
                        <Button secondary onClick={m.endImport}>
                          结束并查看记录
                        </Button>
                        <Button onClick={() => open("recover")}>
                          核对后继续
                          <ArrowRight size={16} />
                        </Button>
                      </div>
                    ) : (
                      <Button secondary onClick={m.real ? m.cancel : m.pause}>
                        <Pause size={15} />
                        {m.real ? "停止并保留记录" : "暂停导入"}
                      </Button>
                    )}
                    <p className="tiny-note">
                      {m.real
                        ? "已提交的表情请以飞书面板和任务记录为准。"
                        : "这是模拟进度，不会向真实飞书账号添加表情。"}
                    </p>
                  </div>
                ) : (
                  <>
                    <h1 ref={heading} tabIndex={-1}>
                      准备好，就出发。
                    </h1>
                    <p className="intro">
                      表情将添加到你的飞书个人面板，不会发送聊天消息。
                    </p>
                    <div className="import-layout">
                      <div className="import-panel">
                        <div className="section-heading">
                          <span className="section-number">01</span>
                          <h3>接收表情的账号</h3>
                        </div>
                        {m.real && (
                          <label className="feishu-profile-label">
                            本地账号名称
                            <input
                              value={m.account}
                              onChange={(event) =>
                                m.setAccount(event.target.value)
                              }
                              maxLength={80}
                              placeholder="例如：我的飞书"
                            />
                          </label>
                        )}
                        <div className="login-row">
                          <span className="avatar large-avatar">
                            <BrandLogo brand="feishu" />
                          </span>
                          <div>
                            <strong>
                              {m.loggedIn
                                ? m.real
                                  ? m.account
                                  : "我的飞书 · 演示"
                                : "还没有登录飞书"}
                            </strong>
                            <p>
                              {m.loggedIn
                                ? "已在独立窗口核对接收账号"
                                : "将在独立浏览器窗口中登录"}
                            </p>
                          </div>
                          <button
                            className="text-button feishu-login-button"
                            onClick={() => open("feishu-intro")}
                          >
                            {m.loggedIn ? "切换账号" : "登录飞书"}
                            <ArrowUpRight size={14} />
                          </button>
                        </div>
                        <div className="section-heading capacity-heading">
                          <span className="section-number">02</span>
                          <h3>确认可用空间</h3>
                        </div>
                        <label
                          className="existing-label"
                          htmlFor="existing-count"
                        >
                          飞书目前已有多少张个人表情？
                        </label>
                        <div className="number-field">
                          <input
                            id="existing-count"
                            type="number"
                            min="0"
                            max="1000"
                            value={m.existing}
                            onChange={(event) =>
                              m.setExisting(event.target.value)
                            }
                            aria-describedby="capacity-feedback"
                          />
                          <span>/ 1,000 张</span>
                        </div>
                        <p className="field-hint">
                          请在飞书表情面板查看，目前需要手动填写。
                        </p>
                        <div className="capacity-visual">
                          <div
                            style={{
                              transform: `scaleX(${m.validCount ? Number(m.existing) / 1000 : 0})`,
                            }}
                          />
                          <span
                            style={{
                              left: `${m.validCount ? Math.min(Number(m.existing) / 10, 98) : 0}%`,
                              width: `${Math.min(m.selected.size / 10, 100)}%`,
                            }}
                          />
                        </div>
                        <p
                          id="capacity-feedback"
                          className={`capacity-feedback ${!m.fits ? "capacity-invalid" : ""}`}
                          role="status"
                        >
                          {m.real && m.recoveryJob
                            ? "恢复会跳过已确认项目；待核对项会阻止自动重传。请填写最新已有数量。"
                            : !m.validCount
                              ? "请填写 0 到 1000 之间的整数。"
                              : m.fits
                                ? `还可添加 ${m.available} 张，本次 ${m.selected.size} 张放得下。`
                                : `空间还差 ${Math.max(0, m.selected.size - m.available)} 张，请返回减少选择或先整理飞书表情。`}
                        </p>
                      </div>
                      <div className="selection-summary">
                        <div className="summary-stack">
                          {Array.from(m.selected)
                            .slice(0, 3)
                            .map((id) => (
                              <div key={id}>
                                <Sticker item={stickers[id]} />
                              </div>
                            ))}
                        </div>
                        <h2>
                          {m.selected.size}
                          <span> 张表情</span>
                        </h2>
                        <p>准备添加到飞书个人面板</p>
                        <div className="summary-details">
                          <div>
                            <span>原图与动图</span>
                            <span>已保留</span>
                          </div>
                          <div>
                            <span>既有飞书表情</span>
                            <span>不会删除</span>
                          </div>
                          <div>
                            <span>聊天消息</span>
                            <span>不会发送</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
            {m.step === 3 && m.result && (
              <div className="result-state">
                <span className="success-symbol">
                  <Check size={35} strokeWidth={2} />
                </span>
                <div className="eyebrow">
                  {m.result.remaining || m.result.unknown
                    ? "本次进度已保存"
                    : "迁移完成"}
                </div>
                <h1 ref={heading} tabIndex={-1}>
                  {m.result.remaining || m.result.unknown
                    ? "下次，从这里接着来。"
                    : "换个地方，继续表达。"}
                </h1>
                <p className="intro">
                  {m.result.remaining || m.result.unknown
                    ? "已完成的项目不会丢失，待核对项也已单独记录。"
                    : "喜欢的表情已经准备好了。下次聊天，试试它们。"}
                </p>
                <div className="result-stats">
                  <div>
                    <strong>{m.result.success}</strong>
                    <span>已确认添加</span>
                  </div>
                  <div>
                    <strong>{m.result.unknown}</strong>
                    <span>需要核对</span>
                  </div>
                  <div>
                    <strong>{m.result.remaining}</strong>
                    <span>尚未提交</span>
                  </div>
                </div>
                {m.real && m.result.diagnostic && (
                  <div className="result-diagnostic">
                    <Diagnostics error={m.result.diagnostic} />
                  </div>
                )}
                <div className="center-actions">
                  <Button secondary onClick={openHistory}>
                    <Clock3 size={16} />
                    查看本次记录
                  </Button>
                  <Button
                    onClick={() => {
                      m.reset();
                      setQuery("");
                      setFilter("all");
                    }}
                  >
                    再迁移一批
                    <Plus size={16} />
                  </Button>
                </div>
                <p className="tiny-note">
                  {m.real
                    ? `任务 ${m.result.taskId || ""} · 记录已保存在本机`
                    : "交互原型 · 本次没有操作真实微信或飞书"}
                </p>
              </div>
            )}
          </section>
        </main>
        {(m.step === 1 || m.step === 2) && (
          <footer className="bottom-bar">
            <div className="bottom-caption">
              {m.step === 1 ? (
                <>
                  <strong>{m.selected.size}</strong> 张已选择
                  <span className="bottom-caption-extra">
                    原图与动图均已保留
                  </span>
                </>
              ) : (
                <>
                  <span className="demo-dot" />
                  {m.real
                    ? "本机处理 · 仅导入个人自定义表情"
                    : "演示数据，不会操作真实账号"}
                </>
              )}
            </div>
            <div className="bottom-actions">
              {m.step === 1 && (
                <Button
                  onClick={() => m.setStep(2)}
                  disabled={!m.selected.size}
                >
                  准备导入
                  <ArrowRight size={16} />
                </Button>
              )}
              {m.step === 2 && !busy && (
                <>
                  <button className="text-button" onClick={() => m.setStep(1)}>
                    <ChevronLeft size={15} />
                    调整选择
                  </button>
                  <Button
                    onClick={
                      m.real && m.recoveryJob
                        ? () => m.resume(m.recoveryJob)
                        : m.real && !m.plan
                          ? m.preparePlan
                          : m.startImport
                    }
                    disabled={
                      !m.fits ||
                      (m.real
                        ? Boolean(m.plan || m.recoveryJob) && !m.loggedIn
                        : !m.loggedIn)
                    }
                  >
                    {m.real && m.recoveryJob
                      ? "检查并恢复未提交项目"
                      : m.real && !m.plan
                        ? "检查导入计划"
                        : `开始导入 ${m.selected.size} 张`}
                    <ArrowRight size={16} />
                  </Button>
                </>
              )}
            </div>
          </footer>
        )}
      </div>

      {dialog === "real-error" && m.error && (
        <Modal
          title={m.error.message}
          description={m.error.recovery || "请保留诊断信息后检查。"}
          onClose={() => {
            m.setError(null);
            close();
          }}
          footer={
            <Button
              secondary
              onClick={() => {
                m.setError(null);
                close();
              }}
            >
              知道了
            </Button>
          }
        >
          <Diagnostics error={m.error} />
        </Modal>
      )}
      {dialog === "resume-export" && m.exportState && (
        <Modal
          title="继续上次导出"
          description={
            m.exportState.expected
              ? `已完成 ${m.exportState.ready} / ${m.exportState.expected} 张，只处理未完成项目。`
              : "将继续上次任务，已保存的图片会保留。"
          }
          onClose={close}
          footer={
            <Button disabled={busy} onClick={continueExport}>
              继续导出 <ArrowRight size={16} />
            </Button>
          }
        >
          <p className="modal-note">
            {m.exportState.canResumeWithoutKey || m.exportState.snapshot_ready
              ? "已保存导出清单，无需重新打开微信。"
              : m.keyReady
                ? "将复用已有密钥，不再重新获取。"
                : "如果需要准备微信，会在下一步提示。"}
          </p>
        </Modal>
      )}
      {dialog === "existing-export" && existingExport && (
        <Modal
          title={existingExport.legacy_raw ? "继续旧版导出" : "发现已有导出"}
          description={
            existingExport.legacy_raw
              ? `已保存 ${existingExport.raw_count} 个原始文件，将在原目录继续并复用已有文件。`
              : `这里已有 ${existingExport.ready} 张图片，可以直接挑选。`
          }
          onClose={busy ? undefined : close}
          footer={
            <Button
              disabled={busy}
              onClick={async () => {
                if (existingExport.legacy_raw) {
                  const value = await m.adoptExistingExport(
                    existingExport.directory,
                  );
                  if (!value) return;
                  close();
                  if (value.existing === "complete") return;
                  if (value.keyCached || value.canResumeWithoutKey)
                    await m.startExport();
                  else open("wechat-quit");
                } else {
                  const value = await m.useExistingExport(
                    existingExport.directory,
                  );
                  if (value) close();
                }
              }}
            >
              {existingExport.legacy_raw ? "确认账号并继续" : "使用已有图片"}
              <ArrowRight size={16} />
            </Button>
          }
        >
          <p className="modal-note">
            这份旧记录未保存微信账号，请确认它属于当前选择的微信账号：
            {account?.nickname || m.wxid}。
          </p>
          {existingExport.legacy_raw && (
            <p className="modal-note">
              旧版没有保留完整清单，继续时会先读取清单，再检查并补齐缺失图片。
            </p>
          )}
        </Modal>
      )}
      {dialog === "export-directory" && (
        <Modal
          title="选择导出位置"
          description="应用中会打开文件夹选择窗口，默认保存到 Downloads。"
          onClose={close}
          footer={<Button onClick={close}>知道了</Button>}
        >
          <p className="modal-note">当前是交互预览，不会更改本机文件。</p>
        </Modal>
      )}
      {dialog === "wechat-quit" && (
        <Modal
          title="先让微信休息一下"
          description="首次读取表情，需要先获取这台 Mac 的微信密钥。"
          onClose={busy ? undefined : close}
          footer={
            <Button disabled={busy} onClick={prepareWeChat}>
              {busy ? "正在等待微信退出…" : "退出微信并继续"}
              <ArrowRight size={16} />
            </Button>
          }
        >
          <div className="modal-app-icon wechat-icon">
            <BrandLogo brand="wechat" />
          </div>
          <GuideRow number="1" title="确认后自动退出微信">
            请先完成聊天、通话或文件传输。退出成功后会自动继续。
          </GuideRow>
          <GuideRow number="2" title="接下来会打开一个微信副本">
            如出现登录窗口，按提示登录即可。准备好后会自动开始读取。
          </GuideRow>
          {!m.real && (
            <p className="modal-note">交互预览：不会关闭或启动真实微信。</p>
          )}
        </Modal>
      )}
      {dialog === "wechat-login" && (
        <Modal
          title="正在准备微信"
          description="准备完成后会自动读取表情，无需额外确认。"
          onClose={dismissLogin}
          footer={
            <Button secondary onClick={dismissLogin}>
              取消
            </Button>
          }
        >
          <div className="wechat-preparing" role="status" aria-live="polite">
            <div className="wechat-preparing-icon">
              <BrandLogo brand="wechat" />
            </div>
            <LoaderCircle
              className="preparing-spinner"
              size={25}
              aria-hidden="true"
            />
            <strong>请稍等，正在准备读取表情…</strong>
            <p>如果出现微信登录窗口，按提示完成登录即可。</p>
          </div>
          <p className="modal-note">
            微信副本可能会自动关闭，是否成功以这里的任务状态为准。
          </p>
          {!m.real && (
            <p className="modal-note">交互预览：不会操作真实微信。</p>
          )}
        </Modal>
      )}
      {dialog === "export-error" && (
        <Modal
          title="微信没有准备好"
          description="尚未获取到读取权限，本次没有完成导出。"
          onClose={() => {
            m.setError(null);
            close();
          }}
          footer={
            <>
              <Button
                secondary
                onClick={() => {
                  m.setError(null);
                  close();
                }}
              >
                稍后再试
              </Button>
              <Button
                onClick={() => {
                  m.setError(null);
                  open("wechat-quit");
                }}
              >
                <RefreshCw size={15} />
                重新准备微信
              </Button>
            </>
          }
        >
          <div className="notice-block">
            <strong>先检查这三件事</strong>
            <p>
              原微信是否已完全退出；副本是否完成登录；诊断中是否有启动或密钥错误。
            </p>
            <p>如果仍然闪退，请保留终端错误与微信版本，不要反复扫码登录。</p>
          </div>
        </Modal>
      )}
      {dialog === "feishu-intro" && (
        <Modal
          className="feishu-dialog"
          title="去飞书，确认接收账号"
          description="接下来会打开独立的 Chromium 浏览器窗口。"
          onClose={close}
          footer={
            <Button
              className="feishu-primary"
              onClick={() => {
                open("feishu-login");
                if (m.real) m.login();
              }}
            >
              打开浏览器登录
              <ArrowUpRight size={16} />
            </Button>
          }
        >
          <div className="modal-app-icon feishu-icon">
            <BrandLogo brand="feishu" />
          </div>
          <GuideRow number="1" title="在新窗口登录飞书">
            首次使用会先下载浏览器，已有登录状态时可以复用。
          </GuideRow>
          <GuideRow number="2" title="核对真正接收表情的账号">
            这里添加的是个人自定义表情，不需要管理员权限。
          </GuideRow>
          {!m.real && (
            <p className="modal-note">
              交互预览：不会启动浏览器或登录真实账号。
            </p>
          )}
        </Modal>
      )}
      {dialog === "feishu-login" && (
        <Modal
          className="feishu-dialog"
          title="登录后，再确认一次"
          description="请在独立浏览器窗口登录你要接收表情的飞书账号。"
          onClose={close}
          footer={
            <Button
              disabled={!confirmed || (m.real && !m.loggedIn)}
              onClick={() => {
                if (!m.real) m.setLoggedIn(true);
                close();
              }}
            >
              <Check size={15} />
              已登录，继续
            </Button>
          }
        >
          <div className="login-preview">
            <BrandLogo brand="feishu" />
            <span>飞书个人账号登录</span>
            <span className="small-tag">
              {m.real
                ? m.loggedIn
                  ? "登录已完成"
                  : "等待浏览器登录…"
                : "浏览器窗口 · 演示"}
            </span>
          </div>
          <div className="notice-block">
            <strong>账号名字不代表登录身份</strong>
            <p>请以浏览器里显示的实际账号为准。工具不会自动替你选择账号。</p>
          </div>
          <CheckLine checked={confirmed} onChange={setConfirmed}>
            我已核对，这是要接收表情的账号
          </CheckLine>
        </Modal>
      )}
      {dialog === "recover" && (
        <Modal
          title="先核对，再接着来"
          description="暂停前提交的最后一张，可能已经添加成功。"
          onClose={close}
          footer={
            <Button
              disabled={!confirmed}
              onClick={() => {
                close();
                m.resume();
              }}
            >
              继续未提交的表情
              <Play size={15} />
            </Button>
          }
        >
          <div className="recovery-item">
            <Sticker item={stickers[Array.from(m.selected)[m.done] ?? 0]} />
            <div>
              <strong>1 张结果待核对</strong>
              <p>到飞书个人表情面板检查是否已添加。</p>
            </div>
          </div>
          <p className="field-hint">
            这里模拟“已确认添加”的恢复路径，不会重新提交这张表情。
          </p>
          <CheckLine checked={confirmed} onChange={setConfirmed}>
            已在飞书核对，该项已经添加
          </CheckLine>
        </Modal>
      )}
      {dialog === "preview" && preview && (
        <Modal
          title={preview.label}
          description={
            m.real
              ? "本机图片预览，尚未上传。"
              : "示例表情预览，不含你的真实微信数据。"
          }
          onClose={close}
          footer={
            <Button secondary onClick={close}>
              完成
            </Button>
          }
        >
          <div className="sticker-preview">
            <Sticker item={preview} large />
          </div>
          <div className="preview-meta">
            <span>
              {preview.animated
                ? m.real
                  ? "动图"
                  : "GIF · 动图示例"
                : "静态图片"}
            </span>
            <span>{preview.size}</span>
          </div>
        </Modal>
      )}
      {dialog === "history" && (
        <Modal
          title="迁移记录"
          description={
            m.real
              ? "本机保存的任务与导入结果。中断任务请先核对再恢复。"
              : "演示记录只保留在当前会话中，不读取本机任务数据。"
          }
          onClose={close}
          footer={
            <Button secondary onClick={close}>
              完成
            </Button>
          }
        >
          {m.real ? (
            <div className="real-history">
              {!m.history.length ? (
                <p>还没有导入记录。</p>
              ) : (
                m.history.map((job) => (
                  <article key={job.id}>
                    <strong>
                      {job.account} · {job.count} 张
                    </strong>
                    <p>
                      {new Date(job.createdAt).toLocaleString()} ·{" "}
                      {{
                        planned: "已检查计划，尚未导入",
                        running: "导入中",
                        partial: "部分完成",
                        interrupted: "已中断",
                        complete: "已完成",
                      }[job.state] || job.state}
                    </p>
                    <p>
                      已确认 {job.result?.success ?? "待查询"} · 待核对{" "}
                      {job.result?.unknown ?? "待查询"}
                    </p>
                    {job.recoverable && (
                      <Button
                        secondary
                        disabled={busy}
                        onClick={() => {
                          close();
                          m.prepareRecovery(job.id);
                        }}
                      >
                        准备恢复此任务
                      </Button>
                    )}
                    <small>
                      {job.recoverable
                        ? "恢复前需重新核对登录账号与已有数量。"
                        : "本机记录已保存。"}
                    </small>
                  </article>
                ))
              )}
            </div>
          ) : m.result ? (
            <div className="history-card">
              <div>
                <span className="history-icon">
                  <Smile size={21} />
                </span>
                <div>
                  <strong>微信 → 飞书个人表情</strong>
                  <p>本次演示迁移</p>
                </div>
              </div>
              <dl>
                <div>
                  <dt>已确认添加</dt>
                  <dd>{m.result.success} 张</dd>
                </div>
                <div>
                  <dt>结果待核对</dt>
                  <dd>{m.result.unknown} 张</dd>
                </div>
                <div>
                  <dt>尚未提交</dt>
                  <dd>{m.result.remaining} 张</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="empty-state compact">
              <Clock3 size={30} />
              <h3>还没有迁移记录</h3>
              <p>完成一次迁移后，结果会出现在这里。</p>
            </div>
          )}
        </Modal>
      )}
      {dialog === "help" && (
        <Modal
          title="迁移前，你可能想知道"
          description="先导出到本机，再决定添加到哪个飞书账号。"
          onClose={close}
          footer={
            <Button secondary onClick={close}>
              知道了
            </Button>
          }
        >
          <GuideRow number="1" title="微信只在需要取密钥时重新登录">
            已有有效密钥可直接复用，无需每次退出微信。
          </GuideRow>
          <GuideRow number="2" title="飞书会在独立浏览器中登录">
            确认实际账号后再导入，个人表情按 1,000 张预检查。
          </GuideRow>
          <GuideRow number="3" title="原图不会丢，已有表情不会被删">
            中断后先看记录，再核对不确定项，避免重复添加。
          </GuideRow>
        </Modal>
      )}
    </div>
  );
}
