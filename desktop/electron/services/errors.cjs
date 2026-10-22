const { randomUUID } = require("node:crypto");

const messages = {
  CLI_NOT_FOUND: [
    "找不到本机提取工具",
    "请重新完整安装应用，或检查维护者提供的 CLI 路径。",
  ],
  OPERATION_BUSY: [
    "上一项操作还没有结束",
    "请等待完成，或停止当前操作后再试。",
  ],
  CLI_PROTOCOL_ERROR: [
    "工具返回的数据无法识别",
    "保留任务编号，检查应用与 CLI 是否为配套版本。",
  ],
  CLI_EXITED: [
    "工具意外退出",
    "已保留诊断记录。导入中断时，请先核对飞书里的实际结果。",
  ],
  CLI_TIMEOUT: [
    "这一步等待超时",
    "检查登录窗口和网络，再查看诊断记录。不要直接重新提交表情。",
  ],
  INVALID_REQUEST: ["操作参数不正确", "请返回重新选择账号、文件夹或表情。"],
  NO_ACCOUNTS: [
    "没有找到本机微信账号",
    "请先在这台 Mac 登录微信，或选择本地图片。",
  ],
  NO_VALID_IMAGES: [
    "没有可用的图片",
    "请确认文件夹里有可解码的图片，或检查导出报告。",
  ],
  INVALID_IMAGE: ["部分图片无法读取", "原图已保留，请查看图片校验结果。"],
  CAPACITY_EXCEEDED: [
    "飞书剩余空间不足",
    "减少本次选择，或先自行整理飞书个人表情。",
  ],
  CAPACITY_REQUIRED: ["请确认已有表情数量", "填写 0 到 1000 之间的整数。"],
  IMPORT_PLAN_INVALID: [
    "这批表情暂时不能导入",
    "检查文件大小、校验结果和待核对的历史记录。",
  ],
  LOGIN_TIMEOUT: [
    "飞书登录没有完成",
    "确认独立浏览器窗口中的登录状态，再重新登录。",
  ],
  ACCOUNT_UNCONFIRMED: [
    "尚未核对接收账号",
    "先在浏览器完成登录，再核对实际账号。",
  ],
  SELECTION_CHANGED: ["表情选择已变化", "请重新检查导入计划后再开始。"],
  LEDGER_UNRESOLVED: [
    "有已提交项目需要核对",
    "先在飞书确认结果。不会自动重传结果不明的项目。",
  ],
  CANCELLED: [
    "操作已停止",
    "已完成的文件和任务记录会保留；导入结果不明的项目需要核对。",
  ],
  DIRECTORY_NOT_FOUND: [
    "图片文件夹不存在",
    "重新选择图片文件夹，检查目录是否被移动。",
  ],
  LEDGER_ACCOUNT_MISMATCH: [
    "记录属于另一个本地账号",
    "使用原账号名称，并核对实际飞书登录身份。",
  ],
  LEDGER_ACCOUNT_UNKNOWN: [
    "记录缺少账号绑定",
    "保留原始记录，不能自动重新上传。",
  ],
  LEDGER_NOT_FOUND: ["找不到原始导入记录", "检查记录位置，不要从头重复提交。"],
  PARTIAL_RESULT: [
    "部分项目没有确认完成",
    "已保留成功与待核对记录，先核对后再恢复。",
  ],
  ENGINE_ERROR: [
    "处理没有完成",
    "查看下面的失败步骤与诊断信息，再决定是否重试。",
  ],
};
function redact(value) {
  return String(value ?? "")
    .replace(/https?:\/\/[^\s"'<>]+/g, "[资源链接已隐藏]")
    .replace(/\b[0-9a-f]{64,}\b/gi, "[密钥或摘要已隐藏]")
    .replace(/\b(?:gh[pousr]_[\w]+|github_pat_[\w]+)\b/g, "[令牌已隐藏]")
    .replace(
      /((?:cookie|authorization|token|password|db_key|secret)\s*[=:]\s*)[^\r\n]+/gi,
      "$1[已隐藏]",
    )
    .replace(/wxid_[\w-]+/g, "[微信账号]")
    .replaceAll(process.env.HOME || "__NO_HOME_CONFIGURED__", "~");
}
function failure(code, stage, detail = "", extra = {}) {
  const [message, recovery] = messages[code] || messages.ENGINE_ERROR;
  return {
    id: randomUUID(),
    code,
    stage,
    message,
    recovery,
    detail: redact(detail).slice(-8000),
    time: new Date().toISOString(),
    ...extra,
  };
}
function assert(condition, detail) {
  if (!condition) throw failure("INVALID_REQUEST", "参数检查", detail);
}
module.exports = { failure, redact, assert };
