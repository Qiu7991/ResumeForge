// SPDX-License-Identifier: Apache-2.0
/**
 * 采集的搜索条件：多关键词 + 5 类站点筛选 + 最新优先。
 *
 * 为什么单独成组件：`NativeJobHuntView` 已经 430+ 行（守 500 行预算），而这块是
 * 自成一体的表单——它的选项表、默认值、与"有未生效筛选"的提示都在这里收口。
 *
 * 编码表**不在前端**：界面上是中文标签，后端用 `services/job_hunt/search_filters`
 * 按已验证的离线快照折成 BOSS 数字编码。前端自己写一份映射必然分叉，而分叉的后果是
 * 静默筛错（站点不报错，返回的却是没筛过的结果）。
 */
import { Checkbox, Select, Space, Tooltip, Typography } from "antd";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

const { Text } = Typography;

/**
 * 经验/学历等分组的可选项。
 *
 * **这些中文是协议值，不是界面文案**：它们原样发给后端，由
 * `services/job_hunt/search_filters` 按已验证的离线快照折成 BOSS 数字编码
 * （"应届生" → `102`）。翻成 i18n key 会让后端认不出来 —— 那是静默筛错。
 *
 * 前端不做"显示中文/发送编码"的双轨，因为两份映射必然分叉，而分叉的后果是
 * 站点不报错、返回的却是没筛过的结果。
 */
// 每行行尾标 i18n-ok：守卫只认「本行行尾」或「上一行」的标记，写在块注释里不算。
// 为什么是豁免而不是走语言包：这些中文是**发给后端的协议值**（后端折成 BOSS 编码），
// 翻成 i18n key 后端就认不出来了。
export const FILTER_OPTIONS: Record<string, string[]> = {
  jobType: ["全职", "兼职", "实习"], // i18n-ok: 协议值，后端折成站点编码
  experience: [
    "在校生", // i18n-ok: 协议值
    "应届生", // i18n-ok: 协议值
    "经验不限", // i18n-ok: 协议值
    "1年以内", // i18n-ok: 协议值
    "1-3年", // i18n-ok: 协议值
    "3-5年", // i18n-ok: 协议值
    "5-10年", // i18n-ok: 协议值
    "10年以上", // i18n-ok: 协议值
  ],
  degree: [
    "学历不限", // i18n-ok: 协议值
    "初中及以下", // i18n-ok: 协议值
    "中专/中技", // i18n-ok: 协议值
    "高中", // i18n-ok: 协议值
    "大专", // i18n-ok: 协议值
    "本科", // i18n-ok: 协议值
    "硕士", // i18n-ok: 协议值
    "博士", // i18n-ok: 协议值
  ],
  scale: [
    "0-20人", // i18n-ok: 协议值
    "20-99人", // i18n-ok: 协议值
    "100-499人", // i18n-ok: 协议值
    "500-999人", // i18n-ok: 协议值
    "1000-9999人", // i18n-ok: 协议值
    "10000人以上", // i18n-ok: 协议值
  ],
  salary: [
    "3K以下", // i18n-ok: 协议值
    "3-5K", // i18n-ok: 协议值
    "5-10K", // i18n-ok: 协议值
    "10-20K", // i18n-ok: 协议值
    "20-50K", // i18n-ok: 协议值
    "50K以上", // i18n-ok: 协议值
  ],
};

/** 分组 → i18n 标签 key。 */
const GROUP_LABEL_KEYS = {
  jobType: "aiJobs.hunt.filter.jobType",
  experience: "aiJobs.hunt.filter.experience",
  degree: "aiJobs.hunt.filter.degree",
  scale: "aiJobs.hunt.filter.scale",
  salary: "aiJobs.hunt.filter.salary",
} as const;

export type FilterGroupKey = keyof typeof GROUP_LABEL_KEYS;

/**
 * 出厂默认条件：**打开页面就能直接点「开始采集」**，不用每次手填。
 *
 * 这组值对齐 BossHunter 的出厂配置思路（多个相关词 + 经验/学历/类型筛选 + 最新优先），
 * 并按"AI 岗 + 广州 + 应届到 3 年"的具体处境调过：
 * - 4 个关键词覆盖 AI / AI应用 / 大模型 / Agent 四种叫法（招聘方用词不统一）
 * - 经验收到「应届生 + 1年以内 + 1-3年」——再宽会混进要求 5 年的岗
 * - 学历本科、求职类型全职
 *
 * 关键词是**用户内容**（他要搜什么），不是界面文案——所以不进语言包。
 */
export const DEFAULT_KEYWORDS = ["AI", "AI应用", "大模型", "Agent"]; // i18n-ok: 搜索词，直接发给站点
export const DEFAULT_FILTERS: Record<string, string[]> = {
  jobType: ["全职"], // i18n-ok: 协议值
  experience: ["应届生", "1年以内", "1-3年"], // i18n-ok: 协议值
  degree: ["本科"], // i18n-ok: 协议值
};

interface Props {
  keywords: string[];
  onKeywordsChange: (next: string[]) => void;
  filters: Record<string, string[]>;
  onFiltersChange: (next: Record<string, string[]>) => void;
  newestFirst: boolean;
  onNewestFirstChange: (next: boolean) => void;
  /** 未生效的筛选项（后端回报），界面要如实显示。 */
  unapplied?: string[];
}

export default function HuntFilterForm({
  keywords,
  onKeywordsChange,
  filters,
  onFiltersChange,
  newestFirst,
  onNewestFirstChange,
  unapplied = [],
}: Props) {
  // 模块级 t()：必须订阅语言变化，否则切语言后这一块不重渲染。
  useLocale();

  const setGroup = (group: string, values: string[]) => {
    const next = { ...filters };
    if (values.length === 0) {
      delete next[group];
    } else {
      next[group] = values;
    }
    onFiltersChange(next);
  };

  return (
    <Space orientation="vertical" size={8} style={{ width: "100%" }}>
      <Space wrap size={8}>
        <Tooltip title={t("aiJobs.hunt.keywordsHint")}>
          <Select
            mode="tags"
            value={keywords}
            onChange={(values) => onKeywordsChange(values as string[])}
            placeholder={t("aiJobs.hunt.keywordsLabel")}
            // 选项留空：这是自由输入，"tags" 模式下回车即添加。
            options={[]}
            style={{ minWidth: 320 }}
            aria-label={t("aiJobs.hunt.keywordsLabel")}
          />
        </Tooltip>

        {(Object.keys(GROUP_LABEL_KEYS) as FilterGroupKey[]).map((group) => (
          <Tooltip key={group} title={t(GROUP_LABEL_KEYS[group])}>
            <Select
              mode="multiple"
              allowClear
              value={filters[group] ?? []}
              onChange={(values) => setGroup(group, values as string[])}
              placeholder={t(GROUP_LABEL_KEYS[group])}
              options={FILTER_OPTIONS[group].map((label) => ({ value: label, label }))}
              style={{ minWidth: 132 }}
              aria-label={t(GROUP_LABEL_KEYS[group])}
            />
          </Tooltip>
        ))}

        <Tooltip title={t("aiJobs.hunt.newestFirstHint")}>
          <Checkbox checked={newestFirst} onChange={(e) => onNewestFirstChange(e.target.checked)}>
            {t("aiJobs.hunt.newestFirst")}
          </Checkbox>
        </Tooltip>
      </Space>

      {unapplied.length > 0 ? (
        <Text type="warning" style={{ fontSize: 12 }}>
          {t("aiJobs.hunt.unapplied", { list: unapplied.join(t("aiJobs.native.errorSeparator")) })}
        </Text>
      ) : null}
    </Space>
  );
}
