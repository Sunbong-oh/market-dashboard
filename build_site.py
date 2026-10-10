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
import subprocess
import sys
from datetime import datetime
from html import escape, unescape
from pathlib import Path

import dashboard as d

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("SITE_OUT", ROOT / "_site"))
DAILY = ROOT / "archive" / "daily"
CLOSE = Path(os.environ.get("CLOSE_REPO", ROOT.parent / "kb-market-report")) / "archive"
SITE_NAME = "Brian's 투자노트"
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


APP_NAME = "Brian's 투자노트"  # 홈 화면 아이콘 아래 이름
# 이름·아이콘을 바꾸면 파일 이름도 바꾼다(폰 브라우저가 예전 manifest를 캐시에서 다시 쓰지 않게)
MANIFEST = "app-brian.webmanifest"


def head_tags(root):
    """홈 화면에 앱처럼 설치되도록 하는 manifest·아이콘 태그."""
    return (f'<link rel="manifest" href="{root}{MANIFEST}"><meta name="theme-color" content="#1c2330">'
            f'<link rel="icon" href="{root}assets/icon-192.png"><link rel="apple-touch-icon" href="{root}assets/apple-touch-icon.png">'
            f'<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">'
            f'<meta name="apple-mobile-web-app-title" content="{APP_NAME}">')


def write_app_files():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    manifest = {"name": SITE_NAME, "short_name": APP_NAME, "lang": "ko", "start_url": "./", "scope": "./",
                "display": "standalone", "background_color": "#f4f5f7", "theme_color": "#1c2330",
                "icons": [{"src": "assets/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                          {"src": "assets/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
    (OUT / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def page(title, body, root, active, kicker="MY STOCK NOTE", sub="", hero=True):
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="robots" content="noindex">{head_tags(root)}<style>{CSS}</style></head><body>
{nav(root, active)}<div class="wrap">
{f'''<header class="top"><div class="kicker">{kicker}</div><h1>{escape(title)}</h1>{f'<div class="sub">{sub}</div>' if sub else ""}</header>''' if hero else ""}
{body}
<footer>매일 자동으로 업데이트됩니다. 투자 판단의 근거가 아닌 참고용 자료이며, 투자 결과의 책임은 투자자 본인에게 있습니다.</footer>
</div></body></html>'''


SUB_STYLE = ("display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:6px 12px;background:#2b3444;"
             "font:600 13px/1.2 'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#c9d1de")
SUB_LINK = "color:#ffd43b;text-decoration:none;padding:4px 8px;border-radius:6px;border:1px solid #4a5568"


def with_nav(html, root, active, sub=None):
    """원본 리포트 HTML의 <body> 바로 뒤에 메뉴를 넣는다. sub=(설명, [(href, 이름)...])이면 보조 막대도."""
    html = re.sub(r"</head>", lambda _: head_tags(root) + "</head>", html, count=1, flags=re.I)
    m = re.search(r"<body[^>]*>", html, re.I)
    bar = nav(root, active)
    if sub:
        text, links = sub
        bar += (f'<div style="{SUB_STYLE}"><span style="margin-right:4px">{escape(text)}</span>'
                + "".join(f'<a href="{h}" style="{SUB_LINK}">{escape(t)}</a>' for h, t in links) + "</div>")
    return html[:m.end()] + bar + html[m.end():] if m else bar + html


# 데일리의 '주요 지표' 12개를 폰에서도 텔레그램처럼 3열 4줄로: 600px 폭 3열로 배치한 뒤 화면 폭에 맞게 축소
GRID3 = """<style>.panel.kr{display:none!important}  /* 사이트에서는 '돈이 되는 뉴스'와 겹쳐 뺀다 */
@media (max-width:640px){
.grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}
.g3 .card{padding:11px 11px 10px!important;border-radius:12px}
.g3 .card header{flex-direction:column;align-items:flex-start;gap:0}
.g3 .card h3{font-size:18px!important}.g3 .sym{font-size:12px!important}
.g3 .price{font-size:27px!important;margin-top:4px}.g3 .price small{font-size:15px!important}
.g3 .badge{font-size:12px!important;padding:1px 6px!important}.g3 .delta{font-size:15px!important}
.g3 .spark{height:46px!important;margin-top:6px}
.g3 .range,.g3 .range-cap{display:none!important}
.g3 .chips{gap:2px!important;margin-top:8px}.g3 .chip{padding:4px 3px!important;font-size:12px!important;border-radius:6px;overflow:hidden}
.g3 .chip b{font-size:13px!important;letter-spacing:-.04em}.g3 .chip small{display:none!important}}</style>
<script>(function(){function f(){var g=document.querySelector('.grid');if(!g)return;g.classList.add('g3');
if(innerWidth<=640){g.style.width='600px';g.style.zoom=(g.parentElement.clientWidth/600)}else{g.style.width='';g.style.zoom=''}}
addEventListener('DOMContentLoaded',f);addEventListener('resize',f)})()</script>"""


def daily_grid3(html):
    i = html.lower().rfind("</body>")
    return html[:i] + GRID3 + html[i:] if i >= 0 else html + GRID3


def embed_html(html):
    """홈 화면에 통째로 끼워 넣을 원본 리포트 (메뉴 없이, 링크는 바깥 창에서 열림)."""
    tag = '<base target="_top">'
    m = re.search(r"<head[^>]*>", html, re.I)
    return html[:m.end()] + tag + html[m.end():] if m else tag + html


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
                dest.joinpath(f.name).write_text(with_nav(daily_grid3(f.read_text(encoding="utf-8")), "../../", "daily/"),
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
    if html:
        (out / p.name / "embed.html").write_text(embed_html(daily_grid3(html)), encoding="utf-8")
    return dict(day=p.name, headline=unescape(m.group(1)) if m else "", kr=[unescape(t) for t in kr_titles],
                embed=f"daily/{p.name}/embed.html" if html else "",
                newhighs=(p / "newhighs.html").exists())


# ---------- 실시간 시세 (밤 22:00~02:00 KST, 10분마다) ----------
LIVE_START, LIVE_END = 22, 2  # KST 시


def live_window(now):
    return now.hour >= LIVE_START or now.hour < LIVE_END or (now.hour == LIVE_END and now.minute <= 10)


def build_live(now):
    """미국 장중에는 데일리 대시보드를 지금 시세로 새로 만든다 (live-prices.yml이 10분마다 호출)."""
    if os.environ.get("LIVE") != "1" and not live_window(now):
        return None
    try:
        subprocess.run([sys.executable, "dashboard.py", "--no-open"], cwd=ROOT, check=True, timeout=600)
        html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    except Exception as e:
        print("실시간 시세 생성 실패:", type(e).__name__, e, file=sys.stderr)
        return None
    dest = OUT / "daily" / "live"
    dest.mkdir(parents=True, exist_ok=True)
    html = daily_grid3(html)
    (dest / "index.html").write_text(with_nav(html, "../../", "daily/"), encoding="utf-8")
    (dest / "embed.html").write_text(embed_html(html), encoding="utf-8")
    return dict(at=now, embed="daily/live/embed.html")


# ---------- 돈이 되는 뉴스 ----------
def theme_news(limit=10):
    """국내 수혜주·관련주·특징주 기사 (종목 추천·부동산 등은 뺀다), 최근 24시간."""
    since = datetime.now(d.KST).timestamp() - 86400
    items = [x for q in d.KR_THEME_QUERIES for x in d.google_news(q)
             if d.KR_THEME.search(x["raw"]) and not d.KR_EXCLUDE.search(x["raw"])
             and x["ts"] >= since and not x["src"].startswith(d.KR_SKIP_SRC)]
    return d.rank(d.market_news(items), limit=limit)


# ---------- 관심 테마 뉴스 (Claude 루틴이 일~목 21:00에 theme_news/<발송일>.html 커밋) ----------
THEME_ARCHIVE = ROOT / "archive" / "theme"
INDEX_KPI = re.compile(r"나스닥|다우|S&P|코스피|코스닥|러셀|SOX|필라델피아|반도체지수|지수")


def build_theme():
    """가장 최근 테마 뉴스 카드(4장)를 사이트에 넣는다. theme_news/ 와 archive/theme/ 중 최신 날짜."""
    files = {}
    for folder in (THEME_ARCHIVE, d.THEME_DIR):
        if folder.is_dir():
            for f in folder.glob("*.html"):
                if DATE_RE.match(f.stem):
                    files[f.stem] = f
    if not files:
        return None
    day = max(files)
    (OUT / "theme").mkdir(parents=True, exist_ok=True)
    html = files[day].read_text(encoding="utf-8")
    # 카드는 540px 고정 폭이라 화면 폭에 맞춰 늘고 줄게 바꾸고, 지수 등락 박스(나스닥 등)는 뺀다
    fit = ("<style>html,body{margin:0!important;overflow:hidden}.card{width:auto!important;max-width:540px;margin:0 auto 12px!important}"
           "@media (max-width:420px){.card{padding:16px 14px 12px!important}h1{font-size:23px!important}.t{font-size:17px!important}"
           ".p{font-size:17px!important}.w{font-size:15px!important}.kpi .v{font-size:24px!important}}</style>")
    html = html.replace("</head>", fit + "</head>", 1) if "</head>" in html else fit + html
    html = re.sub(r'<div class="kpi"><div><div class="n">([^<]*)</div>.*?<div class="v[^"]*">[^<]*</div></div>',
                  lambda m: "" if INDEX_KPI.search(m.group(1)) else m.group(0), html)
    (OUT / "theme" / f"{day}.html").write_text(embed_html(html), encoding="utf-8")
    return dict(day=day, path=f"theme/{day}.html")


def theme_block(theme, root):
    if not theme:
        return ""
    return (f'<section class="panel"><div class="tag">관심 테마 뉴스</div>'
            f'<p class="meta">AI 밸류체인 · 메가테크 · 모빌리티·에너지 — 전날 밤 21시 작성 ({label(theme["day"])})</p>'
            f'<iframe class="embed" scrolling="no" src="{root}{theme["path"]}" title="관심 테마 뉴스" loading="lazy"></iframe></section>')


def build_news(now, theme_doc=None):
    def safe(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # 뉴스 하나가 실패해도 사이트는 만든다
            print("뉴스 수집 실패:", fn.__name__, type(e).__name__, e, file=sys.stderr)
            return []
    kr = safe(d.fetch_kr_news, n=6)  # dashboard.market_news로 주가 관련 기사만 후보에 들어간다
    theme = safe(theme_news)
    body = (f'{theme_block(theme_doc, "")}'
            f'<section class="panel"><div class="tag">오늘 한국 시장에 영향 줄 뉴스</div>'
            f'<p class="meta">직전 한국 장 마감(15:30) 이후 뉴스 중 주가·실적·금리·환율·유가·관세·업종과 직접 관련된 것만,'
            f' 여러 언론이 크게 다룬 순 (정치·사회 기사 제외)</p>{news_items(kr)}</section>'
            f'<section class="panel"><div class="tag n">수혜주 · 관련주 · 특징주</div>'
            f'<p class="meta">최근 24시간 · 주가 등락 나열, 칼럼·종목 추천성 기사 제외</p>{news_items(theme)}</section>')
    (OUT / "news").mkdir(parents=True, exist_ok=True)
    news_page_body = (body.replace(f'src="{theme_doc["path"]}"', f'src="../{theme_doc["path"]}"')
                      if theme_doc else body)
    (OUT / "news" / "index.html").write_text(
        page("돈이 되는 뉴스", f'<style>{HOME_CSS}</style>' + news_page_body + FIT_JS, "../", "news/", "MONEY NEWS",
             f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 수집 · 하루 여러 번 자동 갱신"), encoding="utf-8")
    return dict(kr=kr, theme=theme, at=now, body=body)


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


# 차트 리포트에 이미 있는 항목(지수·수급·선물옵션·강세 테마·등락 종목수)은 빼고, 나머지(실적·이슈·일정·한 줄 요약)만 차트 아래에 붙인다
CHART_HAS = ("지수", "투자자별", "선물", "강세 테마", "등락 종목")
EXTRA_CSS = """<style>
.site-extra{max-width:1180px;margin:0 auto 24px;padding:0 16px;font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#1c2330}
.site-extra .box{background:#fff;border:1px solid #e3e6ec;border-radius:14px;padding:16px 18px;margin-top:14px}
.site-extra h3{font-size:17px;margin:16px 0 6px;color:#e8590c}.site-extra h3:first-child{margin-top:0}
.site-extra ul{margin:0;padding-left:20px;line-height:1.55}.site-extra p{margin:6px 0;line-height:1.55}
.site-extra .one{font-size:17px;font-weight:800;background:#fff4e6;border-radius:10px;padding:10px 12px;margin-top:12px}
.site-extra .dates{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:8px 0 0}
.site-extra .dates a{display:block;padding:7px 12px;border-radius:10px;border:1px solid #e3e6ec;text-decoration:none;color:#1c2330;font-weight:700}
.site-extra .dates a.on{background:#f08c00;border-color:#f08c00;color:#fff}
</style>"""


def close_extra_lines(lines):
    out, keep, one = [], False, ""
    for ln in lines:
        t = ln.strip()
        if t.startswith("■"):
            keep = not any(k in t for k in CHART_HAS)
        elif t.startswith("▶"):
            one = t.lstrip("▶ ").strip()
            keep = False
            continue
        if keep and not t.startswith("(데이터"):
            out.append(ln)
    return out, one


def _tmin(t):
    """'0915' -> 08:45부터 지난 분."""
    t = str(t).zfill(4)
    return (int(t[:2]) * 60 + int(t[2:4])) - (8 * 60 + 45)


def futures_chart(day_dir):
    """회사 PC 서버가 올린 futures_flow.json으로 KOSPI200 선물(좌축)과 외국인 선물 순매수 누적(우축) 교차 차트."""
    f = day_dir / "futures_flow.json"
    if not f.exists():
        return ""
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    bars = [(_tmin(b["t"]), b["c"]) for b in d.get("bars") or [] if b.get("c") is not None and 0 <= _tmin(b["t"]) <= 420]
    flows = [(_tmin(r["t"]), r["외국인"]) for r in d.get("flows") or []
             if r.get("외국인") is not None and 0 <= _tmin(r["t"]) <= 420]
    if len(bars) < 2 or len(flows) < 2:
        return ""
    W, H, L, R, T, B = 640, 320, 92, 548, 20, 270
    x = lambda m: L + (R - L) * m / 420

    def scale(vals, zero=False):
        lo, hi = min(vals), max(vals)
        if zero:
            lo, hi = min(lo, 0), max(hi, 0)
        pad = (hi - lo) * 0.08 or 1
        lo, hi = lo - pad, hi + pad
        return lo, hi, (lambda v: B - (B - T) * (v - lo) / (hi - lo))

    flo, fhi, yf = scale([c for _, c in bars])
    glo, ghi, yg = scale([v for _, v in flows], zero=True)
    path = lambda pts, y: "M" + " L".join(f"{x(m):.1f},{y(v):.1f}" for m, v in pts)
    grid = "".join(f'<line x1="{x(_tmin(t))}" y1="{T}" x2="{x(_tmin(t))}" y2="{B}" stroke="#e3e6ec"/>'
                   f'<text x="{x(_tmin(t))}" y="{B + 26}" text-anchor="middle">{t[:2]}:{t[2:]}</text>'
                   for t in ("0900", "1100", "1300", "1500"))
    zero = (f'<line x1="{L}" y1="{yg(0):.1f}" x2="{R}" y2="{yg(0):.1f}" stroke="#e03131" stroke-dasharray="4 4" opacity=".45"/>'
            + (f'<text x="{R + 6}" y="{yg(0) + 6:.1f}" fill="#e03131">0</text>'
               if T + 36 < yg(0) < B - 26 else ""))
    fmt = lambda v: f"{v:+,.0f}"
    axes = (f'<text x="{L - 6}" y="{T + 16}" text-anchor="end">{fhi:,.1f}</text>'
            f'<text x="{L - 6}" y="{B}" text-anchor="end">{flo:,.1f}</text>'
            f'<text x="{R + 6}" y="{T + 16}" fill="#e03131">{fmt(ghi)}</text>'
            f'<text x="{R + 6}" y="{B}" fill="#e03131">{fmt(glo)}</text>')
    last_f, last_g = bars[-1][1], flows[-1][1]
    others = [(k, (d.get("flows") or [{}])[-1].get(k)) for k in ("기관계", "개인")]
    others = " · ".join(f"{k} {fmt(v)}" for k, v in others if v is not None)
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="KOSPI200 선물과 외국인 선물 순매수 누적"'
           f' style="font:19px \'Malgun Gothic\',sans-serif;fill:#6b7385;display:block">'
           f'<rect x="{L}" y="{T}" width="{R - L}" height="{B - T}" fill="#fafbfc" stroke="#e3e6ec"/>{grid}{zero}{axes}'
           f'<path d="{path(bars, yf)}" fill="none" stroke="#1c2330" stroke-width="1.8"/>'
           f'<path d="{path(flows, yg)}" fill="none" stroke="#e03131" stroke-width="2.2"/></svg>')
    return (f'<div class="box"><h3>선물지수 · 외국인 선물 순매수 (분 단위)</h3>'
            f'<p style="margin:0 0 8px;font-size:13px;color:#6b7385"><b style="color:#1c2330">━ KOSPI200 선물</b> (좌) {last_f:,.2f} · '
            f'<b style="color:#e03131">━ 외국인 순매수 누적</b> (우, 억원) {fmt(last_g)}{" · " + others if others else ""}</p>'
            f'{svg}<p style="margin:6px 0 0;font-size:12px;color:#8a92a3">회사 PC 서버가 08:45~15:45 1분마다 기록한 값 '
            f'(서버가 꺼져 있던 시간은 비어 있음)</p></div>')


def close_extra(lines, days, cur, prefix, chart=""):
    """차트 리포트 아래에 붙이는 블록: 선물·외국인 교차 차트, 실적·이슈·일정, 한 줄 요약, 날짜별 리포트 목록."""
    rest, one = close_extra_lines(lines)
    one_html = f'<div class="one">▶ {escape(one)}</div>' if one else ""
    body = f'<div class="box">{report_text(chr(10).join(rest))}{one_html}</div>' if rest or one else ""
    chips = "".join(f'<li><a href="{prefix}{p.name}/"{" class=on" if p.name == cur else ""}>{label(p.name)}</a></li>'
                    for p in days)
    return (f'{EXTRA_CSS}<div class="site-extra">{chart}{body}'
            f'<div class="box"><h3>날짜별 장마감 리포트</h3><ul class="dates">{chips}</ul></div></div>')


def with_extra(html, extra):
    i = html.lower().rfind("</body>")
    return html[:i] + extra + html[i:] if i >= 0 else html + extra


def build_close():
    out = OUT / "close"
    days = dated_dirs(CLOSE)
    first = None
    latest_html = None
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
            fchart = futures_chart(p)
            html = (p / "장마감 수급체크.html").read_text(encoding="utf-8")
            (dest / "index.html").write_text(
                with_extra(with_nav(html, "../../", "close/"), close_extra(lines, days, p.name, "../", fchart)),
                encoding="utf-8")
            if p == days[0]:  # 메뉴 '장마감 리포트'는 목록 대신 최신 리포트를 바로 연다
                latest_html = with_extra(with_nav(html, "../", "close/"), close_extra(lines, days, p.name, "", fchart))
                (out / "embed.html").write_text(with_extra(embed_html(html), close_extra(lines, days, p.name, "", fchart)),
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
            first = dict(day=p.name, title=title, summary=summary, img=f"close/{p.name}/{imgs[0]}.jpg" if imgs else "",
                         embed="close/embed.html" if chart else "")
    rows = "".join(f'<li><a href="{p.name}/">{label(p.name)}</a></li>' for p in days)
    body = (f'<section class="panel"><ul class="dates">{rows}</ul></section>' if days
            else '<p class="err">장마감 리포트를 불러오지 못했습니다.</p>')
    out.mkdir(parents=True, exist_ok=True)
    if latest_html:
        (out / "index.html").write_text(latest_html, encoding="utf-8")
        return first
    (out / "index.html").write_text(page("장마감 리포트 지난 리포트", body, "../", "close/", "KOREA MARKET CLOSE",
                                         "평일 오후 4시경, 국내 장마감 수급 체크"), encoding="utf-8")
    return first


# ---------- 홈 ----------
# 홈 한 페이지에서 스크롤만으로 오전 데일리 → 돈이 되는 뉴스 → 장마감 수급을 모두 본다.
# 데일리·장마감은 원본 HTML을 iframe에 넣고 내용 높이만큼 늘려 안쪽 스크롤이 생기지 않게 한다.
HOME_CSS = """
.sec{scroll-margin-top:56px;margin-top:22px}
#daily{margin-top:0}
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:0 0 10px}
.sec-h h2{margin:0}.sec-h a{font-size:13px;color:var(--muted)}
iframe.embed{display:block;width:100%;border:0;border-radius:14px;background:var(--card);min-height:400px}
@media (max-width:520px){iframe.embed{width:calc(100% + 32px);margin:0 -16px;border-radius:0}}
"""
FIT_JS = """<script>
function fit(f){try{var d=f.contentDocument,z=parseFloat(d.documentElement.style.zoom)||1;f.style.height=Math.ceil(Math.max(d.documentElement.scrollHeight,d.body.scrollHeight)*z)+'px'}catch(e){}}
document.querySelectorAll('iframe.embed').forEach(function(f){f.addEventListener('load',function(){fit(f);
try{new ResizeObserver(function(){fit(f)}).observe(f.contentDocument.body)}catch(e){}
setTimeout(function(){fit(f)},800);setTimeout(function(){fit(f)},2500)})});
addEventListener('resize',function(){document.querySelectorAll('iframe.embed').forEach(fit)});
</script>"""


def build_home(now, daily, news, close, live=None):
    if live:
        s1 = f'<iframe class="embed" scrolling="no" src="{live["embed"]}" title="실시간 시세" loading="eager"></iframe>'
    elif daily and daily.get("embed"):
        s1 = f'<iframe class="embed" scrolling="no" src="{daily["embed"]}" title="오전 데일리" loading="eager"></iframe>'
    else:
        s1 = '<section class="panel"><p class="err">오전 데일리는 다음 아침 7시 발송분부터 표시됩니다.</p></section>'
    if close and close.get("embed"):
        s3 = f'<iframe class="embed" scrolling="no" src="{close["embed"]}" title="장마감 수급" loading="lazy"></iframe>'
        more3 = f'<a href="close/">{label(close["day"])}</a>'
    else:
        s3, more3 = '<section class="panel"><p class="err">장마감 리포트를 불러오지 못했습니다.</p></section>', ""
    body = (f'<style>{HOME_CSS}</style>'
            f'<section class="sec" id="daily">{s1}</section>'
            f'<section class="sec" id="news"><div class="sec-h"><h2>💰 돈이 되는 뉴스</h2>'
            f'<a href="news/">{news["at"]:%m/%d %H:%M} 수집</a></div>{news["body"]}</section>'
            f'<section class="sec" id="close"><div class="sec-h"><h2>📊 장마감 수급</h2>{more3}</div>{s3}</section>'
            f'{FIT_JS}')
    (OUT / "index.html").write_text(page(SITE_NAME, body, "", "", hero=False),
                                    encoding="utf-8")


def main():
    now = datetime.now(d.KST)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / ".nojekyll").write_text("")
    write_app_files()
    daily = build_daily()
    theme_doc = build_theme()
    news = build_news(now, theme_doc)
    close = build_close()
    live = build_live(now)
    build_home(now, daily, news, close, live)
    print(json.dumps({"out": str(OUT), "daily": daily and daily["day"], "close": close and close["day"],
                      "live": bool(live),
                      "news": [len(news["kr"]), len(news["theme"])]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
