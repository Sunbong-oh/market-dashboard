"""나만의 주식투자 사이트(GitHub Pages) 생성기.

실행: python build_site.py  ->  _site/ 폴더에 정적 사이트 생성 (GitHub Actions site.yml이 배포)

메뉴
  /             홈: 세 가지 리포트의 최신 요약
  /daily/       오전 데일리 (미국 데일리 마켓) — archive/daily/YYYY-MM-DD/ (daily-dashboard.yml이 매일 저장)
  /news/        돈이 되는 뉴스 — 빌드할 때마다 Google 뉴스에서 새로 수집 (dashboard.py의 뉴스 로직 재사용)
  /close/       장마감 리포트 (국내 장마감 수급체크) — kb-market-report 저장소의 archive/ (환경변수 CLOSE_REPO)
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime
from html import escape, unescape
from pathlib import Path

import dashboard as d

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("SITE_OUT", ROOT / "_site"))
DAILY = ROOT / "archive" / "daily"
CLOSE = Path(os.environ.get("CLOSE_REPO", ROOT.parent / "kb-market-report")) / "archive"
SITE_NAME = "나의 주식투자 노트"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WD = "월화수목금토일"

CSS = """
:root{--bg:#f4f5f7;--card:#fff;--text:#1c2330;--muted:#6b7385;--line:#e3e6ec;--up:#d63c3c;--down:#2f6fdb;
  --accent:#f08c00;--hd1:#ffd43b;--hd2:#ff922b;--hd-text:#2b1a00;--blue:#1c7ed6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;
  --line:#272f3d;--up:#ff5d5d;--down:#5b9bff;--accent:#ffa94d;--hd1:#f59f00;--hd2:#e8590c;--hd-text:#1a0f00;--blue:#4dabf7}}
:root[data-theme=dark]{--bg:#0f131a;--card:#181e28;--text:#e6e9ef;--muted:#8d96a8;--line:#272f3d;--up:#ff5d5d;--down:#5b9bff;
  --accent:#ffa94d;--hd1:#f59f00;--hd2:#e8590c;--hd-text:#1a0f00;--blue:#4dabf7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:'Pretendard','Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;line-height:1.5}
a{color:inherit}
.wrap{max-width:1080px;margin:0 auto;padding:18px 16px 48px}
.top{padding:18px 22px;border-radius:18px;color:var(--hd-text);background:linear-gradient(120deg,var(--hd1),var(--hd2));margin-bottom:18px}
.kicker{font-size:12px;font-weight:800;letter-spacing:.18em;opacity:.7}
h1{margin:2px 0 0;font-size:28px;line-height:1.3}
.top .sub{opacity:.8;font-size:14px;margin-top:4px}
h2{font-size:20px;margin:26px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;align-items:start}
.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.card{display:flex;flex-direction:column;gap:8px;text-decoration:none;transition:transform .12s}
a.card:hover{transform:translateY(-2px);border-color:var(--accent)}
.tag{align-self:flex-start;display:inline-block;font-size:13px;font-weight:800;color:var(--hd-text);background:var(--hd1);padding:2px 12px;border-radius:99px}
.tag.n{background:var(--hd2)}.tag.c{background:var(--blue);color:#fff}
.card h3{margin:0;font-size:20px;line-height:1.35}
.meta{font-size:13px;color:var(--muted)}
.card img{width:100%;border-radius:10px;border:1px solid var(--line)}
.more{margin-top:auto;font-size:14px;font-weight:700;color:var(--accent)}
.items{list-style:none;margin:0;padding:0;counter-reset:i}
.items li{counter-increment:i;position:relative;padding:10px 0 10px 34px;font-size:17px;font-weight:700;line-height:1.45}
.items li+li{border-top:1px solid var(--line)}
.items li:before{content:counter(i);position:absolute;left:0;top:12px;width:24px;height:24px;border-radius:50%;
  background:var(--accent);color:#fff;font-size:13px;font-weight:800;text-align:center;line-height:24px}
.items a{text-decoration:none}.items a:hover{text-decoration:underline}
.src{font-size:12.5px;font-weight:400;color:var(--muted);margin-top:2px}
.card .items li{font-size:15px;padding:7px 0 7px 30px}.card .items li:before{top:9px;width:20px;height:20px;line-height:20px;font-size:12px}
.panel+.panel{margin-top:14px}
.dates{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:0}
.dates a{display:block;padding:8px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);text-decoration:none;font-weight:700;font-variant-numeric:tabular-nums}
.dates a:hover{border-color:var(--accent)}
.report h3{font-size:17px;margin:18px 0 6px;color:var(--accent)}.report h3:first-child{margin-top:0}
.report ul{margin:0;padding-left:20px}.report li{margin:2px 0}.report p{margin:4px 0}
.shots{display:grid;gap:14px;margin-top:14px}.shots img{width:100%;border-radius:12px;border:1px solid var(--line);background:#fff}
.btn{display:inline-block;padding:8px 14px;border-radius:10px;background:var(--accent);color:#fff;font-weight:700;text-decoration:none;margin:4px 6px 0 0}
.btn.ghost{background:var(--card);color:var(--text);border:1px solid var(--line)}
.err{color:var(--muted)}
footer{margin-top:28px;color:var(--muted);font-size:13px}
@media (max-width:520px){h1{font-size:22px}.top{padding:14px 16px}.items li{font-size:16px}}
"""

# 각 리포트 HTML(원본 그대로) 맨 위에 붙이는 메뉴 막대. 원본 스타일과 섞이지 않게 인라인 스타일만 쓴다.
NAV_STYLE = ("position:sticky;top:0;z-index:9999;display:flex;gap:4px;align-items:center;flex-wrap:wrap;"
             "padding:8px 12px;background:#1c2330;font:600 14px/1.2 'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif")
NAV_LINK = "color:#e6e9ef;text-decoration:none;padding:6px 10px;border-radius:8px"
NAV_ON = NAV_LINK + ";background:#f08c00;color:#fff"
MENU = (("", "홈"), ("daily/", "오전 데일리"), ("news/", "돈이 되는 뉴스"), ("close/", "장마감 리포트"))


def nav(root, active):
    links = "".join(f'<a href="{root}{href}" style="{NAV_ON if href == active else NAV_LINK}">{label}</a>'
                    for href, label in MENU)
    return f'<nav style="{NAV_STYLE}"><b style="color:#ffd43b;margin-right:8px">📈 {SITE_NAME}</b>{links}</nav>'


def page(title, body, root, active, kicker="MY STOCK NOTE", sub=""):
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="robots" content="noindex"><style>{CSS}</style></head><body>
{nav(root, active)}<div class="wrap">
<header class="top"><div class="kicker">{kicker}</div><h1>{escape(title)}</h1>{f'<div class="sub">{sub}</div>' if sub else ""}</header>
{body}
<footer>매일 자동으로 업데이트됩니다. 투자 판단의 근거가 아닌 참고용 자료이며, 투자 결과의 책임은 투자자 본인에게 있습니다.</footer>
</div></body></html>'''


SUB_STYLE = ("display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:6px 12px;background:#2b3444;"
             "font:600 13px/1.2 'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#c9d1de")
SUB_LINK = "color:#ffd43b;text-decoration:none;padding:4px 8px;border-radius:6px;border:1px solid #4a5568"


def with_nav(html, root, active, sub=None):
    """원본 리포트 HTML의 <body> 바로 뒤에 메뉴를 넣는다. sub=(설명, [(href, 이름)...])이면 보조 막대도."""
    m = re.search(r"<body[^>]*>", html, re.I)
    bar = nav(root, active)
    if sub:
        text, links = sub
        bar += (f'<div style="{SUB_STYLE}"><span style="margin-right:4px">{escape(text)}</span>'
                + "".join(f'<a href="{h}" style="{SUB_LINK}">{escape(t)}</a>' for h, t in links) + "</div>")
    return html[:m.end()] + bar + html[m.end():] if m else bar + html


def label(day):
    dt = datetime.strptime(day, "%Y-%m-%d")
    return f"{dt:%Y-%m-%d}({WD[dt.weekday()]})"


def dated_dirs(base):
    if not base.is_dir():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir() and DATE_RE.match(p.name)), key=lambda p: p.name, reverse=True)


def news_items(items, limit=None):
    if not items:
        return '<p class="err">관련 뉴스를 찾지 못했습니다.</p>'
    lis = "".join(f'<li><a href="{escape(n["link"])}" target="_blank" rel="noopener">{escape(n["title"])}</a>'
                  f'<div class="src">{escape(n["src"])} · {datetime.fromtimestamp(n["ts"], d.KST):%m/%d %H:%M}</div></li>'
                  for n in items[:limit])
    return f'<ol class="items">{lis}</ol>'


# ---------- 오전 데일리 ----------
def build_daily():
    out = OUT / "daily"
    days = dated_dirs(DAILY)
    for p in days:
        dest = out / p.name
        dest.mkdir(parents=True, exist_ok=True)
        for f in p.iterdir():
            if f.suffix == ".html":
                dest.joinpath(f.name).write_text(with_nav(f.read_text(encoding="utf-8"), "../../", "daily/"),
                                                 encoding="utf-8")
            elif f.is_file():
                shutil.copy(f, dest / f.name)
    rows = "".join(f'<li><a href="{p.name}/">{label(p.name)}'
                   f'{" · 52주 신고가" if (p / "newhighs.html").exists() else ""}</a></li>' for p in days)
    body = (f'<section class="panel"><ul class="dates">{rows}</ul></section>' if days
            else '<p class="err">아직 저장된 오전 데일리가 없습니다. 다음 아침 발송부터 쌓입니다.</p>')
    (out).mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page("오전 데일리 지난 리포트", body, "../", "daily/", "DAILY US MARKET",
                                         "화~토 아침 7시, 미국 장 마감 정리"), encoding="utf-8")
    if not days:
        return None
    p = days[0]
    html = (p / "index.html").read_text(encoding="utf-8") if (p / "index.html").exists() else ""
    m = re.search(r'<a class="headline"[^>]*>(.*?)</a>', html, re.S)
    kr = re.findall(r'<section class="panel kr">.*?</section>', html, re.S)
    kr_titles = re.findall(r'<li><a [^>]*>(.*?)</a>', kr[0], re.S) if kr else []
    return dict(day=p.name, headline=unescape(m.group(1)) if m else "", kr=[unescape(t) for t in kr_titles],
                newhighs=(p / "newhighs.html").exists())


# ---------- 돈이 되는 뉴스 ----------
def theme_news(limit=10):
    """국내 수혜주·관련주·특징주 기사 (종목 추천·부동산 등은 뺀다), 최근 24시간."""
    since = datetime.now(d.KST).timestamp() - 86400
    items = [x for q in d.KR_THEME_QUERIES for x in d.google_news(q)
             if d.KR_THEME.search(x["raw"]) and not d.KR_EXCLUDE.search(x["raw"])
             and x["ts"] >= since and not x["src"].startswith(d.KR_SKIP_SRC)]
    return d.rank(d.market_news(items), limit=limit)


def build_news(now):
    def safe(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # 뉴스 하나가 실패해도 사이트는 만든다
            print("뉴스 수집 실패:", fn.__name__, type(e).__name__, e, file=sys.stderr)
            return []
    kr = safe(d.fetch_kr_news, n=6)  # dashboard.market_news로 주가 관련 기사만 후보에 들어간다
    us = safe(d.fetch_news)
    theme = safe(theme_news)
    cal = d.calendar_events(now)
    cal_html = ""
    if cal:
        lis = "".join(f'<li>{escape(e)}</li>' for e in cal)
        cal_html = f'<section class="panel"><div class="tag c">오늘의 증시 캘린더</div><ol class="items">{lis}</ol></section>'
    body = (f'{cal_html}'
            f'<section class="panel"><div class="tag">오늘 한국 시장에 영향 줄 뉴스</div>'
            f'<p class="meta">직전 한국 장 마감(15:30) 이후 뉴스 중 주가·실적·금리·환율·유가·관세·업종과 직접 관련된 것만,'
            f' 여러 언론이 크게 다룬 순 (정치·사회 기사 제외)</p>{news_items(kr)}</section>'
            f'<section class="panel"><div class="tag n">수혜주 · 관련주 · 특징주</div>'
            f'<p class="meta">최근 24시간, 비슷한 기사는 하나만</p>{news_items(theme)}</section>'
            f'<section class="panel"><div class="tag c">뉴욕증시 헤드라인</div>{news_items(us)}</section>')
    (OUT / "news").mkdir(parents=True, exist_ok=True)
    (OUT / "news" / "index.html").write_text(
        page("돈이 되는 뉴스", body, "../", "news/", "MONEY NEWS",
             f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 수집 · 하루 여러 번 자동 갱신"), encoding="utf-8")
    return dict(kr=kr, theme=theme, at=now)


# ---------- 장마감 리포트 ----------
IMG_ORDER = ("1_시장", "2_수급", "3_강세테마", "3_강세업종")


def report_text(txt):
    """블로그 본문(■ 제목 / - 항목 / 문장)을 HTML로."""
    out, ul = [], []

    def flush():
        if ul:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in ul) + "</ul>")
            ul.clear()
    for line in txt.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("■"):
            flush()
            out.append(f"<h3>{escape(s.lstrip('■ '))}</h3>")
        elif s.startswith("- ") or re.match(r"^\d+\. ", s):
            ul.append(escape(s[2:] if s.startswith("- ") else s))
        else:
            flush()
            out.append(f"<p>{escape(s)}</p>")
    flush()
    return "".join(out)


def build_close():
    out = OUT / "close"
    days = dated_dirs(CLOSE)
    first = None
    for p in days:
        dest = out / p.name
        dest.mkdir(parents=True, exist_ok=True)
        title = (p / "제목_장마감수급.txt").read_text(encoding="utf-8").strip() if (p / "제목_장마감수급.txt").exists() \
            else f"{p.name} 국내 장마감 수급 체크"
        body_txt = (p / "본문_장마감수급.txt").read_text(encoding="utf-8") if (p / "본문_장마감수급.txt").exists() else ""
        lines = body_txt.strip().splitlines()
        if lines and lines[0].strip() == title:
            lines = lines[1:]
        imgs = []
        for name in IMG_ORDER:
            if (p / f"{name}.jpg").exists():
                shutil.copy(p / f"{name}.jpg", dest / f"{name}.jpg")
                imgs.append(name)
            if name == "3_강세테마" and imgs and imgs[-1] == name:
                break  # 예전 이름(3_강세업종)은 새 이름이 없을 때만
        # 기본 화면은 차트(인터랙티브) 리포트, 글 요약은 summary.html
        chart = (p / "장마감 수급체크.html").exists()
        text_page = "summary.html" if chart else "index.html"
        btn = '<a class="btn" href="./">차트로 보기</a>' if chart else ""
        if chart:
            html = (p / "장마감 수급체크.html").read_text(encoding="utf-8")
            (dest / "index.html").write_text(
                with_nav(html, "../../", "close/", (label(p.name), [("summary.html", "글 요약 보기"), ("../", "지난 리포트")])),
                encoding="utf-8")
            (dest / "interactive.html").write_text(  # 예전 주소 호환
                '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=./"><a href="./">이동</a>',
                encoding="utf-8")
        summary = next((ln.split(":", 1)[1].strip() for ln in lines if "한 줄 요약" in ln and ":" in ln), "")
        shots = "".join(f'<img src="{n}.jpg" alt="{n.split("_", 1)[1]}" loading="lazy">' for n in imgs)
        body = (f'<section class="panel report">{btn}<a class="btn ghost" href="../">지난 리포트</a>'
                f'<div style="margin-top:14px">{report_text(chr(10).join(lines))}</div></section>'
                f'<div class="shots">{shots}</div>')
        (dest / text_page).write_text(page(title, body, "../../", "close/", "KOREA MARKET CLOSE",
                                              f"{label(p.name)} 장 마감 후 자동 작성 · 데이터: KB증권 OpenAPI"),
                                         encoding="utf-8")
        if first is None:
            first = dict(day=p.name, title=title, summary=summary, img=f"close/{p.name}/{imgs[0]}.jpg" if imgs else "")
    rows = "".join(f'<li><a href="{p.name}/">{label(p.name)}</a></li>' for p in days)
    body = (f'<section class="panel"><ul class="dates">{rows}</ul></section>' if days
            else '<p class="err">장마감 리포트를 불러오지 못했습니다.</p>')
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page("장마감 리포트 지난 리포트", body, "../", "close/", "KOREA MARKET CLOSE",
                                         "평일 오후 4시경, 국내 장마감 수급 체크"), encoding="utf-8")
    return first


# ---------- 홈 ----------
def build_home(now, daily, news, close):
    if daily:
        kr = "".join(f"<li>{escape(t)}</li>" for t in daily["kr"][:2])
        c1 = (f'<a class="card" href="daily/{daily["day"]}/"><span class="tag">오전 데일리</span>'
              f'<h3>{escape(daily["headline"] or "미국 데일리 마켓")}</h3><div class="meta">{label(daily["day"])} 아침 7시'
              f'{" · 52주 신고가 포함" if daily["newhighs"] else ""}</div>'
              f'{f"<ol class=items>{kr}</ol>" if kr else ""}<span class="more">리포트 보기 →</span></a>')
    else:
        c1 = ('<a class="card" href="daily/"><span class="tag">오전 데일리</span><h3>미국 데일리 마켓</h3>'
              '<div class="meta">다음 아침 발송부터 표시됩니다.</div><span class="more">지난 리포트 →</span></a>')
    top = "".join(f"<li>{escape(n['title'])}</li>" for n in (news["kr"] or news["theme"])[:3])
    c2 = (f'<a class="card" href="news/"><span class="tag n">돈이 되는 뉴스</span><h3>지금 시장을 움직이는 뉴스</h3>'
          f'<div class="meta">{news["at"]:%m/%d %H:%M} 수집</div>'
          f'<ol class="items">{top or "<li>뉴스 없음</li>"}</ol>'
          f'<span class="more">뉴스 전체 보기 →</span></a>')
    if close:
        img = f'<img src="{close["img"]}" alt="장마감 시장 요약" loading="lazy">' if close["img"] else ""
        c3 = (f'<a class="card" href="close/{close["day"]}/"><span class="tag c">장마감 리포트</span>'
              f'<h3>{escape(close["summary"] or close["title"])}</h3><div class="meta">{escape(close["title"])}</div>'
              f'{img}<span class="more">리포트 보기 →</span></a>')
    else:
        c3 = ('<a class="card" href="close/"><span class="tag c">장마감 리포트</span><h3>국내 장마감 수급 체크</h3>'
              '<div class="meta">리포트를 불러오지 못했습니다.</div><span class="more">지난 리포트 →</span></a>')
    body = f'<div class="grid">{c1}{c2}{c3}</div>'
    (OUT / "index.html").write_text(page(SITE_NAME, body, "", "", "MY STOCK NOTE",
                                         f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 업데이트"),
                                    encoding="utf-8")


def main():
    now = datetime.now(d.KST)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / ".nojekyll").write_text("")
    daily = build_daily()
    news = build_news(now)
    close = build_close()
    build_home(now, daily, news, close)
    print(json.dumps({"out": str(OUT), "daily": daily and daily["day"], "close": close and close["day"],
                      "news": [len(news["kr"]), len(news["theme"])]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
