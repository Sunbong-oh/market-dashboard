"""실적 속보 카드에 '실적 발표 후 주가 반응'(px)을 채운다. 노트북의 실적 감시(kb-market-report)가 꺼져 있어도 되도록 직접 조회.

카드 JSON 의 "sym" 에 [야후 심볼, 표시 이름] 목록을 적어 두면 (예 [["NFLX", "넷플릭스(미국)"]],
[["TSM", "TSMC(미국 ADR)"], ["2330.TW", "TSMC(대만)"]]) 각 종목을 Yahoo 차트로 조회해
  발표 전 정규장 종가 대비 지금 가격(애프터마켓·프리마켓·정규장) 변화(c)와,
  발표 뒤 첫 정규장이 끝났으면 그 종가 변화(d1)를 "px" 로 저장한다 (build_site.earn_px_html 이 그린다).

  python earnings_px.py earnings_flash/20261021-넷플릭스.json [...]
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
CUR = {"USD": "$", "EUR": "€", "TWD": "NT$", "JPY": "¥", "KRW": "₩", "GBP": "£", "HKD": "HK$"}
SESSION = {"pre": "프리마켓", "regular": "정규장", "post": "애프터마켓"}


def chart(sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           "?interval=5m&range=5d&includePrePost=true")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.loads(r.read())["chart"]["result"][0]


def reaction(sym, label, released):
    """released: 발표 시각(UTC epoch). 발표 전 마지막 정규장 종가를 기준으로 본다."""
    r = chart(sym)
    m = r["meta"]
    bars = [(t, c) for t, c in zip(r.get("timestamp") or [], r["indicators"]["quote"][0]["close"]) if c is not None]
    tp = m.get("tradingPeriods") or {}
    periods = {k: [x[0] for x in tp.get(k) or [] if x] for k in ("pre", "regular", "post")}
    closes = []          # (정규장 끝 시각, 그 정규장 마지막 가격)
    for p in periods["regular"]:
        inside = [c for t, c in bars if p["start"] <= t < p["end"]]
        if inside:
            closes.append((p["end"], inside[-1]))
    before = [c for end, c in closes if end <= released]
    if not before or not bars:
        return None
    ref = before[-1]
    t_last, p_last = bars[-1]
    if t_last <= released:
        return None      # 아직 발표 뒤 거래가 없다
    sess = next((SESSION[k] for k in ("pre", "regular", "post")
                 for p in periods[k] if p["start"] <= t_last < p["end"]), "")
    now = datetime.now(timezone.utc).timestamp()
    unit = CUR.get(m.get("currency") or "USD", "")
    row = {"l": label, "s": sess, "t": datetime.fromtimestamp(t_last, KST).strftime("%m/%d %H:%M"),
           "p": f"{unit}{p_last:,.2f}", "c": round((p_last / ref - 1) * 100, 2), "ref": "발표 전 종가"}
    first = [c for end, c in closes if released < end <= now]   # 발표 뒤 처음 끝난 정규장
    if first:
        row["d1"] = round((first[0] / ref - 1) * 100, 2)
    return row


def fill(path):
    card = json.loads(open(path, encoding="utf-8").read())
    if not card.get("sym"):
        print("sym 없음, 건너뜀:", path)
        return False
    released = datetime.fromisoformat(f'{card["day"]}T{card.get("time") or "00:00"}:00+09:00').timestamp()
    rows = []
    for sym, label in card["sym"]:
        try:
            row = reaction(sym, label, released)
        except Exception as e:
            print("주가 조회 실패:", sym, type(e).__name__, e, file=sys.stderr)
            row = None
        if row:
            rows.append(row)
    if not rows:
        print("주가 반응 없음(발표 뒤 거래 전):", path)
        return False
    card["px"] = rows
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(card, ensure_ascii=False, indent=2) + "\n")
    print(path, json.dumps(rows, ensure_ascii=False))
    return True


if __name__ == "__main__":
    for p in sys.argv[1:]:
        fill(p)
