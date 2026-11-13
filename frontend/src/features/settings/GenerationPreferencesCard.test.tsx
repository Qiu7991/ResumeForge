// SPDX-License-Identifier: Apache-2.0
/**
 * 设置页「生成偏好 · 简历内容」卡：简历是否显示项目技术栈。
 *
 * 默认关是老板的明确要求（"生成的简历里面不要带技术栈"），所以这里守两条：
 * 1. 后端返回 false 时开关是关的（不出现"默认就开着"的意外）；
 * 2. 拨动开关时发给后端的字段名是 `show_tech_stack`——名字对不上就是静默不生效。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import settingsUiZh from "../../i18n/messages/zh-CN.settingsUi";
import GenerationPreferencesCard from "./GenerationPreferencesCard";

const apiMocks = vi.hoisted(() => ({
  getGenerationPreferences: vi.fn(),
  saveGenerationPreferences: vi.fn(),
}));

vi.mock("../../api/settings", () => apiMocks);

afterEach(() => cleanup());

beforeEach(() => {
  apiMocks.getGenerationPreferences.mockResolvedValue({ show_tech_stack: false });
  apiMocks.saveGenerationPreferences.mockImplementation(
    async (preferences: { show_tech_stack: boolean }) => preferences,
  );
});

function renderCard() {
  return render(
    <AntdApp>
      <GenerationPreferencesCard />
    </AntdApp>,
  );
}

describe("GenerationPreferencesCard", () => {
  it("默认关闭：读到 false 时开关是关的，并说明关闭不删数据", async () => {
    renderCard();
    await waitFor(() => expect(apiMocks.getGenerationPreferences).toHaveBeenCalledTimes(1));

    const toggle = await screen.findByRole("switch", {
      name: settingsUiZh["settingsUi.generationPrefs.toggleAria"],
    });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(settingsUiZh["settingsUi.generationPrefs.hint"])).toBeInTheDocument();
  });

  it("拨动后按 show_tech_stack 字段保存", async () => {
    renderCard();
    const toggle = await screen.findByRole("switch", {
      name: settingsUiZh["settingsUi.generationPrefs.toggleAria"],
    });

    fireEvent.click(toggle);

    await waitFor(() =>
      expect(apiMocks.saveGenerationPreferences).toHaveBeenCalledWith({ show_tech_stack: true }),
    );
  });
});
