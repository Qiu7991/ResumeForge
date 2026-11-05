// SPDX-License-Identifier: Apache-2.0
// ===== ③ 失败分类（与后端 FAILURE_CATEGORY_LABELS 一致）=====
export const FAILURE_CATEGORIES = [
  "selector_invalid",
  "login_required",
  "captcha_required",
  "greeting_missing",
  "greeting_unconfirmed",
  "network_timeout",
  "file_upload_failed",
  "site_unsupported",
  "profile_insufficient",
  "unconfirmed",
  "job_closed",
  "unknown",
] as const;

export type FailureCategory = (typeof FAILURE_CATEGORIES)[number];

// 这张表必须与后端 FAILURE_CATEGORY_LABELS **逐字一致**（镜像测试锁定）；
// 行尾的 i18n-ok 表示它是协议镜像、不随界面语言变化，不是新写的界面文案。
export const FAILURE_CATEGORY_LABELS: Record<FailureCategory, string> = {
  selector_invalid: "页面结构变化 / 选择器失效",
  login_required: "需要登录",
  captcha_required: "需要验证码或安全验证",
  greeting_missing: "招呼语缺失",
  greeting_unconfirmed: "招呼语待确认", // i18n-ok: 与后端 FAILURE_CATEGORY_LABELS 逐字一致，镜像测试锁定
  network_timeout: "网络超时",
  file_upload_failed: "简历上传失败",
  site_unsupported: "岗位来源不支持自动投递",
  profile_insufficient: "资料不足，需要先补充简历/网申资料",
  unconfirmed: "无法确认投递结果，请到浏览器核对",
  job_closed: "岗位已关闭", // i18n-ok: 与后端 FAILURE_CATEGORY_LABELS 逐字一致，镜像测试锁定
  unknown: "未知失败",
};

/** 后端未给出中文说明时（空串 / 未识别值）回退到原始码或占位。 */
export function failureLabel(category: string, fallback = ""): string {
  if (!category) return fallback;
  return FAILURE_CATEGORY_LABELS[category as FailureCategory] ?? category;
}

// ===== ④ 执行步骤 =====
export const STEP_LABELS: Record<string, string> = {
  opening: "打开岗位页",
  filling: "填写表单",
  greeting: "发送招呼语",
  uploading: "上传简历",
  submitting: "提交投递",
  verifying: "确认结果",
  waiting: "岗位间间隔",
  idle: "空闲",
};

export function stepLabel(step: string): string {
  if (!step) return "空闲";
  return STEP_LABELS[step] ?? step;
}
