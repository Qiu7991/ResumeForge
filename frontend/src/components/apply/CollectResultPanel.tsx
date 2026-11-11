// SPDX-License-Identifier: Apache-2.0
/**
 * 「本次采集结果」：一次采集采到的东西先陈列在这里，**勾选后才进岗位广场**。
 *
 * 为什么不让采集直接入库：采集条件（关键词 + 城市）本来就宽，噪声是常态。直接入库的代价是
 * 用户只能去岗位广场一条条删；"先陈列、再挑选"把这个决定权交还给用户，也让"这次到底采到了
 * 什么"有个地方可看。
 *
 * 导入结果是**逐条**反馈的，而且用常驻提示而不是一条飘过的 toast：勾了 10 条、其中 3 条
 * 岗位广场里已经有了——用户需要知道是哪 3 条、以及为什么，否则他只会看到"导入了 7 条"，
 * 然后去岗位广场里数不出来。
 */
import { LinkOutlined, SendOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Space, Table, Tag, Tooltip, Typography } from "antd";
import EmptyState from "../common/EmptyState";
import type { TableColumnsType } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { importCandidateJobs, listCandidateJobs } from "../../api/candidateJob";
import type { CandidateJobSort } from "../../api/candidateJob";
import CandidateScoreCell from "../jobs/candidate/CandidateScoreCell";
import { useApi } from "../../hooks/useApi";
import { bulkEnqueueJobs, bulkEnqueueSummary } from "./queue/bulkEnqueue";
import { formatDateTime } from "../../utils/format";
import PageSkeleton from "../common/PageSkeleton";
import type { CandidateJob, CandidateJobImportResult } from "../../types";
import { t, type MessageKey } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

interface Props {
  /**
   * 当前采集批次 id；**为空也照常渲染**（这块列的是所有批次的候选）。
   *
   * 它现在只有两个用途：批次切换时清空勾选、以及让宿主在任务结束时通过 `refreshKey`
   * 触发重拉。**不要**再拿它决定"要不要渲染"——那正是 2026-11-10 那个"切页回来看不见
   * 候选"的成因。
   */
  taskId: number | null;
  /** 采集/投递正在跑时禁用导入。 */
  disabled?: boolean;
  /** 同一批次的状态或完成时间变化时重新拉取，避免启动时的空结果一直留在页面上。 */
  refreshKey?: string | number;
  /** 导入完成后通知外层（例如让采集记录里的计数跟着更新）。 */
  onImported?: (result: CandidateJobImportResult) => void;
}

/**
 * 导入结果的 outcome（协议值）→ 说明文案的 key。
 *
 * 键是后端返回的**协议值**，不翻译（`isProblemOutcome` 与入队过滤都靠它们判定）；
 * 值是文案 key，由使用处 `t()`——模块作用域里调 `t()` 会把语言固定在模块求值那一刻。
 */
const OUTCOME_LABEL_KEYS: Record<string, MessageKey> = {
  duplicate: "collectResult.outcome.duplicate",
  trashed: "collectResult.outcome.trashed",
  invalid: "collectResult.outcome.invalid",
  missing: "collectResult.outcome.missing",
};

/**
 * 一条导入结果算不算「没有建成岗位」。
 *
 * 提示语与下面的清单必须用同一份判定：两边各写一遍 `!== "imported"`，提示说 3 个、
 * 清单列 2 条这种事迟早会发生。
 */
function isProblemOutcome(item: { outcome: string }): boolean {
  return item.outcome !== "imported";
}

export default function CollectResultPanel({
  taskId,
  disabled = false,
  refreshKey = 0,
  onImported,
}: Props) {
  // 本组件用模块级 t()：必须订阅语言变化，否则切语言后这一块不重渲染。
  useLocale();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [importing, setImporting] = useState(false);
  const [lastResult, setLastResult] = useState<CandidateJobImportResult | null>(null);

  // 拉**全部批次**的待处理候选（2026-11-10 用户要求）：
  // 以前只列「本次采集结果」，于是昨天采的 46 条躺在暂存区里、界面上看不见，用户以为丢了。
  // 现在一次列完"我采集过的所有岗位"，省得再去「采集记录」翻。
  //
  // `status: "pending"` 仍然只列**还没导入岗位广场**的：已导入的岗位在岗位广场里，
  // 在这里重复列出来只会让这一块越来越长。（"已在投递台"的标注另算，见列定义。）
  //
  // **不再依赖 `taskId`**（2026-11-10 第二次修）：这段列的是"所有批次的候选"，
  // 跟"现在有没有正在跑/刚跑完的采集任务"无关。以前 `taskId` 为空就 `return null`，
  // 于是用户切到别的页、再切回来（当前任务已被收尾、`collectTask` 变 null）时，
  // 整块候选列表凭空消失——他以为数据没了。
  //
  // 排序走**服务端**（`sort` 参数）：本表是客户端分页，本地排序只能排当前页，
  // 用户按分数挑的时候看到的是"这一页里最高的"，不是"所有候选里最高的"。
  const [sort, setSort] = useState<CandidateJobSort>("created_desc");
  const { data, loading, error, reload } = useApi<CandidateJob[]>(
    () => listCandidateJobs({ status: "pending", sort }),
    [refreshKey, sort],
    // 切回本页时重新拉一次：候选可能在别处被导入/删掉了（用户实测"切页回来内容没了"，
    // 反过来"切页回来显示的是旧列表"同样不该发生）。`minIntervalMs` 用默认 30s——
    // 频繁切页不该把接口打满。
    { refetchOnFocus: {} },
  );

  // 采集批次切换时清空勾选与导入反馈：跨批次保留勾选会把上一批的 id 带进下一次导入。
  // Compiler 规范：随 taskId 变化的重置用渲染期守卫式调整（哨兵 null 覆盖挂载场景）。
  const [prevTaskId, setPrevTaskId] = useState(taskId);
  if (prevTaskId !== taskId) {
    setPrevTaskId(taskId);
    setSelectedIds([]);
    setLastResult(null);
  }

  const candidates = data ?? [];

  /** 导入按钮的文案/无障碍名称：带上选中数量，用户不必去数勾了几个。 */
  const importLabel = (count: number): string =>
    count > 0
      ? t("collectResult.import.labelWithCount", { count })
      : t("collectResult.import.label");

  const doImport = async () => {
    if (selectedIds.length === 0) return;
    setImporting(true);
    try {
      const result = await importCandidateJobs(selectedIds);
      setLastResult(result);
      if (result.imported > 0) {
        // 带下一步动作的成功提示：导入的终点是岗位广场，直接给入口（message 的 content
        // 支持 ReactNode；navigate 用的是本组件闭包里的引用，不依赖挂载点的 Router 上下文）。
        message.success({
          content: (
            <span>
              {t("collectResult.import.success", { count: result.imported })}
              <Button
                type="link"
                size="small"
                style={{ padding: 0 }}
                onClick={() => navigate("/jobs")}
              >
                {t("collectResult.import.successAction")}
              </Button>
            </span>
          ),
          duration: 6,
        });
      } else {
        message.warning(
          t("collectResult.import.noneAdded", {
            count: result.results.filter(isProblemOutcome).length,
          }),
        );
      }
      setSelectedIds([]);
      await reload();
      onImported?.(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("collectResult.import.failed"));
    } finally {
      setImporting(false);
    }
  };

  // 海投效率路径：导入岗位广场 + 立即加入投递队列，一步到位（用户实测反馈）。
  // 只有 imported / duplicate 会带回 job_id（trashed/invalid/missing 没有岗位可入队），
  // 这几条自动跳过并在结果里说明；入队带显式确认（未分析/真实缺口），投递前仍核对准入。
  const doImportAndQueue = async () => {
    if (selectedIds.length === 0) return;
    setImporting(true);
    try {
      const result = await importCandidateJobs(selectedIds);
      setLastResult(result);
      const jobIds = (result.results ?? [])
        .filter(
          (item) => (item.outcome === "imported" || item.outcome === "duplicate") && item.job_id,
        )
        .map((item) => item.job_id as number);
      if (jobIds.length === 0) {
        message.warning(t("collectResult.queue.nothingToQueue"));
        await reload();
        return;
      }
      const outcome = await bulkEnqueueJobs(jobIds);
      const summary = t("collectResult.queue.success", {
        count: result.imported,
        summary: bulkEnqueueSummary(outcome),
      });
      message.success({
        content: (
          <span>
            {summary}
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => navigate("/apply?tab=queue")}
            >
              {t("collectResult.queue.successAction")}
            </Button>
          </span>
        ),
        duration: 6,
      });
      setSelectedIds([]);
      await reload();
      onImported?.(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("collectResult.queue.failed"));
    } finally {
      setImporting(false);
    }
  };

  const columns: TableColumnsType<CandidateJob> = [
    {
      title: t("collectResult.column.title"),
      dataIndex: "title",
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{value || t("collectResult.row.unknownTitle")}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.company || t("collectResult.row.unknownCompany")}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: t("collectResult.column.location"),
      dataIndex: "location",
      width: 140,
      render: (value: string) => value || "—",
    },
    {
      title: t("collectResult.column.salary"),
      dataIndex: "salary",
      width: 130,
      render: (value: string) => value || "—",
    },
    {
      // 采集时间（2026-11-10）：用户要看的是"这条是什么时候采的"，靠它区分今天新采的
      // 与之前几轮留下的。手动粘贴的候选没有采集时间，如实显示「手动添加」。
      title: t("collectResult.column.collectedAt"),
      dataIndex: "collected_at",
      width: 130,
      render: (value: string | null | undefined) =>
        value ? formatDateTime(value) : t("collectResult.cell.manual"),
    },
    {
      // 已在投递台（2026-11-10）：服务端算好下发（`in_apply_queue`）。
      // **不拿 `imported_job_id` 代替**：那只说明"导入过岗位广场"，导入后又被移出队列的
      // 岗位必须显示成「未入队」，否则用户以为它还在队里。
      title: t("collectResult.column.queue"),
      dataIndex: "in_apply_queue",
      width: 110,
      render: (value: boolean | undefined) =>
        value ? (
          <Tag color="green">{t("collectResult.cell.inQueue")}</Tag>
        ) : (
          <Typography.Text type="secondary">{t("collectResult.cell.notInQueue")}</Typography.Text>
        ),
    },
    {
      // 匹配分（2026-11-11 方案 3）：采集后后台自动评分，用户按分数挑要导入哪些。
      // 分数由列表接口一起下发（`score_total`/`score_error`），**不逐行请求**。
      // 排序走服务端（`sort=score_desc`）——本页分页，本地排序必错。
      title: t("aiJobs.candidate.score"),
      dataIndex: "score_total",
      width: 100,
      sorter: true,
      render: (_value: number | null | undefined, row) => (
        <CandidateScoreCell score={row.score_total} error={row.score_error} />
      ),
    },
    {
      title: t("collectResult.column.source"),
      dataIndex: "source_url",
      width: 90,
      render: (value: string, row) =>
        value ? (
          <Typography.Link href={value} target="_blank" rel="noopener noreferrer">
            <LinkOutlined /> {t("collectResult.action.openSource")}
          </Typography.Link>
        ) : (
          <Tag>{row.source}</Tag>
        ),
    },
  ];

  const problemResults = (lastResult?.results ?? []).filter(isProblemOutcome);

  return (
    <div className="apply-collect-result">
      <Space orientation="vertical" size={8} style={{ width: "100%" }}>
        <Space size={8} wrap>
          <Typography.Text strong>{t("collectResult.title")}</Typography.Text>
          <Typography.Text type="secondary">{t("collectResult.hint")}</Typography.Text>
        </Space>

        {error && <Alert type="error" showIcon title={error} />}

        {lastResult && problemResults.length > 0 && (
          <Alert
            type="warning"
            showIcon
            closable
            onClose={() => setLastResult(null)}
            title={t("collectResult.problem.title", { count: problemResults.length })}
            description={
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {problemResults.map((item) => {
                  // 未知 outcome（后端将来新增的取值）原样显示，不显示成空字符串。
                  const labelKey: MessageKey | undefined = OUTCOME_LABEL_KEYS[item.outcome];
                  return (
                    <li key={item.candidate_id}>
                      <Typography.Text strong>
                        {item.title || `#${item.candidate_id}`}
                      </Typography.Text>
                      {" — "}
                      {labelKey ? t(labelKey) : item.outcome}
                    </li>
                  );
                })}
              </ul>
            }
          />
        )}

        {loading && !data ? (
          <PageSkeleton rows={4} card={false} />
        ) : candidates.length === 0 ? (
          <EmptyState description={t("collectResult.empty")} />
        ) : (
          <>
            <Table
              className="apply-collect-table"
              rowKey="id"
              size="small"
              columns={columns}
              dataSource={candidates}
              // 单批采集上限 200 条，不加翻页会把整个页签塞满（其余主列表的分页排查见
              // deliverables/pagination-audit-2026-10-09.md）。
              pagination={{ pageSize: 20, hideOnSinglePage: true, showSizeChanger: false }}
              rowSelection={{
                selectedRowKeys: selectedIds,
                onChange: (keys) => setSelectedIds(keys as number[]),
              }}
              onChange={(_pagination, _filters, sorter, extra) => {
                if (extra.action !== "sort") return;
                const field = Array.isArray(sorter) ? sorter[0]?.field : sorter.field;
                const order = Array.isArray(sorter) ? sorter[0]?.order : sorter.order;
                if (field !== "score_total") return;
                // 升序/降序都按服务端键排；取消排序（order 为空）回到默认的最近采集在前。
                setSort(order === "ascend" ? "score_asc" : order === "descend" ? "score_desc" : "created_desc");
              }}
            />
            <Space size={8} wrap>
              <Button
                type="primary"
                icon={<UploadOutlined />}
                loading={importing}
                disabled={disabled || selectedIds.length === 0}
                // 显式 aria-label：antd 会把图标名（"upload"）并进无障碍名称，两字中文按钮
                // 还会被自动插入空格（"全 选"）。不写死名称，界面与测试都容易踩到这两个坑。
                aria-label={importLabel(selectedIds.length)}
                onClick={() => void doImport()}
              >
                {importLabel(selectedIds.length)}
              </Button>
              <Tooltip title={t("collectResult.queue.tooltip")}>
                <Button
                  icon={<SendOutlined />}
                  loading={importing}
                  disabled={disabled || selectedIds.length === 0}
                  aria-label={t("collectResult.queue.aria", { count: selectedIds.length })}
                  onClick={() => void doImportAndQueue()}
                >
                  {t("collectResult.queue.label")}
                </Button>
              </Tooltip>
              <Button
                aria-label={t("collectResult.action.selectAll")}
                disabled={disabled || importing}
                onClick={() => setSelectedIds(candidates.map((item) => item.id))}
              >
                {t("collectResult.action.selectAll")}
              </Button>
              <Button
                aria-label={t("collectResult.action.clearSelection")}
                disabled={disabled || importing || selectedIds.length === 0}
                onClick={() => setSelectedIds([])}
              >
                {t("collectResult.action.clearSelection")}
              </Button>
              <Typography.Text type="secondary">{t("collectResult.footnote")}</Typography.Text>
            </Space>
          </>
        )}
      </Space>
    </div>
  );
}
