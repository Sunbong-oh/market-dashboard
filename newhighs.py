"""미국 52주 신고가 종목 요약. dashboard.py의 아침 발송 뒤에 두 번째 앨범으로 붙는다.

- 후보: 나스닥 스크리너 전종목 중 시가총액 MIN_CAP 이상
- 신고가 판정: 최근 1년 일봉 중 마지막 종가가 가장 높음(종가 기준)
- 시총 큰 순으로 TOP_N개를 6개월 차트·업종·밸류에이션과 함께 카드로, 나머지는 티커만 나열
단독 실행: python newhighs.py [--send]   (--send 없으면 HTML/PNG만 만든다)
"""
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path

import dashboard as d

OUT = Path(__file__).with_name("newhighs.html")
MIN_CAP = 10e9      # 이 시가총액($) 이상만 검색
TOP_N = 8           # 카드로 자세히 보여줄 종목 수(시총 순)
PER_PHOTO = 4       # 사진 한 장에 담을 카드 수 (폰 한 화면 비율 유지)
MIN_BARS = 150      # 일봉이 이보다 적은 신규 상장주는 제외(상장 이후 계속 신고가라 의미가 없다)
SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&download=true"

SECTOR_KO = {
    "Technology": "기술", "Healthcare": "헬스케어", "Financial Services": "금융", "Consumer Cyclical": "경기소비재",
    "Industrials": "산업재", "Communication Services": "커뮤니케이션", "Consumer Defensive": "필수소비재",
    "Energy": "에너지", "Basic Materials": "소재", "Real Estate": "부동산", "Utilities": "유틸리티",
}


def universe():
    """[(티커, 영문명, 시총)] — 시총 내림차순. 우선주·워런트 등 특수 표기는 뺀다."""
    j = d.fetch_json(SCREENER, {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    out = []
    for r in j["data"]["rows"]:
        try:
            cap = float(r.get("marketCap") or 0)
        except ValueError:
            continue
        sym = (r.get("symbol") or "").strip().replace("/", "-")
        if cap >= MIN_CAP and sym and "^" not in sym and " " not in sym:
            out.append((sym, r.get("name", ""), cap))
    return sorted(out, key=lambda x: -x[2])


def fetch_bars(item, tries=3):
    """1년 일봉 종가. 429면 잠깐 쉬고 다시 시도. 실패하면 None."""
    sym = item[0]
    for i in range(tries):
        try:
            j = d.fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d")
            res = j["chart"]["result"][0]
            pts = [(t, c) for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
            return dict(sym=sym, name=item[1], cap=item[2], pts=pts)
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(1.5 * (i + 1))
    return None


def find_highs(bars):
    """마지막 종가가 1년 최고 종가인 종목. 기준일은 전 종목 중 가장 늦은 일봉 날짜."""
    bars = [b for b in bars if b and len(b["pts"]) >= MIN_BARS]
    if not bars:
        return [], None
    asof = max(datetime.fromtimestamp(b["pts"][-1][0], d.US_DAY_TZ).date() for b in bars)
    highs = []
    for b in bars:
        last_day = datetime.fromtimestamp(b["pts"][-1][0], d.US_DAY_TZ).date()
        closes = [c for _, c in b["pts"]]
        if last_day == asof and closes[-1] >= max(closes):
            prev_high = max(closes[:-1]) if len(closes) > 1 else closes[-1]
            b["prev_high"] = prev_high
            highs.append(b)
    return sorted(highs, key=lambda b: -b["cap"]), asof


def details(b):
    """시총 상위 종목의 업종·밸류에이션(야후 quoteSummary). 실패하면 빈 값으로 둔다."""
    s = d.yahoo_summary(b["sym"], ["summaryProfile", "summaryDetail", "defaultKeyStatistics", "financialData"])
    if not s:
        return b
    p, sd, ks, fd = (s.get(k) or {} for k in ("summaryProfile", "summaryDetail", "defaultKeyStatistics", "financialData"))
    b.update(sector=p.get("sector"), industry=p.get("industry"), country=p.get("country"),
             per=d._raw(sd, "trailingPE"), fper=d._raw(sd, "forwardPE"), pbr=d._raw(ks, "priceToBook"),
             eps=d._raw(ks, "trailingEps"), target=d._raw(fd, "targetMeanPrice"),
             rev_g=d._raw(fd, "revenueGrowth"), margin=d._raw(fd, "operatingMargins"))
    return b


def _cap_text(v):
    return f"${v / 1e12:.2f}T" if v >= 1e12 else f"${v / 1e9:,.0f}B"


def _mult(v, eps=None):
    if v is None or v <= 0:
        return "적자" if (eps is not None and eps < 0) else "–"
    return "500배+" if v >= 500 else f"{v:.1f}배"


_NAME_CUT = re.compile(r"[\s,]+(American Depositary|Ordinary Share|Class [A-C]|Common Stock|Holdings?|Inc|Corp|plc|Ltd).*$", re.I)


def short_name(sym, name):
    return d.KO_NAMES.get(sym) or _NAME_CUT.sub("", name).strip() or sym


def card(b):
    pts = b["pts"]
    last, prev = pts[-1][1], pts[-2][1]
    day = (last / prev - 1) * 100
    cut = pts[-1][0] - 183 * 86400
    six = [c for t, c in pts if t >= cut]
    ret6 = (last / six[0] - 1) * 100
    gap = (last / b["prev_high"] - 1) * 100
    sec = SECTOR_KO.get(b.get("sector"), b.get("sector") or "")
    ind = b.get("industry") or ""
    tgt = f'{(b["target"] / last - 1) * 100:+.0f}%' if b.get("target") else "–"
    rg = f'{b["rev_g"] * 100:+.0f}%' if b.get("rev_g") is not None else "–"
    cell = lambda k, v: f'<div class="nh-c"><span>{k}</span><b>{v}</b></div>'
    return f'''<article class="card nh">
<div class="nh-top"><div class="nh-nm"><a href="https://finance.yahoo.com/quote/{escape(b["sym"])}">{escape(short_name(b["sym"], b["name"]))}</a> <span class="sym">{escape(b["sym"])}</span></div>
<div class="nh-px">${d.fnum(last)} <span class="{d.cls(day)}">{"▲" if day > 0 else "▼" if day < 0 else "–"}{abs(day):.2f}%</span></div></div>
<div class="nh-ind">{escape(sec)}{" · " if sec and ind else ""}{escape(ind)}</div>
<div class="nh-mid"><div class="nh-ch">{d.sparkline(six, w=300, h=64, color_cls=d.cls(ret6))}
<div class="nh-cap">6개월 <i class="{d.cls(ret6)}">{ret6:+.0f}%</i> · 전고점 <i class="{d.cls(gap)}">{gap:+.1f}%</i></div></div>
<div class="nh-g">{cell("시총", _cap_text(b["cap"]))}{cell("PER", _mult(b.get("per"), b.get("eps")))}{cell("선행 PER", _mult(b.get("fper")))}
{cell("PBR", _mult(b.get("pbr")))}{cell("매출성장", rg)}{cell("목표가 괴리", tgt)}</div></div>
</article>'''


NH_CSS = """
.nh{margin-top:8px;padding:10px 12px}
.nh-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.nh-nm{font-size:18px;font-weight:800;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.nh-nm .sym{font-weight:400;font-size:12px}
.nh-px{font-size:20px;font-weight:800;white-space:nowrap;font-variant-numeric:tabular-nums}.nh-px span{font-size:14px;font-weight:700}
.nh-ind{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.nh-mid{display:grid;grid-template-columns:42% 1fr;gap:8px;margin-top:6px;align-items:center}
.nh .spark{height:58px;margin-top:0}.nh-cap{font-size:11.5px;color:var(--muted);text-align:center;margin-top:3px;white-space:nowrap}.nh-cap i{font-style:normal;font-weight:700}
.nh-g{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.nh-c{background:var(--bg);border-radius:7px;padding:3px 7px;display:flex;justify-content:space-between;align-items:baseline;min-width:0;gap:4px}
.nh-c span{font-size:11px;color:var(--muted);white-space:nowrap}.nh-c b{font-size:13.5px;font-variant-numeric:tabular-nums;white-space:nowrap}
.nh-sum{margin-top:8px}.nh-sum p{margin:6px 0 0;font-size:15px;line-height:1.5}.nh-sum .tks{font-size:14px;color:var(--muted);word-break:keep-all}
.nh-sum .sec{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}.nh-sum .sec span{background:var(--bg);border-radius:99px;padding:3px 10px;font-size:13px;font-weight:700}
.nh-sum .sec b{color:var(--accent)}
"""

NH_JS = """
const h=location.hash.match(/^#shot([0-9]*)(?:-(\\d))?/);
if(h){document.documentElement.dataset.shot='1';if(h[1])document.documentElement.style.zoom=innerWidth/+h[1];
if(h[2])document.querySelectorAll('[data-photo]').forEach(e=>{if(e.dataset.photo!==h[2])e.style.display='none'})}
document.documentElement.dataset.h=Math.ceil(document.querySelector('.wrap').getBoundingClientRect().bottom);
"""


def build_html(highs, asof, total_scanned, now):
    top = highs[:TOP_N]
    rest = highs[TOP_N:]
    photos = [top[i:i + PER_PHOTO] for i in range(0, len(top), PER_PHOTO)] or [[]]
    # 업종별 신고가 개수(상세를 받은 종목 + 나머지는 집계 불가라 상위 종목 기준)
    secs = {}
    for b in top:
        if b.get("sector"):
            secs[SECTOR_KO.get(b["sector"], b["sector"])] = secs.get(SECTOR_KO.get(b["sector"], b["sector"]), 0) + 1
    sec_html = "".join(f"<span>{escape(k)} <b>{v}</b></span>" for k, v in sorted(secs.items(), key=lambda x: -x[1]))
    head = f'''<header class="top"><div><div class="kicker">US 52-WEEK HIGHS</div>
<h1>미국 52주 신고가 {len(highs)}종목</h1>
<div class="sub">{asof:%m/%d} 마감 기준 · 시총 ${MIN_CAP / 1e9:.0f}B↑ {total_scanned:,}종목 중</div></div></header>'''
    parts = []
    for i, grp in enumerate(photos, 1):
        body = "".join(card(b) for b in grp)
        extra = ""
        if i == 1:
            extra = f'<section class="panel nh-sum"><span class="tag">시총 상위 {len(top)}종목 업종</span><div class="sec">{sec_html}</div></section>'
        if i == len(photos) and rest:
            tk = " · ".join(escape(b["sym"]) for b in rest[:60])
            more = f" 외 {len(rest) - 60}종목" if len(rest) > 60 else ""
            extra += f'<section class="panel nh-sum"><span class="tag">그 외 신고가 {len(rest)}종목</span><p class="tks">{tk}{more}</p></section>'
        parts.append(f'<div data-photo="{i}">{head if i == 1 else ""}{body}{extra}</div>')
    foot = ('<footer>종가 기준 1년 최고가 경신 종목. 출처: 나스닥 스크리너(종목·시총), Yahoo Finance(시세·재무, 지연 가능). '
            '투자 판단의 근거가 아닌 참고용입니다.</footer>')
    html = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>미국 52주 신고가</title><style>{d.CSS}{NH_CSS}</style></head><body><div class="wrap">'
            f'{"".join(parts)}{foot}</div><script>{NH_JS}</script></body></html>')
    return html, len(photos)


def shoot(png, n):
    """photo n(1부터)만 폰 폭으로 캡처."""
    uri = OUT.as_uri() + f"#shot420-{n}"
    for exe in d.find_browsers():
        for _ in range(3):
            try:
                if d._screenshot_once(exe, uri, png, d.SHOT_W, 150, 3):
                    return True
            except Exception as e:
                print("신고가 스크린샷 실패:", type(e).__name__, file=sys.stderr)
    return False


def run(now=None, send=False):
    now = now or datetime.now(d.KST)
    uni = universe()
    with ThreadPoolExecutor(max_workers=12) as ex:
        bars = list(ex.map(fetch_bars, uni))
    highs, asof = find_highs(bars)
    got = sum(1 for b in bars if b)
    print(f"신고가 스캔: 후보 {len(uni)}종목, 시세 수신 {got}종목, 신고가 {len(highs)}종목 (기준일 {asof})")
    if got < len(uni) * 0.7:
        raise RuntimeError(f"시세 수신률이 낮음({got}/{len(uni)}) — 오탐을 막으려고 중단")
    if not highs:
        if send:
            d.send_telegram(f"🚀 미국 52주 신고가: {asof:%m/%d} 마감 기준 시총 ${MIN_CAP / 1e9:.0f}B 이상 신고가 종목이 없습니다.")
        return
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(details, highs[:TOP_N]))
    html, n = build_html(highs, asof, got, now)
    OUT.write_text(html, encoding="utf-8")
    print("생성 완료:", OUT)
    pngs = []
    for i in range(1, n + 1):
        png = OUT.with_name(f"newhighs_{i}.png")
        if not shoot(png, i):
            raise RuntimeError("스크린샷 실패")
        pngs.append(png)
    if send:
        cap = f"🚀 미국 52주 신고가 {len(highs)}종목 · {asof:%m/%d} 마감 (시총 ${MIN_CAP / 1e9:.0f}B↑, 시총 순)"
        if not d.send_telegram_album(pngs, cap):
            raise RuntimeError("텔레그램 발송 실패")


if __name__ == "__main__":
    run(send="--send" in sys.argv)
