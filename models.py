"""岗位数据模型"""
import re
from dataclasses import asdict, dataclass, field, fields

from utils import canonicalize_url, md5_hex

_TEXT_FIELDS = {
    "title", "unit", "location", "province", "city", "education", "major_req",
    "deadline", "link", "source", "publish_date", "region_label", "major_kind",
    "match_points", "exam_advice", "salary_ref", "status", "recruit_count",
    "job_requirements", "salary_detail", "background_check", "exam_subjects",
    "suggestion", "job_type", "first_seen", "category",
}
_INT_DEFAULTS = {
    "score": 0, "region_score": 0, "major_score": 0, "days_left": 0, "tier": 3,
}
_LIST_FIELDS = {"major_hits", "attachments", "match_explanation"}


@dataclass
class Job:
    title: str = ""
    unit: str = ""
    location: str = ""
    province: str = ""
    city: str = ""
    education: str = ""
    major_req: str = ""
    deadline: str = ""
    link: str = ""
    source: str = ""
    publish_date: str = ""
    score: int = 0
    region_score: int = 0
    major_score: int = 0
    region_label: str = ""
    major_kind: str = "none"
    major_hits: list = field(default_factory=list)
    match_points: str = ""
    exam_advice: str = ""
    salary_ref: str = ""
    status: str = "active"
    days_left: int = 0
    recruit_count: str = ""
    job_requirements: str = ""
    salary_detail: str = ""
    background_check: str = ""
    exam_subjects: str = ""
    attachments: list = field(default_factory=list)
    match_explanation: list = field(default_factory=list)
    suggestion: str = ""
    job_type: str = ""
    tier: int = 3
    # 首次发现日期：没有发布日期时作为时效锚点
    first_seen: str = ""
    # 列表栏目名（如“医学人才”），不再混入招聘单位/专业匹配
    category: str = ""

    def unique_id(self):
        """以规范化链接 + 标题年份作为稳定身份。

        同一 URL 被跨年度公告复用时（如“2025-2026学年”与“2026-2027学年”），
        标题年份不同应视为两条记录；同一年内的栏目/单位/标题后缀变化仍去重。
        无链接时才退回文本字段。
        """
        canonical = canonicalize_url(self.link)
        if canonical:
            years = sorted(set(re.findall(r"(20\d{2})", self.title or "")))
            raw = canonical + (f"|{'-'.join(years)}" if years else "")
        else:
            raw = f"{self.unit}|{self.title}|{self.publish_date}"
        return md5_hex(raw)

    def to_dict(self):
        d = asdict(self)
        d["unique_id"] = self.unique_id()
        return d

    @classmethod
    def from_dict(cls, data):
        """容忍历史数据中的 None / 缺失字段，避免整份历史因一条脏数据崩溃。"""
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in (data or {}).items() if k in known}
        for name in _TEXT_FIELDS:
            if not isinstance(values.get(name), str):
                values[name] = "" if values.get(name) is None else str(values[name])
        for name, default in _INT_DEFAULTS.items():
            value = values.get(name, default)
            try:
                values[name] = int(value)
            except (TypeError, ValueError):
                values[name] = default
        for name in _LIST_FIELDS:
            if not isinstance(values.get(name), list):
                values[name] = []
        if values.get("major_kind") not in ("none", "general", "strong"):
            values["major_kind"] = "none"
        if values.get("status") not in ("active", "expiring", "expired"):
            values["status"] = "active"
        return cls(**values)
