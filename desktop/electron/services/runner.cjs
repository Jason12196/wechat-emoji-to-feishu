const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { failure, redact } = require("./errors.cjs");

class CliRunner {
  constructor({
    cli,
    home,
    emit = () => {},
    timeout = 60 * 60 * 1000,
    env = {},
  }) {
    this.cli = cli;
    this.home = home;
    this.emit = emit;
    this.timeout = timeout;
    this.env = env;
    this.active = null;
    this.problems = new Map();
    this.diagnostics = path.join(home, "diagnostics");
    fs.mkdirSync(this.diagnostics, { recursive: true, mode: 0o700 });
  }
  record(error, context = {}) {
    const value = error?.code
      ? error
      : failure(
          "ENGINE_ERROR",
          context.stage || "应用",
          error?.message || error,
        );
    if (context.exitCode !== undefined) value.exitCode = context.exitCode;
    if (context.signal) value.signal = context.signal;
    if (context.operation) value.operation = context.operation;
    if (context.stderr) value.stderr = redact(context.stderr);
    if (context.events?.length) value.lastEvent = context.events.at(-1);
    const report = {
      ...value,
      ...context,
      platform: process.platform,
      arch: process.arch,
    };
    const file = path.join(this.diagnostics, `${value.id}.json`);
    try {
      fs.writeFileSync(file, JSON.stringify(report, null, 2), { mode: 0o600 });
      value.diagnostic = file;
    } catch (cause) {
      value.diagnosticWriteError = redact(cause.message);
    }
    this.problems.set(value.id, value);
    return value;
  }
  cancel() {
    if (!this.active) return false;
    this.active.cancelled = true;
    this.active.stop();
    return true;
  }
  run(args, stage, timeout = this.timeout, onStarted = () => {}) {
    if (this.active)
      return Promise.reject(this.record(failure("OPERATION_BUSY", stage)));
    if (!this.cli || !fs.existsSync(this.cli))
      return Promise.reject(this.record(failure("CLI_NOT_FOUND", stage)));
    return new Promise((resolve, reject) => {
      const operation = randomUUID();
      const context = {
        operation,
        stage,
        startedAt: new Date().toISOString(),
        events: [],
        stderr: "",
      };
      let terminal = null,
        protocolError = null,
        spawnError = null,
        timedOut = false,
        settled = false;
      const child = spawn(this.cli, ["--json", "--home", this.home, ...args], {
        stdio: ["ignore", "pipe", "pipe"],
        env: { ...process.env, ...this.env },
        shell: false,
      });
      const active = { child, operation, stage, cancelled: false };
      this.active = active;
      let killTimer;
      active.stop = () => {
        child.kill("SIGINT");
        if (!killTimer)
          killTimer = setTimeout(() => child.kill("SIGKILL"), 10000);
      };
      const limit = setTimeout(() => {
        timedOut = true;
        active.stop();
      }, timeout);
      child.once("error", (error) => {
        spawnError = error;
      });
      const lines = readline.createInterface({ input: child.stdout });
      lines.on("line", (line) => {
        if (!line.trim()) return;
        try {
          const event = JSON.parse(line);
          if (
            event.protocol_version !== 1 ||
            ![
              "started",
              "progress",
              "action_required",
              "result",
              "error",
            ].includes(event.type)
          )
            throw new Error("Unknown protocol event");
          if (terminal || (context.taskId && event.task_id !== context.taskId))
            throw new Error("Unexpected event sequence");
          if (!/^[a-f0-9-]{36}$/.test(event.task_id || ""))
            throw new Error("Missing task identifier");
          if (!context.taskId) {
            if (event.type !== "started")
              throw new Error("Task must start with a started event");
            onStarted(event.task_id);
          }
          context.taskId = event.task_id;
          context.events.push({
            type: event.type,
            time: event.time,
            code: event.code,
            current: event.current,
            total: event.total,
            message: redact(event.message || event.result?.message),
          });
          if (context.events.length > 150) context.events.shift();
          if (event.type === "result" || event.type === "error")
            terminal = event;
          this.emit({
            operation,
            stage,
            type: event.type,
            task_id: event.task_id,
            time: event.time,
            code: event.code,
            action: event.action,
            status: event.status,
            current: event.current,
            total: event.total,
            message: redact(event.message || event.result?.message),
          });
        } catch (error) {
          protocolError = failure("CLI_PROTOCOL_ERROR", stage, error.message, {
            taskId: context.taskId,
          });
          active.stop();
        }
      });
      child.stderr.on("data", (chunk) => {
        context.stderr = (context.stderr + chunk.toString()).slice(-24000);
      });
      child.once("close", (exitCode, signal) => {
        if (settled) return;
        settled = true;
        clearTimeout(limit);
        clearTimeout(killTimer);
        lines.close();
        if (this.active === active) this.active = null;
        context.stderr = redact(context.stderr);
        Object.assign(context, {
          exitCode,
          signal,
          completedAt: new Date().toISOString(),
        });
        let error = protocolError;
        if (!error && timedOut)
          error = failure("CLI_TIMEOUT", stage, context.stderr, {
            taskId: context.taskId,
          });
        if (!error && active.cancelled)
          error = failure("CANCELLED", stage, context.stderr, {
            taskId: context.taskId,
          });
        if (!error && spawnError)
          error = failure("CLI_EXITED", stage, spawnError.message);
        if (!error && terminal?.type === "error")
          error = failure(
            terminal.code || "ENGINE_ERROR",
            stage,
            terminal.result?.message,
            {
              taskId: context.taskId,
              engineDiagnostic: terminal.result?.diagnostic,
            },
          );
        if (!error && (!terminal || ![0, 3].includes(exitCode)))
          error = failure(
            "CLI_EXITED",
            stage,
            `exit=${exitCode}; signal=${signal || "none"}; ${context.stderr}`,
            { taskId: context.taskId },
          );
        if (error) {
          reject(this.record(error, context));
          return;
        }
        const partial = terminal.status === "partial" || exitCode === 3;
        const partialDiagnostic = partial
          ? this.record(
              failure(
                "PARTIAL_RESULT",
                stage,
                "部分项目没有确认完成，请查看计数和逐项记录。",
                { taskId: context.taskId },
              ),
              context,
            )
          : null;
        resolve({
          data: partialDiagnostic
            ? { ...terminal.result, diagnostic: partialDiagnostic }
            : terminal.result,
          status: terminal.status,
          taskId: context.taskId,
          operation,
        });
      });
    });
  }
}
module.exports = { CliRunner };
