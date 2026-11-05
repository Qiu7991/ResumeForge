/** 支持 `?import_url=…`：浏览器扩展悬浮按钮/书签把岗位链接交给岗位广场导入。 */
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { importJobFromUrl } from "../../api/jobs";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";

interface ImportResultMessage {
  type: "resumeforge-import-result";
  ok: boolean;
  title?: string;
  error?: string;
}

function postToOpener(message: ImportResultMessage | { type: "resumeforge-import-started" }) {
  window.opener?.postMessage(message, "*");
}

function replyToOpener(message: ImportResultMessage) {
  postToOpener({ ...message, type: "resumeforge-import-result" });
}

/** 导入接口按 URL 幂等：网络类失败（常见于后端正在重启）等 2 秒重试一次。 */
async function importWithOneRetry(raw: string) {
  try {
    return await importJobFromUrl(raw);
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "network") throw error;
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    return importJobFromUrl(raw);
  }
}

/** 弹窗要等 opener 收完消息再关；立刻 close 可能把 postMessage 一起掐掉。 */
function closeAfterReply() {
  window.setTimeout(() => window.close(), 300);
}

export function useImportUrlParam(onImported: (jobId: number) => void) {
  const [params, setParams] = useSearchParams();
  const handled = useRef("");
  const raw = params.get("import_url") || "";
  const closeAfter = params.get("close_after") === "1";

  useEffect(() => {
    if (!raw || handled.current === raw) return;
    handled.current = raw;
    // 先告诉扩展"窗口已连上、开始导入"：BOSS 详情页慢时导入可能要几十秒，
    // 扩展据此把"没回应"的判定从 12 秒换成 120 秒，而不是提前报错。
    if (closeAfter) postToOpener({ type: "resumeforge-import-started" });
    void importWithOneRetry(raw)
      .then((job) => {
        if (closeAfter) {
          replyToOpener({ type: "resumeforge-import-result", ok: true, title: job.title });
          closeAfterReply();
          return;
        }
        const next = new URLSearchParams(params);
        next.delete("import_url");
        next.delete("close_after");
        next.set("job_id", String(job.id));
        setParams(next, { replace: true });
        onImported(job.id);
      })
      .catch((error: unknown) => {
        // 网络类错误多半是本地服务正在重启：给一句能指导重试的话，而不是"应用没启动"。
        const message =
          error instanceof ApiError && error.code === "network"
            ? t("jobsPage.importUrl.networkUnavailable")
            : error instanceof Error
              ? error.message
              : t("jobsPage.importUrl.failed");
        if (closeAfter) {
          replyToOpener({ type: "resumeforge-import-result", ok: false, error: message });
          closeAfterReply();
          return;
        }
        const next = new URLSearchParams(params);
        next.delete("import_url");
        next.delete("close_after");
        setParams(next, { replace: true });
      });
  }, [raw, closeAfter, params, setParams, onImported]);
}
