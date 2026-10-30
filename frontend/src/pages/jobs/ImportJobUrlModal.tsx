/** 按招聘网站链接导入岗位：粘贴一条岗位详情页链接，后端用投递专用浏览器抓 JD 落库。 */
import { App, Alert, Button, Input, Modal, Space, Typography } from "antd";
import { useState } from "react";
import { importJobFromUrl } from "../../api/jobs";
import type { Job } from "../../types";

interface Props {
  open: boolean;
  onClose: () => void;
  /** 导入成功：刷新列表（有的调用方还会顺手打开详情）。 */
  onImported: (job: Job) => void;
}

export default function ImportJobUrlModal({ open, onClose, onImported }: Props) {
  const { message } = App.useApp();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    const target = url.trim();
    if (!target || loading) return;
    setLoading(true);
    setError("");
    try {
      const job = await importJobFromUrl(target);
      message.success(`已导入「${job.title}」`);
      setUrl("");
      onImported(job);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="按链接导入岗位"
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        把招聘网站上的岗位详情页链接粘进来，应用会用「投递台」那个已登录的专用浏览器打开它，
        把岗位名称、公司、JD 全文抓下来存成岗位记录。导入后可以直接做匹配分析、生成岗位版简历，
        因为它带着原始链接，也能直接加入投递台。
      </Typography.Paragraph>
      <Input
        aria-label="岗位链接"
        placeholder="粘贴岗位详情页的完整链接"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        onPressEnter={() => void submit()}
        allowClear
      />
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8 }}>
        只支持已注册的招聘网站（当前支持哪一个，在「投递台 → 投递设置 → 当前招聘网站」里看）。
        抓取前请先在「投递台」启动专用浏览器并确认已登录——没登录时页面会跳到登录页，读不到 JD。
      </Typography.Paragraph>
      {error && <Alert type="error" showIcon title={error} style={{ marginTop: 12 }} />}
      <div style={{ marginTop: 16, textAlign: "right" }}>
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={loading} disabled={!url.trim()} onClick={() => void submit()}>
            导入
          </Button>
        </Space>
      </div>
    </Modal>
  );
}
