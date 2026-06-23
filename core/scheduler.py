"""
时间区块调度引擎 — 将解析后的事件安排到合理的时隙
"""
from datetime import datetime, timedelta
from data.database import get_events_in_range, get_time_preferences


def schedule(event: dict) -> dict:
    """
    调度事件：确保时间合理，处理冲突，补充缺失信息

    Args:
        event: 解析后的事件数据

    Returns:
        调度后的事件数据
    """
    start_time = _parse_time(event.get("start_time"))
    end_time = _parse_time(event.get("end_time"))

    if start_time is None:
        # 无时间 → 根据偏好推荐
        event_type = event.get("event_type", "other")
        suggestion = suggest_time(event_type)
        start_time = suggestion["start"]
        end_time = suggestion["end"]
        event["start_time"] = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        event["end_time"] = end_time.strftime("%Y-%m-%dT%H:%M:%S")

    elif end_time is None:
        # 只有开始时间 → 默认 1 小时
        end_time = start_time + timedelta(hours=1)
        event["end_time"] = end_time.strftime("%Y-%m-%dT%H:%M:%S")

    # 检测冲突
    conflicts = detect_conflict(start_time, end_time, exclude_id=event.get("id"))
    if conflicts:
        event["_conflicts"] = [
            {"id": c["id"], "title": c["title"], "start_time": c["start_time"]}
            for c in conflicts
        ]

    # 如果是过去的日期，移到明天
    now = datetime.now()
    if start_time < now - timedelta(hours=1):
        suggested = suggest_time(event.get("event_type", "other"))
        event["start_time"] = suggested["start"].strftime("%Y-%m-%dT%H:%M:%S")
        event["end_time"] = suggested["end"].strftime("%Y-%m-%dT%H:%M:%S")
        event["_auto_rescheduled"] = True

    return event


def detect_conflict(start: datetime, end: datetime,
                    exclude_id: int = None) -> list[dict]:
    """
    检测时间冲突

    Returns:
        冲突的事件列表
    """
    start_str = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%S")

    # 获取同一天的事件
    day_start = start.strftime("%Y-%m-%d") + "T00:00:00"
    day_end = start.strftime("%Y-%m-%d") + "T23:59:59"

    existing = get_events_in_range(day_start, day_end)

    conflicts = []
    for ev in existing:
        if exclude_id and ev["id"] == exclude_id:
            continue

        ev_start = _parse_time(ev["start_time"])
        ev_end = _parse_time(ev.get("end_time"))

        if ev_start is None:
            continue
        if ev_end is None:
            ev_end = ev_start + timedelta(hours=1)

        # 检查时间重叠
        if start < ev_end and end > ev_start:
            conflicts.append(ev)

    return conflicts


def suggest_time(event_type: str) -> dict:
    """
    根据事件类型和用户偏好推荐时间

    Returns:
        {"start": datetime, "end": datetime}
    """
    now = datetime.now()

    # 查询该类型的时间偏好
    prefs = get_time_preferences(event_type)

    if prefs:
        # 使用最高置信度的偏好
        best = prefs[0]
        hour = best.get("preferred_start_hour", 9)
        dow = best.get("preferred_day_of_week")

        target = now + timedelta(hours=1)
        # 如果指定了偏好的星期几，跳到那天
        if dow is not None:
            current_dow = now.weekday()
            days_ahead = (dow - current_dow) % 7
            if days_ahead == 0 and now.hour >= hour:
                days_ahead = 7  # 下周
            target = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
        else:
            # 明天同一时间
            if now.hour >= hour:
                target = (now + timedelta(days=1)).replace(
                    hour=hour, minute=0, second=0, microsecond=0
                )
            else:
                target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    else:
        # 默认规则
        hour_map = {
            "task": 9,
            "meeting": 14,
            "reminder": 9,
            "job_search": 15,
            "learning": 19,
            "other": 10,
        }
        hour = hour_map.get(event_type, 9)

        target = now + timedelta(hours=1)
        if now.hour >= hour:
            target = (now + timedelta(days=1)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
        else:
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)

    end = target + timedelta(hours=1)

    return {"start": target, "end": end}


def _parse_time(time_str) -> datetime | None:
    """解析 ISO 时间字符串"""
    if not time_str:
        return None
    try:
        # 处理各种 ISO 8601 变体
        time_str = time_str.replace("Z", "+00:00")
        if "T" in time_str:
            return datetime.fromisoformat(time_str)
        # 仅日期格式
        return datetime.strptime(time_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
