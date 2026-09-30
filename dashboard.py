"""나만의 데일리 마켓 대시보드 생성기.

실행: python dashboard.py  ->  dashboard.html 생성 후 브라우저로 열기
데이터: Yahoo Finance(시세), CNN Fear & Greed(Put/Call 비율), Google 뉴스(국내 언론 뉴욕증시 기사 제목)
"""
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
NEWS_MAX = 6


def _norm(title):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title)


def _similar(a, b):
    """제목 글자 2-gram 겹침 비율. 같은 기사를 여러 매체가 받아쓴 경우를 걸러낸다."""
    ga = {a[i:i + 2] for i in range(len(a) - 1)}
    gb = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(ga & gb) / (min(len(ga), len(gb)) or 1)


def fetch_news(since_ts=None):
    """국내 언론의 최근 하루 뉴욕증시 기사 제목을 모은다(Google 뉴스 RSS).
    since_ts(미 증시 마감 무렵) 이후 기사를 우선하고, 모자라면 그 전 최신 기사로 채운다.
    기사 제목에 이미 '국채금리 부담에 혼조' 같은 등락 이유가 담겨 있어 그대로 요인으로 쓴다."""
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(NEWS_QUERY)
           + "&hl=ko&gl=KR&ceid=KR:ko")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print("뉴스 수집 실패:", type(e).__name__, file=sys.stderr)
        return []
    items = []
    for it in root.iter("item"):
        src = (it.findtext("source") or "").strip()
        title = unescape(it.findtext("title") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[:-len(src) - 3].strip()
        title = re.sub(r"^\[[^\]]*\]\s*|\s*\[[^\]]*\]$", "", title).strip()  # [속보] [○○ 브리핑] 등 말머리·꼬리표
        if "증시" not in title or src.startswith("v.daum") or len(title) < 12:
            continue
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except Exception:
            continue
        items.append(dict(title=title, src=src, link=it.findtext("link") or "", ts=ts))
    items.sort(key=lambda n: n["ts"], reverse=True)
    if since_ts:
        items.sort(key=lambda n: n["ts"] < since_ts)  # 마감 후 기사 먼저(안정 정렬이라 최신순 유지)
    picked = []
    for n in items:
        k = _norm(n["title"])
        if all(_similar(k, _norm(p["title"])) < 0.55 for p in picked):
            picked.append(n)
        if len(picked) >= NEWS_MAX:
            break
    return picked


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
    asof = datetime.fromtimestamp(pts[-1][0], KST).strftime("%m/%d")

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


def market_driver_summary(quotes):
    """뉴스 문구 없이, 이미 수집한 실제 수치로만 등락 요인을 한 줄로 요약한다.
    (실제 뉴스의 인과 서술("관세 우려 완화" 등)은 매일 무인 실행에서 검증할 방법이
    없어 넣지 않는다 — 숫자로 확인 가능한 사실만 말한다.)"""
    def find(sym):
        return next((q for q in quotes if q["ok"] and q["sym"] == sym), None)

    parts = []
    nas = find("^IXIC")
    if nas:
        last, prev = nas["pts"][-1][1], nas["pts"][-2][1]
        chg = (last / prev - 1) * 100
        parts.append(f"나스닥 {chg:+.2f}%")

    tnx = find("^TNX")
    if tnx:
        last, prev = tnx["pts"][-1][1], tnx["pts"][-2][1]
        parts.append(f"10년물 금리 {(last - prev) * 100:+.1f}bp")

    vix = find("^VIX")
    if vix:
        last, prev = vix["pts"][-1][1], vix["pts"][-2][1]
        vd = last - prev
        vd_str = "0.0" if abs(vd) < 0.05 else f"{vd:+.1f}"
        parts.append(f"VIX {last:.1f}({vix_label(last)}, {vd_str})")

    return " · ".join(parts) if parts else "데이터를 가져오지 못했습니다."


def news_list(news):
    if not news:
        return '<p class="err">뉴스를 가져오지 못했습니다.</p>'
    rows = "".join(
        f'<li><a href="{escape(n["link"])}" target="_blank" rel="noopener">{escape(n["title"])}</a>'
        f'<span class="src">{escape(n["src"])} · {datetime.fromtimestamp(n["ts"], KST):%m/%d %H:%M}</span></li>'
        for n in news)
    return f'<ul class="news">{rows}</ul>'


def top_section(cnn, quotes, news):
    driver = market_driver_summary(quotes)

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

    return f'''<section class="fg">
  <h2>미국 증시 상승·하락 요인</h2>
  <p class="driver-line">{escape(driver)}</p>
  {news_list(news)}
  <div class="driver-cap">국내 언론 뉴욕증시 기사 제목(Google 뉴스, 최근 24시간) · 요약 수치는 전일 종가 대비</div>
</section>
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
:root{--bg:#f4f5f7;--card:#fff;--text:#1c2330;--muted:#6b7385;--line:#e3e6ec;--up:#d63c3c;--down:#2f6fdb;--flat:#8a92a3;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;--line:#272f3d;--up:#ff5d5d;--down:#5b9bff;--flat:#7b8496;--accent:#7b93ff}}
:root[data-theme=dark]{--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;--line:#272f3d;--up:#ff5d5d;--down:#5b9bff;--flat:#7b8496;--accent:#7b93ff}
:root[data-color=us]{--up:#1f9d55;--down:#d63c3c}
:root[data-color=us][data-theme=dark]{--up:#3ddc84;--down:#ff5d5d}
@media (prefers-color-scheme:dark){:root[data-color=us]:not([data-theme=light]){--up:#3ddc84;--down:#ff5d5d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:'Malgun Gothic','Segoe UI',system-ui,sans-serif;line-height:1.4}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 48px}
.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-bottom:18px}
h1{margin:0;font-size:30px}.sub{color:var(--muted);font-size:16px;margin-top:4px}
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
.driver-line{font-size:22px;font-weight:700;line-height:1.5;margin:2px 0 6px}
.news{list-style:none;margin:0;padding:0}.news li{font-size:20px;line-height:1.45;padding:10px 0 10px 20px;border-top:1px solid var(--line);position:relative}
.news li:before{content:'';position:absolute;left:3px;top:21px;width:8px;height:8px;border-radius:50%;background:var(--accent)}
.news .src{display:block;font-size:14px;color:var(--muted);margin-top:2px}
.pc-grid{display:grid;grid-template-columns:minmax(240px,1fr) 1.3fr;gap:24px;align-items:center}
@media (max-width:640px){.pc-grid{grid-template-columns:1fr}}
.driver-cap{font-size:14px;color:var(--muted);margin-top:10px}
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
    news = fetch_news(nas["pts"][-1][0] + 6 * 3600 if nas else None)

    now = datetime.now(KST)
    weekday = "월화수목금토일"[now.weekday()]
    cards = "".join(card(q) for q in quotes)
    failed = [q["name"] for q in quotes if not q["ok"]]

    html = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{report_title(now)}</title><style>{CSS}</style></head><body><div class="wrap">
<div class="top"><div><h1>{report_title(now)}</h1>
<div class="sub">{now:%Y-%m-%d}({weekday}) {now:%H:%M} KST 기준 · 일봉 종가 기준 (장중이면 현재가)</div></div>
<div class="tools"><button id="bc"></button><button id="bt">라이트/다크</button></div></div>
{top_section(cnn, quotes, news)}
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
