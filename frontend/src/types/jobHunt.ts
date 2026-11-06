// SPDX-License-Identifier: Apache-2.0
/**
 * 自研求职采集（/api/job-hunt）的类型。
 *
 * `job_hunt_backend` 是新旧后端的总开关：sidecar = 既有 HTTP 代理（默认），
 * native = 工作通自研采集（services/job_hunt）。新老并存，删旧要等 native 稳定。
 */

export type JobHuntBackend = "sidecar" | "native";

export interface JobHuntConfig {
  job_hunt_backend: JobHuntBackend;
}

export interface JobHuntPlatform {
  key: string;
  name: string;
}

export interface JobHuntStatus {
  backend: JobHuntBackend;
  platforms: JobHuntPlatform[];
}
