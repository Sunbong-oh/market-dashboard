"""나만의 데일리 마켓 대시보드 생성기.

실행: python dashboard.py  ->  dashboard.html 생성 후 브라우저로 열기
데이터: Yahoo Finance(시세), CNN Fear & Greed(Put/Call 비율), Google 뉴스(국내 언론 뉴욕증시 기사 제목)
"""
import http.cookiejar
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

OUT = Path(__file__).with_name("dashboard.html")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
KST = timezone(timedelta(hours=9))
# 미국 거래일 판정용. 주식 일봉(09:30 ET)·선물 일봉(00:00 ET)·마감 시각(16:00 ET)이
# 서머타임 여부와 관계없이 모두 같은 미국 날짜로 떨어지도록 UTC-4로 고정한다.
US_DAY_TZ = timezone(timedelta(hours=-4))

# (표시명, 야후 티커, 종류, 접두/접미, Investing.com 링크)
ITEMS = [
    ("미국 10년물 금리", "^TNX", "yield", "", "https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield"),
    ("VIX 변동성지수", "^VIX", "vix", "", "https://www.investing.com/indices/volatility-s-p-500"),
    ("WTI 원유", "CL=F", "price", "$", "https://www.investing.com/commodities/crude-oil"),
    ("나스닥 종합", "^IXIC", "price", "", "https://www.investing.com/indices/nasdaq-composite"),
    ("금 (Gold)", "GC=F", "price", "$", "https://www.investing.com/commodities/gold"),
    ("비트코인", "BTC-USD", "price", "$", "https://www.investing.com/crypto/bitcoin"),
    ("AMD", "AMD", "price", "$", "https://www.investing.com/equities/adv-micro-device"),
    ("마이크론", "MU", "price", "$", "https://www.investing.com/equities/micron-tech"),
    ("SK하이닉스 ADR", "SKHY", "price", "$", "https://finance.yahoo.com/quote/SKHY"),
    ("팔로알토", "PANW", "price", "$", "https://www.investing.com/equities/palo-alto-networks"),
    ("스페이스X", "SPCX", "price", "$", "https://finance.yahoo.com/quote/SPCX"),
    ("루멘텀", "LITE", "price", "$", "https://www.investing.com/equities/lumentum-holdings-inc"),
]

FINVIZ_MAP_URL = "https://finviz.com/map?t=sec"

CNN_KO = {
    "extreme fear": "극도의 공포", "fear": "공포", "neutral": "중립",
    "greed": "탐욕", "extreme greed": "극도의 탐욕",
}


def fetch_json(url, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
        return json.loads(r.read())


def fetch_quote(item):
    name, sym, kind, unit, link = item
    try:
        j = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=6mo&interval=1d")
        res = j["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
        pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
        # 날짜가 바뀌는 시간대에 마지막 일봉 종가가 비는 경우가 있어, 그때는 meta의 최신 정규장 가격으로 채운다
        m, rt = res["meta"], res["meta"].get("regularMarketTime")
        us_day = lambda t: datetime.fromtimestamp(t, US_DAY_TZ).date()
        if pts and rt and m.get("regularMarketPrice") and us_day(rt) > us_day(pts[-1][0]):
            pts.append((rt, m["regularMarketPrice"]))
        if len(pts) < 2:
            raise ValueError("데이터 부족")
        return dict(name=name, sym=sym, kind=kind, unit=unit, link=link,
                    pts=pts, meta=res["meta"], ok=True)
    except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
        return dict(name=name, sym=sym, kind=kind, unit=unit, link=link, ok=False, err=str(e))


def fetch_cnn():
    try:
        return fetch_json(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            {"Origin": "https://edition.cnn.com",
             "Referer": "https://edition.cnn.com/markets/fear-and-greed"})
    except Exception as e:
        print("CNN 실패:", e, file=sys.stderr)
        return None


NEWS_QUERY = "뉴욕증시 when:1d"
EARN_MIN_CAP = 10e9  # 이 시가총액 이상 기업의 실적 발표만 요약

# 나스닥 실적 일정은 영문명뿐이라, 국내 기사 검색용 한글명(없으면 영문 약칭으로 검색)
KO_NAMES = {
    "AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아", "AMZN": "아마존", "GOOGL": "알파벳",
    "GOOG": "알파벳", "META": "메타", "TSLA": "테슬라", "AVGO": "브로드컴", "AMD": "AMD", "MU": "마이크론",
    "INTC": "인텔", "QCOM": "퀄컴", "ORCL": "오라클", "CRM": "세일즈포스", "ADBE": "어도비", "NFLX": "넷플릭스",
    "PANW": "팔로알토", "CRWD": "크라우드스트라이크", "SNOW": "스노우플레이크", "PLTR": "팔란티어",
    "LITE": "루멘텀", "SPCX": "스페이스X", "TSM": "TSMC", "ASML": "ASML", "ARM": "ARM", "SMCI": "슈퍼마이크로",
    "DELL": "델", "HPE": "HPE", "HPQ": "HP", "CSCO": "시스코", "IBM": "IBM", "ACN": "액센츄어",
    "NKE": "나이키", "SBUX": "스타벅스", "MCD": "맥도날드", "KO": "코카콜라", "PEP": "펩시코", "WMT": "월마트",
    "COST": "코스트코", "TGT": "타깃", "HD": "홈디포", "LOW": "로우스", "DIS": "디즈니", "JPM": "JP모건",
    "BAC": "뱅크오브아메리카", "WFC": "웰스파고", "C": "씨티그룹", "GS": "골드만삭스", "MS": "모건스탠리",
    "V": "비자", "MA": "마스터카드", "PYPL": "페이팔", "UNH": "유나이티드헬스", "JNJ": "존슨앤드존슨",
    "PFE": "화이자", "LLY": "일라이릴리", "MRK": "머크", "ABBV": "애브비", "MRNA": "모더나", "BA": "보잉",
    "CAT": "캐터필러", "GE": "GE", "F": "포드", "GM": "GM", "UBER": "우버", "ABNB": "에어비앤비",
    "FDX": "페덱스", "UPS": "UPS", "XOM": "엑슨모빌", "CVX": "셰브런", "COIN": "코인베이스", "HOOD": "로빈후드",
    "JBL": "자빌", "GIS": "제너럴밀스", "CCL": "카니발", "LEN": "레나", "KMX": "카맥스", "PAYX": "페이첵스",
    "CTAS": "신타스", "DRI": "다든", "CAG": "코나그라", "STZ": "컨스텔레이션브랜즈", "PGR": "프로그레시브",
    "LULU": "룰루레몬", "AZO": "오토존", "ADSK": "오토데스크", "WDAY": "워크데이", "INTU": "인튜이트",
    "MRVL": "마벨", "ANET": "아리스타", "NOW": "서비스나우", "SHOP": "쇼피파이",
}


def _norm(title):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title)


def _similar(a, b):
    """제목 글자 2-gram 겹침 비율. 같은 기사를 여러 매체가 받아쓴 경우를 걸러낸다."""
    ga = {a[i:i + 2] for i in range(len(a) - 1)}
    gb = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(ga & gb) / (min(len(ga), len(gb)) or 1)


def google_news(query):
    """Google 뉴스 RSS(한국어) 검색 결과. raw는 말머리 포함 원제목, title은 말머리·꼬리표를 뗀 제목."""
    return google_news_feed("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
                            + "&hl=ko&gl=KR&ceid=KR:ko", query)


def google_news_feed(url, label=""):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print("뉴스 수집 실패:", label or url, type(e).__name__, file=sys.stderr)
        return []
    items = []
    for it in root.iter("item"):
        src = (it.findtext("source") or "").strip()
        raw = unescape(it.findtext("title") or "").strip()
        if src and raw.endswith(" - " + src):
            raw = raw[:-len(src) - 3].strip()
        raw = re.sub(r"\s+-\s+[^\s-]{2,12}$", "", raw)  # 제목에 남은 ' - 매체명' 꼬리
        # [속보] [美특징주] 등 말머리, '-[美증시 특징주]' 같은 꼬리표 제거
        title = re.sub(r"^\[[^\]]*\]\s*|\s*-?\s*\[[^\]]*\]$", "", raw).strip()
        title = re.sub(r"\s*\((상보|종합|속보|\d보)\)$|\s*·\s*핵심 ?정리$", "", title)  # (상보)·핵심 정리 등 꼬리표
        if src.startswith("v.daum") or len(title) < 12:  # 다음 재전송본은 원문과 중복
            continue
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except Exception:
            continue
        items.append(dict(raw=raw, title=title, src=src, link=it.findtext("link") or "", ts=ts))
    return items


def rank(items, since_ts=None, limit=8):
    """since_ts 이후 기사 먼저, 그 안에서 최신순. 여러 매체가 받아쓴 비슷한 제목은 하나만 남긴다."""
    items = sorted(items, key=lambda n: n["ts"], reverse=True)
    if since_ts:
        items.sort(key=lambda n: n["ts"] < since_ts)  # 안정 정렬이라 최신순 유지
    picked = []
    for n in items:
        k = _norm(n["title"])
        if all(_similar(k, _norm(p["title"])) < 0.55 for p in picked):
            picked.append(n)
        if len(picked) >= limit:
            break
    return picked


def fetch_news(since_ts=None):
    """뉴욕증시 마감 기사 제목 후보. 제목에 '국채금리 부담에 혼조' 같은 등락 이유가 담겨 있다."""
    return rank([n for n in google_news(NEWS_QUERY) if "증시" in n["title"]], since_ts)


# ---------- 한국 시장 영향 뉴스 ----------
KR_THEME_QUERIES = ("수혜주 when:1d", "관련주 when:1d", "특징주 when:1d")
KR_POOL_QUERIES = ("코스피 when:1d", "경제 when:1d", "산업 when:1d", "정부 when:1d")
GN_BUSINESS = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
KR_THEME = re.compile(r"수혜주|관련주|株|주 ?(강세|급등|들썩|훨훨|↑|상승)|[가-힣]주↑")
# 지난 시황(지수 등락·마감)과 미국 증시 기사는 '오늘 영향'이 아니므로 제외
KR_RECAP = re.compile(r"뉴욕증시|美 ?증시|나스닥|다우|S&P|마감|연속|사흘|이틀|연일|보합|장중|후퇴"
                      r"|코스피.*(\d|하락|상승)|코스닥.*(\d|하락|상승)")
KR_SKIP_SRC = ("simplywall", "초이스스탁", "Investing.com", "네이버 프리미엄", "Hypebeast")
KR_STOP = {"증시", "코스", "스피", "주가", "전망", "기대", "강세", "상승", "하락", "오늘", "특징", "징주", "수혜", "혜주",
           "관련", "련주", "국내", "마감", "반등", "급등", "투자", "시장", "종합", "속보", "미국", "한국", "코스닥", "스닥"}


def _grams(t):
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)} - KR_STOP


def fetch_kr_news(n=2, hours=18):
    """오늘 한국 증시에 영향이 클 뉴스 n개.
    후보: 국내 테마(수혜주·관련주·특징주) 기사 + Google 뉴스 경제 주요 기사.
    중요도: 최근 hours시간 동안 같은 주제를 다룬 기사 수(여러 언론이 크게 다룰수록 영향이 크다고 본다)."""
    start = datetime.now(timezone.utc).timestamp() - hours * 3600
    fresh = lambda items: [x for x in items if x["ts"] >= start and not x["src"].startswith(KR_SKIP_SRC)]
    theme = fresh([x for q in KR_THEME_QUERIES for x in google_news(q) if KR_THEME.search(x["raw"])])
    biz = fresh(google_news_feed(GN_BUSINESS, "경제 주요뉴스"))
    pool = {x["link"]: x for x in theme + biz + fresh([x for q in KR_POOL_QUERIES for x in google_news(q)])}
    pool = list(pool.values())
    cands = [x for x in {c["link"]: c for c in theme + biz}.values() if not KR_RECAP.search(x["raw"])]
    for c in cands:
        g = _grams(c["title"])
        c["heat"] = sum(1 for m in pool if m["link"] != c["link"] and len(g & _grams(m["title"])) >= 4)
    cands.sort(key=lambda c: (-c["heat"], -c["ts"]))
    picked = []
    for c in cands:
        if c["heat"] >= 2 and all(len(_grams(c["title"]) & _grams(p["title"])) < 4 for p in picked):
            picked.append(c)
        if len(picked) >= n:
            break
    return picked


def _cap(row):
    try:
        return float(re.sub(r"[^\d.]", "", row.get("marketCap") or "") or 0)
    except ValueError:
        return 0.0


def yahoo_summary(sym, modules):
    """Yahoo quoteSummary. 쿠키+crumb가 있어야 열리므로 세션을 따로 만든다. 실패하면 None."""
    try:
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        op.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
        try:
            op.open("https://fc.yahoo.com", timeout=15)  # 쿠키 발급용(응답 자체는 404)
        except Exception:
            pass
        crumb = op.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).read().decode()
        url = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
               f"?modules={','.join(modules)}&crumb={urllib.parse.quote(crumb)}")
        return json.loads(op.open(url, timeout=20).read())["quoteSummary"]["result"][0]
    except Exception as e:
        print("Yahoo 실적 조회 실패:", sym, type(e).__name__, file=sys.stderr)
        return None


def _raw(d, *keys):
    for k in keys:
        d = (d or {}).get(k)
    return d.get("raw") if isinstance(d, dict) else d


def fetch_whisper(sym):
    """Earnings Whispers 실적 상세(웹페이지가 쓰는 공개 JSON). 실제 EPS·매출과 컨센서스, 위스퍼 넘버,
    회사 가이던스 문장이 들어 있다. 실패하면 None."""
    try:
        return fetch_json(f"https://www.earningswhispers.com/api/epsdetails/{sym.lower()}",
                          {"Referer": f"https://www.earningswhispers.com/epsdetails/{sym.lower()}"})
    except Exception as e:
        print("Earnings Whispers 조회 실패:", sym, type(e).__name__, file=sys.stderr)
        return None


def _guidance(summary):
    """'expects first quarter earnings of $37.15 to $39.15 per share on revenue of $60.0 billion to $63.0 billion.
    The current consensus earnings estimate is $34.83 per share on revenue of $56.6 billion' 형태를 뽑는다."""
    m = re.search(r"expects (\w+) quarter earnings of \$([\d.]+)(?: to \$([\d.]+))? per share"
                  r"(?: on revenue of \$([\d.]+)(?: billion)?(?: to \$([\d.]+))? billion)?", summary or "")
    if not m:
        return None
    c = re.search(r"current consensus earnings estimate is \$([\d.]+) per share(?: on revenue of \$([\d.]+) billion)?",
                  summary)
    f = lambda v: float(v) if v else None
    return dict(q=m.group(1), eps_lo=f(m.group(2)), eps_hi=f(m.group(3)), rev_lo=f(m.group(4)), rev_hi=f(m.group(5)),
                eps_cons=f(c.group(1)) if c else None, rev_cons=f(c.group(2)) if c else None)


def fetch_earnings(session_day):
    """session_day(미국 날짜) 개장 전·마감 후 실적을 낸 기업 중 시가총액 최대 1곳의
    EPS 실제/예상, 매출(전분기 대비), 발표 후 주가 반응(마감 후 발표면 시간외, 개장 전 발표면 당일 정규장).
    EARN_MIN_CAP 미만이면 '주목할 실적 없음'으로 보고 None."""
    try:
        j = fetch_json(f"https://api.nasdaq.com/api/calendar/earnings?date={session_day:%Y-%m-%d}",
                       {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
        rows = (j.get("data") or {}).get("rows") or []
    except Exception as e:
        print("실적 일정 수집 실패:", type(e).__name__, file=sys.stderr)
        return None
    rows = [r for r in rows if r.get("time") in ("time-pre-market", "time-after-hours") and "." not in r["symbol"]]
    if not rows:
        return None
    top = max(rows, key=_cap)
    if _cap(top) < EARN_MIN_CAP:
        return None
    sym = top["symbol"]
    short = re.sub(r",?\s+(Inc|Corp|Corporation|Company|Co|plc|Ltd|Holdings|Technology|Technologies|Brands)\b.*$",
                   "", top["name"]).strip()
    after = top["time"] == "time-after-hours"
    e = dict(sym=sym, name=KO_NAMES.get(sym, short), day=session_day, when="장 마감 후" if after else "개장 전",
             quarter=top.get("fiscalQuarterEnding") or "", eps_act=None, eps_est=None, surprise=None,
             rev=None, rev_qoq=None, px=None, px_pct=None, px_label="시간외" if after else "발표 당일",
             whisper=None, rev_est=None, rev_yoy=None, guide=None)
    try:
        e["eps_est"] = float(re.sub(r"[^\d.\-]", "", top.get("epsForecast") or "").replace("--", "") or "x")
    except ValueError:
        pass

    r = yahoo_summary(sym, ["earnings", "earningsHistory", "price"])
    if not r:
        return e
    q = ((r.get("earnings") or {}).get("earningsChart") or {}).get("quarterly") or []
    last = q[-1] if q else {}
    rep_day = _raw(last, "reportedDate")
    fresh = rep_day and abs(datetime.fromtimestamp(rep_day, timezone.utc).date() - session_day).days <= 1
    if fresh:  # 이번 발표분이 반영됐을 때만 실제치로 쓴다(아니면 직전 분기 값이 나온다)
        hist = ((r.get("earningsHistory") or {}).get("history") or [{}])[-1]
        e["eps_act"] = _raw(hist, "epsActual") or _raw(last, "actual")
        e["eps_est"] = _raw(hist, "epsEstimate") or _raw(last, "estimate") or e["eps_est"]
        if e["eps_act"] is not None and e["eps_est"]:
            e["surprise"] = (e["eps_act"] / e["eps_est"] - 1) * 100
        fin = ((r.get("earnings") or {}).get("financialsChart") or {}).get("quarterly") or []
        if fin:
            e["rev"] = _raw(fin[-1], "revenue")
            prev = _raw(fin[-2], "revenue") if len(fin) > 1 else None
            if e["rev"] and prev:
                e["rev_qoq"] = (e["rev"] / prev - 1) * 100
        fq = re.match(r"(\d)Q(\d{4})", last.get("fiscalQuarter") or "")
        e["quarter"] = f"FY{fq.group(2)[2:]} {fq.group(1)}분기" if fq else e["quarter"]
    pr = r.get("price") or {}
    if after:
        e["px"], pct = _raw(pr, "postMarketPrice"), _raw(pr, "postMarketChangePercent")
    else:
        e["px"], pct = _raw(pr, "regularMarketPrice"), _raw(pr, "regularMarketChangePercent")
    e["px_pct"] = pct * 100 if pct is not None else None
    _apply_whisper(e, fetch_whisper(sym))
    return e


def _apply_whisper(e, w):
    if not w or not w.get("epsDate"):
        return
    try:
        day = datetime.fromisoformat(w["epsDate"]).date()
    except ValueError:
        return
    if abs((day - e["day"]).days) > 1:  # 이번 발표분이 아니면(직전 분기 자료) 쓰지 않는다
        return
    if w.get("eps") is not None:
        e["eps_act"] = w["eps"]
    e["eps_est"] = w.get("estimate") or e["eps_est"]
    e["whisper"] = w.get("whisper")
    e["surprise"] = (e["eps_act"] / e["eps_est"] - 1) * 100 if e["eps_act"] is not None and e["eps_est"] else None
    if w.get("revenue"):
        e["rev"] = w["revenue"] * 1e6  # 백만 달러 단위
        e["rev_est"] = w["revenueEstimate"] * 1e6 if w.get("revenueEstimate") else None
    if w.get("revenueGrowth") is not None:
        e["rev_yoy"] = w["revenueGrowth"] * 100
    e["guide"] = _guidance(w.get("summary"))


# ---------- 포맷 헬퍼 ----------
def fnum(v, d=2):
    return f"{v:,.{d}f}"


def base_at(pts, days):
    """마지막 시점보다 days(달력일) 이전의 종가. 그만큼의 과거 데이터가 없으면 None."""
    cutoff = pts[-1][0] - days * 86400
    if pts[0][0] > cutoff + 4 * 86400:
        return None
    return [c for t, c in pts if t <= cutoff][-1] if pts[0][0] <= cutoff else pts[0][1]


def pct_back(pts, days):
    base = base_at(pts, days)
    return (pts[-1][1] / base - 1) * 100 if base else None


def cls(v):
    return "up" if v > 0 else "down" if v < 0 else "flat"


def chg_chip(label, v, suffix="%", d=2, extra=None):
    if v is None:
        return f'<div class="chip"><span>{label}</span><b class="flat">–</b></div>'
    sign = "+" if v > 0 else ""
    tail = f' <small>({"+" if extra > 0 else ""}{extra:.2f}%)</small>' if extra is not None else ""
    return f'<div class="chip"><span>{label}</span><b class="{cls(v)}">{sign}{v:.{d}f}{suffix}</b>{tail}</div>'


def sparkline(values, w=300, h=64, color_cls="flat"):
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    n = len(values)
    pad = 4
    xy = [(i / (n - 1) * w, pad + (1 - (v - lo) / rng) * (h - 2 * pad)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"0,{h} {line} {w},{h}"
    lx, ly = xy[-1]
    return (f'<svg class="spark {color_cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polygon points="{area}" class="area"/>'
            f'<polyline points="{line}" class="line" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" class="dot"/></svg>')


def vix_label(v):
    if v < 15: return "안정"
    if v < 20: return "보통"
    if v < 30: return "불안"
    return "공포"


def card(q):
    if not q["ok"]:
        return (f'<article class="card"><header><h3>{escape(q["name"])}</h3>'
                f'<span class="sym">{escape(q["sym"])}</span></header>'
                f'<p class="err">데이터를 가져오지 못했습니다<br><small>{escape(q["err"])}</small></p></article>')
    pts = q["pts"]
    last, prev = pts[-1][1], pts[-2][1]
    is_yield = q["kind"] == "yield"
    d1 = last - prev
    d1p = (last / prev - 1) * 100

    if is_yield:
        main = f"{fnum(last, 3)}<small>%</small>"
        sub_v = d1 * 100
        sub = (f'<span class="{cls(sub_v)}">{"+" if sub_v > 0 else ""}{sub_v:.1f}bp '
               f'({"+" if d1p > 0 else ""}{d1p:.2f}%)</span>')
        chips = "".join(chg_chip(l, (last - base_at(pts, n)) * 100 if base_at(pts, n) else None, "bp", 1,
                                 extra=pct_back(pts, n))
                        for l, n in (("1주", 7), ("1개월", 30), ("3개월", 91)))
    else:
        main = f'<small>{q["unit"]}</small>{fnum(last)}'
        sub = (f'<span class="{cls(d1)}">{"▲" if d1 > 0 else "▼" if d1 < 0 else "–"} '
               f'{fnum(abs(d1))} ({"+" if d1p > 0 else ""}{d1p:.2f}%)</span>')
        chips = "".join(chg_chip(l, pct_back(pts, n)) for l, n in (("1주", 7), ("1개월", 30), ("3개월", 91)))

    badge = ""
    if q["kind"] == "vix":
        badge = f'<span class="badge">{vix_label(last)}</span>'

    recent = [pt for pt in pts if pt[0] >= pts[-1][0] - 91 * 86400]
    vals = [c for _, c in recent]
    trend_cls = cls(vals[-1] - vals[0])
    lo, hi = min(vals), max(vals)
    pos = (last - lo) / ((hi - lo) or 1) * 100
    fmt = (lambda v: fnum(v, 3)) if is_yield else fnum
    # 미국 거래일 기준(코인은 UTC 자정 일봉이라 UTC 날짜)
    asof = datetime.fromtimestamp(pts[-1][0], timezone.utc if q["sym"].endswith("-USD") else US_DAY_TZ).strftime("%m/%d")

    return f'''<article class="card">
  <header><h3><a href="{q["link"]}" target="_blank" rel="noopener">{escape(q["name"])}</a></h3>
  <span class="sym">{escape(q["sym"])} · {asof}</span></header>
  <div class="price">{main} {badge}</div>
  <div class="delta">{sub}</div>
  {sparkline(vals, color_cls=trend_cls)}
  <div class="range"><span>{fmt(lo)}</span><div class="bar"><i style="left:{pos:.0f}%"></i></div><span>{fmt(hi)}</span></div>
  <div class="range-cap">3개월 범위 내 위치</div>
  <div class="chips">{chips}</div>
</article>'''


# ---------- Fear & Greed ----------
ZONES = [(0, 25, "#c0392b"), (25, 45, "#e67e22"), (45, 55, "#95a5a6"), (55, 75, "#7fb069"), (75, 100, "#2e9e5b")]


def zone_color(score):
    for a, b, col in ZONES:
        if score <= b:
            return col
    return ZONES[-1][2]


def pick_headline(news):
    """후보 중 등락 이유가 드러나는('…에 혼조', '…에도 상승') 간결한 제목을 우선 고른다."""
    for n in news:
        t = n["title"]
        if len(t) <= 56 and ("…" in t or "에 " in t or "에도" in t or "속" in t):
            return n
    return news[0] if news else None


def headline_block(news):
    n = pick_headline(news)
    if not n:
        return '<p class="err">뉴스를 가져오지 못했습니다.</p>'
    when = datetime.fromtimestamp(n["ts"], KST)
    # '…나스닥 0.24%↑'처럼 뒤에 붙은 지수 등락 꼬리는 떼고 요인만 남긴다
    title = re.sub(r"\s*(…|\.{2,})[^…]*\d[^…]*$", "", n["title"]).strip(" ….") or n["title"]
    return (f'<a class="headline" href="{escape(n["link"])}" target="_blank" rel="noopener">{escape(title)}</a>'
            f'<div class="hl-src">{escape(n["src"])} · {when:%m/%d %H:%M}</div>')


def src_line(n):
    return f'<div class="it-src">{escape(n["src"])} · {datetime.fromtimestamp(n["ts"], KST):%m/%d %H:%M}</div>'


def kr_block(items):
    if not items:
        body = '<p class="err">관련 뉴스를 찾지 못했습니다.</p>'
    else:
        body = "".join(f'<li><a href="{escape(k["link"])}" target="_blank" rel="noopener">{escape(k["title"])}</a>'
                       f'{src_line(k)}</li>' for k in items)
        body = f'<ol class="items">{body}</ol>'
    return f'<section class="panel kr"><div class="tag">오늘 한국 시장 영향</div>{body}</section>'


def _usd(v):
    """매출 표기: 1억 달러 단위(예: 54.23B -> 542.3억 달러)."""
    eok = v / 1e8
    return f"{eok / 1e4:,.2f}조 달러" if eok >= 1e4 else f"{eok:,.1f}억 달러"


def _pct(v, d=1):
    return f'<b class="{cls(v)}">{"+" if v > 0 else ""}{v:.{d}f}%</b>'


def _vs(act, ref, label):
    """실제치가 기준(컨센서스/위스퍼)보다 몇 % 높은지/낮은지."""
    if act is None or not ref:
        return ""
    v = (act / ref - 1) * 100
    word = "상회" if v > 0.05 else "하회" if v < -0.05 else "부합"
    return f'<div class="vs"><small>{label}</small>{_pct(v)} {word}</div>'


def earnings_block(e):
    if not e:
        return ""
    q = f' · {escape(e["quarter"])}' if e["quarter"] else ""
    rows = []
    if e["eps_act"] is not None:
        refs = " · ".join(x for x in (f'컨센 ${e["eps_est"]:,.2f}' if e["eps_est"] else "",
                                       f'위스퍼 ${e["whisper"]:,.2f}' if e["whisper"] else "") if x)
        rows.append(f'<div class="er"><span class="ek">EPS</span><span class="evv">${e["eps_act"]:,.2f}<small>{refs}</small></span>'
                    f'<span class="ev">{_vs(e["eps_act"], e["eps_est"], "컨센")}{_vs(e["eps_act"], e["whisper"], "위스퍼")}</span></div>')
    else:
        refs = " · ".join(x for x in (f'컨센서스 ${e["eps_est"]:,.2f}' if e["eps_est"] else "",
                                       f'위스퍼 ${e["whisper"]:,.2f}' if e["whisper"] else "", "실제치 집계 전") if x)
        rows.append(f'<div class="er"><span class="ek">EPS</span><span class="evv"><small>{refs}</small></span></div>')
    if e["rev"]:
        est = f'<small>예상 {_usd(e["rev_est"])}</small>' if e["rev_est"] else ""
        if e["rev_est"]:
            right = _vs(e["rev"], e["rev_est"], "예상")
        else:
            right = f'<div class="vs"><small>전분기 대비</small>{_pct(e["rev_qoq"])}</div>' if e["rev_qoq"] is not None else ""
        if e["rev_yoy"] is not None:
            right += f'<div class="vs"><small>전년 대비</small>{_pct(e["rev_yoy"], 0)}</div>'
        rows.append(f'<div class="er"><span class="ek">매출</span><span class="evv">{_usd(e["rev"])}{est}</span>'
                    f'<span class="ev">{right}</span></div>')
    g = e["guide"]
    if g and g["eps_lo"]:
        rng = f'${g["eps_lo"]:,.2f}' + (f'~{g["eps_hi"]:,.2f}' if g["eps_hi"] else "")
        mid = (g["eps_lo"] + (g["eps_hi"] or g["eps_lo"])) / 2
        cons = f'<small>다음 분기 · 컨센 ${g["eps_cons"]:,.2f}</small>' if g["eps_cons"] else "<small>다음 분기</small>"
        right = _vs(mid, g["eps_cons"], "중간값") if g["eps_cons"] else ""
        rows.append(f'<div class="er"><span class="ek">가이던스</span><span class="evv">{rng}{cons}</span>'
                    f'<span class="ev">{right}</span></div>')
    if e["px"] is not None and e["px_pct"] is not None:
        rows.append(f'<div class="er"><span class="ek">{e["px_label"]}</span><span class="evv">${e["px"]:,.2f}</span>'
                    f'<span class="ev">{_pct(e["px_pct"], 2)}</span></div>')
    return (f'<div class="panel earn"><div class="tag">실적 발표</div>'
            f'<div class="earn-co"><b>{escape(e["name"])}</b><span>{escape(e["sym"])} · {e["day"]:%m/%d} {e["when"]} 발표{q}</span></div>'
            f'<div class="erows">{"".join(rows)}</div></div>')


def top_section(cnn, news, earnings, kr):
    if cnn:
        pc, hd = cnn["put_call_options"], cnn["put_call_options"]["data"][-1]
        s = pc["score"]
        col = zone_color(s)
        hist = [p["y"] for p in pc["data"]][-90:]
        pc_html = f'''<div class="pc-grid"><div class="comp"><div class="ct"><b>Put/Call 비율</b><span class="cv">{hd["y"]:.2f}</span></div>
  <div class="cbar"><i style="width:{s:.0f}%;background:{col}"></i></div>
  <div class="cn"><span>5일 평균 · 낮을수록 탐욕, 높을수록 공포</span><em style="color:{col}">{CNN_KO.get(pc["rating"], pc["rating"])} · {s:.0f}</em></div></div>
  <div class="fg-hist"><div class="fg-hist-cap">최근 90일 추이 (현재 {hist[-1]:.2f} / 범위 {min(hist):.2f}~{max(hist):.2f})</div>{sparkline(hist, h=90, color_cls="flat")}</div></div>'''
    else:
        pc_html = '<p class="err">CNN 데이터를 가져오지 못했습니다.</p>'

    return f'''<section class="fg driver">
  {headline_block(news)}
</section>
{earnings_block(earnings)}
{kr_block(kr)}
<section class="fg">
  <h2>Put/Call 비율 (CNN)</h2>
  {pc_html}
</section>'''


# ---------- 텔레그램 ----------
def load_env(key):
    v = os.environ.get(key)
    if v:
        return v
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, val = line.partition("=")
            if k.strip() == key:
                return val.strip().strip('"').strip("'")
    return None


def build_summary(quotes, cnn, now):
    lines = [f"📊 데일리 마켓 {now:%m/%d}({'월화수목금토일'[now.weekday()]}) {now:%H:%M} KST", ""]
    if cnn:
        fg = cnn["fear_and_greed"]
        pc = cnn["put_call_options"]["data"][-1]["y"]
        lines.append(f"😨 공포탐욕 {round(fg['score'])} ({CNN_KO.get(fg['rating'], fg['rating'])})"
                     f" · 전일 {round(fg['previous_close'])} / 1주전 {round(fg['previous_1_week'])}")
        lines.append(f"⚖️ Put/Call {pc:.2f}")
        lines.append("")
    for q in quotes:
        if not q["ok"]:
            lines.append(f"• {q['name']}: 수집 실패")
            continue
        last, prev = q["pts"][-1][1], q["pts"][-2][1]
        arrow = "🔺" if last > prev else "🔻" if last < prev else "➖"
        if q["kind"] == "yield":
            lines.append(f"• {q['name']}: {last:.3f}% {arrow} {(last - prev) * 100:+.1f}bp")
        else:
            lines.append(f"• {q['name']}: {q['unit']}{last:,.2f} {arrow} {(last / prev - 1) * 100:+.2f}%")
    return "\n".join(lines)


def split_targets(chat):
    """TELEGRAM_CHAT_ID는 쉼표로 여러 대상(개인 ID, @채널명, -100...)을 적을 수 있다."""
    return [t.strip() for t in chat.split(",") if t.strip()]


def send_telegram(text):
    token, chat = load_env("TELEGRAM_BOT_TOKEN"), load_env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("텔레그램 설정 없음: .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID를 넣으세요.", file=sys.stderr)
        return False
    ok = True
    for target in split_targets(chat):
        data = urllib.parse.urlencode({"chat_id": target, "text": text}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20) as r:
                res = json.loads(r.read()).get("ok", False)
        except Exception as e:
            # 토큰이 URL에 들어 있으므로 예외 메시지를 그대로 출력하지 않는다
            print("텔레그램 발송 실패:", target, type(e).__name__, getattr(e, "code", ""), file=sys.stderr)
            res = False
        print(f"텔레그램 발송 {'완료' if res else '실패'}: {target}")
        ok = ok and res
    return ok


def find_browsers():
    """설치된 헤드리스 캡처용 브라우저를 우선순위대로 모두 반환한다.
    한쪽(예: Edge)이 일시적으로 먹통이어도 다른 쪽(Chrome)으로 넘어가기 위함."""
    return [p for p in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ) if Path(p).exists()]


def _run_killtree(cmd, timeout):
    """subprocess.run이되, 시간 초과 시 자식까지 통째로 죽인다(안 그러면 헤드리스 Edge가
    좀비 프로세스로 남아 다음 실행의 임시 프로필 정리를 방해한다)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        proc.communicate()
        raise


def _screenshot_once(exe, uri, png_path, width, timeout):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:
        base = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                "--no-first-run", "--disable-extensions", "--disable-background-networking",
                "--disable-sync", "--disable-default-apps", "--disable-component-update", "--mute-audio"]
        dom = _run_killtree(base + [f"--window-size={width},2400", "--virtual-time-budget=3000", "--dump-dom", uri],
                            timeout).decode("utf-8", "ignore")
        m = re.search(r'data-h="(\d+)"', dom)
        height = int(m.group(1)) + 16 if m else 1400
        Path(png_path).unlink(missing_ok=True)
        _run_killtree(base + [f"--window-size={width},{height}", "--force-device-scale-factor=2",
                              f"--screenshot={png_path}", uri], timeout)
    return Path(png_path).exists() and Path(png_path).stat().st_size > 10_000


def screenshot(png_path, width=900, attempts=3, timeout=150):
    """헤드리스 Edge/Chrome으로 dashboard.html 전체를 PNG로 저장. 실패하면 False.
    부팅 직후 등 시스템이 무거운 시점을 대비해 시간 초과 시 재시도하고,
    한쪽 브라우저가 통째로 먹통이면 설치된 다른 브라우저로 넘어간다."""
    exes = find_browsers()
    if not exes:
        return False
    uri = OUT.as_uri() + '#shot'
    for exe in exes:
        for i in range(1, attempts + 1):
            try:
                if _screenshot_once(exe, uri, png_path, width, timeout):
                    return True
                print(f"스크린샷 시도 {Path(exe).stem} {i}/{attempts}: 결과 파일이 비정상", file=sys.stderr)
            except Exception as e:
                print(f"스크린샷 시도 {Path(exe).stem} {i}/{attempts} 실패:", type(e).__name__, file=sys.stderr)
    return False


def send_telegram_photo(png_path, caption):
    token, chat = load_env("TELEGRAM_BOT_TOKEN"), load_env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    crlf = bytes([13, 10])
    img = Path(png_path).read_bytes()
    ok = True
    for target in split_targets(chat):
        bd = uuid.uuid4().hex
        parts = []
        for k, v in (("chat_id", target), ("caption", caption)):
            parts.append(f'--{bd}'.encode() + crlf + f'Content-Disposition: form-data; name="{k}"'.encode()
                         + crlf + crlf + v.encode("utf-8") + crlf)
        parts.append(f'--{bd}'.encode() + crlf + b'Content-Disposition: form-data; name="photo"; filename="dashboard.png"'
                     + crlf + b"Content-Type: image/png" + crlf + crlf + img + crlf)
        parts.append(f'--{bd}--'.encode() + crlf)
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", b"".join(parts),
                                     {"Content-Type": f"multipart/form-data; boundary={bd}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read()).get("ok", False)
        except Exception as e:
            print("사진 발송 실패:", target, type(e).__name__, getattr(e, "code", ""), file=sys.stderr)
            res = False
        print(f"텔레그램 사진 {'발송 완료' if res else '발송 실패'}: {target}")
        ok = ok and res
    return ok


def report_title(now):
    """예: 26년 9월 27일 미국 데일리 마켓"""
    return f"{now.year % 100}년 {now.month}월 {now.day}일 미국 데일리 마켓"


def save_blog_post(png, now):
    """블로그 게시용 준비물: blog_post/제목.txt + blog_post/YYYY-MM-DD_미국데일리마켓.png"""
    title = report_title(now)
    folder = OUT.with_name("blog_post")
    folder.mkdir(exist_ok=True)
    (folder / "제목.txt").write_text(title, encoding="utf-8")
    shutil.copy(png, folder / f"{now:%Y-%m-%d}_미국데일리마켓.png")
    print("블로그 준비물 저장:", title)


def notify(quotes, cnn, now):
    png = OUT.with_name("dashboard.png")
    caption = (f"📊 데일리 마켓 {now:%m/%d}({'월화수목금토일'[now.weekday()]}) {now:%H:%M} KST\n"
               f"종목별 지도: {FINVIZ_MAP_URL}")
    sent = False
    if screenshot(png):
        save_blog_post(png, now)
        sent = send_telegram_photo(png, caption)
    if not sent:
        print("사진 발송 불가/실패 -> 텍스트 요약으로 대체")
        send_telegram(build_summary(quotes, cnn, now))


CSS = """
:root{--bg:#f4f5f7;--card:#fff;--text:#1c2330;--muted:#6b7385;--line:#e3e6ec;--up:#d63c3c;--down:#2f6fdb;--flat:#8a92a3;--accent:#f08c00;--hd1:#ffd43b;--hd2:#ff922b;--hd-text:#2b1a00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;--line:#272f3d;--up:#ff5d5d;--down:#5b9bff;--flat:#7b8496;--accent:#ffa94d;--hd1:#f59f00;--hd2:#e8590c;--hd-text:#1a0f00}}
:root[data-theme=dark]{--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;--line:#272f3d;--up:#ff5d5d;--down:#5b9bff;--flat:#7b8496;--accent:#ffa94d;--hd1:#f59f00;--hd2:#e8590c;--hd-text:#1a0f00}
:root[data-color=us]{--up:#1f9d55;--down:#d63c3c}
:root[data-color=us][data-theme=dark]{--up:#3ddc84;--down:#ff5d5d}
@media (prefers-color-scheme:dark){:root[data-color=us]:not([data-theme=light]){--up:#3ddc84;--down:#ff5d5d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:'Malgun Gothic','Segoe UI',system-ui,sans-serif;line-height:1.4}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 48px}
.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-bottom:16px;
  padding:22px 24px;border-radius:18px;color:var(--hd-text);background:linear-gradient(120deg,var(--hd1),var(--hd2));
  box-shadow:0 6px 18px -8px rgba(232,89,12,.55)}
.kicker{font-size:13px;font-weight:800;letter-spacing:.18em;opacity:.7}
h1{margin:2px 0 0;font-size:32px;font-weight:800;letter-spacing:-.01em}.top .sub{color:var(--hd-text);opacity:.8;font-size:16px;margin-top:6px}
.top .tools button{background:rgba(255,255,255,.35);border-color:rgba(0,0,0,.08);color:var(--hd-text)}
.tools button{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer;margin-left:6px}
h2{font-size:22px;margin:26px 0 12px;color:var(--text);font-weight:700;letter-spacing:.01em}
a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.fg+.fg{margin-top:14px}
.card,.fg{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.card header{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.card h3{margin:0;font-size:19px;font-weight:700}.sym{color:var(--muted);font-size:13px;white-space:nowrap}
.price{font-size:36px;font-weight:700;margin-top:6px;font-variant-numeric:tabular-nums}.price small{font-size:19px;font-weight:500;color:var(--muted);margin:0 2px}
.badge{font-size:14px;font-weight:600;background:var(--bg);border:1px solid var(--line);padding:2px 8px;border-radius:99px;vertical-align:middle;color:var(--muted)}
.delta{font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--flat)}
.spark{width:100%;height:64px;margin-top:8px;display:block}
.spark .line{fill:none;stroke:currentColor;stroke-width:1.8}.spark .area{fill:currentColor;opacity:.10}.spark .dot{fill:currentColor}
.spark.up{color:var(--up)}.spark.down{color:var(--down)}.spark.flat{color:var(--flat)}
.range{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--muted);margin-top:8px;font-variant-numeric:tabular-nums}
.bar{flex:1;height:4px;background:var(--line);border-radius:4px;position:relative}
.bar i{position:absolute;top:-3px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--accent)}
.range-cap{font-size:13px;color:var(--muted);text-align:center;margin-top:2px}
.chips{display:flex;gap:5px;margin-top:10px}.chip{flex:1;background:var(--bg);border-radius:8px;padding:6px 6px;font-size:14px;display:flex;flex-direction:column;min-width:0}
.chip span{color:var(--muted)}.chip b{white-space:nowrap;font-size:16px;font-variant-numeric:tabular-nums}.chip small{color:var(--muted);font-size:12px}
.err{color:var(--muted);font-size:16px}
.fg{padding:16px 18px}.fg h2{margin-top:0}
.fg-grid{display:grid;grid-template-columns:minmax(260px,340px) 1fr;gap:24px}
@media (max-width:760px){.fg-grid{grid-template-columns:1fr}}
.top-grid{display:grid;grid-template-columns:1fr minmax(260px,320px);gap:24px}
@media (max-width:760px){.top-grid{grid-template-columns:1fr}}
.driver{border-left:6px solid var(--accent);padding:18px 22px}
.headline{display:block;font-size:30px;font-weight:800;line-height:1.35;letter-spacing:-.01em}
.hl-src{font-size:14px;color:var(--muted);margin-top:10px}
.driver+.panel,.panel+.panel,.panel+.fg{margin-top:14px}
.panel.kr{border-left:6px solid var(--hd1)}.panel.kr .tag{background:linear-gradient(120deg,var(--hd1),var(--hd2))}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.tag{display:inline-block;font-size:14px;font-weight:800;color:var(--hd-text);background:var(--hd1);
  padding:3px 12px;border-radius:99px;margin-bottom:8px}
.panel.earn .tag{background:var(--hd2)}
.items{list-style:none;margin:0;padding:0;counter-reset:i}
.items li{counter-increment:i;position:relative;padding:10px 0 10px 34px;font-size:20px;font-weight:700;line-height:1.4}
.items li+li{border-top:1px solid var(--line)}
.items li:before{content:counter(i);position:absolute;left:0;top:12px;width:24px;height:24px;border-radius:50%;
  background:var(--accent);color:#fff;font-size:14px;font-weight:800;text-align:center;line-height:24px}
.it-src{font-size:13px;font-weight:400;color:var(--muted);margin-top:3px}
.earn-co{font-size:14px;color:var(--muted);margin:2px 0 8px}.earn-co b{display:block;font-size:24px;color:var(--text)}
.erows{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-top:6px;border-top:1px solid var(--line)}
.er{display:flex;flex-direction:column;gap:4px;padding:12px 14px 4px;border-left:1px solid var(--line)}.er:first-child{border-left:0;padding-left:0}
.ek{font-size:15px;color:var(--muted);font-weight:700}.evv{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}.evv small{display:block;font-size:13px;font-weight:400;color:var(--muted)}
.ev{font-size:15px;white-space:nowrap}.ev b{font-size:18px}.ev small{display:block;font-size:12px;color:var(--muted)}
.vs{line-height:1.25}.vs+.vs{margin-top:4px}.vs small{display:inline!important;margin-right:5px}
.ek{line-height:1.25}
.pc-grid{display:grid;grid-template-columns:minmax(240px,1fr) 1.3fr;gap:24px;align-items:center}
@media (max-width:640px){.pc-grid{grid-template-columns:1fr}}
.fg-main{text-align:center}.gauge{width:100%;max-width:300px}
.gauge .needle{stroke:var(--text);stroke-width:3;stroke-linecap:round}.gauge .hub{fill:var(--text)}.gauge .gl{font-size:9px;fill:var(--muted)}
.fg-score{font-size:44px;font-weight:800;line-height:1;margin-top:-6px}.fg-rating{font-weight:700;margin:4px 0 12px}
.cmps{display:flex;gap:6px}.cmp{flex:1;background:var(--bg);border-radius:8px;padding:6px 4px;font-size:11px;display:flex;flex-direction:column}.cmp span{color:var(--muted)}.cmp b{font-size:16px}
.fg-hist .spark{height:110px}.fg-hist-cap{font-size:14px;color:var(--muted);text-align:left}
.fg-comps{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px 20px;align-content:start}
.ct{display:flex;justify-content:space-between;align-items:baseline;font-size:18px;gap:8px}.cv{font-size:24px;font-variant-numeric:tabular-nums;font-weight:600}.cv small{color:var(--muted);font-weight:400}
.cbar{height:10px;background:var(--line);border-radius:6px;margin:5px 0;overflow:hidden}.cbar i{display:block;height:100%}
.cn{display:flex;justify-content:space-between;gap:8px;font-size:14px;color:var(--muted)}.cn em{font-style:normal;font-weight:600;white-space:nowrap}
:root[data-shot] .tools,:root[data-shot] footer{display:none}
footer{margin-top:24px;color:var(--muted);font-size:14px}
"""

JS = """
const r=document.documentElement,g=k=>{try{return localStorage.getItem(k)}catch(e){return null}},s=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
if(location.hash==='#shot')r.dataset.shot='1';if(g('color')==='us')r.dataset.color='us';if(g('theme'))r.dataset.theme=g('theme');
document.getElementById('bc').onclick=()=>{const u=r.dataset.color!=='us';u?r.dataset.color='us':delete r.dataset.color;s('color',u?'us':'kr');lab()};
document.getElementById('bt').onclick=()=>{const d=(r.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'))==='dark';r.dataset.theme=d?'light':'dark';s('theme',r.dataset.theme)};
function lab(){document.getElementById('bc').textContent=r.dataset.color==='us'?'색상: 상승 초록':'색상: 상승 빨강'}lab();
"""


def main():
    with ThreadPoolExecutor(max_workers=10) as ex:
        cnn_f = ex.submit(fetch_cnn)
        quotes = list(ex.map(fetch_quote, ITEMS))
        cnn = cnn_f.result()
    nas = next((q for q in quotes if q["ok"] and q["sym"] == "^IXIC"), None)
    # 일봉 타임스탬프는 개장 시각(13:30~14:30 UTC)이라 +6시간이면 마감 무렵이 된다
    since = nas["pts"][-1][0] + 6 * 3600 if nas else None
    # 일봉 타임스탬프(미 동부 개장 시각)의 날짜 = 가장 최근 미국 거래일
    session_day = (datetime.fromtimestamp(nas["pts"][-1][0], US_DAY_TZ).date()
                   if nas else (datetime.now(KST) - timedelta(days=1)).date())
    news = fetch_news(since)
    earnings = fetch_earnings(session_day)
    kr = fetch_kr_news()

    now = datetime.now(KST)
    weekday = "월화수목금토일"[now.weekday()]
    cards = "".join(card(q) for q in quotes)
    failed = [q["name"] for q in quotes if not q["ok"]]

    html = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{report_title(now)}</title><style>{CSS}</style></head><body><div class="wrap">
<header class="top"><div><div class="kicker">DAILY US MARKET</div><h1>{report_title(now)}</h1>
<div class="sub">{now:%Y-%m-%d}({weekday}) {now:%H:%M} KST 기준 · 일봉 종가 기준 (장중이면 현재가)</div></div>
<div class="tools"><button id="bc"></button><button id="bt">라이트/다크</button></div></header>
{top_section(cnn, news, earnings, kr)}
<h2>주요 지표</h2>
<div class="grid">{cards}</div>
<footer>출처: Yahoo Finance(시세, 지연 가능), CNN Fear &amp; Greed(Put/Call 비율), Google 뉴스(국내 언론 뉴욕증시 기사 제목). 카드 제목을 누르면 Investing.com(또는 Yahoo) 상세 페이지로 이동합니다.
SK하이닉스 ADR은 나스닥 SKHY, 스페이스X는 나스닥 SPCX 기준.
투자 판단의 근거가 아닌 참고용입니다.{"<br>수집 실패: " + ", ".join(failed) if failed else ""}</footer>
</div><script>{JS}</script>
<script>document.documentElement.dataset.h=Math.ceil(document.querySelector('.wrap').getBoundingClientRect().bottom)</script></body></html>'''
    OUT.write_text(html, encoding="utf-8")
    print(f"생성 완료: {OUT}" + (f" (실패: {', '.join(failed)})" if failed else ""))
    if "--notify" in sys.argv:
        notify(quotes, cnn, now)
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
