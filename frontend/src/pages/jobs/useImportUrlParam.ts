/** 支持 `?import_url=…`：浏览器扩展悬浮按钮/书签把岗位链接交给岗位广场导入。 */
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { importJobFromUrl } from "../../api/jobs";
import { t } from "../../i18n";

interface ImportResultMessage {
  type: "resumeforge-import-result";
  ok: boolean;
  title?: string;
  error?: string;
}

function replyToOpener(message: ImportResultMessage) {
  window.opener?.postMessage({ ...message, type: "resumeforge-import-result" }, "*");
}

export function useImportUrlParam(onImported: (jobId: number) => void) {
  const [params, setParams] = useSearchParams();
  const handled = useRef("");
  const raw = params.get("import_url") || "";
  const closeAfter = params.get("close_after") === "1";

  useEffect(() => {
    if (!raw || handled.current === raw) return;
    handled.current = raw;
    void importJobFromUrl(raw)
      .then((job) => {
        if (closeAfter) {
          replyToOpener({ type: "resumeforge-import-result", ok: true, title: job.title });
          window.close();
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
        const message = error instanceof Error ? error.message : t("jobsPage.importUrl.failed");
        if (closeAfter) {
          replyToOpener({ type: "resumeforge-import-result", ok: false, error: message });
          window.close();
          return;
        }
        const next = new URLSearchParams(params);
        next.delete("import_url");
        next.delete("close_after");
        setParams(next, { replace: true });
      });
  }, [raw, closeAfter, params, setParams, onImported]);
}
