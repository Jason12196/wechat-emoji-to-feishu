import { useState } from "react";
import { Copy, FolderOpen } from "lucide-react";

export default function Diagnostics({ error }) {
  const [copied, setCopied] = useState(false),
    [failure, setFailure] = useState("");
  if (!error) return null;
  async function copy() {
    try {
      if (error.id && window.migration) {
        const result = await window.migration.diagnostic({
          id: error.id,
          copy: true,
        });
        if (!result.ok) throw new Error(result.error.message);
      } else
        await navigator.clipboard.writeText(
          JSON.stringify(
            { code: error.code, stage: error.stage, message: error.message },
            null,
            2,
          ),
        );
      setCopied(true);
    } catch (cause) {
      setFailure(cause.message);
    }
  }
  return (
    <details className="diagnostics">
      <summary>查看诊断详情</summary>
      <dl>
        <div>
          <dt>失败步骤</dt>
          <dd>{error.stage || "未知步骤"}</dd>
        </div>
        <div>
          <dt>错误码</dt>
          <dd>{error.code || "UNKNOWN"}</dd>
        </div>
        {error.taskId && (
          <div>
            <dt>任务编号</dt>
            <dd>{error.taskId}</dd>
          </div>
        )}
        {error.id && (
          <div>
            <dt>诊断编号</dt>
            <dd>{error.id}</dd>
          </div>
        )}
        {error.time && (
          <div>
            <dt>发生时间</dt>
            <dd>{new Date(error.time).toLocaleString()}</dd>
          </div>
        )}
        {error.exitCode !== undefined && (
          <div>
            <dt>退出码</dt>
            <dd>
              {error.exitCode === null ? "进程被信号终止" : error.exitCode}
            </dd>
          </div>
        )}
        {error.signal && (
          <div>
            <dt>终止信号</dt>
            <dd>{error.signal}</dd>
          </div>
        )}
        {error.lastEvent?.message && (
          <div>
            <dt>最后进度</dt>
            <dd>{error.lastEvent.message}</dd>
          </div>
        )}
      </dl>
      {error.detail && <pre>{error.detail}</pre>}
      {error.stderr && <pre>{error.stderr}</pre>}
      {error.diagnosticWriteError && (
        <p role="alert">诊断文件无法保存：{error.diagnosticWriteError}</p>
      )}
      {error.engineDiagnostic && (
        <p className="diagnostic-path">引擎诊断：{error.engineDiagnostic}</p>
      )}
      {error.diagnostic && (
        <p className="diagnostic-path">本机记录：{error.diagnostic}</p>
      )}
      <div className="diagnostic-actions">
        <button className="text-button" onClick={copy}>
          <Copy size={14} />
          {copied ? "摘要已复制" : "复制脱敏摘要"}
        </button>
        {window.migration && (
          <button
            className="text-button"
            onClick={async () => {
              const value = await window.migration.openDiagnostics();
              if (!value.ok) setFailure(value.error.message);
            }}
          >
            <FolderOpen size={14} />
            打开诊断目录
          </button>
        )}
      </div>
      {failure && <p role="alert">{failure}</p>}
    </details>
  );
}
