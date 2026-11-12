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
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
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
import CollectResultPanel from "../apply/CollectResultPanel";
import { startBrowser } from "../../api/apply";
import CollectProgressPanel from "./CollectProgressPanel";
import HuntFilterForm, { DEFAULT_FILTERS, DEFAULT_KEYWORDS } from "./HuntFilterForm";

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

  const [siteKey, setSiteKey] = useState(status.platforms[0]?.key ?? "boss");
  // 多关键词（默认预填 4 个）：单关键词翻到底就那十几条，第二轮开始全是重复。
  const [keywords, setKeywords] = useState<string[]>(DEFAULT_KEYWORDS);
  const [filters, setFilters] = useState<Record<string, string[]>>(DEFAULT_FILTERS);
  // 最新优先（BOSS 的 sortType=2）：不勾的话每次翻到的都是默认排序里的同一批。
  const [newestFirst, setNewestFirst] = useState(true);
  // 薪资区间（K）；0 = 不限。BOSS 没有自定义区间参数，后端会先拉覆盖区间的档位并集、
  // 采回来再本地精筛到这个区间。
  const [salaryMinK, setSalaryMinK] = useState(0);
  const [salaryMaxK, setSalaryMaxK] = useState(0);
  const [city, setCity] = useState(t("aiJobs.native.defaultCity"));
  const [maxPages, setMaxPages] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [queued, setQueued] = useState(0);
  // 采集即评分（默认开）。关掉 = 只落备选区不评分，分数列显示「未评分」。
  const [autoScore, setAutoScore] = useState(true);
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
    { title: t("aiJobs.native.col.company"), dataIndex: "company", ellipsis: true, width: 160 },
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
      {state.error && <Alert type="error" showIcon message={state.error} />}
      {collectTask.state.error && (
        <Alert
          type="error"
          showIcon
          message={t("aiJobs.native.collectFailed")}
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
          message={t("aiJobs.native.queuedHint", { count: queued })}
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
            onSalaryRangeChange={(min, max) => {
              setSalaryMinK(min);
              setSalaryMaxK(max);
            }}
            unapplied={task?.unapplied_filters ?? []}
          />
        </div>

        {/* ---------- 分区二：数据源与动作（去哪搜、搜多少、开始）----------
            与上面分开：这一组是"这次跑哪儿、跑多久"，改得没那么频繁。 */}
        <div className="hunt-section">
          <div className="hunt-section-title">
            <Text strong>{t("aiJobs.hunt.sectionSource")}</Text>
          </div>
          <div className="hunt-source-row">
            <div className="hunt-field">
              <span className="hunt-field-label">{t("aiJobs.hunt.platform")}</span>
              <div className="hunt-field-control">
                <Select
                  value={siteKey}
                  onChange={setSiteKey}
                  style={{ width: "100%" }}
                  options={status.platforms.map((platform) => ({
                    value: platform.key,
                    label: platform.name,
                  }))}
                  aria-label={t("aiJobs.hunt.platform")}
                />
              </div>
            </div>
            <div className="hunt-field">
              <span className="hunt-field-label">{t("aiJobs.native.city")}</span>
              <div className="hunt-field-control">
                <Input
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  aria-label={t("aiJobs.native.city")}
                />
              </div>
            </div>
            <div className="hunt-field">
              <span className="hunt-field-label">{t("aiJobs.hunt.pagesLabel")}</span>
              <div className="hunt-field-control">
                <Select
                  value={maxPages}
                  onChange={setMaxPages}
                  style={{ width: "100%" }}
                  options={[1, 2, 3, 5].map((n) => ({
                    value: n,
                    label: t("aiJobs.native.pages", { n }),
                  }))}
                  aria-label={t("aiJobs.hunt.pagesLabel")}
                />
              </div>
            </div>
            <div className="hunt-field hunt-field--narrow">
              <Tooltip title={t("aiJobs.hunt.thresholdHint")}>
                <span className="hunt-field-label">{t("aiJobs.hunt.threshold")}</span>
              </Tooltip>
              <div className="hunt-field-control">
                <InputNumber
                  value={threshold}
                  onChange={(value) => setThreshold(typeof value === "number" ? value : 70)}
                  min={0}
                  max={100}
                  step={5}
                  style={{ width: "100%" }}
                  aria-label={t("aiJobs.hunt.threshold")}
                />
              </div>
            </div>
          </div>

          <Space wrap size={12} style={{ marginTop: 12 }}>
            <Tooltip title={t("aiJobs.native.autoScoreHint")}>
              <Checkbox checked={autoScore} onChange={(e) => setAutoScore(e.target.checked)}>
                {t("aiJobs.native.autoScore")}
              </Checkbox>
            </Tooltip>
            <Button
              type="primary"
              loading={collectTask.state.starting || collecting}
              disabled={collecting}
              onClick={() => void onCollect()}
            >
              {t("aiJobs.native.collect")}
            </Button>
            {collecting && (
              <>
                {task?.status === "paused" ? (
                  <Button onClick={() => void collectTask.control("resume")}>
                    {t("aiJobs.pipeline.resume")}
                  </Button>
                ) : (
                  <Button onClick={() => void collectTask.control("pause")}>
                    {t("aiJobs.pipeline.pause")}
                  </Button>
                )}
                <Button danger onClick={() => void collectTask.control("stop")}>
                  {t("aiJobs.pipeline.stop")}
                </Button>
              </>
            )}
            {/* 组合数提示：4 词 × 3 页 = 12 次翻页，点之前先让人知道要跑多久。 */}
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("aiJobs.hunt.comboHint", {
                keywords: keywords.length || 1,
                pages: maxPages,
                total: (keywords.length || 1) * maxPages,
              })}
            </Text>
          </Space>
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
                message={t("aiJobs.native.persistErrors", {
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
          message={t("aiJobs.native.scoreHintMulti", { count: selected.length })}
        />
      )}

      <Alert type="info" showIcon message={t("aiJobs.native.replyNotAvailable")} />
    </div>
  );
}
