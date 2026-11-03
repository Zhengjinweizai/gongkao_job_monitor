"""工具函数与数据模型测试"""
import json
import os

import pytest

from models import Job
from utils import (
    atomic_write_text,
    canonicalize_url,
    md5_hex,
    safe_url,
    stars,
    to_int,
)


@pytest.mark.parametrize("url, expected", [
    ("HTTPS://Example.COM/a/?utm_source=x#frag", "https://example.com/a"),
    ("http://example.com:80/a//b/", "http://example.com/a/b"),
    ("https://example.com:443/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
    ("https://example.com/a/?from=wechat&id=3", "https://example.com/a?id=3"),
    ("javascript:alert(1)", ""),
    ("mailto:a@b.com", ""),
    ("", ""),
    ("not a url", ""),
])
def test_canonicalize_url(url, expected):
    assert canonicalize_url(url) == expected


@pytest.mark.parametrize("url, expected", [
    ("https://example.com/a", "https://example.com/a"),
    ("javascript:alert(1)", ""),
    ("data:text/html,hi", ""),
    ("", ""),
])
def test_safe_url(url, expected):
    assert safe_url(url) == expected


def test_md5_stars_to_int():
    assert md5_hex("中文") == "a7bac2239fcdcb3a067903d8077c4a07"
    assert stars(0) == "⭐"
    assert stars(10) == "⭐" * 5
    assert stars(99) == "⭐" * 5
    assert to_int("4") == 4
    assert to_int(None, 7) == 7
    assert to_int("x", 3) == 3


def test_atomic_write_text(tmp_path):
    path = tmp_path / "sub" / "file.json"
    atomic_write_text(str(path), '{"a": 1}')
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert [p.name for p in path.parent.glob(".tmp-*")] == []
    atomic_write_text(str(path), "next")
    assert path.read_text(encoding="utf-8") == "next"


def test_job_unique_id_is_stable_by_url():
    a = Job(title="岗位 A", unit="单位", link="https://example.com/job/1?utm_source=x")
    b = Job(title="岗位 A（更新标题）", unit="另一个单位", link="https://EXAMPLE.com/job/1/")
    assert a.unique_id() == b.unique_id()
    c = Job(title="岗位 A", unit="单位", link="https://example.com/job/2")
    assert a.unique_id() != c.unique_id()
    assert len(a.unique_id()) == 32


def test_job_unique_id_without_link():
    a = Job(title="岗位", unit="单位", publish_date="2026-01-01")
    b = Job(title="岗位", unit="单位", publish_date="2026-01-02")
    assert a.unique_id() != b.unique_id()


def test_job_to_dict_and_from_dict():
    job = Job(title="岗位", score=5, major_hits=["医学"], tier=2)
    data = job.to_dict()
    assert data["unique_id"] == job.unique_id()
    assert data["major_hits"] == ["医学"]

    restored = Job.from_dict(data)
    assert restored.title == "岗位"
    assert restored.score == 5
    assert restored.tier == 2


def test_job_from_dict_tolerates_dirty_history():
    restored = Job.from_dict({
        "title": None,
        "score": "8",
        "tier": None,
        "days_left": "x",
        "major_hits": None,
        "attachments": "not-a-list",
        "major_kind": "bogus",
        "status": "unknown",
        "extra": "ignored",
    })
    assert restored.title == ""
    assert restored.score == 8
    assert restored.tier == 3
    assert restored.days_left == 0
    assert restored.major_hits == []
    assert restored.attachments == []
    assert restored.major_kind == "none"
    assert restored.status == "active"
    assert not hasattr(restored, "extra")


def test_job_from_dict_empty():
    restored = Job.from_dict(None)
    assert restored.title == ""
    assert restored.link == ""
    assert restored.tier == 3


def test_atomic_write_replaces_without_temp_leftovers(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("old", encoding="utf-8")
    atomic_write_text(str(path), "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert not os.path.exists(str(path) + ".tmp")


def test_job_unique_id_year_bucket():
    url = "https://www.gaoxiaojob.com/announcement/detail/308957.html"
    old = Job(title="2025-2026学年度招聘公告", link=url)
    new = Job(title="2026-2027学年度招聘公告", link=url)
    new_copy = Job(title="2026-2027学年度招聘公告（补充）", link=url)
    assert old.unique_id() != new.unique_id()
    assert new.unique_id() == new_copy.unique_id()
