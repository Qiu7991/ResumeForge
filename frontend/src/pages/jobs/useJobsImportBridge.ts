/** 岗位广场的导入入口桥：`?import_url=` 进来时导入、提示并切到详情。
 *
 * 单独成 hook 的原因很实际：JobsPage 已经贴着 500 行预算，而这段"提示 + 刷新 + 跳转"
 * 与页面业务无关，放这里既省行数也好单独读。
 */
import { App } from "antd";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useImportUrlParam } from "./useImportUrlParam";

export function useJobsImportBridge(reload: () => void) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  useImportUrlParam(
    useCallback(
      (jobId: number) => {
        message.success("已导入岗位");
        reload();
        navigate(`/jobs?job_id=${jobId}`, { replace: true });
      },
      [message, navigate, reload],
    ),
  );
}
