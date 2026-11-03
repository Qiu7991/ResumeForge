// SPDX-License-Identifier: Apache-2.0
/**
 * 投递队列表格：定宽列 + 行选择 + 右键菜单。
 * （自 ApplyQueuePanel 拆出：columns/rowSelection/<Table>/右键菜单三段整体搬，
 * contextMenu state 随唯一消费者下沉进本组件；rowMenuItems 经 prop 传入；
 * aria-label/类名/定宽注释逐字随迁，行为等价。）
 *
 * 状态标签的展示名走语言包（`QUEUE_STATUS_LABEL_KEYS`），颜色仍取 `QUEUE_STATUS_META`；
 * 列头、空值兜底、提示与 aria-label 走 applyQueue 包。
 */
import { MoreOutlined } from "@ant-design/icons";
import { Button, Dropdown, Menu, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { MenuProps } from "antd";
import type { TableColumnsType } from "antd";
import type { TableRowSelection } from "antd/es/table/interface";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { t } from "../../../i18n";
import { QUEUE_STATUS_LABEL_KEYS } from "../../../i18n/enum/apply";
import { useLocale } from "../../../i18n/i18nContext";
import type { ApplyQueueItem } from "../../../types";
import { QUEUE_STATUS_META } from "../../../types";
import { formatDateTime } from "../../../utils/format";
import { AdmissionTag } from "./AdmissionTag";

export function QueueTable({
  items,
  busy,
  selectedIds,
  setSelectedIds,
  setDetail,
  setEditing,
  rowMenuItems,
}: {
  items: ApplyQueueItem[];
  busy: boolean;
  selectedIds: number[];
  setSelectedIds: (ids: number[]) => void;
  setDetail: (item: ApplyQueueItem) => void;
  /** 点招呼语/待确认标签直接打开编辑弹窗（不再要求先走「更多操作」）。 */
  setEditing: (item: ApplyQueueItem) => void;
  rowMenuItems: (record: ApplyQueueItem) => MenuProps["items"];
}) {
  // 本组件用模块级 t()：必须订阅语言变化，否则切语言后列头停在旧文案。
  useLocale();
  // 每页条数：默认 10 条（队列行高较高，一页塞太多会挤满整屏），由分页器切换。
  const [pageSize, setPageSize] = useState(10);
  // 右键菜单：记录鼠标位置与目标行，用定位式 Menu 渲染（避免把 <tr> 包进 Dropdown 造成行重建竞态）。
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    record: ApplyQueueItem;
  } | null>(null);
  // 打开菜单时记下当时的焦点元素，关闭时还回去（Esc 关闭也不能把焦点丢在 body 上）。
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const closeContextMenu = () => {
    setContextMenu(null);
    const restoreTo = restoreFocusRef.current;
    restoreFocusRef.current = null;
    restoreTo?.focus({ preventScroll: true });
  };

  // Esc 关闭：遮罩层收不到键盘事件（焦点不在它上面），挂 window 监听并随菜单开关装卸。
  useEffect(() => {
    if (!contextMenu) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeContextMenu();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [contextMenu]);

  /** 招呼语/标签是自定义的可点击元素：键盘 Enter / 空格与鼠标单击等价。 */
  const activateEdit = (event: ReactKeyboardEvent<HTMLElement>, item: ApplyQueueItem) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setEditing(item);
    }
  };

  /**
   * 列宽全部写死、`tableLayout="fixed"`：
   * 招呼语是用户可编辑的长文本，之前不设宽度时它会跟「准入 / 状态」抢空间——编辑过一条
   * 队列条目之后整张表就挤成一团。定宽 + 省略号让每列宽度只由表头决定，内容长短不再影响排版。
   */
  const columns: TableColumnsType<ApplyQueueItem> = [
    {
      title: t("applyQueue.column.job"),
      dataIndex: "job_title",
      width: 220,
      render: (title: string, item) => (
        // 外层 Tooltip 只包**岗位标题按钮**，不再包整个单元格：单元格里的「来源不支持」
        // 标签有自己的提示，两层 Tooltip 叠在同一个触发区上会同时弹出两句
        // （2026-10-25 用户截图：鼠标悬停时提示叠在一起）。
        <Space orientation="vertical" size={0} style={{ width: "100%" }}>
          <Tooltip
            title={t("applyQueue.table.joinedAt", { time: formatDateTime(item.created_at) })}
          >
            <Button
              type="link"
              className="table-text-link"
              onClick={() => setDetail(item)}
              aria-label={t("applyQueue.table.viewDetailAria", {
                title: title || t("applyQueue.table.deletedJobShort"),
              })}
            >
              {title || t("applyQueue.detail.deletedJob")}
            </Button>
          </Tooltip>
          <Space size={4} wrap>
            {item.company && (
              <Typography.Text type="secondary" ellipsis>
                {item.company}
              </Typography.Text>
            )}
            {item.apply_supported === false && (
              // 和岗位广场上的「采集 / 手动」同一个位置放来源类标签：用户看来源就看这里。
              <Tooltip title={t("applyQueue.table.unsupportedHint")}>
                <Tag color="red" style={{ marginInlineEnd: 0 }}>
                  {t("applyQueue.table.unsupportedTag")}
                </Tag>
              </Tooltip>
            )}
          </Space>
        </Space>
      ),
    },
    {
      title: t("applyQueue.column.admission"),
      key: "admission",
      width: 140,
      render: (_, item) => <AdmissionTag item={item} />,
    },
    {
      title: t("applyQueue.column.status"),
      dataIndex: "status",
      width: 96,
      align: "center",
      render: (value: ApplyQueueItem["status"]) => {
        const meta = QUEUE_STATUS_META[value];
        return <Tag color={meta.color}>{t(QUEUE_STATUS_LABEL_KEYS[value])}</Tag>;
      },
    },
    {
      title: t("applyQueue.column.assets"),
      key: "assets",
      width: 260,
      render: (_, item) => (
        <Space orientation="vertical" size={0} style={{ width: "100%" }}>
          <Typography.Text
            type="secondary"
            ellipsis={{ tooltip: item.resume_title || t("applyQueue.detail.noResume") }}
          >
            {item.resume_title || t("applyQueue.detail.noResume")}
          </Typography.Text>
          {item.greeting ? (
            // 招呼语本身就是编辑入口：单击打开编辑弹窗，不再要求先走「更多操作 → 编辑」。
            <Typography.Text
              type="secondary"
              ellipsis={{
                tooltip: `${item.greeting} · ${t("applyQueue.greeting.clickToEdit")}`,
              }}
              className="apply-queue-greeting-edit"
              role="button"
              tabIndex={0}
              aria-label={t("applyQueue.greeting.editAria", { job: item.job_title })}
              onClick={() => setEditing(item)}
              onKeyDown={(event) => activateEdit(event, item)}
            >
              {item.greeting}
            </Typography.Text>
          ) : (
            // 空招呼语 = 没确认过。开启「发送前必须确认招呼语」时这条会被跳过，
            // 标签要把话说透，而不是含糊地写「默认招呼语」让人以为会照默认发。
            <Tooltip title={t("applyQueue.greeting.unconfirmedHint")}>
              <Tag
                color="orange"
                role="button"
                tabIndex={0}
                className="apply-queue-greeting-edit"
                aria-label={t("applyQueue.greeting.editAria", { job: item.job_title })}
                onClick={() => setEditing(item)}
                onKeyDown={(event) => activateEdit(event, item)}
                style={{ marginInlineEnd: 0, width: "fit-content" }}
              >
                {t("applyQueue.greeting.unconfirmed")}
              </Tag>
            </Tooltip>
          )}
          {/* 有字但没人工确认：AI 批量生成的草稿。有字不等于确认过，必须单独标出来。 */}
          {item.greeting && item.greeting_confirmed !== true ? (
            <Tooltip title={t("applyQueue.greeting.pendingConfirmHint")}>
              <Tag
                color="gold"
                role="button"
                tabIndex={0}
                className="apply-queue-greeting-edit"
                aria-label={t("applyQueue.greeting.editAria", { job: item.job_title })}
                onClick={() => setEditing(item)}
                onKeyDown={(event) => activateEdit(event, item)}
                style={{ marginInlineEnd: 0, width: "fit-content" }}
              >
                {t("applyQueue.greeting.pendingConfirm")}
              </Tag>
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
    {
      title: t("applyQueue.column.actions"),
      key: "actions",
      width: 64,
      // 表头与单元格一起右对齐：否则「操作」两字靠左、按钮靠右，看起来像没对齐（用户反馈过）。
      align: "right",
      render: (_, item) => (
        <div
          className="apply-queue-actions"
          style={{ display: "flex", justifyContent: "flex-end", marginLeft: "auto" }}
        >
          <Dropdown trigger={["click"]} menu={{ items: rowMenuItems(item) }}>
            <Button
              size="small"
              aria-label={t("applyQueue.table.moreActionsAria", { job: item.job_title })}
              icon={<MoreOutlined />}
            />
          </Dropdown>
        </div>
      ),
    },
  ];

  const rowSelection: TableRowSelection<ApplyQueueItem> = {
    selectedRowKeys: selectedIds,
    onChange: (keys) => setSelectedIds(keys.map(Number)),
    getCheckboxProps: (item) => ({
      // 来源不支持的条目**不可勾选**：勾了也投不出去，不如一开始就不让选（后端还会再拦一次）。
      disabled:
        item.status !== "pending" || item.job_id === null || item.apply_supported === false || busy,
    }),
  };

  return (
    <>
      <Table<ApplyQueueItem>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={items}
        // 每页 10 条：队列条目行高较高，一页塞太多会把整屏挤满；分页形态与岗位广场 /
        // 简历中心一致（条数切换 + 总数显示）。hideOnSinglePage：队列很短时不打扰。
        pagination={{
          pageSize,
          hideOnSinglePage: true,
          showSizeChanger: true,
          showTotal: (total) => t("applyQueue.table.total", { total }),
          // pageSize 一旦写成固定值就是受控属性：不在这里回写 state，切「20 条/页」
          // 会被下一次渲染重置回 10，看起来像选择没生效。
          onChange: (_page, size) => setPageSize(size),
        }}
        rowSelection={rowSelection}
        tableLayout="fixed"
        // 空表时不启用横向滚动（与 `JobTable` 同一口径）：否则 `.ant-table-content` 会变成
        // "可横滚、区域内却没有任何可聚焦元素"的容器，命中 axe 的
        // `scrollable-region-focusable`（serious）。有数据时照旧按列宽固定横滚。
        scroll={items.length ? { x: 880 } : undefined}
        onRow={(record) => ({
          onContextMenu: (event) => {
            event.preventDefault();
            restoreFocusRef.current =
              document.activeElement instanceof HTMLElement ? document.activeElement : null;
            setContextMenu({ x: event.clientX, y: event.clientY, record });
          },
        })}
      />
      {contextMenu && (
        <>
          <div
            style={{ position: "fixed", inset: 0, zIndex: 1050 }}
            onClick={closeContextMenu}
            onContextMenu={(event) => {
              event.preventDefault();
              closeContextMenu();
            }}
          />
          <Menu
            style={{
              position: "fixed",
              left: contextMenu.x,
              top: contextMenu.y,
              zIndex: 1060,
              minWidth: 150,
              boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
            }}
            items={rowMenuItems(contextMenu.record)}
            onClick={closeContextMenu}
          />
        </>
      )}
    </>
  );
}
