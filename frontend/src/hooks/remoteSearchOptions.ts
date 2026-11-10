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
 * 简历远程搜索（限定某岗位 + 收藏，P0-1）：投递队列条目的简历选择用。
 *
 * 候选 = **该岗位关联过的简历** + **收藏的简历**（2026-11-09 补回收藏这一半）。
 *
 * 为什么必须是两路并集：串行只查 `job_id` 时，用户收藏的通用母版根本不出现——
 * 而"挑一份顺手的简历投这个岗位"正是收藏的意义。1.x 早有这条（`Promise.all` 两路
 * 并集 + 去重 + 后缀标签），2.0 移植时只留了 `job_id` 一路，用户实测「和 1.0 不一样，
 * 1.0 是把收藏的简历都显示」。
 *
 * 两路各自带 `page_size`，合并后按 id 去重、先本岗位后收藏（用户更容易在自己的岗位
 * 简历里找到目标）；同一份既属本岗位又是收藏时只出现一次，且标「本岗位」。
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

/**
 * 队列简历选项：本岗位的标「本岗位」，其余收藏项标「收藏」。
 *
 * 后缀只影响展示——`value` 仍是简历 id，所以不影响任何写库口径。
 * 两份都命中的（本岗位 + 收藏）只标「本岗位」：那是更强的语义（这份简历就是为它写的）。
 */
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
