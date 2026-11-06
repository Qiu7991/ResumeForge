// SPDX-License-Identifier: Apache-2.0
/**
 * 生成偏好「显示项目技术栈」的取数与保存（与 `useWebFormRelaxedMode` 同一套写法）。
 *
 * 后端持久化在 `app_setting`（默认关）。这个开关描述的是"我的资料怎么被使用"，
 * 不是单次生成的版式，所以放设置页而不是生成弹窗。
 */
import { useCallback, useEffect, useState } from "react";
import { getGenerationPreferences, saveGenerationPreferences } from "../../api/settings";

export function useShowTechStack() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 纯取数（不含 setState）：effect 与事件路径共用同一实现，避免两份加载逻辑漂移。
  const fetchEnabled = useCallback(async (): Promise<boolean> => {
    try {
      return (await getGenerationPreferences()).show_tech_stack;
    } catch {
      // 读不到按默认关处理：老板的明确要求是"简历不要带技术栈"。
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetchEnabled().then((value) => {
      if (cancelled) return;
      setEnabled(value);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchEnabled]);

  const toggle = useCallback(
    async (checked: boolean): Promise<boolean> => {
      if (saving) return false;
      setSaving(true);
      setEnabled(checked);
      try {
        const saved = await saveGenerationPreferences({ show_tech_stack: checked });
        setEnabled(saved.show_tech_stack);
        return saved.show_tech_stack;
      } catch {
        // 保存失败回滚到切换前的状态。
        setEnabled(!checked);
        return false;
      } finally {
        setSaving(false);
      }
    },
    [saving],
  );

  return { enabled, loading, saving, toggle };
}
