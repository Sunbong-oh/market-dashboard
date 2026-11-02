"""매시간 실적 속보 점검의 '문지기'. Claude 가 웹 검색·카드 작성을 시작하기 전에, 할 일이 있는지 코드로 먼저 본다.

할 일이 없으면 NO_WORK 한 줄만 출력한다. 그러면 점검 작업은 바로 '·' 를 남기고 끝낸다(토큰 절약).
할 일이 있으면 한 줄에 하나씩 적는다:
  NEW  <티커> <회사명> <접수시각 KST> <양식> <링크>   SEC 실적 공시가 나왔는데 카드가 없음
  LIVE <key> <회사명>                                  earnings.json(해외) 항목인데 카드가 없음
  CAL  <날짜> <회사명>                                 캘린더 ★ 일정(앞뒤 하루)인데 SEC 로 감지할 수 없는 회사 → 웹 검색으로 확인
  CALL <카드 경로>                                     '컨퍼런스콜 … 후 업데이트' 가 남아 있고 콜이 끝났을 시각
  D1   <카드 경로>                                     발표 뒤 첫 정규장이 끝났는데 px 에 d1 이 없음

  python earnings_gate.py [--hours 30]
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import earnings_sec

KST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json"
CAL_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/main/calendar/{}.json"


def fetch_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "market-dashboard"}),
                                    timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print("조회 실패:", url, type(e).__name__, file=sys.stderr)
        return None


def load_cards():
    cards = {}
    for p in sorted(glob.glob(os.path.join(HERE, "earnings_flash", "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                cards[os.path.relpath(p, HERE)] = json.load(f)
        except Exception as e:
            print("카드 읽기 실패:", p, type(e).__name__, file=sys.stderr)
    return cards


def has_card(cards, name, day, slack=2):
    """회사 이름이 같은 카드가 day(date) 앞뒤 slack 일 안에 있으면 True."""
    for path, c in cards.items():
        m = re.match(r"(\d{8})-(.+)\.json$", os.path.basename(path))
        if not m:
            continue
        cday = datetime.strptime(m.group(1), "%Y%m%d").date()
        if (name == m.group(2) or name == c.get("company")) and abs((cday - day).days) <= slack:
            return True
    return False


def announced(c):
    try:
        return datetime.strptime(f"{c['day']} {c.get('time') or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except Exception:
        return None


def first_close_after(t):
    """발표 시각 t 뒤 첫 미국 정규장 마감 시각(KST, 넉넉히 06:10 으로 본다; 미국 휴일은 무시)."""
    d = t.date()
    for _ in range(8):
        close = datetime(d.year, d.month, d.day, 6, 10, tzinfo=KST)
        us_day = (close - timedelta(days=1)).weekday()   # 그 마감의 미국 날짜 요일
        if close > t and us_day < 5:
            return close
        d += timedelta(days=1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=30)
    a = ap.parse_args()
    now = datetime.now(KST)
    cards = load_cards()
    work = []

    # (a) SEC 실적 공시
    sec_names = set(earnings_sec.WATCH.values())
    for r in earnings_sec.recent(a.hours):
        acc = r["acc"].astimezone(KST)
        if not has_card(cards, r["name"], acc.date()):
            work.append(f"NEW {r['sym']} {r['name']} {acc:%Y-%m-%d %H:%M} {r['form']} {r['url']}")

    # (b) earnings.json 의 해외 항목 (한국 종목은 kb-market-report 가 따로 처리)
    live = fetch_json(LIVE_URL) or {}
    keys = {os.path.splitext(os.path.basename(p))[0] for p in cards}
    for it in live.get("items", []):
        if it.get("kr") or it.get("key", "").startswith("KR-"):
            continue
        if it.get("key") not in keys:
            work.append(f"LIVE {it.get('key')} {it.get('name')}")

    # (c) 캘린더 ★ 일정 (앞뒤 하루). SEC 로 감지되는 회사는 (a) 가 잡으므로 뺀다.
    days = [(now + timedelta(days=k)).date() for k in (-1, 0, 1)]
    cal = {}
    for ym in sorted({d.strftime("%Y-%m") for d in days}):
        cal.update((fetch_json(CAL_URL.format(ym)) or {}).get("days", {}))
    for d in days:
        for name in cal.get(d.isoformat(), {}).get("earnings_us", []):
            if not name.startswith("★"):
                continue
            name = re.sub(r"\(.*?\)", "", name.lstrip("★")).strip()
            if name in sec_names or has_card(cards, name, d):
                continue
            work.append(f"CAL {d.isoformat()} {name}")

    # (d) 기존 카드 갱신: 콜 후 가이던스, 첫 정규장 종가(d1)
    for path, c in cards.items():
        t = announced(c)
        if not t or now - t > timedelta(days=5):
            continue
        g = " ".join(c.get("guidance") or [])
        if "후 업데이트" in g:
            m = re.search(r"(\d{1,2}):(\d{2})\s*한국시간", g)
            due = t + timedelta(hours=3)
            if m:
                call = t.replace(hour=int(m.group(1)), minute=int(m.group(2)))
                if call < t - timedelta(hours=1):
                    call += timedelta(days=1)
                due = call + timedelta(minutes=90)
            if now >= due:
                work.append(f"CALL {path}")
        px = c.get("px") or []
        close = first_close_after(t)
        if c.get("sym") and close and now >= close and (not px or any(p.get("d1") is None for p in px)):
            work.append(f"D1 {path}")

    print("\n".join(work) if work else "NO_WORK")


if __name__ == "__main__":
    sys.exit(main())
