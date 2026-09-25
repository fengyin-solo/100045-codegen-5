"""雨天溢流与调蓄池监控接口。

看板、事件列表、调蓄池补录共用 OverflowService 同一份数据，
保证刷新后看板上的处置进度与事件列表完全一致。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.overflow import OverflowService

router = APIRouter(prefix="/api/overflow", tags=["雨天溢流监控"])

service = OverflowService()

LIST_FIELDS = ["事件编号", "站点", "溢流口", "发生时间", "溢流原因", "上报人", "处置人", "处置措施", "进度备注", "status"]
STATUSES = ["待处置", "处置中", "已处置"]
SORTS = ["site", "level"]


@router.get("/board")
def get_board(
    site: str | None = Query(default=None, description="按站点过滤"),
    sort: str = Query(default="site", description="site=按站点排列，level=按越限严重程度排列"),
) -> dict[str, Any]:
    """同一张看板：调蓄池液位分级 + 各站点事件处置进度，一屏取齐。"""
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail="排序方式只支持 site（按站点）或 level（按液位）")
    return service.board(site=site, sort=sort)


@router.get("/tanks")
def list_tanks(
    site: str | None = Query(default=None, description="按站点过滤"),
    sort: str = Query(default="site", description="site=按站点排列，level=按越限严重程度排列"),
) -> dict[str, Any]:
    """调蓄池液位列表：返回带分级与兜底提示的调蓄池数据。"""
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail="排序方式只支持 site（按站点）或 level（按液位）")
    items = service.list_tanks(site=site, sort=sort)
    return {"items": items, "total": len(items)}


@router.get("/events", response_model=PageResult[dict])
def list_events(
    site: str | None = Query(default=None, description="按站点过滤"),
    status: str | None = Query(default=None, description="待处置、处置中、已处置"),
    keyword: str | None = Query(default=None, description="按事件编号、溢流口或站点检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """事件列表口径与看板一致：没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_events(site=site, status=status, keyword=keyword, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/events", response_model=ActionResult)
def create_event(payload: EntryPayload) -> ActionResult:
    """登记雨天溢流事件；缺字段或重复上报都给出可读说明，不静默落库。"""
    entry, extra = service.create_event(payload.values)
    if entry is None:
        if isinstance(extra, list):
            return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(extra)}")
        return ActionResult(ok=False, message=extra)
    return ActionResult(ok=True, message="溢流事件已登记", entry=entry)


@router.post("/events/{event_id}/actions", response_model=ActionResult)
def run_event_action(event_id: int, payload: EntryPayload) -> ActionResult:
    """推进单条事件的处置进度（开始处置、更新进度、完成处置）。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(event_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/tanks/{tank_id}/report", response_model=ActionResult)
def report_tank_level(tank_id: int, payload: EntryPayload) -> ActionResult:
    """手动补录调蓄池液位：同池同采集时间的二次上报按重复上报兜底。"""
    level = payload.values.get("液位")
    collected_at = str(payload.values.get("采集时间") or "").strip() or None
    operator = str(payload.values.get("补录人") or "").strip() or None
    tank, message, duplicate = service.report_level(tank_id, level, collected_at, operator)
    if tank is None:
        return ActionResult(ok=False, message=message)
    result = ActionResult(ok=not duplicate, message=message, entry=tank)
    return result


@router.post("/tanks/{tank_id}/recollect", response_model=ActionResult)
def recollect_tank(tank_id: int) -> ActionResult:
    """对采集失败的调蓄池重新采集；正常或无数据状态下调用会被拦下并提示。"""
    tank, message = service.retry_collect(tank_id)
    if tank is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=tank)
