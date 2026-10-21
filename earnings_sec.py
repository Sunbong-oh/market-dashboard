"""관심 종목의 실적 공시(SEC 8-K Item 2.02, 해외 상장사는 6-K)를 최근 N시간 안에 낸 회사를 찾는다.

증시 캘린더 날짜가 틀려도(예: 메타 10/29로 적혔지만 실제 10/21 발표) 놓치지 않도록, 매시간 실적 속보 점검이 먼저 돌린다.
  python earnings_sec.py [--hours 30]
출력: 한 줄에 하나씩 "티커 회사명 접수시각(KST) 양식 링크". 없으면 아무것도 출력하지 않는다.
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "market-dashboard research sunbong5302@gmail.com", "Accept-Encoding": "identity"}
# 반도체·빅테크·관심 종목 (티커 → 한글 이름). 해외 상장사는 6-K 로 실적을 낸다.
WATCH = {
    "NVDA": "엔비디아", "AVGO": "브로드컴", "AMD": "AMD", "INTC": "인텔", "QCOM": "퀄컴", "MU": "마이크론",
    "LRCX": "램리서치", "AMAT": "어플라이드머티리얼즈", "KLAC": "KLA", "TXN": "텍사스인스트루먼트", "ARM": "ARM",
    "SNDK": "샌디스크", "WDC": "웨스턴디지털", "SMCI": "슈퍼마이크로", "MRVL": "마벨", "STX": "씨게이트",
    "TSLA": "테슬라", "GOOGL": "알파벳", "MSFT": "마이크로소프트", "META": "메타", "AAPL": "애플", "AMZN": "아마존",
    "NFLX": "넷플릭스", "ORCL": "오라클", "PLTR": "팔란티어", "SPCX": "스페이스X", "VRT": "버티브",
    "ASML": "ASML", "TSM": "TSMC",
}
FOREIGN = {"ASML", "TSM", "ARM"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.loads(r.read())


def recent(hours=30, foreign=True):
    """최근 hours 시간 안의 실적 공시 [{sym, name, acc(UTC datetime), form, url}] — 새것부터."""
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    tickers = {v["ticker"]: v["cik_str"] for v in get("https://www.sec.gov/files/company_tickers.json").values()}
    out = []
    for sym, name in WATCH.items():
        cik = tickers.get(sym)
        if not cik:
            print("CIK 없음:", sym, file=sys.stderr)
            continue
        try:
            rec = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
        except Exception as e:
            print("조회 실패:", sym, type(e).__name__, file=sys.stderr)
            continue
        time.sleep(0.12)   # SEC 초당 10건 제한
        for i, form in enumerate(rec["form"]):
            acc = datetime.fromisoformat(rec["acceptanceDateTime"][i].replace("Z", "+00:00"))
            if acc < cut:
                break
            items = rec.get("items", [""] * len(rec["form"]))[i] or ""
            if (form == "8-K" and "2.02" in items) or (foreign and form == "6-K" and sym in FOREIGN):
                url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{rec['accessionNumber'][i].replace('-', '')}/"
                       f"{rec['primaryDocument'][i]}")
                out.append({"sym": sym, "name": name, "acc": acc, "form": form, "url": url})
    return sorted(out, key=lambda x: x["acc"], reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=30)
    a = ap.parse_args()
    for r in recent(a.hours):
        print(r["sym"], r["name"], r["acc"].astimezone(KST).strftime("%Y-%m-%d %H:%M"), r["form"], r["url"])


if __name__ == "__main__":
    sys.exit(main())
