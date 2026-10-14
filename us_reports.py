"""해외주식 리포트 모음: 국내 증권사가 낸 미국 주식 리포트를 정리해 us_reports/YYYY-MM-DD.json 으로 저장한다.

데이터: 연합인포맥스 글로벌모니터 리포트 목록 (한국투자증권 '미국주식 리서치리포트' 메뉴가 보여 주는 목록과 같다)
  목록   POST https://globalmonitor.einfomax.co.kr/bizrpt/reportlist
  원문   https://rreport.einfomax.co.kr/report/<secureId>.pdf

실행: python us_reports.py [--date YYYY-MM-DD]
  -> 직전 평일부터 그날까지 발간된 리포트를 모아 us_reports/<날짜>.json, latest.json 저장
build_site.py 가 이 파일을 읽어 '해외주식' 메뉴로 보여 준다.
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path

import dashboard as d

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "us_reports"
LIST_URL = "https://globalmonitor.einfomax.co.kr/bizrpt/reportlist"
PDF_URL = "https://rreport.einfomax.co.kr/report/{}.pdf"
# 한국투자증권 화면의 '전체 리포트' 탭과 같은 분류 코드
SSC = "524910,521090,523050,523070"
# [뉴몬트 (NYS:NEM)] 처럼 제목 앞에 붙는 종목 표시
COMPANY_RE = re.compile(r"^\[(?P<name>[^\[\]]+?)\s*\((?P<ex>[A-Z]{2,4}):(?P<ticker>[A-Z0-9.\-]+)\)\]\s*(?P<rest>.*)$")
# 제목에 적힌 투자의견: '투자의견 매수 유지', '투자의견 매수 하향', '투자의견 적극 매수 유지'
OPINION_RE = re.compile(r"투자의견\s*(?P<op>적극\s*매수|매수|중립|비중\s*축소|매도|Buy|Hold|Sell)\s*(?P<chg>유지|상향|하향|신규)?", re.I)
KIND_RE = re.compile(r"\[(\d?Q\d{2}|\d{2}Q\d) (Preview|Review)\]|\[(Issue & News|Earnings Flash)\]", re.I)


def fetch_page(start, end, page, per=50):
    body = {"targetPeriodCheck": False, "page": page, "sortType": "latest", "lscCd": 700, "targetPeriodDate": None,
            "sscCd": SSC, "authSscCd": 0, "cmd": "rl_011", "startDate": start, "searchItem": "title", "endDate": end,
            "searchStr": "", "authLscCd": 0, "pagePerItem": per}
    req = urllib.request.Request(LIST_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json;charset=UTF-8", "User-Agent": d.UA,
        "Referer": "https://globalmonitor.einfomax.co.kr/ht_usa.html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("reportlist") or []


def fetch_all(start, end, max_pages=10):
    rows, seen = [], set()
    for page in range(1, max_pages + 1):
        got = fetch_page(start, end, page)
        new = [r for r in got if r.get("rptId") not in seen]
        if not new:
            break
        seen.update(r["rptId"] for r in new)
        rows += new
        if len(got) < 50:
            break
    return rows


def parse(r):
    title = unescape(r.get("title") or "").strip()
    m = COMPANY_RE.match(title)
    headline = unescape(r.get("summarytitle") or "").strip()
    if not headline or re.fullmatch(r"[\d.\s/-]+", headline):   # 데일리류는 요약 제목 칸에 날짜만 들어 있다
        headline = m.group("rest") if m else title
    headline = KIND_RE.sub("", headline).strip(" -")
    headline = OPINION_RE.sub("", headline).strip(" ,-·") or headline   # 의견은 따로 보여 준다
    bullets = [re.sub(r"^[-·•\s]+", "", unescape(re.sub(r"<[^>]+>", "", b))).strip()
               for b in re.split(r"<br\s*/?>", r.get("summaryHtml") or "", flags=re.I)]
    op = OPINION_RE.search(title)
    kind = KIND_RE.search(title)
    t = r.get("writeTime") or ""
    return {
        "date": (r.get("writeDate") or "").replace("/", "-"),
        "time": f"{t[:2]}:{t[2:4]}" if len(t) >= 4 else "",
        "broker": r.get("auth") or "",
        "writer": r.get("writer") or "",
        "company": m.group("name").strip() if m else "",
        "exchange": m.group("ex") if m else "",
        "ticker": m.group("ticker") if m else "",
        "title": title,
        "headline": headline,
        "summary": [b for b in bullets if b],
        "opinion": re.sub(r"\s+", " ", op.group("op")) if op else "",
        "opinion_change": (op.group("chg") or "") if op else "",
        "kind": next((g for g in (kind.groups() if kind else ()) if g and not re.match(r"^\d", g)), ""),
        "pages": int(r.get("pagecount") or 0),
        "pdf": PDF_URL.format(r["secureId"]) if r.get("secureId") else "",
        "id": r.get("rptId") or "",
    }


def prev_weekday(day):
    p = day - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def collect(day, now, latest):
    since = prev_weekday(day)
    rows = fetch_all(since.isoformat(), day.isoformat())
    items = [parse(r) for r in rows]
    items = [i for i in items if since.isoformat() <= i["date"] <= day.isoformat()]
    items.sort(key=lambda i: (i["date"], i["time"]), reverse=True)
    stocks = [i for i in items if i["ticker"]]
    doc = {"day": day.isoformat(), "since": since.isoformat(), "made": now.strftime("%Y-%m-%d %H:%M"),
           "n": len(items), "n_stocks": len(stocks), "items": items,
           "source": "연합인포맥스 글로벌모니터 (국내 증권사 미국주식 리포트)"}
    OUT.mkdir(exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    (OUT / f"{day.isoformat()}.json").write_text(text, encoding="utf-8")
    if latest:
        (OUT / "latest.json").write_text(text, encoding="utf-8")
    print(json.dumps({"day": doc["day"], "since": doc["since"], "reports": doc["n"], "stock_reports": doc["n_stocks"]},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="정리할 날짜 (YYYY-MM-DD, 비우면 오늘)")
    ap.add_argument("--days", type=int, default=1, help="그날부터 거슬러 올라가며 정리할 평일 수 (지난 리포트 목록용)")
    args = ap.parse_args()
    now = datetime.now(d.KST)
    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else now.date()
    if day.weekday() >= 5:          # 주말에 돌리면 직전 금요일분
        day = prev_weekday(day)
    for n in range(max(args.days, 1)):
        try:
            collect(day, now, latest=n == 0)
        except Exception as e:      # 하루치가 실패해도 나머지 날짜는 계속
            print(f"{day}: {e}", file=sys.stderr)
        day = prev_weekday(day)


if __name__ == "__main__":
    sys.exit(main())
