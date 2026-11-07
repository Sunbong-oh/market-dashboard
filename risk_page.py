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
import re
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
    return {"asof": ds[-1], "level": level, "checks": ck, "n_ok": n_ok, "since": (i - lastOn) if lastOn >= 0 else None,
            "lastOn": ds[lastOn] if lastOn >= 0 else None, "members": len(mem), "cases": cases,
            "stat": {"n": len(done), "hit": sum(c["mdd"] <= -HIT for c in done),
                     "avg": sum(c["mdd"] for c in done) / len(done) if done else 0,
                     "base_hit": sum(x <= -HIT for x in base) / len(base), "base_avg": sum(base) / len(base),
                     "from": ds[START]},
            "chart": {"d": [ds[j] for j in tail], "S": [S[j] for j in tail], "L": [L[j] for j in tail],
                      "on": [on[j] for j in tail], "nh": [NH[j] for j in tail]}}


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
    src = f"자료: 네이버 증권 일봉(소부장 {r['members']}종목·SK하이닉스·삼성전자), 기준 {_d(r['asof'])} (장중이면 잠정) · 계산 Brian's 투자노트"
    pf = lambda n: f'<div class="pf"><span>{escape(src)}</span><span>{n}</span></div>'
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

<section class="pg"><h2>소부장 vs 대장 (최근 {len(r["chart"]["d"])}거래일, 첫날 = 100)</h2>{svg(r["chart"])}
<p class="note">노란 선이 오르는데 검은 선이 꺾이고 빨간 칸이 생기면 위험 구간입니다.</p>{pf(4)}</section>

<section class="pg"><h2>과거 성적 ({_d(st["from"])} 이후)</h2>
<div class="stat"><div><b>{st["n"]}번</b><span>스위치가 새로 켜진 횟수</span></div>
<div><b>{st["hit"]}번 ({st["hit"] / st["n"] * 100 if st["n"] else 0:.0f}%)</b><span>한 달 안에 소부장 -{HIT:.0%} 이상 하락</span></div>
<div><b>{st["base_hit"] * 100:.0f}%</b><span>아무 날이나 골랐을 때 같은 확률</span></div>
<div><b>{_p(st["avg"])}</b><span>켜진 뒤 한 달 최대 낙폭 평균 (아무 날 {_p(st["base_avg"])})</span></div></div>
<div class="tw"><table><tr><th>켜진 날</th><th>소부장 30일</th><th>신고가 비율</th><th>대장 고점 대비</th><th>한 달 최대 낙폭</th><th>결과</th></tr>{cases}</table></div>
<p class="note">· 한 달 = 켜진 날 다음 {H}거래일, 최대 낙폭 = 그 안의 가장 낮은 소부장 지수 종가 ÷ 켜진 날 종가 - 1.<br>
· 소부장 지수 = 지금 '반도체와반도체장비' 업종(시가총액 상위 500 안) 종목의 하루 등락률 평균. 지금 명단으로 과거를 계산하므로 그 사이 사라지거나 작아진 종목이 빠져 있습니다(실제보다 좋게 보일 수 있음).<br>
· 기준값(+15%·20%·-5%·-5%)은 2015~2026 자료를 보고 정한 <b>가정</b>입니다. 같은 자료로 정하고 같은 자료로 채점했으므로 앞으로의 적중률은 더 낮을 수 있습니다.</p>{pf(5)}</section>

<section class="pg"><h2>고지사항</h2><p class="note">이 페이지는 공개된 시세 자료로 계산한 참고용 점검표이며, 특정 종목의 매수·매도를 권유하지 않습니다.
과거 성과가 미래 수익을 보장하지 않으며, 신호가 켜지지 않은 채 큰 하락이 오거나 신호가 켜졌는데 오르는 경우도 있습니다. 투자 판단과 결과의 책임은 투자자 본인에게 있습니다.
마지막 계산: {now:%Y-%m-%d %H:%M} KST.</p>{pf(6)}</section>
</div>'''


def build(out, page, now=None):
    """/risk/ 페이지와 risk/state.json 을 만들고 결과 dict(실패하면 None)를 돌려준다."""
    now = now or datetime.now(KST)
    d = out / "risk"
    d.mkdir(parents=True, exist_ok=True)
    try:
        r = compute()
    except Exception as e:  # 시세를 못 받아도 사이트는 만든다
        print("위험신호 계산 실패:", e)
        r = None
    if not r:
        (d / "index.html").write_text(page("🚦 위험신호", '<p class="err">시세를 받지 못해 이번에는 계산하지 못했습니다.</p>',
                                           "../", "risk/", "RISK SWITCH", "반도체 소부장 나 홀로 급등 경보"), encoding="utf-8")
        return None
    html = f"<style>{CSS}</style>{body(r, now)}"
    (d / "index.html").write_text(page("🚦 위험신호", html, "../", "risk/", "RISK SWITCH",
                                       f"반도체 소부장 나 홀로 급등 경보 · 기준 {_d(r['asof'])}"), encoding="utf-8")
    (d / "state.json").write_text(json.dumps({k: r[k] for k in ("asof", "level", "n_ok", "lastOn", "since")}, ensure_ascii=False), encoding="utf-8")
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
            f'<span style="margin-left:auto;font-weight:800">자세히 →</span></a>')
