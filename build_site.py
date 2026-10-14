"""나만의 주식투자 사이트(GitHub Pages) 생성기.

실행: python build_site.py  ->  _site/ 폴더에 정적 사이트 생성 (GitHub Actions site.yml이 배포)

메뉴
  /             홈: 세 가지 리포트의 최신 요약
  /daily/       오전 데일리 (미국 데일리 마켓) — archive/daily/YYYY-MM-DD/ (daily-dashboard.yml이 매일 저장)
  /news/        돈이 되는 뉴스 — 빌드할 때마다 Google 뉴스에서 새로 수집 (dashboard.py의 뉴스 로직 재사용)
  /close/       장마감 리포트 (국내 장마감 수급체크) — kb-market-report 저장소의 archive/ (환경변수 CLOSE_REPO)
  /target/      목표주가 변동 (증권사 리포트 상향·하향, 평일 08:00) — kb-market-report 저장소의 consensus/*.json
  /us/          해외주식 리포트 (국내 증권사 미국주식 리포트 요약) — us_reports/*.json (us_reports.py)
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
from company_ko import describe, sector_ko

ROOT = Path(__file__).resolve().parent
# 빌드마다 바뀌는 값: iframe 주소 뒤에 붙여 폰이 예전 내용을 캐시에서 다시 쓰지 않게 한다 (GitHub Pages는 10분 캐시)
VER = datetime.now().strftime("%y%m%d%H%M%S")
OUT = Path(os.environ.get("SITE_OUT", ROOT / "_site"))
DAILY = ROOT / "archive" / "daily"
CLOSE = Path(os.environ.get("CLOSE_REPO", ROOT.parent / "kb-market-report")) / "archive"
CONSENSUS = CLOSE.parent / "consensus"
US_REPORTS = ROOT / "us_reports"
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
.items .rel{display:inline-block;margin-right:6px;padding:1px 7px;border-radius:6px;background:#fff1dc;color:#c25e00;font-size:12px;font-weight:800;vertical-align:2px}
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
MENU = (("", "홈"), ("daily/", "오전 데일리"), ("news/", "돈이 되는 뉴스"), ("stocks/", "관심 종목"), ("target/", "목표주가"),
        ("us/", "해외주식"), ("close/", "장마감 리포트"))


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


# 비트코인은 24시간 거래라 주말에도 움직인다. 홈 임베드를 열 때마다(그리고 1분마다) 바이낸스 일봉으로 카드를 덮어쓴다.
# 실패하면 아침에 찍어 둔 값이 그대로 남는다. 지난 날짜 리포트에는 붙이지 않는다.
BTC_LIVE = """<script>(function(){
var SRC=['https://data-api.binance.vision','https://api.binance.com'];
function fmt(v){return v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}
function card(){var s=document.querySelectorAll('article.card .sym');
for(var i=0;i<s.length;i++)if(s[i].textContent.indexOf('BTC-USD')===0)return s[i].closest('article.card');return null}
function apply(k){var c=card();if(!c||!k||k.length<2)return;
var prev=parseFloat(k[k.length-2][4]),last=parseFloat(k[k.length-1][4]);if(!(prev>0&&last>0))return;
var d=last-prev,p=(last/prev-1)*100,cl=d>0?'up':d<0?'down':'flat';
c.querySelector('.price').firstElementChild.nextSibling.nodeValue=fmt(last);
var dl=c.querySelector('.delta');
dl.innerHTML='<span class="'+cl+'">'+(d>0?'\u25B2':d<0?'\u25BC':'\u2013')+' '+fmt(Math.abs(d))+' ('+(p>0?'+':'')+p.toFixed(2)+'%)</span> <small>\u00B7 \uc2e4\uc2dc\uac04</small>'}
function load(i){if(i>=SRC.length)return;
fetch(SRC[i]+'/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=2').then(function(r){if(!r.ok)throw 0;return r.json()})
.then(apply).catch(function(){load(i+1)})}
load(0);setInterval(function(){load(0)},60000)})()</script>"""


# 미국 데일리 주요지표 실시간: us-live.yml이 미국 장 전후(한국 17:00~09:05) 1분마다 올리는 us-live/quotes.json 으로
# 카드의 가격·전일 대비 등락과 맨 위 나스닥·S&P500 등락을 바꾼다. 리포트(오전 7시)보다 오래된 시세는 쓰지 않는다.
US_LIVE_SRC = ("https://api.github.com/repos/Sunbong-oh/market-dashboard/contents/quotes.json?ref=us-live",
               "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/us-live/quotes.json")
US_LIVE_JS = r"""<script>(function(){var SRC=%s,SINCE='__SINCE__';
function f(v,d){return v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})}
function c(v){return v>0?'up':v<0?'down':'flat'}
function apply(j){if(!j||!j.data||!(j.time>=SINCE))return;var hm=j.time.slice(5,16).replace('-','/');
 document.querySelectorAll('article.card').forEach(function(card){var s=card.querySelector('.sym');if(!s)return;
  var sym=s.textContent.split('\u00B7')[0].trim(),q=j.data[sym];if(!q)return;
  var y=sym==='^TNX',p=q.p,d=p-q.pc,pc=(p/q.pc-1)*100,pr=card.querySelector('.price'),b=pr.querySelector('.badge'),u=pr.querySelector('small');
  if(b&&sym==='^VIX')b.textContent=p<15?'\uc548\uc815':p<20?'\ubcf4\ud1b5':p<30?'\ubd88\uc548':'\uacf5\ud3ec';
  pr.innerHTML=(y?f(p,3)+'<small>%%</small>':'<small>'+(u?u.textContent:'')+'</small>'+f(p,2))+(b?' '+b.outerHTML:'');
  card.querySelector('.delta').innerHTML='<span class="'+c(d)+'">'+(y?(d>0?'+':'')+(d*100).toFixed(1)+'bp ':(d>0?'\u25B2':d<0?'\u25BC':'\u2013')+' '+f(Math.abs(d),2)+' ')+
   '('+(pc>0?'+':'')+pc.toFixed(2)+'%%)</span> <small class="lv">\u00B7 \uc2e4\uc2dc\uac04 '+hm+'</small>'});
 var IX={'\ub098\uc2a4\ub2e5':'^IXIC','S&P500':'^GSPC'};
 document.querySelectorAll('.ix').forEach(function(x){var k=x.dataset.sym||IX[(x.firstChild&&x.firstChild.nodeValue||'').trim()],q=j.data[k],b=x.querySelector('b');if(!q||!b)return;
  var v=(q.p/q.pc-1)*100;b.className=c(v);b.textContent=(v>0?'+':'')+v.toFixed(2)+'%%'})}
function load(i){i=i||0;if(i>=SRC.length)return;
 fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
 .then(function(r){if(!r.ok)throw 0;return r.json()}).then(apply).catch(function(){load(i+1)})}
load();setInterval(function(){if(!document.hidden)load()},60000)})()</script>""" % json.dumps(list(US_LIVE_SRC))


def with_us_live(html, since):
    """since: 'YYYY-MM-DD HH:MM'(KST) — 이보다 오래된 실시간 시세는 무시 (지난 리포트를 덮어쓰지 않게)."""
    js = US_LIVE_JS.replace("__SINCE__", since)
    i = html.lower().rfind("</body>")
    return html[:i] + js + html[i:] if i >= 0 else html + js


def embed_html(html, btc_live=False):
    """홈 화면에 통째로 끼워 넣을 원본 리포트 (메뉴 없이, 링크는 바깥 창에서 열림)."""
    if btc_live:
        i = html.lower().rfind("</body>")
        html = html[:i] + BTC_LIVE + html[i:] if i >= 0 else html + BTC_LIVE
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
    lis = "".join(f'<li>{"<span class=rel>관련주</span>" if n.get("rel") else ""}<a href="{escape(n["link"])}" target="_blank" rel="noopener">{escape(n["title"])}</a>'
                  f'<div class="src">{escape(n["src"])} · {datetime.fromtimestamp(n["ts"], d.KST):%m/%d %H:%M}</div></li>'
                  for n in items[:limit])
    return f'<ol class="items">{lis}</ol>'


# ---------- 오전 데일리 ----------
# '주요 지표' 제목 옆 주황 버튼 → 그날 미국 52주 신고가 페이지 (맵 버튼과 같은 모양·흔들리는 '터치!')
NH_CSS = ("<style>.nh-btn{display:inline-block;margin-left:10px;padding:3px 10px;border-radius:8px;background:#F39800;color:#fff!important;"
          "font-size:13px;font-weight:800;text-decoration:none;vertical-align:2px;letter-spacing:0}"
          ".nh-hint{display:inline-block;margin-left:6px;color:#F39800;font-size:13px;font-weight:800;vertical-align:2px;"
          "animation:nhwig 1s ease-in-out infinite}@keyframes nhwig{0%,100%{transform:translateX(0)}50%{transform:translateX(-6px)}}</style>")


def newhighs_count(day_dir):
    try:
        m = re.search(r'신고가 종목</span><b[^>]*>(\d+)', (day_dir / "newhighs.html").read_text(encoding="utf-8"))
        return int(m.group(1)) if m else None
    except OSError:
        return None


def with_newhighs(html, href, n):
    btn = (f'<a class="nh-btn" href="{href}" target="_top">🚀 52주 신고가{f" {n}종목" if n else ""}</a>'
           '<span class="nh-hint">&lt;--- 터치!</span>')
    html, k = re.subn(r'(<h2 class="ind-h">[^<]*)', lambda m: m.group(1) + btn, html, count=1)
    if not k:
        return html
    return re.sub(r"</head>", lambda _: NH_CSS + "</head>", html, count=1, flags=re.I)


def build_daily():
    out = OUT / "daily"
    days = dated_dirs(DAILY)
    for p in days:
        dest = out / p.name
        dest.mkdir(parents=True, exist_ok=True)
        nh = (p / "newhighs.html").exists()
        for f in p.iterdir():
            if f.suffix == ".html":
                html = daily_grid3(f.read_text(encoding="utf-8"))
                if nh and f.name == "index.html":
                    html = with_newhighs(html, "newhighs.html", newhighs_count(p))
                if p == days[0] and f.name == "index.html":
                    html = with_us_live(html, f"{p.name} 06:30")
                dest.joinpath(f.name).write_text(with_nav(html, "../../", "daily/"), encoding="utf-8")
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
        eh = daily_grid3(html)
        if (p / "newhighs.html").exists():
            eh = with_newhighs(eh, "newhighs.html", newhighs_count(p))
        (out / p.name / "embed.html").write_text(embed_html(with_us_live(eh, f"{p.name} 06:30"), btc_live=True), encoding="utf-8")
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
    nhd = next((p for p in dated_dirs(DAILY) if (p / "newhighs.html").exists()), None)
    if nhd:
        html = with_newhighs(html, f"../{nhd.name}/newhighs.html", newhighs_count(nhd))
    (dest / "index.html").write_text(with_nav(html, "../../", "daily/"), encoding="utf-8")
    (dest / "embed.html").write_text(embed_html(html, btc_live=True), encoding="utf-8")
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


def stock_price(code):
    """네이버 증권 현재가 (사이트를 만들 때 값, 장중엔 약 2시간마다 갱신)."""
    if not code:
        return None
    try:
        r = json.loads(_get(f"https://m.stock.naver.com/api/stock/{code}/basic"))
    except Exception as e:
        print("현재가 실패:", code, type(e).__name__, e, file=sys.stderr)
        return None
    num = lambda v: float(str(v).replace(",", "").replace("+", "")) if v not in (None, "") else None
    try:
        price = num(r.get("closePrice"))
        chg = num(r.get("compareToPreviousClosePrice"))
        pct = num(r.get("fluctuationsRatio"))
    except ValueError:
        return None
    if price is None:
        return None
    kind = str((r.get("compareToPreviousPrice") or {}).get("name") or "")
    if chg is not None and kind in ("FALLING", "LOWER_LIMIT") and chg > 0:
        chg, pct = -chg, -abs(pct or 0)
    at = re.sub(r"\D", "", str(r.get("localTradedAt") or ""))[:12]
    return dict(price=price, chg=chg or 0, pct=pct or 0, at=at, status=str(r.get("marketStatus") or ""))


def stock_info(name, fname):
    txt = (WATCH / fname).read_text(encoding="utf-8")
    code = stock_code(name, txt)
    info = dict(name=name, fname=fname, code=code, price=stock_price(code), news=stock_news(name, code), dis=stock_disclosures(code), rep=stock_reports(code))
    print(f"관심종목 {name}({code or '?'}): 현재가 {info['price'] and info['price']['price']} 공시 {len(info['dis'])} 리포트 {len(info['rep'])} 뉴스 {len(info['news'])}", file=sys.stderr)
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
.px{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;margin:2px 0 4px}.px b{font-size:20px}.px span{font-weight:800;font-size:15px}
.px small{flex-basis:100%;font-size:12px;color:var(--muted)}.px.up b,.px.up span{color:#e03131}.px.dn b,.px.dn span{color:#1c6dd0}
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
   if(navigator.share){navigator.share({title:cur+'님 투자사이트',text:cur+'님 투자사이트',url:url}).catch(function(){})}
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
        pr = x.get("price")
        if pr:
            cls = "up" if pr["chg"] > 0 else "dn" if pr["chg"] < 0 else ""
            arrow = "▲" if pr["chg"] > 0 else "▼" if pr["chg"] < 0 else "-"
            when = f'{pr["at"][4:6]}/{pr["at"][6:8]} {pr["at"][8:10]}:{pr["at"][10:12]}' if len(pr["at"]) >= 12 else ""
            price_html = (f'<div class="px {cls}"><b>{pr["price"]:,.0f}원</b> <span>{arrow} {abs(pr["chg"]):,.0f} '
                          f'({pr["pct"]:+.2f}%)</span><small>{when} 기준{" · 장 마감" if pr["status"] == "CLOSE" else ""}</small></div>')
        else:
            price_html = '<div class="px"></div>' if x["code"] else ""

        rep_html = f'<h4>📝 증권사 리포트</h4>{_mini(rep, "")}' if rep else ""
        cards.append(
            f'<div class="card stk" data-name="{escape(x["name"])}" data-code="{escape(x["code"] or "")}"><h3>{escape(x["name"])}{code}'
            f'<label class="adm"><input type="checkbox"> 이 손님 종목</label>'
            f'<a class="x adm" href="{REPO_URL}/delete/main/watchlist/{escape(x["fname"])}" target="_blank" rel="noopener">삭제</a></h3>{price_html}'
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
            f'<div class="stks">{cards}</div>{empty}</section>{STOCK_JS}{PRICE_JS % json.dumps([u.replace("snapshot.json", "prices.json") for u in SNAP_SRC])}')


# 관심 종목 현재가: kb-market-report 실시간 작업이 평일 08:00~16:05 1분마다 flow-live/prices.json 에 올린다
# (종목 목록은 사이트가 만드는 stocks/codes.json). 사이트를 다시 빌드하지 않아도 1분마다 카드의 가격을 바꾼다.
PRICE_JS = r"""<script>
(function(){var SRC=%s;
 function f0(v){return Math.round(v).toLocaleString('ko-KR')}
 function apply(j){var P=(j&&j.data)||{};document.querySelectorAll('.card.stk[data-code]').forEach(function(c){
  var q=P[c.dataset.code],el=c.querySelector('.px');if(!q||!el||q.p==null)return;
  var cls=q.c>0?'up':q.c<0?'dn':'',ar=q.c>0?'▲':q.c<0?'▼':'-',at=String(q.at||'');
  el.className='px '+cls;el.innerHTML='<b>'+f0(q.p)+'원</b> <span>'+ar+' '+f0(Math.abs(q.c))+' ('+(q.r>0?'+':'')+Number(q.r).toFixed(2)+'%%)</span><small>'+
   (at.length>=12?at.slice(4,6)+'/'+at.slice(6,8)+' '+at.slice(8,10)+':'+at.slice(10,12)+' 기준':'')+(q.st==='CLOSE'?' · 장 마감':' · 실시간')+'</small>'})}
 function load(i){i=i||0;if(i>=SRC.length)return;
  fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(apply).catch(function(){load(i+1)})}
 load();setInterval(function(){if(!document.hidden)load()},60000);
 document.addEventListener('visibilitychange',function(){if(!document.hidden)load()})})();
</script>"""


def build_stocks(now):
    from concurrent.futures import ThreadPoolExecutor
    names = watchlist()
    with ThreadPoolExecutor(8) as ex:
        stocks = list(ex.map(lambda nf: stock_info(*nf), names))
    body = stocks_block(stocks)
    (OUT / "stocks").mkdir(parents=True, exist_ok=True)
    # 실시간 작업이 1분마다 현재가를 받을 종목 코드 목록
    (OUT / "stocks" / "codes.json").write_text(json.dumps(sorted({x["code"] for x in stocks if x["code"]})), encoding="utf-8")
    (OUT / "stocks" / "index.html").write_text(
        page("관심 종목 뉴스", body, "../", "stocks/", "MY STOCKS",
             f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 수집 · 종목별 공시·리포트·최근 7일 기사"), encoding="utf-8")
    return dict(body=body, at=now, n=len(stocks))


# ---------- 관심 테마 뉴스 (Claude 루틴이 일~목 21:00에 theme_news/<발송일>.html 커밋) ----------
THEME_ARCHIVE = ROOT / "archive" / "theme"
INDEX_KPI = re.compile(r"나스닥|다우|S&P|코스피|코스닥|러셀|SOX|필라델피아|반도체지수|지수")


def build_theme():
    """가장 최근 테마 뉴스 카드(4장)를 사이트에 넣는다. theme_news/ 와 archive/theme/ 중 최신 날짜."""
    if not d.THEME_ON:
        return None
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
    html = d.reshape_theme(files[day].read_text(encoding="utf-8"))[0]  # 첫 카드 빼고 AI 카드 2장 합치기 (데일리·텔레그램과 같게)
    # 카드는 540px 고정 폭이라 화면 폭에 맞춰 늘고 줄게 바꾸고, 지수 등락 박스(나스닥 등)는 뺀다
    # 카드는 한 장씩 세로로, 여백·글자를 줄여 한 장의 크기를 작게 한다
    fit = ("<style>html,body{margin:0!important;overflow:hidden}body{background:transparent!important}"
           ".card{width:auto!important;max-width:540px;margin:0 auto 10px!important;padding:12px 12px 10px!important}"
           ".topbar{margin-bottom:8px!important;padding-bottom:4px!important}.house{font-size:13px!important}.meta{font-size:11.5px!important}"
           ".tag{font-size:11px!important;margin-bottom:4px!important}h1{font-size:19px!important}.sect{font-size:13.5px!important;margin-bottom:8px!important}"
           "h2{font-size:16px!important;border-left-width:4px!important;padding-left:7px!important}h2 small{font-size:12px!important}"
           ".t{font-size:14.5px!important}.p{font-size:14px!important}.w{font-size:12.5px!important;margin-top:1px!important}"
           ".sub{font-size:12.5px!important;margin:8px 0 2px!important}.quiet{font-size:13px!important}.next div{font-size:13px!important;padding:5px 0!important}"
           ".next b{min-width:90px!important}.legend,.foot{font-size:11px!important}.b{width:24px!important;height:24px!important;font-size:13px!important}"
           ".sub2{font-size:15px!important;border-left-width:4px!important;padding-left:7px!important;margin:12px 0 4px!important}.kpi{padding:7px 10px!important;margin-bottom:6px!important}.kpi .v{font-size:19px!important}.kpi .n{font-size:13px!important}.kpi .s{font-size:11.5px!important}"
           "</style>")
    html = html.replace("</head>", fit + "</head>", 1) if "</head>" in html else fit + html
    html = re.sub(r'<div class="kpi"><div><div class="n">([^<]*)</div>.*?<div class="v[^"]*">[^<]*</div></div>',
                  lambda m: "" if INDEX_KPI.search(m.group(1)) else m.group(0), html)
    (OUT / "theme" / f"{day}.html").write_text(embed_html(html), encoding="utf-8")
    return dict(day=day, path=f"theme/{day}.html?v={VER}")


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
    kr = safe(d.fetch_kr_news, n=5)  # dashboard.market_news로 주가 관련 기사만 후보에 들어간다
    theme = safe(theme_news, limit=5)
    # 한 목록으로: 시장 영향 뉴스와 관련주 기사를 번갈아 넣고(같은 이야기는 하나만) 5개
    merged = []
    for pair in zip(kr + [None] * 5, theme + [None] * 5):
        for it in pair:
            if it and len(merged) < 5 and all(len(d._grams(it["title"]) & d._grams(m["title"])) < 4 for m in merged):
                merged.append(dict(it, rel=it in theme))
    body = (f'{theme_block(theme_doc, "")}'
            f'<section class="panel"><div class="tag">오늘 한국 시장에 영향 줄 뉴스 · 관련주</div>'
            f'<p class="meta">직전 한국 장 마감 이후 여러 언론이 크게 다룬 시장 뉴스와 관련주 기사 중 5개'
            f' (정치·사회, 칼럼·종목 추천성 기사 제외)</p>{news_items(merged)}</section>')
    (OUT / "news").mkdir(parents=True, exist_ok=True)
    news_page_body = (body.replace(f'src="{theme_doc["path"]}"', f'src="../{theme_doc["path"]}"')
                      if theme_doc else body)
    (OUT / "news" / "index.html").write_text(
        page("돈이 되는 뉴스", f'<style>{HOME_CSS}</style>' + news_page_body + FIT_JS, "../", "news/", "MONEY NEWS",
             f"{now:%Y-%m-%d}({WD[now.weekday()]}) {now:%H:%M} KST 수집 · 하루 여러 번 자동 갱신"), encoding="utf-8")
    return dict(kr=merged, theme=[], at=now, body=body)


# ---------- 장마감 리포트 ----------
IMG_ORDER = ("1_시장", "2_수급", "3_강세테마", "3_강세업종")


def star_red(s):
    """일정의 ★ 핵심 항목은 빨간 굵은 글씨로."""
    return re.sub(r"★([^·]+)", r'<b style="color:#e03131">★\1</b>', s)


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
            ul.append(star_red(escape(s[2:] if s.startswith("- ") else s)))
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


FUT_CSS = """<style>
.fut{font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#1c2330}
.fut .badge2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 0 10px}
.fut .badge2>div{border-radius:12px;padding:9px 12px;background:#f4f5f8}.fut .badge2 .k{display:block;font-size:12.5px;font-weight:700;color:#6b7385}
.fut .badge2 b{display:block;font-size:22px;letter-spacing:-.4px;line-height:1.25}.fut .badge2 .fg b{font-size:26px}
.fut .badge2 .c{display:block;font-size:13px;font-weight:800}.fut .badge2 .fu .c{white-space:nowrap;font-size:13.5px}
.fut .badge2 .fu .k{color:#15803d;font-size:14px;font-weight:800}
.fut .badge2 .up{background:#fff0f0}.fut .badge2 .up b,.fut .badge2 .up .c{color:#e03131}
.fut .badge2 .dn{background:#eef4ff}.fut .badge2 .dn b,.fut .badge2 .dn .c{color:#1c6dd0}
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
 /* 장중에는 가로축을 08:45~(마지막 기록+30분)으로 줄여 지금까지의 흐름을 넓게 보여 준다. 장 마감 뒤엔 하루 전체 */
 var lastM=Math.max(lf[0],hf?fl[fl.length-1][0]:0),END=live?Math.min(420,Math.max(lastM+30,90)):420;
 var W=640,H=310,L=92,R=548,T=14,B=262,x=function(m){return L+(R-L)*m/END};
 var sc=function(v){var lo=Math.min.apply(0,v),hi=Math.max.apply(0,v);if(hi==lo){hi+=1;lo-=1}var pd=(hi-lo)*.06;lo-=pd;hi+=pd;
   return {lo:lo,hi:hi,y:function(a){return B-(B-T)*(a-lo)/(hi-lo)}}};
 var sf=sc(bars.map(function(p){return p[1]})),sg=hf?sc(fl.map(function(p){return p[1]})):null;
 /* 두 축의 비율 고정: 선물 지수 2포인트 = 외국인 200억(1포인트 = 100억). 더 크게 움직인 쪽에 맞춰 둘 다 같은 비율로 */
 if(hf){var RATIO=100,span=Math.max(sf.hi-sf.lo,(sg.hi-sg.lo)/RATIO),fm=(sf.hi+sf.lo)/2,gm=(sg.hi+sg.lo)/2;
  var mk=function(lo,hi){return {lo:lo,hi:hi,y:function(a){return B-(B-T)*(a-lo)/(hi-lo)}}};
  sf=mk(fm-span/2,fm+span/2);sg=mk(gm-span*RATIO/2,gm+span*RATIO/2)}
 var path=function(ps,y){return 'M'+ps.map(function(p){return x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)}).join(' L')};
 var n0=function(v){return Math.round(v).toLocaleString('ko-KR')},sg0=function(v){return (v>0?'+':v<0?'-':'')+n0(Math.abs(v))};
 var f2=function(v){return v.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2})};
 var step=[15,30,60,90].filter(function(s){return END/s<=6})[0]||90,tk=[];
 for(var m=15;m<=END;m+=step){var hm=m+525;tk.push(('0'+Math.floor(hm/60)).slice(-2)+('0'+hm%60).slice(-2))}
 var grid=tk.map(function(t){var X=x(tm(t));return '<line x1="'+X+'" y1="'+T+'" x2="'+X+'" y2="'+B+'" stroke="#e3e6ec"/>'+
  '<text x="'+X+'" y="'+(B+24)+'" text-anchor="middle">'+t.slice(0,2)+':'+t.slice(2)+'</text>'}).join('');
 var fsvg='';
 if(hf){var yz=sg.y(0);
  var z0=sg.lo<0&&sg.hi>0;  /* 외국인 선은 자기 범위로 꽉 차게(0을 억지로 넣지 않음), 0선은 범위 안일 때만 */
  fsvg=(z0?'<line x1="'+L+'" y1="'+yz.toFixed(1)+'" x2="'+R+'" y2="'+yz.toFixed(1)+'" stroke="#e03131" stroke-dasharray="4 4" opacity=".45"/>':'')+
   '<text x="'+(R+6)+'" y="'+(T+12)+'" fill="#e03131">'+sg0(sg.hi)+'</text><text x="'+(R+6)+'" y="'+(B+4)+'" fill="#e03131">'+sg0(sg.lo)+'</text>'+
   (z0&&yz-T>=24&&B-yz>=20?'<text x="'+(R+6)+'" y="'+(yz+5).toFixed(1)+'" fill="#e03131">0</text>':'')+
   '<path d="'+path(fl,sg.y)+'" fill="none" stroke="#e03131" stroke-width="3.2" stroke-linejoin="round"/>'+
   '<circle cx="'+x(fl[fl.length-1][0]).toFixed(1)+'" cy="'+sg.y(fl[fl.length-1][1]).toFixed(1)+'" r="5" fill="#e03131"/>'}
 var svg='<svg viewBox="0 0 '+W+' '+H+'" width="100%" role="img" aria-label="KOSPI200 선물과 외국인 선물 순매수 누적 교차 차트" style="font:15px \'Malgun Gothic\',sans-serif;fill:#6b7385;display:block">'+
  '<rect x="'+L+'" y="'+T+'" width="'+(R-L)+'" height="'+(B-T)+'" fill="#fafbfc" stroke="#e3e6ec"/>'+grid+
  '<text x="'+(L-6)+'" y="'+(T+12)+'" text-anchor="end">'+f2(sf.hi)+'</text><text x="'+(L-6)+'" y="'+(B+4)+'" text-anchor="end">'+f2(sf.lo)+'</text>'+
  '<path d="'+path(bars,sf.y)+'" fill="none" stroke="#1c2330" stroke-width="1.4" stroke-linejoin="round" opacity=".7"/>'+fsvg+'</svg>';
 var ch=prev!=null?last-prev:null,pct=ch!=null&&prev?ch/prev*100:0,cls=ch>0?'up':ch<0?'dn':'';
 var back=hf?fl.filter(function(p){return p[0]<=fl[fl.length-1][0]-30}):[],d30=back.length?fg-back[back.length-1][1]:null;
 var gc=fg>0?'up':fg<0?'dn':'';
 var badge='<div class="badge2">'+(fg!=null?'<div class="fg '+gc+'"><span class="k">외국인 선물 누적 · 주간장'+(hf?'':' (마감)')+'</span><b>'+sg0(fg)+'억</b>'+
  '<span class="c">'+(fg>0?'순매수':fg<0?'순매도':'')+(d30!=null?' · 30분 '+(d30>0?'▲':d30<0?'▼':'')+n0(Math.abs(d30))+'억 '+(d30>0?'사는 중':d30<0?'파는 중':''):'')+'</span></div>':'')+
  (ch!=null?'<div class="fu '+cls+'"><span class="k">KOSPI200 선물</span><b>'+f2(last)+'</b><span class="c">'+(ch>0?'▲':ch<0?'▼':'')+
  f2(Math.abs(ch))+' ('+(pct>0?'+':'')+pct.toFixed(2)+'%)</span></div>':'')+'</div>';
 var rest=hf?(d.flows||[]).slice(-1)[0]||{}:cf,oth=['기관계','개인'].filter(function(k){return rest[k]!=null}).map(function(k){return k+' '+sg0(rest[k])}).join(' · ');
 var hh=lf[0]+525,hhmm=Math.floor(hh/60)+':'+('0'+hh%60).slice(-2);
 el.innerHTML=badge+'<p class="lg">'+(hf?'<b style="color:#e03131">━ 외국인 순매수 누적</b> (우, 억원) · ':'')+
  '<b style="color:#495057">━ KOSPI200 선물</b> (좌) '+f2(last)+'<br><span style="font-size:12px">※ 주간장 기준(08:45~15:45) · 야간장 미포함 — MTS·HTS 투자자동향(야간 포함)과 다를 수 있음</span></p>'+svg+
  '<p class="note">'+(live?'<span class="dot"></span>'+hhmm+' 기준 · 1분마다 기록, 화면은 1~2분마다 자동 갱신':
  (hf?'회사 PC 서버가 08:45~15:45 1분마다 기록한 값 (서버가 꺼져 있던 시간은 비어 있음)':'외국인 분 단위 추이는 회사 PC 기록이 있는 날부터 함께 그려집니다'))+'</p>';
 return true}
</script>"""


def _fut_data(d):
    keep = ("t", "외국인", "기관계", "개인")
    return {"futures": d.get("futures"), "bars": [{"t": b["t"], "c": b.get("c")} for b in d.get("bars") or []],
            "flows": [{k: r[k] for k in keep if k in r} for r in d.get("flows") or []],
            "current_flows": {k: v for k, v in (d.get("current_flows") or {}).items() if k in keep}}


# 리포트의 '투자자별 순매수' 카드는 스크립트가 나중에 그리므로, 다 그려지면 차트를 '선물 · 옵션' 막대 바로 아래로 옮긴다
FUT_MOVE_JS = """<style>.fut.in-report{border:0;border-top:1px solid #e3e6ec;border-radius:0;padding:14px 0 0;margin:14px 0 0;background:none}
.fut.in-report h3{font-size:15px;margin:0 0 8px;color:#1c2330}</style><script>
(function(){var box=document.getElementById('futbox');if(!box)return;
 var t=setInterval(function(){var inv=document.getElementById('investors');
  var g=inv&&[].filter.call(inv.querySelectorAll('.inv-group'),function(e){var h=e.querySelector('h4');return h&&/옵션/.test(h.textContent)})[0];
  if(g&&g.nextElementSibling!==box){box.classList.add('in-report');g.parentNode.insertBefore(box,g.nextSibling)}
  },1000)})();
</script>"""


def final_flows(raw, day_dir):
    """KB 실시간 투자자별 선물 순매수는 15:35 동시호가부터 멈췄다가 장 뒤에 최종값으로 바뀐다(예: 15:35~45 -44억 → 최종 +3,897억).
    장마감 리포트(장 뒤 작성)의 투자자별 값을 15:45 마지막 점과 현재값으로 넣어 리포트 수치와 맞춘다."""
    h = next(day_dir.glob("*.html"), None)
    txt = h.read_text(encoding="utf-8") if h else ""
    i = txt.find('"/api/market": {')
    if i < 0:
        return
    m = json.JSONDecoder().raw_decode(txt[txt.index("{", i):])[0]
    fin = {r.get("name"): r.get("futures") for r in m.get("investors") or [] if r.get("futures") is not None}
    if not any(fin.get(k) for k in ("외국인", "기관계", "개인")):  # 장 마감 약 1시간 뒤 KB가 0으로 초기화한 값은 쓰지 않는다
        return
    cur = raw.setdefault("current_flows", {})
    cur.update({k: v for k, v in fin.items()})
    fl = raw.get("flows") or []
    keys = ("외국인", "기관계", "개인")
    last = {"t": "1545", **{k: fin[k] for k in keys if k in fin}}
    raw["flows"] = [r for r in fl if r.get("t", "") < "1545"] + [last]


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
        final_flows(raw, day_dir)
        data = json.dumps(_fut_data(raw), ensure_ascii=False).replace("</", "<\\/")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""
    return (f'{FUT_CSS}<div class="box fut" id="futbox"><h3>선물지수 · 외국인 선물 순매수 (분 단위)</h3><div></div></div>{FUT_JS}'
            f'<script>(function(b){{if(!futChart(b.lastChild,{data}))b.remove()}})'
            f'(document.currentScript.previousElementSibling.previousElementSibling)</script>{FUT_MOVE_JS}')


SNAP_SRC = ("https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/snapshot.json?ref=flow-live",
             "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/snapshot.json")
# 최신 장마감 리포트(embed·메뉴)에 붙인다: 평일 08:00~16:00에 회사 PC가 1분마다 올리는 오늘 스냅샷이 있으면
# 리포트가 읽는 데이터(window.__SNAPSHOT__)를 바꿔 끼워 실시간 수급으로 보여 준다. 없으면 전일 장마감 그대로.
LIVE_CLOSE_JS = """<style>body.live-close .site-extra .prev,body.live-close #report-title{display:none}</style><script>
(function(){var src=%s;
 function kst(){var n=new Date(Date.now()+9*3600e3);return {d:n.toISOString().slice(0,10).replace(/-/g,''),hm:n.toISOString().slice(11,16),wd:n.getUTCDay()}}
 /* 장중(08:00~16:10)은 실시간. 그 뒤에도 사이트가 아직 오늘 장마감 리포트로 다시 빌드되기 전(이 페이지가 지난 날짜)이면
    오늘 마지막 스냅샷(장마감 수급·외국인 선물 기록)을 그대로 보여 준다 */
 var DAY='__DAY__';
 function on(){var k=kst();return k.wd>0&&k.wd<6&&k.hm>='08:00'&&(k.hm<='16:10'||DAY!==k.d)}
 function apply(j){if(!j||j.date!==kst().d||!j.data||!j.data['/api/market'])return;
  window.__SNAPSHOT__=j.data;window.__SNAPSHOT_TIME__=j.time;document.body.classList.add('live-close');
  var b=document.getElementById('snapshot-banner');if(b){b.textContent=kst().hm>'16:10'?'📊 오늘 장마감 · '+j.time+' 기준':'🔴 실시간 · '+j.time+' 기준 (1분마다 갱신)';b.hidden=false}
  try{refreshFast();refreshSlow()}catch(e){}
  var f=j.data['/api/futures?minutes=1'],fb=document.getElementById('futbox');
  if(f&&fb&&window.futChart){fb.hidden=!futChart(fb.lastChild,f,true)}
  try{parent!==window&&parent.postMessage({liveClose:j.time,fut:f||null},'*')}catch(e){}}
 /* 리포트 페이지는 window.fetch를 스냅샷 읽기로 바꿔 두므로 XMLHttpRequest로 가져온다 */
 function load(i){i=i||0;if(i>=src.length)return;var x=new XMLHttpRequest();
  x.open('GET',src[i]+(i?'?t='+Date.now():''));if(!i)x.setRequestHeader('Accept','application/vnd.github.raw');
  x.onload=function(){if(x.status!==200)return load(i+1);try{apply(JSON.parse(x.responseText))}catch(e){}};
  x.onerror=function(){load(i+1)};x.send()}
 function tick(){if(on()&&!document.hidden)load(0)}
 tick();setInterval(tick,75000);document.addEventListener('visibilitychange',tick)})();
</script>""" % json.dumps(SNAP_SRC)


LIVE_HOME_JS = """<script>
(function(){var h=document.querySelector('#close .sec-h h2');
 addEventListener('message',function(e){var m=e.data;if(!m||!m.liveClose)return;
  var hm=new Date(Date.now()+9*3600e3).toISOString().slice(11,16);
  if(h){h.textContent=(hm>'16:10'?'📊 오늘 장마감 수급 · ':'📊 실시간 수급 · ')+m.liveClose;var a=h.parentNode.querySelector('a');if(a)a.textContent='전일 장마감 보기'}})})();
</script>"""


# 지수 미니차트: 리포트는 09:00~15:30 고정 축이라 장중엔 오른쪽이 비어 보인다 → 마지막 값까지만 그리도록 바꿔 끼운다
MINI_JS = r"""<script>
if(typeof drawMinis==='function'){drawMinis=function(){document.querySelectorAll('svg.mini').forEach(function(svg){
 var d=intraday[svg.dataset.id],pts=((d&&d.points)||[]).filter(function(p){return p.c!=null});
 var W=svg.clientWidth||200,H=64;svg.setAttribute('viewBox','0 0 '+W+' '+H);if(pts.length<2){svg.innerHTML='';return}
 var t0=d.recorded?toMin(pts[0].t):540,t1=Math.max(toMin(pts[pts.length-1].t),t0+30);
 var prev=d.prev_close!=null?d.prev_close:pts[0].c,vals=pts.map(function(p){return p.c}).concat([prev]);
 var lo=Math.min.apply(0,vals),hi=Math.max.apply(0,vals),span=hi-lo||1;
 var x=function(t){return 2+((toMin(t)-t0)/Math.max(1,t1-t0))*(W-4)},y=function(v){return H-14-((v-lo)/span)*(H-20)};
 var last=pts[pts.length-1].c,color=last>=prev?'var(--up)':'var(--down)',line=pts.map(function(p){return x(p.t)+','+y(p.c)}).join(' '),lx=x(pts[pts.length-1].t);
 svg.innerHTML='<polygon points="'+x(pts[0].t)+','+y(prev)+' '+line+' '+lx+','+y(prev)+'" fill="'+color+'" opacity=".12"/>'+
  '<line x1="0" x2="'+W+'" y1="'+y(prev)+'" y2="'+y(prev)+'" stroke="var(--muted)" stroke-dasharray="3 3" opacity=".7"/>'+
  '<polyline fill="none" stroke="'+color+'" stroke-width="1.8" stroke-linejoin="round" points="'+line+'"/>'+
  '<circle cx="'+lx+'" cy="'+y(last)+'" r="2.5" fill="'+color+'"/>'+
  '<text x="2" y="'+(H-1)+'">'+(d.recorded?hhmm(pts[0].t):'09:00')+'</text>'+
  '<text x="'+(W-2)+'" y="'+(H-1)+'" text-anchor="end">'+hhmm(pts[pts.length-1].t)+'</text>'})};try{drawMinis()}catch(e){}}
</script>"""


# 리포트 지수 목록에서 KOSPI200 선물 카드와 그 아래 등락 종목수 줄(#breadth)은 사이트에서 뺀다 (리포트가 15초마다 다시 그려서 계속 확인)
HIDE_IDX_JS = """<style>#breadth{display:none!important}.hts{display:none!important}
#indices .index .v{display:inline-block;margin-right:8px}#indices .index .v+div{display:inline-block;font-weight:700}
#investors .inv-group:first-child h4::after{content:"단위: 억원";float:right;font-size:13px;font-weight:600;color:#7a828c}#investors>p.muted{display:none!important}
.bar-row{grid-template-columns:64px 1fr 112px!important;font-size:14px!important}.bar-row .val{font-size:17px!important;font-weight:800!important}
.inv-cols.pair .bar-row{grid-template-columns:42px 1fr 58px!important;font-size:13px!important}.inv-cols.pair .bar-row .val{font-size:15.5px!important}
</style>""" + MINI_JS + """<script>document.querySelectorAll('.card-head h2').forEach(function(h){if(/투자자별 순매수/.test(h.textContent))h.textContent=h.textContent.replace('투자자별 순매수','투자자별 매매동향')});
setInterval(function(){document.querySelectorAll('#indices .index').forEach(function(e){
 var n=e.querySelector('.n');if(n&&/KOSPI200/.test(n.textContent))e.style.display='none'})},500)</script>"""


# 이슈 테마(같은 기사에 묶인 급등주, kb-market-report /api/themes 의 issues): 예전 리포트 코드로 그리는 화면(실시간 수급 등)에도
# 강세 테마 카드 맨 위에 넣는다. 새 리포트처럼 이미 그려져 있으면 그대로 둔다 (리포트가 다시 그려도 1초마다 확인).
ISSUE_JS = r"""<style>.theme-row.issue{background:rgba(243,152,0,.12);margin:0 -8px;padding:9px 8px;border-radius:8px}
.theme-row.issue .tname small{font-size:11px;font-weight:800;color:#fff;background:#F39800;padding:1px 6px;border-radius:6px;vertical-align:1px}
.theme-row.issue .tsum a{color:var(--muted);text-decoration:underline}</style><script>
(function(){function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function sg(v){return (v>0?'+':'')+Number(v).toFixed(2)+'%'}function c(v){return v>0?'up':v<0?'down':''}
 function f(){var box=document.getElementById('themes'),d=window.__SNAPSHOT__&&window.__SNAPSHOT__['/api/themes'],iss=d&&d.issues;
  if(!box||!iss||!iss.length||!box.querySelector('.theme-row')||box.querySelector('.theme-row.issue'))return;
  var h=iss.map(function(g){return '<div class="theme-row issue"><span class="rank">🔥</span><span class="tname">'+e(g.name)+' <small>이슈</small></span>'+
   '<span class="pct '+c(g.change_pct)+'">'+sg(g.change_pct)+'</span><span class="tsum">'+g.stocks.map(function(s){return '<b>'+e(s.name)+'</b> <span class="'+c(s.change_pct)+'">'+sg(s.change_pct)+'</span>'}).join(', ')+
   '<br>'+(g.url?'<a href="'+e(g.url)+'" target="_blank" rel="noopener">'+e(g.headline)+'</a>':e(g.headline))+'</span></div>'}).join('');
  var lead=box.querySelector('.theme-lead');
  if(lead){lead.insertAdjacentHTML('afterend',h);var b=lead.querySelector('b');if(b)b.insertAdjacentHTML('beforebegin','<b>'+iss.map(function(g){return e(g.name)}).join(' · ')+'</b> 이슈와 ')}
  else box.insertAdjacentHTML('afterbegin',h)}
 f();setInterval(f,1000)})();
</script>"""


def close_extra(lines, days, cur, prefix, chart=""):
    """차트 리포트 아래에 붙이는 블록: 선물·외국인 교차 차트, 실적·이슈·일정, 한 줄 요약, 날짜별 리포트 목록."""
    rest, one = close_extra_lines(lines)
    one_html = f'<div class="one">▶ {escape(one)}</div>' if one else ""
    body = f'<div class="box prev">{report_text(chr(10).join(rest))}{one_html}</div>' if rest or one else ""
    chips = "".join(f'<li><a href="{prefix}{p.name}/"{" class=on" if p.name == cur else ""}>{label(p.name)}</a></li>'
                    for p in days)
    return (f'{EXTRA_CSS}{HIDE_IDX_JS}{ISSUE_JS}{map_btn(prefix + "../map/")}<div class="site-extra">{chart}{body}'
            f'<div class="box"><h3>날짜별 장마감 리포트</h3><ul class="dates">{chips}</ul></div></div>')


def with_extra(html, extra):
    i = html.lower().rfind("</body>")
    return html[:i] + extra + html[i:] if i >= 0 else html + extra


def with_week_schedule(lines, day):
    """'금주의 일정'이 생기기 전(2026-10-13) 리포트에도 같은 증시 캘린더(kb-market-report/market_calendar.py)로 붙인다."""
    if any(t.startswith(("■ 금주의 일정", "■ 다음 주 일정")) for t in lines):
        return lines
    try:
        sys.path.insert(0, str(CLOSE.parent))
        import market_calendar as mc
        today = datetime.strptime(day, "%Y-%m-%d").date()
        title, week = mc._week_rest(today, mc.next_trading_day(today))
    except Exception as e:
        print("금주 일정 붙이기 실패:", type(e).__name__, e, file=sys.stderr)
        return lines
    finally:
        if sys.path and sys.path[0] == str(CLOSE.parent):
            sys.path.pop(0)
    if not week:
        return lines
    add = ["", f"■ {title}", *(f"- {lab}: " + " · ".join(vals) for lab, vals in week)]
    i = next((k for k, t in enumerate(lines) if t.startswith(("(★ 핵심", "▶"))), len(lines))
    return lines[:i] + add + lines[i:]


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
        lines = with_week_schedule(lines, p.name)
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
                latest_html = with_extra(with_nav(html, "../", "close/"), close_extra(lines, days, p.name, "", fchart) + LIVE_CLOSE_JS.replace("__DAY__", p.name.replace("-", "")))
                (out / "embed.html").write_text(with_extra(embed_html(html), close_extra(lines, days, p.name, "", fchart) + LIVE_CLOSE_JS.replace("__DAY__", p.name.replace("-", ""))),
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


# ---------- 목표주가 변동 (증권사 리포트 상향·하향) ----------
# kb-market-report Actions가 평일 08:00에 consensus/YYYY-MM-DD.json 을 올린다 (consensus_report.py).
TARGET_CSS = """
.tp-sum{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 6px}
.tp-sum b{display:inline-block;padding:4px 12px;border-radius:99px;background:var(--card);border:1px solid var(--line);font-size:14px}
.tp-sum b.up{color:#fff;background:var(--up);border-color:var(--up)}.tp-sum b.down{color:#fff;background:var(--down);border-color:var(--down)}
.tp{width:100%;border-collapse:collapse;font-size:15px;font-variant-numeric:tabular-nums}
.tp td{padding:9px 6px;border-top:1px solid var(--line);vertical-align:top}
.tp .co{font-weight:800;white-space:nowrap}.tp .pct{font-weight:800;text-align:right;white-space:nowrap}
.tp .px{white-space:nowrap;text-align:right}.tp .t{font-size:13px;color:var(--muted);margin-top:2px}
.up{color:var(--up)}.down{color:var(--down)}
.tp-one{font-size:16px;font-weight:800;background:color-mix(in srgb,var(--accent) 14%,transparent);border-radius:10px;padding:10px 12px;margin-top:12px}
.tp .m{display:none}
.src-n{font-size:11px;font-weight:700;color:#fff;background:#03c75a;border-radius:6px;padding:0 5px}
.tp-q{width:100%;padding:9px 12px;margin:2px 0 8px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:15px}
@media (max-width:520px){.tp{font-size:14px}.tp .ti{display:none}.tp .m{display:block}.tp .co{white-space:normal}}
"""


def src_tag(it):
    return ' <span class="src-n">네이버</span>' if it.get("source") == "네이버" else ""


def _won(v):
    return f"{v:,}" if v else "-"


def target_rows(items, cls, limit=None):
    rows = []
    for it in items[:limit]:
        op = f'{escape(it.get("prev_opinion") or "")}→{escape(it["opinion"])}' if it.get("opinion_changed") else escape(it.get("opinion") or "")
        title = escape(it.get("title") or "")
        if it.get("pdf"):
            title = f'<a href="{escape(it["pdf"])}" target="_blank" rel="noopener">{title}</a>'
        rows.append(f'<tr><td class="co">{escape(it["company"])}<div class="t">{escape(it["broker"])}{src_tag(it)} · {op}</div>'
                    f'<div class="t m">{title}</div></td><td class="ti">{title}</td><td class="px">{_won(it.get("prev_target"))} →<br><b>{_won(it.get("target"))}</b></td>'
                    f'<td class="pct {cls}">{it["pct"]:+.1f}%</td></tr>')
    return f'<table class="tp">{"".join(rows)}</table>' if rows else '<p class="err">없음</p>'


def target_split(items):
    up = sorted((i for i in items if i.get("pct") is not None and i["pct"] > 0), key=lambda i: -i["pct"])
    down = sorted((i for i in items if i.get("pct") is not None and i["pct"] < 0), key=lambda i: i["pct"])
    return up, down


def all_reports(items):
    """그날 정리한 리포트 전체(상향·하향·유지·신규·비교불가) - 종목·증권사 검색 가능."""
    def change(it):
        if it.get("pct") is None:
            return '<span class="t">신규·비교불가</span>'
        if it["pct"] == 0:
            return '<span class="t">유지</span>'
        return f'<b class="{"up" if it["pct"] > 0 else "down"}">{it["pct"]:+.1f}%</b>'
    rows = []
    for it in sorted(items, key=lambda i: (i["company"], i["broker"])):
        title = escape(it.get("title") or "")
        if it.get("pdf"):
            title = f'<a href="{escape(it["pdf"])}" target="_blank" rel="noopener">{title}</a>'
        key = escape(f'{it["company"]} {it.get("code", "")} {it["broker"]}'.lower())
        rows.append(f'<tr data-k="{key}"><td class="co">{escape(it["company"])}<div class="t">{escape(it["broker"])}{src_tag(it)} · '
                    f'{escape(it.get("opinion") or "-")}</div><div class="t m">{title}</div></td><td class="ti">{title}</td>'
                    f'<td class="px">{_won(it.get("target"))}</td><td class="pct">{change(it)}</td></tr>')
    return (f'<section class="panel report" id="all"><h3>📋 전체 리포트 ({len(items)}건)</h3>'
            '<input class="tp-q" type="search" placeholder="종목·증권사 검색 (예: 에이피알, 메리츠)" '
            'oninput="var q=this.value.trim().toLowerCase();document.querySelectorAll(\'#all tr\').forEach(function(r){'
            'r.style.display=!q||r.dataset.k.indexOf(q)>=0?\'\':\'none\'})">'
            f'<table class="tp">{"".join(rows)}</table></section>')


def build_target():
    out = OUT / "target"
    files = sorted((p for p in CONSENSUS.glob("*.json") if DATE_RE.match(p.stem)), key=lambda p: p.stem, reverse=True) \
        if CONSENSUS.is_dir() else []
    first = None
    dates = "".join(f'<li><a href="{{root}}{p.stem}/">{label(p.stem)}</a></li>' for p in files[:30])
    for i, p in enumerate(files[:60]):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = doc.get("items", [])
        up, down = target_split(items)
        keep = [i for i in items if i.get("pct") == 0]
        new = [i for i in items if i.get("pct") is None]
        opch = [i for i in items if i.get("opinion_changed")]
        one = next((ln.split(":", 1)[1].strip() for ln in doc.get("body", "").splitlines() if "한 줄 요약" in ln), "")
        body = (f'<style>{TARGET_CSS}</style>'
                f'<section class="panel"><div class="tp-sum"><b>리포트 {len(items)}건</b><b class="up">상향 {len(up)}</b>'
                f'<b class="down">하향 {len(down)}</b><b>유지 {len(keep)}</b><b>신규·비교불가 {len(new)}</b></div>'
                + (f'<div class="tp-one">▶ {escape(one)}</div>' if one else "") + '</section>'
                f'<section class="panel report"><h3>🔺 목표주가 상향 ({len(up)})</h3>{target_rows(up, "up")}</section>'
                f'<section class="panel report"><h3>🔻 목표주가 하향 ({len(down)})</h3>{target_rows(down, "down")}</section>')
        if opch:
            body += ('<section class="panel report"><h3>투자의견 변경</h3><ul>' + "".join(
                f'<li>{escape(i["company"])}: {escape(i.get("prev_opinion") or "")} → {escape(i["opinion"])} · {escape(i["broker"])}</li>'
                for i in opch) + '</ul></section>')
        body += all_reports(items)
        sub = f'{label(p.stem)} · {escape(doc.get("made", ""))} 기준 · 같은 증권사 직전 리포트 대비 · 데이터: 한경 컨센서스·네이버 증권 리서치'
        title = f'{label(p.stem)} 목표주가 변동'
        for dest, root in ((out / p.stem, "../../"),) + (((out, "../"),) if i == 0 else ()):
            dest.mkdir(parents=True, exist_ok=True)
            more = f'<section class="panel"><h3 style="margin:0 0 8px">지난 리포트</h3><ul class="dates">{dates.replace("{root}", "" if dest == out else "../")}</ul></section>'
            (dest / "index.html").write_text(page(title, body + more, root, "target/", "TARGET PRICE", sub), encoding="utf-8")
        if first is None:
            first = dict(day=p.stem, made=doc.get("made", ""), up=up, down=down, n=len(items), one=one)
    if first is None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page("목표주가 변동", '<p class="err">목표주가 변동 리포트를 불러오지 못했습니다.</p>',
                                             "../", "target/", "TARGET PRICE", "평일 오전 8시, 증권사 리포트 목표주가 상향·하향"),
                                        encoding="utf-8")
    return first


# ---------- 해외주식 리포트 (국내 증권사 미국주식 리포트 요약) ----------
# us_reports.py 가 us_reports/YYYY-MM-DD.json 을 만든다 (연합인포맥스 글로벌모니터 목록 = 한국투자증권 미국주식 리서치 메뉴).
US_CSS = """
.us .tp .op{white-space:nowrap;text-align:right;font-weight:800}
.us .tp .op .k{display:block;font-size:12px;font-weight:700;color:var(--muted)}
.us .op.dn{color:var(--down)}.us .op.upg{color:var(--up)}
.us .tp .tk{font-size:12px;font-weight:700;color:var(--muted);margin-left:4px}
.us .tp .tm{font-size:13px;color:var(--muted);white-space:nowrap}
.usf{vertical-align:-0.08em;margin-right:2px;border-radius:2px;box-shadow:0 0 0 1px rgba(0,0,0,.12)}
.us .tp .ds{font-size:13px;font-weight:600;color:var(--text);margin-top:3px;white-space:normal;line-height:1.45}
.us .tp .pr{width:1%;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
.us .tp .pr b{display:block;font-size:16px}.us .tp .pr .pc{display:block;font-weight:800;font-size:15px}
.us .tp .pr .nw,.us .tp .pr .nt{display:block;font-size:12px;color:var(--muted);font-weight:600}
@media (max-width:520px){.us .tp .ds,.us .tp .t.m{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
 .us .tp .co{white-space:normal}.us .tp .pr b{font-size:15px}}
.us .tp .sk{display:inline-block;font-size:11.5px;font-weight:700;padding:0 6px;margin-right:5px;border-radius:5px;
 background:#fff1dc;color:#1c2330;vertical-align:1px}
"""


# 국기 이모지(🇺🇸)는 윈도우 PC에서 'US' 글자로 보여서, 작은 SVG 국기를 직접 그린다
US_FLAG = ('<svg class="usf" viewBox="0 0 19 10" width="1.35em" height="0.72em" role="img" aria-label="미국">'
           + "".join(f'<rect y="{i * 10 / 13:.3f}" width="19" height="{10 / 13:.3f}" fill="{"#b22234" if i % 2 == 0 else "#fff"}"/>'
                     for i in range(13))
           + '<rect width="7.6" height="5.385" fill="#3c3b6e"/>'
           + "".join(f'<circle cx="{0.63 + c * 1.27 + (0.63 if r % 2 else 0):.2f}" cy="{0.54 + r * 1.07:.2f}" r="0.28" fill="#fff"/>'
                     for r in range(5) for c in range(6 if r % 2 == 0 else 5))
           + '</svg>')

def us_op(it):
    """종목명 아래 줄에 붙는 투자의견(제목에 있을 때)·리포트 종류."""
    chg = it.get("opinion_change") or ""
    op = f'{it.get("opinion", "")} {chg}'.strip()
    if op:
        cls = "down" if chg == "하향" else "up" if chg == "상향" else ""
        op = f' · <b class="{cls}">{escape(op)}</b>'
    return op + (f' · {escape(it["kind"])}' if it.get("kind") else "")


def _usd(v):
    return f"{v:,.2f}" if v else "-"


def _px(v):
    """좁은 칸용 가격: 1만 달러 이상은 소수점 생략."""
    return "-" if not v else f"{v:,.0f}" if v >= 10000 else f"{v:,.2f}"


def us_px(it):
    """맨 오른쪽 한 칸: 목표주가(컨센서스) / 상승여력 / 현재가."""
    q = it.get("quote") or {}
    if not q.get("price"):
        return '<td class="pr">-</td>'
    cur = "$" if q.get("currency", "USD") == "USD" else ""
    up = q.get("upside")
    tgt = f'<b>{cur}{_px(q["target"])}</b>' if q.get("target") else '<span class="nt">목표가 없음</span>'
    pct = f'<span class="pc {"up" if up > 0 else "down"}">{up:+.1f}%</span>' if up is not None else ""
    return f'<td class="pr">{tgt}{pct}<span class="nw">현재 {cur}{_px(q["price"])}</span></td>'


def short_broker(b):
    """신한투자증권 → 신한, 대신증권 → 대신 (좁은 화면용)."""
    return re.sub(r"(금융)?(투자)?증권$", "", b) or b


def us_rows(items, limit=None, stock=True):
    rows = []
    for it in items[:limit]:
        title = escape(it["headline"])
        if it.get("pdf"):
            title = f'<a href="{escape(it["pdf"])}" target="_blank" rel="noopener">{title}</a>'
        who = f'{escape(it["broker"])} · {escape(it["date"][5:].replace("-", "/"))} {escape(it.get("time", ""))}'
        key = escape(f'{it.get("company", "")} {it.get("ticker", "")} {it["broker"]} {it["headline"]}'.lower())
        if stock:
            who = f'{escape(short_broker(it["broker"]))} {escape(it["date"][5:].replace("-", "/"))}'
            q = it.get("quote") or {}
            desc = describe(it["ticker"], q.get("industry", ""))
            sec = sector_ko(q.get("sector", ""))
            about = (f'<div class="ds">{f"<span class=sk>{escape(sec)}</span>" if sec else ""}{escape(desc)}</div>'
                     if desc or sec else "")
            rows.append(f'<tr data-k="{key} {escape(desc.lower())} {escape(sec)}"><td class="co">{escape(it["company"])}<span class="tk">{escape(it["ticker"])}</span>'
                        f'{about}<div class="t">{who}{us_op(it)}</div><div class="t m">{title}</div></td><td class="ti">{title}</td>{us_px(it)}</tr>')
        else:
            rows.append(f'<tr data-k="{key}"><td>{title}<div class="t">{who}</div></td></tr>')
    return f'<table class="tp">{"".join(rows)}</table>' if rows else '<p class="err">없음</p>'


def us_one(items, stocks):
    """한 줄 요약: 종목 리포트 수, 가장 많이 낸 증권사, 의견 하향, 실적 프리뷰·리뷰 수."""
    if not items:
        return ""
    top = max({x["broker"] for x in items}, key=lambda b: sum(x["broker"] == b for x in items))
    parts = [f'종목 리포트 {len(stocks)}건', f'{top} 최다({sum(x["broker"] == top for x in items)}건)']
    pv = sum(x.get("kind") in ("Preview", "Review") for x in stocks)
    if pv:
        parts.append(f'실적 프리뷰·리뷰 {pv}건')
    dn = [x["company"] for x in stocks if x.get("opinion_change") == "하향"]
    if dn:
        parts.append("의견 하향 " + ", ".join(dn[:3]))
    return ", ".join(parts)


def build_us():
    out = OUT / "us"
    files = sorted((p for p in US_REPORTS.glob("*.json") if DATE_RE.match(p.stem)), key=lambda p: p.stem, reverse=True) \
        if US_REPORTS.is_dir() else []
    first = None
    dates = "".join(f'<li><a href="{{root}}{p.stem}/">{label(p.stem)}</a></li>' for p in files[:30])
    search = ('<input class="tp-q" type="search" placeholder="종목·티커·증권사 검색 (예: 마벨, MRVL, 키움)" '
              'oninput="var q=this.value.trim().toLowerCase();document.querySelectorAll(\'.us tr[data-k]\').forEach(function(r){'
              'r.style.display=!q||r.dataset.k.indexOf(q)>=0?\'\':\'none\'})">')
    for i, p in enumerate(files[:60]):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = doc.get("items", [])
        stocks = [x for x in items if x.get("ticker")]
        others = [x for x in items if not x.get("ticker")]
        one = us_one(items, stocks)
        body = (f'<style>{TARGET_CSS}{US_CSS}</style><div class="us">'
                f'<section class="panel"><div class="tp-sum"><b>리포트 {len(items)}건</b><b class="up">종목 {len(stocks)}</b>'
                f'<b>산업·시황 {len(others)}</b></div>' + (f'<div class="tp-one">▶ {escape(one)}</div>' if one else "")
                + f'{search}</section>'
                f'<section class="panel report"><h3>{US_FLAG} 종목 리포트 ({len(stocks)})</h3>{us_rows(stocks)}</section>'
                f'<section class="panel report"><h3>🌐 산업·시황 ({len(others)})</h3>{us_rows(others, stock=False)}'
                '<p class="t" style="margin-top:8px">제목을 누르면 리포트 원문(PDF)이 열립니다. 의견은 제목에 적힌 경우만 표시합니다. '
                f'오른쪽은 현재가 → 목표주가(애널리스트 평균 컨센서스, Yahoo Finance)와 상승여력이며 {escape(doc.get("made", "")[-5:])} 조회 기준입니다. '
                '자료: 연합인포맥스 글로벌모니터(한국투자증권 미국주식 리서치), 저작권은 각 증권사에 있습니다.</p></section></div>')
        sub = (f'{escape(doc.get("made", ""))} 기준 · {label(doc.get("since", p.stem))}부터 발간분 · '
               '국내 증권사 미국주식 리포트')
        title = f'{label(p.stem)} 해외주식 리포트'
        for dest, root in ((out / p.stem, "../../"),) + (((out, "../"),) if i == 0 else ()):
            dest.mkdir(parents=True, exist_ok=True)
            more = f'<section class="panel"><h3 style="margin:0 0 8px">지난 리포트</h3><ul class="dates">{dates.replace("{root}", "" if dest == out else "../")}</ul></section>'
            (dest / "index.html").write_text(page(title, body + more, root, "us/", "US EQUITY RESEARCH", sub), encoding="utf-8")
        if first is None:
            first = dict(day=p.stem, made=doc.get("made", ""), stocks=stocks, n=len(items), one=one)
    if first is None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page("해외주식 리포트", '<p class="err">해외주식 리포트를 불러오지 못했습니다.</p>',
                                             "../", "us/", "US EQUITY RESEARCH", "국내 증권사 미국주식 리포트"),
                                        encoding="utf-8")
    return first


def us_home(us):
    if not us or not us["stocks"]:
        return ""
    inner = (f'<div class="tp-sum"><b>리포트 {us["n"]}건</b><b class="up">종목 {len(us["stocks"])}</b></div>'
             f'<h3>{US_FLAG} 최신 종목 리포트</h3>{us_rows(us["stocks"], 5)}'
             + (f'<div class="tp-one">▶ {escape(us["one"])}</div>' if us["one"] else "")
             + f'<a class="btn" href="us/">해외주식 리포트 {us["n"]}건 전체 보기</a>')
    return (f'<section class="sec" id="us"><style>{TARGET_CSS}{US_CSS}</style><div class="sec-h"><h2>{US_FLAG} 해외주식 리포트</h2>'
            f'<a href="us/">{escape(us["day"][5:].replace("-", "/"))} {escape(us["made"][-5:])} · 전체</a></div>'
            f'<section class="panel report us">{inner}</section></section>')


# ---------- 맵 (업종별 등락 트리맵) ----------
# kb-market-report Actions가 장중 5분마다 flow-live/map.json(네이버 증권 업종별 종목 등락)을 올린다.
# 업종 넓이 = 시가총액 합, 종목 넓이 = 시가총액, 색 = 등락률(-3%~+3%, 빨강 상승·파랑 하락).
MAP_SRC = [s.replace("snapshot.json", "map.json") for s in SNAP_SRC]
MAP_CSS = """
.mp-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin:4px 0 10px}
.mp-tabs{display:flex;gap:6px}.mp-tabs button{font:700 15px/1 inherit;padding:9px 16px;border-radius:10px;border:1px solid var(--line);
 background:var(--card);color:var(--text);cursor:pointer}.mp-tabs button.on{background:#1c2330;color:#fff;border-color:#1c2330}
.mp-idx{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}.mp-idx b{font-size:20px;margin-right:6px}
.mp-time{font-size:12.5px;color:var(--muted)}
.mp-sz{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin:0 0 8px;font-size:13px;color:var(--muted)}
.mp-sz span{font-weight:700;margin-right:2px}.mp-sz button{font:700 13px/1 inherit;padding:6px 10px;border-radius:8px;border:1px solid var(--line);
 background:var(--card);color:var(--text);cursor:pointer}.mp-sz button.on{background:#F39800;border-color:#F39800;color:#fff}
.mp-hot{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 10px;font-size:14px}.mp-hot b{font-size:13px;margin-right:2px}
.mp-hot span{background:var(--card);border:1px solid var(--line);border-radius:99px;padding:3px 10px;font-weight:700}
.mp-hot i{font-style:normal}.mp-hot em{font-style:normal;font-weight:800}.mp-hot .up{color:var(--up)}.mp-hot .down{color:var(--down)}
#map{position:relative;width:100%;background:#1f232b;border-radius:10px;overflow:hidden;user-select:none}
#map .sec{position:absolute;box-sizing:border-box;border:1px solid #1f232b;overflow:hidden}
#map .sec.thm{border:3px solid #ffd43b;z-index:1}#map .sec.thm .sh{background:#ffd43b;color:#1c2330}
#map .sh{position:absolute;left:0;right:0;top:0;height:17px;padding:0 4px;font:700 11.5px/17px system-ui,sans-serif;color:#fff;
 background:rgba(0,0,0,.38);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#map .st{position:absolute;box-sizing:border-box;border:1px solid rgba(20,22,28,.55);color:#fff;display:flex;flex-direction:column;
 align-items:center;justify-content:center;text-align:center;overflow:hidden;line-height:1.15;cursor:pointer;
 text-shadow:0 1px 1px rgba(0,0,0,.35)}
#map .st b{font-weight:700;white-space:nowrap}#map .st span{font-weight:600;opacity:.95}
.mp-leg{display:flex;justify-content:center;gap:2px;margin:10px 0 4px}.mp-leg span{min-width:44px;padding:4px 0;text-align:center;
 font:700 12px/1 system-ui,sans-serif;color:#fff;border-radius:3px}
.mp-info{min-height:22px;text-align:center;font-size:14px;font-weight:700;margin-top:6px}
@media (max-width:520px){#map{width:calc(100% + 32px);margin:0 -16px;border-radius:0}.mp-leg span{min-width:38px}}
"""
# 맵의 테마 묶음: 네이버 업종과 다르게 보고 싶은 종목을 원래 업종에서 빼 테마 칸 하나로 모은다.
#   sectors: 이 업종의 종목은 전부 테마로 / names: 다른 업종에 있어도 테마로 (네이버 증권 표기 이름, 없으면 건너뜀)
#   한 종목은 위에 적힌 테마 하나에만 들어간다.
MAP_THEMES = [
    {"name": "🔋 2차전지(테마)", "sectors": [], "names": [
        # 셀
        "LG에너지솔루션", "삼성SDI", "SK이노베이션",
        # 양극재·전구체·소재
        "포스코퓨처엠", "에코프로비엠", "에코프로", "에코프로머티", "엘앤에프", "LG화학", "코스모신소재", "코스모화학",
        "금양", "엔켐", "천보", "나노신소재", "대주전자재료", "솔루스첨단소재", "롯데에너지머티리얼즈", "SKC",
        "SK아이이테크놀로지", "더블유씨피", "후성", "레이크머티리얼즈", "에코앤드림", "포스코엠텍",
        # 장비·부품·리사이클
        "피엔티", "하나기술", "윤성에프앤씨", "성일하이텍", "신흥에스이씨", "상신이디피", "LS머트리얼즈"]},
    {"name": "⚓ 조선(테마)", "sectors": ["조선"], "names": [
        # 조선 업종 밖의 기자재·해양플랜트
        "동성화인텍", "성광벤드", "태광", "하이록코리아", "HJ중공업", "SK오션플랜트"]},
    {"name": "🛡️ 방산(테마)", "sectors": ["우주항공과국방"], "names": ["풍산", "SNT다이내믹스"]},
]

MAP_JS = r"""<script>
(function(){var SRC=%s,MAP=null,IDX=null,MK=location.hash=='#kosdaq'?'kosdaq':'kospi',el=document.getElementById('map');
 /* 칸 크기: sqrt=시총 제곱근(기본, 대형주 쏠림 완화) / cap=시총 그대로 / eq=업종 같은 크기 */
 var SZ='sqrt';try{SZ=localStorage.getItem('map-size')||'sqrt'}catch(x){}
 function sz(v){return SZ=='cap'?v:Math.sqrt(v)}
 var THEMES=%s;
 function themeOf(x,sec){for(var i=0;i<THEMES.length;i++){var t=THEMES[i];if(t.names.indexOf(x.n)>=0||t.sectors.indexOf(sec)>=0)return i}return -1}
 /* 테마 종목을 원래 업종에서 빼 테마 칸으로 모은다. 남은 업종의 시총·등락률은 남은 종목으로 다시 계산 */
 function wavg(st){var v=0,s=0;st.forEach(function(x){if(x.v>0){v+=x.v;s+=x.v*x.p}});return v?s/v:(st.length?st.reduce(function(t,x){return t+x.p},0)/st.length:0)}
 function regroup(data){var pick=THEMES.map(function(){return []}),out=[];
  data.forEach(function(s){var keep=[],moved=false;(s.st||[]).forEach(function(x){var t=themeOf(x,s.s);if(t>=0){pick[t].push(x);moved=true}else keep.push(x)});
   if(!moved){out.push(s);return}
   if(keep.length)out.push({s:s.s,st:keep,v:keep.reduce(function(t,x){return t+(x.v||0)},0),p:Math.round(wavg(keep)*100)/100})});
  pick.forEach(function(st,i){if(st.length)out.push({s:THEMES[i].name,theme:1,st:st,v:st.reduce(function(t,x){return t+(x.v||0)},0),p:Math.round(wavg(st)*100)/100})});
  return out}
 var NAME={kospi:'KOSPI',kosdaq:'KOSDAQ'};
 function col(p){var t=Math.min(Math.abs(p)/3,1),a=[64,68,78],b=p>0?[230,44,52]:[30,98,214];if(Math.abs(p)<0.05)t=0;
  return 'rgb('+a.map(function(v,i){return Math.round(v+(b[i]-v)*Math.pow(t,0.75))}).join(',')+')'}
 function sgn(p){return (p>0?'+':'')+p.toFixed(2)+'%%'}
 /* squarified treemap */
 function squarify(vals,x,y,w,h){var out=[],tot=vals.reduce(function(s,v){return s+v},0);if(!tot)return out;
  var items=vals.map(function(v,i){return {i:i,a:v/tot*w*h}}),k=0;
  function worst(row,side){var s=0,mx=0,mn=1e18;row.forEach(function(r){s+=r.a;mx=Math.max(mx,r.a);mn=Math.min(mn,r.a)});
   return Math.max(side*side*mx/(s*s),s*s/(side*side*mn))}
  while(k<items.length){var side=Math.min(w,h),row=[items[k]];k++;
   while(k<items.length&&worst(row.concat([items[k]]),side)<=worst(row,side)){row.push(items[k]);k++}
   var s=row.reduce(function(a,r){return a+r.a},0),thick=s/side,o=0;
   row.forEach(function(r){var len=r.a/thick;out[r.i]=w>=h?{x:x,y:y+o,w:thick,h:len}:{x:x+o,y:y,w:len,h:thick};o+=len});
   if(w>=h){x+=thick;w-=thick}else{y+=thick;h-=thick}}
  return out}
 /* 순서를 지키는 배치(앞쪽이 왼쪽 위): 합이 반이 되는 곳에서 목록을 둘로 나누고 긴 변을 자른다 */
 function ordered(vals,x,y,w,h){var out=[];
  (function go(lo,hi,x,y,w,h){if(hi<=lo)return;if(hi-lo==1){out[lo]={x:x,y:y,w:w,h:h};return}
   var tot=0,i,acc=0,k=lo+1,best=1e18;for(i=lo;i<hi;i++)tot+=vals[i];
   for(i=lo;i<hi-1;i++){acc+=vals[i];var d=Math.abs(acc-tot/2);if(d<best){best=d;k=i+1}}
   var left=0;for(i=lo;i<k;i++)left+=vals[i];var f=tot?left/tot:0.5;
   if(w>=h){go(lo,k,x,y,w*f,h);go(k,hi,x+w*f,y,w*(1-f),h)}else{go(lo,k,x,y,w,h*f);go(k,hi,x,y+h*f,w,h*(1-f))}})(0,vals.length,x,y,w,h);
  return out}
 function esc(s){return String(s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function draw(){var data=MAP&&MAP.data&&MAP.data[MK];document.querySelectorAll('.mp-tabs button').forEach(function(b){b.classList.toggle('on',b.dataset.m==MK)});
  idx();if(!data||!data.length){el.style.height='200px';el.innerHTML='<p style="color:#ccc;padding:20px">맵 데이터를 불러오는 중입니다…</p>';return}
  var W=el.clientWidth,H=Math.round(innerWidth<=640?Math.max(520,W*1.45):Math.max(560,W*0.62));el.style.height=H+'px';
  var secs=regroup(data).filter(function(s){return s.st&&s.st.length}),useCap=secs.every(function(s){return s.v>0});
  secs.forEach(function(s){s.kids=s.st.filter(function(x){return !useCap||x.v>0}).map(function(x){return {x:x,a:useCap?sz(x.v):1}})
   .sort(function(a,b){return b.a-a.a});s.a=!useCap?s.st.length:SZ=='eq'?1:SZ=='cap'?s.v:s.kids.reduce(function(t,k){return t+k.a},0)});
  /* 상승률이 높은 업종(테마)부터 왼쪽 위에 놓는다 */
  secs=secs.slice().sort(function(a,b){return b.p-a.p||b.a-a.a});hot(secs);
  var sv=secs.map(function(s){return s.a}),rs=ordered(sv,0,0,W,H),html='';
  secs.forEach(function(s,i){var r=rs[i];if(!r)return;var head=r.w>=46&&r.h>=40,top=head?17:0;
   html+='<div class="sec'+(s.theme?' thm':'')+'" style="left:'+r.x+'px;top:'+r.y+'px;width:'+r.w+'px;height:'+r.h+'px;background:'+col(s.p)+'" title="'+esc(s.s)+' '+sgn(s.p)+'" data-i="'+esc(s.s+' '+sgn(s.p))+'">';
   if(head){html+='<div class="sh">'+esc(s.s)+' '+sgn(s.p)+'</div>';
    var st=s.kids.map(function(k){return k.x}),vv=s.kids.map(function(k){return k.a}),rr=squarify(vv,0,top,r.w-2,r.h-top-2);
    st.forEach(function(x,j){var q=rr[j];if(!q)return;var nm=String(x.n||''),fs=Math.min(22,Math.sqrt(q.w*q.h)/5.2,(q.w-4)/nm.length);
     if(fs<9){fs=9;var c=Math.floor((q.w-4)/9)-1;nm=c>=2?nm.slice(0,c)+'…':''}
     var showN=nm&&q.h>fs*1.25,showP=showN&&q.h>fs*2.45;
     html+='<div class="st" style="left:'+q.x+'px;top:'+q.y+'px;width:'+q.w+'px;height:'+q.h+'px;background:'+col(x.p)+';font-size:'+fs.toFixed(1)+'px" data-i="'+esc(x.n+' '+sgn(x.p)+'  ·  '+s.s)+'">'+
      (showN?'<b>'+esc(nm)+'</b>':'')+(showP?'<span style="font-size:'+(fs*0.78).toFixed(1)+'px">'+sgn(x.p)+'</span>':'')+'</div>'})}
   else if(r.w>30&&r.h>14)html+='<div class="st" style="left:0;top:0;width:100%%;height:100%%;font-size:10px"><b>'+esc(String(s.s).slice(0,Math.max(2,Math.floor(r.w/10))))+'</b></div>';
   html+='</div>'});
  el.innerHTML=html;
  document.querySelector('.mp-time').textContent=(MAP.date?MAP.date.slice(4,6)+'/'+MAP.date.slice(6,8)+' ':'')+(MAP.time||'')+' 기준 · 네이버 증권 업종 · 5분마다 갱신'}
 function hot(secs){var box=document.querySelector('.mp-hot');if(!box)return;
  var top=secs.filter(function(s){return s.st.length>=3}).slice().sort(function(a,b){return b.p-a.p}).slice(0,5);
  box.innerHTML='<b>오늘 강한 업종</b>'+top.map(function(s){return '<span><i>'+esc(s.s)+'</i> <em class="'+(s.p>0?'up':s.p<0?'down':'')+'">'+sgn(s.p)+'</em></span>'}).join('')}
 function szBtns(){document.querySelectorAll('.mp-sz button').forEach(function(b){b.classList.toggle('on',b.dataset.z==SZ)})}
 document.querySelectorAll('.mp-sz button').forEach(function(b){b.onclick=function(){SZ=b.dataset.z;try{localStorage.setItem('map-size',SZ)}catch(x){}szBtns();draw()}});
 szBtns();
 function idx(){var box=document.querySelector('.mp-idx'),it=null;
  ((IDX&&IDX.indices)||[]).forEach(function(x){if(x.name==NAME[MK])it=x});
  if(!it){box.textContent=NAME[MK];return}
  var c=it.change>0?'var(--up)':it.change<0?'var(--down)':'var(--muted)';
  box.innerHTML=NAME[MK]+' <b>'+it.value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+'</b><span style="color:'+c+'">'+
   (it.change>0?'▲':it.change<0?'▼':'')+Math.abs(it.change).toFixed(2)+' ('+sgn(it.change_pct)+')</span>'}
 function get(name,cb,i){i=i||0;if(i>=SRC.length)return;var u=SRC[i].replace('map.json',name);
  fetch(i?u+'?t='+Date.now():u,{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(cb).catch(function(){get(name,cb,i+1)})}
 function load(){get('map.json',function(j){MAP=j;draw()});get('snapshot.json',function(j){IDX=(j.data||{})['/api/market'];idx()})}
 document.querySelectorAll('.mp-tabs button').forEach(function(b){b.onclick=function(){MK=b.dataset.m;history.replaceState(null,'','#'+MK);draw()}});
 el.addEventListener('click',function(e){var t=e.target.closest('[data-i]');if(t)document.querySelector('.mp-info').textContent=t.dataset.i});
 var lg='';[-3,-2,-1,0,1,2,3].forEach(function(p){lg+='<span style="background:'+col(p)+'">'+(p>0?'+':'')+p+'%%</span>'});
 document.querySelector('.mp-leg').innerHTML=lg;
 var rw;addEventListener('resize',function(){clearTimeout(rw);rw=setTimeout(draw,200)});
 draw();load();setInterval(function(){if(!document.hidden)load()},180000);
 document.addEventListener('visibilitychange',function(){if(!document.hidden)load()})})();
</script>"""


def build_map():
    body = (f'<style>{MAP_CSS}</style><div class="mp-top"><div class="mp-tabs"><button data-m="kospi" class="on">코스피</button>'
            f'<button data-m="kosdaq">코스닥</button></div><div class="mp-idx"></div></div>'
            f'<div class="mp-sz"><span>칸 크기</span><button data-z="sqrt" class="on">완만하게</button><button data-z="cap">시가총액</button>'
            f'<button data-z="eq">업종 같은 크기</button></div><div class="mp-hot"></div>'
            f'<div id="map"></div><div class="mp-info"></div><div class="mp-leg"></div>'
            f'<div class="mp-time" style="text-align:center"></div>' + MAP_JS % (json.dumps(MAP_SRC), json.dumps(MAP_THEMES, ensure_ascii=False)))
    dest = OUT / "map"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(page("🗺️ 맵 · 업종별 등락", body, "../", "map/", hero=False), encoding="utf-8")


# 리포트 지수 카드의 KOSPI·KOSDAQ 이름 옆 주황 '맵' 버튼 → 맵 페이지의 해당 시장 탭 (리포트가 15초마다 다시 그려서 계속 확인)
def map_btn(href):
    return ("<style>.map-btn{display:inline-block;margin-left:8px;padding:2px 9px;border-radius:7px;background:#F39800;color:#fff!important;"
            "font-size:12.5px;font-weight:800;text-decoration:none;vertical-align:1px;letter-spacing:0}"
            ".map-hint{display:inline-block;margin-left:6px;color:#F39800;font-size:12.5px;font-weight:800;vertical-align:1px;"
            "animation:mapwig 1s ease-in-out infinite}@keyframes mapwig{0%,100%{transform:translateX(0)}50%{transform:translateX(-6px)}}"
            "</style><script>(function(){"
            "function f(){document.querySelectorAll('#indices .index .n').forEach(function(n){if(n.querySelector('.map-btn'))return;"
            "var t=n.textContent.trim(),m=t=='KOSPI'?'kospi':t=='KOSDAQ'?'kosdaq':'';"
            f"if(m)n.insertAdjacentHTML('beforeend','<a class=\"map-btn\" href=\"{href}#'+m+'\" target=\"_top\">맵</a><span class=\"map-hint\">&lt;--- 터치!</span>')}})}}"
            "f();setInterval(f,500)})()</script>")


# ---------- 홈 ----------
# 홈 한 페이지에서 스크롤만으로 오전 데일리 → 돈이 되는 뉴스 → 장마감 수급을 모두 본다.
# 데일리·장마감은 원본 HTML을 iframe에 넣고 내용 높이만큼 늘려 안쪽 스크롤이 생기지 않게 한다.
CLOSE_FIRST_JS = """<script>(function(){function f(){var n=new Date(Date.now()+9*3600e3),wd=n.getUTCDay(),hm=n.toISOString().slice(11,16);
 document.documentElement.classList.toggle('close-first',wd>0&&wd<6&&hm>='08:30'&&hm<'17:00')}f();setInterval(f,60000)})();</script>"""
HOME_CSS = """
.sec{scroll-margin-top:56px;margin-top:22px}
.home{display:flex;flex-direction:column}.home>.sec:first-child{margin-top:0}
/* 평일 08:30~17:00: 수급(실시간)을 맨 위로 - 순서만 바꾸므로 iframe을 다시 불러오지 않는다 */
.close-first .home #close{order:-1;margin-top:0}.close-first .home #daily{margin-top:22px}
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:0 0 10px}
.sec-h h2{margin:0}.sec-h a{font-size:13px;color:var(--muted)}
iframe.embed{display:block;width:100%;border:0;border-radius:14px;background:var(--card);min-height:400px}
@media (max-width:520px){iframe.embed{width:calc(100% + 32px);margin:0 -16px;border-radius:0}}
"""
FIT_JS = """<script>
/* 높이는 본문 내용 기준(documentElement.scrollHeight는 iframe 높이 이하로 줄지 않아, 내용이 줄면 회색 빈칸이 남는다) */
function fit(f){try{var d=f.contentDocument,b=d.body,z=parseFloat(d.documentElement.style.zoom)||1,cs=getComputedStyle(b);
 var h=Math.max(b.scrollHeight,b.getBoundingClientRect().height)+(parseFloat(cs.marginTop)||0)+(parseFloat(cs.marginBottom)||0);
 var l=b.lastElementChild;while(l&&(l.tagName=='SCRIPT'||l.tagName=='STYLE'||!l.getBoundingClientRect().height))l=l.previousElementSibling;
 if(l)h=Math.max(h,l.getBoundingClientRect().bottom+d.defaultView.scrollY+(parseFloat(getComputedStyle(l).marginBottom)||0));
 f.style.height=Math.ceil(h*z)+'px'}catch(e){}}
document.querySelectorAll('iframe.embed').forEach(function(f){f.addEventListener('load',function(){fit(f);
try{new ResizeObserver(function(){fit(f)}).observe(f.contentDocument.body)}catch(e){}
setTimeout(function(){fit(f)},800);setTimeout(function(){fit(f)},2500)})});
addEventListener('resize',function(){document.querySelectorAll('iframe.embed').forEach(fit)});
</script>"""


def target_home(target):
    if not target:
        return ""
    up, down = target["up"], target["down"]
    inner = (f'<div class="tp-sum"><b>리포트 {target["n"]}건</b><b class="up">상향 {len(up)}</b><b class="down">하향 {len(down)}</b></div>'
             f'<h3>🔺 상향 상위</h3>{target_rows(up, "up", 5)}<h3>🔻 하향 상위</h3>{target_rows(down, "down", 5)}'
             + (f'<div class="tp-one">▶ {escape(target["one"])}</div>' if target["one"] else "")
             + f'<a class="btn" href="target/#all">전체 리포트 {target["n"]}건 보기 (신규·유지 포함)</a>')
    return (f'<section class="sec" id="target"><style>{TARGET_CSS}</style><div class="sec-h"><h2>🎯 목표주가 변동</h2>'
            f'<a href="target/">{label(target["day"])} {escape(target["made"][-5:])} · 전체 보기</a></div>'
            f'<section class="panel report">{inner}</section></section>')


# 오늘의 핵심 이슈: kb-market-report 실시간 작업이 평일 08:00~16:05 5분마다 올리는 flow-live/issues.json
# (네이버 증권 주요뉴스를 같은 이야기끼리 묶어 기사가 가장 몰린 이슈 + 관련 종목·업종 등락). 평일 07:00~17:00, 오늘 것만 맨 위에.
ISSUE_SRC = [u.replace("snapshot.json", "issues.json") for u in SNAP_SRC]
ISSUE_CSS = """
#issue{order:-2}.close-first .home #issue+#daily{margin-top:22px}
.iss{background:var(--card);border:1px solid var(--line);border-left:5px solid #F39800;border-radius:14px;padding:14px 16px}
.iss h2{margin:0 0 4px;font-size:18px}.iss h2 small{font-size:12px;color:var(--muted);font-weight:600;margin-left:6px}
.iss .it{padding:10px 0;border-top:1px solid var(--line)}.iss .it:first-of-type{border-top:0}
.iss .tt{font-size:16.5px;font-weight:800;line-height:1.4}.iss .it.main .tt{font-size:19px}
.iss .rk{display:inline-block;min-width:20px;height:20px;line-height:20px;text-align:center;border-radius:6px;background:#F39800;color:#fff;font-size:12px;margin-right:6px;vertical-align:2px}
.iss .chips{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin-top:7px}.iss .chips span{font-size:13px;background:var(--bg);border-radius:7px;padding:3px 8px;font-weight:700}
.iss .chips .sec{background:#fff1dc;color:#1c2330}.iss .up{color:var(--up)}.iss .down{color:var(--down)}
.iss .src{margin-top:6px;font-size:12.5px;color:var(--muted);line-height:1.6}.iss .src a{color:var(--muted)}
.iss .note{font-size:12px;color:var(--muted);margin-top:6px}
.iss .pin{display:inline-block;margin-right:6px;padding:1px 7px;border-radius:6px;background:#F39800;color:#fff;font-size:12px;vertical-align:3px}
.iss .kw{display:flex;gap:6px;margin:8px 0 2px}.iss .kw input{flex:1;min-width:0;font:15px inherit;padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--text)}
.iss .kw .kwh{align-self:center}.iss .kw button{font:700 14px inherit;padding:8px 14px;border:0;border-radius:9px;background:#F39800;color:#fff;cursor:pointer}
.iss .kwh{font-size:12px;color:var(--muted)}.iss .hl{font-size:14px;color:var(--muted);margin-top:3px;line-height:1.45}
"""
ISSUE_JS = r"""<script>
(function(){var SRC=%s,box=document.getElementById('issue');if(!box)return;
 function kst(){var n=new Date(Date.now()+9*3600e3);return {d:n.toISOString().slice(0,10).replace(/-/g,''),hm:n.toISOString().slice(11,16),wd:n.getUTCDay()}}
 function on(){var k=kst();return k.wd>0&&k.wd<6&&k.hm>='07:00'&&k.hm<'17:00'}
 function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function pc(v){return v==null?'':'<b class="'+(v>0?'up':v<0?'down':'')+'">'+(v>0?'+':'')+Number(v).toFixed(2)+'%%</b>'}
 var ADM=false;try{ADM=localStorage.getItem('brian-admin')==='1'}catch(x){}
 /* 관리자: 키워드를 넣고 반영 → GitHub '새 파일' 화면(내용 채워짐)에서 Commit만 누르면 1분 안에 1번 이슈로 고정 */
 function kwBox(cur){if(!ADM)return '';cur=cur||[];var ins='';for(var n=0;n<2;n++)ins+='<div class="kw"><input id="kwin'+n+'" placeholder="이슈 '+(n+1)+': 키워드 (쉼표로 여러 개) 또는 제목 | 키워드'+(n?' (선택)':'')+'" value="'+e(cur[n]||'')+'"></div>';
  return ins+'<div class="kw"><button id="kwgo">반영</button><span class="kwh">두 칸 다 비우고 반영하면 해제</span></div>'+
  '<div class="kwh">반영을 누르면 GitHub 화면이 열립니다 → 초록 Commit changes 버튼만 누르세요 (1분 안에 갱신)</div>'}
 function kwBind(){var b=document.getElementById('kwgo');if(!b)return;b.onclick=function(){var k=kst(),vs=[];
  for(var n=0;n<2;n++){var v=(document.getElementById('kwin'+n)||{}).value;v=(v||'').trim();if(v)vs.push(v)}
  var body=vs.map(function(v){return v.indexOf('|')>=0?('제목: '+v.split('|')[0].trim()+'\n'+v.split('|').slice(1).join(',').trim()):v}).join('\n---\n');
  var u='https://github.com/Sunbong-oh/kb-market-report/new/main?filename='+encodeURIComponent('issue_keywords/'+k.d+'-'+k.hm.replace(':','')+'.txt')+
   '&value='+encodeURIComponent(body||' ')+'&message='+encodeURIComponent('핵심 이슈 키워드: '+(vs.join(' / ')||'해제'));window.open(u,'_blank')}}
 function draw(j){if(document.activeElement&&/^kwin/.test(document.activeElement.id||''))return;  /* 입력 중에는 다시 그리지 않음 */
  var ok=j&&j.date===kst().d&&j.data&&j.data.length&&on();
  if(!ok){if(ADM&&on()){box.innerHTML='<div class="iss"><h2>🔥 오늘의 핵심 이슈<small>아직 자료 없음</small></h2>'+kwBox('')+'</div>';box.hidden=false;kwBind()}else box.hidden=true;return}
  var pin=j.data.filter(function(g){return g.pin}).map(function(g){return g.src||g.pin}),pre=j.time<'09:00',h='<div class="iss"><h2>🔥 오늘의 핵심 이슈<small>'+e(j.time)+' 기준 · 네이버 증권 주요뉴스</small></h2>'+kwBox(pin);
  j.data.forEach(function(g,i){h+='<div class="it'+(i?'':' main')+'"><div class="tt"><span class="rk">'+(i+1)+'</span>'+(g.pin?'<span class="pin">📌 '+e(g.pin)+'</span>':'')+e(g.title)+'</div>'+(g.headline?'<div class="hl">'+e(g.headline)+'</div>':'')+'<div class="chips">'+
   (g.sector?'<span class="sec">'+e(g.sector.s)+' '+pc(g.sector.p)+'</span>':'')+
   (g.stocks||[]).map(function(s){return '<span>'+e(s.n)+' '+pc(s.p)+'</span>'}).join('')+'</div>'+
   '<div class="src">기사 '+g.n+'건 · 언론사 '+g.offices+'곳 — '+(g.articles||[]).slice(0,2).map(function(a){return '<a href="'+e(a.url)+'" target="_blank" rel="noopener">'+e(a.o)+' '+e(a.dt.slice(8,10)+':'+a.dt.slice(10,12))+'</a>'}).join(' · ')+'</div></div>'});
  h+=(pre?'<div class="note">장 시작 전: 종목·업종 등락은 전일 종가 기준입니다. 9시부터 실시간으로 바뀝니다.</div>':'')+'</div>';
  box.innerHTML=h;box.hidden=false;kwBind()}
 function load(i){i=i||0;if(i>=SRC.length||!on()){if(!on())box.hidden=true;return}
  fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(draw).catch(function(){load(i+1)})}
 load();setInterval(function(){if(!document.hidden)load()},180000);
 document.addEventListener('visibilitychange',function(){if(!document.hidden)load()})})();
</script>""" % json.dumps(ISSUE_SRC)


# 실적 속보: earnings_flash/YYYYMMDD-회사.json (발표 직후 수동 정리). 발표일과 다음 날까지 핵심 이슈 아래에 보인다.
EARN_CSS = """
#earn{order:-2}.earn{background:var(--card);border:1px solid var(--line);border-left:5px solid #2f6fdb;border-radius:14px;padding:14px 16px;margin-top:10px}
.earn h2{margin:0 0 2px;font-size:18px}.earn h2 small{font-size:12px;color:var(--muted);font-weight:600;margin-left:6px}
.earn .vd{font-size:15px;font-weight:800;color:var(--up);margin:4px 0 8px}
.earn table{width:100%;border-collapse:collapse;font-size:14px}.earn td{padding:6px 4px;border-top:1px solid var(--line);vertical-align:top}
.earn td:first-child{color:var(--muted);font-weight:700;white-space:nowrap}.earn td.v{font-weight:800;white-space:nowrap}
.earn td.c{color:var(--muted);font-size:12.5px;line-height:1.45}.earn .j{color:var(--text);font-size:13px}
.earn h3{font-size:14.5px;margin:12px 0 4px}.earn ul{margin:0;padding-left:18px;line-height:1.55;font-size:14px}
.earn .src{font-size:12px;color:var(--muted);margin-top:8px}.earn .src a{color:var(--muted)}
#earn-live{order:-2}.earn.auto{border-left-color:#e03131}.earn .cal{font-size:13px;color:var(--muted);margin:2px 0 6px}
.earn .cons{font-size:14.5px;font-weight:800;margin:3px 0}.earn.auto ul{margin-top:6px}.earn.auto li{margin:3px 0}
.earn.auto li a{color:var(--text);text-decoration:none;font-weight:600}.earn.auto li span{font-size:12px;color:var(--muted)}
.earn .px{background:var(--bg);border-radius:10px;padding:8px 10px;margin:8px 0}.earn .pxh{font-size:13.5px;font-weight:800;margin-bottom:3px}
.earn .pxr{font-size:13.5px;line-height:1.6}.earn .pl{font-weight:700}.earn .ps,.earn .pr{font-size:12px;color:var(--muted)}
.earn .up{color:var(--up)}.earn .down{color:var(--down)}
"""
EARN_JS = """<script>(function(){var n=new Date(Date.now()+9*3600e3),t=n.toISOString().slice(0,10),y=new Date(n-864e5).toISOString().slice(0,10);
document.querySelectorAll('.earn[data-day]').forEach(function(c){if(c.dataset.day!==t&&c.dataset.day!==y)c.remove()});
var s=document.getElementById('earn');if(s&&!s.querySelector('.earn'))s.remove()})()</script>"""


# 자동 실적 속보: kb-market-report earnings-watch 워크플로가 10분마다 갱신하는 earnings-live/earnings.json
# (★ 실적·주요 반도체 실적 발표 감지 → 컨센서스 + 기사 제목). 수동 정리 카드(earnings_flash)가 있으면 그 회사는 뺀다.
EARN_LIVE_SRC = ("https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/earnings.json?ref=earnings-live",
                 "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json")
EARN_LIVE_JS = r"""<script>
(function(){var SRC=%s,box=document.getElementById('earn-live');if(!box)return;
 function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function pc(v){return v==null?'':'<b class="'+(v>0?'up':v<0?'down':'')+'">'+(v>0?'+':'')+Number(v).toFixed(2)+'%%</b>'}
 function px(i){if(!(i.px||[]).length)return '';return '<div class="px"><div class="pxh">📈 실적 발표 후 주가 반응</div>'+i.px.map(function(r){
   return '<div class="pxr"><span class="pl">'+e(r.l)+'</span> <span class="ps">'+e(r.s)+' '+e(r.t||'')+'</span> <b>'+e(r.p)+'</b> '+
    (r.c!=null?'<span class="pr">'+e(r.ref)+' 대비</span> '+pc(r.c):'')+(r.d1!=null?' <span class="pr">· 첫 정규장</span> '+pc(r.d1):'')+'</div>'}).join('')+'</div>'}
 function draw(j){var now=Date.now(),manual={};document.querySelectorAll('.earn[data-key]').forEach(function(c){manual[c.dataset.key]=c});
  (j&&j.items||[]).forEach(function(i){var c=manual[i.key];if(!c)return;var o=c.querySelector('.px');if(o)o.remove();
   var h=px(i);if(h){var t=c.querySelector('table');(t||c.querySelector('.vd')).insertAdjacentHTML('afterend',h)}});  /* 수동 카드에는 주가 반응만 */
  var its=(j&&j.items||[]).filter(function(i){var t=Date.parse(i.detected.replace(' ','T')+':00+09:00');return now-t<72*3600e3&&!manual[i.key]});
  if(!its.length){box.hidden=true;return}
  box.innerHTML=its.map(function(i){return '<div class="earn auto"><h2>⚡ 실적 발표 · '+e(i.name)+'<small>'+e(i.first)+' 감지 · 자동</small></h2>'+
   (i.item!==i.name?'<div class="cal">캘린더: '+e(i.item)+'</div>':'')+
   (i.cons||[]).map(function(c){return '<div class="cons">▶ '+e(c)+'</div>'}).join('')+px(i)+
   '<ul>'+(i.news||[]).map(function(a){return '<li><a href="'+e(a.u)+'" target="_blank" rel="noopener">'+e(a.t)+'</a> <span>'+e(a.o)+' '+e(a.dt)+'</span></li>'}).join('')+'</ul></div>'}).join('');
  box.hidden=false}
 function load(i){i=i||0;if(i>=SRC.length)return;
  fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(draw).catch(function(){load(i+1)})}
 load();setInterval(function(){if(!document.hidden)load()},300000);
})();
</script>""" % json.dumps(list(EARN_LIVE_SRC))


def earnings_home(now):
    cards = []
    for f in sorted((ROOT / "earnings_flash").glob("*.json"), reverse=True):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (now.date() - datetime.strptime(e["day"], "%Y-%m-%d").date()).days > 1:
            continue
        rows = "".join(f'<tr><td>{escape(r[0])}</td><td class="v">{escape(r[1])}</td><td class="c">'
                       f'{f"<b class=j>{escape(r[3])}</b><br>" if r[3] else ""}{escape(r[2])}</td></tr>' for r in e.get("rows") or [])
        guide = "".join(f"<li>{escape(g)}</li>" for g in e.get("guidance") or [])
        src = " · ".join(f'<a href="{escape(u)}" target="_blank" rel="noopener">{escape(t)}</a>' for t, u in e.get("sources") or [])
        cards.append(f'<div class="earn" data-day="{escape(e["day"])}" data-key="{escape(f.stem)}"><h2>📊 실적 속보 · {escape(e["company"])}'
                     f'<small>{escape(e["period"])} · {escape(e["day"][5:].replace("-", "/"))} {escape(e.get("time", ""))} 발표</small></h2>'
                     f'<div class="vd">{escape(e.get("verdict", ""))}</div><table>{rows}</table>'
                     + (f"<h3>향후 가이던스</h3><ul>{guide}</ul>" if guide else "")
                     + (f'<div class="src">출처: {src}</div>' if src else "") + "</div>")
    live = f'<section class="sec" id="earn-live" hidden></section>'
    if not cards:
        return f'<style>{EARN_CSS}</style>{live}{EARN_LIVE_JS}'
    return f'<section class="sec" id="earn"><style>{EARN_CSS}</style>{"".join(cards)}</section>{EARN_JS}{live}{EARN_LIVE_JS}'


def build_home(now, daily, news, close, live=None, stocks=None, target=None, us=None):
    if live:
        s1 = f'<iframe class="embed" scrolling="no" src="{live["embed"]}?v={VER}" title="실시간 시세" loading="eager"></iframe>'
    elif daily and daily.get("embed"):
        s1 = f'<iframe class="embed" scrolling="no" src="{daily["embed"]}?v={VER}" title="오전 데일리" loading="eager"></iframe>'
    else:
        s1 = '<section class="panel"><p class="err">오전 데일리는 다음 아침 7시 발송분부터 표시됩니다.</p></section>'
    if close and close.get("embed"):
        s3 = f'<iframe class="embed" scrolling="no" src="{close["embed"]}?v={VER}" title="장마감 수급" loading="eager"></iframe>'
        more3 = f'<a href="close/">{label(close["day"])}</a>'
    else:
        s3, more3 = '<section class="panel"><p class="err">장마감 리포트를 불러오지 못했습니다.</p></section>', ""
    body = (f'<style>{HOME_CSS}{ISSUE_CSS}</style>{CLOSE_FIRST_JS}<div class="home">'
            f'<section class="sec" id="issue" hidden></section>'
            f'{earnings_home(now)}'
            f'<section class="sec" id="daily">{s1}</section>'
            f'<section class="sec" id="news"><div class="sec-h"><h2>💰 돈이 되는 뉴스</h2>'
            f'<a href="news/">{news["at"]:%m/%d %H:%M} 수집</a></div>{news["body"]}</section>'
            f'{target_home(target)}{us_home(us)}'
            f'<section class="sec" id="mystocks"><div class="sec-h"><h2>📌 관심 종목 뉴스</h2>'
            f'<a href="stocks/">{stocks["at"]:%m/%d %H:%M} 수집</a></div>{stocks["body"]}</section>'
            f'<section class="sec" id="close"><div class="sec-h"><h2>📊 장마감 수급</h2>{more3}</div>{s3}</section></div>'
            f'{FIT_JS}{LIVE_HOME_JS}{ISSUE_JS}')
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
    target = build_target()
    us = build_us()
    live = build_live(now)
    stocks = build_stocks(now)
    build_map()
    build_home(now, daily, news, close, live, stocks, target, us)
    print(json.dumps({"out": str(OUT), "daily": daily and daily["day"], "close": close and close["day"], "target": target and target["day"],
                      "us": us and us["day"],
                      "live": bool(live),
                      "news": [len(news["kr"]), len(news["theme"])], "stocks": stocks["n"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
