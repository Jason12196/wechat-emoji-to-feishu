const fs = require("node:fs/promises");
const syncFs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { randomUUID, createHash } = require("node:crypto");
const { failure, assert } = require("./errors.cjs");

class MigrationService {
  constructor({ runner, chooseDirectory, downloadsDirectory }) {
    this.runner = runner;
    this.home = runner.home;
    this.chooseDirectory = chooseDirectory;
    this.exportDirectory =
      downloadsDirectory || path.join(os.homedir(), "Downloads");
    this.accounts = [];
    this.exports = new Map();
    this.discoveredExports = new Map();
    this.exportJobs = [];
    this.exportPreferencesLoaded = false;
    this.catalogs = new Map();
    this.assets = new Map();
    this.plans = new Map();
    this.loginAccount = null;
  }
  async initialize() {
    await this.loadExportPreferences();
    await this.refreshAccounts();
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
      exportDirectory: this.exportDirectory,
    };
  }
  account(wxid) {
    const account = this.accounts.find((item) => item.wxid === wxid);
    assert(account, "未知微信账号");
    return account;
  }
  async refreshAccounts() {
    const result = await this.runner.run(["accounts"], "检测微信账号", 30000);
    this.accounts = result.data.accounts;
    return this.accounts;
  }
  async loadExportPreferences() {
    if (this.exportPreferencesLoaded) return;
    const read = async (name, fallback) => {
      try {
        return JSON.parse(
          await fs.readFile(path.join(this.home, "desktop", name), "utf8"),
        );
      } catch (error) {
        if (error.code === "ENOENT") return fallback;
        throw error;
      }
    };
    const preferences = await read("preferences.json", {});
    if (
      typeof preferences.exportDirectory === "string" &&
      path.isAbsolute(preferences.exportDirectory)
    )
      this.exportDirectory = preferences.exportDirectory;
    const jobs = await read("export-jobs.json", []);
    assert(Array.isArray(jobs), "导出准备记录格式不正确");
    this.exportJobs = jobs.filter(
      (job) =>
        typeof job.wxid === "string" &&
        typeof job.directory === "string" &&
        path.isAbsolute(job.directory),
    );
    this.exportPreferencesLoaded = true;
  }
  async saveExportData(name, data) {
    const directory = path.join(this.home, "desktop");
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    const file = path.join(directory, name);
    const temporary = `${file}.${randomUUID()}.tmp`;
    await fs.writeFile(temporary, JSON.stringify(data, null, 2), {
      mode: 0o600,
      flag: "wx",
    });
    try {
      await fs.rename(temporary, file);
    } catch (error) {
      await fs.rm(temporary, { force: true });
      throw error;
    }
  }
  async canonicalDirectory(directory) {
    const absolute = path.resolve(directory);
    try {
      return await fs.realpath(absolute);
    } catch (error) {
      if (error.code === "ENOENT") {
        const parent = path.dirname(absolute);
        if (parent === absolute) return absolute;
        return path.join(
          await this.canonicalDirectory(parent),
          path.basename(absolute),
        );
      }
      throw error;
    }
  }
  async chooseExportDirectory() {
    await this.loadExportPreferences();
    const directory = await this.chooseDirectory(
      "选择表情导出位置",
      this.exportDirectory,
    );
    if (directory) {
      this.exportDirectory = directory;
      this.discoveredExports.clear();
      await this.saveExportData("preferences.json", {
        exportDirectory: directory,
      });
    }
    return { directory: this.exportDirectory };
  }
  async readExportState(directory, wxid) {
    const result = await this.runner.run(
      ["exports", "status", directory, "--wxid", wxid],
      "校验已有微信表情",
      60000,
    );
    const state = result.data;
    const expectedDirectory = await this.canonicalDirectory(directory);
    assert(
      ["none", "partial", "complete", "unbound"].includes(state.state) &&
        typeof state.directory === "string" &&
        (await this.canonicalDirectory(state.directory)) === expectedDirectory,
      "导出记录返回的目录不正确",
    );
    assert(!state.wxid || state.wxid === wxid, "导出记录属于其他微信账号");
    assert(
      !["partial", "complete"].includes(state.state) || state.wxid === wxid,
      "导出记录缺少当前微信账号绑定",
    );
    return { ...state, directory: expectedDirectory };
  }
  async findExports({ wxid }) {
    await this.loadExportPreferences();
    await this.refreshAccounts();
    this.account(wxid);
    return {
      ...(await this.discoverExports(wxid)),
      accounts: this.accounts.map(
        ({ wxid, nickname, key_cached, running }) => ({
          wxid,
          nickname,
          key_cached,
          running,
        }),
      ),
      keyCached: Boolean(this.account(wxid).key_cached),
    };
  }
  async discoverExports(wxid) {
    const result = await this.runner.run(
      ["exports", "discover", this.exportDirectory, "--wxid", wxid],
      "查找已有微信表情",
      60000,
    );
    const parent = await this.canonicalDirectory(this.exportDirectory);
    const exports = [];
    this.discoveredExports.clear();
    for (const item of result.data.exports || []) {
      assert(
        typeof item.directory === "string" && path.isAbsolute(item.directory),
        "导出记录缺少有效目录",
      );
      const directory = await this.canonicalDirectory(item.directory);
      assert(
        directory === parent || path.dirname(directory) === parent,
        "已有导出超出当前导出位置",
      );
      if (item.wxid && item.wxid !== wxid) continue;
      assert(
        ["partial", "complete", "unbound"].includes(item.state),
        "无法识别已有导出的状态",
      );
      const entry = { ...item, directory };
      exports.push(entry);
      this.discoveredExports.set(directory, { wxid, parent });
    }
    return { directory: this.exportDirectory, exports };
  }
  exportToken(directory, wxid) {
    const existing = [...this.exports].find(
      ([, job]) => job.directory === directory && job.wxid === wxid,
    );
    if (existing) return existing[0];
    const token = randomUUID();
    this.exports.set(token, { directory, wxid });
    return token;
  }
  async prepareExport({ wxid, directory: requestedDirectory }) {
    assert(
      requestedDirectory === undefined ||
        typeof requestedDirectory === "string",
      "请选择有效的导出目录",
    );
    await this.loadExportPreferences();
    await this.refreshAccounts();
    const account = this.account(wxid);
    const discovered = await this.discoverExports(wxid);
    const requested = requestedDirectory
      ? await this.canonicalDirectory(requestedDirectory)
      : null;
    const candidate = requestedDirectory
      ? discovered.exports.find((item) => item.directory === requested)
      : discovered.exports.find((item) =>
          ["complete", "partial"].includes(item.state),
        );
    if (requestedDirectory) assert(candidate, "该导出不在当前目录的发现记录中");
    if (candidate) {
      const state = await this.readExportState(candidate.directory, wxid);
      assert(
        state.wxid === wxid && ["complete", "partial"].includes(state.state),
        "该目录尚未确认属于当前微信账号，请使用已有图片入口",
      );
      const common = {
        ...state,
        existing: state.state,
        keyCached: Boolean(account.key_cached),
        running: Boolean(account.running),
      };
      if (state.state === "complete")
        return { ...common, catalog: await this.inspect(state.directory) };
      return {
        ...common,
        token: this.exportToken(state.directory, wxid),
        canResumeWithoutKey: Boolean(state.snapshot_ready),
      };
    }
    const parent = await this.canonicalDirectory(this.exportDirectory);
    let directory;
    for (const job of this.exportJobs.toReversed()) {
      if (
        job.wxid !== wxid ||
        (await this.canonicalDirectory(path.dirname(job.directory))) !== parent
      )
        continue;
      try {
        if (!(await fs.stat(job.directory)).isDirectory()) continue;
      } catch (error) {
        if (error.code === "ENOENT") continue;
        throw error;
      }
      const state = await this.readExportState(job.directory, wxid);
      if (
        state.state === "none" &&
        (await fs.readdir(job.directory)).length === 0
      ) {
        directory = state.directory;
        break;
      }
    }
    if (!directory)
      directory = path.join(
        parent,
        `微信表情-${new Date().toISOString().replace(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`,
      );
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    if (!this.exportJobs.some((job) => job.directory === directory)) {
      this.exportJobs.push({ directory, wxid });
      await this.saveExportData("export-jobs.json", this.exportJobs);
    }
    return {
      existing: "none",
      token: this.exportToken(directory, wxid),
      directory,
      keyCached: Boolean(account.key_cached),
      running: Boolean(account.running),
    };
  }
  async knownExportDirectory(directory, wxid) {
    assert(typeof directory === "string", "请选择已有导出目录");
    const chosen = await this.canonicalDirectory(directory);
    const known = this.discoveredExports.get(chosen);
    assert(
      known &&
        known.wxid === wxid &&
        known.parent === (await this.canonicalDirectory(this.exportDirectory)),
      "该目录不在当前账号的发现记录中，请重新检查已有导出",
    );
    return chosen;
  }
  async useExistingExport({ directory, wxid }) {
    const chosen = await this.knownExportDirectory(directory, wxid);
    const state = await this.readExportState(chosen, wxid);
    assert(
      state.state === "unbound" ||
        (state.state === "complete" && state.wxid === wxid),
      "该导出尚未完成或已变化，请重新检查后继续",
    );
    return {
      ...(await this.inspect(chosen)),
      exportState: state,
    };
  }
  async adoptExistingExport({ directory, wxid, confirmed }) {
    assert(confirmed === true, "请先确认旧导出属于当前微信账号");
    const chosen = await this.knownExportDirectory(directory, wxid);
    await this.refreshAccounts();
    const account = this.account(wxid);
    const before = await this.readExportState(chosen, wxid);
    const knownJob = this.exportJobs.find((job) => job.directory === chosen);
    assert(!knownJob || knownJob.wxid === wxid, "准备记录属于其他微信账号");
    assert(
      before.state === "unbound" &&
        before.legacy_raw === true &&
        Number.isInteger(before.raw_count) &&
        before.raw_count > 0,
      "该目录不是可继续的旧版原始文件导出，请重新检查已有导出",
    );
    try {
      await fs.lstat(path.join(chosen, "export-report.json"));
      assert(false, "该目录已有导出报告，请使用已有图片入口");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    try {
      await fs.writeFile(
        path.join(chosen, "export-state.json"),
        JSON.stringify({ version: 1, wxid, resources: null }, null, 2),
        { flag: "wx", mode: 0o600 },
      );
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      // Another attempt may have bound the directory after the status check.
      // The authoritative status below must still confirm this same account.
    }
    const state = await this.readExportState(chosen, wxid);
    assert(
      state.wxid === wxid && ["partial", "complete"].includes(state.state),
      "旧导出账号绑定失败，请保留原始文件并查看诊断记录",
    );
    if (!knownJob) {
      this.exportJobs.push({ directory: chosen, wxid });
      await this.saveExportData("export-jobs.json", this.exportJobs);
    }
    const prepared = {
      ...state,
      existing: state.state,
      keyCached: Boolean(account.key_cached),
      running: Boolean(account.running),
    };
    if (state.state === "complete")
      return { ...prepared, catalog: await this.inspect(chosen) };
    return {
      ...prepared,
      token: this.exportToken(chosen, wxid),
      canResumeWithoutKey: Boolean(state.snapshot_ready),
    };
  }
  async key({ wxid }) {
    await this.refreshAccounts();
    if (this.account(wxid).key_cached) return { keyCached: true, reused: true };
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
    const before = await this.readExportState(job.directory, job.wxid);
    assert(before.state !== "unbound", "已有图片未绑定微信账号，不能继续导出");
    const result =
      before.state === "complete"
        ? { data: { failed: 0 } }
        : await this.runner.run(
            ["extract", "--wxid", job.wxid, "--out", job.directory],
            "导出微信表情",
          );
    const state = await this.readExportState(job.directory, job.wxid);
    const catalog = await this.inspect(job.directory);
    return {
      ...catalog,
      failed: result.data.failed || 0,
      remaining: state.remaining,
      exportState: state,
    };
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
