# 采集 → 自动评分 → 人工确认导入（方案 3）

> 状态：**已实施**（2026-11-11）。本文件记录终态实现与实测结论，供后续维护者参考。
> 分支 `feat/gongzuotong`。参考实现 `D:\飞牛文件同步\工作\BossHunter`（只读，未复制其源码）。

---

## 1. 为什么做

用户原话：

> 我的意思是，采集评分后，我再决定导入，但是现在却是采集之后就停了

拆开看是三处断点，不是单个 bug：

1. **任务式采集只产内存预览、不落库。** `/api/job-hunt/collect/task`（界面「开始采集」
   走的就是它）入参只有 `site_key/keywords/city/max_pages/city_code`——没有
   `persist`/`analyze`/`backfill_jd`。结果放在 `CollectTask.stubs` 里。
2. **预览表渲染不出来。** `NativeJobHuntView` 的预览表 gate 在 `state.lastResult`，而
   那条路径从不写这个值——采完什么也不显示。
3. **评分接不上。** 评分端点第一行是 `db.get(Job, job_id)`；候选在确认导入前没有 Job 行。

对照 BossHunter：它**没有「导入」这一步**——采集直接 INSERT `jobs`（`status='pending'`），
自动评分后分 `ready`/`filtered`，人工只确认 `ready → approved`。方案 3 保留「导入」这个
动作（用户明确要「我决定才进岗位广场」），但把评分提前到导入之前。

---

## 2. 终态链路

```
① 采集（后台任务，可暂停/停止）
      ↓  结果写 candidate_job，status=pending
② 自动补 JD（backfill_candidate_jd，只补空，限速 1.5s）
      ↓  补不到的标 score_error='jd_missing: …'，不硬评
③ 自动评分（后台串行，复用 scoring.py）
      ↓  分数写 candidate_job 的五列
④ 用户在「AI 求职」页看到带分数的候选列表
      ↓  勾选 + 「导入到岗位广场」
⑤ import_candidates → 建 Job，分数迁到 job_match_analysis
```

人工只有**第 ④ 步**一个决策点。①②③⑤ 全自动。

---

## 3. 数据模型

`candidate_job` 新增 5 列（迁移 `0003_candidate_job_score`，`down_revision=0002`，
幂等、只加列、可回退）：

| 列 | 类型 | 语义 |
|---|---|---|
| `score_total` | `Integer NULL` | 0-100；**NULL = 还没评过**（不是 0 分） |
| `score_payload` | `JSON NULL` | 完整 `SemanticScore`；**不进列表**，只在详情给 |
| `score_model` | `String(64)` | 评分用的模型名 |
| `scored_at` | `DateTime NULL` | 评分时间 |
| `score_error` | `String(255)` | 失败原因；空串 = 无错 |

**为什么不新建表**：候选与评分 1:1，列表要按分数排序；而 `job_match_analysis.job_id` 是
unique + 外键到 job，候选没有 job 行、多条也无法并存。
**为什么不新增 status 取值**：`status` 只有 pending/imported，且被接口的 Literal 白名单
校验；用 `score_total IS NULL` 表达「评没评过」不占状态位，还能表达「评分失败」。

---

## 4. 关键实现与踩过的坑

### 4.1 评分编排必须在 service 层

原来「拼提示词 → 调模型 → 解析」写在 `api/job_hunt_score.py` 的路由函数里。候选评分要用
同一套，留在路由里就只能复制。抽出 `services/job_hunt/scoring_service.py`：

- `score_texts(db, *, title, company, city, salary, jd, resume_id)` —— **不依赖 Job 对象**；
- `persist_semantic_for_job(session, job_id, payload, model)` —— 供 API 与导入两处共用；
- 两类异常分开：`ScoringUnavailable`（环境问题，重试无用）/ `ScoringFailed`（这次失败，可重试）。

原端点改为调用它，现有测试未改一字仍全绿。

### 4.2 备选岗位的 JD 补抓**不能复用**正式岗位那套 ⚠️

这是实施中踩到的最深的坑。`detail_backfill.backfill_details` 是按 `Job` 模型读写的：
它 `db.get(Job, id)` 并判 `job.description` 非空则跳过。

拿**候选 id** 传进去时查不到 Job 行 → 每一条都被判成「已有 JD」**静默跳过**。
实测日志：

```
备选岗位补 JD：尝试 0 / 成功 0 / 跳过 11
```

紧接着 11 条评分全部变成「缺 JD」——整条链路的「补 JD」这一步等于空的，而且**不报错**。

解决：新增 `services/job_hunt/candidate_jd_backfill.py`，同一套适配器解析与限速，读写换
`CandidateJob`，判空复用 `candidate_scoring.candidate_has_jd`（与评分同源），详情页正文按
小标题切成职责/要求两列（与投递台采集落库口径一致）。

> 顺带：本模块在 `app/services/job_hunt/`，相对导入 `...` 会落到 `app.sites`（不存在）、
> `....` 又越出顶层包。最后用绝对导入 `app.services.sites.boss_text`。

### 4.3 一条缺 JD 不能让整批作废 ⚠️

`ScoringUnavailable` 混装两种语义：「整批环境坏了」（没配模型/资料为空）与「这一条缺
JD」。旧代码一律当环境错误整批收尾——实测 `requested=11 / failed=1`，其余 10 条一条没跑。

改成按**协议值前缀** `jd_missing` 分流：缺 JD 只跳过这一条（写 `score_error`），环境错误
才收尾。前端也按这个前缀判断，**不用中文串匹配**——靠 `includes("缺 JD")`，后端改一次文案
前端就静默失效。

### 4.4 语义评分与准入结论同表不同键，互相不能覆盖 ⚠️

两个独立缺陷，都修在这轮：

1. **`api/job_match.py` 的 500**：`JobMatchResult` 是 `extra="forbid"`，而 `result` 里可能
   只有 `semantic_score` 一个子键。旧代码直接 `model_validate` → ValidationError → 500。
   批量路径早有兜底，单岗没有。
2. **`services/apply/_match.py` 的整条覆盖**（更严重，写测试时才发现）：`persist_match`
   用 `row.result = payload` 覆盖整条。用户按分数挑完岗位、再跑一次「匹配度分析」，
   刚迁过去的语义评分就被抹掉了——正好把方案 3 的价值清空。
   改为保留 `semantic_score` 兄弟键（只保留这一个已知键，不做通用合并——`result` 是
   forbid 校验对象，留着历史键会连带报错）。

### 4.5 列表排序必须在服务端

候选表是客户端分页（20 条/页）。本地排序只能排当前页，用户按分数挑时看到的是「这一页里
最高的」而不是「所有候选里最高的」。`sort` 参数走服务端，按分数排时**未评分的固定排
最后**（两个方向都一样）——否则升序会把 NULL 当最小值挤到最前，看着像全是 0 分。

---

## 5. 前端

| 改动 | 文件 | 要点 |
|---|---|---|
| 删死预览表 | `ai-jobs/NativeJobHuntView.tsx` | gate 在 `state.lastResult`，任务式采集下恒 null |
| 挂候选面板 | 同上 | 复用 `apply/CollectResultPanel`（已有完整「表格+勾选+导入」） |
| 流程条真实计数 | 同上 | 不再用 `useState(0)` / 写死的 `scored: 0` |
| 自动评分开关 | 同上 | 默认开，透传 `persist`/`auto_score` |
| 候选 + 评分轮询 | `hooks/useCandidates.ts` | `score_started` 为真才开始轮询；任务收敛后重拉 |
| 分数格 | `jobs/candidate/CandidateScoreCell.tsx` | 只渲染不请求（逐行请求 = N+1） |
| 分数列 + 服务端排序 | `apply/CollectResultPanel.tsx` | ≥70 绿 / 40-69 蓝 / <40 琥珀 |

i18n 只改 `zh-CN.aiJobs.ts` + `en-US.aiJobs.ts`（已注册，不动 aggregator）。

---

## 6. 实测结论（真实采集 + 真实模型）

```
采集 12 条 → 落库（去重 9）→ 补 JD → 评分 46 分（deepseek-v4.1-flash）
→ 导入岗位 271 → job_match_analysis.result.semantic_score.total = 46
→ 对 271 点「匹配度分析」HTTP 200，且跑完后 semantic_score 与 hard_conditions 并存
```

补 JD 实测：`尝试 1 / 成功 1`，JD 413 字 + 要求 111 字，段落切分正确。

---

## 7. 已知缺口

| 项 | 说明 |
|---|---|
| `posted_at` 丢失 | 候选表无此列，导入后发布时间为空。与评分链路无关。 |
| `images` 不随导入迁移 | `import_candidates` 的 `JobCreate` 未带 `note_images`，截图只留在候选行。 |
| 评分串行、无并发 | 一次 15-18 条、每条 3-5 秒，合计约一分钟。并发能压到二十秒，但会让「卡在第几条」不可解释，且抢 LLM 配额。 |
| 评分任务不持久化 | 快照存 `app_setting` 单键，进程重启任务丢失（启动自检标 failed）。这类任务生命周期就几分钟，建表不值得。 |
| 低分不自动隐藏 | 只按分数排序，不隐藏。隐藏会让用户怀疑「采到的怎么少了」。要隐藏再加 `min_score` 参数。 |
| 评分失败仍可导入 | 评分是辅助决策，LLM 调用失败不该挡住导入；`score_error` 如实显示。 |

**存量失败（先于本功能，不归本功能负责）**：前端 4 个（demoBridge 白名单缺 `/ai-jobs`、
`resume-section-visibility` 零样式类名、`ai-jobs/*` 用 `Alert message=`、inlineColorGuard）；
后端若干（`job_hunt_score.py` detail 带「请」、`job_hunt_scoring.md` 未进 preflight 清单、
菜单缺「AI 求职」域、`JobsPage.tsx` 505 行等）。
