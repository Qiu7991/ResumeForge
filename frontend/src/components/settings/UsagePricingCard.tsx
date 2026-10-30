/**
 * 设置页 · 模型用量与计费。
 *
 * 账本只记数字（token / 耗时 / 结束原因），不记提示词与回复；token 缺失时显示「未知」，
 * 不当 0。单价是**每百万 token**、输入拆缓存命中/未命中两档——命中价通常只有未命中的
 * 1/10，合并成一档会把省下来的钱算没。未配置单价时不估算金额。
 */
import { DeleteOutlined, PlusOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Divider,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  activateUsagePricingRecord,
  deleteUsagePricingRecord,
  fetchUsagePricing,
  fetchUsagePricingRecords,
  fetchUsageSummary,
  saveUsagePricing,
} from "../../api/usage";
import type {
  UsageBucketOut,
  UsagePricingIn,
  UsagePricingRecordOut,
  UsageSummaryOut,
} from "../../types/usage";

const EMPTY_FORM: UsagePricingIn = {
  name: "",
  input_cache_hit_per_million: null,
  input_cache_miss_per_million: null,
  output_per_million: null,
  currency: "CNY",
};

function tokensText(value: number | null): string {
  return value === null ? "未知" : value.toLocaleString();
}

function priceText(value: number | null, currency: string): string {
  return value === null ? "未填" : `${value} ${currency}`;
}

function BucketLine({ bucket }: { bucket: UsageBucketOut }) {
  return (
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      {bucket.key}：{bucket.calls} 次，输入 {tokensText(bucket.prompt_tokens)} / 输出{" "}
      {tokensText(bucket.completion_tokens)}
      {bucket.unknown_token_calls > 0 ? `（${bucket.unknown_token_calls} 次未返回 token）` : ""}
    </Typography.Text>
  );
}

export default function UsagePricingCard() {
  const { message } = App.useApp();
  const [summary, setSummary] = useState<UsageSummaryOut | null>(null);
  const [records, setRecords] = useState<UsagePricingRecordOut[]>([]);
  const [form, setForm] = useState<UsagePricingIn>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [nextSummary, current, list] = await Promise.all([
        fetchUsageSummary(),
        fetchUsagePricing(),
        fetchUsagePricingRecords(),
      ]);
      setSummary(nextSummary);
      setRecords(list.items);
      setForm({
        name: "",
        input_cache_hit_per_million: current.input_cache_hit_per_million,
        input_cache_miss_per_million: current.input_cache_miss_per_million,
        output_per_million: current.output_per_million,
        currency: current.currency || "CNY",
      });
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取用量与单价失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const submit = async () => {
    const prices = [
      form.input_cache_hit_per_million,
      form.input_cache_miss_per_million,
      form.output_per_million,
    ];
    if (prices.every((value) => value === null)) {
      setError("至少填写一档单价（缓存命中 / 缓存未命中 / 输出）");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await saveUsagePricing({ ...form, currency: form.currency.trim() || "CNY" });
      message.success("单价已保存，之后的调用按新单价估算");
      await load();
    } catch (caught) {
      const text = caught instanceof Error ? caught.message : "保存单价失败";
      setError(text);
      message.error(text);
    } finally {
      setSaving(false);
    }
  };

  const activate = async (record: UsagePricingRecordOut) => {
    setBusyId(record.id);
    try {
      await activateUsagePricingRecord(record.id);
      await load();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "切换单价失败");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (record: UsagePricingRecordOut) => {
    setBusyId(record.id);
    try {
      await deleteUsagePricingRecord(record.id);
      await load();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "删除单价失败");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card
      size="small"
      title={
        <Space>
          <ThunderboltOutlined />
          用量与计费
          <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
            只记数字，不记提示词与回复
          </Typography.Text>
        </Space>
      }
      loading={loading}
      style={{ marginBottom: 16 }}
    >
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />}

      <Space orientation="vertical" size={4} style={{ width: "100%" }}>
        <Typography.Text>
          共 {summary?.records ?? 0} 次模型调用；合计输入{" "}
          {tokensText(summary?.totals.prompt_tokens ?? null)} / 输出{" "}
          {tokensText(summary?.totals.completion_tokens ?? null)} tokens
          {summary && summary.unknown_token_records > 0
            ? `（${summary.unknown_token_records} 次服务商未返回 token，合计显示未知）`
            : ""}
        </Typography.Text>
        <Typography.Text type={summary?.cost.estimated ? undefined : "secondary"}>
          {summary?.cost.estimated
            ? `按当前单价估算费用：${summary.cost.amount} ${summary.cost.currency}`
            : summary?.cost.reason || "未配置模型价格，不估算费用"}
        </Typography.Text>
        {(summary?.tasks ?? []).slice(0, 5).map((bucket) => (
          <BucketLine key={bucket.key} bucket={bucket} />
        ))}
      </Space>

      <Divider style={{ margin: "12px 0" }} />
      <Typography.Text strong>单价（每百万 token）</Typography.Text>
      <div style={{ marginTop: 8 }}>
        <Space wrap>
          <Input
            aria-label="单价名称"
            placeholder="名称（如 DeepSeek 官方价）"
            style={{ width: 190 }}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <InputNumber
            aria-label="缓存命中输入价"
            addonBefore="命中"
            min={0}
            value={form.input_cache_hit_per_million}
            onChange={(value) => setForm({ ...form, input_cache_hit_per_million: value })}
          />
          <InputNumber
            aria-label="缓存未命中输入价"
            addonBefore="未命中"
            min={0}
            value={form.input_cache_miss_per_million}
            onChange={(value) => setForm({ ...form, input_cache_miss_per_million: value })}
          />
          <InputNumber
            aria-label="输出价"
            addonBefore="输出"
            min={0}
            value={form.output_per_million}
            onChange={(value) => setForm({ ...form, output_per_million: value })}
          />
          <Input
            aria-label="币种"
            style={{ width: 80 }}
            value={form.currency}
            onChange={(event) => setForm({ ...form, currency: event.target.value })}
          />
          <Button type="primary" icon={<PlusOutlined />} loading={saving} onClick={() => void submit()}>
            保存为新单价
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6 }}>
          每次保存都新建一条记录（保留旧价可随时切回）；没有缓存折扣的服务商把「命中」留空即可。
        </Typography.Paragraph>
      </div>

      {records.length > 0 && (
        <Space orientation="vertical" size={4} style={{ width: "100%" }}>
          {records.map((record) => (
            <Space key={record.id} wrap>
              <Tag color={record.is_active ? "green" : "default"}>
                {record.is_active ? "生效中" : "未生效"}
              </Tag>
              <Typography.Text>{record.name || `未命名单价 #${record.id}`}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                命中 {priceText(record.input_cache_hit_per_million, record.currency)} · 未命中{" "}
                {priceText(record.input_cache_miss_per_million, record.currency)} · 输出{" "}
                {priceText(record.output_per_million, record.currency)}
              </Typography.Text>
              {!record.is_active && (
                <Button size="small" loading={busyId === record.id} onClick={() => void activate(record)}>
                  切换到这份
                </Button>
              )}
              <Popconfirm
                title="删除这份单价？"
                okText="删除"
                cancelText="取消"
                onConfirm={() => void remove(record)}
              >
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  loading={busyId === record.id}
                />
              </Popconfirm>
            </Space>
          ))}
        </Space>
      )}
    </Card>
  );
}
