"""地域加权 + 专业匹配打分 + 时效判断 + 备考/薪酬生成"""
import datetime
import re

from config import (
    CIVIL_SERVER_KEYWORDS,
    CIVIL_SERVER_SOURCES,
    EXPIRE_SOON_DAYS,
    GANSUN,
    GENERAL_MAJOR_KEYWORDS,
    NON_ESTABLISHMENT_KEYWORDS,
    PUBLIC_INST_KEYWORDS,
    PUBLIC_INST_SOURCES,
    PUBLIC_INST_UNIT_KEYWORDS,
    REGION_HIGH,
    REGION_LOW,
    REGION_MED,
    SHAANXI,
    STRONG_MAJOR_KEYWORDS,
    VALID_WINDOW_DAYS,
)

PROVINCES = ["北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林",
             "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
             "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
             "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆"]

CITY_MAP = {
    "甘肃": ["兰州", "天水", "白银", "金昌", "嘉峪关", "武威", "张掖", "平凉",
             "庆阳", "酒泉", "定西", "陇南", "临夏", "甘南"],
    "陕西": ["西安", "宝鸡", "咸阳", "铜川", "渭南", "延安", "榆林", "汉中",
             "安康", "商洛"],
    "四川": ["成都", "绵阳", "德阳", "南充", "宜宾", "泸州", "自贡", "攀枝花",
             "广元", "乐山", "雅安", "遂宁", "内江", "资阳", "达州", "巴中", "眉山"],
    "山东": ["济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁",
             "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽"],
    "江苏": ["南京", "苏州", "无锡", "常州", "南通", "徐州", "扬州", "镇江",
             "泰州", "盐城", "淮安", "连云港", "宿迁"],
    "浙江": ["杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州",
             "舟山", "台州", "丽水"],
    "广东": ["广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆",
             "江门", "茂名", "惠州", "梅州", "东莞", "中山", "潮州"],
    "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "新乡", "焦作", "南阳",
             "商丘", "信阳", "周口", "驻马店"],
    "河北": ["石家庄", "唐山", "秦皇岛", "邯郸", "保定", "张家口", "承德",
             "沧州", "廊坊", "衡水"],
    "湖南": ["长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "益阳",
             "郴州", "永州", "怀化"],
    "湖北": ["武汉", "黄石", "十堰", "宜昌", "襄阳", "荆州", "荆门", "孝感",
             "黄冈", "咸宁", "随州"],
}

DATE_RE = re.compile(r"(\d{4})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*[日号]?")


def _norm_province(province):
    province = (province or "").strip()
    return province[:-1] if province.endswith("省") and len(province) > 2 else province


def _norm_city(city):
    city = (city or "").strip()
    return city[:-1] if city.endswith("市") and len(city) > 1 else city


def _earliest(text, candidates):
    best = None
    for candidate in candidates:
        idx = text.find(candidate)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, candidate)
    return best[1] if best else ""


def parse_location(text):
    text = text or ""
    province = _earliest(text, PROVINCES)
    city = ""
    if province in CITY_MAP:
        city = _earliest(text, CITY_MAP[province])
    if not province and not city:
        for p, cities in CITY_MAP.items():
            city = _earliest(text, cities)
            if city:
                province = p
                break
    return province, city


def region_info(province, city):
    province, city = _norm_province(province), _norm_city(city)
    if province == GANSUN and city == "天水":
        return REGION_HIGH, "高（天水本地）"
    if province == SHAANXI and city == "西安":
        return REGION_HIGH, "高（西安本地）"
    if province == GANSUN:
        return REGION_MED, "中（甘肃省内）"
    if province == SHAANXI:
        return REGION_MED, "中（陕西省内）"
    return REGION_LOW, "普通（外省）"


def major_score(text):
    text = text or ""
    hits = [k for k in STRONG_MAJOR_KEYWORDS if k in text]
    if hits:
        return 5, hits, "strong"
    hits = [k for k in GENERAL_MAJOR_KEYWORDS if k in text]
    if hits:
        return 2, hits, "general"
    return 0, [], "none"


def parse_date(s):
    if not s:
        return None
    text = re.sub(r"\s+", "", str(s).strip())
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def check_validity(publish_date, deadline, today, fallback_date=""):
    """判断时效：明确截止日期优先；否则用发布日期，再否则用首次发现日期。"""
    if isinstance(today, str):
        today = parse_date(today) or datetime.date.today()
    dl = parse_date(deadline)
    if dl:
        days = (dl - today).days
        if days < 0:
            return "expired", days
        if days <= EXPIRE_SOON_DAYS:
            return "expiring", days
        return "active", days
    pd = parse_date(publish_date) or parse_date(fallback_date)
    if pd:
        expiry = pd + datetime.timedelta(days=VALID_WINDOW_DAYS)
        days = (expiry - today).days
        if days < 0:
            return "expired", days
        return "active", days
    return "active", VALID_WINDOW_DAYS


def build_match_points(job, major_hits, major_kind):
    parts = []
    if major_kind == "strong":
        parts.append(f"专业强匹配（{'/'.join(major_hits[:3])}）")
    elif major_kind == "general":
        parts.append(f"通用匹配（{'/'.join(major_hits[:3])}）")
    if job.province in (GANSUN, SHAANXI):
        if job.city in ("天水", "西安"):
            parts.append(f"地域优势（{job.city}本地）")
        else:
            parts.append(f"省内岗位（{job.province}省）")
    if job.city:
        parts.append(f"工作地点：{job.city}")
    return " + ".join(parts) if parts else "基础匹配"


def get_exam_advice(job):
    # 招聘单位/栏目名不参与专业判断，避免“医学人才”栏目污染所有岗位
    text = (job.title or "") + (job.major_req or "")
    if any(k in text for k in ("卫健委", "医院", "疾控", "卫生", "医疗", "医学", "卫生院", "保健院")):
        return "职测（E类）+ 综合应用能力（E类·医学基础知识）"
    if any(k in text for k in ("公务员", "选调", "省考", "国考")) or job.source in ("国家公务员局", "甘肃组工网"):
        return "行测 + 申论（行政执法类 / 副省级）"
    if job.major_kind == "general":
        return "职测 + 综合应用能力（A类·综合管理）"
    return "职测 + 综合应用能力（按岗位类别 A/B/C/D/E）"


def get_salary_ref(job):
    if job.province == GANSUN and job.city == "天水":
        base = "转正后月到手约 4k-5k，公积金双边约 1k"
    elif job.province == GANSUN:
        base = "转正后月到手约 4k-5k"
    elif job.province == SHAANXI and job.city == "西安":
        base = "转正后月到手约 5k-7k，公积金双边约 1.5k"
    elif job.province == SHAANXI:
        base = "转正后月到手约 4.5k-6k"
    elif job.source in ("国家公务员局", "甘肃组工网"):
        base = "公务员月到手较事业编高约 1k，公积金更高"
    else:
        base = "转正后月到手约 5k-7k（参考当地水平）"
    return base + "，仅供参考"


def suggestion(score):
    if score >= 8:
        return "优先关注"
    if score >= 5:
        return "重点关注"
    if score >= 2:
        return "一般关注（可备选）"
    return "仅作参考"


def build_match_explanation(job):
    lines = []
    if job.region_score == REGION_HIGH:
        lines.append(f"地域：{job.location or job.city or '天水/西安'} → +{REGION_HIGH}（天水/西安本地优先）")
    elif job.region_score == REGION_MED:
        lines.append(f"地域：{job.province}（{job.city or '省内'}）→ +{REGION_MED}（省内岗位）")
    else:
        lines.append(f"地域：{job.province or '全国'}{job.city or ''} → +{REGION_LOW}（外省，专业匹配仍推荐）")
    if job.major_kind == "strong":
        lines.append(f"专业：命中『{'/'.join(job.major_hits[:3])}』→ +5（生物医学类强匹配）")
    elif job.major_kind == "general":
        lines.append(f"专业：命中『{'/'.join(job.major_hits[:3])}』→ +2（通用匹配）")
    else:
        lines.append("专业：标题未命中关键词 → +0（建议点开公告核对具体专业要求）")
    edu = job.education or ""
    if "硕士" in edu or "研究生" in edu:
        lines.append("学历：硕士 ≥ 岗位要求 → 适配")
    elif edu:
        lines.append(f"学历：岗位要求『{edu}』→ 硕士通常适配")
    else:
        lines.append("学历：公告未注明 → 硕士一般可报（以岗位表为准）")
    lines.append(f"结论：总分 {job.score} → {suggestion(job.score)}")
    return lines


def infer_types(title, unit="", source=""):
    """判定岗位类型档位：1=公务员 2=事业编制 3=其他
    判定顺序：非编词 → 公务员 → 事业编 → 其他（source 启发）"""
    text = f"{title or ''} {unit or ''}"
    for kw in NON_ESTABLISHMENT_KEYWORDS:
        if kw in text:
            return 3, "其他"
    if source in CIVIL_SERVER_SOURCES:
        return 1, "公务员"
    for kw in CIVIL_SERVER_KEYWORDS:
        if kw in (title or ""):
            return 1, "公务员"
    if source in PUBLIC_INST_SOURCES:
        return 2, "事业编制"
    for kw in PUBLIC_INST_KEYWORDS:
        if kw in text:
            return 2, "事业编制"
    if any(k in text for k in PUBLIC_INST_UNIT_KEYWORDS):
        return 2, "事业编制"
    return 3, "其他"


def enrich(job, today, fallback_date=""):
    if isinstance(today, str):
        today = parse_date(today) or datetime.date.today()

    if not job.province or not job.city:
        p, c = parse_location((job.location or "") + (job.title or "") + (job.unit or ""))
        if not job.province:
            job.province = p
        if not job.city:
            job.city = c
        if not job.location:
            job.location = f"{job.province}{job.city}".strip()
    job.province = _norm_province(job.province)
    job.city = _norm_city(job.city)

    # 标题里的日期可能是考试日期而非发布日期；不允许未来日期把岗位“续命”
    publish = parse_date(job.publish_date)
    if publish and publish > today:
        job.publish_date = today.isoformat()

    region_score, region_label = region_info(job.province, job.city)
    # 只对标题+岗位专业要求打分；unit/category 是展示字段，不参与专业匹配
    ms, hits, kind = major_score((job.title or "") + (job.major_req or ""))

    job.region_score = region_score
    job.region_label = region_label
    job.major_score = ms
    job.major_kind = kind
    job.major_hits = hits
    job.score = region_score + ms

    job.match_points = build_match_points(job, hits, kind)
    job.exam_advice = get_exam_advice(job)
    job.salary_ref = get_salary_ref(job)
    job.match_explanation = build_match_explanation(job)
    job.suggestion = suggestion(job.score)

    status, days = check_validity(job.publish_date, job.deadline, today, fallback_date)
    job.status = status
    job.days_left = days

    job.tier, job.job_type = infer_types(job.title, job.unit, job.source)
