// SPDX-License-Identifier: Apache-2.0
/**
 * AI jobs page -- native (self-hosted) mode view.
 *
 * Sits beside `LegacyAiJobsView` (the sidecar path); `AiJobsPage` picks one based on
 * the `job_hunt_backend` setting. The two have different data sources:
 *
 * - legacy: calls the external BossHunter engine (`/api/ai-jobs/*`), requires the engine;
 * - this view: WorkTong collects by itself (`/api/job-hunt/collect`) -> persists into the
 *   job library -> enqueues through the existing apply desk.
 *
 * Deliberately NOT done here:
 * - no greeting editing (the apply desk's editor + gate is the single entry point);
 * - no delivery execution (the apply desk owns batches, breakers, failure classes);
 * - no scoring UI (the job library's match analysis is the same result set).
 */
import { Alert, Button, Card, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import { useJobHuntNative } from "../../hooks/useJobHuntNative";
import ScorePanel from "./ScorePanel";
import BlocklistCard from "./BlocklistCard";
import { useCollectTask } from "../../hooks/useCollectTask";
import type { JobHuntStatus } from "../../types/jobHunt";
import type { JobList } from "../../types/job";
import { useCandidates } from "../../hooks/useCandidates";
import { usePersistentNumber } from "../../hooks/usePersistentNumber";
import { usePersistentValue } from "../../hooks/usePersistentValue";
import CollectResultPanel from "../../features/apply/CollectResultPanel";
import { startBrowser } from "../../api/apply";
import CollectProgressPanel from "./CollectProgressPanel";
import HuntFilterForm, { DEFAULT_FILTERS, DEFAULT_KEYWORDS } from "./HuntFilterForm";
import HuntSourceRow from "./HuntSourceRow";
import {
  HUNT_STORAGE_KEYS,
  normalizeBoolean,
  normalizeCity,
  normalizeFilters,
  normalizeKeywords,
  normalizeMaxPages,
  normalizeSalary,
  normalizeSiteKey,
} from "./huntFilterStorage";
import CompanyName from "../common/CompanyName";

const { Text, Title } = Typography;

interface Props {
  status: JobHuntStatus;
}

export default function NativeJobHuntView({ status }: Props) {
  const navigate = useNavigate();
  // Subscribe to locale changes: module-level t() does not re-render on its own.
  useLocale();
  const { state, enqueue, reload } = useJobHuntNative(status);
  const collectTask = useCollectTask();
  const task = collectTask.state.task;
  const collecting = task?.status === "running" || task?.status === "paused";
  const result = state.lastResult;

  // ---- 搜索条件全部持久化 ----
  //
  // 这些都是**用户填过的判断**（搜什么词、卡哪档经验、什么薪资区间），不是页面临时状态：
  // 采集本来就是反复微调的过程（收紧一次、放宽一次再看），每次刷新都回到出厂值等于
  // 把上一轮的判断作废。所以全部走 localStorage，打开页面就是上次的条件。
  //
  // 归一化函数与存储键集中在 `huntFilterStorage`：存进去的东西会被旧版本形状/手改/
  // 另一个标签页弄脏，而渲染处直接 `.map()`，不校验就是白屏。
  const [siteKey, setSiteKey] = usePersistentValue(
    HUNT_STORAGE_KEYS.siteKey,
    status.platforms[0]?.key ?? "boss",
    (raw) => normalizeSiteKey(raw, status.platforms[0]?.key ?? "boss"),
  );
  // 多关键词（出厂预填 4 个）：单关键词翻到底就那十几条，第二轮开始全是重复。
  const [keywords, setKeywords] = usePersistentValue<string[]>(
    HUNT_STORAGE_KEYS.keywords,
    DEFAULT_KEYWORDS,
    normalizeKeywords,
  );
  const [filters, setFilters] = usePersistentValue<Record<string, string[]>>(
    HUNT_STORAGE_KEYS.filters,
    DEFAULT_FILTERS,
    normalizeFilters,
  );
  // 最新优先（BOSS 的 sortType=2）：不勾的话每次翻到的都是默认排序里的同一批。
  const [newestFirst, setNewestFirst] = usePersistentValue<boolean>(
    HUNT_STORAGE_KEYS.newestFirst,
    true,
    (raw) => normalizeBoolean(raw, true),
  );
  // 薪资区间（K）；0 = 不限。BOSS 没有自定义区间参数，后端会先拉覆盖区间的档位并集、
  // 采回来再本地精筛到这个区间。**两个输入框共用一条存储记录**：分成两个键的话，
  // 用户先改 min 再改 max 的中间态会被当成"min > max"。
  const [salary, setSalary] = usePersistentValue<{ min: number; max: number }>(
    HUNT_STORAGE_KEYS.salary,
    { min: 0, max: 0 },
    normalizeSalary,
  );
  const salaryMinK = salary.min;
  const salaryMaxK = salary.max;
  const setSalaryRange = (min: number, max: number) => setSalary({ min, max });
  const [city, setCity] = usePersistentValue<string>(
    HUNT_STORAGE_KEYS.city,
    t("aiJobs.native.defaultCity"),
    (raw) => normalizeCity(raw, t("aiJobs.native.defaultCity")),
  );
  const [maxPages, setMaxPages] = usePersistentValue<number>(
    HUNT_STORAGE_KEYS.maxPages,
    1,
    normalizeMaxPages,
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [queued, setQueued] = useState(0);
  // 采集即评分（默认开）。关掉 = 只落备选区不评分，分数列显示「未评分」。
  // 同样持久化：这是用户对流程的选择，不是临时开关。
  const [autoScore, setAutoScore] = usePersistentValue<boolean>(
    HUNT_STORAGE_KEYS.autoScore,
    true,
    (raw) => normalizeBoolean(raw, true),
  );
  // 分数线（分水岭）：不低于它的排上面。**持久化**——这是用户的筛选偏好，
  // 刷新一次就回到 70 会让人以为设置没生效。
  const [threshold, setThreshold] = usePersistentNumber("aiJobs.scoreThreshold", 70);
  // 黑名单折叠起来：它是一年改两次的长效配置，不该占着首屏。
  const [blocklistOpen, setBlocklistOpen] = useState(false);

  // 备选岗位列表：既是「导入/已评分」两个计数的来源，也是下面候选面板的数据源。
  // 采集任务进入终态时自动重拉一次（`task?.status`），评分任务结束也重拉一次。
  const {
    data: candidates,
    refresh: refreshCandidates,
    watchScoreTask,
    scoreTask,
  } = useCandidates();
  const scoreRunning = Boolean(scoreTask?.running);

  // 刷新页面后把后台还在跑的采集任务接回来（进度原本只活在内存里）。
  const restoreCollectTask = collectTask.restore;
  useEffect(() => {
    void restoreCollectTask();
  }, [restoreCollectTask]);

  // 采集链路的「落库 → 补 JD → 评分」都在后台线程里跑完；任务快照里
  // `score_started` 为真时评分任务才真的起来了，这时开始轮询分数。
  useEffect(() => {
    if (task?.score_started) watchScoreTask();
  }, [task?.score_started, watchScoreTask]);

  // 流程条要的是「这一批里」的进度，不是全库累计：
  // - imported：已导入岗位广场的条数
  // - scored：已评出分数的条数
  const importedCandidates = candidates.filter((row) => row.status === "imported").length;
  const scoredCandidates = candidates.filter(
    (row) => row.score_total !== null && row.score_total !== undefined,
  ).length;

  // 采集失败最常见的原因是「投递专用浏览器没启动」（后端 503）。按钮直接给出
  // 补救动作，比让用户自己去投递台找入口强。
  const [startingBrowser, setStartingBrowser] = useState(false);
  const onStartBrowser = async () => {
    setStartingBrowser(true);
    try {
      await startBrowser(true);
      // 浏览器起来后再自动重试一次采集：用户点这个按钮的意图就是"我要采集"。
      await onCollect();
    } catch {
      // 失败由 collectTask.state.error 与浏览器状态共同反映，这里不重复弹。
    } finally {
      setStartingBrowser(false);
    }
  };

  const onCollect = async () => {
    setQueued(0);
    await collectTask.start({
      site_key: siteKey,
      // 单词位留给"只有一个关键词"的兼容场景，多词走 keyword_list。
      keywords: keywords.length === 1 ? keywords[0] : "",
      keyword_list: keywords,
      filters,
      sort: newestFirst ? "newest" : "default",
      salary_min_k: salaryMinK,
      salary_max_k: salaryMaxK,
      city,
      max_pages: maxPages,
      // 默认都开：采完自动落备选区 + 补 JD + 评分，用户按分数挑——这正是
      // 「采集评分后再决定导入」那条链路。关掉 auto_score 就是只入库不评分。
      persist: true,
      auto_score: autoScore,
    });
  };

  const onEnqueue = async () => {
    if (!selected.length) return;
    try {
      const count = await enqueue(selected);
      setQueued(count);
      setSelected([]);
    } catch {
      // Same as above.
    }
  };

  const columns: ColumnsType<JobList> = [
    { title: t("aiJobs.native.col.title"), dataIndex: "title", ellipsis: true, width: 240 },
    {
      title: t("aiJobs.native.col.company"),
      dataIndex: "company",
      ellipsis: true,
      width: 160,
      // 公司名可点查风鸟（系统默认浏览器）。截断名/短名渲染成纯文本+说明。
      render: (value: string) => <CompanyName name={value} />,
    },
    { title: t("aiJobs.native.col.location"), dataIndex: "location", ellipsis: true, width: 150 },
    {
      title: t("aiJobs.native.col.salary"),
      dataIndex: "salary",
      width: 120,
      render: (value: string) => value || <Text type="secondary">—</Text>,
    },
    {
      title: t("aiJobs.native.col.status"),
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{value}</Tag>,
    },
  ];



  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 两个 error 是不同来源，必须都显示：
          - state.error 来自 useJobHuntNative（入队/导入等）
          - collectTask.state.error 来自采集任务启动本身（浏览器没启动之类的 503）
          以前只显示前者，于是"点开始采集 → 转一下 → 什么都没发生"——错误被吞了。 */}
      {state.error && <Alert type="error" showIcon title={state.error} />}
      {collectTask.state.error && (
        <Alert
          type="error"
          showIcon
          title={t("aiJobs.native.collectFailed")}
          description={collectTask.state.error}
          action={
            <Button size="small" onClick={() => void onStartBrowser()} loading={startingBrowser}>
              {t("aiJobs.native.startBrowser")}
            </Button>
          }
        />
      )}

      {queued > 0 && (
        <Alert
          type="success"
          showIcon
          title={t("aiJobs.native.queuedHint", { count: queued })}
          action={
            <Button size="small" type="primary" onClick={() => navigate("/apply")}>
              {t("aiJobs.native.goApply")}
            </Button>
          }
        />
      )}

      {/* ---------- 第一栏：筛选与采集（先定条件，再采集）----------
          用户的原话是「把所有筛选条件放在前面」。这里是同一条逻辑：平台/关键词/城市/
          页数/黑名单/分数线都在采集之前定好，采完不需要再回头翻设置。 */}
      <Card
        size="small"
        title={
          <Space size={8}>
            <Title level={5} style={{ margin: 0 }}>
              {t("aiJobs.hunt.filtersTitle")}
            </Title>
            <Text type="secondary">{t("aiJobs.hunt.filtersHint")}</Text>
          </Space>
        }
      >
        {/* ---------- 分区一：搜索条件（搜什么、筛什么）----------
            放在最上面：这是用户每轮都要调的东西（换关键词、调经验）。 */}
        <div className="hunt-section">
          <div className="hunt-section-title">
            <Text strong>{t("aiJobs.hunt.sectionQuery")}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("aiJobs.hunt.sectionQueryHint")}
            </Text>
          </div>
          <HuntFilterForm
            keywords={keywords}
            onKeywordsChange={setKeywords}
            filters={filters}
            onFiltersChange={setFilters}
            newestFirst={newestFirst}
            onNewestFirstChange={setNewestFirst}
            salaryMinK={salaryMinK}
            salaryMaxK={salaryMaxK}
            onSalaryRangeChange={setSalaryRange}
            unapplied={task?.unapplied_filters ?? []}
          />
        </div>

        <HuntSourceRow
          status={status}
          siteKey={siteKey}
          onSiteKeyChange={setSiteKey}
          city={city}
          onCityChange={setCity}
          maxPages={maxPages}
          onMaxPagesChange={setMaxPages}
          threshold={threshold}
          onThresholdChange={setThreshold}
          autoScore={autoScore}
          onAutoScoreChange={setAutoScore}
          keywords={keywords.length}
          collecting={collecting}
          starting={collectTask.state.starting}
          onCollect={() => void onCollect()}
          paused={task?.status === "paused"}
          onPause={() => void collectTask.control("pause")}
          onResume={() => void collectTask.control("resume")}
          onStop={() => void collectTask.control("stop")}
        />

        {/* 黑名单折叠          </Space>
        </div>

        {/* 黑名单折叠：长效配置，不该占首屏。展开后才渲染（省一次接口调用）。 */}
        <div style={{ marginTop: 12 }}>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setBlocklistOpen((v) => !v)}>
            {blocklistOpen ? "− " : "+ "}
            {t("aiJobs.hunt.blocklistToggle")}
          </Button>
          {blocklistOpen && (
            <div style={{ marginTop: 8 }}>
              <BlocklistCard />
            </div>
          )}
        </div>

        {(task || scoreRunning) && (
          <CollectProgressPanel
            task={task}
            scoreTask={scoreTask}
            collecting={collecting}
            onStartBrowser={() => void onStartBrowser()}
            startingBrowser={startingBrowser}
          />
        )}

        {result && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">
              {t("aiJobs.native.collectSummary", {
                inserted: result.persisted.inserted,
                skipped: result.persisted.skipped_duplicate,
                pages: result.pages_fetched,
              })}
            </Text>
            {result.persisted.errors.length > 0 && (
              <Alert
                style={{ marginTop: 8 }}
                type="warning"
                showIcon
                title={t("aiJobs.native.persistErrors", {
                  count: result.persisted.errors.length,
                })}
                description={result.persisted.errors.slice(0, 5).join(t("aiJobs.native.errorSeparator"))}
              />
            )}
          </div>
        )}
      </Card>

      {/* ---------- 第二栏：采到的岗位（按分数线分水岭）----------
          用户要的是「分数高的在上面，优先级最高；低的在下面」。
          这条界线由用户自己设（第一栏的分数线输入框），不是写死的 70。 */}
      <Card
        size="small"
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              {t("aiJobs.native.candidateTitle")}
            </Title>
            <Text type="secondary">{candidates.length}</Text>
          </Space>
        }
        extra={
          <Button size="small" onClick={() => void refreshCandidates()} loading={state.loadingJobs}>
            {t("aiJobs.native.refresh")}
          </Button>
        }
      >
        <CollectResultPanel
          taskId={null}
          disabled={collecting}
          scoreThreshold={threshold}
          refreshKey={`${candidates.length}-${scoredCandidates}-${importedCandidates}`}
          onImported={() => {
            void refreshCandidates();
            void reload();
          }}
        />
      </Card>

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              {t("aiJobs.native.poolTitle")}
            </Title>
            <Text type="secondary">{state.jobs.length}</Text>
          </Space>
        }
        size="small"
        extra={
          <Space>
            <Text type="secondary">
              {t("aiJobs.native.selected", { n: selected.length })}
            </Text>
            <Button
              type="primary"
              disabled={!selected.length}
              loading={state.enqueueing}
              onClick={() => void onEnqueue()}
            >
              {t("aiJobs.native.enqueue")}
            </Button>
          </Space>
        }
      >
        <Table<JobList>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={state.jobs}
          loading={state.loadingJobs}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: (keys) => setSelected(keys as number[]),
          }}
          locale={{ emptyText: <Empty description={t("aiJobs.native.empty")} /> }}
        />
      </Card>

      {selected.length === 1 && <ScorePanel jobId={selected[0]} />}
      {selected.length > 1 && (
        <Alert
          type="info"
          showIcon
          title={t("aiJobs.native.scoreHintMulti", { count: selected.length })}
        />
      )}

      <Alert type="info" showIcon title={t("aiJobs.native.replyNotAvailable")} />
    </div>
  );
}
