// SPDX-License-Identifier: Apache-2.0
/** 回复收件箱（P3-1）：打开聊天（9333 窗口导航）/准备回复/记录回复/忽略。第一版不代发。 */
import { App, Button, List, Space, Spin, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { dismissReply, getAiReplies, openReplyChat, prepareReply, recordReply } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

interface ReplyItem {
  id: number | string;
  action?: string;
  title?: string;
  company?: string;
  content?: string;
  created_at?: string;
}

export default function ReplyInbox() {
  useLocale();
  const { message } = App.useApp();
  const [items, setItems] = useState<ReplyItem[]>([]);
  const [unresolved, setUnresolved] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getAiReplies();
      setItems(((data.items ?? []) as unknown[]) as ReplyItem[]);
      setUnresolved(data.unresolved_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (historyId: string | number, action: () => Promise<unknown>, toast: string) => {
    setBusyId(String(historyId));
    try {
      await action();
      void message.success(toast);
      void load();
    } catch (err) {
      void message.error(err instanceof Error ? err.message : toast);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Space direction="vertical" size="small" style={{ width: "100%" }}>
      <Typography.Text type="secondary">
        {t("aiJobs.monitor.unresolved", { count: unresolved })}
      </Typography.Text>
      {error && (
        <Typography.Text type="danger" role="alert">
          {error}
        </Typography.Text>
      )}
      {loading ? (
        <Spin size="small" />
      ) : (
        <List
          size="small"
          dataSource={items}
          rowKey={(item) => String(item.id)}
          locale={{ emptyText: t("aiJobs.monitor.empty") }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key="open"
                  size="small"
                  loading={busyId === String(item.id)}
                  onClick={() => void act(item.id, () => openReplyChat(String(item.id)), t("aiJobs.monitor.opened"))}
                >
                  {t("aiJobs.monitor.open")}
                </Button>,
                <Button
                  key="prepare"
                  size="small"
                  onClick={() => void act(item.id, () => prepareReply(String(item.id)), t("aiJobs.monitor.prepared"))}
                >
                  {t("aiJobs.monitor.prepare")}
                </Button>,
                <Button
                  key="record"
                  size="small"
                  onClick={() => void act(item.id, () => recordReply(String(item.id), ""), t("aiJobs.monitor.recorded"))}
                >
                  {t("aiJobs.monitor.record")}
                </Button>,
                <Button
                  key="dismiss"
                  size="small"
                  danger
                  onClick={() => void act(item.id, () => dismissReply(String(item.id)), t("aiJobs.monitor.dismissed"))}
                >
                  {t("aiJobs.monitor.dismiss")}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={item.title ?? "-"}
                description={
                  <Space size="small" wrap>
                    {item.company && <Typography.Text type="secondary">{item.company}</Typography.Text>}
                    {item.created_at && (
                      <Typography.Text type="secondary">{item.created_at}</Typography.Text>
                    )}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Space>
  );
}
