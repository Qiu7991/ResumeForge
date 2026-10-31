// SPDX-License-Identifier: Apache-2.0
/** 岗位广场「按链接导入」：按钮 + 弹窗，导入成功后把岗位交给宿主刷新/打开。 */
import { LinkOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { Job } from "../../types";
import ImportJobUrlModal from "./ImportJobUrlModal";
import { useJobsImportBridge } from "./useJobsImportBridge";

export default function JobUrlImportButton({
  disabled = false,
  onImported,
  onPageReload,
}: {
  disabled?: boolean;
  onImported: (job: Job) => void;
  /** ?import_url= 导入成功后刷新当前列表。 */
  onPageReload: () => void;
}) {
  useLocale();
  useJobsImportBridge(onPageReload);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button icon={<LinkOutlined />} disabled={disabled} onClick={() => setOpen(true)}>
        {t("jobsPage.filter.importUrl")}
      </Button>
      <ImportJobUrlModal
        open={open}
        onClose={() => setOpen(false)}
        onImported={onImported}
      />
    </>
  );
}
