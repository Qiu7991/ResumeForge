/** 支持 `?import_url=…`：外部（浏览器扩展的悬浮按钮、书签、分享链接）把岗位链接交给岗位广场导入。
 *
 * 两种进入方式：
 * - 普通页面（`close_after` 缺省）：导入成功后把 URL 换成 `job_id` 并打开详情；
 * - 悬浮按钮开的一次性小窗口（`close_after=1`）：导入结果用 `postMessage` 回给打开它的页面，
 *   随后自己关闭——主页面不跳走，后台也不留下标签页。
 */
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { importJobFromUrl } from "../../api/jobs";

interface ImportResultMessage {
  type: "resumeforge-import-result";
  ok: boolean;
  title?: string;
  error?: string;
}

function replyToOpener(message: ImportResultMessage) {
  // 只用 postMessage，跨源也没问题；不给 opener 任何可执行内容。
  window.opener?.postMessage(message, "*");
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
        const message = error instanceof Error ? error.message : "导入失败";
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
