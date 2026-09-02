"""国企/央企轨道：0-100 评分（专业40 + 企业资质30 + 岗位性质20 + 地域10）"""
import datetime
import re

from config import (SOE_CITY_WEIGHT, SOE_MAJOR_STRONG, SOE_MAJOR_MID,
                    SOE_MAJOR_LOW, SOE_ROLE_HIGH, SOE_ROLE_MID,
                    SOE_TECH_SALES, SOE_PURE_SALES, SOE_CORP_A, SOE_CORP_B,
                    SOE_LOCAL_SOE, VALID_WINDOW_DAYS, EXPIRE_SOON_DAYS)


def norm(text):
    return re.sub(r"\s+", "", text or "")


def score_major(text):
    """专业匹配 0-40"""
    t = norm(text)
    if not t:
        return 5, "专业未注明"
    strong = [k for k in SOE_MAJOR_STRONG if k in t]
    if strong:
        return 40, f"专业强匹配（{'/'.join(strong[:3])}）"
    mid = [k for k in SOE_MAJOR_MID if k in t]
    if mid:
        return 26, f"相关专业（{'/'.join(mid[:3])}）"
    if any(k in t for k in SOE_MAJOR_LOW):
        return 16, "专业不限"
    return 6, "标题未含明确专业要求"


def score_corp(text):
    """企业资质 0-30"""
    t = norm(text)
    for k in SOE_CORP_A:
        if k in t:
            return 30, "目标央企/集团及下属"
    for k in SOE_CORP_B:
        if k in t:
            return 22, "其他央企/国企"
    for k in SOE_LOCAL_SOE:
        if k in t:
            return 15, "地方国企"
    return 2, "未识别为央企/国企"


def score_role(text):
    """岗位性质 0-20（拒绝纯销售）"""
    t = norm(text)
    if not t:
        return 8, "岗位未注明"
    sales = [k for k in SOE_PURE_SALES if k in t]
    if sales and not any(k in t for k in SOE_TECH_SALES):
        return 0, "纯销售岗位（已排除）"
    high = [k for k in SOE_ROLE_HIGH if k in t]
    if high:
        return 20, f"核心研发/技术岗（{'/'.join(high[:2])}）"
    if any(k in t for k in SOE_TECH_SALES):
        return 10, "技术型销售"
    mid = [k for k in SOE_ROLE_MID if k in t]
    if mid:
        return 13, f"技术相关岗（{'/'.join(mid[:2])}）"
    return 5, "岗位性质不明确"


def score_region(text):
    """地域匹配 0-10（取标题/地点中出现偏好的最高档）"""
    t = norm(text)
    best, city = 0, ""
    for c, w in SOE_CITY_WEIGHT.items():
        if c in t and w > best:
            best, city = w, c
    if best:
        return best, city
    if "全国" in t:
        return 4, "全国（工作地点以入职分配为准）"
    return 0, "非偏好城市"


def suggestion(score):
    if score >= 90:
        return "强烈关注"
    if score >= 80:
        return "优先投递"
    if score >= 60:
        return "可关注"
    return "一般参考"


def corp_badge(score):
    if score >= 28:
        return "目标央企"
    if score >= 20:
        return "央企/国企"
    if score >= 12:
        return "地方国企"
    return "其他"


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def validity(publish_date, deadline, today):
    """返回 (status, days_left) 与考公轨 check_validity 口径一致"""
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today)
    dl = parse_date(deadline)
    if dl:
        days = (dl - today).days
        if days < 0:
            return "expired", days
        if days <= EXPIRE_SOON_DAYS:
            return "expiring", days
        return "active", days
    pd = parse_date(publish_date)
    if pd:
        days = (pd + datetime.timedelta(days=VALID_WINDOW_DAYS) - today).days
        return ("expired", days) if days < 0 else ("active", days)
    return "active", VALID_WINDOW_DAYS


def score_job(rec):
    """对一条岗位 dict 计算 0-100 及分项，写回 rec 并返回总分"""
    text = f"{rec.get('title')} {rec.get('unit')}"
    loc_text = f"{rec.get('location')} {rec.get('city')} {rec.get('province')} {rec.get('title')}"

    mp, mp_note = score_major(text)
    cp, cp_note = score_corp(text)
    rp, rp_note = score_role(rec.get("title") or "")
    rg, city = score_region(loc_text)
    total = min(100, mp + cp + rp + rg)

    # 纯销售：无论其他维度多高都压到 49 分以下（绝不进入 ≥80 推送、低于入库门槛）
    if rp == 0 and not any(k in norm(text) for k in SOE_TECH_SALES):
        total = min(total, 49)
        rp_note = "纯销售岗位（已排除）"

    parts = [
        ("专业匹配", mp, mp_note, 40),
        ("企业资质", cp, cp_note, 30),
        ("岗位性质", rp, rp_note, 20),
        ("地域匹配", rg, city or "非偏好城市", 10),
    ]
    rec["s_score"] = total
    rec["s_parts"] = [{"dim": d, "pts": p, "note": n, "max": m} for d, p, n, m in parts]
    rec["s_corp_pts"] = cp
    rec["s_badge"] = corp_badge(cp)
    rec["s_city"] = city
    rec["s_suggestion"] = suggestion(total)
    return total
