"""生成国企/央企轨道历史页 site/guoqi_history.html（结构与考公 history.html 保持一致）"""
import datetime
import html as html_mod
import os

from config import SOE_HTML_FILE, SOE_GRADUATE

CORP_COLORS = {
    "目标央企": "t1", "央企/国企": "t2", "地方国企": "t3", "其他": "t4",
}
DIM_ICON = {"专业匹配": "🎓", "企业资质": "🏭", "岗位性质": "💼", "地域匹配": "📍"}


def esc(s):
    return html_mod.escape(str(s or ""))


def status_badge(status):
    if status == "expired":
        return '<span class="badge b-red">已过期</span>'
    if status == "expiring":
        return '<span class="badge b-gold">即将截止</span>'
    return '<span class="badge b-green">可报</span>'


def corp_badge(j):
    b = j.get("s_badge") or "其他"
    return f'<span class="t-tier {CORP_COLORS.get(b, "t4")}">{esc(b)}</span>'


def sort_key(j):
    rank = {"expiring": 0, "active": 1, "expired": 2}
    return (-1 * (1 if j.get("status") != "expired" else 0),
            rank.get(j.get("status"), 1),
            -int(j.get("s_score", 0)),
            int(j.get("days_left", 999)))


def render_detail(j):
    blocks = []
    parts = j.get("s_parts") or []
    if parts:
        lis = "".join(
            f'<li>{DIM_ICON.get(p.get("dim", ""), "•")} {esc(p.get("dim"))}：'
            f'<b>{p.get("pts", 0)}/{p.get("max", 0)}</b> —— {esc(p.get("note") or "")}</li>'
            for p in parts)
        blocks.append(f'<div class="d-block"><h4>🎯 评分构成（0-100）</h4>'
                      f'<ul class="d-expl">{lis}</ul></div>')
    req = []
    if j.get("education"):
        req.append(f"学历要求：{esc(j['education'])}")
    if j.get("major_req"):
        req.append(f"专业要求：{esc(j['major_req'])}")
    if not req:
        req = ["公告未标注，请点击原文核对岗位表"]
    blocks.append(f'<div class="d-block"><h4>📋 学历 / 专业</h4>'
                  f'<p class="d-text">{"<br>".join(req)}</p></div>')

    dl = j.get("deadline")
    blocks.append(f'<div class="d-block"><h4>⏳ 报名时间</h4>'
                  f'<p class="d-text">{esc(dl) if dl else "公告未注明，建议尽早关注"}</p></div>')
    blocks.append(f'<div class="d-block"><h4>📎 公告原文</h4>'
                  f'<p class="d-text"><a href="{esc(j.get("link"))}" target="_blank" rel="noopener">点击查看（{esc(j.get("source"))}）</a></p></div>')
    return "".join(blocks)


def render_row(j):
    deadline = j.get("deadline") or "详见公告"
    days = j.get("days_left", "")
    days_txt = "已截止" if j.get("status") == "expired" else (f"{days} 天" if days != "" else "")
    sug = j.get("s_suggestion") or ""
    loc = j.get("s_city") or (j.get("city") or j.get("location") or "—")
    hi = int(j.get("s_score", 0)) >= 80
    summary = f"""\
      <tr class="s-row{' hot' if hi else ''} {esc(j.get('status', 'active'))}">
        <td class="score"><div class="sc-num">{esc(j.get('s_score', 0))}</div><div class="sc-sug">{esc(sug)}</div></td>
        <td>{corp_badge(j)}</td>
        <td class="t-title"><a href="{esc(j.get('link'))}" target="_blank" rel="noopener">{esc(j.get('title'))}</a><br><span class="tag-p">{esc(j.get('source'))}</span></td>
        <td>{esc(j.get('unit') or '—')}</td>
        <td>{esc(loc)}</td>
        <td>{esc(j.get('education') or '—')}</td>
        <td>{esc(deadline)}<br><span class="days">{esc(days_txt)}</span></td>
        <td>{status_badge(j.get('status'))}</td>
        <td class="c-detail"><button class="tgl" onclick="tg(this)">详情 ▾</button></td>
      </tr>"""
    detail = f"""\
      <tr class="d-row">
        <td colspan="9"><div class="d-panel">{render_detail(j)}</div></td>
      </tr>"""
    return summary + detail


def render(history, today):
    jobs = history["jobs"]
    active = sum(1 for j in jobs if j.get("status") != "expired")
    ge80 = sum(1 for j in jobs if int(j.get("s_score", 0)) >= 80)

    daily = sorted([j for j in jobs if j.get("fetched_at") == today], key=sort_key)
    cumulative = sorted(jobs, key=sort_key)

    if daily:
        daily_rows = "".join(render_row(j) for j in daily)
        daily_note = f"今日（{esc(today)}）新发现 <b>{len(daily)}</b> 个 ≥0 分岗位"
    else:
        daily_rows = '<tr><td colspan="9" class="empty">今日暂无新增国企/央企岗位</td></tr>'
        daily_note = f"今日（{esc(today)}）暂未发现新的匹配岗位"

    cumulative_rows = "".join(render_row(j) for j in cumulative)
    if not jobs:
        guide = """
  <div class="card" style="padding:18px 22px;border-left:4px solid var(--blue-500);">
    <p style="font-size:.92rem;color:var(--muted);">
      📡 目前抓取渠道：国聘网、国药/中国电科/中国电子/中核/通用技术集团官网、事业单位招聘网与高校人才网全量二次筛选。
      <br>多数央企校招系统为 JS 应用且屏蔽海外/无头请求，海外 GitHub runner 与国内网络差异较大，内容会随渠道可达性逐步累积；评分 ≥80 分即触发微信推送。
    </p>
  </div>
"""
    else:
        guide = ""
    today_disp = today if today else datetime.date.today().isoformat()

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>国企/央企岗位智能匹配汇总（生物医学工程）</title>
<style>
  :root{{--blue-900:#0d3a6e;--blue-600:#1a63b8;--blue-500:#2e7fd0;--blue-100:#e7f1fb;--ink:#243447;--muted:#5b6b7f;--line:#dce6f2;}}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:linear-gradient(180deg,#eef5fc 0%,#f7fafe 180px,#fff 100%);line-height:1.7;}}
  .wrap{{max-width:1200px;margin:0 auto;padding:0 16px;}}
  header{{background:linear-gradient(135deg,#0a3d5c 0%,#14539e 60%);color:#fff;padding:36px 20px;text-align:center;}}
  header h1{{font-size:clamp(1.3rem,3.5vw,2rem);letter-spacing:1px;}}
  header p{{opacity:.92;margin-top:8px;font-size:.95rem;}}
  .stats{{display:flex;gap:12px;justify-content:center;margin-top:16px;flex-wrap:wrap;}}
  .stat{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:12px;padding:8px 18px;font-size:.9rem;}}
  main{{padding:24px 0 40px;}}
  .card{{background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(20,83,158,.10);border:1px solid #eef3fa;overflow:hidden;margin-bottom:26px;}}
  .card-head{{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#f0f6fd,#fff);}}
  .card-head .dot{{flex:0 0 auto;width:10px;height:10px;border-radius:50%;background:var(--blue-500);box-shadow:0 0 0 4px rgba(26,99,184,.15);}}
  .card-head h2{{font-size:1.15rem;color:var(--blue-900);}}
  .card-head .tag-n{{margin-left:auto;font-size:.8rem;color:var(--blue-600);background:var(--blue-100);padding:3px 12px;border-radius:999px;}}
  .empty{{text-align:center;color:var(--muted);padding:26px 0;font-size:.95rem;}}
  .tbl-wrap{{overflow-x:auto;}}
  table{{width:100%;border-collapse:collapse;min-width:980px;font-size:.9rem;}}
  thead th{{background:linear-gradient(135deg,#14539e,var(--blue-600));color:#fff;padding:12px 12px;text-align:left;white-space:nowrap;position:sticky;top:0;}}
  tbody td{{padding:12px;border-top:1px solid var(--line);vertical-align:top;}}
  tbody tr:nth-child(even){{background:#f3f8fd;}}
  tbody tr.s-row:hover{{background:#e9f3fd;}}
  tbody tr.hot{{background:#f4fbf7 !important;}}
  tbody tr.hot:hover{{background:#e6f6ee !important;}}
  tbody tr.expired{{opacity:.55;}}
  .score{{text-align:center;}}
  .sc-num{{font-size:1.3rem;font-weight:800;color:var(--blue-600);}}
  .sc-sug{{font-size:.7rem;color:#178a4d;background:#e6f7ee;border-radius:6px;display:inline-block;padding:1px 6px;margin-top:2px;}}
  .t-title a{{color:var(--blue-600);text-decoration:none;font-weight:600;}}
  .t-title a:hover{{text-decoration:underline;}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:700;white-space:nowrap;}}
  .b-green{{background:#eaf7ef;color:#1e8449;}}
  .b-gold{{background:#fdf6e3;color:#b8860b;}}
  .b-red{{background:#fdeceb;color:#c0392b;}}
  .tag-p{{display:inline-block;font-size:.72rem;color:var(--muted);background:#eef1f5;padding:1px 8px;border-radius:6px;margin-top:3px;}}
  .t-tier{{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:700;white-space:nowrap;}}
  .t1{{background:#dceeff;color:#0a5cb8;}}
  .t2{{background:#e6f7ee;color:#178a4d;}}
  .t3{{background:#fdf3e7;color:#b26a00;}}
  .t4{{background:#f0f0f4;color:#6b7686;}}
  .days{{font-size:.75rem;color:var(--muted);}}
  .c-detail{{text-align:center;white-space:nowrap;}}
  .tgl{{border:1px solid var(--blue-500);color:var(--blue-600);background:#fff;border-radius:8px;padding:5px 12px;font-size:.8rem;cursor:pointer;transition:.2s;}}
  .tgl:hover{{background:var(--blue-600);color:#fff;}}
  .d-row{{display:none;background:#f7fbfe !important;}}
  .d-row.show{{display:table-row;}}
  .d-panel{{padding:14px 18px;}}
  .d-block{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:10px;}}
  .d-block h4{{font-size:.92rem;color:var(--blue-900);margin-bottom:6px;}}
  .d-text{{font-size:.88rem;color:var(--ink);word-break:break-word;}}
  .d-text a{{color:var(--blue-600);}}
  .d-expl{{list-style:none;margin:0;padding:0;}}
  .d-expl li{{font-size:.88rem;padding:3px 0 3px 0;color:var(--ink);}}
  footer{{text-align:center;padding:24px 16px;color:var(--muted);font-size:.85rem;}}
  @media(max-width:640px){{header{{padding:28px 12px;}} .card-head{{flex-wrap:wrap;}} .card-head .tag-n{{margin-left:0;}}}}
</style>
</head>
<body>
<header>
  <h1>国企 / 央企岗位智能匹配汇总</h1>
  <p>目标：北京工业大学 · 生物医学工程 · {esc(SOE_GRADUATE)} 应届 · 偏好 北京>沪苏沈杭深>天水/西安</p>
  <div class="stats">
    <div class="stat">🆕 今日新增：<b>{len(daily)}</b> 个</div>
    <div class="stat">📋 历史累计：<b>{len(jobs)}</b> 个</div>
    <div class="stat">✅ ≥80 分：<b>{ge80}</b> 个</div>
    <div class="stat">✅ 当前可报：<b>{active}</b> 个</div>
    <div class="stat">🗓️ 更新：{esc(today_disp)}</div>
  </div>
</header>
<main class="wrap">
{guide}
  <div class="card">
    <div class="card-head">
      <span class="dot"></span>
      <h2>① 每日新增国企/央企岗位</h2>
      <span class="tag-n">{daily_note}</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr><th>评分(0-100)</th><th>类别</th><th>岗位</th><th>单位/集团</th><th>偏好地点</th><th>学历</th><th>报名截止</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
{daily_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="dot"></span>
      <h2>② 历史累计国企/央企岗位</h2>
      <span class="tag-n">共 {len(jobs)} 条 · ≥80 分优先，可报优先，分数降序 · 绿色行为 ≥80 分</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr><th>评分(0-100)</th><th>类别</th><th>岗位</th><th>单位/集团</th><th>偏好地点</th><th>学历</th><th>报名截止</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
{cumulative_rows}
        </tbody>
      </table>
    </div>
  </div>

  <p style="margin-top:6px;color:#5b6b7f;font-size:.9rem;">评分 = 专业匹配(0-40) + 企业资质(0-30) + 岗位性质(0-20) + 地域匹配(0-10)。≥80 分每日微信推送。</p>
</main>
<footer>本页由每日自动监控脚本生成 · 数据来自各集团官网/国聘网/就业平台 · 以官方公告为准 · 仅供参考</footer>
<script>
function tg(btn){{
  var tr = btn.closest('tr');
  var next = tr.nextElementSibling;
  if (next && next.classList.contains('d-row')) {{
    next.classList.toggle('show');
    btn.textContent = next.classList.contains('show') ? '详情 ▴' : '详情 ▾';
  }}
}}
</script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(SOE_HTML_FILE), exist_ok=True)
    with open(SOE_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[soe_html] 已生成 {SOE_HTML_FILE}（今日新增 {len(daily)}，累计 {len(jobs)}）", flush=True)
