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
MENU = (("", "홈"), ("daily/", "오전 데일리"), ("news/", "돈이 되는 뉴스"), ("stocks/", "관심 종목"), ("close/", "장마감 리포트"))


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


# ---------- 관심 종목 뉴스 (watchlist/<종목>.txt 파일 하나가 종목 하나) ----------
WATCH = ROOT / "watchlist"
REPO_URL = "https://github.com/Sunbong-oh/market-dashboard"


def watchlist():
    names = []
    for f in sorted(WATCH.glob("*.txt")) if WATCH.exists() else []:
        name = (f.read_text(encoding="utf-8").strip().splitlines() or [f.stem])[0].strip() or f.stem
        names.append((name, f.name))
    return names


def naver_stock_news(code, since):
    """네이버 증권 종목 뉴스 (종목코드로 묶인 기사라 제목에 종목명이 없어도 나온다)."""
    if not code:
        return []
    try:
        data = json.loads(_get(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=30&page=1"))
    except Exception as e:
        print("네이버 종목뉴스 실패:", code, type(e).__name__, e, file=sys.stderr)
        return []
    print("  네이버 종목뉴스 응답:", type(data).__name__, str(data)[:300].replace("\n", " "), file=sys.stderr)
    rows = []
    for g in data if isinstance(data, list) else [data]:
        rows += g.get("items") or [] if isinstance(g, dict) and "items" in g else [g] if isinstance(g, dict) else []
    out = []
    for r in rows:
        title = unescape(re.sub(r"<[^>]+>", "", str(r.get("title") or r.get("titleFull") or ""))).strip()
        dt = re.sub(r"\D", "", str(r.get("datetime") or r.get("dateTime") or ""))[:12]
        if not title or len(dt) < 8:
            continue
        try:
            ts = datetime.strptime(dt.ljust(12, "0"), "%Y%m%d%H%M").replace(tzinfo=d.KST).timestamp()
        except ValueError:
            continue
        oid, aid = r.get("officeId"), r.get("articleId")
        link = (f"https://n.news.naver.com/mnews/article/{oid}/{aid}" if oid and aid
                else f"https://m.stock.naver.com/domestic/stock/{code}/news")
        if ts >= since:
            out.append(dict(raw=title, title=title, src=str(r.get("officeName") or "네이버"), link=link, ts=ts))
    return out


def stock_news(name, code="", limit=3):
    """종목 뉴스: 최근 7일 우선, 7일 안에 3건이 안 되면 최근 30일 기사로 채운다.
    네이버 종목뉴스 + Google 뉴스(제목에 종목명), 최신순·중복 제거, 칼럼·추천성·해외 스팸 제외."""
    key = re.sub(r"\s+", "", name)
    week = datetime.now(d.KST).timestamp() - 7 * 86400
    since = datetime.now(d.KST).timestamp() - 30 * 86400
    google = [x for x in d.google_news(f"{name} when:30d")
              if key in re.sub(r"\s+", "", x["raw"]) and x["ts"] >= since
              and not d.FOREIGN_SRC.search(x["src"])
              and (re.search(r"[가-힣]", x["src"]) or d.KR_LATIN_SRC.search(x["src"]))
              and not x["src"].startswith(d.KR_SKIP_SRC)]
    naver = naver_stock_news(code, since)
    items = [x for x in naver + google if not d.CLICKBAIT.search(x["title"])]
    print(f"  뉴스 후보 {name}: 네이버 {len(naver)} 구글 {len(google)}", file=sys.stderr)
    recent = d.rank([x for x in items if x["ts"] >= week], limit=limit)
    if len(recent) < limit:
        recent += [dict(x, old=True) for x in d.rank([x for x in items if x["ts"] < week], limit=limit - len(recent))]
    return recent


def _get(url, enc="utf-8"):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": d.UA, "Referer": "https://m.stock.naver.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode(enc, "replace")


def stock_code(name, txt=""):
    """종목코드 6자리: 파일에 적혀 있으면 그것, 아니면 네이버 증권 검색."""
    m = re.search(r"\b(\d{6})\b", txt)
    if m:
        return m.group(1)
    try:
        import urllib.parse
        data = json.loads(_get("https://ac.stock.naver.com/ac?target=stock&q=" + urllib.parse.quote(name)))
        items = [x for x in data.get("items") or [] if re.fullmatch(r"\d{6}", str(x.get("code", "")))]
        exact = [x for x in items if re.sub(r"\s+", "", x.get("name", "")) == re.sub(r"\s+", "", name)]
        return str((exact or items)[0]["code"]) if items else ""
    except Exception as e:
        print("종목코드 검색 실패:", name, type(e).__name__, e, file=sys.stderr)
        return ""


ORDER = re.compile(r"공급계약|수주|판매ㆍ공급|판매·공급|계약 ?체결")


def stock_disclosures(code, limit=2):
    """네이버 증권(전자공시 DART 연동) 최근 공시. 수주(단일판매·공급계약)는 따로 표시."""
    if not code:
        return []
    try:
        data = json.loads(_get(f"https://m.stock.naver.com/api/stock/{code}/disclosure?page=1&pageSize=15"))
    except Exception as e:
        print("공시 수집 실패:", code, type(e).__name__, e, file=sys.stderr)
        return []
    rows = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) else []
    out = []
    for r in rows[:limit * 2]:
        title = next((r[k] for k in ("title", "disclosureTitle", "reportNm") if r.get(k)), "")
        when = next((str(r[k]) for k in ("datetime", "dateTime", "date", "rceptDt", "disclosureDate") if r.get(k)), "")
        rid = next((str(r[k]) for k in ("rceptNo", "rcpNo", "disclosureId", "id") if r.get(k)), "")
        if not title:
            continue
        link = (f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rid}" if re.fullmatch(r"\d{14}", rid)
                else f"https://m.stock.naver.com/domestic/stock/{code}/disclosure")
        out.append(dict(title=title.strip(), when=re.sub(r"[^0-9]", "", when)[:8], link=link, order=bool(ORDER.search(title))))
    return out[:limit]


def stock_reports(code, limit=4):
    """네이버 증권 리서치 - 종목분석 리포트 (증권사, 날짜, PDF)."""
    if not code:
        return []
    try:
        html = _get(f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}", "euc-kr")
    except Exception as e:
        print("리포트 수집 실패:", code, type(e).__name__, e, file=sys.stderr)
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        m = re.search(r'href="[^"]*?(company_read\.naver\?[^"]+)"[^>]*>(.*?)</a>', tr, re.S | re.I)
        if not m:
            continue
        tds = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        pdf = re.search(r'href="(https?://[^"]+\.pdf)"', tr)
        date = next((t for t in tds if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), "")
        broker = tds[2] if len(tds) > 2 else ""
        out.append(dict(title=unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip(), broker=unescape(broker), date=date,
                        link=pdf.group(1) if pdf else "https://finance.naver.com/research/" + unescape(m.group(1))))
        if len(out) >= limit:
            break
    if not out:
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        i = html.find("type_1")
        print("리포트 0건:", code, len(html), "bytes, company_read 링크", html.count("company_read"),
              "| title:", t.group(1).strip() if t else "-", "| table:", re.sub(r"\s+", " ", html[i:i + 600]) if i >= 0 else "type_1 없음",
              file=sys.stderr)
    return out


def stock_info(name, fname):
    txt = (WATCH / fname).read_text(encoding="utf-8")
    code = stock_code(name, txt)
    info = dict(name=name, fname=fname, code=code, news=stock_news(name, code), dis=stock_disclosures(code), rep=stock_reports(code))
    print(f"관심종목 {name}({code or '?'}): 공시 {len(info['dis'])} 리포트 {len(info['rep'])} 뉴스 {len(info['news'])}", file=sys.stderr)
    return info


def _mini(rows, empty):
    if not rows:
        return f'<p class="none2">{empty}</p>'
    return '<ul class="mini">' + "".join(
        f'<li{" class=ord" if r.get("order") else ""}><a href="{escape(r["link"])}" target="_blank" rel="noopener">'
        f'{"🔴 " if r.get("order") else ""}{escape(r["title"])}</a><span>{escape(r["sub"])}</span></li>' for r in rows) + "</ul>"


STOCK_CSS = """
#stocks:not(.admin) .adm{display:none!important}
.stk-add{display:flex;gap:8px;margin:10px 0 4px}.stk-add input{flex:1;min-width:0;font:inherit;font-size:16px;padding:9px 12px;
 border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text)}
.stk-add button,.cus button{font:inherit;font-weight:800;border:0;border-radius:10px;padding:9px 14px;background:var(--accent);color:#fff;cursor:pointer}
.cus{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 0}.cus button{background:var(--bg);color:var(--text);border:1px solid var(--line);padding:5px 12px;border-radius:99px;font-size:14px}
.cus button.on{background:var(--text);color:var(--card)}.cus button.ed{border-style:dashed}
.stks{display:grid;gap:12px;margin-top:12px}@media (min-width:900px){.stks{grid-template-columns:1fr 1fr}}
.stk h3{display:flex;align-items:center;gap:8px;margin:0 0 4px;font-size:18px}.stk h3 .x{margin-left:auto;font-size:12px;color:var(--muted);text-decoration:none}
.stk h3 label{font-size:13px;font-weight:700;color:var(--accent);display:none}.editing .stk h3 label{display:inline}
.stk .items li{font-size:15px}.stk[hidden]{display:none}
.who{margin:10px 0 0;padding:10px 12px;border-radius:10px;background:var(--bg);font-size:15px}.who small{color:var(--muted)}
.stk h4{margin:12px 0 4px;font-size:14px;color:var(--muted)}.stk h3 small{font-size:12px;color:var(--muted);font-weight:600}
.mini{list-style:none;margin:0;padding:0}.mini li{padding:6px 0;border-top:1px solid var(--line);font-size:15px;font-weight:700;line-height:1.4}
.mini li:first-child{border-top:0}.mini a{text-decoration:none}.mini span{display:block;font-size:12px;font-weight:400;color:var(--muted)}
.mini li.ord a{color:#e03131}.none2{margin:2px 0;font-size:13px;color:var(--muted)}
"""
STOCK_JS = """<script>
(function(){var KEY='brian-customers',box=document.getElementById('stocks');if(!box)return;
 try{var q=new URLSearchParams(location.search).get('admin');if(q==='brian')localStorage.setItem('brian-admin','1');if(q==='off')localStorage.removeItem('brian-admin');
  if(localStorage.getItem('brian-admin')==='1')box.classList.add('admin')}catch(e){}
 /* 홈 화면 앱은 주소창이 없어 ?admin=brian 을 칠 수 없다: 제목 배지를 5번 연달아 누르면 비밀번호를 묻는다 */
 var taps=0,tt=0;box.querySelector('.tag').addEventListener('click',function(){var now=Date.now();taps=now-tt<800?taps+1:1;tt=now;
  if(taps<5)return;taps=0;
  if(box.classList.contains('admin')){if(confirm('관리 화면을 끌까요?')){try{localStorage.removeItem('brian-admin')}catch(e){}location.reload()}return}
  if((prompt('관리 비밀번호')||'').trim()==='brian'){try{localStorage.setItem('brian-admin','1')}catch(e){}location.reload()}});
 function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 if(!box.classList.contains('admin')){
  /* 손님 링크(#c=이름&s=종목,종목): 그 손님 종목만 보여 준다. 주소 # 뒤는 서버로 가지 않고, 이 폰에만 기억한다. */
  var v=null;try{var h=new URLSearchParams(location.hash.slice(1));
   if(h.get('s')){v={c:h.get('c')||'',s:h.get('s').split(',').map(function(x){return x.trim()}).filter(Boolean)};localStorage.setItem('brian-view',JSON.stringify(v))}
   else v=JSON.parse(localStorage.getItem('brian-view')||'null')}catch(e){}
  if(v&&v.s&&v.s.length){var have=[],norm=function(t){return t.replace(/\\s/g,'')},want=v.s.map(norm);
   box.querySelectorAll('.stk').forEach(function(c){var k=norm(c.dataset.name),on=want.indexOf(k)>=0;c.hidden=!on;if(on)have.push(k)});
   var miss=v.s.filter(function(x){return have.indexOf(norm(x))<0});
   var w=document.createElement('p');w.className='who';
   w.innerHTML='👤 <b>'+esc(v.c||'')+'</b>'+(v.c?'님 ':'')+'관심 종목 '+v.s.map(esc).join(' · ')+(miss.length?'<br><small>준비 중: '+miss.map(esc).join(', ')+'</small>':'');
   box.insertBefore(w,box.querySelector('.stks'))}
  return}
 var st;try{st=JSON.parse(localStorage.getItem(KEY))||{}}catch(e){st={}}st.c=st.c||{};
 var cur=st.cur||'',editing=false;
 function save(){st.cur=cur;try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
 function cards(){return box.querySelectorAll('.stk')}
 function draw(){var row=box.querySelector('.cus'),h='<button data-c="" class="'+(cur?'':'on')+'">전체</button>';
  Object.keys(st.c).sort().forEach(function(n){h+='<button data-c="'+n.replace(/"/g,'&quot;')+'" class="'+(n===cur?'on':'')+'">'+n.replace(/</g,'&lt;')+'</button>'});
  h+='<button data-a="add" class="ed">+ 손님</button>'+(cur?'<button data-a="link" class="ed">🔗 손님 링크</button><button data-a="edit" class="ed">'+(editing?'완료':'종목 고르기')+'</button><button data-a="del" class="ed">손님 삭제</button>':'');
  row.innerHTML=h;box.classList.toggle('editing',editing&&!!cur);
  var mine=cur?st.c[cur]||[]:null;
  cards().forEach(function(c){var n=c.dataset.name,cb=c.querySelector('input');cb.checked=!!mine&&mine.indexOf(n)>=0;
   c.hidden=!!mine&&!editing&&mine.indexOf(n)<0});
  var e=box.querySelector('.none');if(e)e.hidden=!(mine&&!editing&&!mine.length)}
 box.addEventListener('click',function(ev){var b=ev.target.closest('.cus button');if(!b)return;
  if(b.dataset.a==='add'){var n=(prompt('손님 이름 (이 핸드폰에만 저장돼요)')||'').trim();if(n){st.c[n]=st.c[n]||[];cur=n;editing=true}}
  else if(b.dataset.a==='link'){var l=st.c[cur]||[];if(!l.length){alert('먼저 "종목 고르기"로 이 손님 종목을 체크하세요.');return}
   var url=location.origin+location.pathname.replace(/stocks\\/.*$/,'').replace(/index\\.html$/,'')+'#c='+encodeURIComponent(cur)+'&s='+encodeURIComponent(l.join(','));
   if(navigator.share){navigator.share({title:cur+'님 관심 종목',url:url}).catch(function(){})}
   else if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){alert('링크를 복사했어요. 카톡·문자에 붙여 넣으세요.\\n'+url)},function(){prompt('이 링크를 복사하세요',url)})}
   else prompt('이 링크를 복사하세요',url);return}
  else if(b.dataset.a==='edit')editing=!editing;
  else if(b.dataset.a==='del'){if(confirm(cur+' 손님을 지울까요? (종목 뉴스는 그대로 남아요)')){delete st.c[cur];cur='';editing=false}}
  else{cur=b.dataset.c;editing=false}
  save();draw()});
 box.addEventListener('change',function(ev){var cb=ev.target;if(!cb.matches('.stk input')||!cur)return;
  var n=cb.closest('.stk').dataset.name,l=st.c[cur]=st.c[cur]||[],i=l.indexOf(n);
  if(cb.checked&&i<0)l.push(n);if(!cb.checked&&i>=0)l.splice(i,1);save()});
 box.querySelector('.stk-add').addEventListener('submit',function(ev){ev.preventDefault();
  var inp=this.querySelector('input'),n=inp.value.replace(/[\\\\/:*?"<>|#%%]/g,'').trim();if(!n)return;
  if(cur){var l=st.c[cur]=st.c[cur]||[];if(l.indexOf(n)<0)l.push(n);save()}
  if([].some.call(cards(),function(c){return c.dataset.name.replace(/\\s/g,'')===n.replace(/\\s/g,'')})){alert(n+'은(는) 이미 추가된 종목이에요.');inp.value='';draw();return}
  window.open('%s/new/main/watchlist?filename='+encodeURIComponent(n+'.txt')+'&value='+encodeURIComponent(n),'_blank');inp.value=''});
 draw()})();
</script>""" % REPO_URL


def stocks_block(stocks):
    """관심 종목 입력칸 + 손님 고르기 + 종목별 뉴스 카드."""
    def ymd(v):
        return f"{v[2:4]}.{v[4:6]}.{v[6:8]}" if len(v) == 8 else v
    cards = []
    for x in stocks:
        dis = [dict(r, sub=ymd(r["when"])) for r in x["dis"]]
        rep = [dict(r, sub=f'{r["broker"]} · {r["date"]}') for r in x["rep"]]
        news = [dict(link=n["link"], title=n["title"],
                     sub=f'{n["src"]} · {datetime.fromtimestamp(n["ts"], d.KST):%m/%d %H:%M}{" · 1주일 이전" if n.get("old") else ""}')
                for n in x["news"]]
        code = f' <small>{x["code"]}</small>' if x["code"] else ""
        rep_html = f'<h4>📝 증권사 리포트</h4>{_mini(rep, "")}' if rep else ""
        cards.append(
            f'<div class="card stk" data-name="{escape(x["name"])}"><h3>{escape(x["name"])}{code}'
            f'<label class="adm"><input type="checkbox"> 이 손님 종목</label>'
            f'<a class="x adm" href="{REPO_URL}/delete/main/watchlist/{escape(x["fname"])}" target="_blank" rel="noopener">삭제</a></h3>'
            f'<h4>📰 뉴스 (최근 1주일)</h4>{_mini(news, "최근 30일 기사 없음")}'
            f'<h4>📢 최근 공시</h4>{_mini(dis, "최근 공시 없음")}'
            f'{rep_html}</div>')
    cards = "".join(cards)
    empty = '' if stocks else '<p class="err">아직 등록된 종목이 없습니다.</p>'
    return (f'<style>{STOCK_CSS}</style><section class="panel" id="stocks"><div class="tag c">관심 종목 공시 · 리포트 · 뉴스</div>'
            f'<form class="stk-add adm"><input placeholder="종목명 (예: 삼성전자)" enterkeyhint="done"><button>추가</button></form>'
            f'<p class="meta adm">추가를 누르면 GitHub 저장 화면이 열려요 → 초록색 <b>Commit changes</b>를 누르면 2~3분 뒤 1주일 뉴스·최근 공시가 붙어요 (🔴 = 수주·공급계약 공시). '
            f'손님 구분은 이 핸드폰에만 저장되고 사이트에는 종목 이름만 보여요.</p>'
            f'<div class="cus adm"></div><p class="err none adm" hidden>이 손님에게 고른 종목이 없어요. "종목 고르기"를 눌러 체크하세요.</p>'
            f'<div class="stks">{cards}</div>{empty}</section>{STOCK_JS}')


def build_stocks(now):
    from concurrent.futures import ThreadPoolExecutor
    names = watchlist()
    with ThreadPoolExecutor(8) as ex:
        stocks = list(ex.map(lambda nf: stock_info(*nf), names))
    body = stocks_block(stocks)
    (OUT / "stocks").mkdir(parents=True, exist_ok=True)
    (OUT / "stocks" / "index.html").write_text(
        page("관심 종목 뉴스", body, "../", "stocks/", "MY STOCKS",
             f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 수집 · 종목별 공시·리포트·최근 7일 기사"), encoding="utf-8")
    return dict(body=body, at=now, n=len(stocks))


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


FUT_SRC = ("https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/futures_flow.json?ref=flow-live",
           "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/futures_flow.json")
FUT_CSS = """<style>
.fut{font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#1c2330}
.fut .badge{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;border-radius:12px;padding:10px 12px;margin:0 0 10px;background:#f4f5f8}
.fut .badge .k{font-size:13px;font-weight:700;color:#6b7385}.fut .badge b{font-size:22px;letter-spacing:-.4px}
.fut .badge .c{font-size:16px;font-weight:800}.fut .badge .g{font-size:13px;font-weight:700;margin-left:auto}
.fut .badge.up{background:#fff0f0}.fut .badge.up b,.fut .badge.up .c{color:#e03131}
.fut .badge.dn{background:#eef4ff}.fut .badge.dn b,.fut .badge.dn .c{color:#1c6dd0}
.fut .g.up{color:#e03131}.fut .g.dn{color:#1c6dd0}
.fut .lg{margin:0 0 8px;font-size:13px;color:#6b7385;line-height:1.5}
.fut .note{margin:6px 0 0;font-size:12px;color:#8a92a3}
.fut .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#e03131;margin-right:5px;animation:futp 1.4s infinite}
@keyframes futp{50%{opacity:.25}}
</style>"""
# 선물 교차 차트: 장마감 페이지(저장된 json)와 홈 실시간 박스(flow-live 브랜치)에서 같은 함수로 그린다.
FUT_JS = r"""<script>
function futChart(el,d,live){
 var tm=function(t){t=String(t);while(t.length<4)t='0'+t;return (+t.slice(0,2))*60+(+t.slice(2,4))-525};
 var ok=function(m){return m>=0&&m<=420};
 var bars=(d.bars||[]).filter(function(b){return b.c!=null}).map(function(b){return [tm(b.t),b.c]}).filter(function(p){return ok(p[0])});
 var fl=(d.flows||[]).filter(function(r){return r['외국인']!=null}).map(function(r){return [tm(r.t),r['외국인']]}).filter(function(p){return ok(p[0])});
 if(bars.length<2)return false;
 var hf=fl.length>=2,cf=d.current_flows||{},lf=bars[bars.length-1],last=lf[1];
 var fg=hf?fl[fl.length-1][1]:cf['외국인'];
 var F=d.futures||{},prev=(F.price!=null&&F.change!=null)?F.price-F.change:null;
 var W=640,H=310,L=92,R=548,T=14,B=262,x=function(m){return L+(R-L)*m/420};
 var sc=function(v){var lo=Math.min.apply(0,v),hi=Math.max.apply(0,v);if(hi==lo){hi+=1;lo-=1}
   return {lo:lo,hi:hi,y:function(a){return B-(B-T)*(a-lo)/(hi-lo)}}};
 var sf=sc(bars.map(function(p){return p[1]})),sg=hf?sc(fl.map(function(p){return p[1]}).concat([0])):null;
 var path=function(ps,y){return 'M'+ps.map(function(p){return x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)}).join(' L')};
 var n0=function(v){return Math.round(v).toLocaleString('ko-KR')},sg0=function(v){return (v>0?'+':v<0?'-':'')+n0(Math.abs(v))};
 var f2=function(v){return v.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2})};
 var grid=['0900','1030','1200','1330','1500'].map(function(t){var X=x(tm(t));return '<line x1="'+X+'" y1="'+T+'" x2="'+X+'" y2="'+B+'" stroke="#e3e6ec"/>'+
  '<text x="'+X+'" y="'+(B+24)+'" text-anchor="middle">'+t.slice(0,2)+':'+t.slice(2)+'</text>'}).join('');
 var fsvg='';
 if(hf){var yz=sg.y(0);
  fsvg='<line x1="'+L+'" y1="'+yz.toFixed(1)+'" x2="'+R+'" y2="'+yz.toFixed(1)+'" stroke="#e03131" stroke-dasharray="4 4" opacity=".45"/>'+
   '<text x="'+(R+6)+'" y="'+(T+12)+'" fill="#e03131">'+sg0(sg.hi)+'</text><text x="'+(R+6)+'" y="'+(B+4)+'" fill="#e03131">'+sg0(sg.lo)+'</text>'+
   (yz-T>=24&&B-yz>=20?'<text x="'+(R+6)+'" y="'+(yz+5).toFixed(1)+'" fill="#e03131">0</text>':(yz-T<24&&sg.hi!==0?'<text x="'+(R+6)+'" y="'+(T+28)+'" fill="#e03131">0</text>':''))+
   '<path d="'+path(fl,sg.y)+'" fill="none" stroke="#e03131" stroke-width="2.2" stroke-linejoin="round"/>'}
 var svg='<svg viewBox="0 0 '+W+' '+H+'" width="100%" role="img" aria-label="KOSPI200 선물과 외국인 선물 순매수 누적 교차 차트" style="font:15px \'Malgun Gothic\',sans-serif;fill:#6b7385;display:block">'+
  '<rect x="'+L+'" y="'+T+'" width="'+(R-L)+'" height="'+(B-T)+'" fill="#fafbfc" stroke="#e3e6ec"/>'+grid+
  '<text x="'+(L-6)+'" y="'+(T+12)+'" text-anchor="end">'+f2(sf.hi)+'</text><text x="'+(L-6)+'" y="'+(B+4)+'" text-anchor="end">'+f2(sf.lo)+'</text>'+
  fsvg+'<path d="'+path(bars,sf.y)+'" fill="none" stroke="#1c2330" stroke-width="1.8" stroke-linejoin="round"/></svg>';
 var ch=prev!=null?last-prev:null,pct=ch!=null&&prev?ch/prev*100:0,cls=ch>0?'up':ch<0?'dn':'';
 var badge=ch==null?'':'<div class="badge '+cls+'"><span class="k">KOSPI200 선물</span> <b>'+f2(last)+'</b> <span class="c">'+(ch>0?'▲':ch<0?'▼':'')+
  f2(Math.abs(ch))+' ('+(pct>0?'+':'')+pct.toFixed(2)+'%) '+(ch>0?'상승':ch<0?'하락':'보합')+'</span>'+
  (fg!=null?'<span class="g '+(fg>0?'up':fg<0?'dn':'')+'">외국인 '+sg0(fg)+'억 '+(fg>0?'순매수':fg<0?'순매도':'')+(hf?'':' (마감)')+'</span>':'')+'</div>';
 var rest=hf?(d.flows||[]).slice(-1)[0]||{}:cf,oth=['기관계','개인'].filter(function(k){return rest[k]!=null}).map(function(k){return k+' '+sg0(rest[k])}).join(' · ');
 var hh=lf[0]+525,hhmm=Math.floor(hh/60)+':'+('0'+hh%60).slice(-2);
 el.innerHTML=badge+'<p class="lg"><b style="color:#1c2330">━ KOSPI200 선물</b> (좌) '+f2(last)+
  (hf?' · <b style="color:#e03131">━ 외국인 순매수 누적</b> (우, 억원) '+sg0(fg):'')+(oth?' · '+oth:'')+'</p>'+svg+
  '<p class="note">'+(live?'<span class="dot"></span>'+hhmm+' 기준 · 회사 PC가 1분마다 올리고 이 화면은 1~2분마다 자동 갱신':
  (hf?'회사 PC 서버가 08:45~15:45 1분마다 기록한 값 (서버가 꺼져 있던 시간은 비어 있음)':'외국인 분 단위 추이는 회사 PC 기록이 있는 날부터 함께 그려집니다'))+'</p>';
 return true}
</script>"""


def _fut_data(d):
    keep = ("t", "외국인", "기관계", "개인")
    return {"futures": d.get("futures"), "bars": [{"t": b["t"], "c": b.get("c")} for b in d.get("bars") or []],
            "flows": [{k: r[k] for k in keep if k in r} for r in d.get("flows") or []],
            "current_flows": {k: v for k, v in (d.get("current_flows") or {}).items() if k in keep}}


def futures_chart(day_dir):
    """회사 PC 서버가 올린 futures_flow.json으로 KOSPI200 선물(좌축)과 외국인 선물 순매수 누적(우축) 교차 차트."""
    f = day_dir / "futures_flow.json"
    try:
        if f.exists():
            raw = json.loads(f.read_text(encoding="utf-8"))
        else:  # PC 기록이 없는 날: 장마감 리포트 HTML에 들어 있는 /api/futures 응답(선물 1분봉 + 마감 수급)
            h = next(day_dir.glob("*.html"), None)
            txt = h.read_text(encoding="utf-8") if h else ""
            i = txt.find('"/api/futures?minutes=1": {')
            if i < 0:
                return ""
            raw = json.JSONDecoder().raw_decode(txt[txt.index("{", i):])[0]
        data = json.dumps(_fut_data(raw), ensure_ascii=False).replace("</", "<\\/")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""
    return (f'{FUT_CSS}<div class="box fut"><h3>선물지수 · 외국인 선물 순매수 (분 단위)</h3><div></div></div>{FUT_JS}'
            f'<script>(function(b){{if(!futChart(b.lastChild,{data}))b.remove()}})'
            f'(document.currentScript.previousElementSibling.previousElementSibling)</script>')


LIVE_FUT = """<section class="sec" id="futlive" hidden><div class="sec-h"><h2>📈 장중 선물 · 외국인</h2><span class="futt">실시간</span></div>
<div class="panel fut"></div></section>"""
LIVE_FUT_JS = """<script>
(function(){var box=document.getElementById('futlive'),src=%s;
 function kst(){var n=new Date(Date.now()+9*3600e3);return {d:n.toISOString().slice(0,10).replace(/-/g,''),hm:n.toISOString().slice(11,16),wd:n.getUTCDay()}}
 function on(){var k=kst();return k.wd>0&&k.wd<6&&k.hm>='08:45'&&k.hm<='16:30'}
 function load(i){i=i||0;if(i>=src.length)return;
  fetch(src[i]+(i?'?t='+Date.now():''),{cache:'no-store',headers:i?{}:{Accept:'application/vnd.github.raw'}})
  .then(function(r){if(!r.ok)throw r;return r.json()})
  .then(function(d){if(d.flow_date===kst().d&&futChart(box.querySelector('.fut'),d,true))box.hidden=false})
  .catch(function(){load(i+1)})}
 function tick(){if(on()&&!document.hidden)load(0)}
 tick();setInterval(tick,90000);document.addEventListener('visibilitychange',tick)})();
</script>"""


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
#daily,#futlive{margin-top:0}#futlive+#daily{margin-top:22px}
.futt{font-size:13px;color:#e03131;font-weight:700}
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


def build_home(now, daily, news, close, live=None, stocks=None):
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
            f'{FUT_CSS}{LIVE_FUT}'
            f'<section class="sec" id="daily">{s1}</section>'
            f'<section class="sec" id="news"><div class="sec-h"><h2>💰 돈이 되는 뉴스</h2>'
            f'<a href="news/">{news["at"]:%m/%d %H:%M} 수집</a></div>{news["body"]}</section>'
            f'<section class="sec" id="mystocks"><div class="sec-h"><h2>📌 관심 종목 뉴스</h2>'
            f'<a href="stocks/">{stocks["at"]:%m/%d %H:%M} 수집</a></div>{stocks["body"]}</section>'
            f'<section class="sec" id="close"><div class="sec-h"><h2>📊 장마감 수급</h2>{more3}</div>{s3}</section>'
            f'{FIT_JS}{FUT_JS}{LIVE_FUT_JS % json.dumps(FUT_SRC)}')
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
    stocks = build_stocks(now)
    build_home(now, daily, news, close, live, stocks)
    print(json.dumps({"out": str(OUT), "daily": daily and daily["day"], "close": close and close["day"],
                      "live": bool(live),
                      "news": [len(news["kr"]), len(news["theme"])], "stocks": stocks["n"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
