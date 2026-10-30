/** 可按需读取已保存密钥的输入控件。 */

import { LoadingOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";
import { useEffect, useRef, useState } from "react";
import { API_KEY_MASK, isMaskedApiKey } from "./SettingsConfig";

interface Props {
  id?: string;
  value?: string;
  onChange?: (value: string) => void;
  editing: boolean;
  disabled: boolean;
  resetToken: number;
  onReveal: () => Promise<string>;
  onRevealError: (message: string) => void;
}

export default function ApiKeyInput({
  id,
  value = "",
  onChange,
  editing,
  disabled,
  resetToken,
  onReveal,
  onRevealError,
}: Props) {
  const [visible, setVisible] = useState(false);
  const [revealedKey, setRevealedKey] = useState("");
  const [revealing, setRevealing] = useState(false);
  const revealRequestId = useRef(0);
  const maskedReference = isMaskedApiKey(value) ? value : "";

  // Compiler 规范：随 editing/resetToken 变化的重置用渲染期守卫式调整；ref 失效
  // 递增留在 effect（渲染期禁止写 ref）。
  const [prevResetKey, setPrevResetKey] = useState<{ editing: boolean; resetToken: number } | null>(
    null,
  );
  if (
    prevResetKey === null ||
    prevResetKey.editing !== editing ||
    prevResetKey.resetToken !== resetToken
  ) {
    setPrevResetKey({ editing, resetToken });
    setVisible(false);
    setRevealedKey("");
    setRevealing(false);
  }

  useEffect(() => {
    revealRequestId.current += 1;
  }, [editing, resetToken]);

  useEffect(
    () => () => {
      revealRequestId.current += 1;
    },
    [],
  );

  const changeVisibility = async (nextVisible: boolean) => {
    if (!nextVisible) {
      revealRequestId.current += 1;
      setVisible(false);
      setRevealedKey("");
      setRevealing(false);
      return;
    }
    if (!maskedReference) {
      setVisible(true);
      return;
    }
    if (revealing) return;

    const requestId = ++revealRequestId.current;
    setRevealing(true);
    try {
      const apiKey = await onReveal();
      if (requestId !== revealRequestId.current) return;
      setRevealedKey(apiKey);
      setVisible(true);
    } catch (error) {
      if (requestId !== revealRequestId.current) return;
      setVisible(false);
      setRevealedKey("");
      onRevealError(error instanceof Error ? error.message : "读取 API Key 失败");
    } finally {
      if (requestId === revealRequestId.current) setRevealing(false);
    }
  };

  // 编辑态下掩码不作为可编辑文本回显：显示空串 + 说明性 placeholder，直接输入即替换；
  // 不动输入框时表单里仍是掩码，保存时后端按占位符还原成已存密钥。
  // 非编辑态照旧回显掩码，让用户知道"这里存着密钥"。
  const displayedValue = maskedReference
    ? visible
      ? revealedKey
      : editing
        ? ""
        : API_KEY_MASK
    : value;
  const placeholder =
    maskedReference && editing && !visible
      ? "已保存密钥：直接输入新密钥即可替换，留空保存则保持不变"
      : "sk-...（无需鉴权时可留空）";

  // 编辑态的"已保存但有密钥"需要一个显式清除入口：空框 + 留空保存 = 保持原值，
  // 想改成本地无需鉴权的服务就必须能把已存密钥删掉。
  const clearSavedKey = () => {
    revealRequestId.current += 1;
    setVisible(false);
    setRevealedKey("");
    setRevealing(false);
    onChange?.("");
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Input.Password
          id={id}
          value={displayedValue}
          placeholder={placeholder}
          autoComplete="off"
          readOnly={!editing}
          disabled={disabled || revealing}
          suffix={revealing ? <LoadingOutlined spin /> : undefined}
          visibilityToggle={{
            visible,
            onVisibleChange: (nextVisible) => void changeVisibility(nextVisible),
          }}
          onChange={(event) => {
            if (!editing) return;
            onChange?.(event.target.value);
          }}
        />
      </div>
      {editing && maskedReference ? (
        <Button
          type="link"
          size="small"
          disabled={disabled || revealing}
          onClick={clearSavedKey}
        >
          清除已保存密钥
        </Button>
      ) : null}
    </div>
  );
}
