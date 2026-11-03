"""匹配打分与时效逻辑测试"""
import datetime

import pytest

from config import REGION_HIGH, REGION_LOW, REGION_MED, VALID_WINDOW_DAYS
from filters import (
    build_match_explanation,
    build_match_points,
    check_validity,
    enrich,
    get_exam_advice,
    get_salary_ref,
    infer_types,
    major_score,
    parse_date,
    parse_location,
    region_info,
    suggestion,
)


@pytest.mark.parametrize("value, expected", [
    ("2026-11-03", datetime.date(2026, 11, 3)),
    ("2026/11/3", datetime.date(2026, 11, 3)),
    ("2026年11月3日", datetime.date(2026, 11, 3)),
    ("2026.11.3", datetime.date(2026, 11, 3)),
    (" 2026 年 11 月 3 日 ", datetime.date(2026, 11, 3)),
    ("2026年11月3号", datetime.date(2026, 11, 3)),
    ("报名时间 2026-11-03 至 2026-11-10", datetime.date(2026, 11, 3)),
    ("2026-13-01", None),
    ("2026-02-30", None),
    ("", None),
    (None, None),
])
def test_parse_date(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("deadline, expected", [
    ("2026-11-02", ("expired", -1)),
    ("2026-11-03", ("expiring", 0)),
    ("2026-11-04", ("expiring", 1)),
    ("2026-11-06", ("expiring", 3)),
    ("2026-11-07", ("active", 4)),
    ("2026-10-31", ("expired", -3)),
    ("2026年11月7日", ("active", 4)),
])
def test_check_validity_deadline_boundaries(deadline, expected):
    assert check_validity("", deadline, datetime.date(2026, 11, 3)) == expected


def test_check_validity_publish_fallback():
    today = datetime.date(2026, 11, 3)
    assert check_validity("2026-10-05", "", today) == ("active", 1)
    assert check_validity("2026-10-04", "", today) == ("active", 0)
    assert check_validity("2026-10-03", "", today) == ("expired", -1)
    assert check_validity("", "", today) == ("active", VALID_WINDOW_DAYS)
    assert check_validity("待定", "待定", today, fallback_date="2026-10-04") == ("active", 0)
    assert check_validity("", "", "2026-11-03") == ("active", VALID_WINDOW_DAYS)


@pytest.mark.parametrize("province, city, score", [
    ("甘肃", "天水", REGION_HIGH),
    ("甘肃", "天水市", REGION_HIGH),
    ("陕西省", "西安市", REGION_HIGH),
    ("甘肃", "兰州", REGION_MED),
    ("陕西", None, REGION_MED),
    ("四川", "成都", REGION_LOW),
    ("", "", REGION_LOW),
    ("陕西", "天水", REGION_MED),
])
def test_region_info(province, city, score):
    assert region_info(province, city)[0] == score


@pytest.mark.parametrize("text, expected", [
    ("甘肃省天水市", ("甘肃", "天水")),
    ("天水市", ("甘肃", "天水")),
    ("西安市雁塔区", ("陕西", "西安")),
    ("兰州市", ("甘肃", "兰州")),
    ("四川省成都市", ("四川", "成都")),
    ("北京市", ("北京", "")),
    ("", ("", "")),
    (None, ("", "")),
    ("甘肃和陕西联合招聘", ("甘肃", "")),
])
def test_parse_location(text, expected):
    assert parse_location(text) == expected


def test_major_score_precedence():
    assert major_score("生物医学工程")[0] == 5
    assert major_score("医学专业不限")[0] == 5
    assert major_score("专业不限")[0] == 2
    assert major_score("机械设计") == (0, [], "none")
    assert major_score("") == (0, [], "none")
    assert major_score(None) == (0, [], "none")


@pytest.mark.parametrize("title, source, expected", [
    ("劳务派遣人员招聘", "国家公务员局", (3, "其他")),
    ("公务员招录公告", "高校人才网", (1, "公务员")),
    ("公开遴选公告", "", (1, "公务员")),
    ("事业单位公开招聘", "", (2, "事业编制")),
    ("XX医院招聘", "", (2, "事业编制")),
    ("随便", "事业单位招聘网", (2, "事业编制")),
    ("编外教师招聘", "", (3, "其他")),
    ("招聘", "", (3, "其他")),
    ("参公管理", "甘肃组工网", (1, "公务员")),
])
def test_infer_types(title, source, expected):
    assert infer_types(title, "", source) == expected


def test_suggestion_thresholds():
    assert suggestion(0) == "仅作参考"
    assert suggestion(1) == "仅作参考"
    assert suggestion(2) == "一般关注（可备选）"
    assert suggestion(4) == "一般关注（可备选）"
    assert suggestion(5) == "重点关注"
    assert suggestion(7) == "重点关注"
    assert suggestion(8) == "优先关注"


def test_enrich_scores_title_not_unit(make_job):
    # unit 是“医学人才”栏目名，但标题不含专业词：不应获得 +5
    job = make_job(title="天水市某单位招聘公告", unit="医学人才",
                   publish_date="2026-10-20", deadline="2026-11-10")
    enrich(job, datetime.date(2026, 11, 3))
    assert job.province == "甘肃"
    assert job.city == "天水"
    assert job.region_score == REGION_HIGH
    assert job.major_score == 0
    assert job.score == REGION_HIGH
    assert job.status == "active"
    assert job.days_left == 7
    assert job.tier == 2


def test_enrich_full_match(make_job):
    job = make_job(title="天水市第一人民医院临床医学招聘", unit="天水市第一人民医院",
                   publish_date="2026-10-01", deadline="2026-11-10")
    enrich(job, datetime.date(2026, 11, 3))
    assert job.score == 8
    assert job.suggestion == "优先关注"
    assert job.status == "active"
    assert job.days_left == 7
    assert "E类" in job.exam_advice
    assert "天水" in job.match_points


def test_enrich_clamps_future_publish_date(make_job):
    job = make_job(publish_date="2027-01-01", deadline="")
    enrich(job, datetime.date(2026, 11, 3))
    assert job.publish_date == "2026-11-03"
    assert job.status == "active"


def test_enrich_no_dates_uses_fallback(make_job):
    job = make_job(publish_date="", deadline="")
    enrich(job, datetime.date(2026, 11, 3), fallback_date="2026-09-01")
    assert job.status == "expired"
    assert job.days_left < 0


def test_get_exam_advice_and_salary(make_job):
    medical = make_job(title="医院招聘", unit="某医院")
    civil = make_job(title="公务员招录", source="国家公务员局")
    general = make_job(title="综合管理岗", source="某单位")
    general.major_kind = "general"
    assert "E类" in get_exam_advice(medical)
    assert "行测" in get_exam_advice(civil)
    assert "A类" in get_exam_advice(general)

    assert "4k-5k" in get_salary_ref(make_job(province="甘肃", city="天水"))
    assert "5k-7k" in get_salary_ref(make_job(province="陕西", city="西安"))
    assert "公务员" in get_salary_ref(make_job(province="", source="国家公务员局"))


def test_build_match_points_and_explanation(make_job):
    job = make_job(title="临床医学招聘", city="天水", province="甘肃")
    job.region_score, job.major_kind, job.major_hits = REGION_HIGH, "strong", ["医学"]
    job.score, job.education, job.location = 8, "硕士", "天水"
    points = build_match_points(job, ["医学"], "strong")
    assert "专业强匹配" in points and "地域优势" in points
    explanation = build_match_explanation(job)
    assert any("+3" in line for line in explanation)
    assert any("+5" in line for line in explanation)
    assert any("总分 8" in line for line in explanation)


def test_enrich_keeps_explicit_location(make_job):
    job = make_job(title="招聘公告", location="四川省成都市", province="四川", city="成都")
    enrich(job, datetime.date(2026, 11, 3))
    assert job.location == "四川省成都市"
    assert job.region_score == REGION_LOW
