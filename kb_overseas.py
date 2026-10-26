"""KB증권 Open API 해외주식 시세 → kb-px 브랜치(us/<티커>.json, log.json).

Claude 작업 환경에서는 KB 서버(developer.kbsec.com:32484)가 연결을 끊어서, 같은 키가 되는 GitHub Actions(kb-px.yml)에서 받는다.
- 현재가: GSS10030 (거래소 krx_cd NAS·NYS·AMX, 종목 is_cd). 52주 고저·PER·EPS·시가총액도 함께 온다. 15분 지연 시세.
- 일봉: GSC10060 (chrt_clsf 3=일, mdfy_stk_prc_use_f 1=수정주가, rcrd_c 최대 5000)
명세: https://openapi.kbsec.com/apidoc_b2c (B2C_해외주식 › 기본시세). 조회 TR 만 쓴다(주문·잔고 TR 은 부르지 않는다).

티커: 인자 / --tickers "NVDA,BRK.B:NYS" / kb_overseas_tickers.txt / us_strong/index.json 의 미국 종목.
거래소를 안 적으면 NAS → NYS → AMX 순으로 현재가를 불러 맞는 곳을 쓴다.
"""
import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from study_fin import _kb_header, _kb_num, _kb_post

KST = timezone(timedelta(hours=9))
EXCH = ("NAS", "NYS", "AMX")
EXCH_NAME = {"NASDAQ": "NAS", "NYSE": "NYS", "NYSE AMERICAN": "AMX", "AMEX": "AMX"}
SRC = "KB증권 Open API (GSS10030 현재가 · GSC10060 일봉, 15분 지연)"


def num(rec, f):
    """'_p4' 로 끝나는 필드는 이미 소수점이 찍혀 와서 study_fin 의 _kb_num 이 float 로 읽는다."""
    try:
        return _kb_num(rec, f)
    except Exception:
        return None


def tickers_from(args, root):
    out = {}

    def add(t, ex=""):
        t = t.strip().upper()
        if t and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", t):
            out.setdefault(t, ex)

    for s in (args.tickers or "").replace(" ", ",").split(",") + list(args.ticker):
        if s.strip():
            t, _, ex = s.partition(":")
            add(t, ex.strip().upper())
    if out or args.only:
        return out
    p = os.path.join(root, "kb_overseas_tickers.txt")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line:
                t, _, ex = line.partition(":")
                add(t, ex.strip().upper())
    p = os.path.join(root, "us_strong", "index.json")
    if os.path.exists(p):
        for r in json.load(open(p, encoding="utf-8")):
            if r.get("region") or not r.get("ticker"):
                continue  # 미국 외 시장(중국 A주 등)은 빼고
            add(r["ticker"], EXCH_NAME.get(str(r.get("exchange", "")).upper(), ""))
    return out


class KB:
    def __init__(self, key, sec):
        self.hdr = _kb_header()
        t = _kb_post("/oauth2/token", {"dataHeader": self.hdr, "dataBody": {"appKey": key, "appSecret": sec, "grantType": "client_credentials"}}, {})
        tb = t.get("dataBody", t)
        tok = tb.get("access_token") or tb.get("accessToken")
        if not tok:
            raise RuntimeError(f"토큰 응답 이상: {str(t)[:200]}")
        self.auth = {"appKey": key, "Authorization": f"bearer {tok}"}

    def call(self, tr, body):
        time.sleep(0.15)  # 한도 5초 200회
        p = _kb_post(f"/api/v1/{tr}", {"dataHeader": self.hdr, "dataBody": body}, self.auth)
        h = p.get("dataHeader") or {}
        b = p.get("dataBody")
        if h.get("processFlag") == "B" or not isinstance(b, dict):
            raise ValueError(f"{tr}: {h.get('processCode')} {h.get('processMessage') or str(p)[:120]}")
        return b

    def quote(self, t, ex):
        b = self.call("gss10030", {"krx_cd": ex, "is_cd": t})
        if not num(b, "now_prc_p4") and not num(b, "sprc_p4"):
            raise ValueError(f"{ex}:{t} 시세 없음 ({str(b.get('msg') or '').strip()[:60]})")
        q = {
            "name": str(b.get("hngl_is_nm") or "").strip(), "nameEn": str(b.get("eng_is_nm") or "").strip(),
            "date": str(b.get("dt") or b.get("bsnss_dt") or "").strip(), "time": str(b.get("tm") or "").strip(),
            "kst": f"{str(b.get('kor_dt') or '').strip()} {str(b.get('kor_tm') or '').strip()}".strip(),
            "currency": str(b.get("dl_crncy") or "").strip(), "market": str(b.get("mkt_clsf") or "").strip(),
        }
        for k, f in [("price", "now_prc_p4"), ("prev", "sprc_p4"), ("chg", "bdy_cmpr_p4"), ("pct", "up_dwn_r_p2"),
                     ("open", "opn_prc_p4"), ("high", "hgh_prc_p4"), ("low", "lw_prc_p4"), ("volume", "vlm"),
                     ("hi52", "wk52_max_prc_p4"), ("lo52", "wk52_min_prc_p4"), ("per", "per_p4"), ("eps", "eps_p4"),
                     ("shares", "isng_stk_c"), ("mktcap", "opn_prc_tl_amt"), ("fx", "ntif_exch_r_p4"),
                     ("after", "mkt_aft_ccls_prc_p4"), ("afterPct", "mkt_aft_up_dwn_r_p2"),
                     ("c1w", "wk1_bfr_cls_prc_p4"), ("c1m", "mms1_bfr_cls_prc_p4"), ("c6m", "mms6_bfr_cls_prc_p4"),
                     ("c1y", "yr1_bfr_cls_prc_p4"), ("cYtd", "tsyr_first_bsnss_dt_cls_prc_p4")]:
            q[k] = num(b, f)
        if str(b.get("bdy_cmpr_ccd") or "").strip() in ("4", "5") and q["chg"] and q["chg"] > 0:
            q["chg"] = -q["chg"]  # 대비구분 4·5 = 하락(KB 는 부호 없이 줌)
        return q

    def daily(self, t, ex, n, today):
        last_err = None
        for start in (today, ""):  # 검색시작일(과거일자 검색용): 오늘부터 거꾸로, 안 되면 비워서
            try:
                b = self.call("gsc10060", {"krx_cd": ex, "is_cd": t, "chrt_clsf": "3", "clsf": "1", "bndl": "",
                                           "mdfy_stk_prc_use_f": "1", "rcrd_c": str(n), "srch_strt_dy": start})
            except Exception as e:
                last_err = e
                continue
            rows = {}
            for r in b.get("out2") or []:
                d = str(r.get("dt") or "").strip()
                c = num(r, "cls_prc_p4")
                if re.fullmatch(r"\d{8}", d) and c:
                    rows[d] = [f"{d[:4]}-{d[4:6]}-{d[6:]}", num(r, "opn_prc_p4"), num(r, "hgh_prc_p4"), num(r, "lw_prc_p4"), c, num(r, "vlm")]
            if rows:
                names = (str(b.get("hngl_is_nm") or "").strip(), str(b.get("eng_is_nm") or "").strip())
                return [rows[d] for d in sorted(rows)], names
        raise ValueError(f"일봉 없음: {last_err}" if last_err else "일봉 없음")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="*")
    ap.add_argument("--tickers", default=os.environ.get("KB_TICKERS", ""))
    ap.add_argument("--only", action="store_true", help="기본 목록(파일·강세종목)은 빼고 준 티커만")
    ap.add_argument("--data", default="_kbpx")
    ap.add_argument("--days", type=int, default=600, help="일봉 개수(최대 5000). 600 ≈ 2년 반")
    args = ap.parse_args()
    root = os.path.dirname(os.path.abspath(__file__))
    now = datetime.now(KST)
    os.makedirs(os.path.join(args.data, "us"), exist_ok=True)
    tick = tickers_from(args, root)
    log = {"run": now.strftime("%Y-%m-%d %H:%M KST"), "tickers": list(tick), "ok": [], "fail": {}}
    key, sec = os.environ.get("KB_OPENAPI_APP_KEY", "").strip(), os.environ.get("KB_OPENAPI_APP_SECRET", "").strip()
    try:
        if not (key and sec):
            raise RuntimeError("KB_OPENAPI_APP_KEY/SECRET 없음")
        kb = KB(key, sec)
    except Exception as e:
        log["error"] = f"토큰 발급 실패: {str(e)[:200]}"
        print(log["error"])
        tick = {}
    today = (now - timedelta(hours=14)).strftime("%Y%m%d")  # 미국 동부 날짜(대략)
    for t, ex in tick.items():
        q = err = None
        for e in ([ex] if ex in EXCH else []) + [x for x in EXCH if x != ex]:  # 적은 거래소가 틀려도 나머지를 본다
            try:
                q, ex = kb.quote(t, e), e
                break
            except Exception as x:
                err = x
        if not q:
            log["fail"][t] = str(err)[:200]
            print(f"  {t} 실패: {err}")
            continue
        rec = {"ticker": t, "krx_cd": ex, **{k: q.pop(k) for k in ("name", "nameEn")}, "quote": q,
               "daily_cols": ["date", "open", "high", "low", "close", "volume"], "daily": [],
               "fetched": now.strftime("%Y-%m-%d %H:%M KST"), "source": SRC}
        try:
            rec["daily"], names = kb.daily(t, ex, min(args.days, 5000), today)
            rec["name"], rec["nameEn"] = rec["name"] or names[0], rec["nameEn"] or names[1]
        except Exception as x:
            log["fail"][t] = f"일봉: {str(x)[:200]}"
            print(f"  {t} 일봉 실패: {x}")
        with open(os.path.join(args.data, "us", f"{t}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
        log["ok"].append(t)
        last = rec["daily"][-1] if rec["daily"] else None
        print(f"  {ex}:{t} {rec['name']} 현재가 {q['price']} ({q['pct']}%) 일봉 {len(rec['daily'])}개 마지막 {last}")
    # 목록: 지금까지 받은 모든 티커(이전 실행분 포함)
    idx = []
    for fn in sorted(os.listdir(os.path.join(args.data, "us"))):
        try:
            r = json.load(open(os.path.join(args.data, "us", fn), encoding="utf-8"))
            idx.append({"ticker": r["ticker"], "krx_cd": r["krx_cd"], "name": r["name"], "price": r["quote"].get("price"),
                        "pct": r["quote"].get("pct"), "days": len(r["daily"]), "fetched": r["fetched"]})
        except Exception:
            pass
    with open(os.path.join(args.data, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=0)
    with open(os.path.join(args.data, "log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(f"KB 해외시세 성공 {len(log['ok'])} · 실패 {len(log['fail'])}")


if __name__ == "__main__":
    main()
