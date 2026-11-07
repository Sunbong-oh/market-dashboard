"""위험신호 › 실적 둔화 규칙 과거 검증 (GitHub Actions risk-bt.yml 에서만 돈다: DART 키가 거기 있음).

규칙: 실적이 폭증하던 종목(직전 분기 매출 전분기 대비 +15%↑ 또는 전년 대비 +50%↑)의
      이번 분기 매출 성장률(전분기 대비)이 직전 분기보다 5%p 넘게 낮으면 → 이번 분기 실적 발표 전에 정리.
과거 컨센서스가 없어 '실제' 성장률을 미리 안다고 가정한다(완벽한 예상 = 규칙이 낼 수 있는 가장 좋은 성적).

자료: DART fnlttMultiAcnt(분기 매출, 연결 우선) · DART list(잠정실적 공정공시·정기보고서 접수일 = 발표일) · 네이버 일봉.
대상: 하이닉스·삼성 + 반도체 소부장(risk_page) + 시가총액 상위 200(kb flow-live map.json).
결과: risk-bt 브랜치 result.json (사건 목록·요약).
  python risk_earn_bt.py --out _bt
"""
import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import risk_page as rp
from study_fin import Dart, Budget, KST, _num

YEARS = range(2015, datetime.now(KST).year + 1)
RC = (("11013", 3), ("11012", 6), ("11014", 9), ("11011", 12))
REV = ("매출액", "수익(매출액)", "영업수익", "매출", "매출액(수익)")
SELL_BEFORE = 5         # 발표 5거래일 전 종가에 판다고 본다
HZ = (20, 60)           # 판 뒤 20·60거래일 성적
BOOM_QOQ, BOOM_YOY, SLOW_PT = rp.BOOM_QOQ, rp.BOOM_YOY, rp.SLOW_PT


def universe():
    mem = rp.members()
    names = dict(rp.LEADERS)
    names.update(mem)
    semi = set(names)
    j, c = rp._get(rp.MAP_URL), rp._get(rp.CODES_URL)
    try:
        codes = {r[1]: r[0] for r in c["list"]}
        rows = [s for secs in j["data"].values() for sec in secs for s in sec["st"]]
        rows.sort(key=lambda s: -(s.get("c") or s.get("v") or 0))   # 시가총액(없으면 거래대금) 큰 순
        for s in rows:
            n = s["n"]
            if len(names) >= len(semi) + 200:
                break
            if n in codes and not n.endswith("우") and not re.search(r"스팩|리츠|ETF|ETN", n):
                names.setdefault(codes[n], n)
    except (TypeError, KeyError):
        pass
    return names, semi


def corp_codes(dart):
    raw = dart.get("corpCode.xml")
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read(z.namelist()[0]).decode("utf-8")
    out = {}
    for blk in re.findall(r"<list>(.*?)</list>", xml, re.S):
        sc = re.search(r"<stock_code>\s*(\d{6})\s*</stock_code>", blk)
        cc = re.search(r"<corp_code>(\d+)</corp_code>", blk)
        if sc and cc:
            out[sc.group(1)] = cc.group(1)
    return out


def revenues(dart, corps):
    """{corp: {(year, months): (누적 또는 당기 금액, fs)}} — 연결(CFS) 우선."""
    got = {}
    cl = list(corps)
    for y in YEARS:
        for rc, months in RC:
            for i in range(0, len(cl), 100):
                j = dart.get("fnlttMultiAcnt.json", corp_code=",".join(cl[i:i + 100]), bsns_year=y, reprt_code=rc) or {}
                for r in j.get("list") or []:
                    if r.get("sj_div") not in ("IS", "CIS") or re.sub(r"\s", "", r.get("account_nm", "")) not in REV:
                        continue
                    cum = _num(r.get("thstrm_add_amount"))
                    cur = _num(r.get("thstrm_amount"))
                    v = cum if (months in (6, 9) and cum is not None) else cur
                    if v is None:
                        continue
                    k = (y, months)
                    d = got.setdefault(r["corp_code"], {})
                    if k not in d or (d[k][1] == "OFS" and r.get("fs_div") == "CFS"):
                        d[k] = (v, r.get("fs_div"), cur, months in (6, 9) and cum is not None)
    return got


def quarterly(d):
    """{(y, q): 매출} 3개월 금액. 반기·3분기는 누적에서 빼고, 4분기 = 연간 - 3분기 누적. 연결/별도가 섞이면 그 분기는 버린다."""
    out = {}
    for y in YEARS:
        prev, prev_fs = None, None   # 직전 보고서의 누적 금액(누적을 모르면 None)
        for q, months in enumerate((3, 6, 9, 12), 1):
            x = d.get((y, months))
            if not x:
                prev = None
                continue
            v, fs, cur, is_cum = x
            if months == 3:
                out[(y, 1)] = v
            elif months in (6, 9) and not is_cum:
                out[(y, q)] = v          # 누적이 없으면 당기(3개월) 금액 그대로, 다음 분기 빼기는 못 함
                prev = None
                continue
            elif prev is not None and fs == prev_fs:
                out[(y, q)] = v - prev
            elif months in (6, 9) and cur is not None:
                out[(y, q)] = cur
            prev, prev_fs = v, fs
    return out


def ann_dates(dart, corp):
    """{(y, q): 'YYYYMMDD'} 가장 이른 발표일(잠정실적 공정공시 또는 정기보고서 접수일)."""
    out = {}

    def put(k, d):
        if k not in out or d < out[k]:
            out[k] = d

    for ty in ("A", "I"):
        page = 1
        while page <= 10:
            j = dart.get("list.json", corp_code=corp, bgn_de="20150101", end_de=datetime.now(KST).strftime("%Y%m%d"),
                         page_no=page, page_count=100,
                         **({"pblntf_ty": "A"} if ty == "A" else {"pblntf_detail_ty": "I002"})) or {}
            for r in j.get("list") or []:
                nm, d = r.get("report_nm", ""), r.get("rcept_dt", "")
                if "정정" in nm or "취소" in nm:
                    continue
                m = re.search(r"(분기|반기|사업)보고서\s*\((\d{4})\.(\d{2})\)", nm)
                if ty == "A" and m:
                    put((int(m.group(2)), int(m.group(3)) // 3), d)
                elif ty == "I" and "잠정" in nm and "실적" in nm and d:
                    y, mo = int(d[:4]), int(d[4:6])
                    q = (mo - 1) // 3          # 발표 달의 직전 분기
                    k = (y - 1, 4) if q == 0 else (y, q)
                    put(k, d)
            if page >= int(j.get("total_page") or 1):
                break
            page += 1
    return out


def closes(code):
    return [(d, c) for d, _, c in rp._bars(code)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_bt")
    ap.add_argument("--budget", type=int, default=4000)
    a = ap.parse_args()
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise SystemExit("DART_API_KEY 없음")
    os.makedirs(a.out, exist_ok=True)
    dart = Dart(key, a.budget)
    log = {"start": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    names, semi = universe()
    cc = corp_codes(dart)
    names = {k: v for k, v in names.items() if k in cc}
    log["stocks"], log["semi"] = len(names), len(semi & set(names))
    print("대상", len(names), "종목")
    rev = revenues(dart, [cc[k] for k in names])
    log["rev_calls"] = dart.calls
    with ThreadPoolExecutor(max_workers=4) as ex:
        dates = dict(zip(names, ex.map(lambda k: ann_dates(dart, cc[k]), names)))
    log["calls"] = dart.calls
    with ThreadPoolExecutor(max_workers=8) as ex:
        px = dict(zip(list(names) + ["KOSPI"], ex.map(closes, list(names) + ["KOSPI"])))
    kmap = {d: c for d, c in px["KOSPI"]}
    events = []
    for code, name in names.items():
        q = quarterly(rev.get(cc[code], {}))
        ser = px.get(code) or []
        if not q or len(ser) < 200:
            continue
        idx = {d: i for i, (d, _) in enumerate(ser)}
        ds = [d for d, _ in ser]
        for (y, qq), v in sorted(q.items()):
            pk = (y - 1, 4) if qq == 1 else (y, qq - 1)
            ppk = (pk[0] - 1, 4) if pk[1] == 1 else (pk[0], pk[1] - 1)
            if pk not in q or ppk not in q or (y - 1, qq) not in q or (pk[0] - 1, pk[1]) not in q:
                continue
            g = lambda a, b: a / b - 1 if b and b > 0 and a is not None else None
            gq, gp, yp = g(v, q[pk]), g(q[pk], q[ppk]), g(q[pk], q[(pk[0] - 1, pk[1])])
            gy = g(v, q[(y - 1, qq)])
            D = dates[code].get((y, qq))
            if None in (gq, gp) or not D:
                continue
            i = next((k for k, d in enumerate(ds) if d >= D), None)
            if i is None or i - SELL_BEFORE - 60 < 0:
                continue
            s = i - SELL_BEFORE
            boom = gp >= BOOM_QOQ or (yp is not None and yp >= BOOM_YOY)
            slow = gq <= gp - SLOW_PT
            e = {"code": code, "n": name, "semi": code in semi, "q": f"{y}Q{qq}", "D": D, "sell": ds[s],
                 "gq": round(gq, 4), "gp": round(gp, 4), "yp": None if yp is None else round(yp, 4), "gy": None if gy is None else round(gy, 4),
                 "boom": boom, "slow": slow, "pre60": round(ser[s][1] / ser[s - 60][1] - 1, 4)}
            for h in HZ:
                if s + h < len(ser):
                    r = ser[s + h][1] / ser[s][1] - 1
                    k0, k1 = kmap.get(ds[s]), kmap.get(ds[s + h])
                    e[f"r{h}"] = round(r, 4)
                    e[f"x{h}"] = round(r - (k1 / k0 - 1), 4) if k0 and k1 else None
            if s + 60 < len(ser):
                e["mdd60"] = round(min(c for _, c in ser[s + 1:s + 61]) / ser[s][1] - 1, 4)
            events.append(e)

    def summ(evs):
        out = {"n": len(evs)}
        for k in ("r20", "x20", "r60", "x60", "mdd60", "pre60"):
            v = sorted(e[k] for e in evs if e.get(k) is not None)
            if v:
                out[k] = {"mean": round(sum(v) / len(v), 4), "med": round(v[len(v) // 2], 4), "neg": round(sum(x < 0 for x in v) / len(v), 3)}
        return out

    groups = {}
    for scope, f in (("all", lambda e: True), ("semi", lambda e: e["semi"])):
        sel = [e for e in events if f(e)]
        groups[scope] = {"rule(폭증+둔화)": summ([e for e in sel if e["boom"] and e["slow"]]),
                         "폭증+유지·가속": summ([e for e in sel if e["boom"] and not e["slow"]]),
                         "둔화(폭증 아님)": summ([e for e in sel if not e["boom"] and e["slow"]]),
                         "전체": summ(sel)}
    log["events"] = len(events)
    log["end"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    json.dump({"log": log, "groups": groups, "events": events}, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(json.dumps({"log": log, "groups": groups}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Budget:
        print("DART 한도", file=sys.stderr)
