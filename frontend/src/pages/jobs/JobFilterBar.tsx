// SPDX-License-Identifier: Apache-2.0
/**
 * 岗位广场筛选工具栏：搜索/类型/状态/来源筛选 + 选择模式与各入口按钮。
 * （自 JobsPage 拆出：:362-487 整块逐字随迁，aria-label「来源筛选」「补齐详情」保留；
 * openMatchBatch/backfillDetails 等经 prop 直通页面 handler，零 api 导入。）
 */
import {
  HistoryOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  UndoOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Input, Select, Space, Tooltip } from "antd";
import type { ReactNode } from "react";
import { useState } from "react";
import { t } from "../../i18n";
import { JOB_STATUS_LABEL_KEYS, JOB_TYPE_LABEL_KEYS } from "../../i18n/enum/jobs";
import { useLocale } from "../../i18n/i18nContext";
import type { JobSortState } from "../../utils/jobSort";
import { DEFAULT_JOB_SORT_STATE, isDefaultJobSort } from "../../utils/jobSort";
import type { BatchAction } from "./jobFilterOptions";
import { SOURCE_KIND_OPTIONS } from "./jobFilterOptions";

export function JobFilterBar({
  keyword,
  setKeyword,
  setPage,
  jobType,
  setJobType,
  status,
  setStatus,
  sourceKind,
  setSourceKind,
  city,
  setCity,
  cityOptions,
  platform,
  setPlatform,
  platformOptions,
  batchAction,
  openMatchBatch,
  emptyDescriptionJobIds,
  backfilling,
  backfillDetails,
  setCandidatesOpen,
  setFormOpen,
  onImportCsv,
  importUrlEntry,
  sortState,
  applySort,
  selectionMode = false,
}: {
  keyword: string;
  setKeyword: (value: string) => void;
  setPage: (value: number) => void;
  jobType: string;
  setJobType: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  sourceKind: "" | "collected" | "manual";
  setSourceKind: (value: "" | "collected" | "manual") => void;
  city: string;
  setCity: (value: string) => void;
  /** 城市选项由页面从后端取，筛选条本身不 import api。 */
  cityOptions: string[];
  platform: string;
  setPlatform: (value: string) => void;
  /** 招聘平台选项由后端按岗位数聚合（清单见 GET /jobs/platforms）。 */
  platformOptions: string[];
  batchAction: BatchAction;
  /** `mode` 缺省是 compare（AI 对比选岗）；match 是逐岗位匹配度分析。 */
  openMatchBatch: (view?: "setup" | "history", mode?: "match" | "compare") => void;
  emptyDescriptionJobIds: number[];
  backfilling: boolean;
  backfillDetails: () => Promise<void>;
  setCandidatesOpen: (value: boolean) => void;
  setFormOpen: (value: boolean) => void;
  onImportCsv: () => void;
  /** 「按链接导入」按钮与弹窗（由页面注入，筛选条本身不 import api）。 */
  importUrlEntry?: ReactNode;
  /** 当前排序（E）：只存在页面状态里，用于「恢复默认排序」的禁用态。 */
  sortState: JobSortState;
  applySort: (next: JobSortState) => void;
  /**
   * 是否处于多选态。默认 `false`（既有调用方与单测都不用改）。
   *
   * 多选时**不渲染**「分析记录」：用户的原话是"多选的时候把分析记录删掉，在 AI 对比选岗
   * 界面看就好了"——勾选状态下这一栏的注意力属于批量动作，跳去历史记录会中断它。
   * 只隐藏入口、不删功能：`?match_batch=history` 深链仍可达（完成通知会跳它），
   * 非多选态下这颗按钮照旧出现。
   */
  selectionMode?: boolean;
}) {
  useLocale();
  // 搜索框受控：本地镜像同步外部 keyword（URL 带参等外部变化能回填输入框），
  // 点 × 清空时立即把筛选也清掉——之前非受控时清空后列表仍按旧关键词过滤。
  // Compiler 规范：镜像同步用渲染期守卫式调整。
  const [searchText, setSearchText] = useState(keyword);
  const [prevKeyword, setPrevKeyword] = useState(keyword);
  if (prevKeyword !== keyword) {
    setPrevKeyword(keyword);
    setSearchText(keyword);
  }

  // 下拉的 value 仍是落库的协议值，展示名在渲染期取（见 i18n/enum/jobs.ts）。
  const jobTypeOptions = Object.entries(JOB_TYPE_LABEL_KEYS).map(([value, key]) => ({
    value,
    label: t(key),
  }));
  const statusOptions = Object.entries(JOB_STATUS_LABEL_KEYS).map(([value, key]) => ({
    value,
    label: t(key),
  }));

  return (
    <div style={{ marginBottom: 16 }}>
      <Space wrap className="jobs-filter-bar">
        <Input.Search
          className="jobs-search-input"
          placeholder={t("jobsPage.filter.searchPlaceholder")}
          allowClear
          disabled={batchAction !== null}
          value={searchText}
          onChange={(event) => {
            const value = event.target.value;
            setSearchText(value);
            if (value === "" && keyword !== "") {
              setKeyword("");
              setPage(1);
            }
          }}
          onSearch={(value) => {
            setSearchText(value);
            setKeyword(value);
            setPage(1);
          }}
        />
        <Select
          aria-label={t("jobsPage.filter.jobTypeAria")}
          placeholder={t("jobsPage.filter.jobTypePlaceholder")}
          allowClear
          disabled={batchAction !== null}
          style={{ width: 110 }}
          value={jobType || undefined}
          onChange={(value) => {
            setJobType(value ?? "");
            setPage(1);
          }}
          options={jobTypeOptions}
        />
        <Select
          aria-label={t("jobsPage.filter.statusAria")}
          placeholder={t("jobsPage.filter.statusPlaceholder")}
          allowClear
          disabled={batchAction !== null}
          style={{ width: 110 }}
          value={status || undefined}
          onChange={(value) => {
            setStatus(value ?? "");
            setPage(1);
          }}
          options={statusOptions}
        />
        <Select
          aria-label={t("jobsPage.filter.sourceAria")}
          placeholder={t("jobsPage.filter.sourcePlaceholder")}
          allowClear
          disabled={batchAction !== null}
          style={{ width: 120 }}
          value={sourceKind || undefined}
          onChange={(value) => {
            setSourceKind((value ?? "") as "" | "collected" | "manual");
            setPage(1);
          }}
          options={SOURCE_KIND_OPTIONS.map((option) => ({
            value: option.value,
            label: t(option.labelKey),
          }))}
        />
        {/* 城市筛选项来自后端聚合（按岗位数排序）；空选项不出现，选中后与列表/全选共用同一筛选器。 */}
        <Select
          aria-label={t("jobsPage.filter.cityAria")}
          placeholder={t("jobsPage.filter.cityPlaceholder")}
          allowClear
          showSearch
          disabled={batchAction !== null}
          style={{ width: 120 }}
          value={city || undefined}
          onChange={(value) => {
            setCity(value ?? "");
            setPage(1);
          }}
          options={cityOptions.map((name) => ({ value: name, label: name }))}
        />
        {/* 招聘平台：从来源 URL / 来源字段 / 备注派生，历史岗位也能区分。 */}
        <Select
          aria-label={t("jobsPage.filter.platformAria")}
          placeholder={t("jobsPage.filter.platformPlaceholder")}
          allowClear
          showSearch
          disabled={batchAction !== null}
          style={{ width: 130 }}
          value={platform || undefined}
          onChange={(value) => {
            setPlatform(value ?? "");
            setPage(1);
          }}
          options={platformOptions.map((name) => ({ value: name, label: name }))}
        />
        {/* 进入选择模式的入口在行右键菜单的「批量选择」（R8）；退出选择已挪到
            BatchToolbar 的「全选全部岗位」右侧（用户要求，两行各归其位）。 */}
        {/* 开始分析在面板里确认（设置视图有「开始分析」按钮）；分析一律走后台任务，
            关掉面板/切页都不会中断，无需单独的"后台运行"入口。 */}
        <Button
          type="primary"
          disabled={batchAction !== null}
          onClick={() => openMatchBatch("setup")}
        >
          {t("jobsPage.filter.analyzeMatch")}
        </Button>
        {/* 逐岗位匹配度分析原来只在岗位详情里，选一批岗位要开 N 次详情。放到这里：
            勾选后一次分析所选（1–50 个），不勾选会先引导进入选择模式。 */}
        <Button
          disabled={batchAction !== null}
          onClick={() => openMatchBatch("setup", "match")}
        >
          {t("jobsPage.filter.matchAnalysis")}
        </Button>
        {/* 多选态不渲染「分析记录」（用户要求）：勾选中这一栏只服务批量动作，
            历史记录请到「AI 对比选岗 / 批量匹配分析」界面看。非多选态保留入口（深链也仍然可达）。 */}
        {selectionMode ? null : (
          <Button
            icon={<HistoryOutlined />}
            disabled={batchAction !== null}
            onClick={() => openMatchBatch("history")}
          >
            {t("jobsPage.filter.matchHistory")}
          </Button>
        )}
        <Button
          icon={<InboxOutlined />}
          disabled={batchAction !== null}
          onClick={() => setCandidatesOpen(true)}
        >
          {t("jobsPage.filter.candidates")}
        </Button>
        {emptyDescriptionJobIds.length > 0 && (
          // 只在有 JD 为空的岗位时才出现——否则按钮点了什么也不会发生。
          // 显式 aria-label：antd 会给纯中文按钮做字距处理，用文本当查询条件可能找不到。
          <Button
            icon={<ReloadOutlined />}
            aria-label={t("jobsPage.filter.backfill")}
            disabled={batchAction !== null}
            loading={backfilling}
            onClick={() => void backfillDetails()}
          >
            {t("jobsPage.filter.backfill")}
          </Button>
        )}
        {importUrlEntry}
        <Button icon={<UploadOutlined />} disabled={batchAction !== null} onClick={onImportCsv}>
          {t("jobsPage.filter.importCsv")}
        </Button>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={batchAction !== null}
          onClick={() => setFormOpen(true)}
        >
          {t("jobsPage.filter.addManual")}
        </Button>
        {/* 恢复默认排序（E）：排序一旦点上列头就没有"取消"的可视入口，这里给一个
            明确的退路；点击同时回到第 1 页（停在第 3 页看默认排序的前几条没有意义）。 */}
        <Tooltip
          title={
            isDefaultJobSort(sortState)
              ? t("jobsPage.filter.sortResetHintDefault")
              : t("jobsPage.filter.sortResetHint")
          }
        >
          <Button
            icon={<UndoOutlined />}
            aria-label={t("jobsPage.filter.sortReset")}
            disabled={batchAction !== null || isDefaultJobSort(sortState)}
            onClick={() => applySort(DEFAULT_JOB_SORT_STATE)}
          >
            {t("jobsPage.filter.sortReset")}
          </Button>
        </Tooltip>
      </Space>
    </div>
  );
}
