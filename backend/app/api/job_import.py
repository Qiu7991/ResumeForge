"""按招聘网站链接导入岗位（岗位广场用）。

**为什么需要**：用户在 BOSS 直聘上看到心动的岗位，想让它在岗位广场里出现——这样能看 JD、
做匹配分析、生成岗位版简历、再加进投递台。缺的从来不是"复制 JD"，而是**这条岗位在站点上
的身份（URL）**：有了 URL，应用已经有一个登录着招聘网站的专用浏览器，标题/公司/JD 都能读回来，
而且落库后 `apply_supported` 自动为真（来源命中站点域名），可以直接自动化投递。

**边界**：只支持"站点适配器实现了 `fetch_job_detail`"的站点（当前是 BOSS 直聘）。不做通用
爬虫——不同站点结构差异巨大，硬套选择器只会得到一半字段的空壳岗位，不如明确报错。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.job import Job
from ..schemas.job import RECOGNITION_SOURCE_COLLECT, JobCreate, JobImportUrlIn, JobOut
from ..services import trash
from ..services.apply._site_browser import browser_status, get_browser_manager
from ..services.browser.browser_manager import BROWSER_STATE_RUNNING, BrowserError
from ..services.job.job_service import create_job_record
from ..services.job.job_type_infer import infer_job_type
from ..services.sites.base import SiteFailure
from ..services.sites.registry import get_registry

router = APIRouter(tags=["jobs"])
logger = logging.getLogger(__name__)


def _import_from_url(db: Session, url: str) -> Job:
    """按 URL 抓详情并落成岗位（两个入口共用）。"""

    try:
        adapter = get_registry().for_target(url)
    except SiteFailure as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fetch_detail = getattr(adapter, "fetch_job_detail", None)
    if fetch_detail is None:
        raise HTTPException(
            status_code=422, detail=f"{adapter.display_name}暂不支持按链接导入岗位"
        )

    existing = (
        db.query(Job).filter(Job.source_url == url).order_by(Job.id.desc()).first()
    )
    if existing is not None and not trash.is_deleted(existing):
        return JobOut.model_validate(existing)

    status = browser_status(db)
    if status.state != BROWSER_STATE_RUNNING:
        raise HTTPException(
            status_code=409,
            detail="请先在「投递台」启动专用浏览器并登录该招聘网站，再按链接导入",
        )

    manager = get_browser_manager(db)
    client = None
    try:
        client = manager.client()
        detail = fetch_detail(client, url) or {}
    except BrowserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SiteFailure as exc:
        raise HTTPException(status_code=502, detail=f"抓取岗位详情失败：{exc}") from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响已读到的结果
                logger.debug("关闭 CDP 客户端失败（可忽略）", exc_info=True)

    title = str(detail.get("job_title") or "").strip()
    if not title:
        raise HTTPException(
            status_code=502,
            detail="页面里没读到岗位名称：可能专用浏览器未登录该站点，或页面结构已变化",
        )

    job = create_job_record(
        db,
        JobCreate(
            title=title,
            company=str(detail.get("company") or "").strip(),
            location=str(detail.get("location") or "").strip(),
            salary=str(detail.get("salary") or "").strip(),
            description=str(detail.get("description") or "").strip(),
            requirements=str(detail.get("requirements") or "").strip(),
            additional_info=str(detail.get("additional_info") or "").strip(),
            # 类型按 JD 推断（大多数是社招；有应届/在校/实习字样才归校招/实习）。
            job_type=infer_job_type(
                title=title,
                description=str(detail.get("description") or ""),
                requirements=str(detail.get("requirements") or ""),
            ),
            source_url=url,
            # 录入方式是"采集"：与自动采集导入的岗位同一个口径，界面上的来源标签才一致。
            recognition_source=RECOGNITION_SOURCE_COLLECT,
        ),
        source=RECOGNITION_SOURCE_COLLECT,
    )
    logger.info("按链接导入岗位 id=%s url=%s", job.id, url)
    return job


@router.post("/import-url", response_model=JobOut)
def import_job_from_url(payload: JobImportUrlIn, db: Session = Depends(get_db)):
    """用专用浏览器打开岗位链接、抓取详情并落成岗位记录。

    同一链接重复导入时直接返回已有岗位（列表里不出现两条一模一样的岗位）。
    """
    return JobOut.model_validate(_import_from_url(db, payload.url.strip()))


@router.post("/import-current", response_model=JobOut)
def import_current_page(db: Session = Depends(get_db)):
    """导入专用浏览器里**当前打开的那个岗位详情页**，不要求用户复制链接。

    第一性上，"复制链接再粘贴"是多余的一步：浏览器本来就在应用手里，标签页的 URL 随时可读。
    所以这里直接问浏览器"你现在开着哪几个页面"，挑出岗位详情页那条再走同一条导入链路。
    """
    status = browser_status(db)
    if status.state != BROWSER_STATE_RUNNING:
        raise HTTPException(
            status_code=409,
            detail="请先在「投递台」启动专用浏览器并登录招聘网站，再导入当前页面",
        )

    manager = get_browser_manager(db)
    try:
        targets = manager.list_page_targets()
    except BrowserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # 优先"最近活跃"的标签：CDP 的目标列表按活跃度倒序，第一条详情页通常就是用户正在看的。
    detail_urls = [
        str(target.get("url") or "")
        for target in targets
        if "/job_detail/" in str(target.get("url") or "")
    ]
    if not detail_urls:
        raise HTTPException(
            status_code=409,
            detail="浏览器里没有打开的岗位详情页：先在窗口里点进某个岗位，再点一次导入",
        )

    return JobOut.model_validate(_import_from_url(db, detail_urls[0]))
