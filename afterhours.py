"""미국 증시 시간외(애프터마켓·프리마켓) 급등락 알림 → 텔레그램.

- 대상: 시가총액 $100억 이상 미국 상장 종목(나스닥 스크리너, newhighs.universe) + 빅테크
- 기준: 정규장 종가 대비 ±5% 이상 (빅테크는 ±3% 이상). 같은 세션에서 처음 넘을 때 한 번 알리고,
  그 뒤 3%p 더 움직이거나 방향이 바뀌면 다시 알린다. 잘못 찍힌 체결 한 건에 속지 않도록 최근 5분봉 두 개가 모두 넘어야 한다.
- 원인: 종목별 야후 뉴스 중 최근 24시간 기사 제목 2개를 한국어로 옮겨 붙인다.
- 주기: 애프터마켓(16:00~20:00 미국 동부)은 한국시간 08시 전까지 5분마다, 그 뒤엔 정시마다.
        프리마켓(04:00~09:30 미국 동부)은 정시마다.
  afterhours.yml 이 세션 시작 직전에 실행하면 세션이 끝날 때까지 돌다가 끝난다.

  python afterhours.py            # 지금(또는 90분 안에 시작하는) 세션을 끝까지 감시
  python afterhours.py --once     # 한 번만 확인 (--dry 면 보내지 않고 출력)
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import dashboard as d
import newhighs

ET = ZoneInfo("America/New_York")
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
TH, TH_BIG, STEP = 5.0, 3.0, 3.0
BIGTECH = {"AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아", "GOOGL": "알파벳", "AMZN": "아마존",
           "META": "메타", "TSLA": "테슬라", "AVGO": "브로드컴", "NFLX": "넷플릭스", "ORCL": "오라클", "AMD": "AMD",
           "PLTR": "팔란티어", "TSM": "TSMC", "SPCX": "스페이스X"}
WINDOWS = {"post": ((16, 0), (20, 0), "애프터마켓"), "pre": ((4, 0), (9, 30), "프리마켓")}


def window_at(now_et):
    """now(ET)가 속하거나 90분 안에 시작하는 세션 (이름, 시작, 끝). 주말·해당 없음은 None."""
    for name, ((h1, m1), (h2, m2), _) in WINDOWS.items():
        start = now_et.replace(hour=h1, minute=m1, second=0, microsecond=0)
        end = now_et.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if start.weekday() < 5 and start - timedelta(minutes=90) <= now_et < end:
            return name, start, end
    return None


def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read())


def spark(syms):
    """{심볼: (최근 5분봉 가격 2개, 마지막 봉 시각, 정규장 종가)} — 시간외 포함 5분봉."""
    url = ("https://query1.finance.yahoo.com/v7/finance/spark?symbols=" + ",".join(syms)
           + "&range=1d&interval=5m&includePrePost=true")
    out = {}
    for _ in range(3):
        try:
            res = get(url)["spark"]["result"]
            break
        except Exception:
            time.sleep(2)
    else:
        return out
    for r in res:
        try:
            x = r["response"][0]
            bars = [(t, c) for t, c in zip(x["timestamp"], x["indicators"]["quote"][0]["close"]) if c]
            out[r["symbol"]] = ([c for _, c in bars[-2:]], bars[-1][0], x["meta"]["regularMarketPrice"])
        except (KeyError, IndexError, TypeError):
            continue
    return out


def quotes(syms):
    chunks = [syms[i:i + 20] for i in range(0, len(syms), 20)]
    out = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for part in ex.map(spark, chunks):
            out.update(part)
    return out


def ko(text):
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q=" + urllib.parse.quote(text)
        return "".join(s[0] for s in get(url, 10)[0] if s and s[0]) or text
    except Exception:
        return text


def news(sym):
    """최근 24시간 이 종목 관련 기사 제목 2개 (한국어, 출처)."""
    try:
        items = get(f"https://query1.finance.yahoo.com/v1/finance/search?q={sym}&newsCount=8&quotesCount=0").get("news") or []
    except Exception:
        return []
    cut = time.time() - 86400
    hits = [n for n in items if n.get("providerPublishTime", 0) >= cut and sym in (n.get("relatedTickers") or [])]
    hits.sort(key=lambda n: len(n.get("relatedTickers") or []) > 3)   # 시장 전체 기사보다 이 종목 기사 먼저
    return [f"{ko(n['title'])} ({n.get('publisher', '')})" for n in hits[:2]]


class Watch:
    def __init__(self, dry=False):
        self.dry = dry
        self.alerted = {}                      # 심볼 -> 마지막으로 알린 등락률
        uni = newhighs.universe()
        self.names = {s: newhighs.short_name(s, n) for s, n, _ in uni}
        self.caps = {s: c for s, _, c in uni}
        self.syms = list(dict.fromkeys(list(BIGTECH) + [s for s, _, _ in uni]))

    def due(self, sym, pct):
        th = TH_BIG if sym in BIGTECH else TH
        last = self.alerted.get(sym)
        if abs(pct) < th:
            return False
        return last is None or (pct > 0) != (last > 0) or abs(pct) >= abs(last) + STEP

    def check(self, name, start):
        label = WINDOWS[name][2]
        hits = []
        for sym, (last2, t, close) in quotes(self.syms).items():
            if t < start.timestamp() or not close:
                continue                       # 이번 세션 체결이 아직 없다
            pcts = [(p / close - 1) * 100 for p in last2]
            pct = pcts[-1]
            th = TH_BIG if sym in BIGTECH else TH
            if all(abs(x) >= th and (x > 0) == (pct > 0) for x in pcts) and self.due(sym, pct):
                hits.append((sym, pct, last2[-1], t))
        if not hits:
            return 0
        hits.sort(key=lambda h: (h[0] not in BIGTECH, -abs(h[1])))
        now = datetime.now(KST)
        lines = [f"🌙 미국 {label} 급등락 · {now:%m/%d %H:%M} (한국시간)", ""]
        reasons = dict(zip([h[0] for h in hits], ThreadPoolExecutor(max_workers=4).map(news, [h[0] for h in hits])))
        for sym, pct, px, t in hits:
            nm = BIGTECH.get(sym) or self.names.get(sym, sym)
            cap = self.caps.get(sym)
            again = " (추가 변동)" if sym in self.alerted else ""
            lines.append(f"{'🔺' if pct > 0 else '🔻'} {nm}({sym}) {pct:+.1f}% ${px:,.2f}"
                         + (f" · 시총 ${cap / 1e9:,.0f}B" if cap else "") + again)
            lines += [f"   └ {r}" for r in reasons.get(sym) or ["관련 뉴스 아직 없음"]]
            self.alerted[sym] = pct
        lines += ["", f"정규장 종가 대비 · 빅테크 ±{TH_BIG:.0f}%, 그 외 시총 $100억↑ ±{TH:.0f}%"]
        text = "\n".join(lines)
        if self.dry:
            print(text)
        else:
            d.send_telegram(text[:4000])
        return len(hits)


def next_check(name, now_et, end):
    """애프터마켓은 한국시간 08시 전까지 5분 간격, 그 외엔 한국시간 정시. 세션 끝 직전(5분 전)에 마지막 확인."""
    now_k = now_et.astimezone(KST)
    if name == "post" and now_k.hour < 8:
        nxt = now_et + timedelta(minutes=5)
        cut = now_k.replace(hour=8, minute=0, second=0, microsecond=0).astimezone(ET)
        nxt = min(nxt, cut) if cut > now_et else nxt
    else:
        nxt = (now_k.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).astimezone(ET)
    last = end - timedelta(minutes=5)
    if now_et < last < nxt:
        return last
    return nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--window", choices=list(WINDOWS), help="--once 확인용: 세션 지정")
    a = ap.parse_args()
    now = datetime.now(ET)
    if a.once:
        name = a.window or (window_at(now) or ("post", None, None))[0]
        (h1, m1) = WINDOWS[name][0]
        start = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        if start > now:
            start -= timedelta(days=1)
        w = Watch(a.dry)
        print("감시 종목", len(w.syms), "알림", w.check(name, start))
        return 0
    win = window_at(now)
    if not win:
        print("지금은 시간외 세션이 아니다:", now.strftime("%Y-%m-%d %H:%M ET"))
        return 0
    name, start, end = win
    if now < start:
        print("세션 시작까지 대기:", start.strftime("%H:%M ET"))
        time.sleep((start - now).total_seconds() + 300)   # 첫 5분봉이 생긴 뒤
    w = Watch(a.dry)
    try:
        import earnings_quick
        q = earnings_quick.Quick(a.dry)    # 빅테크·반도체 실적 공시 1차 속보 (5분마다)
    except Exception as e:
        print("실적 1차 속보 준비 실패:", type(e).__name__, e, file=sys.stderr)
        q = None
    print(f"{WINDOWS[name][2]} 감시 시작: {len(w.syms)}종목, {start:%H:%M}~{end:%H:%M} ET", flush=True)
    nxt = datetime.now(ET)
    while True:
        now = datetime.now(ET)
        if now >= end:
            break
        if now >= nxt:
            try:
                n = w.check(name, start)
                print(f"{now.astimezone(KST):%H:%M} KST 확인 · 알림 {n}종목", flush=True)
            except Exception as e:
                print("확인 실패:", type(e).__name__, e, file=sys.stderr, flush=True)
            nxt = next_check(name, datetime.now(ET), end)
        if q:
            try:
                k = q.check()
                if k:
                    print(f"{now.astimezone(KST):%H:%M} KST 실적 공시 {k}건 속보", flush=True)
            except Exception as e:
                print("실적 공시 확인 실패:", type(e).__name__, e, file=sys.stderr, flush=True)
        wake = min(nxt, datetime.now(ET) + timedelta(minutes=5), end)   # 실적 공시는 5분마다
        if wake >= end:
            break
        time.sleep(max(30, (wake - datetime.now(ET)).total_seconds()))
    print("세션 종료", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
