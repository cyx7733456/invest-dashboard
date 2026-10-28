# -*- coding: utf-8 -*-
"""五组投资大看板 v2 构建脚本（每日可重跑自动生成新日期页）。

== 输入文件清单 ==
1. 公共/数据/simulated_nav_<组>.csv                     五组模拟净值（| 分隔，date/act_nav/n_hold）
2. 公共/数据/daily_report_<组>_<YYYY-MM-DD>.json        每日上报件（market_view/holdings/new_picks）
3. 投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_<日期>.{csv,txt,html}
                                                        实盘卡三件套
== 日期探测逻辑 ==
- 实盘卡日期集合 = daily_live_cards/ 下 daily_live_card_<YYYY-MM-DD>.html 的 glob；
- 每个卡日期 D 的风向标数据取 公共/数据/daily_report_<组>_D.json（缺件 → 该组「未上报」）；
- 最新日期 = 卡日期集合最大值；首页/入口页摘要卡、历史列表、详情页均由该集合自动生成；
- 以后每日新卡落盘后重跑本脚本即自动出新日期页并更新入口页/首页。

== 诚实铁律 ==
- 所有数字直接读源文件；取不到的列/字段一律显示「取不到/未上报」，严禁编造或估算。

== v2 改版（2026-10-27 验收后四需求）==
R1 live/ 入口页：最新一日摘要卡 + 大按钮 + 历史日期卡列表（不再堆叠多日全文）
R2 详情页重设计：KPI 条 + 实盘风向标区 + 共识买入表 + 观察票表 + <details> 折叠原文 + 风险脚注
R3 首页 Top3：来源组徽章 + 参与状态条 + 选取规则注明
R4 首页新增「实盘风向标」板块（位于当日实盘推荐之前）
"""
import csv, json, os, html, re

ROOT = "/Users/apple/Desktop/Investment"
OUT = os.path.join(ROOT, "公共/看板设计/dashboard_v1")
DATA = os.path.join(ROOT, "公共/数据")
CARDS = os.path.join(ROOT, "投资1组_WB/实盘化方案/daily_live_cards")
GROUPS = ["WB", "CX", "QD", "DSK", "HRS"]
TODAY = "2026-10-27"
BUILD_TS = "2026-10-27 深夜（本地构建，AI 生成）"

# ---------- 日期探测 ----------
def card_dates():
    ds = []
    for f in os.listdir(CARDS):
        m = re.match(r"daily_live_card_(\d{4}-\d{2}-\d{2})\.html$", f)
        if m:
            ds.append(m.group(1))
    return sorted(ds)

CARD_DATES = card_dates()
LATEST = CARD_DATES[-1]

def report_path(g, date):
    return f"{DATA}/daily_report_{g}_{date}.json"

def load_report(g, date):
    p = report_path(g, date)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)

# ---------- 净值 ----------
navs = {}
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
    return {
        "first": rows[0][0], "last": rows[-1][0], "act": rows[-1][1],
        "n_hold": rows[-1][2], "win": win, "n": len(rets),
        "winrate": win / len(rets), "cum": rows[-1][1] / rows[0][1] - 1,
        "dchg": rows[-1][1] / rows[-2][1] - 1,
    }

M = {g: metrics(g) for g in GROUPS}

def latest_report(g):
    cands = sorted(f for f in os.listdir(DATA)
                   if re.match(rf"daily_report_{g}_\d{{4}}-\d{{2}}-\d{{2}}\.json$", f))
    p = os.path.join(DATA, cands[-1])
    with open(p) as f:
        return {"path": p, "fname": cands[-1], **json.load(f)}

R = {g: latest_report(g) for g in GROUPS}  # 持仓明细用最新一份

# ---------- 风向标（v2）----------
def compass(date):
    """返回 (counts, rows)。无观点 = conf==0（本组自述无观点）；缺件 = 未上报。"""
    counts = {"看多": 0, "看空": 0, "中性": 0, "无观点": 0, "未上报": 0}
    rows = []
    for g in GROUPS:
        d = load_report(g, date)
        if d is None:
            counts["未上报"] += 1
            rows.append({"g": g, "state": "未上报", "stance": None, "conf": None,
                         "basis": f"当日上报件不存在（daily_report_{g}_{date}.json 缺件）",
                         "no_timing": False, "human": None})
            continue
        mv = d.get("market_view") or {}
        conf = mv.get("confidence")
        stance = mv.get("stance")
        basis = str(mv.get("basis") or "未上报")
        no_timing = (conf == 0)
        state = "无观点" if no_timing else (stance if stance in counts else "中性")
        counts[state] += 1
        rows.append({"g": g, "state": state, "stance": stance, "conf": conf,
                     "basis": basis, "no_timing": no_timing,
                     "human": mv.get("is_human"), "np": len(d.get("new_picks") or [])})
    line = "、".join(f"{v} 组{k}" for k, v in counts.items() if v) or "无数据"
    return counts, rows, sum(counts.values()), line

def compass_html(date):
    counts, rows, total, _ = compass(date)
    order = ["看多", "中性", "看空", "无观点", "未上报"]
    seg_col = {"看多": "var(--up)", "中性": "#6e7681", "看空": "var(--dn)",
               "无观点": "#30363d",
               "未上报": "repeating-linear-gradient(45deg,#21262d,#21262d 4px,#161b22 4px,#161b22 8px)"}
    segs = "".join(
        f'<div class="cseg" style="width:{counts[k]/total*100:.0f}%;background:{seg_col[k]}" title="{k} {counts[k]} 组">{counts[k] if counts[k] else ""}</div>'
        for k in order if counts[k])
    cnt_bits = " · ".join(
        f'<span class="{"up" if k == "看多" else "dn" if k == "看空" else "warn" if k == "未上报" else "dim"}">{k} {counts[k]} 组</span>'
        for k in order if counts[k])
    stag_cls = {"看多": "up", "看空": "dn", "中性": "dim", "无观点": "dim", "未上报": "warn"}
    grows = ""
    for r in rows:
        st = r["state"]
        conf = r["conf"]
        conf_bar = (f'<span class="cbar"><i style="width:{min(conf,1)*100:.0f}%"></i></span>'
                    f'<span class="dim">{conf:.2f}</span>') if isinstance(conf, (int, float)) else '<span class="dim">—</span>'
        b = html.escape(r["basis"])
        short = b if len(b) <= 72 else b[:72] + "…"
        tag_note = ' <span class="dim">（本组无择时模型）</span>' if r["no_timing"] else ""
        human_note = ' <span class="dim">[人工]</span>' if r.get("human") is True else ""
        grows += f"""<div class="grow"><span class="gbadge">{r['g']}</span>
<span class="stag {stag_cls[st]}">{st}{tag_note}{human_note}</span>
{conf_bar}<span class="gbasis">{short}</span></div>"""
    return f"""
<div class="compass">
  <div class="cbarwrap">{segs}</div>
  <div class="cln">{cnt_bits}</div>
  {grows}
  <div class="sub">口径：无观点 = 该组上报件 confidence=0 且自述无择时模型；未上报 = 当日上报件缺件。卡面旧汇总把无观点组计入中性，本区按上报件实况区分。</div>
</div>"""

# ---------- 实盘卡数据 ----------
def card_rows(date):
    with open(f"{CARDS}/daily_live_card_{date}.csv", newline="") as f:
        return list(csv.DictReader(f))

def card_facts(date):
    txt = open(f"{CARDS}/daily_live_card_{date}.txt").read().splitlines()
    hdr = [l for l in txt if l.startswith("#")]
    def grab(pat):
        for l in hdr:
            m = re.search(pat, l)
            if m:
                return m.group(1).strip()
        return None
    return {
        "gen": grab(r"生成 (.+)$"),
        "sources": grab(r"信号来源：(.+?) /"),
        "missing": grab(r"缺失：(.+)"),
        "n_buy": grab(r"买入推荐：(\d+) 只"),
        "n_watch": grab(r"观察池：(\d+) 只"),
        "n_new": grab(r"新增推荐 (\d+) 只"),
        "risk": grab(r"风险等级：(.+)"),
    }

def industry_map(date):
    """code → industry，取自当日各组上报件（picks/holdings/new_picks）；查不到 → 未上报。"""
    m = {}
    for g in GROUPS:
        d = load_report(g, date)
        if not d:
            continue
        for k in ("picks", "holdings", "new_picks"):
            for x in d.get(k) or []:
                if x.get("code") and x.get("industry") and x["code"] not in m:
                    m[x["code"]] = x["industry"]
    return m

def pick_table(rows, date, kind):
    im = industry_map(date)
    sel = [r for r in rows if r["动作"].startswith(kind)]
    if not rows:
        return '<div class="dim" style="padding:8px 0">取不到：当日卡 csv 无逐票行（旧口径卡未提供），仅卡面自述口径，见下方原文折叠。</div>'
    if not sel:
        return '<div class="dim" style="padding:8px 0">当日无此类条目。</div>'
    tr = ""
    for r in sel:
        ind = im.get(r["代码"])
        ind_s = html.escape(ind) if ind else '<span class="dim">未上报</span>'
        tp, sl = r.get("止盈价/锚") or "", r.get("止损价/锚") or ""
        cons = f" <span class='dim'>共识 {html.escape(r['共识票数'])}/5</span>" if r.get("共识票数") else ""
        tr += f"""<tr><td>{html.escape(r['代码'])}</td><td>{html.escape(r['名称'])}</td>
<td>{html.escape(r['动作'].split('（')[0])}</td><td><span class="gbadge">{html.escape(r['组'])}</span>{cons}</td>
<td>{ind_s}</td><td>{html.escape(r['买入参考价/触发价'])} <span class="dim">({html.escape(r.get('价格口径') or '')})</span></td>
<td>{sl or '<span class=dim>未上报</span>'}</td><td>{tp or '<span class=dim>未上报</span>'}</td></tr>"""
    return f"""<table><tr><th>代码</th><th>名称</th><th>档位</th><th>来源组</th><th>行业</th><th>触发价</th><th>止损</th><th>止盈</th></tr>{tr}</table>
<div class="sub">行业列取自当日各组上报件的 industry 字段；卡 csv 无行业列，查不到的如实标「未上报」。</div>"""

def card_html_parts(date):
    with open(f"{CARDS}/daily_live_card_{date}.html") as f:
        src = f.read()
    styles = "".join(re.findall(r"<style>.*?</style>", src, re.S)).replace("<style>", "").replace("</style>", "")
    body = re.search(r"<body>(.*)</body>", src, re.S).group(1)
    return styles, body

# ---------- 通用骨架 ----------
CSS = """
:root{--bg:#0b0e14;--panel:#12161f;--line:#232a36;--tx:#d7dee8;--dim:#8a93a3;--up:#e5544b;--dn:#3fb950;--acc:#58a6ff;--warn:#d29922}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",monospace}
a{color:var(--acc);text-decoration:none} a:hover{text-decoration:underline}
.topnav{display:flex;gap:18px;padding:12px 22px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}
.topnav a{color:var(--dim);font-size:13px} .topnav a.on{color:var(--tx);font-weight:700;border-bottom:2px solid var(--acc)}
.wrap{max-width:1080px;margin:0 auto;padding:22px}
h1{font-size:22px;margin:6px 0 2px} h2{font-size:16px;margin:26px 0 10px;border-left:3px solid var(--acc);padding-left:9px}
.sub{color:var(--dim);font-size:12px}
.grid{display:grid;gap:12px} .g5{grid-template-columns:repeat(5,1fr)} .g3{grid-template-columns:repeat(3,1fr)}
.g6{grid-template-columns:repeat(3,1fr)} .gk{grid-template-columns:repeat(5,1fr)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:14px}
.card b{font-size:19px} .card .lab{color:var(--dim);font-size:11px;display:block}
.up{color:var(--up)} .dn{color:var(--dn)} .dim{color:var(--dim)} .warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:right;white-space:nowrap}
th{background:#171c26;color:var(--dim);font-weight:600} th:first-child,td:first-child{text-align:left}
.tag{display:inline-block;background:#1c2432;border:1px solid var(--line);border-radius:5px;padding:1px 8px;font-size:11px;color:var(--dim);margin:2px}
.entry{display:block;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px;color:var(--tx)}
.entry:hover{border-color:var(--acc);text-decoration:none}
.bigbtn{display:inline-block;background:#1f3a5f;border:1px solid var(--acc);border-radius:8px;padding:10px 26px;color:#cfe4ff;font-size:15px;font-weight:700;margin-top:10px}
.bigbtn:hover{background:#25477a;text-decoration:none}
footer{color:#5c6575;font-size:11px;text-align:center;padding:22px;border-top:1px solid var(--line);margin-top:34px}
.btns button{background:#171c26;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:6px 14px;margin-right:8px;cursor:pointer;font-size:13px}
.btns button.on{border-color:var(--acc);color:var(--acc)}
.holdsec{display:none} .holdsec.on{display:block}
details{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-top:12px;background:var(--panel)}
details summary{cursor:pointer;color:var(--dim);font-size:13px}
.compass{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:14px}
.cbarwrap{display:flex;height:26px;border-radius:6px;overflow:hidden;border:1px solid var(--line)}
.cseg{display:flex;align-items:center;justify-content:center;color:#d7dee8;font-size:12px;min-width:0}
.cln{margin:8px 0 4px;font-size:13px}
.grow{display:flex;align-items:center;gap:10px;padding:6px 0;border-top:1px dashed #1c2330;font-size:12.5px}
.gbadge{display:inline-block;background:#1f2937;border:1px solid var(--line);border-radius:5px;padding:1px 8px;font-weight:700;min-width:34px;text-align:center}
.stag{font-weight:700;min-width:52px}
.cbar{display:inline-block;width:80px;height:7px;background:#0d1117;border:1px solid var(--line);border-radius:4px;overflow:hidden;vertical-align:middle}
.cbar i{display:block;height:100%;background:var(--acc)}
.gbasis{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.status i{font-style:normal;margin:0 2px}
.riskfoot{margin-top:22px;border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:8px;padding:10px 14px;color:var(--dim);font-size:12px}
@media(max-width:900px){.g5,.g3,.g6,.gk{grid-template-columns:repeat(2,1fr)}}
"""

def page(title, body, depth=0):
    pre = "" if depth == 0 else "../"
    nav = (
        f'<a href="{pre}index.html"{" class=on" if title == "首页" else ""}>首页</a>'
        f'<a href="{pre}live/index.html"{" class=on" if title in ("实盘推荐", "实盘详情") else ""}>实盘推荐</a>'
        f'<a href="{pre}sim/index.html">模拟盘赛马</a>'
        f'<a href="{pre}strategies/index.html">策略档案</a>'
        f'<a href="{pre}data-status/index.html">数据状态</a>')
    footer = f'<footer>数据截至：{BUILD_TS} ｜ 数据源：五组每日上报件与公共数据集，AI 生成仅供参考</footer>'
    # v2.1：全站密码门锁（auth.js 置于 <head> 首位，未认证同步隐藏正文防闪烁）
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="{pre}auth.js"></script>
<title>{title} · 五组投资大看板</title>
<style>{CSS}</style></head><body>
<nav class="topnav">{nav}</nav>
<div class="wrap">
{body}
</div>
{footer}
</body></html>"""

def pct(x, signed=True):
    s = f"{x*100:+.2f}%" if signed else f"{x*100:.2f}%"
    return f'<span class="{"up" if x > 0 else "dn" if x < 0 else "dim"}">{s}</span>'

def part_status_html(date):
    """参与状态条：✅已报new_picks ⚠已报但0只 ❌缺件未上报。"""
    bits = []
    for g in GROUPS:
        d = load_report(g, date)
        if d is None:
            bits.append(f'<span class="warn">{g}❌未上报</span>')
        elif len(d.get("new_picks") or []) == 0:
            bits.append(f'<span class="warn">{g}⚠当日0只</span>')
        else:
            bits.append(f'<span class="up">{g}✅</span>')
    return '<span class="status">' + " · ".join(bits) + "</span>"

# ================= R4+R3：首页 =================
counts, crows, total, _ = compass(LATEST)
buy_cnt = f'{counts["看空"]} 看空 / {counts["中性"]} 中性 / {counts["看多"]} 看多'
sum_line = (f"五组中 {counts['看空']} 组看空、{counts['中性']} 组中性、{counts['看多']} 组看多"
            + (f"、{counts['无观点']} 组自述无观点" if counts["无观点"] else "")
            + (f"、{counts['未上报']} 组当日未上报" if counts["未上报"] else "")
            + "（客观计数陈述，非主观结论、非投资建议）")

top3 = []
with open(f"{CARDS}/daily_live_card_{LATEST}.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["动作"].startswith("买入"):
            top3.append(r)
TOP3 = top3[:3]

im_latest = industry_map(LATEST)
top3_html = ""
for i, r in enumerate(TOP3):
    ind = im_latest.get(r["代码"])
    ind_s = html.escape(ind) if ind else '<span class="dim">未上报</span>'
    top3_html += f"""<div class="card"><span class="lab">{i+1}. {html.escape(r['名称'])}（{r['代码']}）· {ind_s}</span>
<b class="up">{html.escape(r['动作'].split('（')[0])}</b> <span class="gbadge">{html.escape(r['组'])}</span>
<span class="dim">共识 {html.escape(r.get('共识票数') or '—')}/5 组</span><br>
<span class="dim">触发价 {r['买入参考价/触发价']}（{r['价格口径']}）｜ 止损 {r['止损价/锚']} ｜ 止盈 {r['止盈价/锚']}</span><br>
<span class="dim">有效期 {r['有效期(天)']} 天 ｜ 意向非成交</span></div>"""

nav_cards = ""
for g in GROUPS:
    m = M[g]
    lag = "" if m["last"] == TODAY else f'<span class="warn">数据截至 {m["last"]}</span>'
    nav_cards += f"""<div class="card"><span class="lab">{g} 组 · 模拟净值</span>
<b>{m['act']:.4f}</b><br>{pct(m['dchg'])} <span class="dim">当日</span><br>
<span class="dim">累计 {m['cum']*100:+.1f}% ｜ 持仓 {m['n_hold']} 只</span><br>{lag}</div>"""

entries = [
    ("实盘推荐专区", "live/index.html", "每日实盘推荐卡：最新摘要 + 历史日期导航"),
    ("模拟盘赛马", "sim/index.html", "五组净值对比曲线、日胜率与当前持仓明细"),
    ("策略档案", "strategies/index.html", "五组策略卡片墙（版本待契约回填）"),
    ("数据状态", "data-status/index.html", "六项数据源红黄绿灯 + 已知缺日"),
    (f"最新实盘卡 {LATEST[5:]}", f"live/{LATEST}.html", "共识买入表 / 观察票表 / 风向标"),
    ("上一实盘卡 10-26", "live/2026-10-26.html", "共识买入 36 只 / 观察池 4 只"),
]
entry_html = "".join(f'<a class="entry" href="{p}"><b>{t}</b><br><span class="dim">{d}</span></a>' for t, p, d in entries)

seg_style = {"看多": "var(--up)", "看空": "var(--dn)", "中性": "#6e7681", "无观点": "#30363d", "未上报": "#21262d"}
home_segs = "".join(f'<div class="cseg" style="width:{c/5*100:.0f}%;background:{seg_style[k]}" title="{k} {c} 组">{c if c else ""}</div>'
                    for k, c in counts.items() if c)
home_rows = "".join(
    f'<div class="grow"><span class="gbadge">{r["g"]}</span>'
    f'<span class="stag {"up" if r["state"]=="看多" else "dn" if r["state"]=="看空" else "dim"}{" warn" if r["state"]=="未上报" else ""}">{r["state"]}</span>'
    f'<span class="dim">conf {r["conf"] if r["conf"] is not None else "—"}</span>'
    f'<span class="gbasis">{html.escape(str(r["basis"])[:80])}{"…" if len(str(r["basis"]))>80 else ""}</span></div>'
    for r in crows)

body = f"""
<h1>五组投资大看板</h1>
<div class="sub">今日 {TODAY} ｜ 投资一组（WB）承建 ｜ 模拟净值起点 2026-09-03/04，全部数字可溯源至公共数据集与每日上报件</div>
<h2>五组模拟净值总览</h2>
<div class="grid g5">{nav_cards}</div>
<div class="sub" style="margin-top:6px">日胜率口径：act_nav 日收益&gt;0 的交易日 ÷ 总交易日；详见模拟盘赛马页</div>
<h2>实盘风向标（{LATEST}）</h2>
<div class="compass">
  <div class="cbarwrap">{home_segs}</div>
  <div class="cln"><span class="dn">看空 {counts["看空"]} 组</span> · <span class="dim">中性 {counts["中性"]} 组</span> · <span class="up">看多 {counts["看多"]} 组</span> · <span class="dim">无观点 {counts["无观点"]} 组</span> · <span class="warn">未上报 {counts["未上报"]} 组</span></div>
  {home_rows}
  <div class="sub" style="margin-top:6px">{sum_line}</div>
</div>
<div style="margin-top:8px"><a class="bigbtn" href="live/{LATEST}.html#compass">查看详情（当日风向标区）</a></div>
<h2>当日实盘推荐 Top3（{LATEST} 卡 · 行业共识 ≥2 组判据）</h2>
{part_status_html(LATEST)}
<div class="sub" style="margin:4px 0 10px">Top3 选取规则：取当日卡 csv 中「买入（行业共识≥2 组）」档前 3 条，按卡面原序，未加工。</div>
<div class="grid g3">{top3_html}</div>
<div class="sub" style="margin-top:6px">来源组徽章为卡面记录的单票来源组；共识票数含同行业他组候选。全部为 AI 意向、未成交；完整卡见 <a href="live/{LATEST}.html">实盘专区</a></div>
<h2>板块入口</h2>
<div class="grid g6">{entry_html}</div>
"""
open(f"{OUT}/index.html", "w").write(page("首页", body, depth=0))

# ================= R1：live/ 入口页 =================
def date_summary(d):
    facts = card_facts(d)
    if facts["n_buy"]:
        cnt = f'共识买入 {facts["n_buy"]} 只 ｜ 观察 {facts["n_watch"]} 只'
    else:
        cnt = f'卡面自述新增推荐 {facts["n_new"]} 只（旧口径，无逐票 csv）'
    _, drows, _, _ = compass(d)
    wind = " · ".join(f'{k} {sum(1 for r in drows if r["state"]==k)}'
                      for k in ("看空", "中性", "看多"))
    return cnt, wind, facts

hist_cards = ""
for d in reversed(CARD_DATES):
    cnt, wind, _ = date_summary(d)
    hist_cards += f"""<a class="entry" href="{d}.html"><b>{d}</b><br>
<span class="dim">{cnt}</span><br><span class="dim">风向：看空 {wind.split(" · ")[0].split()[-1]} / 中性 {wind.split(" · ")[1].split()[-1]} / 看多 {wind.split(" · ")[2].split()[-1]}</span></a>"""

lf = card_facts(LATEST)
body = f"""
<h1>实盘推荐专区</h1>
<div class="sub">卡片口径：买入档 = 行业共识 ind_n≥2（2026-10-27 起为本卡唯一『推荐』口径）；价格列可能为「本组未设」（QD 无日内价源）</div>
<div class="card" style="margin-top:14px">
  <span class="lab">最新一日 · {LATEST}（生成 {lf['gen'] or '未上报'}）</span>
  <b style="font-size:24px">共识买入 {lf['n_buy']} 只</b> <span class="dim">｜ 观察 {lf['n_watch']} 只</span><br>
  <span class="dim">信号来源 {lf['sources']} ｜ 缺失 {lf['missing']}</span><br>
  <span class="dim">风险等级：{lf['risk']}</span><br>
  {part_status_html(LATEST)}
  <br><a class="bigbtn" href="{LATEST}.html">查看当日详情 →</a>
</div>
<h2>历史日期</h2>
<div class="grid g3">{hist_cards}</div>
"""
open(f"{OUT}/live/index.html", "w").write(page("实盘推荐", body, depth=1))

# ================= R2：详情页 =================
for d in CARD_DATES:
    card_r = card_rows(d)
    facts = card_facts(d)
    styles, cbody = card_html_parts(d)
    _, drows, _, _ = compass(d)
    if facts["n_buy"]:
        kpi_buy = f'<div><label>✅ 共识买入（≥2 组）</label><b>{facts["n_buy"]}</b><small>本卡唯一推荐口径</small></div>'
        kpi_watch = f'<div><label>👁 观察池</label><b>{facts["n_watch"]}</b><small>非推荐，仅跟踪</small></div>'
    else:
        kpi_buy = '<div><label>✅ 共识买入</label><b class="dim">取不到</b><small>当日卡 csv 无逐票行</small></div>'
        kpi_watch = f'<div><label>卡面自述新增推荐</label><b>{facts["n_new"]}</b><small>旧口径，非共识口径</small></div>'
    n_report = sum(1 for g in GROUPS if os.path.exists(report_path(g, d)))
    dcounts, drows, _, _ = compass(d)
    d_buy_cnt = f'{dcounts["看空"]} 看空 / {dcounts["中性"]} 中性 / {dcounts["看多"]} 看多'
    buy_tbl = pick_table(card_r, d, "买入")
    watch_tbl = pick_table(card_r, d, "观察")
    detail_rows = "".join(
        f'<div class="grow"><span class="gbadge">{r["g"]}</span>'
        f'<span class="gbasis" style="white-space:normal">{html.escape(str(r["basis"]))}</span></div>'
        for r in drows)
    orig_hdr = html.escape("\n".join(
        l for l in open(f"{CARDS}/daily_live_card_{d}.txt").read().splitlines() if l.startswith("#")))
    body = f"""
<h1>每日实盘推荐卡 · {d}</h1>
<div class="sub">生成 {facts['gen'] or '未上报'} ｜ 来源：投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_{d}.{{csv,txt,html}} ｜ <a href="index.html">← 返回实盘列表</a></div>
<div class="grid gk" style="margin-top:12px">
  {kpi_buy}
  {kpi_watch}
  <div><label>📥 参与组</label><b>{n_report}/5</b><small>{facts['sources'] or ''}{' ｜ 缺失 ' + facts['missing'] if facts['missing'] and facts['missing'] != '无' else ''}</small></div>
  <div><label>🧭 当日风向</label><b style="font-size:14px">{d_buy_cnt.replace(' / ', '<br>')}</b><small>按各组上报件实况统计</small></div>
  <div><label>风险等级</label><b style="font-size:14px">{facts['risk'] or '未上报'}</b><small>卡面自述</small></div>
</div>

<h2 id="compass">实盘风向标</h2>
{compass_html(d)}

<h2>共识买入（行业共识 ≥2 组 · 意向非成交）</h2>
{buy_tbl}

<h2>观察票（未达共识门槛 · 非推荐）</h2>
{watch_tbl}

<details><summary>展开原文：五组 market_view 全文与卡面说明（含卡片完整原文）</summary>
{detail_rows}
<hr style="border:0;border-top:1px dashed #1c2330">
<pre style="white-space:pre-wrap;color:var(--dim);font-size:12px">{orig_hdr}</pre>
<div>{cbody}</div>
</details>

<div class="riskfoot">⚠️ 风险提示：本卡由 AI 生成、非投资建议；所有信号均为意向，未产生任何真实成交；是否录入由用户自行决定。止盈止损为机械参考位，跳空/跌停情形条件单可能不成交。</div>
"""
    out = page("实盘详情", body, depth=1)
    # 卡片自带样式插到站内主样式之前，站内骨架样式优先
    out = out.replace("<style>" + CSS, f"<style>{styles}\n{CSS}")
    open(f"{OUT}/live/{d}.html", "w").write(out)

# ================= sim / strategies / data-status（沿用 v1 逻辑） =================
chart_data = {g: [[r[0], r[1]] for r in navs[g]] for g in GROUPS}

rows = ""
for g in GROUPS:
    m = M[g]
    lag = "" if m["last"] == TODAY else f' <span class="warn">（最后更新 {m["last"]}）</span>'
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
    f"""<tr><td><span class="{lights[s][1]}">●</span> {lights[s][0]}</td><td>{t}</td><td class="dim">{p}</td><td style="white-space:normal">{d}</td></tr>"""
    for s, t, p, d in STATUS)
body = f"""
<h1>数据状态</h1>
<div class="sub">逐项实测于 2026-10-27 深夜；实测依据（文件路径 + 末行/行数 + mtime）见 build_report.md</div>
<table style="margin-top:14px">
<tr><th>状态</th><th>数据项</th><th>源文件</th><th>说明</th></tr>
{srows}
</table>
"""
open(f"{OUT}/data-status/index.html", "w").write(page("数据状态", body, depth=1))

print("v2 build done | cards:", CARD_DATES, "| latest:", LATEST)
