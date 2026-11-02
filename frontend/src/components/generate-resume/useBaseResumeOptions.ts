/** 生成弹窗的「底稿」候选：打开时拉一次简历列表，关掉不请求。

候选文案带上岗位与日期，是因为同一个"通用母版"往往有好几版，只给标题根本分不清。
取不到列表时静默为空——底稿是增强项，不该让它阻断正常生成。
*/
import { useCallback, useEffect, useState } from "react";
import { listResumes } from "../../api/resumes";
import type { BaseResumeOption } from "./GenerationConfigStage";

export function useBaseResumeOptions(open: boolean) {
  const [baseResumeId, setBaseResumeId] = useState<number | null>(null);
  const [baseResumeOptions, setBaseResumeOptions] = useState<BaseResumeOption[]>([]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    void listResumes({ page_size: 50 })
      .then((page) => {
        if (!alive) return;
        setBaseResumeOptions(
          page.items.map((item) => ({
            value: item.id,
            label: `${item.title}${item.job_title ? ` · ${item.job_title}` : ""}${
              item.created_at ? ` · ${item.created_at.slice(0, 10)}` : ""
            }`,
            // 底稿不只是正文：模板/版式/页数/字号/语言也一起带回来，选中后可以沿用。
            template: item.template,
            format_name: item.format_name,
            format_config: item.format_config ?? {},
            page_limit: item.page_limit,
            font_scale: item.font_scale,
            language: item.language,
          })),
        );
      })
      .catch(() => {
        if (alive) setBaseResumeOptions([]);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const resetBaseResume = useCallback(() => setBaseResumeId(null), []);

  return { baseResumeId, setBaseResumeId, baseResumeOptions, resetBaseResume };
}
