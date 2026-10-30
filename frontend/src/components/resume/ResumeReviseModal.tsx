/** AI 修改简历：输入修改要求（可留空整体重写），修订结果直接更新当前记录。 */
import { LoadingOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Alert, App, Input, Modal, Space, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { reviseResume } from "../../api/resumes";
import { MaxLengthHint } from "../common/MaxLengthHint";
import type { ResumeDetail } from "../../types";

interface Props {
  open: boolean;
  recordId: number | null;
  /** 打开时预填的修改要求（如从警告区「AI 补上这段」带过来的指令）。 */
  initialInstructions?: string;
  onClose: () => void;
  /** 修订成功后把更新后的记录交回父组件刷新预览（弹窗自己负责关闭）。 */
  onApplied: (detail: ResumeDetail) => Promise<void> | void;
}

const MAX_CHARS = 2000;

export default function ResumeReviseModal({
  open,
  recordId,
  initialInstructions = "",
  onClose,
  onApplied,
}: Props) {
  const { message } = App.useApp();
  const [instructions, setInstructions] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  // 生成期间给一个会动的等待反馈：模型这一轮通常 20–60 秒，光转按钮用户会以为卡死。
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startedAtRef = useRef(0);

  // 预填指令在每次打开时生效（父组件每次带入的都可能是不同条目的指令）。
  // Compiler 规范：随 prop 变化的重置用渲染期守卫式调整。
  const [prevSync, setPrevSync] = useState<{ open: boolean; initialInstructions?: string } | null>(
    null,
  );
  if (
    prevSync === null ||
    prevSync.open !== open ||
    prevSync.initialInstructions !== initialInstructions
  ) {
    setPrevSync({ open, initialInstructions });
    if (open) setInstructions(initialInstructions);
  }

  // 只在提交期间走秒；effect 体内不做同步 setState（Compiler 规范），计时起点在 submit 里落。
  useEffect(() => {
    if (!submitting) return;
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [submitting]);

  const close = () => {
    setInstructions("");
    setError("");
    setSubmitting(false);
    onClose();
  };

  const submit = async () => {
    if (!recordId || submitting) return;
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);
    setSubmitting(true);
    setError("");
    try {
      const updated = await reviseResume(recordId, instructions);
      await onApplied(updated);
      const seconds = Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000));
      message.success(
        `${instructions.trim() ? "已按你的要求修改简历" : "已重新生成简历内容"}（用时 ${seconds} 秒）`,
      );
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : "修订简历失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const hasInstructions = instructions.trim().length > 0;

  return (
    <Modal
      title={
        <span>
          <ThunderboltOutlined /> AI 修改简历
        </span>
      }
      open={open}
      // 生成中锁住弹窗：请求是同步的，关掉只会让结果落库了却没刷新预览，
      // 用户看到的内容和数据库对不上。
      onCancel={() => {
        if (!submitting) close();
      }}
      closable={!submitting}
      mask={{ closable: false }}
      keyboard={!submitting}
      cancelButtonProps={{ disabled: submitting }}
      confirmLoading={submitting}
      onOk={() => void submit()}
      okText={submitting ? "生成中…" : hasInstructions ? "按要求修改" : "整体重新生成"}
      cancelText="取消"
      width={560}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {hasInstructions
          ? "AI 只会修改你明确提出的内容，其余部分逐字保留。"
          : "没有填写修改要求时，AI 会整体重新生成：事实与经历保持不变，表达与结构重新组织。"}
      </Typography.Paragraph>
      <Input.TextArea
        value={instructions}
        onChange={(event) => setInstructions(event.target.value.slice(0, MAX_CHARS))}
        placeholder={`可选。例：把个人总结改得更突出数据分析能力；项目经历里补充量化结果。留空则整体重新生成。最多 ${MAX_CHARS} 字。`}
        autoSize={{ minRows: 4, maxRows: 10 }}
        maxLength={MAX_CHARS}
        disabled={submitting}
      />
      <MaxLengthHint value={instructions} maxLength={MAX_CHARS} />
      {submitting ? (
        <div role="status" aria-live="polite" style={{ marginTop: 12 }}>
          <Space size={8}>
            <LoadingOutlined spin />
            <Typography.Text strong>正在生成…（已等待 {elapsedSeconds} 秒）</Typography.Text>
          </Space>
          <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
            通常需要 20–60 秒，最长约 3 分钟。这段时间请不要关闭弹窗，完成后会自动刷新预览并提示用时。
          </Typography.Paragraph>
        </div>
      ) : null}
      {error ? <Alert type="error" showIcon message={error} style={{ marginTop: 12 }} /> : null}
    </Modal>
  );
}
