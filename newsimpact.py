"""글로벌 뉴스 · 종목 영향 패널. dashboard.py의 요약 이미지(part a)에 '오늘 한국 시장 영향' 아래로 붙는다.

- 후보: 직전 한국 장 마감(15:30 KST) 이후의 글로벌 이슈 기사(Google 뉴스 한국어 검색)
- 각 기사를 테마(반도체·유가·금리·환율 …) 하나에 묶고, 테마별 미국 연관 지표의 간밤 등락을 함께 보여준다
- 국내 연관 종목의 방향(▲/▼)은 '연관 지표 등락 × 종목과 지표의 관계'로 정한다.
  연관 지표가 없거나 거의 안 움직였으면 기사 제목의 논조(급등/급락 등)로 정하고, 그것도 없으면 '–'
- 방향은 추정치다(패널에 그렇게 표시). 종목과 관계는 THEMES 표에서 고친다.
단독 실행: python newsimpact.py  ->  newsimpact.html (패널만 미리보기)
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape

import dashboard as d

N_NEWS = 3          # 패널에 싣는 기사 수(요약 이미지가 길어지지 않게 3건, 한 건당 두 줄)
FLAT_MOVE = 0.3     # 연관 지표가 이보다 적게(%) 움직이면 '보합'으로 보고 기사 논조로 방향을 정한다

GLOBAL_QUERIES = ("해외증시 when:1d", "월가 when:1d", "글로벌 경제 when:1d", "미국 경제 when:1d", "중국 경제 when:1d",
                  "연준 when:1d", "국제유가 when:1d", "반도체 when:1d", "환율 when:1d", "관세 when:1d",
                  "배터리 when:1d", "방산 when:1d", "원전 when:1d", "바이오 when:1d")

# (테마, 제목 패턴, 연관 지표(야후 티커, 표시명) 또는 None, [(국내 종목, 관계)])
# 관계 +1: 지표(또는 기사 논조)와 같은 방향, -1: 반대 방향. 위에 있는 테마가 먼저 걸린다.
THEMES = (
    ("반도체", r"반도체|HBM|메모리|D램|디램|낸드|마이크론|TSMC|파운드리|AI ?칩|엔비디아",
     ("^SOX", "SOX"), (("삼성전자", 1), ("SK하이닉스", 1), ("한미반도체", 1))),
    ("유가", r"유가|원유|석유|정유|브렌트|WTI|OPEC|산유국",
     ("CL=F", "WTI"), (("S-Oil", 1), ("SK이노", 1), ("대한항공", -1))),
    ("금리", r"국채 ?금리|연준|Fed|FOMC|파월|기준금리|금리 ?(인하|인상|동결)",
     ("^TNX", "美10년"), (("KB금융", 1), ("신한지주", 1), ("NAVER", -1))),
    ("환율", r"환율|원·?달러|원화|강달러|약달러|달러 ?(강세|약세)",
     ("KRW=X", "원/달러"), (("현대차", 1), ("기아", 1), ("대한항공", -1))),
    ("2차전지", r"2차전지|이차전지|배터리|리튬|전기차",
     ("LIT", "리튬 ETF"), (("LG엔솔", 1), ("삼성SDI", 1), ("에코프로비엠", 1))),
    ("원전", r"원전|원자력|SMR|우라늄",
     ("URA", "우라늄 ETF"), (("두산에너빌", 1), ("한전기술", 1), ("현대건설", 1))),
    ("방산", r"방산|국방|무기|미사일|전쟁|휴전|파병|공습|나토|NATO",
     ("ITA", "美방산 ETF"), (("한화에어로", 1), ("LIG넥스원", 1), ("현대로템", 1))),
    ("조선", r"조선|선박|LNG선|해운|마스가|MASGA",
     None, (("HD한국조선", 1), ("한화오션", 1), ("삼성중공업", 1))),
    ("바이오", r"바이오|제약|신약|FDA|비만약|비만 치료제|임상",
     ("XBI", "美바이오 ETF"), (("삼성바이오", 1), ("셀트리온", 1), ("알테오젠", 1))),
    ("금", r"금값|금 ?가격|금 ?선물|안전자산",
     ("GC=F", "금"), (("고려아연", 1), ("풍산", 1))),
    ("자동차", r"자동차|완성차|관세|테슬라",
     None, (("현대차", 1), ("기아", 1), ("현대모비스", 1))),
    ("AI·빅테크", r"AI|인공지능|오픈AI|챗GPT|데이터센터|빅테크|클라우드",
     ("^IXIC", "나스닥"), (("NAVER", 1), ("카카오", 1), ("LS ELECTRIC", 1))),
    ("중국", r"중국|中|시진핑|위안화|홍콩|항셍",
     ("FXI", "中대형주 ETF"), (("아모레퍼시픽", 1), ("LG생활건강", 1), ("호텔신라", 1))),
)
THEMES = tuple((k, re.compile(p), px, st) for k, p, px, st in THEMES)

TONE_UP = re.compile(r"급등|상승|강세|호조|호실적|반등|돌파|사상 ?최고|최고치|급증|증가|확대|상향|흑자|수혜|훈풍|날개|껑충|↑")
TONE_DOWN = re.compile(r"급락|하락|약세|부진|감소|축소|중단|금지|제재|우려|쇼크|하향|적자|둔화|충격|폭락|타격|악재|먹구름|↓")


def theme_of(title):
    return next((t for t in THEMES if t[1].search(title)), None)


def tone(title):
    """기사 제목 논조: +1(호재 표현만), -1(악재 표현만), 0(없거나 섞임)."""
    up, down = bool(TONE_UP.search(title)), bool(TONE_DOWN.search(title))
    return 1 if up and not down else -1 if down and not up else 0


def collect(now_ts=None, exclude=()):
    """직전 한국 장 마감 이후 글로벌 이슈 기사 중 화제가 된 순으로 N_NEWS개(테마가 겹치지 않게).
    exclude(이미 '오늘 한국 시장 영향'에 실린 기사)와 같은 기사는 뺀다."""
    end = now_ts or datetime.now(timezone.utc).timestamp()
    start = d.last_kr_close(end)
    with ThreadPoolExecutor(max_workers=8) as ex:
        feeds = list(ex.map(d.google_news, GLOBAL_QUERIES))
    pool = {x["link"]: x for f in feeds for x in f
            if start <= x["ts"] <= end and not x["src"].startswith(d.KR_SKIP_SRC)}
    pool = list(pool.values())
    cands = []
    for c in pool:
        th = theme_of(c["title"])
        if not th or d.KR_EXCLUDE.search(c["raw"]) or d.KR_RECAP.search(c["raw"]):
            continue
        g = d._grams(c["title"])
        heat = sum(1 for m in pool if m["link"] != c["link"] and len(g & d._grams(m["title"])) >= 4)
        shock = min(len({m.group(0) for m in d.KR_SHOCK.finditer(c["title"])}), 2)
        cands.append(dict(c, theme=th, heat=heat, score=(heat + 1) * (1 + d.KR_SHOCK_WEIGHT * shock), shock=shock > 0))
    cands.sort(key=lambda c: (-c["score"], -c["ts"]))
    seen = [d._grams(x["title"]) for x in exclude]
    picked = []
    for c in cands:
        if len(picked) >= N_NEWS:
            break
        g = d._grams(c["title"])
        if not (c["heat"] >= 1 or c["shock"]) or any(len(g & s) >= 4 for s in seen):
            continue
        if any(p["theme"][0] == c["theme"][0] for p in picked):
            continue
        picked.append(c)
        seen.append(g)
    return picked


def proxy_moves(news, quotes=()):
    """{티커: (전일 대비 %, 표시 문자열)} — 대시보드가 이미 받아 둔 시세는 다시 받지 않는다. 금리는 bp로 표시."""
    have = {q["sym"]: q for q in quotes if q.get("ok")}
    need = sorted({n["theme"][2][0] for n in news if n["theme"][2]} - set(have))
    with ThreadPoolExecutor(max_workers=6) as ex:
        for q in ex.map(d.fetch_quote, [("", s, "price", "", "") for s in need]):
            if q["ok"]:
                have[q["sym"]] = q
    out = {}
    for s, q in have.items():
        last, prev = q["pts"][-1][1], q["pts"][-2][1]
        pct = (last / prev - 1) * 100
        out[s] = (pct, f"{(last - prev) * 100:+.1f}bp" if s == "^TNX" else f"{pct:+.2f}%")
    return out


def impact(n, moves):
    """(지표 등락 % 또는 None, 방향 +1/-1/0, 근거 '지표'/'논조'/'')"""
    px = n["theme"][2]
    mv = (moves.get(px[0]) or (None,))[0] if px else None
    if mv is not None and abs(mv) >= FLAT_MOVE:
        return mv, 1 if mv > 0 else -1, "지표"
    t = tone(n["title"])
    return mv, t, "논조" if t else ""


def _arrow(sign):
    return ('<b class="up">▲</b>' if sign > 0 else '<b class="down">▼</b>' if sign < 0
            else '<b class="flat">–</b>')


def row(n, moves):
    """한 건 = 두 줄: [테마] 기사 제목(한 줄로 자름) / 연관 지표 등락 · 종목▲▼"""
    key, _, px, stocks = n["theme"]
    mv, sign, _ = impact(n, moves)
    proxy = ""
    if px:
        val = (f'<b class="{d.cls(mv)}">{moves[px[0]][1]}</b>' if mv is not None
               else '<b class="flat">–</b>')
        proxy = f'<span class="ni-px">{escape(px[1])} {val}</span>'
    sts = "".join(f'<span class="ni-st">{escape(name)}{_arrow(sign * rel)}</span>' for name, rel in stocks)
    return (f'<li><div class="ni-h"><span class="ni-th">{escape(key)}</span>'
            f'<a href="{escape(n["link"])}" target="_blank" rel="noopener">{escape(n["title"])}</a></div>'
            f'<div class="ni-sts">{proxy}{sts}</div></li>')


def block(news, moves):
    if not news:
        return ""
    lis = "".join(row(n, moves) for n in news)
    return (f'<section class="panel ni"><div class="tag">글로벌 뉴스 · 종목 영향</div>'
            f'<ul class="ni-list">{lis}</ul>'
            f'<div class="ni-note">▲▼ 연관 지표 간밤 등락(없으면 기사 논조) 기준 추정</div></section>')


def build(quotes=(), exclude=(), now_ts=None):
    """대시보드에 넣을 패널 HTML. 실패하거나 실을 기사가 없으면 빈 문자열(데일리 발송은 그대로 진행)."""
    try:
        news = collect(now_ts, exclude)
        return block(news, proxy_moves(news, quotes))
    except Exception as e:
        print("뉴스·종목 영향 섹션 실패:", type(e).__name__, e, file=sys.stderr)
        return ""


if __name__ == "__main__":
    from pathlib import Path
    out = Path(__file__).with_name("newsimpact.html")
    out.write_text(f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{d.CSS}</style></head>'
                   f'<body><div class="wrap">{build()}</div></body></html>', encoding="utf-8")
    print("생성 완료:", out)
