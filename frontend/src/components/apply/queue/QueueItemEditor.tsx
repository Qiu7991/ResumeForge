// SPDX-License-Identifier: Apache-2.0
/**
 * 编辑某条队列条目的招呼语与简历；招呼语可先按岗位生成一版再改。
 * （自 ApplyQueuePanel 拆出，逐字搬运，行为等价；App.useApp() 原本就在本组件内调用。）
 */
import { App, Button, Form, Modal, Select, Space, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { previewGreeting, updateQueueItem } from "../../../api/apply";
import { getJob } from "../../../api/jobs";
import { getResume } from "../../../api/resumes";
import AbortButton from "../../common/AbortButton";
import { errorText, useAbortableRequest } from "../../../hooks/useAbortableRequest";
import { useResumeSearchSelectForJob } from "../../../hooks/remoteSearchOptions";
import { t } from "../../../i18n";
import { useLocale } from "../../../i18n/i18nContext";
import { HintedTextArea } from "../../common/MaxLengthHint";
import type { ApplyQueueItem } from "../../../types";

/** 从 v2 简历文档里取项目名（`projects` 分区每个条目的 `name` 字段）。 */
function projectNamesOf(content: unknown): string[] {
  const sections = (content as { sections?: Array<Record<string, unknown>> } | null)?.sections;
  if (!Array.isArray(sections)) return [];
  const projectSection = sections.find((section) => section?.key === "projects");
  const entries = (projectSection?.entries as Array<Record<string, unknown>> | undefined) ?? [];
  const names: string[] = [];
  for (const entry of entries) {
    const items = (entry?.items as Array<Record<string, unknown>> | undefined) ?? [];
    for (const item of items) {
      if (item?.key === "name" && typeof item.value === "string" && item.value.trim()) {
        names.push(item.value.trim());
      }
    }
  }
  return names;
}

export function QueueItemEditor({
  item,
  onClose,
  onSaved,
}: {
  item: ApplyQueueItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  // 本组件用模块级 t()：必须订阅语言变化，否则切语言后弹窗停在旧文案。
  useLocale();
  const [form] = Form.useForm<{ greeting: string; resume_id?: number }>();
  // 简历下拉改为远程搜索（P0-1）：候选限定该岗位关联过的简历，
  // 编辑器挂载即打开，挂载时回查已选值并预拉第一页候选。
  const resumeSelect = useResumeSearchSelectForJob(item.job_id);
  // 招呼语是现场生成的一小段文案，但同样要等模型回包：等着的时候可以停。
  const greetingRequest = useAbortableRequest();
  const generating = greetingRequest.loading;
  const [saving, setSaving] = useState(false);
  // 岗位 JD：写招呼语时要能对照职位描述，否则只能凭标题猜「贵司岗位 JD」写了什么。
  // 展开时才拉取（`/jobs/{id}` 带完整正文），拉过一次就缓存，收起再开不重复请求。
  const [jdOpen, setJdOpen] = useState(false);
  const [jdLoading, setJdLoading] = useState(false);
  const [jd, setJd] = useState<{ description: string; requirements: string } | null>(null);
  // 这条招呼语第 3 句讲哪个项目：有全项目简历时，自动挑未必合心意（例如总是挑到 AIGC），
  // 这里给一个显式选择。只影响这次生成，不写回简历。
  const watchedResumeId = Form.useWatch("resume_id", form) as number | undefined;
  const [projects, setProjects] = useState<string[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [focusProject, setFocusProject] = useState<string | undefined>(undefined);

  const loadJd = async (jobId: number) => {
    setJdLoading(true);
    try {
      const job = await getJob(jobId);
      setJd({ description: job.description || "", requirements: job.requirements || "" });
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("applyQueue.editor.jdFailed"));
    } finally {
      setJdLoading(false);
    }
  };

  const toggleJd = () => {
    const next = !jdOpen;
    setJdOpen(next);
    if (next && jd === null && !jdLoading && item.job_id != null) void loadJd(item.job_id);
  };

  useEffect(() => {
    form.setFieldsValue({ greeting: item.greeting, resume_id: item.resume_id ?? undefined });
  }, [form, item]);

  useEffect(() => {
    // 已选简历的保显示（P0-1）：按 id 回查补进候选，再预拉第一页候选。
    void resumeSelect.ensure(item.resume_id);
    void resumeSelect.reload();
    // 编辑目标在本组件生命周期内不变，只在挂载时执行一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 项目候选取自「当前选中的简历」：换简历后选项跟着换，旧选择不在新列表里就清掉，
  // 避免把别的简历里的项目名发给模型。
  useEffect(() => {
    const resumeId = watchedResumeId ?? item.resume_id ?? null;
    if (resumeId == null) {
      setProjects([]);
      setFocusProject(undefined);
      return undefined;
    }
    let cancelled = false;
    setProjectsLoading(true);
    getResume(resumeId)
      .then((detail) => {
        if (cancelled || !detail) return;
        const names = projectNamesOf(detail.content);
        setProjects(names);
        setFocusProject((current) =>
          current && names.includes(current) ? current : undefined,
        );
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [watchedResumeId, item.resume_id]);

  const generateGreeting = async () => {
    // 先落到局部常量：闭包里读 `item.job_id` 会丢掉上面的判空收窄（TS 不跨回调保留）。
    const jobId = item.job_id;
    if (jobId == null) return;
    // 下拉里刚选的简历可能还没保存：一起传过去，招呼语才和将要用那份简历一致。
    const resumeId = form.getFieldValue("resume_id") as number | undefined;
    const outcome = await greetingRequest.run((signal) =>
      previewGreeting(
        {
          job_id: jobId,
          item_id: item.id,
          resume_id: resumeId,
          focus_project: focusProject,
        },
        signal,
      ),
    );
    if (outcome.status === "error") {
      message.error(errorText(outcome.error, t("applyQueue.toast.greetingFailed")));
      return;
    }
    if (outcome.status === "aborted") return;
    if (outcome.data.source === "no_resume") {
      // 没有简历就不生成：招呼语必须是「这份简历 + 这个岗位」的投影。
      message.warning(t("applyQueue.toast.greetingNoResume"));
      return;
    }
    form.setFieldValue("greeting", outcome.data.greeting);
    message.success(
      outcome.data.source === "generated"
        ? t("applyQueue.toast.greetingGenerated")
        : t("applyQueue.toast.greetingDefault"),
    );
  };

  const save = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const greeting = values.greeting ?? "";
      // 换简历时，只有「文案也跟着变了」（重新生成或手改）才算用户确认了眼前这段字；
      // 只是换了简历、文案原样带回来，仍然打回未确认，避免把对旧简历写的文案发出去。
      const resumeChanged = (values.resume_id ?? null) !== (item.resume_id ?? null);
      const greetingChanged = greeting !== item.greeting;
      const saved = await updateQueueItem(item.id, {
        greeting,
        // 保存 = 用户看过这段字：显式确认，批量生成的草稿也在这里转正。
        confirm_greeting: !(resumeChanged && !greetingChanged),
        ...(values.resume_id ? { resume_id: values.resume_id } : {}),
      });
      if (values.greeting && saved.greeting_confirmed === false) {
        message.warning(t("applyQueue.toast.resumeChangedGreeting"));
      } else if (values.greeting) {
        // 「保存」就是这一步的确认动作：明确回执，用户才知道这条已经可以投了。
        message.success(t("applyQueue.toast.savedConfirmed"));
      } else {
        message.success(t("applyQueue.toast.updated"));
      }
      onSaved();
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("applyQueue.toast.updateFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("applyQueue.editor.title", {
        title: item.job_title || t("applyQueue.editor.untitledJob"),
      })}
      open
      onCancel={onClose}
      footer={null}
      mask={{ closable: false }}
      width={760}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="resume_id"
          label={t("applyQueue.detail.resume")}
          extra={t("applyQueue.editor.resumeHint")}
        >
          <Select
            allowClear
            placeholder={t("applyQueue.editor.resumePlaceholder")}
            {...resumeSelect.selectProps}
          />
        </Form.Item>
        <Form.Item
          label={t("applyQueue.editor.focusProject.label")}
          extra={t("applyQueue.editor.focusProject.hint")}
        >
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            loading={projectsLoading}
            disabled={projects.length === 0}
            value={focusProject}
            onChange={(value) => setFocusProject(value ?? undefined)}
            placeholder={
              projects.length === 0
                ? t("applyQueue.editor.focusProject.empty")
                : t("applyQueue.editor.focusProject.placeholder")
            }
            options={projects.map((name) => ({ value: name, label: name }))}
          />
        </Form.Item>
        <Form.Item
          name="greeting"
          label={t("applyQueue.detail.greeting")}
          extra={t("applyQueue.editor.saveConfirmHint")}
        >
          {/* 从招呼语标签点进来时光标直接落在这里；7–16 行自适应，长招呼语不用一直滚。 */}
          <HintedTextArea
            autoSize={{ minRows: 7, maxRows: 16 }}
            maxLength={1000}
            autoFocus
          />
        </Form.Item>
      </Form>
      {/* 写招呼语时对照 JD：收起时只占一行链接，展开后是可滚动的只读正文。 */}
      <div className="apply-queue-jd">
        <Button
          type="link"
          size="small"
          style={{ paddingInline: 0 }}
          onClick={toggleJd}
          disabled={item.job_id == null}
        >
          {jdOpen ? t("applyQueue.editor.hideJd") : t("applyQueue.editor.viewJd")}
        </Button>
        {item.job_id == null && (
          <Typography.Text type="secondary">{t("applyQueue.editor.jdNoJob")}</Typography.Text>
        )}
        {jdOpen && item.job_id != null && (
          <div className="apply-queue-jd-body" role="region" aria-label={t("applyQueue.editor.viewJd")}>
            {jdLoading ? (
              <Space size={8}>
                <Spin size="small" />
                <Typography.Text type="secondary">{t("applyQueue.editor.jdLoading")}</Typography.Text>
              </Space>
            ) : jd === null ? null : !jd.description.trim() && !jd.requirements.trim() ? (
              <Typography.Text type="secondary">{t("applyQueue.editor.jdEmpty")}</Typography.Text>
            ) : (
              <Space orientation="vertical" size={6} style={{ width: "100%" }}>
                {jd.description.trim() ? (
                  <div>
                    <Typography.Text strong>{t("applyQueue.editor.jdDescription")}</Typography.Text>
                    <Typography.Paragraph style={{ whiteSpace: "pre-wrap", margin: "2px 0 0" }}>
                      {jd.description}
                    </Typography.Paragraph>
                  </div>
                ) : null}
                {jd.requirements.trim() ? (
                  <div>
                    <Typography.Text strong>{t("applyQueue.editor.jdRequirements")}</Typography.Text>
                    <Typography.Paragraph style={{ whiteSpace: "pre-wrap", margin: "2px 0 0" }}>
                      {jd.requirements}
                    </Typography.Paragraph>
                  </div>
                ) : null}
              </Space>
            )}
          </div>
        )}
      </div>
      <Space>
        <Button onClick={() => void generateGreeting()} loading={generating}>
          {t("applyQueue.editor.generate")}
        </Button>
        {generating && <AbortButton onClick={() => greetingRequest.cancel()} />}
        <Button type="primary" loading={saving} onClick={() => void save()}>
          {t("applyQueue.editor.saveConfirm")}
        </Button>
        <Button onClick={onClose}>{t("common.action.cancel")}</Button>
      </Space>
    </Modal>
  );
}
