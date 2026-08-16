"""生成历史记录 HTML：① 每日新增 + ② 历史累计（行内展开详情：匹配说明/薪资/职业要求/政审/备考）"""
import datetime
import html as html_mod
import os

from config import HTML_FILE, PAGES_URL, GRADUATE_DATE


def stars(score):
    score = max(0, min(10, int(score)))
    return "⭐" * max(1, round(score / 2))


def esc(s):
    return html_mod.escape(str(s or ""))


def status_badge(status):
    if status == "expired":
        return '<span class="badge b-red">已过期</span>'
    if status == "expiring":
        return '<span class="badge b-gold">即将截止</span>'
    return '<span class="badge b-green">可报</span>'


def sort_key(job):
    rank = {"expiring": 0, "active": 1, "expired": 2}
    return (rank.get(job.get("status"), 1),
            -int(job.get("score", 0)),
            int(job.get("days_left", 999)))


def render_detail(j):
    blocks = []
    expl = j.get("match_explanation") or []
    if expl:
        li = "".join(f"<li>{esc(x)}</li>" for x in expl)
        blocks.append(f'<div class="d-block"><h4>🎯 与我的匹配度说明</h4><ul class="d-expl">{li}</ul></div>')
    else:
        blocks.append(f'<div class="d-block"><h4>🎯 与我的匹配度说明</h4><p class="d-text">{esc(j.get("match_points") or "已按地域+专业打分推荐")}</p></div>')

    sal = []
    if j.get("salary_detail"):
        sal.append(f"公告待遇：{esc(j['salary_detail'])}")
    if j.get("salary_ref"):
        sal.append(f"同类岗位预估：{esc(j['salary_ref'])}")
    if not sal:
        sal = ["公告未注明薪资，请点击原文查看"]
    blocks.append(f'<div class="d-block"><h4>💰 薪资岗位参考</h4><p class="d-text">{"<br>".join(sal)}</p></div>')

    req = []
    if j.get("recruit_count"):
        req.append(f"招聘人数：{esc(j['recruit_count'])}")
    if j.get("education"):
        req.append(f"学历要求：{esc(j['education'])}")
    if j.get("major_req"):
        req.append(f"专业要求：{esc(j['major_req'])}")
    if j.get("job_requirements"):
        req.append(f"报考条件：{esc(j['job_requirements'])}")
    if not req:
        req = ["公告详情未获取，请点击原文查看岗位表"]
    blocks.append(f'<div class="d-block"><h4>📋 职业要求 / 报考条件</h4><p class="d-text">{"<br>".join(req)}</p></div>')

    bc = j.get("background_check")
    blocks.append(f'<div class="d-block"><h4>🕵️ 政审 / 背调要求</h4><p class="d-text">{esc(bc) if bc else "公告未注明（公务员/事业编招聘通常含政审、考察环节）"}</p></div>')

    subj = j.get("exam_subjects")
    exam = f"考试科目：{esc(subj)}；" if subj else "考试科目：公告未注明；"
    blocks.append(f'<div class="d-block"><h4>📝 考试科目 / 备考建议</h4><p class="d-text">{exam}备考建议：{esc(j.get("exam_advice") or "行测+申论")}</p></div>')

    atts = j.get("attachments") or []
    if atts:
        att_html = "".join(f'<a href="{esc(a)}" target="_blank" rel="noopener">附件{i}</a> ' for i, a in enumerate(atts[:5], 1))
    else:
        att_html = "无"
    blocks.append(f'<div class="d-block"><h4>📎 岗位表附件 / 公告原文</h4><p class="d-text">附件：{att_html}<br><a href="{esc(j.get("link"))}" target="_blank" rel="noopener">点击查看公告原文</a></p></div>')
    return "".join(blocks)


def render_row(j):
    deadline = j.get("deadline") or "详见公告"
    if j.get("status") == "active" and not j.get("deadline"):
        deadline = f"约 {j.get('days_left', '')} 天后推定失效"
    days = j.get("days_left", "")
    if j.get("status") == "expired":
        days = "已截止"
    else:
        days = f"{days} 天"
    summary = f"""\
      <tr class="s-row {esc(j.get('status', 'active'))}">
        <td class="score"><div class="sc-num">{esc(j.get('score'))}</div><div class="sc-star">{stars(j.get('score', 0))}</div><div class="sc-sug">{esc(j.get('suggestion'))}</div></td>
        <td class="t-title"><a href="{esc(j.get('link'))}" target="_blank" rel="noopener">{esc(j.get('title'))}</a></td>
        <td>{esc(j.get('unit') or '—')}</td>
        <td>{esc(j.get('location') or (j.get('city') or '—'))}<br><span class="tag-p">{esc(j.get('region_label'))}</span></td>
        <td>{esc(j.get('education') or '详见公告')}</td>
        <td>{esc(j.get('major_req') or '—')}</td>
        <td>{esc(deadline)}<br><span class="days">{esc(days)}</span></td>
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

    daily = sorted([j for j in jobs if j.get("fetched_at") == today], key=sort_key)
    cumulative = sorted(jobs, key=sort_key)

    if daily:
        daily_rows = "".join(render_row(j) for j in daily)
        daily_note = f"今日（{esc(today)}）新发现匹配岗位 <b>{len(daily)}</b> 个"
    else:
        daily_rows = '<tr><td colspan="9" class="empty">今日无新增匹配岗位</td></tr>'
        daily_note = f"今日（{esc(today)}）暂未发现新的匹配岗位"

    cumulative_rows = "".join(render_row(j) for j in cumulative)

    pages = PAGES_URL
    pages_note = f'<a href="{esc(pages)}" target="_blank" rel="noopener">{esc(pages)}</a>' if pages \
        else "未配置 PAGES_URL，请在 GitHub Actions 运行结果 → Artifacts 中下载 history.html 查看"

    today_disp = today if today else datetime.date.today().isoformat()
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>考公岗位智能匹配汇总（生物医学硕士）</title>
<style>
  :root{{--blue-900:#0d3a6e;--blue-600:#1a63b8;--blue-500:#2e7fd0;--blue-100:#e7f1fb;--ink:#243447;--muted:#5b6b7f;--line:#dce6f2;}}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:linear-gradient(180deg,#eef5fc 0%,#f7fafe 180px,#fff 100%);line-height:1.7;}}
  .wrap{{max-width:1200px;margin:0 auto;padding:0 16px;}}
  header{{background:linear-gradient(135deg,var(--blue-900) 0%,var(--blue-600) 60%);color:#fff;padding:36px 20px;text-align:center;}}
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
  tbody tr.expired{{opacity:.55;}}
  .score{{text-align:center;}}
  .sc-num{{font-size:1.3rem;font-weight:800;color:var(--blue-600);}}
  .sc-star{{font-size:.8rem;letter-spacing:1px;}}
  .sc-sug{{font-size:.7rem;color:var(--blue-500);background:var(--blue-100);border-radius:6px;display:inline-block;padding:1px 6px;margin-top:2px;}}
  .t-title a{{color:var(--blue-600);text-decoration:none;font-weight:600;}}
  .t-title a:hover{{text-decoration:underline;}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:700;white-space:nowrap;}}
  .b-green{{background:#eaf7ef;color:#1e8449;}}
  .b-gold{{background:#fdf6e3;color:#b8860b;}}
  .b-red{{background:#fdeceb;color:#c0392b;}}
  .tag-p{{display:inline-block;font-size:.72rem;color:var(--blue-600);background:var(--blue-100);padding:1px 8px;border-radius:6px;margin-top:3px;}}
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
  <h1>考公岗位智能匹配汇总</h1>
  <p>目标：生物医学硕士 · 2027 届应届（{esc(GRADUATE_DATE)}毕业） · 生源地甘肃天水</p>
  <div class="stats">
    <div class="stat">🆕 今日新增：<b>{len(daily)}</b> 个</div>
    <div class="stat">📋 历史累计：<b>{len(jobs)}</b> 个</div>
    <div class="stat">✅ 当前可报：<b>{active}</b> 个</div>
    <div class="stat">🗓️ 更新：{esc(today_disp)}</div>
  </div>
</header>
<main class="wrap">

  <div class="card">
    <div class="card-head">
      <span class="dot"></span>
      <h2>① 每日新增匹配岗位</h2>
      <span class="tag-n">{daily_note}</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr><th>匹配度</th><th>岗位名称</th><th>招录单位</th><th>工作地点</th><th>学历要求</th><th>专业要求</th><th>报名截止</th><th>状态</th><th></th></tr>
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
      <h2>② 历史累计匹配岗位</h2>
      <span class="tag-n">共 {len(jobs)} 条 · 可报/即将截止优先 → 匹配度降序 · 点"详情"看薪资/条件/政审</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr><th>匹配度</th><th>岗位名称</th><th>招录单位</th><th>工作地点</th><th>学历要求</th><th>专业要求</th><th>报名截止</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
{cumulative_rows}
        </tbody>
      </table>
    </div>
  </div>

  <p style="margin-top:6px;color:#5b6b7f;font-size:.9rem;">匹配度 = 地域权重(天水/西安+3，甘肃其他/陕西其他+1，外省+0) + 专业匹配(生物医学类+5，通用类+2)。</p>
  <p style="margin-top:6px;color:#5b6b7f;font-size:.9rem;">📊 在线预览：{pages_note}</p>
</main>
<footer>本页由每日自动监控脚本生成 · 数据以官方公告为准 · 仅供参考</footer>
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
    os.makedirs(os.path.dirname(HTML_FILE), exist_ok=True)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[generate_html] 已生成 {HTML_FILE}（今日新增 {len(daily)}，累计 {len(jobs)}）", flush=True)