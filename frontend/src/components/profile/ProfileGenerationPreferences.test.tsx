// SPDX-License-Identifier: Apache-2.0
/** 资料页「生成偏好」：默认关；改动即保存。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { t } from "../../i18n";
import ProfileGenerationPreferences from "./ProfileGenerationPreferences";

const profileMocks = vi.hoisted(() => ({
  getGenerationPreferences: vi.fn(),
  saveGenerationPreferences: vi.fn(),
}));

vi.mock("../../api/profile", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/profile")>()),
  ...profileMocks,
}));

beforeEach(() => {
  profileMocks.getGenerationPreferences.mockReset();
  profileMocks.saveGenerationPreferences.mockReset();
  profileMocks.getGenerationPreferences.mockResolvedValue({ include_tech_stack: false });
  profileMocks.saveGenerationPreferences.mockImplementation(async (payload) => payload);
});

afterEach(cleanup);

describe("ProfileGenerationPreferences", () => {
  it("默认关闭，打开后立即保存", async () => {
    render(
      <AntdApp>
        <ProfileGenerationPreferences />
      </AntdApp>,
    );

    const toggle = await screen.findByRole("switch", {
      name: t("profileLibrary.generationPrefs.techStack"),
    });
    await waitFor(() => expect(toggle).not.toBeChecked());

    fireEvent.click(toggle);

    await waitFor(() =>
      expect(profileMocks.saveGenerationPreferences).toHaveBeenCalledWith({
        include_tech_stack: true,
      }),
    );
  });
});
