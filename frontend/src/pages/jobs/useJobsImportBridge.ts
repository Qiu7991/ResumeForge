/** 岗位广场导入桥：`?import_url=` 进来时导入、提示并切到详情。 */
import { App } from "antd";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { t } from "../../i18n";
import { useImportUrlParam } from "./useImportUrlParam";

export function useJobsImportBridge(reload: () => void) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  useImportUrlParam(
    useCallback(
      (jobId: number) => {
        message.success(t("jobsPage.importUrl.imported"));
        reload();
        navigate(`/jobs?job_id=${jobId}`, { replace: true });
      },
      [message, navigate, reload],
    ),
  );
}
