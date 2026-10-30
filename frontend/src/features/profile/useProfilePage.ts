/** 我的资料页状态、加载保存和拖拽/粘贴操作。 */

import { App, Form, Upload } from "antd";
import type { FormInstance, UploadProps } from "antd";
import { useEffect, useRef, useState } from "react";
import { getProfile, parseProfileText, saveProfile } from "../../api/profile";
import { normalizeSectionOrder } from "../../components/profile/ProfileSectionConfig";
import { attachmentInputs, useRecognitionFiles } from "../../hooks/useRecognitionFiles";
import type { Profile, RecognitionSource } from "../../types";
import { mergeParsedProfileValues } from "../../utils/profileText";
import { useProfileSectionReorder } from "./useProfileSectionReorder";

export type ProfileFormValues = Omit<Profile, "id" | "updated_at">;

const PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const PHOTO_MAX_BYTES = 2 * 1024 * 1024;

/**
 * 字段名 → 中文标签。`validateFields()` 的 `errorFields` 只给字段路径（如 `name`），
 * 不给表单项的 label，所以提示条里必须自己翻译一次，否则用户看到的是英文 key。
 * 只收必填与常见字段：没登记的字段退回字段名，至少能定位。
 */
const FIELD_LABELS: Record<string, string> = {
  name: "姓名",
  phone: "手机号",
  email: "邮箱",
  city: "所在城市",
  job_intent: "求职意向",
  summary: "个人总结",
  school: "学校",
  major: "专业",
  company: "公司",
  role: "角色/职位",
  organization: "组织/部门",
  project_name: "项目名称",
  skill_name: "技能名称",
  award_name: "奖项名称",
  title: "名称",
};

/**
 * 表单校验失败时的可见反馈：列出没填好的字段并滚到第一个错误处。
 *
 * 为什么必须有这一步：`form.validateFields()` 失败只 reject、不弹任何东西，调用方以前
 * 直接 `catch { return false }`，于是用户点「保存全部资料」看到的就是"按钮点了没反应"。
 * 而红字提示可能远在下方几屏（姓名在页头、技能在页尾），滚动到错误处比只弹一条提示更
 * 能让人立刻明白卡在哪。
 */
function reportValidationFailure(
  form: FormInstance<ProfileFormValues>,
  message: { error: (content: string) => void },
  error: unknown,
): void {
  const errorFields = (
    error as { errorFields?: { name: (string | number)[]; errors: string[] }[] } | null
  )?.errorFields;
  if (!errorFields || errorFields.length === 0) {
    message.error("资料没有保存：有字段没填好，请检查页面上的红字提示");
    return;
  }

  // 字段路径转成可读名：数组下标换成「第 N 条」，键名翻成中文。
  const describe = (field: { name: (string | number)[]; errors: string[] }): string => {
    const parts: string[] = [];
    for (let index = 0; index < field.name.length; index += 1) {
      const part = field.name[index];
      if (typeof part === "number") {
        parts.push(`第 ${part + 1} 条`);
        continue;
      }
      // 紧跟在数组下标后的键是条目内的字段，直接用中文名即可（不必重复"第 N 条 学校"）。
      parts.push(FIELD_LABELS[part] ?? String(part));
    }
    return `${parts.join(" ")}（${field.errors[0] || "没填好"}）`;
  };

  const labels = errorFields.map(describe);
  const shown = labels.slice(0, 3).join("、");
  const more = labels.length > 3 ? ` 等 ${labels.length} 处` : "";
  message.error(`资料没有保存：${shown}${more}`);

  // 滚到第一个错误字段，并聚焦它——提示条会消失，位置不会。
  const first = errorFields[0].name;
  if (first.length > 0) {
    window.setTimeout(() => {
      form.scrollToField(first, { behavior: "smooth", block: "center" });
      const instance = form.getFieldInstance(first) as { focus?: () => void } | undefined;
      instance?.focus?.();
    });
  }
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new Error("读取照片失败"));
    reader.readAsDataURL(file);
  });
}

function toFormValues(profile: Profile): ProfileFormValues {
  return {
    photo: profile.photo,
    name: profile.name,
    gender: profile.gender,
    birth_year: profile.birth_year,
    phone: profile.phone,
    email: profile.email,
    city: profile.city,
    target_city: profile.target_city,
    job_intent: profile.job_intent,
    personal_website: profile.personal_website,
    github: profile.github,
    summary: profile.summary,
    // 网申专用字段必须一起带上：保存是**整体替换**，漏一个就等于把它清空。
    wechat: profile.wechat,
    birth_date: profile.birth_date,
    id_type: profile.id_type,
    id_number: profile.id_number,
    country_region: profile.country_region,
    native_place: profile.native_place,
    political_status: profile.political_status,
    phone_country_code: profile.phone_country_code,
    family_info: profile.family_info,
    expected_salary: profile.expected_salary,
    qq: profile.qq,
    advisor: profile.advisor,
    research_direction: profile.research_direction,
    preferred_industry: profile.preferred_industry,
    section_order: normalizeSectionOrder(profile.section_order),
    educations: profile.educations,
    experiences: profile.experiences,
    campus_experiences: profile.campus_experiences,
    projects: profile.projects,
    skills: profile.skills,
    awards: profile.awards,
  };
}

export function useProfilePage() {
  const [form] = Form.useForm<ProfileFormValues>();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [photoReading, setPhotoReading] = useState(false);
  const [profileTextOpen, setProfileTextOpen] = useState(false);
  const [profileText, setProfileText] = useState("");
  const [profileTextWarnings, setProfileTextWarnings] = useState<string[]>([]);
  const [profileTextParsing, setProfileTextParsing] = useState(false);
  // 上传进度（0-100；null 表示不在上传中）：附件 base64 进 JSON 体，大文件上传
  // 可达数秒以上，弹窗里画出进度条比一个转圈按钮更让人安心。
  const [profileTextUploadPercent, setProfileTextUploadPercent] = useState<number | null>(null);
  const [profileTextRecognized, setProfileTextRecognized] = useState("");
  const [profileTextSource, setProfileTextSource] = useState<RecognitionSource | null>(null);
  const {
    files,
    reading: filesReading,
    addFiles,
    removeFile,
    clear: clearFiles,
    onPaste: onPasteFiles,
  } = useRecognitionFiles();
  const photoReadId = useRef(0);
  const profileTextRequestId = useRef(0);
  const savedValues = useRef<ProfileFormValues | null>(null);
  const photo = Form.useWatch("photo", form) ?? "";
  const sectionReorder = useProfileSectionReorder({ editing, saving, photoReading });
  const {
    sectionOrder,
    setSectionOrder,
    sectionReorderMode,
    setSectionReorderMode,
    dragOverSection,
    resetSectionReorder,
    handleSectionPointerDown,
    toggleSectionReorderMode,
    moveSectionByOffset,
  } = sectionReorder;

  useEffect(() => {
    let active = true;
    void getProfile()
      .then((profile) => {
        if (!active) return;
        const values = toFormValues(profile);
        form.setFieldsValue(values);
        setSectionOrder(normalizeSectionOrder(values.section_order));
        savedValues.current = values;
        setSectionReorderMode(false);
      })
      .catch((err) => {
        if (active) message.error(err instanceof Error ? err.message : "加载资料失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [form, message, setSectionOrder, setSectionReorderMode]);

  useEffect(
    () => () => {
      photoReadId.current += 1;
    },
    [],
  );

  const closeProfileTextModal = () => {
    profileTextRequestId.current += 1;
    setProfileTextParsing(false);
    setProfileTextUploadPercent(null);
    clearFiles();
    setProfileTextOpen(false);
  };

  /** 提交资料表单；返回是否真的保存成功（校验不过 / 请求失败都算没存上），
   * 供调用方决定"未保存更改"警示是否可以解除。 */
  const submit = async (): Promise<boolean> => {
    if (!editing || saving || photoReading) return false;
    let values: ProfileFormValues;
    try {
      const formValues = await form.validateFields();
      values = { ...formValues, section_order: sectionOrder } as ProfileFormValues;
    } catch (error) {
      // 校验不过时必须给出提示：以前这里静默 return，用户点「保存全部资料」看到的就是
      // "按钮点了没反应"——而真实原因是某个必填项还空着，红字提示可能在下方几屏之外。
      reportValidationFailure(form, message, error);
      return false;
    }
    setSaving(true);
    try {
      const profile = await saveProfile(values);
      const nextValues = toFormValues(profile);
      form.setFieldsValue(nextValues);
      savedValues.current = nextValues;
      resetSectionReorder(normalizeSectionOrder(nextValues.section_order));
      setEditing(false);
      message.success("资料已保存，现在可以去岗位广场生成简历了");
      return true;
    } catch (err) {
      message.error(err instanceof Error ? err.message : "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const cancelEditing = () => {
    if (saving || photoReading) return;
    if (savedValues.current) {
      form.resetFields();
      form.setFieldsValue(savedValues.current);
      resetSectionReorder(normalizeSectionOrder(savedValues.current.section_order));
    } else {
      resetSectionReorder();
    }
    closeProfileTextModal();
    setEditing(false);
  };

  const beforePhotoUpload: UploadProps["beforeUpload"] = (file) => {
    if (!editing) return Upload.LIST_IGNORE;
    if (!PHOTO_TYPES.has(file.type)) {
      message.error("请选择 JPG、PNG 或 WebP 格式的照片");
      return Upload.LIST_IGNORE;
    }
    if (file.size > PHOTO_MAX_BYTES) {
      message.error("照片不能超过 2 MB");
      return Upload.LIST_IGNORE;
    }
    const readId = ++photoReadId.current;
    setPhotoReading(true);
    void readAsDataUrl(file)
      .then((dataUrl) => {
        if (photoReadId.current === readId) form.setFieldValue("photo", dataUrl);
      })
      .catch((err) => {
        if (photoReadId.current === readId) {
          message.error(err instanceof Error ? err.message : "读取照片失败");
        }
      })
      .finally(() => {
        if (photoReadId.current === readId) setPhotoReading(false);
      });
    return false;
  };

  const parseProfile = async () => {
    const text = profileText.trim();
    if (!text && files.length === 0) {
      message.warning("请先粘贴个人资料，或添加截图、上传文档");
      return;
    }
    setProfileTextParsing(true);
    const requestId = ++profileTextRequestId.current;
    setProfileTextUploadPercent(0);
    try {
      const parsed = await parseProfileText(
        {
          text,
          images: attachmentInputs(files, "image"),
          documents: attachmentInputs(files, "document"),
        },
        (percent) => {
          if (requestId === profileTextRequestId.current) setProfileTextUploadPercent(percent);
        },
      );
      if (requestId !== profileTextRequestId.current) return;
      const { warnings, parse_engine: recognitionSource } = parsed;
      const currentValues = form.getFieldsValue(true) as Partial<ProfileFormValues>;
      const merged = mergeParsedProfileValues(currentValues as ProfileFormValues, parsed);
      form.setFieldsValue({ ...merged, section_order: sectionOrder });
      setProfileTextWarnings(warnings);
      setProfileTextRecognized(parsed.recognized_text ?? "");
      // 提示条会消失，但"是 AI 还是本地规则"要一直留在弹窗里。
      setProfileTextSource(recognitionSource);
      message.success(
        `${recognitionSource === "ai" ? "已使用 AI" : "已使用本地规则"}识别并填入资料，请核对后保存`,
      );
    } catch (err) {
      if (requestId !== profileTextRequestId.current) return;
      setProfileTextWarnings([]);
      setProfileTextRecognized("");
      setProfileTextSource(null);
      message.error(err instanceof Error ? err.message : "识别个人资料失败");
    } finally {
      if (requestId === profileTextRequestId.current) {
        setProfileTextParsing(false);
        setProfileTextUploadPercent(null);
      }
    }
  };

  const openProfileTextModal = () => {
    setProfileText("");
    setProfileTextWarnings([]);
    setProfileTextRecognized("");
    setProfileTextSource(null);
    clearFiles();
    setProfileTextOpen(true);
  };

  const handleProfileTextChange = (value: string) => {
    // 内容改了，上一次识别的来源与抄录都不再对应当前内容。
    setProfileText(value);
    setProfileTextWarnings([]);
    setProfileTextRecognized("");
    setProfileTextSource(null);
  };

  return {
    form,
    loading,
    saving,
    editing,
    setEditing,
    photoReading,
    sectionOrder,
    sectionReorderMode,
    dragOverSection,
    profileTextOpen,
    profileText,
    profileTextWarnings,
    profileTextParsing,
    profileTextUploadPercent,
    profileTextRecognized,
    profileTextSource,
    files,
    filesReading,
    addFiles,
    removeFile,
    onPasteFiles,
    photo,
    submit,
    cancelEditing,
    beforePhotoUpload,
    handleSectionPointerDown,
    toggleSectionReorderMode,
    moveSectionByOffset,
    openProfileTextModal,
    handleProfileTextChange,
    closeProfileTextModal,
    parseProfile,
  };
}
