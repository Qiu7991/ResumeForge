// SPDX-License-Identifier: Apache-2.0
/**
 * 投递队列：逐条确认准入、编辑招呼语与简历，然后显式开始投递。
 *
 * 准入提示直接读后端返回的 `admission` / `requires_confirm`（不在这里重判一次）：
 * - `block`（真实缺口）显示为「不投」并说明原因；
 * - `needs_confirm`（证据不足 / 待确认）提示需要用户确认；
 * - 未分析的岗位以「未分析」呈现。
 */
import { DeleteOutlined, EditOutlined, EyeOutlined } from "@ant-design/icons";
import { App, Alert, Button, Empty, Space, Tag, Typography, Popconfirm } from "antd";
import PageSkeleton from "../common/PageSkeleton";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createApplyTask,
  getApplyConfig,
  getBrowserStatus,
  listQueue,
  removeQueueItem,
  updateQueueItem,
} from "../../api/apply";
import {
  stopGreetingBatch,
  useGreetingBatchState,
} from "../../features/apply/greetingBatchRunner";
import { useApi } from "../../hooks/useApi";
import {
  QUEUE_STATUS_META,
  type ApplyQueueItem,
  type ApplyQueueList,
  type ApplyTask,
  type QueueStatus,
} from "../../types";
import { formatDateTime } from "../../utils/format";
import { RecordDetailDrawer } from "../common/RecordDetail";
import { useRowActionMenu } from "../common/rowActionMenu";
import { AdmissionTag } from "./queue/AdmissionTag";
import { QueueFilterBar } from "./queue/QueueFilterBar";
import { UNANALYZED_FILTER, type AdmissionFilterValue } from "./queue/filterOptions";
import { QueueItemEditor } from "./queue/QueueItemEditor";
import { QueueTable } from "./queue/QueueTable";
import { t } from "../../i18n";
import { QUEUE_STATUS_LABEL_KEYS } from "../../i18n/enum/apply";
import { useLocale } from "../../i18n/i18nContext";

interface Props {
  /** 有任务正在运行时为真：禁止重复开始。 */
  disabled: boolean;
  onStarted: (task: ApplyTask) => void;
  /** 队列内容变化（增删改）时通知页面刷新概览。 */
  onChanged?: () => void;
}

export default function ApplyQueuePanel({ disabled, onStarted, onChanged }: Props) {
  const { message, modal } = App.useApp();
  // 本面板用模块级 t()：必须订阅语言变化。
  useLocale();
  const [reloadKey, setReloadKey] = useState(0);
  // 列表响应是 { items, total, truncated }（P2-2）：队列封顶 500 条，total 是真实条数。
  const { data, loading, error, reload } = useApi<ApplyQueueList>(() => listQueue(), [reloadKey]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [editing, setEditing] = useState<ApplyQueueItem | null>(null);
  const [detail, setDetail] = useState<ApplyQueueItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState<QueueStatus | undefined>(undefined);
  const [admissionFilter, setAdmissionFilter] = useState<AdmissionFilterValue | undefined>(
    undefined,
  );
  const [batchRemoving, setBatchRemoving] = useState(false);
  const [confirmingGreetings, setConfirmingGreetings] = useState(false);
  const greetingBatch = useGreetingBatchState();
  const buildMenu = useRowActionMenu();

  useEffect(() => {
    if (error) message.error(error);
  }, [error, message]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const queueTotal = data?.total ?? 0;
  const queueTruncated = data?.truncated ?? false;
  const pendingItems = useMemo(
    () => items.filter((item) => item.status === "pending" && item.job_id !== null),
    [items],
  );
  // 来源不支持的待投条目：它们**无法**被自动投递，整队列投递时会被后端一次性拦下。
  // 提前在页面上说明，用户才不会在点了「开始投递」之后才被一条 409 拦住。
  const unsupportedPending = useMemo(
    () => pendingItems.filter((item) => item.apply_supported === false),
    [pendingItems],
  );
  // 有文案但没经用户确认的草稿（批量生成的）。闸门开着时这些条目会被逐条跳过，
  // 所以工具栏给一个显式的批量确认入口；没有选中时覆盖整队列。
  const confirmableItems = useMemo(
    () =>
      pendingItems.filter((item) => item.greeting.trim() && item.greeting_confirmed !== true),
    [pendingItems],
  );
  const selectedConfirmable = useMemo(
    () => confirmableItems.filter((item) => selectedIds.includes(item.id)),
    [confirmableItems, selectedIds],
  );
  const confirmGreetingCount =
    selectedIds.length > 0 ? selectedConfirmable.length : confirmableItems.length;
  // 筛选只影响表格显示：准入告警、开始投递的可用性判断仍看全量 items。
  const filteredItems = useMemo(
    () =>
      items.filter((item) => {
        if (statusFilter && item.status !== statusFilter) return false;
        if (admissionFilter) {
          if (admissionFilter === UNANALYZED_FILTER) return item.admission === null;
          return item.admission === admissionFilter;
        }
        return true;
      }),
    [items, statusFilter, admissionFilter],
  );
  const filterActive = statusFilter !== undefined || admissionFilter !== undefined;
  // 「全选队列」= 勾选当前筛选结果里**全部可投**的条目（跨页生效），可选范围与表格
  // 勾选框的非禁用条件（getCheckboxProps）保持一致。
  const selectableIds = useMemo(
    () =>
      filteredItems
        .filter(
          (item) =>
            item.status === "pending" && item.job_id !== null && item.apply_supported !== false,
        )
        .map((item) => item.id),
    [filteredItems],
  );

  const refresh = () => {
    setReloadKey((value) => value + 1);
    onChanged?.();
  };

  // 批量生成结束后拉一次队列：表格里的「待确认」标签与文案要立刻反映落库结果。
  // 只在 running 由真变假时刷新，避免每条完成都重拉一次整队列。
  const greetingWasRunning = useRef(false);
  useEffect(() => {
    if (greetingWasRunning.current && !greetingBatch.running) refresh();
    greetingWasRunning.current = greetingBatch.running;
    // refresh 每次渲染都是新函数，依赖它会让这个效果每渲染都跑；只想盯 running 的边沿。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [greetingBatch.running]);

  /**
   * 右键菜单项：与「···」菜单一致（编辑 / 移出队列）。移出队列走 Modal.confirm。
   */
  /**
   * 行操作的唯一清单：右键菜单与「···」下拉都从这里取，避免两处慢慢长歪。
   * 「移出队列」走 Modal.confirm（由 buildMenu 统一加二次确认）。
   */
  const rowMenuItems = (record: ApplyQueueItem) =>
    buildMenu([
      {
        key: "detail",
        label: t("applyQueue.action.viewDetail"),
        icon: <EyeOutlined />,
        onClick: () => setDetail(record),
      },
      {
        key: "edit",
        label: t("applyQueue.action.edit"),
        icon: <EditOutlined />,
        onClick: () => setEditing(record),
      },
      {
        key: "remove",
        label: t("applyQueue.action.remove"),
        danger: true,
        icon: <DeleteOutlined />,
        confirm: t("applyQueue.confirm.removeTitle"),
        // 与「删除」区别开：移出队列不动数据，正文要说清"岗位与投递记录都还在"。
        confirmBody: t("applyQueue.confirm.removeBody"),
        onClick: () => void remove(record),
      },
    ]);

  const remove = async (item: ApplyQueueItem) => {
    setBusy(true);
    try {
      await removeQueueItem(item.id);
      setSelectedIds((current) => current.filter((id) => id !== item.id));
      message.success(t("applyQueue.toast.removed"));
      refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("applyQueue.toast.removeFailed"));
    } finally {
      setBusy(false);
    }
  };

  /** 批量移出：后端没有批量端点，逐条 DELETE、allSettled 聚合账目——一条失败不拖垮整批。 */
  const removeSelected = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    setBatchRemoving(true);
    try {
      const results = await Promise.allSettled(ids.map((id) => removeQueueItem(id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      setSelectedIds([]);
      refresh();
      if (failed > 0) {
        message.warning(t("applyQueue.toast.removePartial", { ok: ids.length - failed, failed }));
      } else {
        message.success(t("applyQueue.toast.removedCount", { count: ids.length }));
      }
    } finally {
      setBatchRemoving(false);
    }
  };

  /**
   * 批量确认招呼语草稿：逐条 PATCH（后端只有单条更新端点），allSettled 聚合——
   * 一条失败不拖垮整批，失败条数如实回给用户。
   */
  const confirmDrafts = async (targets: ApplyQueueItem[], { toast = true } = {}) => {
    if (targets.length === 0) return true;
    setConfirmingGreetings(true);
    try {
      const results = await Promise.allSettled(
        targets.map((item) => updateQueueItem(item.id, { confirm_greeting: true })),
      );
      const failed = results.filter((result) => result.status === "rejected").length;
      const ok = targets.length - failed;
      // 刷新队列：表格里的「待确认」标签要立刻消失，用户才敢点开始。
      refresh();
      if (failed > 0) {
        message.warning(t("applyQueue.toast.confirmGreetingsFailed", { ok, failed }));
      } else if (toast) {
        message.success(t("applyQueue.toast.confirmedGreetings", { count: ok }));
      }
      return failed === 0;
    } finally {
      setConfirmingGreetings(false);
    }
  };

  const askConfirmGreetings = () => {
    // 有选中就只确认选中的（按钮上的数字也是这个口径）；没选中时确认整队列的草稿。
    const targets = selectedIds.length > 0 ? selectedConfirmable : confirmableItems;
    if (targets.length === 0) return;
    modal.confirm({
      title: t("applyQueue.confirm.confirmGreetingsTitle"),
      content: t("applyQueue.confirm.confirmGreetingsBody", { count: targets.length }),
      okText: t("applyQueue.action.confirmGreetings", { count: targets.length }),
      cancelText: t("common.action.cancel"),
      onOk: () => confirmDrafts(targets),
    });
  };

  const start = async () => {
    // Table 的 rowKey 是队列条目 id，而后端 /apply/tasks 的 job_ids 明确要求岗位 id。
    // 两种 id 通常不同，直接提交 selectedIds 会投错岗位，甚至在碰巧存在同号岗位时静默误投。
    const selectedPending =
      selectedIds.length > 0
        ? items.filter(
            (item): item is ApplyQueueItem & { job_id: number } =>
              selectedIds.includes(item.id) && item.status === "pending" && item.job_id !== null,
          )
        : [];
    const chosen =
      selectedIds.length > 0 ? selectedPending.map((item) => item.job_id) : undefined;
    if (selectedIds.length > 0 && chosen?.length === 0) {
      message.warning(t("applyQueue.toast.notEligible"));
      return;
    }
    setBusy(true);
    try {
      // 投递由受控浏览器执行：浏览器没启动时后端必然失败。按钮不禁用（保留可发现性），
      // 但点击时先查一次状态并给出引导，而不是让用户去读一条后端报错。
      const browser = await getBrowserStatus();
      if (browser.state !== "running") {
        message.warning(t("applyQueue.toast.needBrowser"));
        return;
      }

      const submit = async () => {
        const task = await createApplyTask(
          chosen ? { job_ids: chosen, use_queue: false } : { use_queue: true },
        );
        message.success(
          chosen
            ? t("applyQueue.toast.startedSelected", { count: chosen.length })
            : t("applyQueue.toast.startedAll"),
        );
        setSelectedIds([]);
        onStarted(task);
      };

      // 开始前预检：闸门开启时，有文案但未确认 / 没有文案的条目都会被逐条跳过。
      // 之前这里没有任何提示，用户看着整批「已跳过·招呼语缺失」只会以为程序没读到文案，
      // 所以改为开始时就说清楚，并允许当场确认草稿（仍需用户显式点确认，不自动放行）。
      const targets = selectedIds.length > 0 ? selectedPending : pendingItems;
      const drafts = targets.filter(
        (item) => item.greeting.trim() && item.greeting_confirmed !== true,
      );
      const missing = targets.filter((item) => !item.greeting.trim());
      if (drafts.length > 0 || missing.length > 0) {
        const reviewRequired = await getApplyConfig()
          .then((config) => config.require_greeting_review)
          .catch(() => false);
        if (reviewRequired) {
          modal.confirm({
            title: t("applyQueue.preflight.title", { count: drafts.length + missing.length }),
            content: (
              <Space orientation="vertical" size={4}>
                <span>{t("applyQueue.preflight.body", { confirmable: drafts.length })}</span>
                {missing.length > 0 ? (
                  <span>{t("applyQueue.preflight.alsoMissing", { count: missing.length })}</span>
                ) : null}
              </Space>
            ),
            okText: drafts.length
              ? t("applyQueue.preflight.confirmAndStart")
              : t("applyQueue.preflight.startAnyway"),
            cancelText: t("common.action.cancel"),
            onOk: async () => {
              setBusy(true);
              try {
                if (drafts.length > 0) await confirmDrafts(drafts, { toast: false });
                await submit();
              } catch (err) {
                message.error(
                  err instanceof Error ? err.message : t("applyQueue.toast.startFailed"),
                );
              } finally {
                setBusy(false);
              }
            },
          });
          return;
        }
      }
      await submit();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("applyQueue.toast.startFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !data) return <PageSkeleton rows={5} />;

  return (
    <div className="apply-queue-panel">
      {/* 用户反馈过「点进来不知道下一步干什么」：这一段是唯一的入口说明，明确"岗位从哪来、
          在这里做什么、什么时候才真的投出去"。不用弹窗，避免每次进来都要关一次。 */}
      <Alert
        className="apply-queue-flow"
        type="info"
        showIcon
        title={t("applyQueue.guide.title")}
        description={
          <ol style={{ margin: 0, paddingLeft: 18 }}>
            <li>{t("applyQueue.guide.step1")}</li>
            <li>{t("applyQueue.guide.step2")}</li>
            <li>{t("applyQueue.guide.step3")}</li>
            <li>{t("applyQueue.guide.step4")}</li>
          </ol>
        }
      />

      {/* 来源不支持的条目现在的**唯一**来源是"闸门上线前就已经在队列里"的历史数据。
          写清楚它们是什么、以及两种处理方式，用户才不会在点开始时被一条 409 拦住。 */}
      {unsupportedPending.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t("applyQueue.unsupported.title", { count: unsupportedPending.length })}
          description={<span>{t("applyQueue.unsupported.body")}</span>}
        />
      )}

      {/* 队列被封顶展示（P2-2）：如实在说，引导用筛选/开始投递消化，而不是假装队列只有 500 条。 */}
      {queueTruncated && items.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={t("applyQueue.truncated", { total: queueTotal, shown: items.length })}
          style={{ marginBottom: 12 }}
        />
      )}

      <QueueFilterBar
        statusFilter={statusFilter}
        onStatusChange={setStatusFilter}
        admissionFilter={admissionFilter}
        onAdmissionChange={setAdmissionFilter}
        queueTotal={queueTotal}
        filteredCount={filteredItems.length}
        filterActive={filterActive}
        selectedCount={selectedIds.length}
        selectableCount={selectableIds.length}
        busy={busy}
        batchRemoving={batchRemoving}
        loading={loading}
        onSelectAll={() => setSelectedIds(selectableIds)}
        onClearSelection={() => setSelectedIds([])}
        onRemoveSelected={() => void removeSelected()}
        onConfirmGreetings={askConfirmGreetings}
        confirmGreetingCount={confirmGreetingCount}
        confirmingGreetings={confirmingGreetings}
        onReload={() => void reload()}
        greetingBatch={greetingBatch}
        onStopGreetings={stopGreetingBatch}
        startDisabled={disabled || pendingItems.length === 0 || greetingBatch.running}
        onStart={() => void start()}
      />

      {items.length === 0 ? (
        <Empty
          description={
            <Space orientation="vertical" size={4}>
              <Typography.Text>{t("applyQueue.empty.title")}</Typography.Text>
              <Typography.Text type="secondary">{t("applyQueue.empty.body")}</Typography.Text>
            </Space>
          }
        />
      ) : (
        <QueueTable
          items={filteredItems}
          busy={busy}
          selectedIds={selectedIds}
          setSelectedIds={setSelectedIds}
          setDetail={setDetail}
          setEditing={setEditing}
          rowMenuItems={rowMenuItems}
        />
      )}

      {/* 队列条目的详情：表格里只放得下摘要，招呼语全文、准入结论与时间都在这里看。 */}
      <RecordDetailDrawer
        open={detail !== null}
        title={detail?.job_title || t("applyQueue.detail.deletedJob")}
        subtitle={detail?.company}
        tags={detail && <AdmissionTag item={detail} />}
        fields={
          detail
            ? [
                {
                  label: t("applyQueue.detail.autoApply"),
                  value:
                    detail.apply_supported === false ? (
                      <Tag color="red">{t("applyQueue.detail.unsupported")}</Tag>
                    ) : (
                      t("applyQueue.detail.supported")
                    ),
                },
                {
                  label: t("applyQueue.detail.status"),
                  value: (
                    <Tag color={QUEUE_STATUS_META[detail.status].color}>
                      {t(QUEUE_STATUS_LABEL_KEYS[detail.status])}
                    </Tag>
                  ),
                },
                {
                  label: t("applyQueue.detail.queuePosition"),
                  value: t("applyQueue.detail.position", {
                    index: items.findIndex((i) => i.id === detail.id) + 1,
                  }),
                },
                {
                  label: t("applyQueue.detail.resume"),
                  value: detail.resume_title || t("applyQueue.detail.noResume"),
                },
                {
                  label: t("applyQueue.detail.joinedAt"),
                  value: formatDateTime(detail.created_at),
                },
                {
                  label: t("applyQueue.detail.updatedAt"),
                  value: formatDateTime(detail.updated_at),
                },
              ]
            : []
        }
        sections={
          detail
            ? [
                {
                  title: t("applyQueue.detail.greeting"),
                  content: detail.greeting || t("applyQueue.detail.defaultGreeting"),
                },
              ]
            : []
        }
        actions={
          detail && (
            <Space>
              <Button
                icon={<EditOutlined />}
                onClick={() => {
                  setEditing(detail);
                  setDetail(null);
                }}
              >
                {t("applyQueue.action.edit")}
              </Button>
              <Popconfirm
                title={t("applyQueue.confirm.removeTitle")}
                // 后果段与行菜单那一处同措辞：移出队列不动岗位与投递记录。
                description={t("applyQueue.confirm.removeBody")}
                okText={t("applyQueue.action.removeShort")}
                cancelText={t("common.action.cancel")}
                okButtonProps={{ danger: true }}
                onConfirm={() => {
                  void remove(detail);
                  setDetail(null);
                }}
              >
                <Button danger icon={<DeleteOutlined />}>
                  {t("applyQueue.action.remove")}
                </Button>
              </Popconfirm>
            </Space>
          )
        }
        onClose={() => setDetail(null)}
      />

      {editing && (
        <QueueItemEditor
          item={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            refresh();
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
