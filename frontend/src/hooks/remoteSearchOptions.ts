// SPDX-License-Identifier: Apache-2.0
/**
 * 远程搜索选择器的开箱即用工厂（P0-1）：把岗位 / 简历 / 进度三类高频下拉的
 * 取数、标签拼装与已选值回查统一封装，替代各页 `page_size: 100` 当全量的旧取法。
 *
 * 各页曾经的标签口径保留不变：
 * - 岗位：`标题 · 公司`（无公司时只有标题）
 * - 简历：标题（缺省 `简历 #id`）
 * - 进度：`公司 · 岗位`
 */
import { getJob, listJobs } from "../api/jobs";
import { getResume, listResumes } from "../api/resumes";
import { getTrack, listTracksPage } from "../api/tracker";
import { t } from "../i18n";
import type { ResumeBrief } from "../types";
import { useRemoteSearchSelect } from "./useRemoteSearchSelect";
import type { RemoteSelectOption } from "./useRemoteSearchSelect";

/** 下拉搜索的每页条数：搜索结果足够扫一眼，翻找靠继续输入关键词。 */
const SELECT_PAGE_SIZE = 50;

export function jobOption(job: { id: number; title: string; company: string }): RemoteSelectOption {
  return { value: job.id, label: `${job.title}${job.company ? ` · ${job.company}` : ""}` };
}

export function resumeOption(resume: { id: number; title: string }): RemoteSelectOption {
  return {
    value: resume.id,
    label: resume.title || t("hooksUi.option.resumeFallback", { id: resume.id }),
  };
}

export function trackOption(track: {
  id: number;
  company: string;
  title: string;
}): RemoteSelectOption {
  return { value: track.id, label: `${track.company} · ${track.title}` };
}

export function useJobSearchSelect() {
  return useRemoteSearchSelect({
    fetchOptions: (keyword) =>
      listJobs({ keyword, page_size: SELECT_PAGE_SIZE }).then((page) => page.items.map(jobOption)),
    fetchById: (id) =>
      getJob(id)
        .then(jobOption)
        .catch(() => null),
  });
}

export function useResumeSearchSelect() {
  return useRemoteSearchSelect({
    fetchOptions: (keyword) =>
      listResumes({ keyword, page_size: SELECT_PAGE_SIZE }).then((page) =>
        page.items.map(resumeOption),
      ),
    fetchById: (id) =>
      getResume(id)
        .then(resumeOption)
        .catch(() => null),
  });
}

/**
 * 简历远程搜索（投递队列用）：候选 = 本岗位生成的简历 + 收藏的简历。
 *
 * 排序按优先级：**本岗位的简历排最前**（为这条 JD 专门生成/改过的那份），收藏简历
 * 补在后面并去重——收藏是通用备选，默认不该盖过岗位版。标签后缀标出来源，避免同名
 * 简历分不清该投哪份。
 */
export function useResumeSearchSelectForJob(jobId: number | null) {
  return useRemoteSearchSelect({
    fetchOptions: async (keyword) => {
      const [forJob, favorites] = await Promise.all([
        jobId == null
          ? Promise.resolve([] as ResumeBrief[])
          : listResumes({ job_id: jobId, keyword, page_size: SELECT_PAGE_SIZE }).then(
              (page) => page.items,
            ),
        listResumes({ favorite: true, keyword, page_size: SELECT_PAGE_SIZE }).then(
          (page) => page.items,
        ),
      ]);
      const options = forJob.map((resume) => queueResumeOption(resume, jobId));
      const seen = new Set(options.map((option) => option.value));
      for (const resume of favorites) {
        if (seen.has(resume.id)) continue;
        seen.add(resume.id);
        options.push(queueResumeOption(resume, jobId));
      }
      return options;
    },
    fetchById: (id) =>
      getResume(id)
        .then((resume) => queueResumeOption(resume, jobId))
        .catch(() => null),
  });
}

/** 队列简历选项：岗位版标「本岗位」，其余收藏项标「收藏」，后缀只影响展示。 */
function queueResumeOption(
  resume: Pick<ResumeBrief, "id" | "title" | "job_id" | "favorite">,
  jobId: number | null,
): RemoteSelectOption {
  const option = resumeOption(resume);
  if (jobId != null && resume.job_id === jobId) {
    return { ...option, label: `${option.label}${t("hooksUi.option.resumeForJob")}` };
  }
  if (resume.favorite) {
    return { ...option, label: `${option.label}${t("hooksUi.option.resumeFavorite")}` };
  }
  return option;
}

/**
 * 简历远程搜索（限定某岗位 + 通用，0066）：**模拟面试的「关联简历」**用。
 *
 * 与 `useResumeSearchSelectForJob` 只差一个 `include_general`：候选人可能专门为这个岗位
 * 写了一份简历，也可能用一份通用简历，两种都该出现在可选范围里——但**别的岗位**的简历
 * 不该出现（面试官只会看到你提交的那份）。
 */
export function useResumeSearchSelectForJobOrGeneral(jobId: number | null) {
  return useRemoteSearchSelect({
    fetchOptions: (keyword) =>
      listResumes({
        job_id: jobId ?? undefined,
        include_general: true,
        keyword,
        page_size: SELECT_PAGE_SIZE,
      }).then((page) => page.items.map(resumeOption)),
    fetchById: (id) =>
      getResume(id)
        .then(resumeOption)
        .catch(() => null),
  });
}

export function useTrackSearchSelect() {
  return useRemoteSearchSelect({
    fetchOptions: (keyword) =>
      listTracksPage({ keyword }, 1, SELECT_PAGE_SIZE).then((page) => page.items.map(trackOption)),
    fetchById: (id) =>
      getTrack(id)
        .then(trackOption)
        .catch(() => null),
  });
}
