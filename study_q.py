"""재무제표 공부 › 분기 실적: 종목별 분기·연간 매출액·영업이익·순이익 (네이버 증권, 억원).

study-q.yml 이 study-fin 브랜치의 index.json 종목마다 네이버 증권 finance/quarter·annual 을 받아
q/<종목코드>.json 으로 저장하고, site.yml 이 사이트의 /study/q/ 에 붙인다.
  {"u": 받은 날, "q": [[분기 끝 "YYYY.MM", 매출, 영업이익, 순이익, 컨센서스면 1], ...], "a": [... 연간 ...]}
  순이익은 지배주주순이익(없으면 당기순이익). 네이버 표의 마지막 칸은 보통 컨센서스(추정치)다.
그날 나온 잠정실적은 화면이 kb earnings-live 의 earnings.json kr_prelim 으로 바로 덧붙인다(이 파일은 하루 한 번).

  python study_q.py --data _fin            # _fin/index.json 의 모든 종목 → _fin/q/
  python study_q.py --data _fin 000660     # 한 종목만
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
URL = "https://m.stock.naver.com/api/stock/{code}/finance/{kind}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
      "Referer": "https://m.stock.naver.com/"}
ROWS = (("매출액",), ("영업이익",), ("지배주주순이익", "당기순이익"))


def _num(cell):
    v = str((cell or {}).get("value", "")).replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def table(code: str, kind: str) -> list[list]:
    """[[기간 'YYYY.MM', 매출, 영업이익, 순이익, 컨센서스 1/0], ...] 오래된 것부터."""
    with urllib.request.urlopen(urllib.request.Request(URL.format(code=code, kind=kind), headers=UA), timeout=15) as r:
        fi = json.loads(r.read()).get("financeInfo") or {}
    rows = {r.get("title"): r.get("columns") or {} for r in fi.get("rowList") or []}
    out = []
    for t in fi.get("trTitleList") or []:
        k = t.get("key", "")
        vals = []
        for names in ROWS:
            v = next((x for x in (_num(rows.get(n, {}).get(k)) for n in names) if x is not None), None)
            vals.append(v)
        if any(v is not None for v in vals):
            out.append([f"{k[:4]}.{k[4:6]}", *vals, 1 if t.get("isConsensus") == "Y" else 0])
    return out


def one(code: str) -> dict | None:
    try:
        q, a = table(code, "quarter"), table(code, "annual")
    except Exception:
        return None
    return {"u": datetime.now(KST).strftime("%Y-%m-%d"), "q": q, "a": a} if q or a else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="_fin")
    ap.add_argument("codes", nargs="*")
    args = ap.parse_args()
    root = Path(args.data)
    codes = args.codes or [c for c, *_ in json.loads((root / "index.json").read_text(encoding="utf-8"))["list"]]
    (root / "q").mkdir(parents=True, exist_ok=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for code, d in zip(codes, ex.map(one, codes)):
            if d:
                (root / "q" / f"{code}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                ok += 1
    print(f"분기 실적: {ok} / {len(codes)} 종목", file=sys.stderr)


if __name__ == "__main__":
    main()
