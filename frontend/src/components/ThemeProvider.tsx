// SPDX-License-Identifier: Apache-2.0
/**
 * 主题装配：把 antd 的 ThemeConfig 切换与 `<html data-theme>` 绑在一处。
 *
 * 为什么单独一个组件而不是写在 `main.tsx` 里：切主题必须触发重渲染，而 `main.tsx`
 * 只在启动时跑一次。`ConfigProvider` 的 `theme` 一变，antd 的整套 token 会重算；
 * 自定义 CSS 走 `[data-theme="dark"]`，两条线都由这里统一驱动。
 *
 * 浅色 / 深色是**两套独立的 ThemeConfig**（`appTheme` / `darkTheme`），不是
 * "一套 token + 算法开关"：antd 的 token 覆盖发生在算法之后，浅色 token 盖到
 * `darkAlgorithm` 上会得到深底 + 深字（2026-10 用户截图里的不可读界面）。
 *
 * **antd 的组件文案语言与界面语言同源**：antd 自带的分页「上一页」、日期选择器的月份名、
 * `Modal` 的按钮都来自它自己的语言包，与 `src/i18n` 的语言包是两套数据。所以这里不再
 * 直接 import `antd/locale/zh_CN`，而是取 `useLocale()` 再经 `antdLocale()` 映射——
 * 映射只留一处，切到 `en-US` 时分页与日期控件也会一起切换。
 */
import { App as AntdApp, ConfigProvider } from "antd";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { antdLocale } from "../i18n/antdLocale";
import { useLocale } from "../i18n/i18nContext";
import { appTheme } from "../theme/appTheme";
import { darkTheme } from "../theme/darkTheme";
import { MESSAGE_CONFIG } from "../theme/feedbackConfig";
import {
  applyTheme,
  hydrateThemeFromServer,
  useResolvedTheme,
  useThemeMode,
} from "../features/theme/themeStore";
import { usePrefersReducedMotion } from "../features/tou-tou/usePrefersReducedMotion";

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useThemeMode();
  // antd 的组件文案跟随当前界面语言。
  const locale = useLocale();

  useEffect(() => {
    // 首屏先从服务端取一次（跨数据集/换浏览器）；服务端无值时保留本地选择。
    void hydrateThemeFromServer();
  }, []);

  useEffect(() => {
    // 首屏与每次切换都把 data-theme 落到 <html>：避免"主题存了深色、页面却是浅色"。
    applyTheme(mode);
  }, [mode]);

  // 跟随系统时也要在系统切换的那一刻重画：useResolvedTheme 内部订阅了 matchMedia。
  const dark = useResolvedTheme() === "dark";
  // 系统「减少动画」时关闭 antd 的 motion（见下方 getPopupContainer 旁的说明）。
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <ConfigProvider
      locale={antdLocale(locale)}
      theme={
        prefersReducedMotion
          ? { ...(dark ? darkTheme : appTheme), token: { ...(dark ? darkTheme : appTheme).token, motion: false } }
          : dark
            ? darkTheme
            : appTheme
      }
      /*
       * 浮层统一挂到 body：简历预览里 `.resume-preview-pages` 用 transform 做缩放，
       * transform 会创建新的定位上下文——浮层若留在原地会被困在缩放容器里，
       * 表现为「点开下拉没有任何选项」。挂到 body 才能脱离该上下文。
       *
       * 动画必须跟随系统偏好关闭（motion: false）：`foundation.css` 在
       * prefers-reduced-motion 下把 animation-duration 压到 0.01ms，而 antd 的浮层
       * 靠 rc-motion 监听 animationend 推进状态机——动画在监听挂上之前就跑完，
       * 于是永远停在 `ant-slide-up-appear-prepare`（opacity: 0）。
       * 实测：系统开启「减少动画」后，版式/字段语言下拉创建了却始终不可见。
       * 关掉 motion 让 antd 走无动画路径，浮层直接以最终状态出现。
       */
      getPopupContainer={() => document.body}
    >
      <AntdApp message={MESSAGE_CONFIG}>{children}</AntdApp>
    </ConfigProvider>
  );
}
