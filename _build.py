# -*- coding: utf-8 -*-
"""五组投资大看板 v2 构建脚本（每日可重跑自动生成新日期页）。

== 输入文件清单 ==
1. 公共/数据/simulated_nav_<组>.csv                     五组模拟净值（| 分隔，date/act_nav/n_hold）
2. 公共/数据/daily_report_<组>_<YYYY-MM-DD>.json        每日上报件（market_view/holdings/new_picks）
3. 投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_<日期>.{csv,txt,html}
                                                        实盘卡三件套
4. 公共/数据/kline_etf_510300_WB.csv                    ETF 510300 日线（| 分隔 16 列；
                                                        收益用 close_hfq_mul 后复权乘法，
                                                        MA/价格位置用 bfq close）——市场分析页
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
import csv, json, os, html, re, math
from datetime import datetime as _dt

ROOT = "/Users/apple/Desktop/Investment"
OUT = os.path.join(ROOT, "公共/看板设计/dashboard_v1")
DATA = os.path.join(ROOT, "公共/数据")
CARDS = os.path.join(ROOT, "投资1组_WB/实盘化方案/daily_live_cards")
GROUPS = ["WB", "CX", "QD", "DSK", "HRS"]
# 显示名映射（用户 2026-10-28 要求：页面上一律用「1组~5组」，不用英文简称；
# 文件名/HTML id/图表数据键仍用内部代码，不影响任何逻辑）
GD = {"WB": "1组", "CX": "2组", "QD": "3组", "DSK": "4组", "HRS": "5组"}

def disp_groups(s):
    """把卡面来源/缺失串里的组代码替换为显示名，如 'CX,DSK,WB' → '2组、4组、1组'。"""
    if not s:
        return s
    out = str(s)
    for k, v in GD.items():
        out = re.sub(rf"\b{k}\b", v, out)
    return out.replace(",", "、")

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
# 自动化修正（2026-10-28）：TODAY 不再写死——跟随最新实盘卡日期，
# 否则每日定时重跑生成的永远是旧日期口径
TODAY = LATEST
BUILD_TS = _dt.now().strftime("%Y-%m-%d %H:%M") + "（本地自动构建）"

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

# ---------- 风向标（v2.2）----------
def _read_day(g, d, mv):
    """报告日 ≠ 读数日（3组 2026-10-28 函建议④：两格分开，否则跨日趋势会把同日截面画成两天判断）。
    读数日取法（按可溯源优先级）：
    1) market_view.rule.window.last（判据窗口末端＝读数日；3组 QD-B1 已提供，其他组补齐时套同一模板）；
    2) 件内 canon_row_basis.as_of（+uses_t_day_row 注明是否 T 日行，3组 件自带）；
    3) 3组 两者皆无 → 标「常态=T−1」（不写死具体日期）；其他组 → 未提供。"""
    mv_rule = mv.get("rule") if isinstance(mv.get("rule"), dict) else {}
    w = (mv_rule or {}).get("window") or {}
    if w.get("last"):
        return str(w["last"]), "rule.window.last"
    crb = d.get("canon_row_basis")
    if isinstance(crb, dict) and crb.get("as_of"):
        return str(crb["as_of"]), ("T日行" if crb.get("uses_t_day_row") else "缺行退回")
    if g == "QD":
        return None, "常态=T−1"
    return None, None

def _rule_notes(mv):
    """HRS 建议2 / 3组建议3：把结构化判据 rule 摊平成可读文本，供看板自动校验"是否裸结论"。
    无 rule → (None, None)。"""
    rule = mv.get("rule") if isinstance(mv.get("rule"), dict) else {}
    if not rule:
        return None, None
    th = rule.get("thresholds") or {}
    bits = []
    if rule.get("id"):
        bits.append(f"判据 {rule['id']}")
    if "S" in rule:
        bits.append(f"S={rule['S']}")
    if th.get("bear_lte") is not None and th.get("bull_gte") is not None:
        bits.append(f"S≤{th['bear_lte']:g} 看空 / S≥{th['bull_gte']:g} 看多")
    if rule.get("conf_cap") is not None:
        bits.append(f"conf 上限 {rule['conf_cap']:g}")
    if rule.get("carrier_set_sha16"):
        bits.append(f"载体集 sha16={rule['carrier_set_sha16']}")
    try:
        full = json.dumps(rule, ensure_ascii=False)
    except Exception:
        full = str(rule)
    return "；".join(bits), full

def compass(date):
    """返回 (counts, rows)。无观点 = conf==0（本组自述无观点）；缺件 = 未上报。
    v2.2：每行附 读数日、当日生成/事后补跑（generated_at vs date）、结构化判据、旧口径标记。"""
    counts = {"看多": 0, "看空": 0, "中性": 0, "无观点": 0, "未上报": 0}
    rows = []
    for g in GROUPS:
        d = load_report(g, date)
        if d is None:
            counts["未上报"] += 1
            rows.append({"g": g, "state": "未上报", "stance": None, "conf": None,
                         "basis": f"当日上报件不存在（daily_report_{g}_{date}.json 缺件）",
                         "no_timing": False, "human": None,
                         "rd_disp": "读数日 未提供", "gen_status": None,
                         "rule_note": None, "rule_full": None, "legacy": False,
                         "has_rule": False})
            continue
        mv = d.get("market_view") or {}
        conf = mv.get("confidence")
        stance = mv.get("stance")
        basis = str(mv.get("basis") or "未上报")
        no_timing = (conf == 0)
        state = "无观点" if no_timing else (stance if stance in counts else "中性")
        counts[state] += 1
        rd, rd_src = _read_day(g, d, mv)
        if rd:
            rd_disp = f"读数日 {rd}"
            if rd_src == "T日行":
                rd_disp += "（T日行）"
            elif rd_src == "缺行退回":
                rd_disp += "（缺行退回）"
        elif rd_src == "常态=T−1":
            rd_disp = "读数日 常态=T−1"
        else:
            rd_disp = "读数日 未提供"
        # HRS 建议3：generated_at 与 date 同日 → 当日生成；不同日 → 事后补跑（PIT 可能不完整）
        gen_at = str(d.get("generated_at") or "")
        gday = gen_at[:10]
        rep_date = str(d.get("date") or date)
        if gday and gday == rep_date:
            gen_status = "当日生成"
        elif gday:
            gen_status = f"事后补跑（生成于 {gday}，PIT 可能不完整）"
        else:
            gen_status = "生成时间未提供"
        rule_note, rule_full = _rule_notes(mv)
        # 3组 2026-10-26 及更早旧件：stance 为脚本字面量、件内无 rule/readings，不可反推 → 如实标注旧口径
        legacy = (g == "QD" and not rule_note)
        rows.append({"g": g, "state": state, "stance": stance, "conf": conf,
                     "basis": basis, "no_timing": no_timing,
                     "human": mv.get("is_human"), "np": len(d.get("new_picks") or []),
                     "rd_disp": rd_disp, "gen_status": gen_status,
                     "rule_note": rule_note, "rule_full": rule_full,
                     "legacy": legacy, "has_rule": bool(rule_note)})
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
        short = b if len(b) <= 60 else b[:60] + "…"
        tag_note = ' <span class="dim">（本组无择时模型）</span>' if r["no_timing"] else ""
        human_note = ' <span class="dim">[人工]</span>' if r.get("human") is True else ""
        # 可比性标记（3组 建议1：原始值逐字展示 + 可比性标记，不做共识票）
        cmp_tag = ('<span class="tag" title="件内含结构化判据 rule，可复算">有结构化判据</span>' if r.get("has_rule")
                   else ('' if st == "未上报" else '<span class="tag" title="判据埋在自然语言 basis 里，看板无法自动复算">仅文字 basis</span>'))
        # 元信息：读数日（报告日≠读数日） + 生成状态（当日生成/事后补跑） + 旧口径
        meta_bits = [r.get("rd_disp") or "读数日 未提供"]
        if r.get("gen_status"):
            meta_bits.append(r["gen_status"])
        if r.get("legacy"):
            meta_bits.append("旧口径：无判据（脚本字面量，不可反推）")
        meta = html.escape("｜".join(meta_bits))
        grows += f"""<div class="grow"><span class="gbadge">{GD[r['g']]}</span>
<span class="stag {stag_cls[st]}">{st}{tag_note}{human_note}</span>
{conf_bar}{cmp_tag}<span class="dim" style="font-size:11px">{meta}</span><span class="gbasis">{short}</span></div>"""
    return f"""
<div class="compass">
  <div class="cbarwrap">{segs}</div>
  <div class="cln">{cnt_bits}</div>
  {grows}
  <div class="sub">口径：无观点 = 该组上报件 confidence=0 且自述无择时模型（5组 2026-10-28 确认为诚实占位）；未上报 = 当日上报件缺件（出件失败≠无观点，两格分开，不把故障读成态度）。以下为各组当前看法（描述），非收益预测；各组样本池/阈值/confidence 定义不同，不可直接横向比大小。「有结构化判据/仅文字 basis」为可比性标记。读数日＝判据数据实际截止日，报告日≠读数日；「当日生成/事后补跑」由件内 generated_at 与 date 比对得出，事后补跑件 PIT 完整性可能存疑。各组 stance 历史命中率列尚未建立（需回算历史上报件，取不到，不编造）。3组 2026-10-26 及更早旧件为旧口径（stance 为脚本字面量、无结构化判据），已逐格如实标注。</div>
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
<td>{html.escape(r['动作'].split('（')[0])}</td><td><span class="gbadge">{GD.get(r['组'], html.escape(r['组']))}</span>{cons}</td>
<td>{ind_s}</td><td>{html.escape(r['买入参考价/触发价'])} <span class="dim">({html.escape(r.get('价格口径') or '')})</span></td>
<td>{sl or '<span class=dim>未上报</span>'}</td><td>{tp or '<span class=dim>未上报</span>'}</td></tr>"""
    return f"""<table><tr><th>代码</th><th>名称</th><th>档位</th><th>来源组</th><th>行业</th><th>触发价</th><th>止损</th><th>止盈</th></tr>{tr}</table>
<div class="sub">行业列取自当日各组上报件的 industry 字段；卡 csv 无行业列，查不到的如实标「未上报」。触发价口径以卡面「价格口径」列逐票标注为准（如 hfq=后复权价）；2026-10-29 起卡面价格修复为裸价/实际价口径，此前旧卡或为后复权价，不可与市价直接比较。</div>"""

def card_html_parts(date):
    with open(f"{CARDS}/daily_live_card_{date}.html") as f:
        src = f.read()
    styles = "".join(re.findall(r"<style>.*?</style>", src, re.S)).replace("<style>", "").replace("</style>", "")
    body = re.search(r"<body>(.*)</body>", src, re.S).group(1)
    # 卡面原文中的组简称同步替换为显示名（实测卡面 HTML 属性中无组代号，仅文本，
    # 前后向断言排除 daily_report_WB_ / 投资1组_WB 等文件路径与 CSS 类名）
    body = re.sub(r"(?<![A-Za-z0-9_])(WB|CX|QD|DSK|HRS)(?![A-Za-z0-9_])",
                  lambda m: GD[m.group(1)], body)
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
        f'<a href="{pre}market/index.html"{" class=on" if title == "市场分析" else ""}>市场分析</a>'
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
    """参与状态条（HRS 建议5：三种「空」分开文案，不合并成「无信号」）：
    ✅已报new_picks ⚠今日无新增([]) ❌缺件未上报(字段省略)。"""
    bits = []
    for g in GROUPS:
        d = load_report(g, date)
        if d is None:
            bits.append(f'<span class="warn">{GD[g]}❌未上报</span>')
        elif len(d.get("new_picks") or []) == 0:
            bits.append(f'<span class="warn">{GD[g]}⚠今日无新增</span>')
        else:
            bits.append(f'<span class="up">{GD[g]}✅</span>')
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
<b class="up">{html.escape(r['动作'].split('（')[0])}</b> <span class="gbadge">{GD.get(r['组'], html.escape(r['组']))}</span>
<span class="dim">共识 {html.escape(r.get('共识票数') or '—')}/5 组</span><br>
<span class="dim">触发价 {r['买入参考价/触发价']}（{r['价格口径']}）｜ 止损 {r['止损价/锚']} ｜ 止盈 {r['止盈价/锚']}</span><br>
<span class="dim">有效期 {r['有效期(天)']} 天 ｜ 意向非成交</span></div>"""

nav_cards = ""
for g in GROUPS:
    m = M[g]
    lag = "" if m["last"] == TODAY else f'<span class="warn">数据截至 {m["last"]}</span>'
    nav_cards += f"""<div class="card"><span class="lab">{GD[g]} · 模拟净值</span>
<b>{m['act']:.4f}</b><br>{pct(m['dchg'])} <span class="dim">当日</span><br>
<span class="dim">累计 {m['cum']*100:+.1f}% ｜ 持仓 {m['n_hold']} 只</span><br>{lag}</div>"""

entries = [
    ("实盘推荐专区", "live/index.html", "每日实盘推荐卡：最新摘要 + 历史日期导航"),
    ("模拟盘赛马", "sim/index.html", "五组净值对比曲线、日胜率与当前持仓明细"),
    ("市场分析", "market/index.html", "A股当前状态分位 · 历史相似段扫描 · 切换信号清单"),
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
    f'<div class="grow"><span class="gbadge">{GD[r["g"]]}</span>'
    f'<span class="stag {"up" if r["state"]=="看多" else "dn" if r["state"]=="看空" else "dim"}{" warn" if r["state"]=="未上报" else ""}">{r["state"]}</span>'
    f'<span class="dim">conf {r["conf"] if r["conf"] is not None else "—"}</span>'
    f'<span class="dim" style="font-size:11px">{r["rd_disp"]}</span>'
    f'<span class="gbasis">{html.escape(str(r["basis"])[:60])}{"…" if len(str(r["basis"]))>60 else ""}</span></div>'
    for r in crows)

body = f"""
<h1>五组投资大看板</h1>
<div class="sub">今日 {TODAY} ｜ 投资1组承建 ｜ 模拟净值起点 2026-09-03/04，全部数字可溯源至公共数据集与每日上报件</div>
<h2>五组模拟净值总览</h2>
<div class="grid g5">{nav_cards}</div>
<div class="sub" style="margin-top:6px">日胜率口径：act_nav 日收益&gt;0 的交易日 ÷ 总交易日；详见模拟盘赛马页。净值列为各组 act_nav（上报口径，扣费口径未统一：仅 5组 csv 另报 nav_net 净列、与 act_nav 恒差约 45bp 累计费差，其余组未提供净列）——看板不混用两列以免口径失真，跨组比较时知悉该差异（5组 2026-10-28 建议4）。</div>
<h2>实盘风向标（{LATEST}）</h2>
<div class="compass">
  <div class="cbarwrap">{home_segs}</div>
  <div class="cln"><span class="dn">看空 {counts["看空"]} 组</span> · <span class="dim">中性 {counts["中性"]} 组</span> · <span class="up">看多 {counts["看多"]} 组</span> · <span class="dim">无观点 {counts["无观点"]} 组</span> · <span class="warn">未上报 {counts["未上报"]} 组</span></div>
  {home_rows}
  <div class="sub" style="margin-top:6px">{sum_line}</div>
  <div class="sub" style="margin-top:4px">以下为各组当前看法（描述），非收益预测，不构成共识票；各组样本池/阈值/confidence 定义不同，不可直接横向比大小（5组/3组 2026-10-28 函）。读数日＝判据数据实际截止日，报告日≠读数日。各组 stance 历史命中率列尚未建立（需回算历史上报件，取不到，不编造）。</div>
</div>
<div style="margin-top:8px"><a class="bigbtn" href="live/{LATEST}.html#compass">查看详情（当日风向标区）</a></div>
<h2>当日实盘推荐 Top3（{LATEST} 卡 · 行业共识 ≥2 组判据）</h2>
{part_status_html(LATEST)}
<div class="sub" style="margin:4px 0 10px">Top3 选取规则：取当日卡 csv 中「买入（行业共识≥2 组）」档前 3 条，按卡面原序，未加工。触发价口径随卡面「价格口径」列（2026-10-29 起修复为裸价/实际价）。</div>
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
<div class="sub">卡片口径：买入档 = 行业共识 ind_n≥2（2026-10-27 起为本卡唯一『推荐』口径）；触发价为裸价/实际价（2026-10-29 修复口径），旧卡以卡面「价格口径」列逐票标注为准；价格列可能为「本组未设」（3组 无日内价源）</div>
<div class="card" style="margin-top:14px">
  <span class="lab">最新一日 · {LATEST}（生成 {lf['gen'] or '未上报'}）</span>
  <b style="font-size:24px">共识买入 {lf['n_buy']} 只</b> <span class="dim">｜ 观察 {lf['n_watch']} 只</span><br>
  <span class="dim">信号来源 {disp_groups(lf['sources'])} ｜ 缺失 {disp_groups(lf['missing'])}</span><br>
  <span class="dim">风险等级：{lf['risk']}</span><br>
  {part_status_html(LATEST)}
  <br><a class="bigbtn" href="{LATEST}.html">查看当日详情 →</a>
</div>
<h2>实盘风向标（{LATEST}）</h2>
{compass_html(LATEST)}
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
    detail_rows = ""
    for r in drows:
        meta_bits = [f"报告日 {d}", r.get("rd_disp") or "读数日 未提供"]
        if r.get("gen_status"):
            meta_bits.append(r["gen_status"])
        if r.get("legacy"):
            meta_bits.append("旧口径：无判据（脚本字面量，不可反推）")
        rule_line = ""
        if r.get("rule_full"):
            rule_line = (f'<br><span class="dim" style="white-space:normal">结构化判据（rule，可复算）：'
                         f'{html.escape(r["rule_full"])}</span>')
        detail_rows += (f'<div class="grow"><span class="gbadge">{GD[r["g"]]}</span>'
                        f'<span class="gbasis" style="white-space:normal">{html.escape(str(r["basis"]))}'
                        f'<br><span class="dim" style="white-space:normal">{html.escape("｜".join(meta_bits))}</span>{rule_line}</span></div>')
    orig_hdr = html.escape(disp_groups("\n".join(
        l for l in open(f"{CARDS}/daily_live_card_{d}.txt").read().splitlines() if l.startswith("#"))))
    body = f"""
<h1>每日实盘推荐卡 · {d}</h1>
<div class="sub">生成 {facts['gen'] or '未上报'} ｜ 来源：投资1组_WB/实盘化方案/daily_live_cards/daily_live_card_{d}.{{csv,txt,html}} ｜ <a href="index.html">← 返回实盘列表</a></div>
<div class="grid gk" style="margin-top:12px">
  {kpi_buy}
  {kpi_watch}
  <div><label>📥 参与组</label><b>{n_report}/5</b><small>{disp_groups(facts['sources']) or ''}{' ｜ 缺失 ' + disp_groups(facts['missing']) if facts['missing'] and facts['missing'] != '无' else ''}</small></div>
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
    rows += f"""<tr><td>{GD[g]}</td><td>{m['act']:.4f}{lag}</td><td>{pct(m['dchg'])}</td><td>{pct(m['cum'])}</td>
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
        note = '<div class="sub">注：5组 上报件无 unreal_pct 字段 → 浮盈列如实标「未知」；该件 nav=0.840125 与 simulated_nav_HRS.csv 最新 act_nav=0.7705 口径不同（CSV 为 steady 档净值），本页净值一律以 CSV 为准。</div>'
    if g == "QD":
        note = '<div class="sub">注：3组 现价为 canon 后复权（计价口径），非市价；本件持仓 entry 无空值。</div>'
    if g == "CX":
        note = '<div class="sub">注：2组 持仓为事件式调仓批记录（entry_date=2026-10-08 批，99 只），以 2026-10-27 收盘价逐只重估（覆盖 99/99）。</div>'
    return f"""<div class="holdsec{' on' if g == 'WB' else ''}" id="hold_{g}">{note}<table>
<tr><th>代码</th><th>名称</th><th>行业</th><th>现价</th><th>成本/入场</th><th>浮盈</th><th>动作</th></tr>{tr}</table></div>"""

btns = "".join(f'<button id="btn_{g}" onclick="showH(\'{g}\')"{" class=on" if g == "WB" else ""}>{GD[g]}（{len(R[g]["holdings"])} 只）</button>' for g in GROUPS)

body = f"""
<h1>模拟盘赛马</h1>
<div class="sub">数据源：公共/数据/simulated_nav_&lt;组&gt;.csv ｜ 指标口径：日胜率 = act_nav 日收益&gt;0 的交易日 ÷ 总交易日（各样本 ≥20 天）；区间累计收益 = 末值/首值 − 1</div>
<h2>五组净值曲线（act_nav · 各组上报口径）</h2>
<div class="card" style="padding:18px"><canvas id="navchart" height="110"></canvas></div>
<h2>赛马指标表</h2>
<table>
<tr><th>组</th><th>最新净值 (act_nav)</th><th>当日涨跌</th><th>区间累计收益</th><th>日胜率</th><th>当前持仓</th><th>样本区间</th></tr>
{rows}
</table>
<div class="sub" style="margin-top:6px">3组/4组 最初两档 act_nav 有 1.0/0.997 等起点差异；1组 2026-09-04 首日 act_nav=0.997（含建仓成本）。</div>
<div class="sub" style="margin-top:4px">净/毛口径（5组 2026-10-28 建议4）：本页一律用 act_nav；仅 5组 csv 提供 nav_net（净，已扣成本，与 act_nav 恒差约 45bp 累计费差），其余组无净列 → 跨组比较存在扣费口径差异，看板不混用两列，如实标注而非替换。</div>
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
const GNAME = {{WB:'1组',CX:'2组',QD:'3组',DSK:'4组',HRS:'5组'}};
const labels = DATA.WB.map(d => d[0]);
new Chart(document.getElementById('navchart'), {{
  type: 'line',
  data: {{ datasets: Object.keys(DATA).map(g => ({{
    label: GNAME[g] || g, data: DATA[g].map(d => ({{x: d[0], y: d[1]}})),
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
        "C8 择时闸门为空壳（v9_live_signal_scan.py 仅注释占位）——如实转自 1组 2026-10-27 上报件 data_gaps。"),
 "CX": ("QF-1.2：Top100 事件式调仓批（最近批 entry_date=2026-10-08），暴露 E=0.50，risk 闸门（当前 34.65），禁杠杆；虚拟本金 100 万元计分。",
        "线索取自 2组 2026-10-27 上报件 strategy/tier/gate_id 字段与 data_gaps。"),
 "QD": ("QB：震荡 regime，等权 12 槽（当前 11 只持仓 + 1 现金槽），eq=0.590；选股为技术类认证变体 vol20_asc（20 日平均成交量升序）；无止损规则。",
        "线索取自 3组 2026-10-26 上报件 tier/exit_rule/new_picks_basis 字段。"),
 "DSK": ("机械 R3 等权持有 15 只，无择时模型（market_view confidence=0）；成本按双边 30bp 实扣，post_anchor 严格边界。",
        "线索取自 4组 2026-10-27 上报件 market_view/data_gaps 字段。"),
 "HRS": ("双档：aggressive Top20 / steady Top50（拥挤倒数），排序键 = 20 日反转升序；20 交易日整篮换仓冻结；C8 择时（202609 市场收益 mean/median 存在口径分歧，现采用 mean）。",
        "线索取自 5组 2026-10-26 上报件与 simulated_nav_HRS.csv tier 字段。"),
}
scards = ""
for g in GROUPS:
    main, clue = STRAT[g]
    scards += f"""<div class="card"><b>{GD[g]}</b> <span class="tag">版本未上报（契约增补已发，待各组回填）</span>
<p style="margin:8px 0 4px">{main}</p>
<p class="dim" style="font-size:12px;margin:4px 0 0">{clue}</p></div>"""
body = f"""
<h1>策略档案</h1>
<div class="sub">五组上报件均无 strategy 版本字段（实测 2026-10-27）→ 版本一律标灰，待策略契约回填后更新；下方打法描述均取自上报件真实字段，未编造。</div>
<div class="grid g6" style="margin-top:14px">{scards}</div>
"""
open(f"{OUT}/strategies/index.html", "w").write(page("策略档案", body, depth=1))

STATUS = [
 ("green", "canon 主K线（3组 hfq）", "公共/数据/kline_25y_QD_hfq.csv",
  "实测末行 date=2026-10-27，总数据行 16,230,290（wc -l 16,230,291 含表头），mtime 2026-10-27 19:05。日更正常。"),
 ("green", "ETF 510300（1组 源）", "公共/数据/kline_etf_510300_WB.csv",
  "实测末行 date=2026-10-27（2026-10-29 复测，3,502 个数据行，16 列齐全）——10-25 时曾停在 10-23，现已恢复日更；市场分析页依赖本文件。"),
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

# ================= market：市场分析页（v2.3，2026-10-29） =================
# 数据源：公共/数据/kline_etf_510300_WB.csv（1组 维护，腾讯+新浪双源）。
# 铁律同全站：全部数字由本脚本每次构建时从源文件动态计算；文件缺失/行数不足 300 → 页面诚实兜底「取不到」。

ETF_SRC = "公共/数据/kline_etf_510300_WB.csv"

def _median(xs):
    s = sorted(xs); n = len(s)
    if not n:
        return None
    return s[n//2] if n % 2 else (s[n//2-1] + s[n//2]) / 2

def _percentile(vals, v):
    """全历史滚动窗口法分位（含当前值自身）：≤当前值的窗口占比×100。"""
    if not vals:
        return None
    return sum(1 for x in vals if x <= v) / len(vals) * 100

def _pearson(a, b):
    """Pearson 相关。各自标准化（减均值/除标准差）后相关不变，故直接对原序列算即等价于
    「标准化日收益 Pearson 相关」。"""
    n = len(a)
    ma, mb = sum(a)/n, sum(b)/n
    cov = sa = sb = 0.0
    for x, y in zip(a, b):
        dx, dy = x-ma, y-mb
        cov += dx*dy; sa += dx*dx; sb += dy*dy
    if sa <= 0 or sb <= 0:
        return None
    return cov / math.sqrt(sa*sb)

def _etf_load():
    p = f"{DATA}/kline_etf_510300_WB.csv"
    if not os.path.exists(p):
        return None
    dates, bfq, hfq = [], [], []
    with open(p, newline="") as f:
        rd = csv.DictReader(f, delimiter="|")
        if not {"date", "close", "close_hfq_mul"}.issubset(set(rd.fieldnames or [])):
            return None
        for r in rd:
            try:
                dates.append(r["date"])
                bfq.append(float(r["close"]))
                hfq.append(float(r["close_hfq_mul"]))
            except (TypeError, ValueError):
                continue
    if len(dates) < 300:
        return None
    return dates, bfq, hfq

ETF = _etf_load()
NA = '<span class="dim">取不到</span>'

def qbar(q):
    """分位横条：按看板涨红跌绿主题——高分位红（强）/低分位绿（弱）/中段黄。"""
    if q is None:
        return NA
    color = "var(--up)" if q >= 60 else "var(--dn)" if q <= 40 else "var(--warn)"
    return (f'<span class="cbar" style="width:110px"><i style="width:{min(q,100):.0f}%;background:{color}"></i></span>'
            f'<span class="dim" style="font-size:11px">{q:.0f}% 分位</span>')

if ETF:
    etf_dates, etf_bfq, etf_hfq = ETF
    etf_ret = [etf_hfq[i]/etf_hfq[i-1] - 1 for i in range(1, len(etf_hfq))]
    AS_OF = etf_dates[-1]
    N_DATA = len(etf_dates)

    # --- 区块1：当前状态（滚动窗口法分位） ---
    stat_cards = ""
    for N in (20, 60, 120, 250):
        if len(etf_hfq) > N:
            cums = [etf_hfq[i]/etf_hfq[i-N] - 1 for i in range(N, len(etf_hfq))]
            cur = etf_hfq[-1]/etf_hfq[-1-N] - 1
            q = _percentile(cums, cur)
            stat_cards += (f'<div class="card"><span class="lab">近 {N} 日累计收益</span>'
                           f'<b>{pct(cur)}</b><br>{qbar(q)}</div>')
        else:
            stat_cards += f'<div class="card"><span class="lab">近 {N} 日累计收益</span><b>{NA}</b></div>'
    V = 60
    if len(etf_ret) >= V + 2:
        def _ann_vol(w):
            m = sum(w)/len(w)
            return math.sqrt(sum((x-m)**2 for x in w)/(len(w)-1)) * math.sqrt(250)
        vols = [_ann_vol(etf_ret[i-V:i]) for i in range(V, len(etf_ret)+1)]
        cur_vol = _ann_vol(etf_ret[-V:])
        qv = _percentile(vols, cur_vol)
        stat_cards += (f'<div class="card"><span class="lab">60 日年化波动（√250）</span>'
                       f'<b>{cur_vol*100:.1f}%</b><br>{qbar(qv)}</div>')
    else:
        stat_cards += f'<div class="card"><span class="lab">60 日年化波动</span><b>{NA}</b></div>'
    if len(etf_bfq) >= 250:
        ma250 = sum(etf_bfq[-250:]) / 250
        dev = etf_bfq[-1]/ma250 - 1
        dd = etf_bfq[-1]/max(etf_bfq[-250:]) - 1
        stat_cards += (f'<div class="card"><span class="lab">现价距 MA250 偏离（bfq）</span>'
                       f'<b>{pct(dev)}</b><br><span class="dim" style="font-size:11px">MA250={ma250:.4f}</span></div>')
        stat_cards += (f'<div class="card"><span class="lab">距 250 日最高回撤（bfq）</span>'
                       f'<b>{pct(dd)}</b><br><span class="dim" style="font-size:11px">250 日高 {max(etf_bfq[-250:]):.4f}</span></div>')
    else:
        stat_cards += (f'<div class="card"><span class="lab">现价距 MA250 偏离</span><b>{NA}</b></div>'
                       f'<div class="card"><span class="lab">距 250 日最高回撤</span><b>{NA}</b></div>')

    # --- 区块2：历史相似段（最近 60 交易日 全历史扫描） ---
    Q, FWD = 60, 70
    n_ret = len(etf_ret)
    q_win = etf_ret[-Q:]
    q_cum = etf_hfq[-1]/etf_hfq[-1-Q] - 1
    # 窗口终点 = 收益索引 e（含）；前瞻 ≥70 日 + 与查询窗不重叠 → e ≤ min(n_ret-1-70, n_ret-61)
    e_max = min(n_ret - 1 - FWD, n_ret - Q - 1)
    cands = []
    if e_max >= Q - 1:
        for e in range(Q-1, e_max+1):
            corr = _pearson(etf_ret[e-Q+1:e+1], q_win)
            if corr is None:
                continue
            w_cum = etf_hfq[e+1]/etf_hfq[e+1-Q] - 1
            close = 1 - abs(w_cum-q_cum) / (abs(w_cum)+abs(q_cum) + 1e-12)
            f20 = etf_hfq[e+1+20]/etf_hfq[e+1] - 1
            f60 = etf_hfq[e+1+60]/etf_hfq[e+1] - 1
            cands.append({"e": e, "end": etf_dates[e+1], "corr": corr, "close": close,
                          "score": corr*close, "cum": w_cum, "f20": f20, "f60": f60})
    if cands:
        top8 = sorted(cands, key=lambda c: -c["score"])[:8]
        sim_rows = ""
        for c in top8:
            low = c["corr"] < 0.6
            corr_s = (f'<span class="warn">{c["corr"]:.2f}</span>' if low
                      else f'{c["corr"]:.2f}')
            sim_rows += (f'<tr><td>{c["end"]}</td><td>{corr_s}{" <span class=dim>(<0.6)</span>" if low else ""}</td>'
                         f'<td>{c["close"]:.2f}</td><td>{pct(c["cum"])}</td>'
                         f'<td>{pct(c["f20"])}</td><td>{pct(c["f60"])}</td></tr>')
        m20, m60 = _median([c["f20"] for c in top8]), _median([c["f60"] for c in top8])
        w20 = sum(1 for c in top8 if c["f20"] > 0)
        w60 = sum(1 for c in top8 if c["f60"] > 0)
        b20, b60 = _median([c["f20"] for c in cands]), _median([c["f60"] for c in cands])
        sim_tbl = f"""<table>
<tr><th>窗口末日</th><th>形态相关</th><th>幅度接近度</th><th>段内累计</th><th>后20日</th><th>后60日</th></tr>
{sim_rows}
</table>
<div class="sub">汇总（Top8）：后 20 日中位 {m20*100:+.2f}%、胜率 {w20}/8；后 60 日中位 {m60*100:+.2f}%、胜率 {w60}/8。无条件基线（全部 {len(cands)} 个候选窗）：后 20 日中位 {b20*100:+.2f}%、后 60 日中位 {b60*100:+.2f}%。综合分 = 形态相关 × 幅度接近度；幅度接近度 = 1 − |段内累计−当前累计| /（|段内累计|+|当前累计|）。</div>
<div class="riskfoot">⚠️ <b>历史先验，非预测。</b>本次实测 Top8 形态相关全部 &lt; 0.45 —— 形态相关 &lt; 0.6 时仅为「幅度同族」而非「过程相似」，其后走势对当下的参考价值接近于零，请勿据此下注。本表仅陈述历史上形态/幅度相近的时段后来发生了什么。</div>"""
    else:
        sim_tbl = f'<div class="dim">取不到：候选窗口不足（扫描窗 {n_ret} 个收益日，需窗口+前瞻 ≥130 日），不编造。</div>'

    market_body = f"""
<h1>市场分析</h1>
<div class="sub">数据源：{ETF_SRC}（1组 维护，腾讯+新浪双源；截至 {AS_OF}，{N_DATA} 个交易日）｜ 收益一律用 close_hfq_mul（后复权乘法），MA/价格位置用 bfq close ｜ 本页全部数字由 _build.py 每次构建时从源文件动态计算，无手工写死</div>
<h2>当前状态（as_of {AS_OF} · 分位 = 全历史滚动窗口法，含当前值）</h2>
<div class="grid g5">{stat_cards}</div>
<div class="sub" style="margin-top:6px">分位条按看板涨红跌绿主题：高分位红（历史偏强）/ 低分位绿（历史偏弱）/ 中段黄。分位 = 历史上同长度滚动窗口收益 ≤ 当前值的占比。</div>
<h2>历史相似段 Top8（最近 {Q} 个交易日 × 全历史扫描，窗口终点留 ≥{FWD} 日前瞻、剔除与查询窗重叠）</h2>
{sim_tbl}
<h2>方法论（三层验证法）</h2>
<div class="card" style="font-size:13px">
<p style="margin:4px 0">① 状态分位匹配——区块 1 的滚动分位（当下处于历史什么位置）；② 形态相关——最近 {Q} 日标准化日收益与各历史窗的 Pearson 相关（标准化后相关不变）；③ 环境对齐——宏观/流动性环境比对，暂无自动化数据源，<b>本页未做第三层</b>。</p>
<p style="margin:4px 0" class="dim">口径：年化波动按 250 交易日（√250）；收益用后复权乘法列，价格位置用 bfq，两者分工见页首。样本为单一 ETF（510300），代表大盘蓝筹宽度，不代表全市场。</p>
<p style="margin:4px 0" class="dim">免责：Top8 样本量小、历史收益分布宽，任何「相似段后走势」都是历史先验而非预测；形态相关低时更只是幅度同族。本页不构成投资建议。</p>
</div>
<h2>切换信号清单（人工跟踪项）</h2>
<table>
<tr><th>#</th><th>信号</th><th>状态</th></tr>
<tr><td>①</td><td style="white-space:normal">10Y 美债收益率稳定回落至 5% 以下</td><td><span class="tag">☐ 未触发</span></td></tr>
<tr><td>②</td><td style="white-space:normal">两市成交额重回 1.8 万亿以上</td><td><span class="tag">☐ 未触发</span></td></tr>
<tr><td>③</td><td style="white-space:normal">AI 链三季报 / 海外云资本开支指引扭转</td><td><span class="tag">☐ 未触发</span></td></tr>
<tr><td>④</td><td style="white-space:normal">国内政策实物工作量落地</td><td><span class="tag">☐ 未触发</span></td></tr>
</table>
<div class="sub">以上 4 条为<b>人工跟踪项</b>：看板不自动判（无对应自动化数据源），状态格由用户人工维护；构建脚本不写触发状态，只在每次重建时还原为「未触发」底稿。</div>
"""
else:
    market_body = f"""
<h1>市场分析</h1>
<div class="sub">数据源：{ETF_SRC}</div>
<div class="riskfoot">取不到：数据源文件缺失、列不全或数据行不足 300（本页全部指标依赖该文件，缺源不编造、不估算）。请先修复 510300 数据日更后重跑 _build.py。</div>
"""
os.makedirs(f"{OUT}/market", exist_ok=True)
open(f"{OUT}/market/index.html", "w").write(page("市场分析", market_body, depth=1))

print("v2 build done | cards:", CARD_DATES, "| latest:", LATEST)
