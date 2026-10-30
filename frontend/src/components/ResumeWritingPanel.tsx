/** 简历写作增强面板：STAR 改写 / 话术生成 / 风格润色 / 中英互译。
 *
 * 输入框里的文字就是父组件选定的那个字段（在整份编辑器里是「个人总结」）：
 * 直接改会通过 `onTextChange` 写回表单，随保存一起落库；生成结果点「回填」覆盖同一段。
 * 早期版本把这段文字放在面板私有 state 里，用户改完点保存却什么也没发生——
 * 因为只有点「回填」才会写到表单，这个坑别再踩。
 */
import { App, Button, Checkbox, Input, Radio, Segmented, Space, Spin, Typography } from "antd";
import { useMemo, useState } from "react";
import {
  generatePhrases,
  polishResumeText,
  rewriteStar,
  translateResumeText,
} from "../api/resumeWriting";
import type {
  PhraseMode,
  PhrasesResult,
  PolishStyle,
  TranslateDirection,
} from "../types/resumeWriting";

type Operation = "star" | "phrases" | "polish" | "translate";

const OPERATIONS: { value: Operation; label: string }[] = [
  { value: "star", label: "STAR 改写" },
  { value: "phrases", label: "话术生成" },
  { value: "polish", label: "风格润色" },
  { value: "translate", label: "中英互译" },
];

const POLISH_STYLES: { value: PolishStyle; label: string }[] = [
  { value: "big_tech", label: "大厂风" },
  { value: "concise_tech", label: "简洁干练风" },
  { value: "campus", label: "应届生风" },
];

const PHRASE_MODES: { value: PhraseMode; label: string }[] = [
  { value: "star", label: "STAR 版" },
  { value: "resume", label: "简历版" },
  { value: "interview", label: "面试口述版" },
];

interface Props {
  resumeId: number;
  initialText?: string;
  /** 把某条结果回填到父组件选定的字段。 */
  onApply: (text: string) => void;
  /** 输入框里的文字改了：父组件应把它写回同一个字段，让「保存」能带走这次编辑。 */
  onTextChange?: (text: string) => void;
}

export default function ResumeWritingPanel({
  resumeId,
  initialText = "",
  onApply,
  onTextChange,
}: Props) {
  const { message } = App.useApp();
  const [text, setText] = useState(initialText);
  const [operation, setOperation] = useState<Operation>("star");
  const [polishStyle, setPolishStyle] = useState<PolishStyle>("concise_tech");
  const [direction, setDirection] = useState<TranslateDirection>("zh2en");
  const [modes, setModes] = useState<PhraseMode[]>(["star", "resume", "interview"]);
  const [loading, setLoading] = useState(false);
  const [singleResult, setSingleResult] = useState("");
  const [phrasesResult, setPhrasesResult] = useState<PhrasesResult | null>(null);

  const editText = (next: string) => {
    setText(next);
    onTextChange?.(next);
  };

  const canRun = useMemo(() => text.trim().length > 0, [text]);

  const run = async () => {
    if (!canRun || loading) return;
    setLoading(true);
    setSingleResult("");
    setPhrasesResult(null);
    try {
      if (operation === "star") {
        setSingleResult((await rewriteStar(resumeId, text.trim())).result);
      } else if (operation === "phrases") {
        setPhrasesResult(await generatePhrases(resumeId, text.trim(), modes));
      } else if (operation === "polish") {
        setSingleResult((await polishResumeText(resumeId, text.trim(), polishStyle)).result);
      } else {
        setSingleResult((await translateResumeText(resumeId, text.trim(), direction)).result);
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : "生成失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const apply = (result: string) => {
    if (!result) return;
    setText(result);
    onApply(result);
    message.success("已回填到个人总结");
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size="middle">
      <Input.TextArea
        rows={4}
        value={text}
        placeholder="这里就是简历里的「个人总结」，可以直接改"
        onChange={(event) => editText(event.target.value)}
        aria-label="写作输入文本"
      />
      <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
        直接改这段文字等于改个人总结，点「保存并更新预览」就会生效；生成结果点「回填」会覆盖这一段。
      </Typography.Text>

      <Segmented
        block
        options={OPERATIONS}
        value={operation}
        onChange={(value) => setOperation(value as Operation)}
      />

      {operation === "polish" && (
        <Radio.Group
          value={polishStyle}
          onChange={(event) => setPolishStyle(event.target.value)}
          aria-label="润色风格"
        >
          {POLISH_STYLES.map((item) => (
            <Radio.Button key={item.value} value={item.value}>
              {item.label}
            </Radio.Button>
          ))}
        </Radio.Group>
      )}

      {operation === "translate" && (
        <Radio.Group
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          aria-label="翻译方向"
        >
          <Radio.Button value="zh2en">中译英</Radio.Button>
          <Radio.Button value="en2zh">英译中</Radio.Button>
        </Radio.Group>
      )}

      {operation === "phrases" && (
        <Checkbox.Group
          options={PHRASE_MODES}
          value={modes}
          onChange={(value) => setModes(value as PhraseMode[])}
          aria-label="话术版式"
        />
      )}

      <Button type="primary" loading={loading} disabled={!canRun} onClick={() => void run()}>
        生成
      </Button>

      {loading && <Spin />}

      {!loading && singleResult && (
        <ResultBlock label="结果" onApply={() => apply(singleResult)}>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {singleResult}
          </Typography.Paragraph>
        </ResultBlock>
      )}

      {!loading && phrasesResult && (
        <Space orientation="vertical" style={{ width: "100%" }} size="small">
          {(
            [
              ["star", "STAR 版"],
              ["resume", "简历版"],
              ["interview", "面试口述版"],
            ] as const
          )
            .filter(([key]) => phrasesResult[key])
            .map(([key, label]) => (
              <ResultBlock key={key} label={label} onApply={() => apply(phrasesResult[key])}>
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
                  {phrasesResult[key]}
                </Typography.Paragraph>
              </ResultBlock>
            ))}
        </Space>
      )}
    </Space>
  );
}

function ResultBlock({
  label,
  onApply,
  children,
}: {
  label: string;
  onApply: () => void;
  children: React.ReactNode;
}) {
  return (
    <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 12 }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Text strong>{label}</Typography.Text>
        <Button size="small" type="link" onClick={onApply}>
          回填
        </Button>
      </Space>
      {children}
    </div>
  );
}
