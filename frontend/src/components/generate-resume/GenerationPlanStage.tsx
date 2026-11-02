// SPDX-License-Identifier: Apache-2.0
/** 生成前匹配报告：每条 JD 要求 → 直接/可迁移证据 → 缺口；可勾选换项目。 */
import { Alert, Button, Card, Checkbox, Empty, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type {
  GenerationPlan,
  GenerationPlanEvidence,
  GenerationPlanRequirement,
  PlanMatch,
} from "../../types/generationPlan";

interface Props {
  plan: GenerationPlan;
  saving: boolean;
  onBack: () => void;
  onSkip: () => void;
  onGenerate: (planId: number, selectedEvidenceIds: string[]) => void;
}

const MATCH_COLOR: Record<PlanMatch, string> = {
  direct: "green",
  transferable: "gold",
  none: "default",
};

function matchLabel(match: PlanMatch): string {
  if (match === "direct") return t("generate.plan.match.direct");
  if (match === "transferable") return t("generate.plan.match.transferable");
  return t("generate.plan.match.none");
}

function refLabel(refType: GenerationPlanEvidence["ref_type"]): string {
  if (refType === "project") return t("generate.plan.ref.project");
  if (refType === "experience") return t("generate.plan.ref.experience");
  return t("generate.plan.ref.claim");
}

export default function GenerationPlanStage({
  plan,
  saving,
  onBack,
  onSkip,
  onGenerate,
}: Props) {
  useLocale();
  const [selected, setSelected] = useState<string[]>(() =>
    plan.evidence.filter((item) => item.selected).map((item) => item.id),
  );

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const byRequirement = useMemo(() => {
    const grouped: Record<string, GenerationPlanEvidence[]> = {};
    for (const item of plan.evidence) {
      if (item.match === "none") continue;
      (grouped[item.requirement_id] ??= []).push(item);
    }
    return grouped;
  }, [plan.evidence]);

  const requirementStatus = (requirement: GenerationPlanRequirement) => {
    const items = byRequirement[requirement.id] ?? [];
    const chosen = items.filter((item) => selectedSet.has(item.id));
    if (chosen.some((item) => item.match === "direct")) return "direct" as const;
    if (chosen.some((item) => item.match === "transferable")) return "transferable" as const;
    return "gap" as const;
  };

  const selectedFor = (requirementId: string) =>
    (byRequirement[requirementId] ?? []).filter((item) => selectedSet.has(item.id)).length;

  const toggle = (item: GenerationPlanEvidence, checked: boolean) => {
    setSelected((current) => {
      if (!checked) return current.filter((id) => id !== item.id);
      if (current.includes(item.id)) return current;
      if (selectedFor(item.requirement_id) >= 2) return current;
      return [...current, item.id];
    });
  };

  const coverage = plan.coverage ?? {
    direct: 0,
    transferable: 0,
    gaps: [],
    by_requirement: {},
  };
  const gapCount = plan.requirements.filter(
    (requirement) => requirementStatus(requirement) === "gap",
  ).length;

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {t("generate.plan.title")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {t("generate.plan.subtitle")}
      </Typography.Paragraph>

      <Space wrap size={8} style={{ marginBottom: 12 }}>
        <Tag color="green">
          {t("generate.plan.coverage.direct")} {coverage.direct ?? 0}
        </Tag>
        <Tag color="gold">
          {t("generate.plan.coverage.transferable")} {coverage.transferable ?? 0}
        </Tag>
        <Tag color={gapCount ? "red" : "default"}>
          {t("generate.plan.coverage.gap")} {gapCount}
        </Tag>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("generate.plan.selectedCount", { count: selected.length })}
        </Typography.Text>
      </Space>

      {plan.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("generate.plan.warnings")}
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {plan.warnings.slice(0, 8).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          }
        />
      )}

      {plan.requirements.length === 0 ? (
        <Empty description={t("generate.plan.empty")} />
      ) : (
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          {plan.requirements.map((requirement) => {
            const status = requirementStatus(requirement);
            const items = byRequirement[requirement.id] ?? [];
            const chosen = selectedFor(requirement.id);
            return (
              <Card
                key={requirement.id}
                size="small"
                title={
                  <Space wrap size={6}>
                    <Tag>{requirement.id}</Tag>
                    <span>{requirement.text}</span>
                    <Tag>{t("generate.plan.weight", { weight: requirement.weight })}</Tag>
                    <Tag color={status === "direct" ? "green" : status === "transferable" ? "gold" : "red"}>
                      {status === "direct"
                        ? t("generate.plan.coverage.direct")
                        : status === "transferable"
                          ? t("generate.plan.coverage.transferable")
                          : t("generate.plan.coverage.gap")}
                    </Tag>
                  </Space>
                }
              >
                {items.length === 0 ? (
                  <Typography.Text type="secondary">
                    {t("generate.plan.noEvidence")}
                  </Typography.Text>
                ) : (
                  <Space direction="vertical" size={10} style={{ width: "100%" }}>
                    {items.map((item) => {
                      const checked = selectedSet.has(item.id);
                      const disabled = !checked && chosen >= 2;
                      return (
                        <div
                          key={item.id}
                          style={{
                            border: "1px solid var(--rf-border-color, #f0f0f0)",
                            borderRadius: 8,
                            padding: 10,
                            background: checked
                              ? "var(--rf-fill-quaternary, #fafafa)"
                              : undefined,
                          }}
                        >
                          <Checkbox
                            checked={checked}
                            disabled={disabled}
                            onChange={(event) => toggle(item, event.target.checked)}
                          >
                            <Space wrap size={6}>
                              <Tag color={MATCH_COLOR[item.match]}>{matchLabel(item.match)}</Tag>
                              <Tag>{refLabel(item.ref_type)}</Tag>
                              <Typography.Text strong>{item.ref_name}</Typography.Text>
                            </Space>
                          </Checkbox>
                          {item.rationale && (
                            <Typography.Paragraph
                              type="secondary"
                              style={{ margin: "6px 0 0 24px", fontSize: 12 }}
                            >
                              {item.rationale}
                            </Typography.Paragraph>
                          )}
                          {item.fact_quotes.length > 0 && (
                            <div style={{ margin: "6px 0 0 24px" }}>
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                {t("generate.plan.quotes")}
                              </Typography.Text>
                              {item.fact_quotes.map((quote) => (
                                <Typography.Paragraph
                                  key={quote}
                                  style={{
                                    margin: "2px 0",
                                    paddingLeft: 8,
                                    borderLeft: "2px solid #d9d9d9",
                                    fontSize: 12,
                                  }}
                                >
                                  {quote}
                                </Typography.Paragraph>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </Space>
                )}
                {status === "gap" && (
                  <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 12 }}>
                    {t("generate.plan.gapHint")}
                  </Typography.Paragraph>
                )}
              </Card>
            );
          })}
        </Space>
      )}

      <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between", gap: 8 }}>
        <Button onClick={onBack}>{t("generate.plan.action.back")}</Button>
        <Space wrap>
          <Button onClick={onSkip}>{t("generate.plan.action.skip")}</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={plan.requirements.length === 0}
            onClick={() => onGenerate(plan.id, selected)}
          >
            {saving ? t("generate.plan.action.saving") : t("generate.plan.action.generate")}
          </Button>
        </Space>
      </div>
    </div>
  );
}
