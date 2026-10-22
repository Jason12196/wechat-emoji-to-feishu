const fs = require("node:fs/promises");
const syncFs = require("node:fs");
const path = require("node:path");
const { randomUUID, createHash } = require("node:crypto");
const { failure, assert } = require("./errors.cjs");

class MigrationService {
  constructor({ runner, chooseDirectory }) {
    this.runner = runner;
    this.home = runner.home;
    this.chooseDirectory = chooseDirectory;
    this.accounts = [];
    this.exports = new Map();
    this.catalogs = new Map();
    this.assets = new Map();
    this.plans = new Map();
    this.loginAccount = null;
  }
  async initialize() {
    const result = await this.runner.run(["accounts"], "检测微信账号", 30000);
    this.accounts = result.data.accounts;
    const environment = await this.runner.run(
      ["doctor"],
      "检查运行环境",
      60000,
    );
    return {
      accounts: this.accounts.map(
        ({ wxid, nickname, key_cached, running }) => ({
          wxid,
          nickname,
          key_cached,
          running,
        }),
      ),
      environment: environment.data,
    };
  }
  account(wxid) {
    const account = this.accounts.find((item) => item.wxid === wxid);
    assert(account, "未知微信账号");
    return account;
  }
  async prepareExport({ wxid }) {
    const account = this.account(wxid);
    const parent = await this.chooseDirectory("选择表情导出位置");
    if (!parent) return null;
    const token = randomUUID();
    const directory = path.join(
      parent,
      `微信表情-${new Date().toISOString().replace(/[:.]/g, "-")}`,
    );
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    this.exports.set(token, { directory, wxid });
    return {
      token,
      keyCached: Boolean(account.key_cached),
      running: Boolean(account.running),
    };
  }
  async key({ wxid }) {
    this.account(wxid);
    const result = await this.runner.run(
      ["key", "--wxid", wxid],
      "获取微信密钥",
      240000,
    );
    this.account(wxid).key_cached = true;
    return { keyCached: result.data.key_cached };
  }
  async extract({ token }) {
    const job = this.exports.get(token);
    assert(job, "导出任务不存在");
    const result = await this.runner.run(
      ["extract", "--wxid", job.wxid, "--out", job.directory],
      "导出微信表情",
    );
    const catalog = await this.inspect(job.directory);
    return { ...catalog, failed: result.data.failed || 0 };
  }
  async openLocal() {
    const directory = await this.chooseDirectory("选择图片文件夹");
    if (!directory) return null;
    const out = path.join(this.home, "desktop", "prepared", randomUUID());
    const prepared = await this.runner.run(
      ["images", "prepare", directory, "--out", out],
      "校验并准备本地图片",
    );
    const catalog = await this.inspect(out);
    return { ...catalog, failed: prepared.data.failed || 0 };
  }
  async inspect(directory) {
    const result = await this.runner.run(
      ["images", "inspect", directory],
      "建立表情预览",
    );
    if (!result.data.valid) throw failure("NO_VALID_IMAGES", "建立表情预览");
    const token = randomUUID();
    const root = await fs.realpath(directory);
    const items = [];
    for (const image of result.data.images) {
      const file = await fs.realpath(image.file);
      assert(path.dirname(file) === root, "预览文件超出已选择的目录");
      assert(
        ["PNG", "GIF", "JPEG", "WEBP"].includes(image.format),
        "不支持的预览格式",
      );
      const asset = randomUUID();
      this.assets.set(asset, file);
      items.push({
        id: items.length,
        label: path.basename(file),
        file,
        url: `emoji://asset/${asset}`,
        animated: image.frames > 1,
        frames: image.frames,
        bytes: image.bytes,
        size: `${Math.ceil(image.bytes / 1024)} KB`,
        format: image.format,
      });
    }
    this.catalogs.set(token, { directory: root, items });
    return {
      token,
      items: items.map(({ file, ...item }) => item),
      invalid: result.data.invalid || 0,
      directory: root,
    };
  }
  validateChoice({ catalog, selected, account, existing }) {
    const source = this.catalogs.get(catalog);
    assert(source, "图片来源已失效，请重新选择");
    assert(
      Array.isArray(selected) && selected.length > 0 && selected.length <= 1000,
      "请选择 1 到 1000 张图片",
    );
    assert(new Set(selected).size === selected.length, "重复的图片编号");
    assert(
      selected.every((id) => Number.isInteger(id) && source.items[id]),
      "图片编号不在当前目录中",
    );
    assert(
      typeof account === "string" &&
        account.trim().length > 0 &&
        account.length <= 80,
      "请填写本地飞书账号名称",
    );
    assert(
      Number.isInteger(existing) && existing >= 0 && existing <= 1000,
      "已有表情数量必须为 0 到 1000",
    );
    return source;
  }
  async plan(request) {
    const source = this.validateChoice(request);
    const token = randomUUID();
    const directory = path.join(this.home, "desktop", "selections", token);
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    const selection = [];
    for (const id of request.selected) {
      const item = source.items[id];
      const file = await fs.realpath(item.file);
      assert(path.dirname(file) === source.directory, "图片位置已变化");
      const name = `${String(id).padStart(5, "0")}${path.extname(file).toLowerCase()}`;
      const output = path.join(directory, name);
      await fs.copyFile(file, output);
      await fs.chmod(output, 0o600);
      const digest = createHash("sha256")
        .update(await fs.readFile(output))
        .digest("hex");
      selection.push({ id, file: name, label: item.label, digest });
    }
    const result = await this.runner.run(
      [
        "feishu",
        "plan",
        directory,
        "--account",
        request.account,
        "--existing-count",
        String(request.existing),
      ],
      "检查飞书导入计划",
    );
    const value = {
      token,
      directory,
      account: request.account,
      existing: request.existing,
      selection,
      state: "planned",
      createdAt: new Date().toISOString(),
      plan: result.data,
    };
    this.plans.set(token, value);
    await this.saveJob(value);
    const { files, ...publicPlan } = result.data;
    return { token, ...publicPlan };
  }
  async login({ account }) {
    assert(
      typeof account === "string" && account.trim() && account.length <= 80,
      "请填写本地飞书账号名称",
    );
    this.loginAccount = null;
    const result = await this.runner.run(
      ["feishu", "login", "--account", account],
      "登录飞书",
      15 * 60 * 1000,
    );
    if (result.data.logged_in) this.loginAccount = account;
    return { loggedIn: Boolean(result.data.logged_in) };
  }
  async importSelection({ token, confirmed }) {
    const job = this.plans.get(token);
    assert(
      job && job.state === "planned",
      "导入计划不存在或已提交，请重新检查",
    );
    if (!confirmed || job.account !== this.loginAccount)
      throw failure("ACCOUNT_UNCONFIRMED", "核对飞书账号");
    if (!job.plan.fits) throw failure("CAPACITY_EXCEEDED", "检查飞书导入计划");
    for (const item of job.selection) {
      const file = await fs.realpath(path.join(job.directory, item.file));
      if (
        path.dirname(file) !== (await fs.realpath(job.directory)) ||
        createHash("sha256")
          .update(await fs.readFile(file))
          .digest("hex") !== item.digest
      )
        throw failure("SELECTION_CHANGED", "校验本次导入清单", item.label);
    }
    job.state = "running";
    await this.saveJob(job);
    try {
      const result = await this.runner.run(
        [
          "feishu",
          "import",
          job.directory,
          "--account",
          job.account,
          "--existing-count",
          String(job.existing),
        ],
        "导入飞书个人表情",
        undefined,
        (taskId) => {
          job.taskId = taskId;
          job.ledger = path.join(this.home, "imports", `${taskId}.json`);
          this.saveJobSync(job);
        },
      );
      job.taskId = result.taskId;
      job.result = result.data;
      job.state = result.status;
      await this.saveJob(job);
      return { ...result.data, taskId: result.taskId, job: token };
    } catch (error) {
      job.taskId = error.taskId || job.taskId;
      job.state = "interrupted";
      if (job.taskId)
        job.ledger = path.join(this.home, "imports", `${job.taskId}.json`);
      const progress = await this.ledgerProgress(job);
      job.result = progress;
      error.progress = { ...progress, job: token, taskId: job.taskId };
      await this.saveJob(job);
      throw error;
    }
  }
  saveJobSync(job) {
    const directory = path.join(this.home, "desktop", "jobs");
    syncFs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    const file = path.join(directory, `${job.token}.json`);
    const tmp = `${file}.tmp`;
    syncFs.writeFileSync(tmp, JSON.stringify(job, null, 2), { mode: 0o600 });
    syncFs.renameSync(tmp, file);
  }
  async ledgerProgress(job) {
    const expected = new Set(
      job.selection.map((item) => item.digest || item.file || item.id),
    ).size;
    let values = [];
    try {
      values = Object.values(
        JSON.parse(await fs.readFile(job.result?.ledger || job.ledger, "utf8")),
      );
    } catch {
      return {
        success: 0,
        unknown: expected,
        remaining: 0,
        ledger: job.ledger,
        verificationRequired: true,
      };
    }
    const success = values.filter((item) => item.status === "confirmed").length;
    const unknown = values.filter((item) => item.status !== "confirmed").length;
    return {
      success,
      unknown,
      remaining: Math.max(0, expected - success - unknown),
      ledger: job.ledger,
    };
  }
  async saveJob(job) {
    const directory = path.join(this.home, "desktop", "jobs");
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    const file = path.join(directory, `${job.token}.json`);
    const tmp = `${file}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(job, null, 2), { mode: 0o600 });
    await fs.rename(tmp, file);
  }
  async history() {
    const directory = path.join(this.home, "desktop", "jobs");
    let files;
    try {
      files = await fs.readdir(directory);
    } catch (error) {
      if (error.code === "ENOENT") return [];
      throw error;
    }
    const jobs = [];
    for (const name of files.filter((name) =>
      /^[a-f0-9-]{36}\.json$/.test(name),
    )) {
      const job = JSON.parse(
        await fs.readFile(path.join(directory, name), "utf8"),
      );
      if (job.state === "running" || job.state === "interrupted")
        job.result = await this.ledgerProgress(job);
      if (job.state === "running" && !this.runner.active)
        job.state = "interrupted";
      jobs.push({
        id: job.token,
        account: job.account,
        state: job.state,
        createdAt: job.createdAt,
        result: job.result,
        taskId: job.taskId,
        count: job.selection.length,
        recoverable:
          Boolean(job.ledger || job.result?.ledger) && job.state !== "complete",
      });
    }
    return jobs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  async restoreContext({ job: token }) {
    assert(/^[a-f0-9-]{36}$/.test(token), "无效任务编号");
    const job = JSON.parse(
      await fs.readFile(
        path.join(this.home, "desktop", "jobs", `${token}.json`),
        "utf8",
      ),
    );
    assert(job.ledger || job.result?.ledger, "该记录尚未提交，不需要恢复上传");
    const catalog = await this.inspect(job.directory);
    return {
      ...catalog,
      account: job.account,
      recoveryJob: token,
      recoverySummary: await this.ledgerProgress(job),
    };
  }
  async resume({ job: token, existing, confirmed }) {
    assert(/^[a-f0-9-]{36}$/.test(token), "无效任务编号");
    assert(
      Number.isInteger(existing) && existing >= 0 && existing <= 1000,
      "请更新已有表情数量",
    );
    const job = JSON.parse(
      await fs.readFile(
        path.join(this.home, "desktop", "jobs", `${token}.json`),
        "utf8",
      ),
    );
    if (!confirmed || job.account !== this.loginAccount)
      throw failure("ACCOUNT_UNCONFIRMED", "恢复导入");
    const ledger = job.result?.ledger || job.ledger;
    if (!ledger)
      throw failure(
        "LEDGER_UNRESOLVED",
        "恢复导入",
        "该任务没有可用的导入记录，不能自动重新提交。",
      );
    const result = await this.runner.run(
      [
        "feishu",
        "plan",
        job.directory,
        "--account",
        job.account,
        "--existing-count",
        String(existing),
        "--ledger",
        ledger,
      ],
      "检查恢复计划",
    );
    if (!result.data.fits)
      throw failure(
        "LEDGER_UNRESOLVED",
        "检查恢复计划",
        JSON.stringify({
          unresolved: result.data.unresolved,
          available: result.data.available,
        }),
      );
    const imported = await this.runner.run(
      [
        "feishu",
        "import",
        job.directory,
        "--account",
        job.account,
        "--existing-count",
        String(existing),
        "--ledger",
        ledger,
      ],
      "恢复未提交的表情",
      undefined,
      (taskId) => {
        job.taskId = taskId;
        job.ledger = ledger;
        job.state = "running";
        this.saveJobSync(job);
      },
    );
    job.result = { ...imported.data, ...(await this.ledgerProgress(job)) };
    job.state = imported.status;
    job.taskId = imported.taskId;
    await this.saveJob(job);
    return { ...job.result, job: token, taskId: imported.taskId };
  }
}
module.exports = { MigrationService };
