"""
智能日程安排表 — Eel 桌面应用入口
"""
import os
import sys
import json
from datetime import datetime, timedelta
import eel

from config import EVENT_TYPE_COLORS
from data.database import init_db
from data.database import (
    insert_event, update_event, delete_event,
    get_event, get_events_in_range, get_all_events,
)
from data.database import (
    insert_sample, update_sample, get_all_samples,
    get_corrected_samples, get_sample_count,
)
from data.database import (
    insert_job_info, get_job_info, get_job_info_recent,
)
from data.database import (
    upsert_time_preference, get_time_preferences,
    set_preference, get_preference,
)
from data.models import Event, LearningSample, JobInfo, TimePreference


# ============ 初始化 ============

def bootstrap():
    """应用启动初始化"""
    init_db()
    print("[OK] 数据库初始化完成")


# ============ 事件 API（暴露给前端） ============

@eel.expose
def api_get_events(start_date: str = None, end_date: str = None) -> list:
    """获取事件列表"""
    if start_date and end_date:
        events = get_events_in_range(start_date, end_date)
    else:
        events = get_all_events()

    # 转换 tags 为前端可直接使用的格式
    for ev in events:
        tags = ev.get("tags", "[]")
        if isinstance(tags, str):
            try:
                ev["tags"] = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                ev["tags"] = []
        ev["color"] = EVENT_TYPE_COLORS.get(ev.get("event_type", "other"), "#95A5A6")

    return events


@eel.expose
def api_add_event(event_data: dict) -> dict:
    """添加事件（手动）"""
    event_id = insert_event(event_data)
    return {"id": event_id, "status": "ok"}


@eel.expose
def api_update_event(event_id: int, updates: dict) -> dict:
    """更新事件"""
    update_event(event_id, updates)
    return {"status": "ok"}


@eel.expose
def api_delete_event(event_id: int) -> dict:
    """删除事件"""
    delete_event(event_id)
    return {"status": "ok"}


# ============ 智能解析 API ============

@eel.expose
def api_parse_input(text: str) -> dict:
    """智能解析用户输入（调用 parser.py）
    返回解析后的事件数据。如果检测到求职相关内容，自动触发校招搜索
    """
    try:
        from core.parser import parse as smart_parse, classify_event_type
        from core.scheduler import schedule as smart_schedule
        from core.learner import get_few_shot_samples, record_parse

        now = datetime.now()

        # 获取 few-shot 样本
        few_shot = get_few_shot_samples(text)

        # 智能解析
        parsed = smart_parse(text, now, few_shot)

        # 调度（安排时间区块）
        scheduled = smart_schedule(parsed)

        # 记录样本
        sample_id = record_parse(text, scheduled)

        # 附加样本 ID 以便后续修正
        scheduled["_sample_id"] = sample_id

        # 如果检测到求职相关内容，自动触发校招搜索
        event_type = scheduled.get("event_type", "")
        tags = scheduled.get("tags", [])

        if event_type == "job_search" or any(
            kw in text for kw in ["校招", "面试", "笔试", "投递", "招聘",
                                   "offer", "内推", "网申", "春招", "秋招"]
        ):
            scheduled["_trigger_job_search"] = True
            # 从文本和标签中提取搜索关键词
            search_keywords = list(set(
                [t for t in tags if len(t) >= 2] +
                [w for w in ["校招", "校园招聘"] if w in text]
            ))
            if not search_keywords:
                search_keywords = ["校招"]
            scheduled["_job_keywords"] = search_keywords

        return scheduled

    except Exception as e:
        print(f"[WARN] 智能解析失败: {e}")
        return {
            "title": text,
            "event_type": "other",
            "start_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "description": text,
            "tags": [],
            "source": "manual",
            "_parse_error": str(e),
        }


@eel.expose
def api_confirm_parse(parsed_data: dict) -> dict:
    """用户确认解析结果，保存事件"""
    sample_id = parsed_data.pop("_sample_id", None)
    parsed_data.pop("_parse_error", None)
    parsed_data.pop("_conflicts", None)
    parsed_data.pop("_auto_rescheduled", None)

    # 处理 tags
    tags = parsed_data.get("tags", [])
    if isinstance(tags, list):
        parsed_data["tags"] = json.dumps(tags, ensure_ascii=False)
    else:
        parsed_data["tags"] = "[]"

    parsed_data["source"] = "auto"

    event_id = insert_event(parsed_data)
    return {"id": event_id, "status": "ok", "sample_id": sample_id}


@eel.expose
def api_correct_parse(sample_id: int, correction: dict) -> dict:
    """用户修正解析结果，记录学习"""
    from core.learner import record_correction
    record_correction(sample_id, correction)
    return {"status": "ok"}


# ============ 校招搜索 API ============

@eel.expose
def api_search_jobs(keywords: list = None) -> list:
    """搜索校招信息"""
    try:
        from core.job_searcher import (
            search_campus_recruitment, get_cached_job_info,
        )
        if keywords:
            results = search_campus_recruitment(keywords)
        else:
            results = get_cached_job_info()

        # 如果有截止日期的信息，自动创建日历事件
        from core.job_searcher import create_job_events
        create_job_events(results)

        return results
    except Exception as e:
        print(f"[WARN] 校招搜索失败: {e}")
        # 返回缓存的信息
        return get_job_info_recent(days=30)


@eel.expose
def api_get_job_panel() -> list:
    """获取校招面板数据"""
    return get_job_info_recent(days=30)


@eel.expose
def api_mark_job_applied(job_id: int, is_applied: bool = True) -> dict:
    """标记校招信息为已投递/取消标记"""
    from data.database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE job_info SET is_applied = ? WHERE id = ?",
        (1 if is_applied else 0, job_id),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ============ 学习统计 API ============

@eel.expose
def api_get_learning_stats() -> dict:
    """获取学习统计信息"""
    total = get_sample_count()
    corrected = len(get_corrected_samples())

    accuracy = 0.0
    if total > 0:
        accuracy = round((1 - corrected / total) * 100, 1)

    time_prefs = get_time_preferences()

    return {
        "total_samples": total,
        "corrected_samples": corrected,
        "accuracy": accuracy,
        "time_preferences": time_prefs,
    }


# ============ 启动应用 ============

def main():
    bootstrap()

    # 处理 PyInstaller 打包后的路径
    import sys
    if getattr(sys, 'frozen', False):
        # 打包后运行: web 文件夹在 sys._MEIPASS 下
        web_dir = os.path.join(sys._MEIPASS, "web")
    else:
        web_dir = "web"

    # 启动 Eel 桌面窗口
    eel.init(web_dir)
    eel.start(
        "index.html",
        mode="chrome",        # 使用系统 Chrome/Edge
        size=(1400, 900),
        port=0,               # 自动选择端口
        cmdline_args=[        # Chrome 启动参数
            "--disable-extensions",
            "--disable-web-security",
            "--disable-features=DialMediaRouteProvider",
        ],
    )


if __name__ == "__main__":
    main()
