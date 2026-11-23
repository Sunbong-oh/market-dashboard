"""저점신호 (/bottom/) — 폭락장 지수 저점 판별. 사이트를 만들 때마다 다시 계산한다.

계산은 bottom_signals.py(= .claude/skills/market-bottom-signals/scripts/bottom_signals.py 와 같은 파일)의 compute().
  ① 투매형: 풋콜(Cboe 주식+ETP, CNN 근사) 5일 평균 1.0 이상 → VIX 장중 고점에서 15% 이상 꺾임
  ② 다이버전스형: 1차 폭락 저점을 종가로 깨는데 VIX 장중 고점과 풋콜 5일 평균 고점이 1차 때보다 낮음
  ③ 자금시장 필터: 금융CP 3개월 − T-bill 3개월 5일 평균 0.5%p 미만일 때만 ①② 신뢰(1.0%p 이상이면 불신)
"""
import json
from datetime import datetime, timedelta, timezone
from html import escape
from risk_page import CSS as RISK_CSS
import bottom_signals

KST = timezone(timedelta(hours=9))
PUBLIC = True  # False 면 메뉴·홈 줄 없이 /bottom/ 주소로만 열린다(build_site.py MENU 도 같이)
HOME_PC_MIN = 0.9  # 홈 저점신호기 칸은 풋콜(Cboe 주식+ETP, CNN 근사) 5일 평균이 이 값 이상일 때만 보인다(사용자 지시 2026-11-23). 신호가 켜져도 이 값 미만이면 숨김(사용자 선택)
DAYS = 150     # 화면에 쓰는 기간(달력일). 기준 저점은 최근 5거래일을 뺀 직전 60거래일의 최저 종가로 자동 선택

EXTRA_CSS = """
.rk .go{border-color:var(--grn)}.rk .go .lamp{background:var(--grn)}.rk .go .t{color:var(--grn)}
.rk .fear{border-color:var(--red)}.rk .fear .lamp{background:#E8798A}.rk .fear .t{color:var(--red)}
.rk .veto{border-color:var(--red)}.rk .veto .lamp{background:var(--red)}.rk .veto .t{color:var(--red)}
.rk .two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.rk .two>div{min-width:0}
.rk .cap{font-size:13px;font-weight:700;margin:2px 0 6px}
.rk .note{font-size:12.5px;color:var(--mut);line-height:1.65;margin:10px 0 0}
.rk td.y{background:#FDF3D7;font-weight:700}
.rk .lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mut);margin:6px 0 0}
.rk .lg i{display:inline-block;width:14px;height:3px;vertical-align:4px;margin-right:5px}
.rk .ladw{display:flex;flex-direction:column;gap:6px}
.rk .lad{display:flex;align-items:center;gap:12px;padding:8px 12px;border:1px solid var(--ln);border-radius:6px;background:#fff;color:#A8A294}
.rk .lad i{width:18px;height:18px;border-radius:50%;flex:none;background:#D9D4C7}
.rk .lad .t{font-size:15px;font-weight:700}
.rk .lad.cur{border-width:2px;padding:12px;color:var(--ink,#3D3A35)}
.rk .lad.cur i{width:34px;height:34px;animation:bsblink 1.2s ease-in-out infinite}
.rk .lad.cur .t{font-size:21px;font-weight:900}
.rk .lad .s{font-size:13.5px;color:var(--mut);margin-top:3px;line-height:1.55}
.rk .sit{margin:12px 0 4px;padding:12px 14px;background:#fff;border:1px solid var(--ln);border-radius:6px}
.rk .sit h3{margin:0 0 6px;font-size:15px;font-weight:900;color:#3D3A35}
.rk .sit h3 small{font-weight:500;color:var(--mut);font-size:12px;margin-left:6px}
.rk .sit p{margin:0 0 7px;font-size:14px;line-height:1.7}
.rk .sit p:last-child{margin:0}
.rk .lad .now{display:inline-block;font-size:12px;font-weight:800;color:#fff;background:#3D3A35;border-radius:3px;padding:1px 6px;vertical-align:3px}
@media(max-width:640px){.rk .cov,.rk .two{grid-template-columns:1fr}.rk .sw .t{font-size:20px}}
"""

LV = {
    "go_cap": ("🟢 투매형 바닥 가능성", "풋콜 5일 평균이 1.0을 넘은 뒤 VIX가 고점에서 꺾였고, 자금시장도 정상입니다. 재시험(다이버전스)이 올 수 있어 나눠서 대응합니다."),
    "go_div": ("🟢 다이버전스 바닥 가능성", "전저점을 깼는데 VIX와 풋콜 고점은 1차 폭락보다 낮고, 자금시장도 정상입니다. 2011년 10월·2022년 10월과 같은 모양입니다."),
    "veto": ("🔴 바닥 신호 무효 (자금시장 경색)", "투매형이나 다이버전스 조건은 맞았지만, 금융CP − T-bill 스프레드가 1%p를 넘어 금융 시스템이 막혀 있다는 뜻이라 믿지 않습니다. 2008년 3·7·11월에는 이 상태의 신호가 모두 중간 저점이었습니다."),
    "fear": ("🟠 공포 확산 중", "가격이 1차 폭락 저점을 깨면서 VIX와 풋콜도 더 높아졌습니다. 아직 바닥 모양이 아닙니다. 새 고점을 다음 비교 기준으로 삼습니다."),
    "wait": ("🟡 재시험 대기", "1차 폭락 뒤 아직 저점을 다시 깨지 않았습니다. 다시 깰 때 VIX·풋콜이 기준선보다 낮은지 봅니다."),
}

ORDER = ["fear", "wait", "go_cap", "go_div", "veto"]  # 단계 표에 보이는 순서
LV_COLOR = {"go_cap": "#2E7D4F", "go_div": "#2E7D4F", "veto": "#C8102E", "fear": "#E67E22", "wait": "#F2A900"}
LV_SHORT = {"fear": "공포 확산 중", "wait": "재시험 대기", "go_cap": "투매형 바닥 가능성", "go_div": "다이버전스 바닥 가능성", "veto": "바닥 신호 무효(자금시장 경색)"}
BLINK_CSS = ("@keyframes bsblink{0%,100%{opacity:1}50%{opacity:.25}}"
             "@media(prefers-reduced-motion:reduce){.bsb{animation:none!important}}")


def ladder(lv):
    """판정 다섯 단계를 모두 보여 주고, 지금 판정만 색깔을 넣어 깜빡이게 한다. 나머지는 회색."""
    out = []
    for k in ORDER:
        label, sub = LV[k]
        name = label.split(" ", 1)[1]  # 앞의 색 동그라미 이모지는 빼고 점등으로 표시
        if k == lv:
            c = LV_COLOR[k]
            out.append(f'<div class="lad cur" style="border-color:{c}"><i class="bsb" style="background:{c}"></i>'
                       f'<div><div class="t" style="color:{c}">{escape(name)} <span class="now">지금</span></div><div class="s">{escape(sub)}</div></div></div>')
        else:
            out.append(f'<div class="lad"><i></i><div><div class="t">{escape(name)}</div></div></div>')
    return '<div class="ladw">' + "".join(out) + "</div>"


def _pct(a, b):
    return (a / b - 1) * 100


def where(j):
    """(지금 종가, 날짜, 1차 저점 대비 %, ref, new) — 상황 설명용."""
    d = j["signals"]["divergence"]
    ref, new = d.get("ref_low") or {}, d.get("new_low") or {}
    last = [r for r in j["rows"] if r.get("index_close") is not None][-1]
    return last["index_close"], last["date"], _pct(last["index_close"], ref["close"]) if ref else None, ref, new


def fear_word(ref, new):
    """1차 폭락 때와 비교해 겁(VIX 장중 고점·풋콜 5일 고점)이 커졌는지 한 마디로."""
    up_v, up_p = new.get("vix_high", 0) >= ref.get("vix_high", 0), new.get("pc5", 0) >= ref.get("pc5", 0)
    if up_v and up_p:
        return "겁은 1차 때보다 더 커졌습니다"
    if not up_v and not up_p:
        return "겁은 1차 때보다 작아졌습니다"
    return "겁은 VIX와 풋콜이 서로 엇갈립니다"


def situation(name, j, us=True, eun="은"):
    """지수 하나의 '지금 상황' 문장들 (사용자 요청 2026-11-23: 상황 설명이 필요). 숫자는 계산 결과 그대로."""
    last, day, pct, ref, new = where(j)
    if not ref:
        return [f"{name}: 비교할 1차 폭락 저점을 찾지 못했습니다."]
    r = f'1차 폭락 저점({_d(ref["date"])} 종가 {ref["close"]:,.1f})'
    out = []
    if new:
        np_ = _pct(new["close"], ref["close"])
        txt = f'<b>{name}</b>{eun} {_d(new["date"])} 종가 {new["close"]:,.1f}로 {r}을 <b>{abs(np_):.1f}% 밑돌았습니다</b>.'
        if new["date"] != day:
            txt += f' 지금({_d(day)})은 {last:,.1f}로 1차 저점보다 {abs(pct):.1f}% {"위" if pct >= 0 else "아래"}입니다.'
        out.append(txt)
        out.append(f'가격은 더 빠졌는데 {fear_word(ref, new)}: VIX 장중 고점 {ref["vix_high"]:.1f} → {new["vix_high"]:.1f}, '
                   f'풋콜 5일 평균 {ref["pc5"]:.3f} → {new["pc5"]:.3f}' + ("" if us else " (미국 기준)") + '.')
    else:
        out.append(f'<b>{name}</b>{eun} 지금({_d(day)}) {last:,.1f}로 {r}보다 <b>{abs(pct):.1f}% 위</b>에 있습니다. 그 저점을 아직 다시 깨지 않았습니다.')
    return out


def summary(lv, spx):
    """판정별 정리 문장(다음에 무엇을 보면 되는지)."""
    s = spx["signals"]
    ref, new = s["divergence"].get("ref_low") or {}, s["divergence"].get("new_low") or {}
    pv = max(new.get("vix_high") or 0, ref.get("vix_high") or 0)
    pp = max(new.get("pc5") or 0, ref.get("pc5") or 0)
    pc = s["capitulation"].get("latest_pc_eqetp_5d")
    fu = s["funding_filter"]
    fund = {"ok": "정상이라 금융 시스템이 막혔다는 신호는 없습니다",
            "caution": "주의 구간이라 신호가 나와도 한 번 더 확인합니다",
            "fail": "1%p를 넘어 금융 시스템이 막혀 있다는 뜻입니다"}[fu["state"]]
    out = []
    if pc is not None:
        out.append(f'풋콜 5일 평균은 지금 {pc:.3f}입니다. ' + (f'투매 기준 1.0까지 {1 - pc:.3f} 남았습니다.' if pc < 1
                   else '투매 기준 1.0을 넘었습니다. 이제 VIX가 장중 고점에서 15% 이상 꺾이는지 봅니다.'))
    out.append(f'자금시장(금융CP − T-bill)은 {fu["cp_tbill_5d"]:.2f}%p로 {fund}.')
    lvl = (new or ref).get("close")
    nxt = {
        "fear": f'가격이 빠질수록 겁도 커지는 중이라 아직 바닥 모양이 아닙니다. 다음에 S&amp;P500이 {lvl:,.1f}를 또 깰 때 VIX 장중 고점이 {pv:.1f} 아래, 풋콜 5일 평균이 {pp:.3f} 아래에 머물면 다이버전스 바닥 가능성으로 바뀝니다. 그 전에 풋콜이 1.0을 넘고 VIX가 꺾이면 투매형 바닥 가능성입니다.',
        "wait": f'1차 저점 위에서 지켜보는 단계입니다. 1차 저점이 진짜 바닥일 수도 있고, 다시 내려와 시험할 수도 있습니다(어느 쪽인지는 아직 알 수 없습니다). 다시 내려와 {lvl:,.1f}를 깰 때 VIX 장중 고점이 {pv:.1f}, 풋콜 5일 평균이 {pp:.3f}보다 낮으면 다이버전스 바닥 가능성입니다.',
    }.get(lv, LV[lv][1])
    out.append("<b>정리:</b> " + nxt)
    return out


def home_line(spx):
    """홈 칸 한 줄 상황: 1차 저점 대비 위치와 겁의 크기."""
    last, day, pct, ref, new = where(spx)
    if not ref:
        return ""
    if new:
        return f'S&amp;P500 1차 저점({_d(ref["date"])})보다 {abs(_pct(new["close"], ref["close"])):.1f}% 아래로 내려갔고, {fear_word(ref, new)}.'
    return f'S&amp;P500이 1차 저점({_d(ref["date"])})보다 {abs(pct):.1f}% 위, 아직 다시 깨지 않았습니다.'


def level(s):
    cap, div, fund = s["capitulation"], s["divergence"], s["funding_filter"]["state"]
    if (cap["met"] or div["met"]) and fund == "fail":
        return "veto"
    if div["met"]:
        return "go_div"
    if cap["met"]:
        return "go_cap"
    if div.get("new_low"):
        return "fear"
    return "wait"


def _d(s):
    return s[2:].replace("-", ".") if s else "-"


def _f(v, fmt="{:.2f}"):
    return "-" if v is None else fmt.format(v)


def svg(rows, key, color, title, refs=(), marks=(), fmt="{:.0f}", W=720, H=230):
    pts = [(i, r[key]) for i, r in enumerate(rows) if r.get(key) is not None]
    if not pts:
        return ""
    vals = [v for _, v in pts] + [v for v, _ in refs]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    pl, pr, pt, pb = 52, 14, 10, 26
    n = len(rows)
    x = lambda i: pl + (W - pl - pr) * i / max(1, n - 1)
    y = lambda v: pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo))
    g = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        g += (f'<line x1="{pl}" x2="{W - pr}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#E6E0D2"/>'
              f'<text x="{pl - 5}" y="{y(v) + 4:.1f}" font-size="12" fill="#6B665D" text-anchor="end">{fmt.format(v)}</text>')
    for v, lab in refs:
        g += (f'<line x1="{pl}" x2="{W - pr}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#C8102E" stroke-dasharray="5 4"/>'
              f'<text x="{W - pr - 4}" y="{y(v) - 5:.1f}" font-size="12" fill="#C8102E" text-anchor="end">{escape(lab)}</text>')
    ticks = "".join(f'<text x="{x(i):.1f}" y="{H - 7}" font-size="12" fill="#6B665D" text-anchor="middle">{rows[i]["date"][5:].replace("-", "/")}</text>'
                    for i in range(0, n, max(1, n // 6)))
    path = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
    mk = ""
    for d, lab in marks:
        i = next((j for j, r in enumerate(rows) if r["date"] == d), None)
        if i is None or rows[i].get(key) is None:
            continue
        cx, cy = x(i), y(rows[i][key])
        anc = "end" if cx > W * 0.7 else "start"
        mk += (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#fff" stroke="#3D3A35" stroke-width="2"/>'
               f'<text x="{cx + (-8 if anc == "end" else 8):.1f}" y="{cy + 18:.1f}" font-size="12.5" font-weight="700" fill="#3D3A35" text-anchor="{anc}" '
               f'paint-order="stroke" stroke="#fff" stroke-width="3">{escape(lab)}</text>')
    lx, ly = x(pts[-1][0]), y(pts[-1][1])
    return (f'<div class="cap">{escape(title)}</div><svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">{g}{ticks}'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round"/>{mk}'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" fill="{color}" stroke="#fff" stroke-width="2"/></svg>')


def check_table(name, j):
    s = j["signals"]
    cap, div, fu, cr = s["capitulation"], s["divergence"], s["funding_filter"], s["credit_filter"]
    ref, new = div.get("ref_low") or {}, div.get("new_low") or {}
    broke = bool(new) and new["close"] < ref["close"]
    vix_ok, pc_ok = div.get("vix_lower_high"), div.get("pc_lower_high")
    mark = lambda ok: "✅" if ok else "⬜"
    rows = [
        (mark(cap["met"]), "① 투매형: 풋콜 5일 평균 1.0 이상 → VIX 고점에서 15% 꺾임", f'최근 {_f(cap.get("latest_pc_eqetp_5d"), "{:.3f}")}', "1.0 이상"),
        (mark(broke), "② 다이버전스 · 전저점 종가 이탈",
         f'{_f(new.get("close"), "{:,.1f}")} ({_d(new.get("date"))})' if new else "아직 없음", f'{_f(ref.get("close"), "{:,.1f}")} ({_d(ref.get("date"))}) 아래'),
        (mark(broke and vix_ok), "② 다이버전스 · VIX 장중 고점이 더 낮음", _f(new.get("vix_high"), "{:.1f}") if new else "-", f'{_f(ref.get("vix_high"), "{:.1f}")} 미만'),
        (mark(broke and pc_ok), "② 다이버전스 · 풋콜 5일 평균 고점이 더 낮음", _f(new.get("pc5"), "{:.3f}") if new else "-", f'{_f(ref.get("pc5"), "{:.3f}")} 미만'),
        ("✅" if fu["state"] == "ok" else "⚠️" if fu["state"] == "caution" else "❌", "③ 자금시장: 금융CP − T-bill 5일 평균", f'{_f(fu["cp_tbill_5d"])}%p', "0.5%p 미만"),
        ("ℹ️", "참고: 하이일드 OAS / Baa−10년", f'{_f(cr.get("hy_oas"))}% / {_f(cr.get("baa10y"))}%p', "4.0% 미만이면 평온"),
    ]
    kr = s.get("kr_foreign_put_sell")
    if kr:
        lt, wo = kr.get("latest") or ["", None], kr.get("worst") or ["", None]
        rows.insert(5, ("✅" if kr["hits"] else "⬜", "④ 국내: 외국인 코스피200 풋옵션 하루 순매도",
                        f'{lt[1]:+,}억 ({_d(lt[0])})' + (f' · 최대 {wo[1]:+,}억 ({_d(wo[0])})' if wo[1] is not None else ""), f'{kr["threshold_eok"]:,}억 이하'))
    body = "".join(f'<tr><td>{a}</td><td class="l">{escape(b)}</td><td>{escape(c)}</td><td>{escape(d)}</td></tr>' for a, b, c, d in rows)
    return f'<div class="cap">{escape(name)}</div><div class="tw"><table class="chk"><tr><th></th><th>조건</th><th>지금</th><th>기준</th></tr>{body}</table></div>'


CASES = [
    ("2009.03.09", "S&P500", "다이버전스", "81.5 → 52.0", "1.03 → 0.84", "0.42", "바닥", 1),
    ("2011.09.26", "코스피", "다이버전스", "48.0 → 43.9", "0.93 → 0.73", "0.25", "바닥(전저점 1,684 → 1,644 이탈 후 반등)", 1),
    ("2011.10.03", "S&P500", "다이버전스", "48.0 → 46.9", "0.93 → 0.81", "0.25", "바닥", 1),
    ("2022.10.12", "S&P500", "다이버전스", "35.1 → 34.5", "1.10 → 0.94", "0.16", "바닥(6월 투매 뒤 재시험)", 1),
    ("2025.04.08", "S&P500", "투매", "60.1", "1.04", "0.10", "바닥", 1),
    ("2020.03.23", "S&P500", "투매", "85.5", "1.23", "1.12", "바닥(연준 무제한 유동성 발표, 예외)", 1),
    ("2008.03.17", "S&P500", "투매", "35.6", "1.01", "1.43", "중간 저점 → 붕괴", 0),
    ("2008.07.15", "S&P500", "다이버전스", "35.6 → 30.8", "1.01 → 0.91", "1.15", "두 달 뒤 리먼 → 붕괴", 0),
    ("2008.11.20", "S&P500", "투매", "81.5", "1.03", "1.64", "미국은 2009.3까지 추가 하락", 0),
    ("2022.06.16", "S&P500", "투매", "35.1", "1.10", "0.22", "10월에 신저점(재시험)", 0),
]


def body(spx, ks, asof, src):
    s = spx["signals"]
    lv = level(s)
    ref, new = s["divergence"].get("ref_low") or {}, s["divergence"].get("new_low") or {}
    rows = [r for r in spx["rows"] if r.get("vix_close") is not None][-95:]
    krows = [r for r in ks["rows"] if r.get("index_close") is not None][-95:]
    kref, knew = ks["signals"]["divergence"].get("ref_low") or {}, ks["signals"]["divergence"].get("new_low") or {}
    peak_vix = max((new or ref).get("vix_high") or 0, ref.get("vix_high") or 0)
    peak_pc = max((new or ref).get("pc5") or 0, ref.get("pc5") or 0)
    sit = "".join(f"<p>{x}</p>" for x in situation("S&amp;P500", spx) + situation("코스피", ks, us=False, eun="는") + summary(lv, spx))
    pf = lambda n: f'<div class="pf"><span>{escape(src)}</span><span>{n}</span></div>'
    kd = (f'<div class="kd"><b>KEY DATA</b>'
          f'<div><span>기준일</span><span>{_d(asof)}</span></div>'
          f'<div><span>S&amp;P500</span><span>{_f(rows[-1]["index_close"], "{:,.1f}")}</span></div>'
          f'<div><span>코스피</span><span>{_f(krows[-1]["index_close"], "{:,.1f}")}</span></div>'
          f'<div><span>VIX 장중 고점</span><span>{_f(rows[-1]["vix_high"], "{:.1f}")}</span></div>'
          f'<div><span>풋콜 5일 (CNN 근사)</span><span>{_f(s["capitulation"].get("latest_pc_eqetp_5d"), "{:.3f}")}</span></div>'
          f'<div><span>1차 폭락 기준</span><span>{_d(ref.get("date"))}</span></div>'
          f'<div><span>자금시장 스프레드</span><span>{_f(s["funding_filter"]["cp_tbill_5d"])}%p</span></div>'
          f'<div><span>하이일드 OAS</span><span>{_f(s["credit_filter"].get("hy_oas"))}%</span></div></div>')
    cases = "".join(f'<tr class="{"hit" if ok else ""}"><td>{d}</td><td>{m}</td><td>{ty}</td><td>{v}</td><td>{p}</td><td>{f}</td>'
                    f'<td class="l"><span class="{"ok" if ok else "no"}">{escape(res)}</span></td></tr>' for d, m, ty, v, p, f, res, ok in CASES)
    nxt = (f"<li><b>투매형까지:</b> 풋콜 5일 평균 {_f(s['capitulation'].get('latest_pc_eqetp_5d'), '{:.3f}')} → 1.0 이상, 그 뒤 VIX가 장중 고점에서 15% 이상 꺾이면 바닥 가능성이 커집니다.</li>"
           f"<li><b>다이버전스 조건:</b> S&amp;P500이 {_f((new or ref).get('close'), '{:,.1f}')}, 코스피가 {_f((knew or kref).get('close'), '{:,.1f}')}를 종가로 깰 때 "
           f"VIX 장중 고점이 <b>{peak_vix:.1f} 미만</b>, 풋콜 5일 평균이 <b>{peak_pc:.3f} 미만</b>이면 2011년 10월과 같은 모양입니다.</li>"
           f"<li><b>필터:</b> 그때 금융CP − T-bill 5일 평균이 0.5%p 미만이어야 합니다(지금 {_f(s['funding_filter']['cp_tbill_5d'])}%p).</li>"
           "<li><b>국내 수급:</b> 외국인이 코스피200 풋옵션을 하루 200억원 이상 순매도하기 시작하면 바닥 준비 신호로 봅니다(미국 쪽 신호와 겹칠 때 무게). 10월 이후 최대 순매도는 47억(10/15)이라 아직 나오지 않았습니다.</li>"
           "<li>코스피는 미국 밤사이 급락이 다음 날 갭으로 반영돼 신저점이 '강제'되는 날이 많습니다. 같은 날 밤 미국장의 VIX 장중 고점과 함께 봅니다.</li>")
    return f'''<div class="rk">
<section class="pg"><div class="cov"><div>
<h2>폭락장 저점 신호</h2>
{ladder(lv)}
<div class="sit"><h3>지금 상황<small>기준 {_d(asof)} 미국장 · 코스피 {_d(krows[-1]["date"])}</small></h3>{sit}</div>
<ul class="sq"><li>바닥은 매도 연료(겁에 질린 매도, 급한 헤지, 강제 청산)가 바닥날 때 나옵니다. 풋콜비율·VIX·자금시장으로 그 연료를 잽니다.</li>
<li><b>투매형</b>은 한 번에 공포가 터지고 끝나는 바닥(2025년 4월), <b>다이버전스형</b>은 전저점을 깨는데 겁은 1차 때보다 작은 바닥(2011년 10월)입니다.</li>
<li>예측이 아니라 <b>점검표</b>입니다. 자금시장이 막히면 같은 신호도 믿지 않습니다(2008년 3·7·11월).</li></ul>
</div>{kd}</div>{pf(1)}</section>

<section class="pg"><h2>오늘의 조건 점검</h2>
<div class="two"><div>{check_table("S&P500 (기준 저점 " + _d(ref.get("date")) + ")", spx)}</div><div>{check_table("코스피 (기준 저점 " + _d(kref.get("date")) + ")", ks)}</div></div>
<p class="note">VIX·풋콜·자금시장은 미국 데이터입니다. 코스피 줄은 코스피 종가로 전저점 이탈을 보고, 그 날짜 앞뒤의 미국 VIX·풋콜 고점을 비교합니다.</p>{pf(2)}</section>

<section class="pg"><h2>다음 기준선</h2><ul class="sq">{nxt}</ul>{pf(3)}</section>

<section class="pg"><h2>최근 흐름</h2>
{svg(rows, "index_close", "#3D3A35", "S&P500 종가", W=560, H=250, marks=[(ref.get("date"), "1차 폭락"), (new.get("date"), "신저점")] if new else [(ref.get("date"), "1차 폭락")], fmt="{:,.0f}")}
<div class="two" style="margin-top:12px"><div>{svg(rows, "vix_high", "#C8102E", "VIX 장중 고점", refs=[(peak_vix, f"다이버전스 기준 {peak_vix:.1f}")], fmt="{:.0f}", W=480, H=230)}</div>
<div>{svg(rows, "pc_eqetp_5d", "#F2A900", "풋콜 5일 평균 (Cboe 주식+ETP, CNN 근사)", refs=[(1.0, "투매 기준 1.0")], fmt="{:.2f}", W=480, H=230)}</div></div>
<p class="note">가격이 신저점을 낼 때 빨간 선(VIX)과 노란 선(풋콜)이 기준선 아래에 머물면 다이버전스입니다. 지금은 두 선이 가격과 함께 올라가고 있습니다.</p>{pf(4)}</section>

<section class="pg"><h2>과거 사례</h2><div class="tw"><table style="min-width:680px"><tr><th>날짜</th><th>지수</th><th>유형</th><th>VIX 장중 고점</th><th>풋콜 5일</th><th>자금 %p</th><th>결과</th></tr>{cases}</table></div>
<p class="note">· 풋콜 = Cboe 주식+ETP 풋콜비율 5일 평균. 2012년 6월 이전 Cboe '주식' 비율에는 ETP가 포함돼 있어 같은 정의로 이어집니다. CNN 지수는 2012년에 나와 그 전 값은 재구성치입니다.<br>
· 자금 = FRED 금융CP 3개월(AA) − T-bill 3개월 5일 평균. 2020.3.23은 1.12%p였지만 연준이 무제한 유동성을 발표한 날이라 예외입니다.<br>
· 성공·실패 사례가 각각 몇 개뿐이라, 신호는 '바닥일 확률이 높아졌다'는 뜻으로만 씁니다.</p>{pf(5)}</section>

<section class="pg"><h2>고지사항</h2><p class="note">이 페이지는 공개된 시세 자료로 계산한 참고용 점검표이며, 특정 종목이나 지수의 매수·매도를 권유하지 않습니다.
과거 성과가 미래 수익을 보장하지 않으며, 신호 없이 바닥이 나거나 신호가 나온 뒤 더 빠지는 경우도 있습니다. 투자 판단과 결과의 책임은 투자자 본인에게 있습니다.</p>{pf(6)}</section>
</div>'''


def home(spx):
    """홈 저점신호기 칸: 첫 줄 이름, 다음 줄 판정과 수치 (사용자 요청 2026-11-22: 이름 저점신호기, 글씨 크게).
    order:-2 는 실적속보 제목(#earn-h, order:-2)보다 위에 오게 한다(HTML 에서 먼저 나오므로 같은 값이면 앞).
    """
    if not spx:
        return ""
    s = spx["signals"]
    lv = level(s)
    t, _ = LV[lv]
    bg, fg, c = "#fff", "#3D3A35", LV_COLOR[lv]
    chips = "".join(
        (f'<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;border:2px solid {c};color:{c};font-weight:900">'
         f'<i class="bsb" style="width:10px;height:10px;border-radius:50%;background:{c};animation:bsblink 1.2s ease-in-out infinite"></i>{LV_SHORT[k]}</span>')
        if k == lv else
        f'<span style="padding:3px 9px;border-radius:999px;border:1px solid #E6E0D2;color:#B5AFA2;font-weight:500">{LV_SHORT[k]}</span>'
        for k in ORDER)
    pc = s["capitulation"].get("latest_pc_eqetp_5d")
    if pc is None or pc < HOME_PC_MIN:
        return ""  # 메뉴·/bottom/ 페이지는 그대로
    return (f'<style>{BLINK_CSS}</style><a href="bottom/" class="sec" style="display:block;text-decoration:none;'
            f'background:{bg};color:{fg};border:1px solid #E6E0D2;border-left:8px solid #F2A900;border-radius:12px;padding:14px 16px;'
            f'order:-2;margin:0 0 14px;font-family:\'Noto Sans KR\',sans-serif;line-height:1.45">'
            f'<span style="display:flex;align-items:center;gap:8px;font-size:21px;font-weight:900">📉 저점신호기'
            f'<span style="margin-left:auto;font-size:16px;font-weight:800">자세히 →</span></span>'
            f'<span style="display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;margin-top:8px">'
            f'<b style="font-size:20px;font-weight:900;color:{c}">{t.split(" ", 1)[1]}</b>'
            f'<span style="font-size:17px;font-weight:500;opacity:.9">풋콜 {_f(pc, "{:.2f}")} · VIX {_f(spx["rows"][-1].get("vix_high"), "{:.1f}")} · 자금 {_f(s["funding_filter"]["cp_tbill_5d"])}%p</span>'
            f'</span><span style="display:block;margin-top:6px;font-size:15px;font-weight:500;color:#6B665D">{home_line(spx)}</span>'
            f'<span style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;font-size:13px">{chips}</span></a>')


def build(out, page, now=None):
    """/bottom/ 페이지와 bottom/state.json 을 만들고 S&P500 결과(홈 줄용)를 돌려준다. 실패하면 None(사이트는 계속 만든다)."""
    now = now or datetime.now(KST)
    d = out / "bottom"
    d.mkdir(parents=True, exist_ok=True)
    start = (now.date() - timedelta(days=DAYS)).isoformat()
    try:
        spx = bottom_signals.compute("^GSPC", start, pre_days=40)
        ks = bottom_signals.compute("^KS11", start, pre_days=40, kr_flow_dir="github")
    except Exception as e:
        print("저점신호 계산 실패:", e)
        (d / "index.html").write_text(page("📉 저점신호기", '<p class="err">시세를 받지 못해 이번에는 계산하지 못했습니다.</p>',
                                           "../", "bottom/", "BOTTOM SIGNAL", "폭락장 지수 저점 점검"), encoding="utf-8")
        return None
    asof = [r for r in spx["rows"] if r.get("index_close") is not None][-1]["date"]
    src = f"자료: Cboe 풋콜 통계, Yahoo Finance 일봉(^GSPC·^KS11·^VIX), FRED(금융CP·T-bill·하이일드), KB증권 Open API(외국인 풋옵션) · 기준 {asof} · 계산 Brian's 투자노트"
    html = f"<style>{RISK_CSS}{EXTRA_CSS}{BLINK_CSS}</style>{body(spx, ks, asof, src)}"
    (d / "index.html").write_text(page("📉 저점신호기", html, "../", "bottom/", "BOTTOM SIGNAL", f"폭락장 지수 저점 점검 · 기준 {_d(asof)}"), encoding="utf-8")
    st = {"asof": asof, "spx": level(spx["signals"]), "kospi": level(ks["signals"]), "computed": f"{now:%Y-%m-%d %H:%M}"}
    (d / "state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print("저점신호:", st)
    return spx


if __name__ == "__main__":
    import build_site
    spx, ks = json.load(open("bt_spx.json")), json.load(open("bt_ks.json"))
    asof = spx["rows"][-1]["date"]
    src = f"자료: Cboe 풋콜 통계, Yahoo Finance 일봉(^GSPC·^KS11·^VIX), FRED(금융CP·T-bill·하이일드) · 기준 {asof} · 계산 Brian's 투자노트"
    html = f"<style>{RISK_CSS}{EXTRA_CSS}{BLINK_CSS}</style>{body(spx, ks, asof, src)}"
    out = build_site.page("📉 저점신호기", html, "../", "bottom/", "BOTTOM SIGNAL", f"폭락장 지수 저점 점검 · 기준 {_d(asof)}")
    out = out.replace(build_site.VISIT_JS, "")
    open("bottom_preview.html", "w", encoding="utf-8").write(out)
    print("ok", len(out), level(spx["signals"]), level(ks["signals"]))
