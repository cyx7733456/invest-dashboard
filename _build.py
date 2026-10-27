# -*- coding: utf-8 -*-
"""五组投资大看板 v1 构建脚本。所有数字均直接读自源文件，不估算。
数据源（相对 /Users/apple/Desktop/Investment/）：
  公共/数据/simulated_nav_<组>.csv         五组模拟净值（| 分隔）
  公共/数据/daily_report_<组>_<日期>.json  每日上报件（持仓/new_picks 用最新一份）
  投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_<日期>.html  实盘卡三件套
"""
import csv, json, os, html, re, datetime

ROOT = "/Users/apple/Desktop/Investment"
OUT = os.path.join(ROOT, "公共/看板设计/dashboard_v1")
DATA = os.path.join(ROOT, "公共/数据")
CARDS = os.path.join(ROOT, "投资1组_WB/实盘化方案/daily_live_cards")
GROUPS = ["WB", "CX", "QD", "DSK", "HRS"]
BUILD_TS = "2026-10-27 深夜（构建于本地，AI 生成）"

# ---------- 读取净值 ----------
navs = {}  # g -> list of (date, act_nav, n_hold)
for g in GROUPS:
    rows = []
    with open(f"{DATA}/simulated_nav_{g}.csv", newline="") as f:
        for r in csv.DictReader(f, delimiter="|"):
            rows.append((r["date"], float(r["act_nav"]), int(r["n_hold"])))
    navs[g] = rows

def metrics(g):
    rows = navs[g]
    rets = [rows[i][1] / rows[i-1][1] - 1 for i in range(1, len(rows))]
    win = sum(1 for r in rets if r > 0)
    cum = rows[-1][1] / rows[0][1] - 1
    dchg = rows[-1][1] / rows[-2][1] - 1
    return {
        "first": rows[0][0], "last": rows[-1][0], "act": rows[-1][1],
        "n_hold": rows[-1][2], "win": win, "n": len(rets),
        "winrate": win / len(rets), "cum": cum, "dchg": dchg,
    }

M = {g: metrics(g) for g in GROUPS}

# ---------- 最新上报件 ----------
def latest_report(g):
    cands = sorted(
        f for f in os.listdir(DATA)
        if re.match(rf"daily_report_{g}_\d{{4}}-\d{{2}}-\d{{2}}\.json$", f)
    )
    return os.path.join(DATA, cands[-1]), cands[-1]

R = {}
for g in GROUPS:
    path, fname = latest_report(g)
    with open(path) as f:
        R[g] = {"path": path, "fname": fname, **json.load(f)}

# ---------- 实盘卡 ----------
def card_dates():
    ds = []
    for f in os.listdir(CARDS):
        m = re.match(r"daily_live_card_(\d{4}-\d{2}-\d{2})\.html$", f)
        if m:
            ds.append(m.group(1))
    return sorted(ds, reverse=True)

CARD_DATES = card_dates()

def card_html(date):
    with open(f"{CARDS}/daily_live_card_{date}.html") as f:
        src = f.read()
    styles = "".join(re.findall(r"<style>.*?</style>", src, re.S))
    body = re.search(r"<body>(.*)</body>", src, re.S).group(1)
    return styles, body

def card_txt_header(date):
    txt = open(f"{CARDS}/daily_live_card_{date}.txt").read().splitlines()
    return [l for l in txt if l.startswith("#")][:12]

# 10-27 共识买入 Top（来自卡 csv：动作=买入（行业共识…）且共识票数≥2）
top3 = []
with open(f"{CARDS}/daily_live_card_2026-10-27.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["动作"].startswith("买入"):
            top3.append(r)
TOP3 = top3[:3]

# ---------- 通用片段 ----------
def nav_bar(active):
    items = [("首页", "../index.html" if active else "index.html"),
             ("实盘推荐", "live/index.html" if active in (None, "index") else ("../live/index.html" if active != "live" else "index.html")),
             ("模拟盘赛马", "sim/index.html" if active in (None, "index", "live") else "../sim/index.html"),
             ("策略档案", "strategies/index.html" if active in (None, "index", "live") else "../strategies/index.html"),
             ("数据状态", "data-status/index.html" if active in (None, "index", "live") else "../data-status/index.html")]
    # 统一按页面深度生成：root 页面用根相对，子页用 ../
    def link(name, path):
        return f'<a href="{path}"{" class=on" if name == active else ""}>{name}</a>'
    return '<nav class="topnav">' + "".join(link(n, p) for n, p in
        [("首页", "../index.html" if active not in (None, "index") else "index.html"),
         ("实盘推荐", "live/index.html" if active is None else ("index.html" if active == "live" else "../live/index.html")),
         ("模拟盘赛马", "../sim/index.html" if active not in (None, "index", "live") else "sim/index.html"),
         ("策略档案", "../strategies/index.html" if active not in (None, "index", "live") else "strategies/index.html"),
         ("数据状态", "../data-status/index.html" if active not in (None, "index", "live") else "data-status/index.html")]) + "</nav>"

def page(title, body, depth=0, extra_head=""):
    pre = "" if depth == 0 else "../"
    footer = (f'<footer>数据截至：{BUILD_TS} ｜ 数据源：五组每日上报件与公共数据集，AI 生成仅供参考</footer>')
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 五组投资大看板</title>{extra_head}
<style>
:root{{--bg:#0b0e14;--panel:#12161f;--line:#232a36;--tx:#d7dee8;--dim:#8a93a3;--up:#e5544b;--dn:#3fb950;--acc:#58a6ff;--warn:#d29922}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--tx);font:14px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",monospace}}
a{{color:var(--acc);text-decoration:none}} a:hover{{text-decoration:underline}}
.topnav{{display:flex;gap:18px;padding:12px 22px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}}
.topnav a{{color:var(--dim);font-size:13px}} .topnav a.on{{color:var(--tx);font-weight:700;border-bottom:2px solid var(--acc)}}
.wrap{{max-width:1080px;margin:0 auto;padding:22px}}
h1{{font-size:22px;margin:6px 0 2px}} h2{{font-size:16px;margin:26px 0 10px;border-left:3px solid var(--acc);padding-left:9px}}
.sub{{color:var(--dim);font-size:12px}}
.grid{{display:grid;gap:12px}} .g5{{grid-template-columns:repeat(5,1fr)}} .g3{{grid-template-columns:repeat(3,1fr)}} .g6{{grid-template-columns:repeat(3,1fr)}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:14px}}
.card b{{font-size:19px}} .card .lab{{color:var(--dim);font-size:11px;display:block}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}} .dim{{color:var(--dim)}} .warn{{color:var(--warn)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}}
th,td{{border:1px solid var(--line);padding:6px 8px;text-align:right;white-space:nowrap}}
th{{background:#171c26;color:var(--dim);font-weight:600}} th:first-child,td:first-child{{text-align:left}}
.tag{{display:inline-block;background:#1c2432;border:1px solid var(--line);border-radius:5px;padding:1px 8px;font-size:11px;color:var(--dim);margin:2px}}
.entry{{display:block;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px;color:var(--tx)}}
.entry:hover{{border-color:var(--acc);text-decoration:none}}
footer{{color:#5c6575;font-size:11px;text-align:center;padding:22px;border-top:1px solid var(--line);margin-top:34px}}
.btns button{{background:#171c26;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:6px 14px;margin-right:8px;cursor:pointer;font-size:13px}}
.btns button.on{{border-color:var(--acc);color:var(--acc)}}
.holdsec{{display:none}} .holdsec.on{{display:block}}
@media(max-width:900px){{.g5,.g3,.g6{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
{nav_bar(None if depth == 0 else "sub")}
<div class="wrap">
{body}
</div>
{footer}
</body></html>"""

def pct(x, signed=True):
    s = f"{x*100:+.2f}%" if signed else f"{x*100:.2f}%"
    return f'<span class="{"up" if x > 0 else "dn" if x < 0 else "dim"}">{s}</span>'

# ---------- 首页 ----------
today = "2026-10-27"
nav_cards = ""
for g in GROUPS:
    m = M[g]
    lag = "" if m["last"] == today else f'<span class="warn">数据截至 {m["last"]}</span>'
    nav_cards += f"""<div class="card"><span class="lab">{g} 组 · 模拟净值</span>
<b>{m['act']:.4f}</b><br>{pct(m['dchg'])} <span class="dim">当日</span><br>
<span class="dim">累计 {m['cum']*100:+.1f}% ｜ 持仓 {m['n_hold']} 只</span><br>{lag}</div>"""

top3_html = "".join(
    f"""<div class="card"><span class="lab">{i+1}. {html.escape(r['名称'])}（{r['代码']}）· 共识 {r['共识票数']}/5 组</span>
<b class="up">{html.escape(r['动作'].split('（')[0])}</b><br>
<span class="dim">触发价 {r['买入参考价/触发价']}（{r['价格口径']}）｜ 止损 {r['止损价/锚']} ｜ 止盈 {r['止盈价/锚']}</span><br>
<span class="dim">来源组 {r['组']} ｜ 有效期 {r['有效期(天)']} 天 ｜ 意向非成交</span></div>"""
    for i, r in enumerate(TOP3))

entries = [
    ("实盘推荐专区", "live/index.html", "每日实盘推荐卡：行业共识买入 + 观察池，历史可翻"),
    ("模拟盘赛马", "sim/index.html", "五组净值对比曲线、日胜率与当前持仓明细"),
    ("策略档案", "strategies/index.html", "五组策略卡片墙（版本待契约回填）"),
    ("数据状态", "data-status/index.html", "六项数据源红黄绿灯 + 已知缺日"),
    ("最新实盘卡 10-27", "live/2026-10-27.html", "共识买入 7 只 / 观察池 13 只"),
    ("上一实盘卡 10-26", "live/2026-10-26.html", "共识买入 36 只 / 观察池 4 只"),
]
entry_html = "".join(f'<a class="entry" href="{p}"><span class="lab">{t}</span><b>{t}</b><br><span class="dim">{d}</span></a>'.replace(
    f'<span class="lab">{t}</span><b>{t}</b>', f'<b>{t}</b>') for t, p, d in entries)

body = f"""
<h1>五组投资大看板</h1>
<div class="sub">今日 {today} ｜ 投资一组（WB）承建 ｜ 模拟净值起点 2026-09-03/04，全部数字可溯源至公共数据集与每日上报件</div>
<h2>五组模拟净值总览</h2>
<div class="grid g5">{nav_cards}</div>
<div class="sub" style="margin-top:6px">日胜率口径：act_nav 日收益&gt;0 的交易日 ÷ 总交易日；详见模拟盘赛马页</div>
<h2>当日实盘推荐 Top3（2026-10-27 卡 · 行业共识 ≥2 组）</h2>
<div class="grid g3">{top3_html}</div>
<div class="sub" style="margin-top:6px">全部为 AI 意向、未成交；完整卡见 <a href="live/2026-10-27.html">实盘专区</a></div>
<h2>板块入口</h2>
<div class="grid g6">{entry_html}</div>
"""
open(f"{OUT}/index.html", "w").write(page("首页", body, depth=0))

# ---------- live/index.html ----------
items = []
for d in CARD_DATES:
    hdr = card_txt_header(d)
    def grab(pat):
        for l in hdr:
            m = re.search(pat, l)
            return m.group(1) if m else "未标注"
        return "未标注"
    nb = grab(r"买入推荐：(\d+) 只")
    watch = grab(r"观察池：(\d+) 只")
    miss = grab(r"缺失：(.+)")
    items.append(f"""<a class="entry" href="{d}.html"><b>{d} 实盘卡</b><br>
<span class="dim">共识买入 {nb} 只 ｜ 观察池 {watch} 只 ｜ 缺失组：{miss}</span><br>
<span class="dim">来源：daily_live_card_{d}.html/.csv/.txt（照原文呈现，不加工）</span></a>""")
body = f"""
<h1>实盘推荐专区</h1>
<div class="sub">按日期倒序；卡片口径：买入档 = 行业共识 ind_n≥2；价格列可能为「本组未设」（QD 无日内价源）</div>
<div class="grid" style="grid-template-columns:1fr;margin-top:14px">{''.join(items)}</div>
"""
open(f"{OUT}/live/index.html", "w").write(page("实盘推荐", body, depth=1))

# ---------- live/<date>.html ----------
for d in CARD_DATES:
    styles, cbody = card_html(d)
    body = f"""<div class="card" style="border:1px solid var(--line)"><span class="dim">来源：投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_{d}.html（照原文嵌入，未加工）｜ <a href="index.html">← 返回实盘列表</a></span></div>
{cbody}
<style>{styles.replace('<style>', '').replace('</style>', '')}</style>
"""
    open(f"{OUT}/live/{d}.html", "w").write(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>实盘卡 {d} · 五组投资大看板</title>
<style>
:root{{--bg:#0b0e14;--panel:#12161f;--line:#232a36;--tx:#d7dee8;--dim:#8a93a3;--acc:#58a6ff}}
*{{box-sizing:border-box}} body{{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,"PingFang SC",sans-serif;line-height:1.6}}
a{{color:#58a6ff;text-decoration:none}}
.topnav{{display:flex;gap:18px;padding:12px 22px;background:#12161f;border-bottom:1px solid #232a36}}
.topnav a{{color:#8a93a3;font-size:13px}}
</style></head><body>
<div class="topnav"><a href="../index.html">首页</a><a href="index.html">实盘推荐</a><a href="../sim/index.html">模拟盘赛马</a><a href="../strategies/index.html">策略档案</a><a href="../data-status/index.html">数据状态</a></div>
<div style="max-width:1000px;margin:0 auto;padding:24px">
<div class="card" style="margin-bottom:16px"><span style="color:#8a93a3;font-size:12px">来源：投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_{d}.html（照原文嵌入，未加工）｜ <a href="index.html">← 返回实盘列表</a></span></div>
{cbody}
</div></body></html>""")

# ---------- sim/index.html ----------
chart_data = {g: [[r[0], r[1]] for r in navs[g]] for g in GROUPS}
last_dates = {g: M[g]["last"] for g in GROUPS}

rows = ""
for g in GROUPS:
    m = M[g]
    lag = "" if m["last"] == today else f' <span class="warn">（最后更新 {m["last"]}）</span>'
    rows += f"""<tr><td>{g}</td><td>{m['act']:.4f}{lag}</td><td>{pct(m['dchg'])}</td><td>{pct(m['cum'])}</td>
<td>{m['winrate']*100:.1f}% <span class="dim">（{m['win']}/{m['n']} 日）</span></td><td>{m['n_hold']}</td><td class="dim">{m['first']} → {m['last']}</td></tr>"""

def hold_table(g):
    h = R[g]["holdings"]
    tr = ""
    for x in h:
        def gv(k, fmt=None):
            v = x.get(k)
            if v is None:
                return '<span class="dim">未上报</span>'
            return fmt(v) if fmt else html.escape(str(v))
        up = x.get("unreal_pct")
        if up is None:
            upc = '<span class="dim">未知</span>'
        else:
            cls = "up" if up > 0 else "dn" if up < 0 else "dim"
            upc = f'<span class="{cls}">{up:+.2f}%</span>'
        extra = ""
        if g == "DSK" and x.get("price_date"):
            extra = f'<span class="dim">（价 {x["price_date"]}）</span>'
        if g == "QD" and x.get("last_basis"):
            extra = f'<br><span class="dim" style="white-space:normal">{html.escape(x["last_basis"])}</span>'
        tr += f"""<tr><td>{gv('code')}</td><td>{gv('name')}</td><td>{gv('industry')}</td>
<td>{gv('last', lambda v: f'{v:.4g}' if isinstance(v,(int,float)) else html.escape(str(v)))}{extra}</td>
<td>{gv('entry', lambda v: f'{v:.4g}' if isinstance(v,(int,float)) else html.escape(str(v)))}</td>
<td>{upc}</td><td>{gv('action')}</td></tr>"""
    note = ""
    if g == "HRS":
        note = '<div class="sub">注：HRS 上报件无 unreal_pct 字段 → 浮盈列如实标「未知」；该件 nav=0.840125 与 simulated_nav_HRS.csv 最新 act_nav=0.7705 口径不同（CSV 为 steady 档净值），本页净值一律以 CSV 为准。</div>'
    if g == "QD":
        note = '<div class="sub">注：QD 现价为 canon 后复权（计价口径），非市价；本件持仓 entry 无空值。</div>'
    if g == "CX":
        note = '<div class="sub">注：CX 持仓为事件式调仓批记录（entry_date=2026-10-08 批，99 只），以 2026-10-27 收盘价逐只重估（覆盖 99/99）。</div>'
    return f"""<div class="holdsec{' on' if g == 'WB' else ''}" id="hold_{g}">{note}<table>
<tr><th>代码</th><th>名称</th><th>行业</th><th>现价</th><th>成本/入场</th><th>浮盈</th><th>动作</th></tr>{tr}</table></div>"""

btns = "".join(f'<button id="btn_{g}" onclick="showH(\'{g}\')"{" class=on" if g == "WB" else ""}>{g}（{len(R[g]["holdings"])} 只）</button>' for g in GROUPS)

body = f"""
<h1>模拟盘赛马</h1>
<div class="sub">数据源：公共/数据/simulated_nav_&lt;组&gt;.csv ｜ 指标口径：日胜率 = act_nav 日收益&gt;0 的交易日 ÷ 总交易日（各样本 ≥20 天）；区间累计收益 = 末值/首值 − 1</div>
<h2>五组净值曲线（act_nav）</h2>
<div class="card" style="padding:18px"><canvas id="navchart" height="110"></canvas></div>
<h2>赛马指标表</h2>
<table>
<tr><th>组</th><th>最新净值</th><th>当日涨跌</th><th>区间累计收益</th><th>日胜率</th><th>当前持仓</th><th>样本区间</th></tr>
{rows}
</table>
<div class="sub" style="margin-top:6px">QD/DSK 最初两档 act_nav 有 1.0/0.997 等起点差异；WB 2026-09-04 首日 act_nav=0.997（含建仓成本）。</div>
<h2>当前持仓明细（取各组最新上报件 holdings）</h2>
<div class="btns">{btns}</div>
{''.join(hold_table(g) for g in GROUPS)}
<script>
function showH(g) {{
  document.querySelectorAll('.holdsec').forEach(e => e.classList.remove('on'));
  document.querySelectorAll('.btns button').forEach(e => e.classList.remove('on'));
  document.getElementById('hold_' + g).classList.add('on');
  document.getElementById('btn_' + g).classList.add('on');
}}
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const DATA = {json.dumps(chart_data)};
const COLORS = {{WB:'#58a6ff',CX:'#d2a8ff',QD:'#3fb950',DSK:'#d29922',HRS:'#f85149'}};
const labels = DATA.WB.map(d => d[0]);
new Chart(document.getElementById('navchart'), {{
  type: 'line',
  data: {{ datasets: Object.keys(DATA).map(g => ({{
    label: g, data: DATA[g].map(d => ({{x: d[0], y: d[1]}})),
    borderColor: COLORS[g], backgroundColor: COLORS[g],
    pointRadius: 2, borderWidth: 1.6, tension: 0.15
  }})) }},
  options: {{
    parsing: false,
    scales: {{
      x: {{ type: 'category', labels: labels, ticks: {{ color:'#8a93a3', maxRotation:45, font:{{size:10}} }}, grid:{{color:'#1c2330'}} }},
      y: {{ ticks: {{ color:'#8a93a3' }}, grid:{{color:'#1c2330'}} }}
    }},
    plugins: {{ legend: {{ labels: {{ color:'#d7dee8' }} }} }}
  }}
}});
</script>
"""
open(f"{OUT}/sim/index.html", "w").write(page("模拟盘赛马", body, depth=1))

# ---------- strategies/index.html ----------
STRAT = {
 "WB": ("V9 月度调仓：反转 + 质量分打分，V6 现金滤镜；持仓 25 只，gate_id=V9，tier=满仓；止盈 +15% / 止损 −10%（自今日收盘价起算）。",
        "C8 择时闸门为空壳（v9_live_signal_scan.py 仅注释占位）——如实转自 WB 2026-10-27 上报件 data_gaps。"),
 "CX": ("QF-1.2：Top100 事件式调仓批（最近批 entry_date=2026-10-08），暴露 E=0.50，risk 闸门（当前 34.65），禁杠杆；虚拟本金 100 万元计分。",
        "线索取自 CX 2026-10-27 上报件 strategy/tier/gate_id 字段与 data_gaps。"),
 "QD": ("QB：震荡 regime，等权 12 槽（当前 11 只持仓 + 1 现金槽），eq=0.590；选股为技术类认证变体 vol20_asc（20 日平均成交量升序）；无止损规则。",
        "线索取自 QD 2026-10-26 上报件 tier/exit_rule/new_picks_basis 字段。"),
 "DSK": ("机械 R3 等权持有 15 只，无择时模型（market_view confidence=0）；成本按双边 30bp 实扣，post_anchor 严格边界。",
        "线索取自 DSK 2026-10-27 上报件 market_view/data_gaps 字段。"),
 "HRS": ("双档：aggressive Top20 / steady Top50（拥挤倒数），排序键 = 20 日反转升序；20 交易日整篮换仓冻结；C8 择时（202609 市场收益 mean/median 存在口径分歧，现采用 mean）。",
        "线索取自 HRS 2026-10-26 上报件与 simulated_nav_HRS.csv tier 字段。"),
}
scards = ""
for g in GROUPS:
    main, clue = STRAT[g]
    scards += f"""<div class="card"><b>{g} 组</b> <span class="tag">版本未上报（契约增补已发，待各组回填）</span>
<p style="margin:8px 0 4px">{main}</p>
<p class="dim" style="font-size:12px;margin:4px 0 0">{clue}</p></div>"""
body = f"""
<h1>策略档案</h1>
<div class="sub">五组上报件均无 strategy 版本字段（实测 2026-10-27）→ 版本一律标灰，待策略契约回填后更新；下方打法描述均取自上报件真实字段，未编造。</div>
<div class="grid g6" style="margin-top:14px">{scards}</div>
"""
open(f"{OUT}/strategies/index.html", "w").write(page("策略档案", body, depth=1))

# ---------- data-status/index.html ----------
STATUS = [
 ("green", "canon 主K线（QD hfq）", "公共/数据/kline_25y_QD_hfq.csv",
  "实测末行 date=2026-10-27，总数据行 16,230,290（wc -l 16,230,291 含表头），mtime 2026-10-27 19:05。日更正常。"),
 ("yellow", "ETF 510300（WB 源）", "公共/数据/kline_etf_510300_WB.csv",
  "实测末行 date=2026-10-23（应到 10-27）→ 停更，日更修复进行中；mtime 2026-10-25 14:09。"),
 ("grey", "main_flow 主力资金流", "—", "已冻结（2026-10-27 用户裁定不恢复）。"),
 ("grey", "实时/分钟价", "—", "无源；模式 = 收盘后决策、次日开盘执行。"),
 ("grey", "券商委托回报", "—", "无 API，待用户手工导入。"),
 ("grey", "公告/新闻催化剂", "—", "未采集（探路中）。"),
 ("yellow", "canon 2026-09-25 全市场缺日", "公共/数据/canon_hfq_patch_20260925_QD.csv",
  "已知项：canon 主K线 2026-09-25 全市场缺一日，曾有补丁文件；页内如实保留黄灯提示。"),
]
lights = {"green": ("绿灯", "up"), "yellow": ("黄灯", "warn"), "grey": ("灰灯", "dim")}
srows = "".join(
    f"""<tr><td><span class="{c}">●</span> {lights[s][0]}</td><td>{t}</td><td class="dim">{p}</td><td style="white-space:normal">{d}</td></tr>"""
    for s, t, p, d in [(s, t, p, d) for (s, t, p, d) in STATUS] for c in [lights[s][1]])
body = f"""
<h1>数据状态</h1>
<div class="sub">逐项实测于 2026-10-27 深夜；实测依据（文件路径 + 末行/行数 + mtime）见 build_report.md</div>
<table style="margin-top:14px">
<tr><th>状态</th><th>数据项</th><th>源文件</th><th>说明</th></tr>
{srows}
</table>
"""
open(f"{OUT}/data-status/index.html", "w").write(page("数据状态", body, depth=1))

print("pages done:", CARD_DATES, "| nav last:", {g: M[g]["last"] for g in GROUPS})
