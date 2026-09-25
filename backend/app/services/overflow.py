"""雨天溢流与调蓄池监控业务规则。

本模块独立维护站点配置、液位上报与溢流事件三类数据，不接入通用 SEED_ROWS，
因此看板统计不会串入运营概览，也不影响进水监测等既有模块的统计口径。

看板上的事件处置进度与事件列表永远来自同一份事件数据（board 一次聚合输出），
刷新后不会出现进度数字与列表状态不一致的问题。
"""
from __future__ import annotations

from datetime import date
from typing import Any

# 溢流事件状态流转：待处置 → 处置中 → 已处置 → 已关闭
EVENT_STATUS = ["待处置", "处置中", "已处置", "已关闭"]
EVENT_PROGRESS = {"待处置": 0, "处置中": 50, "已处置": 100, "已关闭": 100}
ACTION_RULES = {"开始处置": "处置中", "完成处置": "已处置", "关闭归档": "已关闭"}
ALLOWED_ACTIONS: dict[str, list[str]] = {
    "待处置": ["开始处置"],
    "处置中": ["完成处置"],
    "已处置": ["关闭归档"],
    "已关闭": [],
}
REQUIRED_FIELDS = ["站点编号", "溢流点位", "发生时间", "上报人"]

# 液位数据状态：ok 正常取到；failed 最新一条采集失败；no_data 该站从无上报
DATA_OK = "ok"
DATA_FAILED = "failed"
DATA_NO_DATA = "no_data"

# 液位越限分级：normal 正常、warning 预警、alarm 报警
LEVEL_NORMAL = "normal"
LEVEL_WARNING = "warning"
LEVEL_ALARM = "alarm"

# 看板按越限严重程度排列时的先后：报警 > 预警 > 采集失败 > 无数据 > 正常
SEVERITY_ORDER = {
    LEVEL_ALARM: 0,
    LEVEL_WARNING: 1,
    DATA_FAILED: 2,
    DATA_NO_DATA: 3,
    LEVEL_NORMAL: 4,
}

# 调蓄池站点配置：各站预警、报警液位阈值（单位 m）
SITE_CONFIG: list[dict[str, Any]] = [
    {"站点编号": "TANK-01", "站点名称": "东区调蓄池", "预警液位": 4.0, "报警液位": 5.0, "设计容积": "8000m³"},
    {"站点编号": "TANK-02", "站点名称": "西区调蓄池", "预警液位": 4.0, "报警液位": 5.0, "设计容积": "6500m³"},
    {"站点编号": "TANK-03", "站点名称": "南区调蓄池", "预警液位": 3.5, "报警液位": 4.5, "设计容积": "5200m³"},
    {"站点编号": "TANK-04", "站点名称": "北区调蓄池", "预警液位": 4.0, "报警液位": 5.0, "设计容积": "7000m³"},
    {"站点编号": "TANK-05", "站点名称": "中心调蓄池", "预警液位": 4.2, "报警液位": 5.2, "设计容积": "9000m³"},
]


def _seed_levels() -> list[dict[str, Any]]:
    """液位上报样例：液位为 None 表示采集失败；覆盖正常、预警、报警、失败、无数据、重复上报。"""
    return [
        # TANK-01：09:00 有两条重复上报，按最新一条（id 最大）展示
        {"id": 1, "站点编号": "TANK-01", "上报时间": "2026-09-25 08:00", "液位": 2.8},
        {"id": 2, "站点编号": "TANK-01", "上报时间": "2026-09-25 09:00", "液位": 3.1},
        {"id": 3, "站点编号": "TANK-01", "上报时间": "2026-09-25 09:00", "液位": 3.1},
        # TANK-02：最新液位落在预警区间
        {"id": 4, "站点编号": "TANK-02", "上报时间": "2026-09-25 08:05", "液位": 3.8},
        {"id": 5, "站点编号": "TANK-02", "上报时间": "2026-09-25 09:05", "液位": 4.6},
        # TANK-03：最新液位达到报警阈值
        {"id": 6, "站点编号": "TANK-03", "上报时间": "2026-09-25 08:10", "液位": 4.2},
        {"id": 7, "站点编号": "TANK-03", "上报时间": "2026-09-25 09:10", "液位": 4.8},
        # TANK-04：最新一条采集失败，需要回退展示最近一次有效液位
        {"id": 8, "站点编号": "TANK-04", "上报时间": "2026-09-25 08:00", "液位": 2.9},
        {"id": 9, "站点编号": "TANK-04", "上报时间": "2026-09-25 09:00", "液位": None},
        # TANK-05：没有任何上报，看板给“暂无液位数据”兜底
    ]


def _seed_events() -> list[dict[str, Any]]:
    """雨天溢流事件样例：覆盖待处置、处置中、已处置、已关闭四种进度。"""
    rows = [
        {"id": 1, "事件编号": "OVF-20260925-001", "站点编号": "TANK-02", "溢流点位": "2#溢流口",
         "发生时间": "2026-09-25 06:20", "溢流量": "约120m³", "上报人": "王建国",
         "事件描述": "强降雨期间西区调蓄池超高，2#溢流口短时溢入河道。", "status": "已处置"},
        {"id": 2, "事件编号": "OVF-20260925-002", "站点编号": "TANK-03", "溢流点位": "南区进厂主干管",
         "发生时间": "2026-09-25 07:05", "溢流量": "约80m³", "上报人": "李海燕",
         "事件描述": "进厂水量超抽排能力，南区主干管出现冒溢，已加开移动泵车。", "status": "处置中"},
        {"id": 3, "事件编号": "OVF-20260925-003", "站点编号": "TANK-01", "溢流点位": "1#溢流口",
         "发生时间": "2026-09-25 08:40", "溢流量": "约40m³", "上报人": "赵志强",
         "事件描述": "东区液位快速上涨，1#溢流口有溢流迹象，待现场核实处置。", "status": "待处置"},
        {"id": 4, "事件编号": "OVF-20260924-011", "站点编号": "TANK-02", "溢流点位": "1#溢流口",
         "发生时间": "2026-09-24 22:15", "溢流量": "约60m³", "上报人": "王建国",
         "事件描述": "夜间阵雨导致的短时溢流，处置完成后已归档。", "status": "已关闭"},
    ]
    for row in rows:
        row["progress"] = EVENT_PROGRESS[row["status"]]
    return rows


class OverflowService:
    """雨天溢流事件登记/处置流转 + 调蓄池液位分级看板。"""

    def __init__(self) -> None:
        self._sites = [dict(site) for site in SITE_CONFIG]
        self._levels = _seed_levels()
        self._events = _seed_events()

    # ---- 站点与液位 -------------------------------------------------

    def list_sites(self) -> list[dict[str, Any]]:
        return [dict(site) for site in self._sites]

    def _station_card(self, site: dict[str, Any]) -> dict[str, Any]:
        """聚合单个站点的最新液位、越限分级与兜底提示。"""
        card: dict[str, Any] = {
            "站点编号": site["站点编号"],
            "站点名称": site["站点名称"],
            "设计容积": site.get("设计容积", ""),
            "预警液位": site["预警液位"],
            "报警液位": site["报警液位"],
            "液位": None,
            "上报时间": None,
            "data_state": DATA_NO_DATA,
            "level_state": None,
            "severity": DATA_NO_DATA,
            "重复上报": 0,
            "最近有效液位": None,
            "最近有效时间": None,
            "提示": [],
        }

        records = [row for row in self._levels if row["站点编号"] == site["站点编号"]]
        if not records:
            card["提示"].append("该站点暂无液位数据上报，请确认采集链路是否投运")
            return card

        # 同一站点同一上报时间视为重复上报：只保留 id 最大（最新入库）的一条
        latest_by_time: dict[str, dict[str, Any]] = {}
        duplicate_count = 0
        for row in sorted(records, key=lambda item: int(item["id"])):
            key = str(row["上报时间"])
            if key in latest_by_time:
                duplicate_count += 1
            latest_by_time[key] = row
        deduped = sorted(latest_by_time.values(), key=lambda item: str(item["上报时间"]))
        card["重复上报"] = duplicate_count
        if duplicate_count:
            card["提示"].append(
                f"检测到 {duplicate_count} 条重复上报，已按最新入库记录展示"
            )

        latest = deduped[-1]
        card["上报时间"] = latest["上报时间"]
        valid_history = [row for row in reversed(deduped[:-1]) if row["液位"] is not None]

        if latest["液位"] is None:
            # 采集失败：回退最近一次有效液位；连历史有效值都没有时单独提示
            card["data_state"] = DATA_FAILED
            card["severity"] = DATA_FAILED
            if valid_history:
                last_valid = valid_history[0]
                card["最近有效液位"] = last_valid["液位"]
                card["最近有效时间"] = last_valid["上报时间"]
                card["液位"] = last_valid["液位"]
                card["level_state"] = self._classify(last_valid["液位"], site)
                card["提示"].append(
                    f"最新数据采集失败（{latest['上报时间']}），"
                    f"暂展示最近一次有效液位 {last_valid['液位']:.2f}m"
                    f"（{last_valid['上报时间']}），请检查液位计与通讯链路"
                )
            else:
                card["提示"].append(
                    f"液位数据采集失败（{latest['上报时间']}），且暂无历史有效数据，请尽快现场确认"
                )
            return card

        card["data_state"] = DATA_OK
        card["液位"] = latest["液位"]
        card["level_state"] = self._classify(latest["液位"], site)
        card["severity"] = card["level_state"]
        return card

    @staticmethod
    def _classify(level: float, site: dict[str, Any]) -> str:
        if level >= float(site["报警液位"]):
            return LEVEL_ALARM
        if level >= float(site["预警液位"]):
            return LEVEL_WARNING
        return LEVEL_NORMAL

    # ---- 溢流事件 ---------------------------------------------------

    def list_events(self, site: str | None = None) -> list[dict[str, Any]]:
        rows = self._events
        if site:
            rows = [row for row in rows if row["站点编号"] == site]
        return sorted(rows, key=lambda row: int(row["id"]), reverse=True)

    def create_event(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        site_code = str(values["站点编号"]).strip()
        if not any(site["站点编号"] == site_code for site in self._sites):
            return None, f"站点「{site_code}」不在调蓄池站点清单内，请核对后再登记"

        point = str(values["溢流点位"]).strip()
        occurred_at = str(values["发生时间"]).strip()
        # 重复上报兜底：同站点、同溢流点位、同发生时间只允许登记一次
        for row in self._events:
            if (row["站点编号"] == site_code
                    and str(row["溢流点位"]).strip() == point
                    and str(row["发生时间"]).strip() == occurred_at):
                return None, (
                    f"该站点「{point}」在 {occurred_at} 已登记溢流事件"
                    f"（{row['事件编号']}），请勿重复上报"
                )

        new_id = max((int(row["id"]) for row in self._events), default=0) + 1
        today = date.today().strftime("%Y%m%d")
        seq = sum(1 for row in self._events if str(row["事件编号"])[4:12] == today) + 1
        entry = {
            "id": new_id,
            "事件编号": f"OVF-{today}-{seq:03d}",
            "站点编号": site_code,
            "溢流点位": point,
            "发生时间": occurred_at,
            "溢流量": str(values.get("溢流量") or "").strip(),
            "上报人": str(values["上报人"]).strip(),
            "事件描述": str(values.get("事件描述") or "").strip(),
            "status": EVENT_STATUS[0],
            "progress": EVENT_PROGRESS[EVENT_STATUS[0]],
        }
        self._events.append(entry)
        return entry, "雨天溢流事件已登记"

    def run_action(self, event_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = next((row for row in self._events if int(row["id"]) == event_id), None)
        if entry is None:
            return None, f"溢流事件 {event_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于雨天溢流事件可执行范围"
        if action not in ALLOWED_ACTIONS.get(str(entry["status"]), []):
            return None, f"事件当前为「{entry['status']}」，不能执行「{action}」"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["progress"] = EVENT_PROGRESS[target]
        return entry, f"溢流事件已{action}"

    # ---- 看板聚合 ---------------------------------------------------

    def board(self, *, site: str | None = None, sort: str = "site") -> dict[str, Any]:
        """一次返回站点液位卡片、事件列表与统计，保证三者口径同源。"""
        sites = self._sites
        if site:
            sites = [item for item in sites if item["站点编号"] == site]

        stations = [self._station_card(item) for item in sites]
        if sort == "severity":
            stations.sort(key=lambda card: (SEVERITY_ORDER.get(card["severity"], 99), card["站点编号"]))
        else:
            stations.sort(key=lambda card: card["站点编号"])

        events = self.list_events(site)

        def count_status(name: str) -> int:
            return sum(1 for row in events if row["status"] == name)

        summary = {
            "event_total": len(events),
            "todo": count_status("待处置"),
            "doing": count_status("处置中"),
            "done": count_status("已处置"),
            "closed": count_status("已关闭"),
            "site_total": len(stations),
            "alarm": sum(1 for card in stations if card["severity"] == LEVEL_ALARM),
            "warning": sum(1 for card in stations if card["severity"] == LEVEL_WARNING),
            "normal": sum(1 for card in stations if card["severity"] == LEVEL_NORMAL),
            "failed": sum(1 for card in stations if card["data_state"] == DATA_FAILED),
            "no_data": sum(1 for card in stations if card["data_state"] == DATA_NO_DATA),
            "duplicate": sum(int(card["重复上报"]) for card in stations),
        }

        return {
            "summary": summary,
            "stations": stations,
            "events": events,
            "total": len(events),
        }
