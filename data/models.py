"""
数据模型定义 — 使用 dataclass 表示各表实体
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import json


@dataclass
class Event:
    """日程事件"""
    title: str
    event_type: str
    start_time: str  # ISO 8601
    id: Optional[int] = None
    description: str = ""
    end_time: Optional[str] = None
    location: str = ""
    priority: int = 0
    tags: list = field(default_factory=list)
    source: str = "manual"  # manual / auto / job_search
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = json.dumps(self.tags, ensure_ascii=False)
        return d

    @classmethod
    def from_row(cls, row: dict) -> "Event":
        tags = row.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        return cls(
            id=row.get("id"),
            title=row["title"],
            description=row.get("description", ""),
            event_type=row.get("event_type", "other"),
            start_time=row["start_time"],
            end_time=row.get("end_time"),
            location=row.get("location", ""),
            priority=row.get("priority", 0),
            tags=tags,
            source=row.get("source", "manual"),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


@dataclass
class LearningSample:
    """学习样本"""
    raw_input: str
    parsed_result: dict
    id: Optional[int] = None
    user_correction: Optional[dict] = None
    is_correct: bool = False
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["parsed_result"] = json.dumps(self.parsed_result, ensure_ascii=False)
        d["user_correction"] = json.dumps(self.user_correction, ensure_ascii=False) if self.user_correction else None
        return d

    @classmethod
    def from_row(cls, row: dict) -> "LearningSample":
        parsed = row.get("parsed_result", "{}")
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (json.JSONDecodeError, TypeError):
                parsed = {}

        correction = row.get("user_correction")
        if isinstance(correction, str) and correction:
            try:
                correction = json.loads(correction)
            except (json.JSONDecodeError, TypeError):
                correction = None

        return cls(
            id=row.get("id"),
            raw_input=row["raw_input"],
            parsed_result=parsed,
            user_correction=correction,
            is_correct=bool(row.get("is_correct", 0)),
            created_at=row.get("created_at", ""),
        )


@dataclass
class JobInfo:
    """校招信息"""
    company: str
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    deadline: str = ""
    url: str = ""
    source: str = ""
    is_applied: bool = False
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "JobInfo":
        return cls(
            id=row.get("id"),
            company=row["company"],
            title=row.get("title", ""),
            description=row.get("description", ""),
            deadline=row.get("deadline", ""),
            url=row.get("url", ""),
            source=row.get("source", ""),
            is_applied=bool(row.get("is_applied", 0)),
            fetched_at=row.get("fetched_at", ""),
        )


@dataclass
class TimePreference:
    """时间偏好"""
    event_type: str
    id: Optional[int] = None
    preferred_start_hour: Optional[int] = None
    preferred_day_of_week: Optional[int] = None
    confidence: float = 0.0
    sample_count: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "TimePreference":
        return cls(
            id=row.get("id"),
            event_type=row["event_type"],
            preferred_start_hour=row.get("preferred_start_hour"),
            preferred_day_of_week=row.get("preferred_day_of_week"),
            confidence=row.get("confidence", 0.0),
            sample_count=row.get("sample_count", 0),
            updated_at=row.get("updated_at", ""),
        )
