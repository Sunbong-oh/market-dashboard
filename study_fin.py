"""재무제표 공부 · 5분 체크 자동 입력용 재무 데이터 (OpenDART).

실행: DART_API_KEY=... python study_fin.py --data <폴더> [--budget 6000]
  - study-fin.yml 이 매일 밤 돌리고, 결과 폴더를 study-fin 브랜치에 저장한다.
  - site.yml 이 그 브랜치를 사이트의 /study/fin/ 에 붙인다 → 5분 체크에서 종목명을 넣으면 불러온다.

만드는 파일
  index.json        [[종목코드, 회사명, 시장]]  상장사 전체 (시장은 한 번 조회한 회사만)
  fin/<종목코드>.json 가장 최근 정기보고서(분기·반기·사업)의 누적 실적과 전년 같은 기간, 감사의견, 최근 2년 자금조달
  state.json        진행 상황 (다음 실행에서 이어서)

DART 하루 호출 한도(키 하나당 2만 회)를 다른 작업과 나눠 쓰므로 한 번에 --budget 회까지만 부른다.
처음엔 며칠에 걸쳐 전체를 채우고, 그 뒤로는 새 정기보고서를 낸 회사와 오래된 회사만 다시 받는다.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

API = "https://opendart.fss.or.kr/api/"
KST = timezone(timedelta(hours=9))
REPRT = {"11013": ("1분기", 3), "11012": ("반기", 6), "11014": ("3분기", 9), "11011": ("사업", 12)}
MKT = {"Y": "코스피", "K": "코스닥", "N": "코넥스"}
RAISE_RE = re.compile(r"유상증자결정|전환사채권발행결정|신주인수권부사채권발행결정|교환사채권발행결정")


class Budget(Exception):
    pass


class Dart:
    def __init__(self, key, budget):
        self.key, self.left, self.calls = key, budget, 0

    def get(self, name, **params):
        if self.left <= 0:
            raise Budget()
        self.left -= 1
        self.calls += 1
        url = API + name + "?" + urllib.parse.urlencode({"crtfc_key": self.key, **params})
        for i in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    raw = r.read()
                break
            except Exception as e:
                if i == 2:
                    print(f"  {name} 실패: {e}", file=sys.stderr)
                    return None
                time.sleep(2 + i * 3)
        time.sleep(0.12)  # 초당 8회 이하
        if name.endswith(".xml"):
            return raw
        try:
            j = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if j.get("status") == "020":  # 요청 제한 초과 → 오늘은 그만
            print("DART 호출 한도 초과(020). 오늘은 여기까지.", file=sys.stderr)
            raise Budget()
        if j.get("status") in ("010", "011", "012", "901"):
            raise SystemExit(f"DART 키 오류: {j.get('status')} {j.get('message')}")
        return j


# ---------- 계정 찾기 ----------
def _norm(s):
    return re.sub(r"[\s·ㆍ\(\)\[\]]", "", s or "")


def _num(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find(rows, sj, ids=(), names=()):
    """sj(재무제표 구분) 안에서 account_id 먼저, 없으면 계정명(정확히 같은 이름)으로 첫 줄을 찾는다."""
    cand = [r for r in rows if r.get("sj_div") in sj]
    for i in ids:
        for r in cand:
            if r.get("account_id") == i:
                return r
    nn = [_norm(n) for n in names]
    for n in nn:
        for r in cand:
            if _norm(r.get("account_nm")) == n:
                return r
    return None


def amt(r, cum):
    """cum=True 면 누적(분기·반기 손익은 thstrm_add_amount), 아니면 당기 금액."""
    if not r:
        return None
    if cum:
        v = _num(r.get("thstrm_add_amount"))
        if v is not None:
            return v
    return _num(r.get("thstrm_amount"))


def amt_prev(r, cum):
    if not r:
        return None
    if cum:
        v = _num(r.get("frmtrm_add_amount"))
        if v is not None:
            return v
    return _num(r.get("frmtrm_amount"))


IS = ("IS", "CIS")
ACC = {
    "rev": (IS, ("ifrs-full_Revenue",), ("매출액", "수익(매출액)", "매출", "영업수익", "매출및지분법손익")),
    "op": (IS, ("dart_OperatingIncomeLoss",), ("영업이익", "영업이익(손실)", "영업손익", "영업손실")),
    "ebt": (IS, ("ifrs-full_ProfitLossBeforeTax",), ("법인세비용차감전순이익", "법인세비용차감전순이익(손실)",
                                                       "법인세비용차감전순손익", "법인세차감전순이익", "법인세비용차감전계속사업이익")),
    "ni_parent": (IS, ("ifrs-full_ProfitLossAttributableToOwnersOfParent",), ("지배기업의소유주에게귀속되는당기순이익", "지배기업소유주지분")),
    "ni": (IS, ("ifrs-full_ProfitLoss",), ("당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익", "분기순이익(손실)", "반기순이익(손실)")),
    "cf": (("CF",), ("ifrs-full_CashFlowsFromUsedInOperatingActivities",), ("영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동순현금흐름")),
    "ar": (("BS",), ("ifrs-full_TradeAndOtherCurrentReceivables", "ifrs-full_CurrentTradeReceivables", "dart_ShortTermTradeReceivable"),
           ("매출채권및기타채권", "매출채권", "매출채권및기타유동채권", "단기매출채권")),
    "ca": (("BS",), ("ifrs-full_CurrentContractAssets", "ifrs-full_ContractAssets"), ("계약자산", "미청구공사", "유동계약자산")),
    "inv": (("BS",), ("ifrs-full_Inventories", "ifrs-full_CurrentInventoriesHeldForSale"), ("재고자산",)),
    "eq_parent": (("BS",), ("ifrs-full_EquityAttributableToOwnersOfParent",), ("지배기업의소유주에게귀속되는자본", "지배기업소유주지분")),
    "eq": (("BS",), ("ifrs-full_Equity",), ("자본총계",)),
}
INT_IS = (IS, (), ("이자비용",))
INT_CF = (("CF",), ("ifrs-full_InterestPaidClassifiedAsOperatingActivities", "ifrs-full_InterestPaidClassifiedAsFinancingActivities"),
          ("이자의지급", "이자지급", "이자의 지급", "이자지급액"))
INT_FC = (IS, ("ifrs-full_FinanceCosts",), ("금융비용", "금융원가"))


def eok(v):
    return None if v is None else round(v / 1e8, 1)


def pick(rows, key):
    sj, ids, names = ACC[key]
    return find(rows, sj, ids, names)


def extract(rows, prev_rows, months):
    """rows: 이번 보고서, prev_rows: 전년 같은 보고서(재무상태표 비교용). 단위 억원."""
    cum = months < 12
    g = lambda k: pick(rows, k)
    out = {}
    for k in ("rev", "op", "cf"):
        r = g(k)
        out[k] = [eok(amt(r, cum)), eok(amt_prev(r, cum))]
    out["ebt"] = eok(amt(g("ebt"), cum))
    ni = g("ni_parent") or g("ni")
    out["ni"] = eok(amt(ni, cum))
    # 이자비용: 손익의 '이자비용' → 현금흐름표의 '이자 지급' → 금융비용(이자 외 포함) 순서
    src = None
    for spec, label in ((INT_IS, "이자비용"), (INT_CF, "이자 지급(현금흐름표)"), (INT_FC, "금융비용(이자 외 항목 포함)")):
        r = find(rows, *spec)
        v = amt(r, cum if spec is not INT_CF else False)
        if v is not None:
            out["int"], src = eok(abs(v)), label
            break
    else:
        out["int"] = None
    out["int_src"] = src

    def bs(rws, k):
        return amt(pick(rws, k), False) if rws else None

    ar_now = (bs(rows, "ar") or 0) + (bs(rows, "ca") or 0) if (bs(rows, "ar") is not None or bs(rows, "ca") is not None) else None
    ar_prev = None
    if prev_rows:
        a, c = bs(prev_rows, "ar"), bs(prev_rows, "ca")
        ar_prev = (a or 0) + (c or 0) if (a is not None or c is not None) else None
    out["ar"] = [eok(ar_now), eok(ar_prev)]
    out["inv"] = [eok(bs(rows, "inv")), eok(bs(prev_rows, "inv"))]
    eqp = bs(rows, "eq_parent")
    out["eq"] = eok(eqp if eqp is not None else bs(rows, "eq"))
    out["roe"] = round(out["ni"] * 12 / months / out["eq"] * 100, 1) if out["ni"] is not None and out["eq"] else None
    return out


# ---------- 보고서 고르기 ----------
def candidates(today):
    """오늘 기준으로 나와 있을 가능성이 큰 정기보고서부터 (12월 결산 기준 제출기한)."""
    y = today.year
    seq = []
    for yy in (y, y - 1):
        seq += [(yy, "11014", datetime(yy, 11, 14)), (yy, "11012", datetime(yy, 8, 14)),
                (yy, "11013", datetime(yy, 5, 15)), (yy - 1, "11011", datetime(yy, 3, 31))]
    naive = today.replace(tzinfo=None)
    return [(yy, rc) for yy, rc, due in seq if due - timedelta(days=45) <= naive][:4]  # 기한 전에 내는 회사가 많다


def fin_rows(dart, corp, year, rc):
    for fs in ("CFS", "OFS"):
        j = dart.get("fnlttSinglAcntAll.json", corp_code=corp, bsns_year=year, reprt_code=rc, fs_div=fs)
        if j and j.get("status") == "000" and j.get("list"):
            return j["list"], ("연결" if fs == "CFS" else "별도")
    return None, None


def audit(dart, corp, year):
    j = dart.get("accnutAdtorNmNdAdtOpinion.json", corp_code=corp, bsns_year=year, reprt_code="11011")
    if not j or j.get("status") != "000":
        return None
    for r in j.get("list", []):
        if "당기" in (r.get("bsns_year") or "") and r.get("adt_opinion"):
            return r["adt_opinion"].strip()
    lst = [r for r in j.get("list", []) if r.get("adt_opinion")]
    return lst[0]["adt_opinion"].strip() if lst else None


def raises(dart, corp, today):
    bgn = (today - timedelta(days=730)).strftime("%Y%m%d")
    j = dart.get("list.json", corp_code=corp, bgn_de=bgn, end_de=today.strftime("%Y%m%d"),
                 pblntf_ty="B", page_count=100)
    if not j or j.get("status") not in ("000", "013"):
        return None
    seen, items = set(), []
    for r in j.get("list", []) or []:
        nm = r.get("report_nm", "")
        if not RAISE_RE.search(nm) or "철회" in nm:
            continue
        base = re.sub(r"^\[[^\]]*\]", "", nm).strip()
        key = (base, r.get("rcept_dt", "")[:6])  # 정정공시는 같은 달 같은 이름이면 한 번으로
        if key in seen:
            continue
        seen.add(key)
        items.append([r.get("rcept_dt", ""), base, r.get("rcept_no", "")])
    return items


def company(dart, corp):
    j = dart.get("company.json", corp_code=corp)
    if not j or j.get("status") != "000":
        return {}
    return {"cls": j.get("corp_cls", ""), "induty": j.get("induty_code", ""), "name": j.get("stock_name") or j.get("corp_name")}


def build_one(dart, corp, info, today):
    rows = None
    for year, rc in candidates(today):
        rows, fs = fin_rows(dart, corp, year, rc)
        if rows:
            break
    if not rows:
        return None
    label, months = REPRT[rc]
    prev_rows, _ = fin_rows(dart, corp, year - 1, rc)
    v = extract(rows, prev_rows, months)
    rcept = rows[0].get("rcept_no", "")
    ay = year if rc == "11011" else year - 1
    op = audit(dart, corp, ay)
    rs = raises(dart, corp, today)
    ind = info.get("induty", "")
    period = f"{year} {label}" + ("" if rc == "11011" else " 누적")
    prev_period = f"{year - 1} {label}" + ("" if rc == "11011" else " 누적")
    bs_now = {"11013": "03-31", "11012": "06-30", "11014": "09-30", "11011": "12-31"}[rc]
    return {
        "code": info["code"], "name": info["name"], "market": MKT.get(info.get("cls"), ""),
        "fin": ind[:2] in ("64", "65", "66"),  # 금융·보험업 (표준산업분류)
        "basis": {"year": year, "reprt": label, "months": months, "fs": fs, "rcept_no": rcept,
                  "filed": rcept[:8], "now": period, "prev": prev_period,
                  "bs_now": f"{year}-{bs_now}", "bs_prev": f"{year - 1}-{bs_now}" if prev_rows else None},
        "v": v,
        "audit": {"year": ay, "opinion": op},
        "raises": rs,
        "updated": today.strftime("%Y-%m-%d"),
    }


# ---------- 전체 흐름 ----------
def listed(dart):
    raw = dart.get("corpCode.xml")
    z = zipfile.ZipFile(io.BytesIO(raw))
    root = ET.fromstring(z.read(z.namelist()[0]))
    out = {}
    for e in root.iter("list"):
        sc = (e.findtext("stock_code") or "").strip()
        if sc:
            out[e.findtext("corp_code").strip()] = {"code": sc, "name": (e.findtext("corp_name") or "").strip()}
    return out


def new_filers(dart, today, days):
    """최근 며칠 사이 정기보고서를 낸 상장사 corp_code."""
    got, page = set(), 1
    bgn = (today - timedelta(days=days)).strftime("%Y%m%d")
    while True:
        j = dart.get("list.json", bgn_de=bgn, end_de=today.strftime("%Y%m%d"), pblntf_ty="A",
                     page_no=page, page_count=100)
        if not j or j.get("status") != "000":
            break
        for r in j.get("list", []):
            if r.get("corp_cls") in ("Y", "K", "N") and re.search(r"분기보고서|반기보고서|사업보고서", r.get("report_nm", "")):
                got.add(r["corp_code"])
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--days", type=int, default=4, help="최근 며칠 안에 정기보고서를 낸 회사는 다시 받는다")
    ap.add_argument("--stale", type=int, default=45, help="이보다 오래된 자료는 남는 호출로 다시 받는다(자금조달 갱신)")
    a = ap.parse_args()
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise SystemExit("DART_API_KEY 가 없습니다 (저장소 Settings → Secrets → Actions 에 추가).")
    data = os.path.abspath(a.data)
    os.makedirs(os.path.join(data, "fin"), exist_ok=True)
    sp = os.path.join(data, "state.json")
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    comp = state.setdefault("company", {})   # corp_code -> {cls, induty}
    done = state.setdefault("done", {})      # corp_code -> {rcept, updated}
    today = datetime.now(KST)
    dart = Dart(key, a.budget)
    try:
        corps = listed(dart)
    except Budget:
        corps = {}
    print(f"상장사 {len(corps)}곳 · 완료 {len(done)}곳")

    try:
        fresh = new_filers(dart, today, a.days) if done else set()
    except Budget:
        fresh = set()
    todo = [c for c in corps if c in fresh]                       # 1) 새 정기보고서
    todo += [c for c in corps if c not in done and c not in fresh]  # 2) 아직 없는 회사
    old = sorted((c for c in corps if c in done and c not in fresh), key=lambda c: done[c].get("updated", ""))
    cut = (today - timedelta(days=a.stale)).strftime("%Y-%m-%d")
    todo += [c for c in old if done[c].get("updated", "") < cut]   # 3) 오래된 회사
    print(f"이번에 받을 후보 {len(todo)}곳 (새 공시 {len(fresh)}곳)")

    n_ok = n_none = 0
    try:
        for c in todo:
            info = dict(corps[c])
            if c not in comp:
                comp[c] = company(dart, c)
            info.update({k: comp[c].get(k) for k in ("cls", "induty")})
            rec = build_one(dart, c, info, today)
            if rec:
                with open(os.path.join(data, "fin", info["code"] + ".json"), "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
                done[c] = {"rcept": rec["basis"]["rcept_no"], "updated": rec["updated"]}
                n_ok += 1
            else:
                done[c] = {"rcept": "", "updated": today.strftime("%Y-%m-%d")}  # 정기보고서 없음(스팩·신규 등)
                n_none += 1
    except Budget:
        print("호출 한도에 닿아 여기서 멈춤. 다음 실행에서 이어 받는다.")

    idx = sorted(([v["code"], v["name"], MKT.get(comp.get(c, {}).get("cls"), "")]
                  for c, v in corps.items() if os.path.exists(os.path.join(data, "fin", v["code"] + ".json"))),
                 key=lambda x: x[1])
    with open(os.path.join(data, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": today.strftime("%Y-%m-%d %H:%M"), "total": len(corps), "list": idx}, f,
                  ensure_ascii=False, separators=(",", ":"))
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    print(f"저장 {n_ok}곳, 정기보고서 없음 {n_none}곳, 목록 {len(idx)}곳, DART 호출 {dart.calls}회")


if __name__ == "__main__":
    main()
