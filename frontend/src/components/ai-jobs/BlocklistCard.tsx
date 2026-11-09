// SPDX-License-Identifier: Apache-2.0
/**
 * Blocklist editor: companies and keywords skipped during collection.
 *
 * Why a separate component: the blocklist is a long-lived preference, not part of the
 * one-off collect form. Keeping it in a card makes it obvious where to change it, and
 * lets the collect flow stay focused on "search -> preview -> import".
 *
 * Matching rule lives on the backend (`is_blocked`): case-insensitive substring against
 * company name or job title. This component only edits the lists.
 */
import { Alert, Button, Card, Input, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { getBlocklist, saveBlocklist } from "../../api/jobHunt";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

const { Text } = Typography;

export default function BlocklistCard() {
  useLocale();
  const [companies, setCompanies] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [companyInput, setCompanyInput] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBlocklist()
      .then((config) => {
        setCompanies(config.companies);
        setKeywords(config.keywords);
      })
      .catch(() => {
        // A failed load must not block the page: the list simply starts empty.
      });
  }, []);

  const add = (
    value: string,
    current: string[],
    setter: (next: string[]) => void,
    clear: () => void,
  ) => {
    const trimmed = value.trim();
    if (!trimmed || current.includes(trimmed)) return;
    setter([...current, trimmed]);
    clear();
    setSaved(false);
  };

  const save = useCallback(async () => {
    setSaving(true);
    setError("");
    try {
      await saveBlocklist({ companies, keywords });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }, [companies, keywords]);

  return (
    <Card
      size="small"
      title={t("aiJobs.native.blocklistTitle")}
      extra={
        <Button size="small" type="primary" loading={saving} onClick={() => void save()}>
          {t("aiJobs.native.blocklistSave")}
        </Button>
      }
    >
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t("aiJobs.native.blocklistHint")}
        </Text>

        {error && <Alert type="error" showIcon message={error} />}
        {saved && <Alert type="success" showIcon message={t("aiJobs.native.blocklistSaved")} />}

        <div>
          <Text strong>{t("aiJobs.native.blocklistCompanies")}</Text>
          <Input
            value={companyInput}
            onChange={(event) => setCompanyInput(event.target.value)}
            onPressEnter={() =>
              add(companyInput, companies, setCompanies, () => setCompanyInput(""))
            }
            placeholder={t("aiJobs.native.blocklistCompanies")}
            style={{ marginTop: 6 }}
          />
          <Space wrap size={4} style={{ marginTop: 6 }}>
            {companies.map((name) => (
              <Tag
                key={name}
                closable
                onClose={() => {
                  setCompanies(companies.filter((item) => item !== name));
                  setSaved(false);
                }}
              >
                {name}
              </Tag>
            ))}
          </Space>
        </div>

        <div>
          <Text strong>{t("aiJobs.native.blocklistKeywords")}</Text>
          <Input
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
            onPressEnter={() =>
              add(keywordInput, keywords, setKeywords, () => setKeywordInput(""))
            }
            placeholder={t("aiJobs.native.blocklistKeywords")}
            style={{ marginTop: 6 }}
          />
          <Space wrap size={4} style={{ marginTop: 6 }}>
            {keywords.map((word) => (
              <Tag
                key={word}
                closable
                onClose={() => {
                  setKeywords(keywords.filter((item) => item !== word));
                  setSaved(false);
                }}
              >
                {word}
              </Tag>
            ))}
          </Space>
        </div>
      </Space>
    </Card>
  );
}
