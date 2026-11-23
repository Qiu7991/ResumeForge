// SPDX-License-Identifier: Apache-2.0
/**
 * 设置域类型入口。
 * 2026-11-14 拆分：原文件贴 500 行预算，按域拆到相邻的 settings-*.ts 分片；
 * 这里保留同名 re-export，types/settings 与 types 的历史导入路径不变。
 */
export * from "./settings-llm";
export * from "./settings-datasets";
export * from "./settings-preferences";
export * from "./settings-updates";
export * from "./settings-backup";
export * from "./settings-models";
