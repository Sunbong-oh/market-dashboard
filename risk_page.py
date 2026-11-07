"""위험신호 (/risk/) — 반도체 소부장 '나 홀로 급등' 경보.

2026-10 사례: 9/4~10/6 반도체 소부장(소재·부품·장비)이 +35% 오르며 무더기 신고가를 냈지만, 대장주(SK하이닉스·삼성전자)는
10/2부터 이미 빠지고 있었다. 이슈 없이 10/14 -6.5%, 10/15 -14.5% 되밀렸다. 이런 '대장 없이 소부장만 달리는' 모양을 매일 점검한다.

스위치 조건(4개 모두 = 켜짐, 3개 = 주의). 2015~2026 네이버 일봉으로 정한 값:
  ① 급등: 소부장 지수(동일가중)가 30거래일 저점보다 +15% 이상
  ② 그룹 신고가: 최근 11거래일 중 하루라도 소부장의 20% 이상이 3개월(60거래일) 신고가(장중 고가 기준)
  ③ 대장 이탈: 대장 2종목(하이닉스·삼성 동일가중)이 20거래일 고점보다 -5% 이하
  ④ 소부장은 고점권: 소부장 지수가 20거래일 고점의 -5% 이내
켜지면 마지막으로 4개가 맞은 날부터 HOLD 거래일 동안 '켜짐 유지'.

소부장 명단 = kb flow-live map.json '반도체와반도체장비'(시가총액 상위 500 안) - 대장·SK스퀘어·우선주. 실패하면 FALLBACK.
지금 명단으로 과거를 계산하므로(사라진·작아진 종목 빠짐) 과거 성적은 실제보다 좋게 보일 수 있다.
"""
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
FCHART = "https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=3000&requestType=0"
MAP_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/map.json"
CODES_URL = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/study-fin/index.json"
SECTOR = "반도체와반도체장비"
LEADERS = {"000660": "SK하이닉스", "005930": "삼성전자"}
SKIP = {"삼성전자", "SK하이닉스", "SK스퀘어"}
FALLBACK = {
    "042700": "한미반도체", "007660": "이수페타시스", "000990": "DB하이텍", "281820": "케이씨텍", "003160": "디아이",
    "195870": "해성디에스", "029460": "케이씨", "011930": "신성이엔지", "077500": "유니퀘스트", "025560": "미래산업",
    "092220": "KEC", "006200": "한국전자홀딩스", "036930": "주성엔지니어링", "058470": "리노공업", "039030": "이오테크닉스",
    "240810": "원익IPS", "403870": "HPSP", "031980": "피에스케이홀딩스", "095340": "ISC", "319660": "피에스케이",
    "030530": "원익홀딩스", "357780": "솔브레인", "131290": "티에스이", "080220": "제주반도체", "440110": "파두",
    "084370": "유진테크", "067310": "하나마이크론", "005290": "동진쎄미켐", "064760": "티씨케이", "095610": "테스",
    "131970": "두산테스나", "089030": "테크윙", "036540": "SFA반도체", "183300": "코미코", "089970": "브이엠",
    "420770": "기가비스", "232140": "와이씨", "425420": "티에프이", "166090": "하나머티리얼즈", "252990": "샘씨엔에스",
    "356860": "티엘비", "101490": "에스앤에스텍"}
RUN, NHT, LGAP, SGAP = 0.15, 0.20, 0.05, 0.05
RUN_N, NH_N, NH_LB, HI_N = 30, 60, 10, 20
HOLD = 20          # 켜짐 유지 거래일
H = 20             # 결과 판정: 신호 뒤 20거래일(약 한 달) 안 최대 낙폭
HIT = 0.10         # 소부장 -10% 이상이면 '조정'
START = 300        # 과거 검증 시작(앞쪽은 계산용)
# 켜졌을 때 할 일(사용자가 바꾸면 여기만 고친다)
ACTIONS = ("소부장 신규 매수 멈춤 (추가 매수·물타기 금지)",
           "소부장 보유 비중 절반으로 줄이기 — 수익 난 종목부터",
           "남은 물량은 5일선 종가 이탈 때 정리",
           "스위치가 꺼지거나 소부장이 고점 대비 -15% 넘게 빠진 뒤 다시 판단")


def _get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _bars(code):
    """[(YYYYMMDD, 고가, 종가)] 오래된 것부터."""
    for _ in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(FCHART.format(code=code), headers=UA), timeout=30) as r:
                xml = r.read().decode("euc-kr", "replace")
            out = []
            for d in re.findall(r'data="([^"]+)"', xml):
                p = d.split("|")
                if len(p) >= 6 and p[4] not in ("", "0", "null"):
                    out.append((p[0], float(p[2]), float(p[4])))
            if out:
                return out
        except Exception:
            pass
    return []


# ---------- KB증권 Open API 일봉 (IVS11560, 수정주가) ----------
# KB 서버는 GitHub Actions 에서만 연결된다(사이트 빌드 site.yml 에 KB 키를 넘김). 최근 KB_CNT 거래일은 KB 값으로,
# 그보다 오래된 과거(2015~)는 네이버 일봉으로 채운다. KB 가 안 되면 네이버만 쓴다. 결과는 risk/state.json 의 src.
KB_BASE = os.environ.get("KB_OPENAPI_BASE_URL", "https://developer.kbsec.com:32484").rstrip("/")
KB_CNT = 400


class KB:
    def __init__(self):
        self.key = os.environ.get("KB_OPENAPI_APP_KEY", "").strip()
        self.sec = os.environ.get("KB_OPENAPI_APP_SECRET", "").strip()
        self.token, self.ok, self.fail, self.err = None, 0, 0, None
        if not (self.key and self.sec):
            self.err = "KB 키 없음"
            return
        try:
            from study_fin import _kb_header, _kb_post
            self.hdr, self._post = _kb_header(), _kb_post
            t = _kb_post("/oauth2/token", {"dataHeader": self.hdr, "dataBody": {"appKey": self.key, "appSecret": self.sec,
                                                                                 "grantType": "client_credentials"}}, {})
            tb = t.get("dataBody", t)
            self.token = tb.get("access_token") or tb.get("accessToken")
            if not self.token:
                self.err = f"토큰 응답 이상: {str(t)[:120]}"
        except Exception as e:
            self.err = f"토큰 발급 실패: {str(e)[:120]}"

    def daily(self, code, kosdaq):
        """[(YYYYMMDD, 고가, 종가)] KB 원문 단위(자릿수는 나중에 네이버와 맞춘다). 실패하면 []."""
        if not self.token:
            return []
        last = None
        for info in ("2", "1"):  # 2 = 수정주가, 안 되면 1
            try:
                p = self._post("/api/v1/ivs11560", {"dataHeader": self.hdr, "dataBody": {
                    "info_ccd": info, "mkt_clsf": "1" if kosdaq else "0", "chrt_clsf": "D", "minute_tck_indx": "",
                    "is_cd": code, "inq_clsf": "2", "strt_dy": "", "inq_cnt": str(KB_CNT)}},
                    {"appKey": self.key, "Authorization": f"bearer {self.token}"})
                out = []
                stack = [p.get("dataBody")]
                while stack:
                    o = stack.pop()
                    if isinstance(o, dict):
                        if "cls_prc_p2" in o:
                            d = str(o.get("dt") or "").strip()
                            try:
                                h = float(str(o.get("hgh_prc_p2")).replace(",", ""))
                                c = float(str(o.get("cls_prc_p2")).replace(",", ""))
                            except (TypeError, ValueError):
                                continue
                            if re.fullmatch(r"20\d{6}", d) and c > 0:
                                out.append((d, h, c))
                        stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
                    elif isinstance(o, list):
                        stack.extend(o)
                time.sleep(0.12)
                if len(out) >= 20:
                    self.ok += 1
                    return sorted(set(out))
                last = str((p.get("dataHeader") or {}).get("processMessage") or p)[:120]
            except Exception as e:
                last = str(e)[:120]
        self.fail += 1
        self.err = self.err or last
        return []


def _merge(nv, kb):
    """네이버 일봉에 KB 일봉을 덮어쓴다. KB 가격 자릿수(10의 거듭제곱)는 겹치는 날 네이버 종가에 맞춘다."""
    if not kb:
        return nv, False
    nm = {d: c for d, _, c in nv}
    rs = sorted(nm[d] / c for d, _, c in kb if d in nm and c)
    f = 1.0
    if rs:
        r = rs[len(rs) // 2]
        f = next((10.0 ** k for k in range(-4, 5) if 0.5 < r / 10.0 ** k < 2), 1.0)
    first = kb[0][0]
    return [b for b in nv if b[0] < first] + [(d, h * f, c * f) for d, h, c in kb], True


def markets():
    """{코드: True(코스닥)}"""
    c = _get(CODES_URL) or {}
    return {r[0]: (len(r) > 2 and r[2] == "코스닥") for r in c.get("list") or []}


def members():
    """{코드: 이름} 소부장 명단."""
    j, c = _get(MAP_URL), _get(CODES_URL)
    try:
        codes = {r[1]: r[0] for r in c["list"]}
        names = [s["n"] for secs in j["data"].values() for sec in secs if sec.get("s") == SECTOR for s in sec["st"]]
        out = {codes[n]: n for n in names if n in codes and n not in SKIP and not n.endswith("우")}
        if len(out) >= 20:
            return out
    except (TypeError, KeyError):
        pass
    return dict(FALLBACK)


def compute(mem=None):
    mem = mem or members()
    codes = list(mem) + list(LEADERS)
    with ThreadPoolExecutor(max_workers=8) as ex:
        bars = dict(zip(codes, ex.map(_bars, codes)))
    kb, mk = KB(), markets()
    used = 0
    if kb.token:
        with ThreadPoolExecutor(max_workers=3) as ex:
            kbars = dict(zip(codes, ex.map(lambda c: kb.daily(c, mk.get(c, False)), codes)))
        for c in codes:
            bars[c], u = _merge(bars[c], kbars[c])
            used += u
    src = {"kb": used, "total": len(codes), "kb_fail": kb.fail, "kb_err": kb.err}
    print("위험신호 일봉 출처: KB", used, "/", len(codes), "종목", "" if not kb.err else f"(KB: {kb.err})")
    lead = [bars[c] for c in LEADERS]
    if any(not b for b in lead):
        return None
    ds = sorted({b[0] for c in codes for b in bars[c]})
    ds = [d for d in ds if d >= lead[0][0][0]]
    P = {d: i for i, d in enumerate(ds)}
    N = len(ds)
    rets, nhs = [[] for _ in ds], [[] for _ in ds]
    for c in mem:
        B = bars[c]
        for k in range(NH_N + 1, len(B)):
            i = P.get(B[k][0])
            if i is None or B[k - 1][2] <= 0:
                continue
            rets[i].append(B[k][2] / B[k - 1][2] - 1)
            nhs[i].append(B[k][1] >= max(b[1] for b in B[k - NH_N:k]))
    S = [100.0]
    for i in range(1, N):
        S.append(S[-1] * (1 + (sum(rets[i]) / len(rets[i]) if rets[i] else 0)))
    NH = [sum(x) / len(x) if len(x) >= 10 else 0 for x in nhs]
    L = []
    for b in lead:
        m, last, s = {x[0]: x[2] for x in b}, None, []
        for d in ds:
            last = m.get(d, last)
            s.append(last)
        L.append(s)
    L = [(L[0][i] / L[0][0] + L[1][i] / L[1][0]) * 50 for i in range(N)]

    def checks(i):
        run = S[i] / min(S[i - RUN_N + 1:i + 1]) - 1
        nh = max(NH[i - NH_LB:i + 1])
        lg = L[i] / max(L[i - HI_N + 1:i + 1]) - 1
        sg = S[i] / max(S[i - HI_N + 1:i + 1]) - 1
        return [(run >= RUN, run), (nh >= NHT, nh), (lg <= -LGAP, lg), (sg >= -SGAP, sg)]

    def fwd(i):
        return None if i + H >= N else min(S[i + 1:i + H + 1]) / S[i] - 1

    on = [i >= RUN_N and all(c for c, _ in checks(i)) for i in range(N)]
    sig, last = [], -99
    for i in range(START, N):
        if on[i]:
            if i - last > HOLD:
                sig.append(i)
            last = i
    cases = []
    for i in sig:
        ck = checks(i)
        cases.append({"d": ds[i], "run": ck[0][1], "nh": ck[1][1], "lg": ck[2][1], "sg": ck[3][1], "mdd": fwd(i),
                      "days": sum(on[i:i + HOLD + 1])})
    base = [fwd(i) for i in range(START, N - H)]
    done = [c for c in cases if c["mdd"] is not None]
    i = N - 1
    ck = checks(i)
    lastOn = max([j for j in range(N) if on[j]] or [-999])
    n_ok = sum(c for c, _ in ck)
    if on[i]:
        level = "on"
    elif i - lastOn <= HOLD:
        level = "hold"
    elif n_ok >= 3:
        level = "warn"
    else:
        level = "off"
    tail = range(max(0, N - 160), N)
    return {"src": src, "asof": ds[-1], "level": level, "checks": ck, "n_ok": n_ok, "since": (i - lastOn) if lastOn >= 0 else None,
            "lastOn": ds[lastOn] if lastOn >= 0 else None, "members": len(mem), "cases": cases,
            "stat": {"n": len(done), "hit": sum(c["mdd"] <= -HIT for c in done),
                     "avg": sum(c["mdd"] for c in done) / len(done) if done else 0,
                     "base_hit": sum(x <= -HIT for x in base) / len(base), "base_avg": sum(base) / len(base),
                     "from": ds[START]},
            "_bars": bars, "chart": {"d": [ds[j] for j in tail], "S": [S[j] for j in tail], "L": [L[j] for j in tail],
                      "on": [on[j] for j in tail], "nh": [NH[j] for j in tail]}}


# ---------- 실적 둔화 경보 (분기 매출 성장률) ----------
# 사용자 규칙(2026-11-07): 실적이 폭증하다가 '다음 분기 매출 성장률이 줄어들 것'으로 예상되면 그 분기 실적 발표 전에 정리.
# 실제 = 네이버 분기 표(study-fin q/<코드>.json) + 오늘까지 나온 DART 잠정실적(kb earnings-live kr_prelim).
# 다음 분기 예상 = 네이버 분기 컨센서스. 없고 다음 분기가 4분기면 '연간 컨센서스 - 1~3분기 실제'로 만든다.
Q_URL = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/study-fin/q/{code}.json"
PRE_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json"
CAL_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/main/calendar/{ym}.json"
BOOM_QOQ, BOOM_YOY, SLOW_PT = 0.15, 0.50, 0.05   # 폭증: 직전 분기 전분기 대비 +15%↑ 또는 전년 대비 +50%↑ / 둔화: 성장률 5%p↑ 하락
# 매도 방아쇠(2026-11-07 사용자: '하이닉스를 6월에 팔았어야 하는 규칙'): 둔화 구간(직전 발표 ~ 다음 발표) 안에서
# 60거래일 상승률(전날 기준) +RUN60 이상이던 종목이 하루 -DROP1 이상 빠지면 매도. 가속 구간의 같은 급락은 눌림이었다(검증 risk_earn_bt).
RUN60, DROP1 = 1.00, 0.10
# 과거 검증(risk-bt 2026-11-07 실행, 반도체 44종목 2015~2026, 실제 매출로 구간을 정한 '완벽한 예상' 가정): (60일 상승, 하루 하락, 둔화 n·중앙·하락비율, 가속 n·중앙·하락비율)
BT_ROWS = ((1.00, 0.10, 10, -0.116, 0.70, 6, 0.294, 0.17), (1.50, 0.07, 13, -0.121, 0.62, 2, 0.074, 0.50),
           (1.00, 0.07, 21, -0.051, 0.62, 8, 0.294, 0.12), (0.80, 0.07, 37, -0.019, 0.54, 12, 0.250, 0.17))


def _qnext(q):
    y, m = int(q[:4]), int(q[5:7])
    return f"{y + (m == 12)}.{(m % 12) + 3:02d}"


def _qprev(q, n=1):
    y, m = int(q[:4]), int(q[5:7])
    for _ in range(n):
        y, m = (y - 1, 12) if m == 3 else (y, m - 3)
    return f"{y}.{m:02d}"


def _cal_days(now):
    """{회사 이름: 'YYYY-MM-DD'} 앞으로 석 달 증시 캘린더 국내 실적 일정."""
    out, y, m = {}, now.year, now.month
    for _ in range(3):
        j = _get(CAL_URL.format(ym=f"{y}-{m:02d}")) or {}
        for day, v in sorted((j.get("days") or {}).items()):
            if day < now.strftime("%Y-%m-%d"):
                continue
            for n in v.get("earnings_kr") or []:
                n = re.sub(r"\(.*?\)|★|\s", "", n)
                out.setdefault(n, day)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def earn_one(code, name, qj, pre, cal, bars=None):
    act, cons = {}, {}
    for row in (qj or {}).get("q") or []:
        if row[1] is None:
            continue
        (cons if len(row) > 4 and row[4] else act)[row[0]] = row[1]
    p = pre.get(code)
    if p and p.get("sales") and p["sales"][0]:
        act[p["q"]] = p["sales"][0]
        if p["sales"][1]:
            act.setdefault(_qprev(p["q"]), p["sales"][1])
        if p["sales"][2]:
            act.setdefault(_qprev(p["q"], 4), p["sales"][2])
    if not act:
        return None
    last = max(act)
    nq = _qnext(last)
    est, how = cons.get(nq), "네이버 분기 컨센서스"
    if est is None and nq.endswith(".12"):
        y = nq[:4]
        ann = {r[0]: r[1] for r in (qj or {}).get("a") or [] if len(r) > 4 and r[4] and r[1]}
        q123 = [act.get(f"{y}.{m}") for m in ("03", "06", "09")]
        if ann.get(nq) and all(q123):
            est, how = ann[nq] - sum(q123), "연간 컨센서스 - 1~3분기 실제"
    g = lambda a, b: (a / b - 1) if a and b and b > 0 else None
    lq, ly = g(act[last], act.get(_qprev(last))), g(act[last], act.get(_qprev(last, 4)))
    nqoq, nyoy = g(est, act[last]), g(est, act.get(_qprev(nq, 4)))
    prev_q = g(act.get(_qprev(last)), act.get(_qprev(last, 2)))
    boom = (lq is not None and lq >= BOOM_QOQ) or (ly is not None and ly >= BOOM_YOY)
    # 둔화 구간의 시작 = 직전 분기 실적 발표일(잠정실적 공시일, 없으면 정기보고서 제출 기한)
    if p and p.get("day") and p["q"] == last:
        start = p["day"].replace("-", "")
    else:
        y, m = int(last[:4]), int(last[5:7])
        start = ((datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)) + timedelta(days=90 if m == 12 else 45)).strftime("%Y%m%d")
    c = [b[2] for b in bars or []]
    dd = [b[0] for b in bars or []]
    run = c[-1] / c[-61] - 1 if len(c) > 61 else None
    trig = None
    for i in range(max(61, next((k for k, d in enumerate(dd) if d > start), len(dd))), len(c)):
        if c[i - 1] / c[i - 61] - 1 >= RUN60 and c[i] / c[i - 1] - 1 <= -DROP1:
            trig = (dd[i], c[i] / c[i - 1] - 1, c[i - 1] / c[i - 61] - 1)
            break
    window = nqoq is not None and lq is not None and boom and nqoq <= lq - SLOW_PT
    if nqoq is None or lq is None:
        lvl = "none"
    elif window:
        lvl = "sell" if trig else "ready" if run is not None and run >= RUN60 else "watch"
    else:
        lvl = "dip" if trig else "ok"
    when = cal.get(name)
    if when:
        when_t = f"{when[5:7]}/{when[8:]} (캘린더)"
    elif p and p.get("day") and p["q"] == last:
        dt = datetime.strptime(p["day"], "%Y-%m-%d") + timedelta(days=91)
        when_t, when = f"{dt:%m/%d}께 (추정)", dt.strftime("%Y-%m-%d")
    else:  # 잠정실적 공시가 없는 회사: 정기보고서 제출 기한(분기 끝 + 45일, 4분기는 + 90일)
        y, m = int(nq[:4]), int(nq[5:7])
        end = datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        dt = end + timedelta(days=90 if m == 12 else 45)
        when, when_t = dt.strftime("%Y-%m-%d"), f"{dt:%m/%d}까지 (보고서 기한)"

    return {"code": code, "n": name, "last": last, "sales": act[last], "lq": lq, "ly": ly, "pq": prev_q,
            "nq": nq, "est": est, "how": how, "nqoq": nqoq, "nyoy": nyoy, "boom": boom, "lvl": lvl,
            "when": when, "when_t": when_t, "start": start, "run": run, "trig": trig}


def earnings(mem, now, bars=None):
    names = dict(LEADERS)
    names.update(mem)
    pre = (_get(PRE_URL) or {}).get("kr_prelim") or {}
    cal = _cal_days(now)
    with ThreadPoolExecutor(max_workers=8) as ex:
        qs = dict(zip(names, ex.map(lambda c: _get(Q_URL.format(code=c)), names)))
    rows = [x for x in (earn_one(c, n, qs[c], pre, cal, (bars or {}).get(c)) for c, n in names.items()) if x]
    order = {"sell": 0, "ready": 1, "watch": 2, "dip": 3, "ok": 4, "none": 5}
    rows.sort(key=lambda x: (x["code"] not in LEADERS, order[x["lvl"]], -(x["sales"] or 0)))
    return rows


def _won(v):
    return "-" if v is None else f"{v / 10000:,.1f}조" if v >= 10000 else f"{v:,.0f}억"


EL = {"sell": ("🔴 매도 신호", "sell"), "ready": ("🟠 급락 하루면 매도", "ready"), "watch": ("🟡 둔화 구간", "slow"),
      "dip": ("🟢 가속 구간 급락(눌림)", "okk"), "ok": ("🟢 유지·가속", "okk"), "none": ("⚪ 예상치 없음", "nn")}
ES = {"sell": "🔴 매도", "ready": "🟠 대기", "watch": "🟡 둔화", "dip": "🟢 눌림", "ok": "🟢 유지", "none": "⚪ 없음"}


def _md(d):
    return f"{int(d[4:6])}/{int(d[6:])}"


def earn_why(x):
    if x["lvl"] == "sell":
        t = x["trig"]
        return f'{_md(t[0])} 하루 {_p(t[1])} (그 전 60일 {_p(t[2])})'
    if x["lvl"] in ("ready", "watch"):
        return f'60일 {_p(x["run"]) if x["run"] is not None else "-"}'
    if x["lvl"] == "dip":
        return f'{_md(x["trig"][0])} {_p(x["trig"][1])}'
    return ""


def earn_section(rows, n):
    if not rows:
        return ""
    head = ""
    for x in rows:
        if x["code"] in LEADERS and x["lvl"] != "none":
            head += (f'<li><b>{escape(x["n"])}</b>: 매출 성장률(전분기 대비) {_p(x["pq"]) if x["pq"] is not None else "-"} → '
                     f'{_p(x["lq"])} ({x["last"][2:4]}년 {int(x["last"][5:7]) // 3}분기 실제) → <b>{_p(x["nqoq"])}</b> ({x["nq"][2:4]}년 {int(x["nq"][5:7]) // 3}분기 예상). '
                     f'판정 <b>{EL[x["lvl"]][0]}</b>{f" ({escape(earn_why(x))})" if earn_why(x) else ""}, 다음 발표 {escape(x["when_t"])}</li>')
    trs = ""
    for x in rows:
        c = EL[x["lvl"]][1]
        trs += (f'<tr class="{c}"><td class="l"><b>{escape(x["n"])}</b><br><small>{x["last"][2:]} 매출 {_won(x["sales"])}</small></td>'
                f'<td>{_p(x["lq"]) if x["lq"] is not None else "-"}<br><small>→ 예상 {_p(x["nqoq"]) if x["nqoq"] is not None else "-"}</small></td>'
                f'<td>{ES[x["lvl"]]}<br><small>{escape(earn_why(x))}</small></td><td>{escape(x["when_t"])}</td></tr>')
    bt = "".join(f'<tr><td>+{g:.0%} / -{d:.0%}</td><td>{n1}건 · {_p(m1)} · {r1:.0%}</td><td>{n2}건 · {_p(m2)} · {r2:.0%}</td></tr>'
                 for g, d, n1, m1, r1, n2, m2, r2 in BT_ROWS)
    return f"""<section class="pg"><h2>실적 둔화 경보 — 둔화 구간의 첫 급락에 판다</h2>
<ul class="sq">{head}
<li><b>둔화 구간</b>: 실적이 폭증하던 종목(직전 분기 매출 전분기 대비 +{BOOM_QOQ:.0%}↑ 또는 전년 대비 +{BOOM_YOY:.0%}↑)인데 다음 분기 예상 성장률(전분기 대비)이 {SLOW_PT * 100:.0f}%p 넘게 낮을 때. 직전 실적 발표일부터 다음 발표일까지.</li>
<li><b>매도 신호</b>: 둔화 구간 안에서, 60거래일 동안 +{RUN60:.0%} 넘게 오른 종목이 <b>하루 -{DROP1:.0%} 이상</b> 빠진 첫날. 하이닉스는 2026-06-23(전날 292만 원 → 255.5만 원)에 신호가 나왔고, 7/30에는 132만 원까지 내렸습니다.</li>
<li>🟠 급락 하루면 매도 = 둔화 구간이고 60일 +{RUN60:.0%} 넘게 오른 상태. 다음 -{DROP1:.0%} 하루가 매도 신호입니다.</li>
<li>같은 급락이 <b>가속 구간</b>(성장률이 유지·가속)에서 나오면 과거엔 대부분 눌림이었습니다(아래 표).</li></ul>
<div class="tw"><table class="earn"><tr><th>종목</th><th>직전 분기 성장률<br>(전분기 대비)</th><th>판정</th><th>다음 발표</th></tr>{trs}</table></div>
<h2 style="margin-top:16px">과거 검증 — 급락한 날 팔았다면 60거래일 뒤 코스피 대비</h2>
<div class="tw"><table><tr><th>60일 상승 / 하루 하락</th><th>둔화 구간에서 팔았을 때<br><small>건수 · 중앙값 · 판 뒤 덜 오른 비율</small></th><th>가속 구간에서 팔았을 때</th></tr>{bt}</table></div>
<p class="note">· 검증: 반도체 44종목 2015~2026, DART 분기 매출·발표일(잠정실적 공시 또는 정기보고서 접수일) + 네이버 일봉, 2026-11-07 실행(risk-bt 브랜치 result.json). 지금 쓰는 기준은 첫 줄(+100% / -10%).<br>
· 과거엔 그때의 컨센서스가 없어 <b>실제 매출로 구간을 정했습니다(완벽한 예상 가정)</b>. 실제로는 예상치가 틀릴 수 있어 성적이 더 나쁠 수 있고, 건수가 적고(10건) 2026년에 몰려 있습니다. 둔화 구간에서도 판 뒤 더 오른 경우가 3건 있었습니다(제주반도체 2026-03, 기가비스 2026-03, 케이씨텍 2026-06).<br>
· 실제 = 네이버 증권 분기 실적 + DART 영업(잠정)실적 공시. 다음 분기 예상 = 네이버 분기 컨센서스, 없고 4분기면 '연간 컨센서스 - 1~3분기 실제'(<b>가정</b>).<br>
· 다음 발표일은 증시 캘린더 → 지난 잠정실적 공시일 + 91일 <b>추정</b> → 분기·사업보고서 제출 기한(분기 끝 + 45일, 4분기는 + 90일) 순서로 씁니다.</p>{n}</section>"""


# ---------- 차트 클라이맥스 경보 (2026-11-07 사용자: '하이닉스는 재무제표보다 클라이맥스 차트였어') ----------
# 🟠 클라이맥스 구간: 전날 종가가 200일 이동평균의 +CL_EXT 이상이고 60거래일 +CL_RUN 이상.
# 🔴 매도 신호: 구간에 든 뒤 CL_WIN 거래일 안에 하루 -CL_DROP 이상 빠진 첫날(그 뒤 CL_HOLD 거래일 표시).
# 🟡 과열: 200일선 +CL_WARN 이상 — 이 정도에선 실적이 가속 중이면 급락이 눌림이었다(아래 검증).
CL_EXT, CL_RUN, CL_DROP, CL_WIN, CL_HOLD, CL_WARN = 2.0, 0.5, 0.10, 10, 20, 1.0
# 검증(2026-11-07, 시가총액 상위 약 240종목 2015~2026 네이버 일봉, 판 날부터 60거래일 코스피 대비): (조건, 건수, 중앙값, 덜 오른 비율)
CL_BT = (("아무 날", 81356, -0.015, 0.54), ("200일선 +100% → 첫 -10%", 190, -0.036, 0.57),
         ("200일선 +150% → 첫 -10%", 90, -0.080, 0.59), ("200일선 +200% → 첫 -10% (지금 기준)", 49, -0.127, 0.71),
         ("  └ 2015~2020", 8, 0.057, 0.38), ("  └ 2021~2026", 41, -0.140, 0.78))


def climax(bars):
    """{lvl, ext(200일선 이격), run(60일), trig(날짜, 하루 등락)} 또는 None."""
    c = [b[2] for b in bars or []]
    d = [b[0] for b in bars or []]
    if len(c) < 262:
        return None
    cs = [0.0]
    for x in c:
        cs.append(cs[-1] + x)
    ext = lambda i: c[i] / ((cs[i + 1] - cs[i - 199]) / 200) - 1
    hot = lambda i: ext(i) >= CL_EXT and c[i] / c[i - 60] - 1 >= CL_RUN
    n = len(c)
    trig, armed = None, -999
    for i in range(max(262, n - CL_HOLD - CL_WIN - 5), n):
        if hot(i - 1):
            armed = i - 1
        if i - armed <= CL_WIN and c[i] / c[i - 1] - 1 <= -CL_DROP and i >= n - CL_HOLD:
            trig = (d[i], c[i] / c[i - 1] - 1)
            break
    e, run = ext(n - 1), c[-1] / c[-61] - 1
    lvl = "sell" if trig else "hot" if (hot(n - 1) or n - 1 - armed <= CL_WIN) else "warm" if e >= CL_WARN else "ok"
    return {"lvl": lvl, "ext": e, "run": run, "trig": trig}


CLV = {"sell": ("🔴 매도 신호", "sell"), "hot": ("🟠 클라이맥스", "ready"), "warm": ("🟡 과열", "slow"), "ok": ("🟢 보통", "okk")}


def climax_rows(names, bars):
    rows = []
    for code, nm in names.items():
        x = climax((bars or {}).get(code))
        if x:
            rows.append({"code": code, "n": nm, **x})
    order = {"sell": 0, "hot": 1, "warm": 2, "ok": 3}
    rows.sort(key=lambda x: (order[x["lvl"]], x["code"] not in LEADERS, -x["ext"]))
    return rows


def climax_section(rows, n):
    if not rows:
        return ""
    show = [x for x in rows if x["lvl"] != "ok" or x["code"] in LEADERS]
    tg = lambda x: f'<br><small>{_md(x["trig"][0])} {_p(x["trig"][1])}</small>' if x["trig"] else ""
    trs = "".join(f'<tr class="{CLV[x["lvl"]][1]}"><td class="l"><b>{escape(x["n"])}</b></td><td>{_p(x["ext"])}</td><td>{_p(x["run"])}</td>'
                  f'<td>{CLV[x["lvl"]][0]}{tg(x)}</td></tr>' for x in show)
    quiet = len(rows) - len(show)
    bt = "".join(f'<tr><td class="l">{escape(a)}</td><td>{b:,}</td><td>{_p(c)}</td><td>{d:.0%}</td></tr>' for a, b, c, d in CL_BT)
    return f"""<section class="pg"><h2>차트 클라이맥스 경보 — 하이닉스 2026년 6월형</h2>
<ul class="sq"><li><b>🟠 클라이맥스</b>: 주가가 200일 이동평균보다 <b>+{CL_EXT:.0%} 이상</b>(평균의 {CL_EXT + 1:.0f}배) 위에 있고 60거래일 +{CL_RUN:.0%} 이상 오른 상태. 다음 급락 하루가 매도 신호입니다.</li>
<li><b>🔴 매도 신호</b>: 클라이맥스 구간에 든 뒤 {CL_WIN}거래일 안에 <b>하루 -{CL_DROP:.0%} 이상</b> 빠진 첫날. 하이닉스: 6/22 200일선 +216%·60일 +196% → <b>6/23 -12.5%</b>(292만 → 255.5만 원) 신호, 7/30 132만 원.</li>
<li>🟡 과열(200일선 +{CL_WARN:.0%}↑)에서는 실적이 가속 중이면 급락이 눌림이었습니다(판 뒤 60일 코스피 대비 +23.8%, 23건). 그래서 매도 신호는 +{CL_EXT:.0%}에서만 냅니다.</li></ul>
<div class="tw"><table class="earn"><tr><th>종목</th><th>200일선 대비</th><th>60일 상승</th><th>판정</th></tr>{trs}</table></div>
<p class="note">{f"그 밖의 {quiet}종목은 🟢 보통(200일선 +{CL_WARN:.0%} 미만)." if quiet else ""}</p>
<h2 style="margin-top:16px">과거 검증 — 급락한 날 팔았다면 60거래일 뒤 코스피 대비</h2>
<div class="tw"><table><tr><th>조건 (60일 +{CL_RUN:.0%}↑ 공통)</th><th>건수</th><th>중앙값</th><th>덜 오른 비율</th></tr>{bt}</table></div>
<p class="note">· 시가총액 상위 약 240종목(반도체 포함), 2015~2026 네이버 일봉, 2026-11-07 계산. 같은 종목은 60거래일에 한 번만 셉니다.<br>
· <b>2015~2020년엔 통하지 않았습니다</b>(8건, 중앙 +5.7%). 성적 대부분이 2021년 이후, 특히 2026년 급락장에서 나왔습니다. 판 뒤 더 오른 경우도 있습니다(성호전자 2025-12 +760%, 네이처셀 2017-12, 알테오젠 2020-06 등).<br>
· 실적 구간과 겹쳐 보면: 200일선 +200%에선 실적이 가속 중이어도 판 쪽이 나았습니다(11건 중 7건, 중앙 -3.6%).</p>{n}</section>"""


# ---------- 화면 (KB 리서치 스타일) ----------
CSS = """
.rk{--y:#F2A900;--y2:#FBE7B0;--ink:#3D3A35;--bg2:#FAF8F3;--mut:#6B665D;--ln:#E6E0D2;--red:#C8102E;--grn:#2E7D4F;
  font-family:'Noto Sans KR','Pretendard','Malgun Gothic',sans-serif;color:var(--ink)}
.rk .pg{background:var(--bg2);border:1px solid var(--ln);border-top:6px solid var(--y);border-radius:6px;padding:18px 18px 10px;margin:0 0 16px}
.rk h2{margin:0 0 12px;font-size:18px;padding-left:10px;border-left:5px solid var(--y);color:var(--ink)}
.rk .pf{display:flex;justify-content:space-between;gap:8px;border-top:1px solid var(--ln);margin-top:14px;padding-top:6px;font-size:11.5px;color:var(--mut)}
.rk .cov{display:grid;grid-template-columns:1fr 240px;gap:16px}
.rk .kd{background:var(--ink);color:#fff;border-radius:4px;padding:12px 14px;font-size:13px}
.rk .kd b{display:block;color:var(--y);font-size:12px;letter-spacing:.1em;margin-bottom:6px}
.rk .kd div{display:flex;justify-content:space-between;border-bottom:1px solid #57534b;padding:4px 0}.rk .kd div:last-child{border:0}
.rk .sw{display:flex;align-items:center;gap:14px;padding:14px;border-radius:6px;background:#fff;border:2px solid var(--ln)}
.rk .sw .lamp{width:58px;height:58px;border-radius:50%;flex:none;box-shadow:inset 0 -4px 0 rgba(0,0,0,.18)}
.rk .sw .t{font-size:24px;font-weight:900;line-height:1.2}.rk .sw .s{font-size:13.5px;color:var(--mut);margin-top:3px}
.rk .on{border-color:var(--red)}.rk .on .lamp{background:var(--red)}.rk .on .t{color:var(--red)}
.rk .hold{border-color:var(--red)}.rk .hold .lamp{background:#E8798A}.rk .hold .t{color:var(--red)}
.rk .warn{border-color:var(--y)}.rk .warn .lamp{background:var(--y)}
.rk .off .lamp{background:var(--grn)}
.rk ul.sq{list-style:none;padding:0;margin:10px 0 0}.rk ul.sq li{position:relative;padding:3px 0 3px 16px;font-size:14px}
.rk ul.sq li:before{content:'';position:absolute;left:0;top:10px;width:8px;height:8px;background:var(--y)}
.rk table{width:100%;border-collapse:collapse;font-size:13px;background:#fff}
.rk th{background:var(--ink);color:#fff;font-weight:700;padding:7px 6px;text-align:center;white-space:nowrap}
.rk td{border-bottom:1px solid var(--ln);padding:7px 6px;text-align:center;font-variant-numeric:tabular-nums}
.rk td.l{text-align:left}.rk tr.hit td{background:#FDF3D7}.rk .ok{color:var(--red);font-weight:800}.rk .no{color:var(--mut)}
.rk .tw{overflow-x:auto}
.rk .chk td:first-child{font-size:18px;width:34px}
.rk .chart{width:100%;height:auto;display:block;background:#fff;border:1px solid var(--ln)}
.rk .stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}
.rk .stat div{background:#fff;border:1px solid var(--ln);border-top:3px solid var(--y);padding:8px 10px}
.rk .stat b{display:block;font-size:22px}.rk .stat span{font-size:12px;color:var(--mut)}
.rk .lg{display:flex;flex-wrap:wrap;gap:12px;font-size:12.5px;font-weight:700;margin-top:6px}.rk .lg i{display:inline-block;width:14px;height:8px;margin-right:5px;vertical-align:1px}
.rk table.earn td:first-child{min-width:96px}.rk table.earn td:nth-child(3){white-space:nowrap}.rk table.earn td:nth-child(4){font-size:11.5px}.rk table.earn small{color:var(--mut);font-size:11px}.rk tr.sell td{background:#FBE3E6}.rk tr.slow td{background:#FDF3D7}.rk tr.ready td{background:#FCE3C8}.rk tr.nn td{color:var(--mut)}
.rk .act li{font-size:15px;font-weight:700}
.rk .note{font-size:12px;color:var(--mut);line-height:1.6}
@media(max-width:640px){.rk .cov{grid-template-columns:1fr}.rk .sw .t{font-size:20px}.rk table{font-size:12px}.rk th,.rk td{padding:6px 3px}}
"""
LV = {"on": ("🔴 위험 스위치 켜짐", "4개 조건이 모두 맞았습니다. 소부장 대응 규칙을 지금 실행하세요."),
      "hold": ("🔴 켜짐 유지", "최근 {HOLD}거래일 안에 4개 조건이 모두 맞은 날이 있습니다(마지막 {lastOn}, {since}거래일 전)."),
      "warn": ("🟡 주의", "4개 중 3개가 맞았습니다. 나머지 하나가 맞으면 켜집니다."),
      "off": ("🟢 꺼짐", "소부장 나 홀로 급등 모양이 아닙니다.")}
NAMES = ("① 소부장 급등 (30일 저점 대비)", "② 그룹 신고가 (3개월 신고가 종목 비율, 최근 11일 최대)",
         "③ 대장 이탈 (하이닉스·삼성 20일 고점 대비)", "④ 소부장은 고점권 (20일 고점 대비)")
RULE = (f"+{RUN:.0%} 이상", f"{NHT:.0%} 이상", f"-{LGAP:.0%} 이하", f"-{SGAP:.0%} 이내")


def _d(s):
    return f"{s[:4]}.{s[4:6]}.{s[6:]}"


def _p(x, sign=True):
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.0f}%"


def lv_text(r):
    t, s = LV[r["level"]]
    return t, s.format(HOLD=HOLD, lastOn=_d(r["lastOn"]) if r.get("lastOn") else "-", since=r.get("since"))


def svg(ch):
    W, Hh, pl, pr, pt, pb = 720, 340, 48, 14, 10, 30
    S, L, on, d = ch["S"], ch["L"], ch["on"], ch["d"]
    n = len(S)
    s0, l0 = S[0], L[0]
    S = [x / s0 * 100 for x in S]
    L = [x / l0 * 100 for x in L]
    lo, hi = min(S + L), max(S + L)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    x = lambda i: pl + (W - pl - pr) * i / max(1, n - 1)
    y = lambda v: pt + (Hh - pt - pb) * (1 - (v - lo) / (hi - lo))
    bw = (W - pl - pr) / max(1, n - 1)
    shade = "".join(f'<rect x="{x(i) - bw / 2:.1f}" y="{pt}" width="{bw:.1f}" height="{Hh - pt - pb}" fill="#C8102E" opacity=".16"/>'
                    for i in range(n) if on[i])
    grid = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        grid += (f'<line x1="{pl}" x2="{W - pr}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#E6E0D2"/>'
                 f'<text x="{pl - 4}" y="{y(v) + 4:.1f}" font-size="14" fill="#6B665D" text-anchor="end">{v:.0f}</text>')
    ticks = "".join(f'<text x="{x(i):.1f}" y="{Hh - 8}" font-size="14" fill="#6B665D" text-anchor="middle">{d[i][4:6]}/{d[i][6:]}</text>'
                    for i in range(0, n, max(1, n // 6)))
    path = lambda a: "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(a))
    return (f'<svg class="chart" viewBox="0 0 {W} {Hh}" role="img" aria-label="소부장 지수와 대장 2종목 비교">{grid}{shade}'
            f'<path d="{path(L)}" fill="none" stroke="#3D3A35" stroke-width="2"/>'
            f'<path d="{path(S)}" fill="none" stroke="#F2A900" stroke-width="2.6"/>{ticks}'
            '</svg><div class="lg"><span><i style="background:#F2A900"></i>소부장 지수(동일가중)</span>'
            '<span><i style="background:#3D3A35"></i>대장(하이닉스·삼성)</span><span><i style="background:#C8102E;opacity:.35"></i>4개 조건 충족일</span></div>')


def body(r, now):
    t, s = lv_text(r)
    st = r["stat"]
    k = r.get("src") or {}
    feed = (f"KB증권 Open API 일봉(최근 {KB_CNT}거래일, {k['kb']}/{k['total']}종목)·네이버 증권 일봉(그 이전)" if k.get("kb")
            else "네이버 증권 일봉(KB증권 API 연결 실패)")
    src = f"자료: {feed}, 소부장 {r['members']}종목·SK하이닉스·삼성전자, 기준 {_d(r['asof'])} (장중이면 잠정) · 계산 Brian's 투자노트"
    pf = lambda n: f'<div class="pf"><span>{escape(src)}</span><span>{n}</span></div>'
    esrc = f"자료: 네이버 증권 분기 실적·컨센서스, DART 영업(잠정)실적 공시, 증시 캘린더 · 기준 {now:%Y-%m-%d %H:%M} KST"

    kd = (f'<div class="kd"><b>KEY DATA</b>'
          f'<div><span>기준일</span><span>{_d(r["asof"])}</span></div>'
          f'<div><span>맞은 조건</span><span>{r["n_ok"]} / 4</span></div>'
          f'<div><span>소부장 30일 상승</span><span>{_p(r["checks"][0][1])}</span></div>'
          f'<div><span>신고가 비율</span><span>{_p(r["checks"][1][1], False)}</span></div>'
          f'<div><span>대장 고점 대비</span><span>{_p(r["checks"][2][1])}</span></div>'
          f'<div><span>마지막 켜짐</span><span>{_d(r["lastOn"]) if r["lastOn"] else "-"}</span></div>'
          f'<div><span>과거 신호</span><span>{st["n"]}번 중 {st["hit"]}번 조정</span></div></div>')
    rows = "".join(f'<tr><td>{"✅" if ok else "⬜"}</td><td class="l">{NAMES[k]}</td><td>{_p(v, k != 1)}</td><td>{RULE[k]}</td></tr>'
                   for k, (ok, v) in enumerate(r["checks"]))
    cases = ""
    for c in reversed(r["cases"]):
        m = c["mdd"]
        res = ('<span class="no">진행 중</span>' if m is None else
               '<span class="ok">조정</span>' if m <= -HIT else '<span class="no">빗나감</span>')
        cases += (f'<tr class="{"hit" if m is not None and m <= -HIT else ""}"><td>{_d(c["d"])}</td><td>{_p(c["run"])}</td><td>{_p(c["nh"], False)}</td>'
                  f'<td>{_p(c["lg"])}</td><td>{"-" if m is None else _p(m)}</td><td>{res}</td></tr>')
    acts = "".join(f"<li>{escape(a)}</li>" for a in ACTIONS)
    return f'''<div class="rk">
<section class="pg"><div class="cov"><div>
<h2>소부장 나 홀로 급등 경보</h2>
<div class="sw {r["level"]}"><div class="lamp"></div><div><div class="t">{t}</div><div class="s">{escape(s)}</div></div></div>
<ul class="sq"><li>반도체 소부장(소재·부품·장비)이 무더기로 신고가를 내며 급등하는데 대장주(하이닉스·삼성)는 이미 빠지는 모양을 찾습니다.</li>
<li>2026년 10월: 9/4~10/6 소부장 약 +35%, 10/1 신고가 23종목. 하이닉스는 10/2부터 하락. 10/7에 스위치가 켜졌고, 이슈 없이 10/14 -6.5%·10/15 -14.5% 되밀렸습니다.</li>
<li>예측이 아니라 <b>대응 스위치</b>입니다. 과거 {st["n"]}번 켜져 {st["hit"]}번 맞았고 {st["n"] - st["hit"]}번은 빗나갔습니다.</li></ul>
</div>{kd}</div>{pf(1)}</section>

<section class="pg"><h2>오늘의 조건 점검</h2><div class="tw"><table class="chk"><tr><th></th><th>조건</th><th>지금</th><th>기준</th></tr>{rows}</table></div>
<p class="note">4개가 모두 맞으면 켜지고, 그 뒤 {HOLD}거래일 동안 '켜짐 유지'로 둡니다. 3개면 주의.</p>{pf(2)}</section>

<section class="pg"><h2>켜지면 할 일 (미리 정한 내 규칙)</h2><ul class="sq act">{acts}</ul>
<p class="note">스위치가 켜졌을 때 고민하지 않고 그대로 하기 위해 미리 적어 둔 규칙입니다. 바꾸고 싶으면 말해 주세요.</p>{pf(3)}</section>
{climax_section(r.get("climax") or [], pf(4))}
{earn_section(r.get("earn") or [], pf(5).replace(src, esrc))}

<section class="pg"><h2>소부장 vs 대장 (최근 {len(r["chart"]["d"])}거래일, 첫날 = 100)</h2>{svg(r["chart"])}
<p class="note">노란 선이 오르는데 검은 선이 꺾이고 빨간 칸이 생기면 위험 구간입니다.</p>{pf(6)}</section>

<section class="pg"><h2>과거 성적 ({_d(st["from"])} 이후)</h2>
<div class="stat"><div><b>{st["n"]}번</b><span>스위치가 새로 켜진 횟수</span></div>
<div><b>{st["hit"]}번 ({st["hit"] / st["n"] * 100 if st["n"] else 0:.0f}%)</b><span>한 달 안에 소부장 -{HIT:.0%} 이상 하락</span></div>
<div><b>{st["base_hit"] * 100:.0f}%</b><span>아무 날이나 골랐을 때 같은 확률</span></div>
<div><b>{_p(st["avg"])}</b><span>켜진 뒤 한 달 최대 낙폭 평균 (아무 날 {_p(st["base_avg"])})</span></div></div>
<div class="tw"><table><tr><th>켜진 날</th><th>소부장 30일</th><th>신고가 비율</th><th>대장 고점 대비</th><th>한 달 최대 낙폭</th><th>결과</th></tr>{cases}</table></div>
<p class="note">· 한 달 = 켜진 날 다음 {H}거래일, 최대 낙폭 = 그 안의 가장 낮은 소부장 지수 종가 ÷ 켜진 날 종가 - 1.<br>
· 소부장 지수 = 지금 '반도체와반도체장비' 업종(시가총액 상위 500 안) 종목의 하루 등락률 평균. 지금 명단으로 과거를 계산하므로 그 사이 사라지거나 작아진 종목이 빠져 있습니다(실제보다 좋게 보일 수 있음).<br>
· 기준값(+15%·20%·-5%·-5%)은 2015~2026 자료를 보고 정한 <b>가정</b>입니다. 같은 자료로 정하고 같은 자료로 채점했으므로 앞으로의 적중률은 더 낮을 수 있습니다.</p>{pf(7)}</section>

<section class="pg"><h2>고지사항</h2><p class="note">이 페이지는 공개된 시세 자료로 계산한 참고용 점검표이며, 특정 종목의 매수·매도를 권유하지 않습니다.
과거 성과가 미래 수익을 보장하지 않으며, 신호가 켜지지 않은 채 큰 하락이 오거나 신호가 켜졌는데 오르는 경우도 있습니다. 투자 판단과 결과의 책임은 투자자 본인에게 있습니다.
마지막 계산: {now:%Y-%m-%d %H:%M} KST.</p>{pf(8)}</section>
</div>'''


def build(out, page, now=None):
    """/risk/ 페이지와 risk/state.json 을 만들고 결과 dict(실패하면 None)를 돌려준다."""
    now = now or datetime.now(KST)
    d = out / "risk"
    d.mkdir(parents=True, exist_ok=True)
    mem = members()
    try:
        r = compute(mem)
    except Exception as e:  # 시세를 못 받아도 사이트는 만든다
        print("위험신호 계산 실패:", e)
        r = None
    if r:
        try:
            r["earn"] = earnings(mem, now, r.get("_bars"))
        except Exception as e:
            print("실적 둔화 계산 실패:", e)
            r["earn"] = []
        try:
            nm = dict(LEADERS)
            nm.update(mem)
            r["climax"] = climax_rows(nm, r.get("_bars"))
        except Exception as e:
            print("클라이맥스 계산 실패:", e)
            r["climax"] = []
    if not r:
        (d / "index.html").write_text(page("🚦 위험신호", '<p class="err">시세를 받지 못해 이번에는 계산하지 못했습니다.</p>',
                                           "../", "risk/", "RISK SWITCH", "반도체 소부장 나 홀로 급등 경보"), encoding="utf-8")
        return None
    html = f"<style>{CSS}</style>{body(r, now)}"
    (d / "index.html").write_text(page("🚦 위험신호", html, "../", "risk/", "RISK SWITCH",
                                       f"반도체 소부장 나 홀로 급등 경보 · 기준 {_d(r['asof'])}"), encoding="utf-8")
    st = {k: r[k] for k in ("asof", "level", "n_ok", "lastOn", "since", "src")}
    st["earn_sell"] = [x["n"] for x in r["earn"] if x["lvl"] == "sell"]
    st["earn_ready"] = [x["n"] for x in r["earn"] if x["lvl"] == "ready"]
    st["climax"] = {x["n"]: x["lvl"] for x in r.get("climax") or [] if x["lvl"] in ("sell", "hot")}
    (d / "state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print("위험신호:", r["level"], r["n_ok"], "/ 4, 과거", r["stat"]["n"], "번 중", r["stat"]["hit"], "번")
    return r


def home(r):
    """홈 맨 위 한 줄."""
    if not r:
        return ""
    t, s = lv_text(r)
    bg = {"on": "#C8102E", "hold": "#C8102E", "warn": "#F2A900", "off": "#FAF8F3"}[r["level"]]
    fg = {"on": "#fff", "hold": "#fff", "warn": "#3D3A35", "off": "#3D3A35"}[r["level"]]
    return (f'<a href="risk/" class="sec" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;text-decoration:none;'
            f'background:{bg};color:{fg};border:1px solid #E6E0D2;border-left:6px solid #F2A900;border-radius:10px;padding:9px 12px;'
            f'margin:0 0 12px;font:700 14px/1.4 \'Noto Sans KR\',sans-serif"><span>🚦 소부장 위험신호</span><b style="font-size:15px">{t}</b>'
            f'<span style="font-weight:500;opacity:.85">조건 {r["n_ok"]}/4 · {_d(r["asof"])}</span>'
            + "".join(f'<span style="background:#fff;color:#C8102E;border-radius:6px;padding:1px 7px;font-size:13px">📉 {escape(x["n"])} {EL[x["lvl"]][0]}</span>'
                      for x in r.get("earn") or [] if x["code"] in LEADERS and x["lvl"] in ("sell", "ready"))
            + "".join(f'<span style="background:#fff;color:#C8102E;border-radius:6px;padding:1px 7px;font-size:13px">📈 {escape(x["n"])} 차트 {CLV[x["lvl"]][0]}</span>'
                      for x in r.get("climax") or [] if x["lvl"] in ("sell", "hot")) +
            f'<span style="margin-left:auto;font-weight:800">자세히 →</span></a>')
