/** 订阅通用 AI 任务登记表（`utils/aiTaskWatcher`）的 React 入口。 */
import { useSyncExternalStore } from "react";
import { getAiTasks, subscribeAiTasks, type AiTaskView } from "../utils/aiTaskWatcher";

export function useAiTasks(): AiTaskView[] {
  return useSyncExternalStore(subscribeAiTasks, getAiTasks, getAiTasks);
}
