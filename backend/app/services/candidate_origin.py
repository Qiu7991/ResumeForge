# SPDX-License-Identifier: Apache-2.0
"""备选岗位的「来历」判据：这条候选是采集来的，还是手动录入的。

## 为什么单独一个模块

这个判据有**两个消费点**（列表出口的 `collected_at`、导入岗位广场时的
`recognition_source`），而它们分属两个文件；写在 `candidate_jobs.py` 里会让那个文件
越过 500 行预算，写在 `candidate_jobs_read.py` 里又会让「写路径」依赖「读路径」。
判据本身是纯函数、无依赖，独立成模块最省事，也让两个消费点引用同一份实现。

## 为什么不能只看 ``collect_task_id``

``collect_task_id`` 的语义是 1.x 采集批次的 ``apply_task.id``（int，见模型注释），
而 2.0 的自研采集用的是**内存里的 UUID 任务号**，没有对应的 int 批次行——那条链路的
``_stage_results`` 只能传 ``task_id=None``。于是只看这一列的话，自研采集采回来的岗位
**全被当成手动添加**：候选表的「采集时间」整列显示「手动添加」，导入后
``recognition_source`` 也被记成「备选岗位导入」（2026-11-13 用户反馈的现象）。
"""

from __future__ import annotations

# 手动录入时 ``source`` 只可能是这几个固定值（见 ``CandidateJobCreate.source``）。
# 采集链路的 ``source`` 写的是**平台展示名**（`BOSS直聘` / `智联招聘` …），
# 两者取值空间不相交——这是判断"是不是采集来的"最可靠的依据。
MANUAL_CANDIDATE_SOURCES = frozenset(
    {"手动添加", "粘贴文本", "招聘截图", "招聘文档", "助手录入", "CSV 导入"}
)


def is_collected_candidate(source: str | None) -> bool:
    """这条候选是不是采集来的（而不是手动录入的）。

    判据：``source`` 非空且不是手动录入的那几个固定值。采集写的是平台名。

    空 ``source`` 不算——早期手动录入不填来源，那批老数据不能被当成采集
    （否则它们的「采集时间」会显示成录入时间，比显示"手动添加"更误导）。
    """
    cleaned = (source or "").strip()
    return bool(cleaned) and cleaned not in MANUAL_CANDIDATE_SOURCES


__all__ = ["MANUAL_CANDIDATE_SOURCES", "is_collected_candidate"]
