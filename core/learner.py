"""
学习引擎 — 记忆式学习，通过记录用户修正来提升解析准确率
"""
import json
from datetime import datetime
from collections import Counter

from data.database import (
    insert_sample, update_sample, get_all_samples,
    get_corrected_samples, get_sample_count,
    upsert_time_preference, get_time_preferences,
)


def record_parse(raw_input: str, parsed: dict) -> int:
    """
    记录一次解析结果

    Args:
        raw_input: 用户原始输入
        parsed: 系统解析结果

    Returns:
        样本 ID
    """
    return insert_sample(raw_input, parsed)


def record_correction(sample_id: int, correction: dict):
    """
    记录用户对解析结果的修正

    Args:
        sample_id: 样本 ID
        correction: 用户修正后的事件数据
    """
    update_sample(sample_id, correction, is_correct=False)

    # 更新事件类型修正
    if "event_type" in correction:
        _update_event_type_stats(correction["event_type"])

    # 更新时间偏好
    _update_time_preferences_from_correction(correction)


def get_similar_samples(text: str, limit: int = 5) -> list[dict]:
    """
    获取与输入文本相似的历史样本

    使用 jieba 分词 + 关键词重叠度计算相似度
    """
    import jieba

    samples = get_corrected_samples()
    if not samples:
        return []

    input_words = set(jieba.cut(text))
    # 过滤停用词
    stopwords = {"的", "了", "在", "是", "我", "要", "去", "和", "与",
                 "这", "那", "吗", "呢", "吧", "啊", "哦", "嗯", "就", "也",
                 "都", "还", "会", "能", "可以", "一个", "一下", "什么", "怎么"}
    input_words -= stopwords

    if not input_words:
        return samples[:limit]

    scored = []
    for sample in samples:
        raw = sample.get("raw_input", "")
        sample_words = set(jieba.cut(raw)) - stopwords

        if not sample_words:
            continue

        # Jaccard 相似度
        intersection = input_words & sample_words
        union = input_words | sample_words
        score = len(intersection) / len(union) if union else 0

        # 如果有修正，加分
        if sample.get("user_correction"):
            score *= 1.5

        scored.append((score, sample))

    # 按相似度排序，取 top-N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:limit]]


def get_few_shot_samples(text: str, limit: int = 5) -> list[dict]:
    """
    获取与输入相关的 few-shot 学习样本

    Returns:
        相似样本列表（可直接传给 parser.parse 的 few_shot_samples 参数）
    """
    return get_similar_samples(text, limit=limit)


def update_time_preferences():
    """
    从所有修正样本中重新统计时间偏好，更新 time_preferences 表
    """
    samples = get_corrected_samples()
    if not samples:
        return

    # 按事件类型分组统计
    type_hours = {}   # {event_type: [hour, ...]}
    type_dows = {}    # {event_type: [day_of_week, ...]}

    for sample in samples:
        try:
            correction = json.loads(sample.get("user_correction", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue

        event_type = correction.get("event_type", "other")
        start_str = correction.get("start_time")

        if not start_str:
            continue

        try:
            start_dt = datetime.fromisoformat(start_str)
        except (ValueError, TypeError):
            continue

        hour = start_dt.hour
        dow = start_dt.weekday()

        if event_type not in type_hours:
            type_hours[event_type] = []
            type_dows[event_type] = []

        type_hours[event_type].append(hour)
        type_dows[event_type].append(dow)

    # 为每个事件类型计算偏好
    for event_type in set(list(type_hours.keys()) + list(type_dows.keys())):
        hours = type_hours.get(event_type, [])
        dows = type_dows.get(event_type, [])

        # 取最常见的小时（众数）
        if hours:
            hour_counter = Counter(hours)
            most_common_hour, hour_count = hour_counter.most_common(1)[0]
            hour_confidence = hour_count / len(hours)
        else:
            most_common_hour = None
            hour_confidence = 0.0

        # 取最常见的星期几
        if dows:
            dow_counter = Counter(dows)
            most_common_dow, dow_count = dow_counter.most_common(1)[0]
            dow_confidence = dow_count / len(dows)
        else:
            most_common_dow = None
            dow_confidence = 0.0

        upsert_time_preference({
            "event_type": event_type,
            "preferred_start_hour": most_common_hour,
            "preferred_day_of_week": most_common_dow,
            "confidence": (hour_confidence + dow_confidence) / 2,
            "sample_count": len(samples),
        })


def get_time_suggestions(event_type: str) -> dict:
    """
    获取特定事件类型的时间建议

    Returns:
        {"preferred_hours": [...], "preferred_days": [...], "confidence": float}
    """
    prefs = get_time_preferences(event_type)

    if not prefs:
        return {
            "preferred_hours": [9, 10, 14, 15],
            "preferred_days": [0, 1, 2, 3, 4],
            "confidence": 0.0,
        }

    hours = []
    days = []
    for p in prefs:
        if p.get("preferred_start_hour") is not None:
            hours.append(p["preferred_start_hour"])
        if p.get("preferred_day_of_week") is not None:
            days.append(p["preferred_day_of_week"])

    confidences = [p.get("confidence", 0) for p in prefs]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "preferred_hours": hours[:4],
        "preferred_days": days[:3],
        "confidence": round(avg_confidence, 2),
    }


def _update_event_type_stats(event_type: str):
    """更新事件类型统计（内部使用）"""
    # 简单计数，可以后续扩展
    pass


def _update_time_preferences_from_correction(correction: dict):
    """从单次修正中更新时间偏好（增量更新）"""
    update_time_preferences()
