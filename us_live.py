"""미국 데일리 주요지표 실시간 시세 (us-live.yml).

미국 장 전후(한국 17:00 ~ 다음 날 09:05, 월~금 미국 거래일) 1분마다 야후 시세를 받아
us-live 브랜치의 quotes.json 으로 올린다. 데일리 페이지(US_LIVE_JS)가 이 파일을 읽어 카드의 가격·등락을 바꾼다.
한 번 실행은 최대 5시간 40분(Actions 6시간 제한) — 시간이 남으면 out/relay 를 남겨 워크플로가 다음 실행을 띄운다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard import INDEX_STRIP, ITEMS

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
MAX_RUN = timedelta(hours=5, minutes=40)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
      "Accept": "application/json"}
SYMS = list(dict.fromkeys([sym for _, sym, *_ in ITEMS if not sym.endswith("-USD")] + [sym for _, sym in INDEX_STRIP]))  # 비트코인은 바이낸스로 따로


def in_window(now: datetime) -> bool:
    hm = now.strftime("%H%M")
    return (hm >= "1700" and now.weekday() <= 4) or (hm <= "0905" and 1 <= now.weekday() <= 5)


def quote(sym: str) -> dict | None:
    """정규장 가격(p)·전일 종가(pc). 개별 종목은 장전·시간외 거래가 있으면 x(가격)·xs(세션)·xt(시각)도."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1d&interval=1m&includePrePost=true"
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read())["chart"]["result"][0]
        m = r["meta"]
        p, pc = m.get("regularMarketPrice"), m.get("chartPreviousClose") or m.get("previousClose")
        if p is None or not pc:
            return None
        out = {"p": p, "pc": pc, "t": m.get("regularMarketTime")}
        if not sym.startswith("^") and "=" not in sym:  # 지수·선물은 장전·시간외가 따로 없다
            pts = [(t, c) for t, c in zip(r.get("timestamp") or [], (r["indicators"]["quote"][0].get("close") or [])) if c is not None]
            ctp = m.get("currentTradingPeriod") or {}
            if pts and pts[-1][0] > (m.get("regularMarketTime") or 0):
                t, c = pts[-1]
                for key, name in (("pre", "프리마켓"), ("post", "애프터마켓")):
                    per = ctp.get(key) or {}
                    if per.get("start", 0) <= t < per.get("end", 0):
                        out.update(x=round(c, 4), xs=name, xt=datetime.fromtimestamp(t, KST).strftime("%H:%M"))
        return out
    except Exception as e:
        print("  시세 실패:", sym, type(e).__name__, e, flush=True)
        return None


def push(data: dict) -> None:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print(json.dumps(data, ensure_ascii=False)[:300])
        return
    with tempfile.TemporaryDirectory() as d:
        Path(d, "quotes.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        git = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, timeout=60)
        git("init", "-q", "-b", "us-live")
        git("add", "quotes.json")
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-q", "-m", f"미국 시세 {data['time']}")
        r = git("push", "-q", "-f", f"https://x-access-token:{token}@github.com/{repo}", "us-live")
        if r.returncode:
            print("  올리기 실패:", r.stderr.decode()[-200:], flush=True)


def main() -> None:
    start = datetime.now(KST)
    if not in_window(start):
        nxt = start.replace(hour=17, minute=0, second=0, microsecond=0)
        if timedelta(0) < nxt - start <= timedelta(minutes=40) and start.weekday() <= 4:
            print("17:00까지 대기", flush=True)
            time.sleep((nxt - start).total_seconds())
        else:
            print("시간 밖 → 종료", flush=True)
            return
    while True:
        now = datetime.now(KST)
        if not in_window(now):
            print("창 종료", flush=True)
            return
        if now - start >= MAX_RUN:
            (ROOT / "out").mkdir(exist_ok=True)
            (ROOT / "out" / "relay").write_text("1")
            print("다음 실행으로 넘김", flush=True)
            return
        data = {k: v for k, v in ((s, quote(s)) for s in SYMS) if v}
        if data:
            push({"time": now.strftime("%Y-%m-%d %H:%M"), "data": data})
            print(now.strftime("%H:%M"), len(data), "종목", flush=True)
        time.sleep(max(5, 60 - (datetime.now(KST) - now).total_seconds()))


if __name__ == "__main__":
    if "--once" in sys.argv:
        print(json.dumps({s: quote(s) for s in SYMS}, ensure_ascii=False))
    else:
        main()
