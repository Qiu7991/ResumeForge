// SPDX-License-Identifier: Apache-2.0
/**
 * 资料页的日期输入：**直接打字**（YYYY / YYYY-MM / YYYY-MM-DD），不再弹三个下拉。
 *
 * 2026-11 用户反馈：点年份下拉时整页抖动、Ego Lite 里甚至不显示选项。日期在资料页
 * 是高频编辑项，三个联动 Select 的弹层在滚动容器里既慢又脆；改成单输入框 + 失焦归一化
 * 后，修改只需敲键，且彻底没有弹层定位问题。
 */
import { Checkbox, Input, Space, Typography } from "antd";
import { memo, useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import {
  arePartialDatePropsEqual,
  normalizePartialDate,
  parsePartialDate,
  type PartialDateSelectProps as Props,
} from "./partialDate";

function PartialDateInputImpl({
  id,
  value = "",
  onChange,
  disabled,
  label,
  allowOngoing = false,
  yearOnly = false,
}: Props) {
  useLocale();
  const parsed = parsePartialDate(value);
  const ongoing = Boolean(parsed?.ongoing);
  const [draft, setDraft] = useState(ongoing ? "" : value);
  const [prevValue, setPrevValue] = useState(value);
  if (prevValue !== value) {
    // 外部值变化（切条目/撤销/服务端刷新）时同步输入框；渲染期守卫式调整。
    setPrevValue(value);
    setDraft(ongoing ? "" : value);
  }
  const lastConcreteRef = useRef("");
  useEffect(() => {
    if (!ongoing && value.trim()) lastConcreteRef.current = value;
  }, [value, ongoing]);

  const unsupported = value.trim() && !parsed;
  const commit = () => onChange?.(normalizePartialDate(draft));

  return (
    <div className="profile-partial-date-select">
      <Space.Compact block className="profile-partial-date-select__controls">
        <Input
          id={id}
          aria-label={t(
            yearOnly ? "dateFields.aria.inputYear" : "dateFields.aria.input",
            { label },
          )}
          value={draft}
          disabled={disabled || ongoing || undefined}
          placeholder={t(
            yearOnly ? "dateFields.placeholder.inputYear" : "dateFields.placeholder.input",
          )}
          onChange={(event) => {
            setDraft(event.target.value);
            // 输入中的原文先进表单，失焦时再归一化；这样不会吞掉用户正在敲的字符。
            onChange?.(event.target.value);
          }}
          onBlur={commit}
          onPressEnter={commit}
          allowClear
        />
      </Space.Compact>
      {allowOngoing ? (
        <Checkbox
          className="profile-partial-date-select__ongoing"
          checked={ongoing}
          disabled={disabled || undefined}
          onChange={(event) => {
            if (event.target.checked) {
              setDraft("");
              onChange?.("至今"); // i18n-ok: 存储协议值
            } else {
              const restored = lastConcreteRef.current;
              setDraft(restored);
              onChange?.(restored);
            }
          }}
        >
          {t("dateFields.ongoing")}
        </Checkbox>
      ) : null}
      {unsupported ? (
        <Typography.Text type="warning" style={{ flexBasis: "100%", marginTop: 4 }}>
          {t("dateFields.parseUnsupported")}
        </Typography.Text>
      ) : null}
    </div>
  );
}

export default memo(PartialDateInputImpl, arePartialDatePropsEqual);
