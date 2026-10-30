# SPDX-License-Identifier: Apache-2.0
"""简历中心的「批量导出」：把多份简历打成一个 zip。

**为什么是 zip 而不是 N 个下载**：浏览器会拦截连续多次自动下载，而"批量"本来就该是
一个交付物。zip 里每份简历的文件名沿用单份导出的命名（标题 + 岗位），重名时追加序号。

**与上游的差异（合并时只看这一处）**：上游 10-28 的版本把格式/字号/页数/版式**只从
「设置 → 批量操作」读**，请求体只有 id；本仓库没有那套批量设置（`services/batch_operation`
与设置页的批量区都没移植），所以这里把「格式」放进请求体（默认 PDF），字号/页数/版式
沿用**每份简历自己记录**的值。等以后移植批量设置时，把 `payload.format` 换成
`read_batch_operation_config(db).export` 即可，其余逻辑（zip、去重、失败跳过、响应头）
与上游逐字一致。

单份失败（正文仍有 `【待补】` 标记、模板渲染失败等）不拖垮整批：跳过并在响应头里说明
跳过几份、第一份为什么被跳过；全部失败才返回 409。
"""

from __future__ import annotations

import logging
import os
import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Literal
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request as HTTPRequest
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.resume import ResumeRecord
from ...services import trash
from ...services.export_pipeline import ExportRequest
from .export_routes import _export_record, _require_local_export_request

logger = logging.getLogger(__name__)

router = APIRouter()

# 一次最多导出 50 份：服务端要逐份同步渲染 PDF，50 份已经是"几分钟"的量级；
# 再大应该分批来，而不是让一个请求挂着直到前端超时。
MAX_BATCH_EXPORT = 50

BatchExportFormat = Literal["pdf", "docx", "html", "txt", "md", "json"]

_DISPOSITION_STAR = re.compile(r"filename\*=UTF-8''([^;]+)", re.IGNORECASE)
_DISPOSITION_PLAIN = re.compile(r'filename="?([^";]+)"?', re.IGNORECASE)


class BatchExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_ids: list[int] = Field(min_length=1, max_length=MAX_BATCH_EXPORT)
    # 默认 PDF：批量导出的主场景是"投递用文件"，其余格式留给需要归档/二次编辑的人。
    format: BatchExportFormat = "pdf"
    # 与单份 POST /export 同一个闸门：默认拦下还带【待补】的草稿，避免把半成品投出去。
    allow_incomplete: bool = False


def _filename_from_headers(headers: dict[str, str], fallback: str) -> str:
    # Starlette 的 Headers 是大小写不敏感的；转成 dict 后键会变成小写，这里统一按小写取。
    disposition = next(
        (value for key, value in headers.items() if key.lower() == "content-disposition"), ""
    )
    starred = _DISPOSITION_STAR.search(disposition)
    if starred is not None:
        return unquote(starred.group(1)) or fallback
    plain = _DISPOSITION_PLAIN.search(disposition)
    return (plain.group(1) if plain else "") or fallback


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        return name
    stem, suffix = os.path.splitext(name)
    index = 2
    while f"{stem}-{index}{suffix}" in used:
        index += 1
    return f"{stem}-{index}{suffix}"


@router.post("/batch-export")
def batch_export_resumes(
    request: HTTPRequest,
    payload: BatchExportRequest,
    db: Session = Depends(get_db),
):
    """把选中的简历按同一格式导出为一个 zip。"""
    _require_local_export_request(request)
    resume_ids = list(dict.fromkeys(payload.resume_ids))
    rows = (
        db.query(ResumeRecord)
        .filter(trash.live_only(ResumeRecord), ResumeRecord.id.in_(resume_ids))
        .all()
    )
    found = {row.id: row for row in rows}
    missing = [resume_id for resume_id in resume_ids if resume_id not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"以下简历不存在或已在回收站：{'、'.join(map(str, missing))}",
        )

    archive_bytes = BytesIO()
    used: set[str] = set()
    exported = 0
    skipped: list[str] = []
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        for resume_id in resume_ids:
            record = found[resume_id]
            try:
                response = _export_record(
                    db,
                    record,
                    ExportRequest(format=payload.format),
                    allow_incomplete=payload.allow_incomplete,
                    # 批量导出是"一次交付"，不逐份往设置里的保存目录落副本（那会变成
                    # N 份重名文件）——zip 本身就是交付物。
                    save_copy=False,
                )
            except HTTPException as exc:
                skipped.append(f"《{record.title}》：{exc.detail}")
                continue
            except Exception:  # noqa: BLE001 - 单份失败不拖垮整批，原因记日志
                logger.exception("批量导出单份简历失败 resume_id=%s", resume_id)
                skipped.append(f"《{record.title}》：导出失败")
                continue
            filename = _unique_name(
                _filename_from_headers(dict(response.headers), f"resume-{resume_id}"),
                used,
            )
            used.add(filename)
            archive.writestr(filename, response.body)
            exported += 1

    if exported == 0:
        raise HTTPException(
            status_code=409,
            detail="没有可导出的简历：" + "；".join(skipped[:3]),
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    download_name = f"简历批量导出-{stamp}.zip"
    detail = "；".join(skipped[:5])
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name, safe='')}",
        "X-Batch-Exported": str(exported),
        "X-Batch-Skipped": str(len(skipped)),
        # 头里只能是 latin-1：中文原因做 URL 编码，前端解码后展示。
        "X-Batch-Skipped-Detail": quote(detail, safe=""),
    }
    return Response(archive_bytes.getvalue(), media_type="application/zip", headers=headers)


__all__ = ["MAX_BATCH_EXPORT", "BatchExportRequest", "router"]
