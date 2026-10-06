"""미국 52주 신고가 종목 요약. dashboard.py의 아침 발송 뒤에 두 번째 앨범으로 붙는다.

- 후보: 나스닥 스크리너 전종목 중 시가총액 MIN_CAP 이상
- 신고가 판정: 최근 1년 일봉 중 마지막 종가가 가장 높음(종가 기준)
- 시총 큰 순으로 최대 TOP_N개를 6개월 차트·업종·밸류에이션과 함께 카드로, 나머지는 티커만 나열
- 소프트웨어 기업은 SEC 실적 보도자료에서 ARR(연간 반복 매출)을 찾아 함께 표시
단독 실행: python newhighs.py [--send]   (--send 없으면 HTML/PNG만 만든다)
"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape, unescape
from pathlib import Path

import dashboard as d
from company_ko import describe

OUT = Path(__file__).with_name("newhighs.html")
MIN_CAP = 10e9      # 이 시가총액($) 이상만 검색
TOP_N = 300         # 카드로 보여줄 최대 종목 수(시총 순). 사실상 신고가 종목 전부. 넘는 종목만 티커로 나열
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


SEC_UA = {"User-Agent": os.environ.get("SEC_UA", "Sunbong Oh sunbong5302@gmail.com")}
_sec_cik = {}
ARR_A = re.compile(r"\bARR\b[^.•$]{0,120}?(?:grew|increased|rose|up)\s+(?:by\s+)?(\d+(?:\.\d+)?)%[^.•$]{0,60}?\$\s?([\d.,]+)\s*(billion|million)", re.I)
ARR_B = re.compile(r"\bARR\b[^.•$]{0,60}?\$\s?([\d.,]+)\s*(billion|million)[^.•]{0,60}?(?:up|increase of|growth of|grew)\s+(\d+(?:\.\d+)?)%", re.I)


def _sec_get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=SEC_UA), timeout=30) as r:
        return r.read()


def fetch_arr(sym):
    """SEC 최근 실적 8-K 보도자료에서 ARR(연간 반복 매출)과 전년 대비 성장률을 찾는다.
    ARR는 회계 항목이 아니라 회사가 문장으로 공시하는 지표라 공시하지 않는 회사(예: 포티넷·옥타)는 None.
    반환: dict(val=달러, growth=%, date=공시일) / None=보도자료에 ARR 없음(미공시) / False=조회 실패."""
    try:
        if not _sec_cik:
            for v in json.loads(_sec_get("https://www.sec.gov/files/company_tickers.json")).values():
                _sec_cik[v["ticker"]] = v["cik_str"]
        cik = _sec_cik.get(sym)
        if not cik:
            return False
        rec = json.loads(_sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))["filings"]["recent"]
        for i, form in enumerate(rec["form"]):
            if form != "8-K" or "2.02" not in (rec["items"][i] or ""):
                continue
            base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{rec['accessionNumber'][i].replace('-', '')}/"
            files = [x["name"] for x in json.loads(_sec_get(base + "index.json"))["directory"]["item"]]
            main_doc = rec["primaryDocument"][i]
            ex = [n for n in files if n.lower().endswith((".htm", ".html")) and n != main_doc
                  and re.search(r"ex-?99|99[-_.]?1|press|release|earnings", n, re.I)
                  and not re.search(r"index|^R\d+\.htm", n, re.I)]
            if not ex:
                return False
            t = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", _sec_get(base + ex[0]).decode("utf-8", "ignore"))))
            for m in ARR_A.finditer(t):
                if not re.search(r"net\s+new\s*$", t[max(0, m.start() - 12):m.start()], re.I):
                    g, v, u = m.groups()
                    break
            else:
                m = ARR_B.search(t)
                if not m:
                    return None
                v, u, g = m.groups()
            return dict(val=float(v.replace(",", "")) * (1e9 if u.lower() == "billion" else 1e6), growth=float(g),
                        date=rec["filingDate"][i])
        return None
    except Exception as e:
        print("ARR 조회 실패:", sym, type(e).__name__, file=sys.stderr)
        return False


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
    if "Software" in (b.get("industry") or ""):
        b["arr"] = fetch_arr(b["sym"])
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


def spark(values, color_cls, w=300, h=64):
    """KB 리포트식 미니 차트: 시작값 기준 점선 위·아래를 옅게 채우고 마지막 점을 찍는다."""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    n, pad = len(values), 5
    y = lambda v: pad + (1 - (v - lo) / rng) * (h - 2 * pad)
    xy = [(i / (n - 1) * w, y(v)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in xy)
    base = y(values[0])
    lx, ly = xy[-1]
    return (f'<svg class="sp {color_cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polygon points="0,{base:.1f} {line} {w},{base:.1f}" class="ar"/>'
            f'<line x1="0" y1="{base:.1f}" x2="{w}" y2="{base:.1f}" class="bl"/>'
            f'<polyline points="{line}" class="ln" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.2" class="dt"/></svg>')


def tile(b):
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
    c = d.cls(day)
    arr = ""
    if "Software" in ind:
        a = b.get("arr")
        arr = (f'<div class="r"><span>ARR</span><b>${a["val"] / 1e9:.2f}B <i class="{d.cls(a["growth"])}">{a["growth"]:+.0f}%</i></b></div>' if a
               else f'<div class="r"><span>ARR</span><b class="flat">{"–" if a is False else "미공시"}</b></div>')
    row = lambda k, v: f'<div class="r"><span>{k}</span><b>{v}</b></div>'
    return f'''<div class="tile">
<div class="nm"><a href="https://finance.yahoo.com/quote/{escape(b["sym"])}">{escape(short_name(b["sym"], b["name"]))}</a></div>
<div class="tk">{escape(b["sym"])} · {escape(sec)}</div>
<div class="desc">{escape(describe(b["sym"], ind))}</div>
<div class="px {c}">{d.fnum(last)}</div>
<div class="dl {c}">{"▲" if day > 0 else "▼" if day < 0 else "–"} {abs(day):.2f}%</div>
{spark(six, d.cls(ret6))}
<div class="cap">6개월 <i class="{d.cls(ret6)}">{ret6:+.0f}%</i> · 전고점 <i class="{d.cls(gap)}">{gap:+.1f}%</i></div>
<div class="rows">{row("시총", _cap_text(b["cap"]))}{row("PER", _mult(b.get("per"), b.get("eps")))}{row("선행 PER", _mult(b.get("fper")))}{row("PBR", _mult(b.get("pbr")))}{arr}{row("매출성장", rg)}{row("목표가 괴리", tgt)}</div>
</div>'''


NH_CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#1b1f24;--muted:#7a828c;--line:#e7e9ec;--tile:#f3f4f6;--up:#d93b3b;--down:#2f6fdb;--flat:#6b7280;--label:#15803d;--kb:#f97316}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 'Pretendard','Malgun Gothic',system-ui,sans-serif;font-variant-numeric:tabular-nums}
.wrap{max-width:460px;margin:0 auto;padding:10px 10px 8px}
.hd{display:flex;justify-content:space-between;align-items:center;gap:8px;background:var(--kb);color:#fff;border-radius:14px;padding:13px 16px}
.hd h1{margin:0;font-size:22px;font-weight:800}.hd .dt{font-size:12.5px;font-weight:700;text-align:right;line-height:1.3}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-top:10px}
.sh{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:8px}
.sh h2{margin:0;font-size:16px;font-weight:800}.sh span{font-size:11px;color:var(--muted)}
.sum{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
.sum div{background:var(--tile);border-radius:10px;padding:8px 10px}.sum span{display:block;font-size:11px;color:var(--muted)}
.sum b{font-size:22px;font-weight:800}.sum b.up{color:var(--up)}
.pills{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.pills span{background:var(--tile);border-radius:99px;padding:3px 10px;font-size:12px;font-weight:700}.pills b{color:var(--kb)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.tile{background:var(--tile);border-radius:10px;padding:9px 10px;min-width:0}
.nm{font-size:16px;font-weight:800;color:var(--label);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tk{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.px{font-size:25px;font-weight:800;margin-top:4px;line-height:1.1}.dl{font-size:13px;font-weight:600}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--flat)}
.sp{width:100%;height:50px;display:block;margin-top:5px}
.sp .ln{fill:none;stroke:currentColor;stroke-width:1.8}.sp .ar{fill:currentColor;opacity:.13}.sp .dt{fill:currentColor}.sp .bl{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3;opacity:.7;vector-effect:non-scaling-stroke}
.sp.up{color:var(--up)}.sp.down{color:var(--down)}.sp.flat{color:var(--flat)}
.cap{font-size:11px;color:var(--muted);margin-top:2px;white-space:nowrap}.cap i{font-style:normal;font-weight:700}
.rows{margin-top:6px;border-top:1px solid var(--line);padding-top:4px}
.r{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;padding:1.5px 0}.r span{color:var(--muted)}.r b{font-weight:700}
.desc{font-size:12px;line-height:1.35;color:var(--ink);margin-top:3px;min-height:33px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;word-break:keep-all}
.tks{font-size:13px;color:var(--muted);line-height:1.6}
.foot{font-size:10.5px;color:var(--muted);margin:10px 4px 0;line-height:1.5}
a{color:inherit;text-decoration:none}
"""

NH_JS = """
const h=location.hash.match(/^#shot([0-9]*)(?:-(\\d))?/);
if(h){if(h[1])document.documentElement.style.zoom=innerWidth/+h[1];
if(h[2])document.querySelectorAll('[data-photo]').forEach(e=>{if(e.dataset.photo!==h[2])e.style.display='none'})}
document.documentElement.dataset.h=Math.ceil(document.querySelector('.wrap').getBoundingClientRect().bottom);
"""


def build_html(highs, asof, total_scanned, now):
    top, rest = highs[:TOP_N], highs[TOP_N:]
    # 마지막 장만 1~2개로 남지 않게 사진 수를 먼저 정하고 균등하게 나눈다
    n_photo = max(1, -(-len(top) // PER_PHOTO))
    base, extra = divmod(len(top), n_photo)
    groups, at = [], 0
    for k in range(n_photo):
        take = base + (1 if k < extra else 0)
        groups.append(top[at:at + take])
        at += take
    secs = {}
    for b in highs[:TOP_N]:
        k = SECTOR_KO.get(b.get("sector"), b.get("sector"))
        if k:
            secs[k] = secs.get(k, 0) + 1
    pills = "".join(f"<span>{escape(k)} <b>{v}</b></span>" for k, v in sorted(secs.items(), key=lambda x: -x[1]))
    wd = "월화수목금토일"[asof.weekday()]
    head = (f'<div class="hd"><h1>미국 52주 신고가</h1><div class="dt">{asof:%Y.%m.%d} ({wd}) 마감<br>시총 ${MIN_CAP / 1e9:.0f}B↑ 기준</div></div>'
            f'<div class="card"><div class="sh"><h2>신고가 요약</h2><span>종가 기준 1년 최고가</span></div>'
            f'<div class="sum"><div><span>신고가 종목</span><b class="up">{len(highs)}</b></div>'
            f'<div><span>검색 대상</span><b>{total_scanned:,}</b></div>'
            f'<div><span>신고가 비율</span><b>{len(highs) / total_scanned * 100:.1f}%</b></div></div>'
            f'<div class="pills">{pills}</div></div>')
    parts = []
    for i, grp in enumerate(groups, 1):
        body = (f'<div class="card"><div class="sh"><h2>시총 상위 신고가{f" ({i}/{len(groups)})" if len(groups) > 1 else ""}</h2>'
                f'<span>6개월 차트 · 밸류에이션</span></div><div class="grid">{"".join(tile(b) for b in grp)}</div></div>')
        extra = ""
        if i == len(groups) and rest:
            tk = " · ".join(escape(b["sym"]) for b in rest[:60]) + (f" 외 {len(rest) - 60}종목" if len(rest) > 60 else "")
            extra = f'<div class="card"><div class="sh"><h2>그 외 신고가 {len(rest)}종목</h2><span>시총 순</span></div><div class="tks">{tk}</div></div>'
        parts.append(f'<div data-photo="{i}">{head if i == 1 else ""}{body}{extra}</div>')
    foot = ('<div class="foot">출처: 나스닥 스크리너(종목·시총), Yahoo Finance(시세·재무, 지연 가능). '
            'ARR는 회사가 최근 실적 보도자료(SEC 8-K)에 공시한 값이며, 공시하지 않는 회사는 미공시로 표시합니다. 투자 판단의 근거가 아닌 참고용입니다.</div>')
    html = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>미국 52주 신고가</title><style>{NH_CSS}</style></head><body><div class="wrap">'
            f'{"".join(parts)}{foot}</div><script>{NH_JS}</script></body></html>')
    return html, len(groups)


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
        # 텔레그램 앨범은 한 번에 10장까지라 나눠서 보낸다
        for k in range(0, len(pngs), 10):
            part = f"{cap} ({k // 10 + 1}/{-(-len(pngs) // 10)})" if len(pngs) > 10 else cap
            if not d.send_telegram_album(pngs[k:k + 10], part if k == 0 or len(pngs) > 10 else ""):
                raise RuntimeError("텔레그램 발송 실패")


if __name__ == "__main__":
    run(send="--send" in sys.argv)
