"""재무제표 공부 · 5분 체크 자동 입력용 재무 데이터 (OpenDART).

실행: DART_API_KEY=... python study_fin.py --data <폴더> [--budget 6000]
  - study-fin.yml 이 매일 밤 돌리고, 결과 폴더를 study-fin 브랜치에 저장한다.
  - site.yml 이 그 브랜치를 사이트의 /study/fin/ 에 붙인다 → 5분 체크에서 종목명을 넣으면 불러온다.

만드는 파일
  index.json        [[종목코드, 회사명, 시장]]  최근 180일 안에 정기보고서를 낸 코스피·코스닥 상장사 중 받은 곳
  log.json          마지막 실행 결과 (DART 호출 수, KB PER·PBR 성공·실패, 첫 오류)
  fin/<종목코드>.json 가장 최근 정기보고서(분기·반기·사업)의 누적 실적과 전년 같은 기간, 감사의견, 최근 2년 자금조달
  state.json        진행 상황 (다음 실행에서 이어서)

DART 하루 호출 한도(키 하나당 2만 회)를 다른 작업과 나눠 쓰므로 한 번에 --budget 회까지만 부른다.
처음엔 며칠에 걸쳐 전체를 채우고, 그 뒤로는 새 정기보고서를 낸 회사와 오래된 회사만 다시 받는다.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
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
KIND_RE = re.compile(r"(분기|반기|사업)보고서\s*\((\d{4})\.(\d{2})\)")


def periodic(dart, today, days=180):
    """최근 days일 사이 정기보고서(최종본)를 낸 코스피·코스닥 회사 → 회사별 가장 최근 보고서.
    상장 폐지된 회사는 자연히 빠지고, 어떤 보고서가 최신인지 추측할 필요가 없다. (목록 조회는 90일 단위)"""
    out = {}
    end = today
    while (today - end).days < days:
        bgn = max(end - timedelta(days=89), today - timedelta(days=days))
        for cls in ("Y", "K"):
            page = 1
            while True:
                j = dart.get("list.json", bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"), corp_cls=cls,
                             pblntf_ty="A", last_reprt_at="Y", page_no=page, page_count=100)
                if not j or j.get("status") != "000":
                    break
                for r in j.get("list", []):
                    m = KIND_RE.search(r.get("report_nm", ""))
                    sc = (r.get("stock_code") or "").strip()
                    if not m or not sc or "스팩" in r.get("corp_name", ""):
                        continue
                    c = r["corp_code"]
                    if c not in out or r.get("rcept_no", "") > out[c]["rcept_no"]:
                        out[c] = {"code": sc, "name": r.get("corp_name", "").strip(), "cls": cls, "kind": m.group(1),
                                  "y": int(m.group(2)), "m": int(m.group(3)), "rcept_no": r.get("rcept_no", "")}
                if page >= int(j.get("total_page", 1)):
                    break
                page += 1
        end = bgn - timedelta(days=1)
    return out


def report_keys(f):
    """보고서 이름(분기·반기·사업 + 기말 연월) → DART 재무 API 의 (사업연도, 보고서코드) 후보."""
    y, m, k = f["y"], f["m"], f["kind"]
    if k == "사업":
        return [(y, "11011")]
    if k == "반기":
        return [(y, "11012"), (y - 1, "11012"), (y + 1, "11012")] if m != 6 else [(y, "11012")]
    if m == 3:
        return [(y, "11013")]
    if m == 9:
        return [(y, "11014")]
    return [(y, "11013"), (y, "11014"), (y - 1, "11014"), (y + 1, "11013")]  # 12월 결산이 아닌 회사


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
    return {"induty": j.get("induty_code", "")}


def is_fin(ind):
    """은행·보험·증권·카드 같은 금융업 (표준산업분류). 지주회사(64992)는 빼고 본다."""
    ind = ind or ""
    return ind.startswith(("641", "6491", "65", "6612", "6611"))


def build_one(dart, corp, f, info, state, today):
    rows = year = rc = None
    for year, rc in report_keys(f):
        rows, fs = fin_rows(dart, corp, year, rc)
        if rows:
            break
    if not rows:
        return None
    label, months = REPRT[rc]
    prev_rows, _ = fin_rows(dart, corp, year - 1, rc)
    v = extract(rows, prev_rows, months)
    ay = f["y"] if rc == "11011" else f["y"] - 1   # 감사의견은 가장 최근 사업보고서
    au = state.setdefault("audit", {})
    if (au.get(corp) or [None])[0] != ay:
        au[corp] = [ay, audit(dart, corp, ay)]
    rs = raises(dart, corp, today)
    ym, pym = f"{f['y']}.{f['m']:02d}", f"{f['y'] - 1}.{f['m']:02d}"
    span = "" if rc == "11011" else " 누적"
    return {
        "code": f["code"], "name": f["name"], "market": MKT.get(f["cls"], ""),
        "fin": is_fin(info.get("induty")),
        "basis": {"year": year, "reprt": label, "months": months, "fs": fs, "rcept_no": f["rcept_no"],
                  "filed": f["rcept_no"][:8], "now": f"{ym}까지 {label}{span}", "prev": f"{pym}까지 {label}{span}",
                  "bs_now": f"{ym}말", "bs_prev": f"{pym}말" if prev_rows else None},
        "v": v,
        "audit": {"year": ay, "opinion": au[corp][1]},
        "raises": rs,
        "updated": today.strftime("%Y-%m-%d"),
    }


# ---------- KB증권 Open API: PER·PBR (kb-market-report 의 app/kb_client.py 와 같은 방식) ----------
KB_BASE = os.environ.get("KB_OPENAPI_BASE_URL", "https://developer.kbsec.com:32484").rstrip("/")
_SCALE = re.compile(r"_p(\d)(?:_\d+)?$")


def _kb_header():
    import socket
    import uuid
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    node = uuid.getnode()
    return {"ipAddr": ip, "macAddr": ":".join(f"{(node >> k) & 0xFF:02X}" for k in range(40, -1, -8))}


def _kb_post(path, body, headers):
    req = urllib.request.Request(KB_BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _kb_num(rec, field):
    v = rec.get(field)
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        if "." in s:
            return float(s)
        n = int(s)
    except ValueError:
        return None
    m = _SCALE.search(field)
    return n / 10 ** int(m.group(1)) if m else n


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                r = _find(v, key)
                if r is not None:
                    return r
    return None


def kb_prices(data, today, minutes=25):
    """fin/*.json 마다 KB 현재가(IVU10140)의 PER·PBR·주가를 px 로 넣는다. 밤에 돌므로 그날 종가 기준."""
    key, sec = os.environ.get("KB_OPENAPI_APP_KEY", "").strip(), os.environ.get("KB_OPENAPI_APP_SECRET", "").strip()
    if not (key and sec):
        print("KB_OPENAPI_APP_KEY/SECRET 이 없어 PER·PBR 은 건너뜀")
        return {"error": "KB 키 없음"}
    hdr = _kb_header()
    try:
        t = _kb_post("/oauth2/token", {"dataHeader": hdr, "dataBody": {"appKey": key, "appSecret": sec, "grantType": "client_credentials"}}, {})
        tb = t.get("dataBody", t)
        token = tb.get("access_token") or tb.get("accessToken")
    except Exception as e:
        print(f"KB 토큰 발급 실패: {e}")
        return {"error": f"토큰 발급 실패: {str(e)[:200]}"}
    if not token:
        print(f"KB 토큰 응답에 access_token 없음: {str(t)[:200]}")
        return {"error": f"토큰 응답 이상: {str(t)[:200]}"}
    files = sorted(glob.glob(os.path.join(data, "fin", "*.json")))
    ok = fail = streak = 0
    first_err, sample = None, None
    day = today.strftime("%Y-%m-%d")
    t0 = time.monotonic()
    for i, fp in enumerate(files):
        if time.monotonic() - t0 > minutes * 60:
            print(f"KB {minutes}분이 지나 여기서 멈춤 ({i}/{len(files)}). 다음 실행에서 나머지를 받는다.")
            break
        rec = json.load(open(fp, encoding="utf-8"))
        if (rec.get("px") or {}).get("date") == day:
            continue
        try:
            p = _kb_post("/api/v1/ivu10140", {"dataHeader": hdr, "dataBody": {"excg_clsf": "1", "shrt_cd": rec["code"]}},
                         {"appKey": key, "Authorization": f"bearer {token}"})
            body = p.get("dataBody")
            r = _find(body, "now_prc") if isinstance(body, dict) else None
            if not r:
                raise ValueError(str((p.get("dataHeader") or {}).get("processMessage") or p)[:120])
            per, pbr, price = _kb_num(r, "per_p2"), _kb_num(r, "pbr_p2"), _kb_num(r, "now_prc")
            rec["px"] = {"per": per, "pbr": pbr, "price": price, "date": day, "src": "KB증권"}
            if sample is None or rec["code"] == "005930":
                sample = [rec["code"], rec["name"], price, per, pbr]
            if i < 3 or rec["code"] == "005930":
                print(f"  KB {rec['code']} {rec['name']}: 주가 {price} PER {per} PBR {pbr}")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
            ok += 1
            streak = 0
        except Exception as e:
            fail += 1
            streak += 1
            first_err = first_err or str(e)[:200]
            if streak <= 3:
                print(f"  KB {rec.get('code')} 실패: {str(e)[:160]}")
            if streak >= 20:
                print("KB 연속 20회 실패 → 중단")
                break
        time.sleep(0.12)
    print(f"KB PER·PBR 저장 {ok}곳, 실패 {fail}곳")
    return {"ok": ok, "fail": fail, "first_error": first_err, "sample": sample}



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--kb", action="store_true", help="DART 다음에 KB증권 PER·PBR 도 받는다")
    ap.add_argument("--minutes", type=float, default=55, help="DART 받기 시간 상한(분) — 워크플로 제한 전에 저장하고 끝낸다")
    ap.add_argument("--kb-minutes", type=float, default=25, help="KB PER·PBR 받기 시간 상한(분)")
    ap.add_argument("--stale", type=int, default=45, help="이보다 오래된 자료는 남는 호출로 다시 받는다(자금조달 갱신)")
    a = ap.parse_args()
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise SystemExit("DART_API_KEY 가 없습니다 (저장소 Settings → Secrets → Actions 에 추가).")
    data = os.path.abspath(a.data)
    os.makedirs(os.path.join(data, "fin"), exist_ok=True)
    sp = os.path.join(data, "state.json")
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    if state.get("v") != 2:   # 첫 버전 진행 기록(상장폐지 회사까지 돌던 것)은 버린다
        state = {"v": 2}
    comp = state.setdefault("company", {})   # corp_code -> {induty}
    done = state.setdefault("done", {})      # corp_code -> {rcept, updated}
    today = datetime.now(KST)
    dart = Dart(key, a.budget)
    log = {"start": today.strftime("%Y-%m-%d %H:%M")}
    try:
        filings = periodic(dart, today)
    except Budget:
        filings = {}
    log["listed"] = len(filings)
    print(f"최근 정기보고서를 낸 상장사 {len(filings)}곳 · 완료 {len(done)}곳 (목록 조회 {dart.calls}회)")

    # 1) 더 새 보고서가 나온 회사 2) 아직 없는 회사 3) 오래된 회사(자금조달 갱신)
    newer = [c for c, f in filings.items() if c in done and done[c].get("rcept") != f["rcept_no"]]
    missing = [c for c in filings if c not in done]
    cut = (today - timedelta(days=a.stale)).strftime("%Y-%m-%d")
    old = sorted((c for c in filings if c in done and c not in newer and done[c].get("updated", "") < cut),
                 key=lambda c: done[c].get("updated", ""))
    todo = newer + missing + old
    print(f"이번에 받을 후보 {len(todo)}곳 (새 보고서 {len(newer)} · 처음 {len(missing)} · 오래됨 {len(old)})")

    def save():
        names = {f["code"]: (f["name"], MKT.get(f["cls"], "")) for f in filings.values()}
        idx = sorted(([code, *names[code]] for code in names if os.path.exists(os.path.join(data, "fin", code + ".json"))),
                     key=lambda x: x[1])
        with open(os.path.join(data, "index.json"), "w", encoding="utf-8") as fp:
            json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "total": len(filings), "list": idx}, fp,
                      ensure_ascii=False, separators=(",", ":"))
        with open(sp, "w", encoding="utf-8") as fp:
            json.dump(state, fp, ensure_ascii=False, separators=(",", ":"))
        return len(idx)

    n_ok = n_none = 0
    t0 = time.monotonic()
    try:
        for k, c in enumerate(todo, 1):
            if time.monotonic() - t0 > a.minutes * 60:
                print(f"{a.minutes:.0f}분이 지나 여기서 멈춤. 다음 실행에서 이어 받는다.")
                break
            if k % 100 == 0:
                el = time.monotonic() - t0
                print(f"  {k}/{len(todo)}곳 · {el / 60:.0f}분 · DART {dart.calls}회 ({dart.calls / max(el, 1):.1f}회/초)", flush=True)
                save()
            f = filings[c]
            if c not in comp:
                comp[c] = company(dart, c)
            rec = build_one(dart, c, f, comp[c], state, today)
            if rec:
                with open(os.path.join(data, "fin", f["code"] + ".json"), "w", encoding="utf-8") as fp:
                    json.dump(rec, fp, ensure_ascii=False, separators=(",", ":"))
                n_ok += 1
            else:
                n_none += 1
                log.setdefault("no_fin", []).append(f["name"])
            done[c] = {"rcept": f["rcept_no"], "updated": today.strftime("%Y-%m-%d")}
    except Budget:
        print("호출 한도에 닿아 여기서 멈춤. 다음 실행에서 이어 받는다.")
    n_idx = save()
    log.update({"saved": n_ok, "no_fin_n": n_none, "index": n_idx, "dart_calls": dart.calls,
                "dart_min": round((time.monotonic() - t0) / 60, 1)})
    log["no_fin"] = log.get("no_fin", [])[:30]
    print(f"저장 {n_ok}곳, 재무 없음 {n_none}곳, 목록 {n_idx}곳, DART 호출 {dart.calls}회, {(time.monotonic() - t0) / 60:.0f}분")
    if a.kb:
        log["kb"] = kb_prices(data, today, a.kb_minutes)
    with open(os.path.join(data, "log.json"), "w", encoding="utf-8") as fp:   # 실행 결과 (저장소에서 바로 확인용)
        json.dump(log, fp, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
