// SPDX-License-Identifier: Apache-2.0
/** AI 修改简历：输入修改要求（可留空整体重写），修订结果直接更新当前记录。 */
import { LoadingOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Alert, App, Input, Modal, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { reviseResume } from "../../api/resumes";
import { useI18n } from "../../i18n/i18nContext";
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
  const { t } = useI18n();
  const { message } = App.useApp();
  const [instructions, setInstructions] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // 生成期间给一个会走的计时：模型这一轮通常 20–60 秒，只转按钮用户会以为卡死。
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState("");
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
        instructions.trim()
          ? t("resume.revise.successTargetedSeconds", { seconds })
          : t("resume.revise.successFullSeconds", { seconds }),
      );
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("resume.revise.failed"));
    } finally {
      setSubmitting(false);
    }
  };

  const hasInstructions = instructions.trim().length > 0;

  return (
    <Modal
      title={
        <span>
          <ThunderboltOutlined /> {t("resume.revise.title")}
        </span>
      }
      open={open}
      // 提交期间锁住弹窗：请求是同步的，关掉会让结果落库了却没刷新预览，界面与库不一致。
      onCancel={() => {
        if (!submitting) close();
      }}
      closable={!submitting}
      mask={{ closable: false }}
      keyboard={!submitting}
      cancelButtonProps={{ disabled: submitting }}
      confirmLoading={submitting}
      onOk={() => void submit()}
      okText={
        submitting
          ? t("resume.revise.submitting", { seconds: elapsedSeconds })
          : hasInstructions
            ? t("resume.revise.okTargeted")
            : t("resume.revise.okFull")
      }
      width={560}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {hasInstructions ? t("resume.revise.hintTargeted") : t("resume.revise.hintFull")}
      </Typography.Paragraph>
      <Input.TextArea
        value={instructions}
        onChange={(event) => setInstructions(event.target.value.slice(0, MAX_CHARS))}
        placeholder={t("resume.revise.placeholder", { max: MAX_CHARS })}
        autoSize={{ minRows: 4, maxRows: 10 }}
        maxLength={MAX_CHARS}
        disabled={submitting}
      />
      <MaxLengthHint value={instructions} maxLength={MAX_CHARS} />
      {submitting ? (
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          <LoadingOutlined /> {t("resume.revise.waiting", { seconds: elapsedSeconds })}
        </Typography.Paragraph>
      ) : null}
      {error ? <Alert type="error" showIcon title={error} style={{ marginTop: 12 }} /> : null}
    </Modal>
  );
}
