/**
 * 简历批量导出：选中多份简历，后端打成一个 zip 返回。
 *
 * 与单份导出的区别：不再逐份弹下载（浏览器会拦截连续下载），而是一个交付物；
 * 参数只有格式（默认 PDF）——字号/页数/版式沿用每份简历自己的记录。
 */
import type { ExportFormat } from "../types/export";
import { getFilenameFromDisposition, requestRaw } from "./client";

export interface BatchExportResult {
  blob: Blob;
  filename: string;
  /** 成功打进 zip 的份数（由后端响应头带回，不靠前端数）。 */
  exported: number;
  /** 被跳过的份数（正文还有【待补】标记、模板渲染失败等）。 */
  skipped: number;
  /** 跳过原因（最多前 5 条，中文，已从 URL 编码还原）。 */
  skippedDetail: string;
}

function readCountHeader(value: string | null): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

/** 响应头只能是 latin-1，中文原因由后端 URL 编码；解不开就原样展示。 */
function decodeHeaderText(value: string | null): string {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** 一次最多 50 份（与后端 MAX_BATCH_EXPORT 一致）：再多就该分批，否则请求会挂到超时。 */
export const MAX_BATCH_EXPORT = 50;

export async function batchExportResumes(
  resumeIds: number[],
  format: ExportFormat = "pdf",
): Promise<BatchExportResult> {
  const resp = await requestRaw("/resumes/batch-export", {
    method: "POST",
    // 逐份同步渲染，50 份 PDF 是"几分钟"量级；走 export 预算（10 分钟）。
    budget: "export",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_ids: resumeIds, format }),
  });
  return {
    blob: await resp.blob(),
    filename:
      getFilenameFromDisposition(resp.headers.get("Content-Disposition")) ?? "简历批量导出.zip",
    exported: readCountHeader(resp.headers.get("X-Batch-Exported")),
    skipped: readCountHeader(resp.headers.get("X-Batch-Skipped")),
    skippedDetail: decodeHeaderText(resp.headers.get("X-Batch-Skipped-Detail")),
  };
}
