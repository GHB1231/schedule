"""
智能日程安排表 — Web 版（Flask 后端）
手机和电脑共用同一个服务端，数据自动同步
"""
import os
import sys
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, send_from_directory, redirect, url_for

# 初始化 Flask
app = Flask(__name__, static_folder="web", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# 数据库初始化
from data.database import init_db
init_db()

from data.database import (
    insert_event, update_event, delete_event,
    get_event, get_events_in_range, get_all_events,
    insert_sample, update_sample, get_all_samples,
    get_corrected_samples, get_sample_count,
    insert_job_info, get_job_info, get_job_info_recent,
    upsert_time_preference, get_time_preferences,
    set_preference as db_set_pref, get_preference as db_get_pref,
)
from config import EVENT_TYPE_COLORS


# ============ 简单鉴权 ============

# 密码存在数据库中（首次运行从环境变量或默认密码读取）
def _get_password():
    pwd = db_get_pref("login_password")
    if not pwd:
        pwd = os.environ.get("APP_PASSWORD", "schedule123")
        db_set_pref("login_password", _hash_pwd(pwd))
        return pwd
    return pwd


def _hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def _check_pwd(pwd: str) -> bool:
    stored = db_get_pref("login_password")
    if not stored:
        return True
    return _hash_pwd(pwd) == stored


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "未登录", "code": "AUTH_REQUIRED"}), 401
        return f(*args, **kwargs)
    return decorated


# ============ 页面路由 ============

@app.route("/")
def index():
    if not session.get("logged_in"):
        return send_from_directory("web", "login.html")
    return send_from_directory("web", "index.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    pwd = data.get("password", "")
    if _check_pwd(pwd):
        session["logged_in"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "密码错误"}), 403


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/check_auth")
def check_auth():
    return jsonify({"logged_in": session.get("logged_in", False)})


# ============ 事件 API ============

@app.route("/api/events")
@login_required
def api_get_events():
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    if start_date and end_date:
        events = get_events_in_range(start_date, end_date)
    else:
        events = get_all_events()

    for ev in events:
        tags = ev.get("tags", "[]")
        if isinstance(tags, str):
            try:
                ev["tags"] = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                ev["tags"] = []
        ev["color"] = EVENT_TYPE_COLORS.get(ev.get("event_type", "other"), "#95A5A6")

    return jsonify(events)


@app.route("/api/events", methods=["POST"])
@login_required
def api_add_event():
    event_data = request.get_json()
    event_id = insert_event(event_data)
    return jsonify({"id": event_id, "status": "ok"})


@app.route("/api/events/<int:event_id>", methods=["PUT"])
@login_required
def api_update_event(event_id):
    updates = request.get_json()
    update_event(event_id, updates)
    return jsonify({"status": "ok"})


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
@login_required
def api_delete_event(event_id):
    delete_event(event_id)
    return jsonify({"status": "ok"})


# ============ 智能解析 API ============

@app.route("/api/parse", methods=["POST"])
@login_required
def api_parse_input():
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "输入为空"}), 400

    try:
        from core.parser import parse as smart_parse, classify_event_type
        from core.scheduler import schedule as smart_schedule
        from core.learner import get_few_shot_samples, record_parse

        now = datetime.now()
        few_shot = get_few_shot_samples(text)
        parsed = smart_parse(text, now, few_shot)
        scheduled = smart_schedule(parsed)
        sample_id = record_parse(text, scheduled)
        scheduled["_sample_id"] = sample_id

        # 自动触发校招搜索
        event_type = scheduled.get("event_type", "")
        tags = scheduled.get("tags", [])
        if event_type == "job_search" or any(
            kw in text for kw in ["校招","面试","笔试","投递","招聘","offer","内推","网申","春招","秋招"]
        ):
            scheduled["_trigger_job_search"] = True
            search_keywords = list(set(
                [t for t in tags if len(t) >= 2] +
                [w for w in ["校招", "校园招聘"] if w in text]
            ))
            if not search_keywords:
                search_keywords = ["校招"]
            scheduled["_job_keywords"] = search_keywords

        return jsonify(scheduled)

    except Exception as e:
        print(f"[WARN] 智能解析失败: {e}")
        return jsonify({
            "title": text,
            "event_type": "other",
            "start_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "description": text,
            "tags": [],
            "source": "manual",
            "_parse_error": str(e),
        })


@app.route("/api/parse/confirm", methods=["POST"])
@login_required
def api_confirm_parse():
    parsed_data = request.get_json()
    sample_id = parsed_data.pop("_sample_id", None)
    parsed_data.pop("_parse_error", None)
    parsed_data.pop("_conflicts", None)
    parsed_data.pop("_auto_rescheduled", None)
    parsed_data.pop("_trigger_job_search", None)
    parsed_data.pop("_job_keywords", None)

    tags = parsed_data.get("tags", [])
    if isinstance(tags, list):
        parsed_data["tags"] = json.dumps(tags, ensure_ascii=False)
    else:
        parsed_data["tags"] = "[]"

    parsed_data["source"] = "auto"
    event_id = insert_event(parsed_data)
    return jsonify({"id": event_id, "status": "ok", "sample_id": sample_id})


@app.route("/api/parse/correct", methods=["POST"])
@login_required
def api_correct_parse():
    data = request.get_json()
    sample_id = data.get("sample_id")
    correction = data.get("correction")
    from core.learner import record_correction
    record_correction(sample_id, correction)
    return jsonify({"status": "ok"})


# ============ 校招搜索 API ============

@app.route("/api/jobs/search", methods=["POST"])
@login_required
def api_search_jobs():
    data = request.get_json()
    keywords = data.get("keywords", ["校招"])
    try:
        from core.job_searcher import search_campus_recruitment, get_cached_job_info, create_job_events
        results = search_campus_recruitment(keywords)
        create_job_events(results)
        return jsonify(results)
    except Exception as e:
        print(f"[WARN] 校招搜索失败: {e}")
        return jsonify(get_job_info_recent(days=30))


@app.route("/api/jobs")
@login_required
def api_get_job_panel():
    return jsonify(get_job_info_recent(days=30))


@app.route("/api/jobs/<int:job_id>/applied", methods=["POST"])
@login_required
def api_mark_job_applied(job_id):
    data = request.get_json()
    is_applied = data.get("is_applied", True)
    from data.database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE job_info SET is_applied = ? WHERE id = ?",
        (1 if is_applied else 0, job_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


# ============ 学习统计 API ============

@app.route("/api/stats")
@login_required
def api_get_learning_stats():
    total = get_sample_count()
    corrected = len(get_corrected_samples())
    accuracy = round((1 - corrected / total) * 100, 1) if total > 0 else 0.0
    time_prefs = get_time_preferences()
    return jsonify({
        "total_samples": total,
        "corrected_samples": corrected,
        "accuracy": accuracy,
        "time_preferences": time_prefs,
    })


# ============ 启动 ============

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
