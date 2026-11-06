# SPDX-License-Identifier: Apache-2.0
"""采集断点游标的持久化：存 ``AppSetting`` KV（不新建表，避免迁移）。

游标按「站点 + 搜索条件的哈希」定位——同一批搜索条件中断后能续，条件变了就
另起一份（旧的留着不碍事，覆盖语义见 ``save_cursor``）。值里只有页码与 URL
集合，不含任何凭据。
"""

import json
import logging

from sqlalchemy.orm import Session

from ...models.setting import AppSetting
from .runner import HuntCursor

logger = logging.getLogger(__name__)

_KEY_PREFIX = "job_hunt_cur_"


def kv_key(site_key: str, criteria_hash: str) -> str:
    """KV 键：``job_hunt_cur_{site}_{hash}``（AppSetting.key 上限 64 字符）。"""
    return f"{_KEY_PREFIX}{site_key}_{criteria_hash}"


def load_cursor(db: Session, site_key: str, criteria_hash: str) -> HuntCursor | None:
    """读游标；缺失/损坏返回 None（损坏时顺手清掉，避免永久脏数据）。"""
    row = db.get(AppSetting, kv_key(site_key, criteria_hash))
    if row is None:
        return None
    try:
        cursor = HuntCursor.from_dict(json.loads(row.value))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        logger.warning("采集游标数据损坏，已丢弃（site=%s hash=%s）", site_key, criteria_hash)
        db.delete(row)
        db.commit()
        return None
    if cursor is None:
        return None
    if cursor.site_key != site_key or cursor.criteria_hash != criteria_hash:
        # 键值对不上（不该发生）：按无游标处理并清理。
        db.delete(row)
        db.commit()
        return None
    return cursor


def save_cursor(db: Session, cursor: HuntCursor) -> None:
    """保存游标（同键覆盖；site/hash 必须一致才允许落库）。"""
    if not cursor.site_key or not cursor.criteria_hash:
        raise ValueError("游标缺少 site_key / criteria_hash，拒绝保存")
    key = kv_key(cursor.site_key, cursor.criteria_hash)
    row = db.get(AppSetting, key)
    serialized = json.dumps(cursor.to_dict(), ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=key, value=serialized))
    else:
        row.value = serialized
    db.commit()


def clear_cursor(db: Session, site_key: str, criteria_hash: str) -> None:
    """清游标（一次采集完整跑完/用户重开时调用）。"""
    row = db.get(AppSetting, kv_key(site_key, criteria_hash))
    if row is not None:
        db.delete(row)
        db.commit()


__all__ = ["kv_key", "load_cursor", "save_cursor", "clear_cursor"]
