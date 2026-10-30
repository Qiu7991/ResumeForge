/**
 * 设置页 API Key 的「替换」路径：编辑态空框直接输入、点眼睛看完还能接着改。
 *
 * 单独成文件而不是塞回 SettingsPage.test.tsx：那个文件已经贴着 500 行预算
 * （test_file_size_budget 会拦），而这块交互的 mock 脚手架与页面其余用例并不共享。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./SettingsPage";

const apiMocks = vi.hoisted(() => ({
  acknowledgeUpdateInstallResult: vi.fn(),
  getAssistantOrbSetting: vi.fn(),
  checkForUpdate: vi.fn(),
  checkLLMThinking: vi.fn(),
  activateDataset: vi.fn(),
  deleteDataset: vi.fn(),
  deleteLLMConfigRecord: vi.fn(),
  exportAllDatasets: vi.fn(),
  exportDataset: vi.fn(),
  getLLMConfig: vi.fn(),
  getLLMSessionKeyStatus: vi.fn(),
  clearLLMSessionKey: vi.fn(),
  setLLMSessionKey: vi.fn(),
  getNavigationVisibility: vi.fn(),
  getReminderPopupSetting: vi.fn(),
  getSearchConfig: vi.fn(),
  getUpdateDownloadStatus: vi.fn(),
  getUpdateInstallResult: vi.fn(),
  installDownloadedUpdate: vi.fn(),
  importDataset: vi.fn(),
  listDatasets: vi.fn(),
  listLLMConfigRecords: vi.fn(),
  renameDataset: vi.fn(),
  revealLLMApiKey: vi.fn(),
  saveLLMConfig: vi.fn(),
  saveLLMConfigRecord: vi.fn(),
  saveAssistantOrbSetting: vi.fn(),
  saveReminderPopupSetting: vi.fn(),
  saveSearchConfig: vi.fn(),
  startUpdateDownload: vi.fn(),
  testLLM: vi.fn(),
}));

vi.mock("../api/settings", () => apiMocks);

const skillMocks = vi.hoisted(() => ({
  deleteSkill: vi.fn(),
  importSkill: vi.fn(),
  listSkills: vi.fn(),
  setSkillEnabled: vi.fn(),
}));

vi.mock("../api/skill", () => skillMocks);

const navigationMocks = vi.hoisted(() => ({ reloadPage: vi.fn() }));

vi.mock("../utils/navigation", () => navigationMocks);

const mainDataset = {
  id: "main",
  name: "主数据",
  source: "本机",
  size_bytes: 4_947_968,
  created_at: null,
  is_active: true,
  exists: true,
};

const llmConfig = {
  provider: "openai",
  base_url: "https://api.openai.com/v1",
  api_key: "********",
  model: "gpt-4o-mini",
  temperature: 0.1,
  timeout_seconds: 120,
  max_tokens: 4096,
};

const searchConfig = {
  sources: ["bing", "duckduckgo"],
  searxng_url: "",
  fetch_pages: 0,
  max_results: 8,
};

beforeEach(() => {
  apiMocks.getLLMConfig.mockResolvedValue(llmConfig);
  apiMocks.getLLMSessionKeyStatus.mockResolvedValue({ configured: false });
  apiMocks.getNavigationVisibility.mockResolvedValue({ hidden: [] });
  apiMocks.getAssistantOrbSetting.mockResolvedValue({ enabled: true, tips_enabled: true });
  apiMocks.getReminderPopupSetting.mockResolvedValue({ enabled: true });
  apiMocks.getSearchConfig.mockResolvedValue(searchConfig);
  apiMocks.getUpdateDownloadStatus.mockResolvedValue({
    state: "idle",
    current_version: "0.11.0",
    target_version: "",
    progress: 0,
    downloaded_bytes: 0,
    total_bytes: null,
    background: false,
    installable: false,
    message: "",
  });
  apiMocks.getUpdateInstallResult.mockResolvedValue(null);
  apiMocks.acknowledgeUpdateInstallResult.mockResolvedValue(undefined);
  apiMocks.checkLLMThinking.mockResolvedValue({
    style: "reasoning_effort",
    efforts: ["minimal", "low", "medium", "high"],
    supported: true,
    note: "内置表给的说明",
    probed: false,
    accepted: null,
    reasoning_seen: false,
    message: "",
  });
  apiMocks.listLLMConfigRecords.mockResolvedValue([]);
  apiMocks.saveAssistantOrbSetting.mockImplementation(async (setting) => setting);
  apiMocks.listDatasets.mockResolvedValue([mainDataset]);
  apiMocks.revealLLMApiKey.mockResolvedValue({ api_key: "sk-revealed" });
  skillMocks.listSkills.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderSettings() {
  render(
    <AntdApp>
      <SettingsPage />
    </AntdApp>,
  );
}

function passwordToggle(): HTMLElement {
  const input = screen.getByLabelText("API Key（选填）");
  const toggle = input
    .closest(".ant-input-affix-wrapper")
    ?.querySelector<HTMLElement>(".ant-input-password-icon");
  if (!toggle) throw new Error("未找到 API Key 显示按钮");
  return toggle;
}

describe("SettingsPage API Key 替换路径", () => {
  it("编辑态用空框输入新密钥，不会追加到掩码后面", async () => {
    apiMocks.getLLMConfig.mockResolvedValue({ ...llmConfig, api_key: "********" });
    apiMocks.saveLLMConfig.mockImplementation(async (config) => config);

    renderSettings();
    const input = await screen.findByLabelText("API Key（选填）");
    await waitFor(() => expect(input).toHaveValue("********"));

    fireEvent.click(screen.getByRole("button", { name: /编辑设置/ }));
    // 编辑态不再把掩码当成可编辑文本：空框 + 说明，用户不会把新密钥打在星号后面，
    // 保存时表单里仍是掩码，后端按占位符保留原密钥。
    await waitFor(() => expect(input).toHaveValue(""));
    expect(input).toHaveProperty("readOnly", false);

    fireEvent.change(input, { target: { value: "sk-brand-new" } });
    expect(input).toHaveValue("sk-brand-new");

    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));
    await waitFor(() =>
      expect(apiMocks.saveLLMConfig).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: "sk-brand-new" }),
      ),
    );
  });

  it("显示出来的密钥仍可编辑，不再一显示就锁死", async () => {
    apiMocks.getLLMConfig.mockResolvedValue({ ...llmConfig, api_key: "********" });
    apiMocks.saveLLMConfig.mockImplementation(async (config) => config);

    renderSettings();
    const input = await screen.findByLabelText("API Key（选填）");
    await waitFor(() => expect(input).toHaveValue("********"));

    fireEvent.click(screen.getByRole("button", { name: /编辑设置/ }));
    fireEvent.click(passwordToggle());
    await waitFor(() => expect(input).toHaveValue("sk-revealed"));
    // 以前显示明文密钥后输入框变 readOnly，用户以为"点不动"；现在看完可以接着改。
    expect(input).toHaveProperty("readOnly", false);

    fireEvent.change(input, { target: { value: "sk-edited" } });
    expect(input).toHaveValue("sk-edited");
  });
});
