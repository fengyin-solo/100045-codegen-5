"""雨天溢流与调蓄池监控业务规则。

看板（看板事件处置进度 + 调蓄池液位分级）与事件列表共用同一份内存数据，
任何处置动作落库后，两个入口再刷新时取到的状态必然一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

EVENT_MODULE = "overflow"
TANK_MODULE = "retention"

REQUIRED_EVENT_FIELDS = ["站点", "溢流口", "发生时间"]
STATUS_ORDER = ["待处置", "处置中", "已处置"]
ACTION_RULES = {
    "开始处置": "处置中",
    "更新进度": "处置中",
    "完成处置": "已处置",
}
EVENT_PREFIX = "OVER"

# 液位分级标签与看板提示语都统一收在这里，避免前端各写一套口径。
GRADE_DANGER = "超限"
GRADE_WARN = "警戒"
GRADE_NORMAL = "正常"
GRADE_FAILED = "采集失败"
GRADE_EMPTY = "无数据"
GRADE_ORDER = [GRADE_DANGER, GRADE_WARN, GRADE_FAILED, GRADE_EMPTY, GRADE_NORMAL]
GRADE_HINTS = {
    GRADE_DANGER: "液位超过超限阈值，立即执行溢流应急调度",
    GRADE_WARN: "液位超过警戒阈值，加密观测并预启抽排",
    GRADE_FAILED: "液位采集失败，先到现场确认再补录数据",
    GRADE_EMPTY: "暂无液位数据，巡检确认后手动补录",
    GRADE_NORMAL: "液位在阈值范围内，保持常规监测",
}
# 组内排列优先级：越限等级越高的调蓄池排得越靠前，无数据/采集失败也要优先暴露
GRADE_SEVERITY = {
    GRADE_DANGER: 0,
    GRADE_FAILED: 1,
    GRADE_EMPTY: 2,
    GRADE_WARN: 3,
    GRADE_NORMAL: 4,
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _to_float(value: Any) -> float | None:
    """把上报值转成数值；空串、非数字都视为没有可用液位。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def classify_tank(tank: dict[str, Any]) -> str:
    """按「采集失败 → 没有数据 → 阈值分级」的顺序判定调蓄池等级。"""
    if str(tank.get("采集状态") or "") == "失败":
        return GRADE_FAILED
    level = _to_float(tank.get("液位"))
    if level is None:
        return GRADE_EMPTY
    danger = _to_float(tank.get("超限液位"))
    warn = _to_float(tank.get("警戒液位"))
    if danger is not None and level >= danger:
        return GRADE_DANGER
    if warn is not None and level >= warn:
        return GRADE_WARN
    return GRADE_NORMAL


def tank_view(tank: dict[str, Any]) -> dict[str, Any]:
    """给调蓄池补上分级、占比与提示语，看板和列表都用同一份口径。"""
    grade = classify_tank(tank)
    level = _to_float(tank.get("液位"))
    danger = _to_float(tank.get("超限液位"))
    percent: float | None = None
    if level is not None and danger:
        percent = round(min(level / danger, 1.2) * 100, 1)
    hint = GRADE_HINTS[grade]
    if tank.get("重复上报"):
        hint = f"检测到重复上报（{tank.get('采集时间', '')}），已保留首次记录：{hint}"
    view = dict(tank)
    view.update(
        液位等级=grade,
        等级提示=hint,
        液位百分比=percent,
        越限=grade in (GRADE_DANGER, GRADE_WARN),
    )
    return view


def _sync_flags(row: dict[str, Any], module: str) -> None:
    """让 pending/abnormal 始终跟随业务状态，概览卡片不用改口径。"""
    if module == EVENT_MODULE:
        row["pending"] = row.get("status") != STATUS_ORDER[-1]
        row["abnormal"] = row.get("status") != STATUS_ORDER[-1]
    else:
        grade = classify_tank(row)
        row["abnormal"] = grade in (GRADE_DANGER, GRADE_WARN, GRADE_FAILED, GRADE_EMPTY)
        row["pending"] = grade != GRADE_NORMAL


class OverflowService:
    # ---------------------------------------------------------------- 事件列表
    def list_events(
        self,
        *,
        site: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(EVENT_MODULE)
        if site:
            rows = [row for row in rows if row.get("站点") == site]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("事件编号", ""))
                or keyword in str(row.get("溢流口", ""))
                or keyword in str(row.get("站点", ""))
            ]
        # 列表与看板默认按站点排列；排序稳定，先按发生时间倒序，再按站点正序，
        # 同站点内新事件排在前面。
        rows.sort(key=lambda r: str(r.get("发生时间", "")), reverse=True)
        rows.sort(key=lambda r: str(r.get("站点", "")))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        return store.find(EVENT_MODULE, event_id)

    # ---------------------------------------------------------------- 事件登记
    def create_event(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str] | str]:
        missing = [
            field for field in REQUIRED_EVENT_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing
        site = str(values.get("站点")).strip()
        outlet = str(values.get("溢流口")).strip()
        occurred_at = str(values.get("发生时间")).strip()
        # 重复上报兜底：同站点 + 同溢流口 + 同发生时间视为同一事件
        for row in store.rows(EVENT_MODULE):
            if (
                str(row.get("站点", "")).strip() == site
                and str(row.get("溢流口", "")).strip() == outlet
                and str(row.get("发生时间", "")).strip() == occurred_at
            ):
                return None, f"该溢流事件已登记（编号 {row.get('事件编号')}），请勿重复上报"
        rows = store.rows(EVENT_MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["事件编号"] = f"{EVENT_PREFIX}-{entry['id']:04d}"
        entry["站点"] = site
        entry["溢流口"] = outlet
        entry["发生时间"] = occurred_at
        entry["溢流原因"] = str(values.get("溢流原因") or "").strip()
        entry["上报人"] = str(values.get("上报人") or "值班员").strip()
        entry["处置人"] = ""
        entry["处置措施"] = ""
        entry["进度备注"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["登记时间"] = _now()
        entry["更新时间"] = entry["登记时间"]
        _sync_flags(entry, EVENT_MODULE)
        rows.append(entry)
        return entry, []

    # ---------------------------------------------------------------- 处置进度
    def run_action(self, event_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(EVENT_MODULE, event_id)
        if entry is None:
            return None, f"溢流事件 {event_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于雨天溢流可执行范围"
        target = ACTION_RULES[action]
        values = values or {}

        if action == "开始处置":
            if entry["status"] != "待处置":
                return None, f"事件 {entry.get('事件编号')} 当前为{entry['status']}，无需重复开始处置"
            operator = str(values.get("处置人") or "").strip()
            if not operator:
                return None, "开始处置前请填写处置人"
            entry["处置人"] = operator
            entry["进度备注"] = str(values.get("进度备注") or "已到场，开始应急处置").strip()
        elif action == "更新进度":
            if entry["status"] == "已处置":
                return None, f"事件 {entry.get('事件编号')} 已处置完成，不能再更新进度"
            note = str(values.get("进度备注") or "").strip()
            if not note:
                return None, "更新进度时请填写进度备注"
            entry["进度备注"] = note
            if str(values.get("处置人") or "").strip():
                entry["处置人"] = str(values["处置人"]).strip()
        else:  # 完成处置
            if entry["status"] == "已处置":
                return None, f"事件 {entry.get('事件编号')} 已处置完成，请勿重复操作"
            measure = str(values.get("处置措施") or "").strip()
            if not measure:
                return None, "完成处置前请填写处置措施"
            entry["处置措施"] = measure
            if str(values.get("处置人") or "").strip():
                entry["处置人"] = str(values["处置人"]).strip()
            entry["进度备注"] = str(values.get("进度备注") or "处置完成，现场恢复正常").strip()

        entry["status"] = target
        entry["更新时间"] = _now()
        _sync_flags(entry, EVENT_MODULE)
        return entry, f"溢流事件已{action}"

    # ---------------------------------------------------------------- 调蓄池
    def list_tanks(self, *, site: str | None = None, sort: str = "site") -> list[dict[str, Any]]:
        rows = [tank_view(dict(row)) for row in store.rows(TANK_MODULE)]
        if site:
            rows = [row for row in rows if row.get("站点") == site]
        if sort == "level":
            rows.sort(key=lambda r: (GRADE_SEVERITY[r["液位等级"]], -(r.get("液位百分比") or 0)))
        else:
            rows.sort(key=lambda r: (str(r.get("站点", "")), GRADE_SEVERITY[r["液位等级"]]))
        return rows

    def report_level(
        self, tank_id: int, level: Any, collected_at: str | None, operator: str | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """手动补录液位。

        返回值第三项表示是否为重复上报：同池、同采集时间只保留第一次的记录。
        """
        tank = store.find(TANK_MODULE, tank_id)
        if tank is None:
            return None, f"调蓄池 {tank_id} 不存在", False
        value = _to_float(level)
        if value is None:
            return None, "补录液位必须是数字，本次上报未登记", False
        if value < 0:
            return None, "补录液位不能为负数，本次上报未登记", False
        stamp = (collected_at or _now()).strip()
        if str(tank.get("采集时间") or "") == stamp and str(tank.get("采集状态") or "") == "正常":
            tank["重复上报"] = True
            return tank_view(tank), f"调蓄池 {tank.get('调蓄池编号')} 在 {stamp} 已上报过液位，请勿重复上报", True
        # 补录前把上一笔正常读数留档，看板可以提示最近一次成功采集
        if tank.get("采集状态") == "正常" and _to_float(tank.get("液位")) is not None:
            tank["上次液位"] = tank.get("液位")
            tank["上次采集时间"] = tank.get("采集时间")
        tank["液位"] = value
        tank["采集时间"] = stamp
        tank["采集状态"] = "正常"
        tank["重复上报"] = False
        _sync_flags(tank, TANK_MODULE)
        who = f"（补录人：{operator}）" if operator else ""
        return tank_view(tank), f"调蓄池 {tank.get('调蓄池编号')} 液位已补录为 {value:g} m{who}", False

    def retry_collect(self, tank_id: int) -> tuple[dict[str, Any] | None, str]:
        """对采集失败/无数据的调蓄池重新采集，模拟一次现场恢复后的读数。"""
        tank = store.find(TANK_MODULE, tank_id)
        if tank is None:
            return None, f"调蓄池 {tank_id} 不存在"
        if tank.get("采集状态") != "失败":
            grade = classify_tank(tank)
            if grade == GRADE_EMPTY:
                return None, f"调蓄池 {tank.get('调蓄池编号')} 暂无液位数据，请使用手动补录"
            return None, f"调蓄池 {tank.get('调蓄池编号')} 当前采集正常，无需重试"
        # 演示环境用确定性的恢复读数：优先沿用最近一次成功采集值，没有时回到警戒液位附近
        last = _to_float(tank.get("上次液位"))
        warn = _to_float(tank.get("警戒液位"))
        restored = last if last is not None else round((warn or 5.0) - 0.3, 2)
        tank["液位"] = restored
        tank["采集时间"] = _now()
        tank["采集状态"] = "正常"
        tank["重复上报"] = False
        _sync_flags(tank, TANK_MODULE)
        return tank_view(tank), f"调蓄池 {tank.get('调蓄池编号')} 重新采集成功，当前液位 {restored:g} m"

    # ---------------------------------------------------------------- 同一张看板
    def board(self, *, site: str | None = None, sort: str = "site") -> dict[str, Any]:
        events = store.rows(EVENT_MODULE)
        if site:
            events = [row for row in events if row.get("站点") == site]
        tanks = self.list_tanks(site=site, sort=sort)

        sites = sorted({str(row.get("站点", "")) for row in store.rows(TANK_MODULE)}
                       | {str(row.get("站点", "")) for row in store.rows(EVENT_MODULE)})
        groups: list[dict[str, Any]] = []
        for name in sites:
            site_tanks = [tank for tank in tanks if tank.get("站点") == name]
            site_events = [row for row in events if row.get("站点") == name]
            if not site_tanks and not site_events:
                continue
            grade_counts = {grade: 0 for grade in GRADE_ORDER}
            for tank in site_tanks:
                grade_counts[tank["液位等级"]] += 1
            groups.append({
                "站点": name,
                "调蓄池数": len(site_tanks),
                "液位分级": grade_counts,
                "事件待处置": sum(1 for row in site_events if row.get("status") == "待处置"),
                "事件处置中": sum(1 for row in site_events if row.get("status") == "处置中"),
                "事件已处置": sum(1 for row in site_events if row.get("status") == "已处置"),
                "tanks": site_tanks,
            })

        grade_total = {grade: sum(1 for tank in tanks if tank["液位等级"] == grade) for grade in GRADE_ORDER}
        stats = [
            {"label": "溢流事件", "value": len(events)},
            {"label": "待处置", "value": sum(1 for row in events if row.get("status") == "待处置")},
            {"label": "处置中", "value": sum(1 for row in events if row.get("status") == "处置中")},
            {"label": "调蓄池", "value": len(tanks)},
            {"label": "液位超限", "value": grade_total[GRADE_DANGER]},
            {"label": "液位警戒", "value": grade_total[GRADE_WARN]},
            {"label": "采集异常", "value": grade_total[GRADE_FAILED] + grade_total[GRADE_EMPTY]},
        ]
        return {
            "stats": stats,
            "sites": sites,
            "groups": groups,
            "tanks": tanks,
            "gradeOrder": GRADE_ORDER,
        }
