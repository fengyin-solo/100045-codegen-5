"""雨天溢流与调蓄池监控接口。

同一张看板同时呈现溢流事件登记/处置进度与调蓄池液位分级；
站点清单、事件动作与登记入口分别提供独立端点。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload
from app.services.overflow import OverflowService

router = APIRouter(prefix="/api/overflow", tags=["雨天溢流与调蓄池监控"])

service = OverflowService()


@router.get("/board")
def board(
    site: str | None = Query(default=None, description="按站点编号过滤"),
    sort: str = Query(default="site", description="site 按站点排列，severity 按越限严重程度排列"),
) -> dict[str, object]:
    """聚合看板：事件列表、处置进度统计、各站液位分级同源返回。

    没有液位数据、采集失败、重复上报均在站点卡片里给出兜底提示。
    """
    sort_mode = "severity" if sort == "severity" else "site"
    return service.board(site=site, sort=sort_mode)


@router.get("/sites")
def list_sites() -> dict[str, object]:
    """调蓄池站点清单：供看板筛选与事件登记下拉使用。"""
    return {"items": service.list_sites()}


@router.post("/events", response_model=ActionResult)
def create_event(payload: EntryPayload) -> ActionResult:
    """登记一条雨天溢流事件；缺字段、站点不存在或重复上报都会被拦下并说明原因。"""
    entry, message = service.create_event(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/events/{event_id}/actions", response_model=ActionResult)
def run_action(event_id: int, payload: EntryPayload) -> ActionResult:
    """对溢流事件执行开始处置、完成处置、关闭归档；状态不对的动作会被拦下。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(event_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
