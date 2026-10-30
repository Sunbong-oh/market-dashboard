"""나만의 주식투자 사이트(GitHub Pages) 생성기.

실행: python build_site.py  ->  _site/ 폴더에 정적 사이트 생성 (GitHub Actions site.yml이 배포)

메뉴
  /             홈: 세 가지 리포트의 최신 요약
  /daily/       오전 데일리 (미국 데일리 마켓) — archive/daily/YYYY-MM-DD/ (daily-dashboard.yml이 매일 저장)
  /close/       장마감 리포트 (국내 장마감 수급체크) — kb-market-report 저장소의 archive/ (환경변수 CLOSE_REPO)
  /target/      목표주가 변동 (증권사 리포트 상향·하향, 평일 08:40·21:00) — kb-market-report 저장소의 consensus/*.json
  /us/          해외주식 리포트 (국내 증권사 미국주식 리포트 요약) — us_reports/*.json (us_reports.py)
  /strong/      전일 미국장 강세종목 리포트 (날짜별, Claude가 만든 종목 리포트) — us_strong/index.json + HTML
  홈 '오늘의 주식 퀴즈' — quiz/questions.json(주식 상식) + study/terms.json(용어) 에서 날마다 3문제
  /play/        놀이터 (게임 9가지·등급·오늘의 미션) + 홈 '코스피 오를까 내릴까?' 투표 — play_page.py
  /study/       재무제표 공부 (활용법·5분 체크·업종별·용어사전·사례노트) — study/*.json (study_page.py)
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path

import dashboard as d
import study_page
import play_page
from company_ko import KR_COMPANY, describe, sector_ko

ROOT = Path(__file__).resolve().parent
# 빌드마다 바뀌는 값: iframe 주소 뒤에 붙여 폰이 예전 내용을 캐시에서 다시 쓰지 않게 한다 (GitHub Pages는 10분 캐시)
VER = datetime.now().strftime("%y%m%d%H%M%S")
OUT = Path(os.environ.get("SITE_OUT", ROOT / "_site"))
DAILY = ROOT / "archive" / "daily"
CLOSE = Path(os.environ.get("CLOSE_REPO", ROOT.parent / "kb-market-report")) / "archive"
CONSENSUS = CLOSE.parent / "consensus"
US_REPORTS = ROOT / "us_reports"
US_STRONG = ROOT / "us_strong"
MEMO = ROOT / "memo"
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
MENU = (("", "홈"), ("daily/", "오전 데일리"), ("target/", "목표주가 변동"), ("reports/", "실적발표 종목"),
        ("us/", "해외주식"), ("strong/", "전일 미국장 강세종목"), ("memo/", "Brian's memo"), ("close/", "장마감 리포트"), ("study/", "재무제표 공부"), ("play/", "놀이터"),
        # 아티팩트로 만든 계산기 (새 탭으로 열린다). 주소를 바꾸면 메뉴와 홈 카드가 함께 바뀐다.
        ("https://claude.ai/artifact/DQyDxi1Tj5ZZn4xHiwW3dX", "연금 계산기"),
        ("https://claude.ai/artifact/WSirn5BiFzgjdjQyeM2Evt", "라이프 플랜"))


def nav(root, active):
    links = "".join(f'<a href="{href if href.startswith("http") else root + href}" style="{NAV_ON if href == active else NAV_LINK}"'
                    f'{" target=_blank rel=noopener" if href.startswith("http") else ""}>{label}</a>'
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
</div>{VISIT_JS}</body></html>'''


SUB_STYLE = ("display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:6px 12px;background:#2b3444;"
             "font:600 13px/1.2 'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#c9d1de")
SUB_LINK = "color:#ffd43b;text-decoration:none;padding:4px 8px;border-radius:6px;border:1px solid #4a5568"


def with_nav(html, root, active, sub=None, extra=""):
    """원본 리포트 HTML의 <body> 바로 뒤에 메뉴를 넣는다. sub=(설명, [(href, 이름)...])이면 보조 막대도, extra 는 그 뒤에 그대로."""
    html = re.sub(r"</head>", lambda _: head_tags(root) + "</head>", html, count=1, flags=re.I)
    m = re.search(r"<body[^>]*>", html, re.I)
    bar = nav(root, active)
    if sub:
        text, links = sub
        bar += (f'<div style="{SUB_STYLE}"><span style="margin-right:4px">{escape(text)}</span>'
                + "".join(f'<a href="{h}" style="{SUB_LINK}">{escape(t)}</a>' for h, t in links) + "</div>")
    bar += extra
    return html[:m.end()] + bar + html[m.end():] if m else bar + html


# 데일리의 '주요 지표' 12개를 폰에서도 텔레그램처럼 3열 4줄로: 600px 폭 3열로 배치한 뒤 화면 폭에 맞게 축소
# 데일리 맨 위 '라이트/다크' 버튼은 휴대폰에 선택을 저장해, 홈페이지는 밝은데 데일리(주요 지표)만 어둡게 남았다.
# 사이트 안에서는 버튼을 숨기고 저장값을 지워, 데일리도 홈페이지 전체처럼 휴대폰 설정(밝게/어둡게)을 따른다.
DAILY_THEME = ("<style>#bt{display:none!important}</style>"
               "<script>try{localStorage.removeItem('theme')}catch(e){}delete document.documentElement.dataset.theme</script>")
GRID3 = """<style>.panel.kr{display:none!important}  /* 사이트에서는 뉴스 칸을 보이지 않는다 (돈이 되는 뉴스는 2026-10-23 사용자 요청으로 없앰) */
@media (max-width:640px){
.grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}
.g3 .card{padding:11px 11px 10px!important;border-radius:12px}
.g3 .card header{flex-direction:column;align-items:flex-start;gap:0}
.g3 .card h3{font-size:18px!important}.g3 .sym{font-size:12px!important}
.g3 .price{font-size:27px!important;margin-top:4px}.g3 .price small{font-size:15px!important}
.g3 .badge{font-size:12px!important;padding:1px 6px!important}.g3 .delta{font-size:15px!important}
.g3 .spark{height:46px!important;margin-top:6px}
.g3 .range{font-size:10px!important;gap:3px!important;margin-top:6px!important;overflow:hidden}.g3 .range span{white-space:nowrap}.g3 .range-cap{display:none!important}
.g3 .chips{gap:2px!important;margin-top:8px}.g3 .chip{padding:4px 3px!important;font-size:12px!important;border-radius:6px;overflow:hidden}
.g3 .chip b{font-size:13px!important;letter-spacing:-.04em}.g3 .chip small{display:none!important}}</style>
<script>(function(){function f(){var g=document.querySelector('.grid');if(!g)return;g.classList.add('g3');
if(innerWidth<=640){var p=g.parentElement,s=getComputedStyle(p);  // clientWidth 는 좌우 여백을 포함해 그만큼 오른쪽이 잘렸다
g.style.width='600px';g.style.zoom=(p.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight))/600}else{g.style.width='';g.style.zoom=''}}
addEventListener('DOMContentLoaded',f);addEventListener('resize',f)})()</script>"""


def daily_grid3(html):
    i = html.lower().rfind("</body>")
    return html[:i] + GRID3 + DAILY_THEME + html[i:] if i >= 0 else html + GRID3 + DAILY_THEME


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
   '('+(pc>0?'+':'')+pc.toFixed(2)+'%%)</span> <small class="lv">\u00B7 \uc2e4\uc2dc\uac04 '+hm+'</small>'+
   /* 장전·시간외: 최근 정규장 종가 대비 */
   (q.x!=null?'<div class="xh" style="font-size:.86em;margin-top:3px"><b>'+q.xs+'</b> $'+f(q.x,2)+' <span class="'+c(q.x-p)+'">('+((q.x/p-1)*100>0?'+':'')+((q.x/p-1)*100).toFixed(2)+'%%)</span> <small>'+q.xt+'</small></div>':'')});
 var h=j.hl,a=document.querySelector('a.headline');  /* 실시간 헤드라인: 리포트 이후 기사일 때만 */
 if(h&&a&&h.dt>=SINCE&&a.textContent!==h.t){a.textContent=h.t;a.href=h.u;var hs=document.querySelector('.hl-src');
  if(hs)hs.textContent=h.s+' \u00B7 '+h.dt.slice(5).replace('-','/')+' \u00B7 \uc2e4\uc2dc\uac04'}
 var IX={'\ub098\uc2a4\ub2e5':'^IXIC','S&P500':'^GSPC'};
 document.querySelectorAll('.ix').forEach(function(x){var k=x.dataset.sym||IX[(x.firstChild&&x.firstChild.nodeValue||'').trim()],q=j.data[k],b=x.querySelector('b');if(!q||!b)return;
  var v=(q.p/q.pc-1)*100;b.className=c(v);b.textContent=(v>0?'+':'')+v.toFixed(2)+'%%'})}
function load(i){i=i||0;if(i>=SRC.length)return;
 fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
 .then(function(r){if(!r.ok)throw 0;return r.json()}).then(apply).catch(function(){load(i+1)})}
load();setInterval(function(){if(!document.hidden)load()},60000)})()</script>""" % json.dumps(list(US_LIVE_SRC))


# 데일리의 '실적 발표' 칸(어젯밤 미국장 실적)도 실적 속보처럼 발표 24시간이 지나면 숨긴다(Put/Call 표시는 남김).
# 발표 시각은 칸의 '10/14 개장 전 발표' 문구로 어림한다: 개장 전 = 그날 21:00 KST, 장 마감 후 = 다음 날 05:00 KST.
EARN_DAILY_JS = r"""<script>(function(){function z(n){return ('0'+n).slice(-2)}
function f(){var p=document.querySelector('.panel.earn');if(!p)return;var s=p.querySelector('.earn-co > span');if(!s)return;
 var m=/(\d{1,2})\/(\d{1,2})\s*(개장 전|장 마감 후)?/.exec(s.textContent);if(!m)return;
 var y=new Date(Date.now()+9*3600e3).getUTCFullYear(),after=m[3]==='장 마감 후';
 var ts=Date.parse(y+'-'+z(m[1])+'-'+z(m[2])+'T'+(after?'05:00':'21:00')+':00+09:00')+(after?864e5:0);
 if(!(Date.now()-ts>864e5))return;
 var pc=p.querySelector('.pcb');if(pc){var w=document.createElement('section');w.className='panel pc-solo';w.appendChild(pc);p.replaceWith(w)}else p.remove()}
f();setInterval(f,300000)})()</script>"""


def with_us_live(html, since):
    """since: 'YYYY-MM-DD HH:MM'(KST) — 이보다 오래된 실시간 시세는 무시 (지난 리포트를 덮어쓰지 않게)."""
    js = US_LIVE_JS.replace("__SINCE__", since) + EARN_DAILY_JS
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
                    html = with_cal_hide(with_us_live(html, f"{p.name} 06:30"), p.name)
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
        (out / p.name / "embed.html").write_text(embed_html(with_cal_hide(with_us_live(eh, f"{p.name} 06:30"), p.name), btc_live=True), encoding="utf-8")
    return dict(day=p.name, headline=unescape(m.group(1)) if m else "", kr=[unescape(t) for t in kr_titles],
                embed=f"daily/{p.name}/embed.html" if html else "",
                newhighs=(p / "newhighs.html").exists())


# '오늘의 증시 캘린더'에서 이미 실적을 발표한 회사를 뺀다 (보는 사람이 '오늘 발표 예정'으로 오해하지 않게).
# 사이트를 만들 때 확인한 목록(실적 카드·SEC 8-K·국내 잠정실적 공시)에, 보는 순간 kb earnings-live 의 국내 공시 이름을 더한다.
_ANN = None
CAL_HIDE_JS = r"""function nm(s){s=s.trim();s=AL[s]||s;return s.replace(/[\s()㈜]|주식회사/g,'').toLowerCase()}
function run(){document.querySelectorAll('.panel.cal:not(.done):not(.wk) ol.items>li').forEach(function(li){
 var tn=null;li.childNodes.forEach(function(n){if(n.nodeType===3&&n.textContent.trim())tn=n});if(!tn)return;
 var m=tn.textContent.trim().match(/^([^()]+?) 실적$/);if(!m)return;
 var ns=m[1].split('·'),left=ns.filter(function(n){return !A[nm(n)]});if(left.length===ns.length)return;
 if(!left.length){li.parentNode.removeChild(li);return}
 tn.textContent=(/^\s/.test(tn.textContent)?' ':'')+left.join('·')+' 실적'});
 document.querySelectorAll('.panel.cal:not(.done):not(.wk)').forEach(function(p){var o=p.querySelector('ol.items');if(o&&!o.children.length)p.parentNode.removeChild(p)})}
run();
try{fetch(SRC+'?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){var now=Date.now();
 (j.items||[]).forEach(function(i){if(String(i.kr)==='True'||i.kr===true){var t=Date.parse(i.first_iso);if(t>=LO&&t<=now)A[nm(i.name||'')]=1}});
 var kd=j.kr_done||{};Object.keys(kd).forEach(function(k){if(Date.parse(k+'T00:00:00+09:00')>=LO)kd[k].forEach(function(n){A[nm(n)]=1})});run()}).catch(function(){})}catch(e){}"""


def refresh_cal(html, day):
    """아침에 만든 데일리의 '오늘의 증시 캘린더'를 지금의 market_calendar.json(날짜를 바로잡은 것)으로 다시 채운다.
    이미 있던 항목은 그 줄(예상치·실제치 포함)을 그대로 쓰고, 이미 실적을 발표한 회사는 뺀다."""
    m = re.search(r'<section class="panel cal"><div class="tag">오늘의 증시 캘린더</div><ol class="items">(.*?)</ol></section>', html, re.S)
    if not m:
        return html
    old = {}
    for li in re.findall(r"<li>.*?</li>", m.group(1), re.S):
        head = li.split('<div class="cv">')[0]
        key = ("★" if "class=hot" in head else "") + unescape(re.sub(r"<[^>]+>", "", head.replace("<b class=hot>★</b>", ""))).strip()
        old[key] = li
    ev = d._calendar().get(day) or []
    ev = [ev] if isinstance(ev, str) else [str(x) for x in ev]
    ev = d.drop_announced(ev, _ann())
    lis = "".join(old.get(e) or d._cal_li(e) for e in ev)
    new = (f'<section class="panel cal"><div class="tag">오늘의 증시 캘린더</div><ol class="items">{lis}</ol></section>' if lis else "")
    return html[:m.start()] + new + html[m.end():]


def _ann():
    global _ANN
    if _ANN is None:
        try:
            _ANN = d.announced(datetime.now(d.KST))
        except Exception as e:
            print("발표 여부 확인 실패:", type(e).__name__, e, file=sys.stderr)
            _ANN = {}
    return _ANN


def with_cal_hide(html, day=None):
    """최신 오전 데일리의 '오늘의 증시 캘린더'를 바로잡고(day 가 있으면), 보는 순간에도 이미 발표한 회사를 빼는 스크립트를 붙인다."""
    if day:
        html = refresh_cal(html, day)
    _ann()
    js = (f"<script>(function(){{var A={json.dumps({k: 1 for k in _ANN}, ensure_ascii=False)},"
          f"AL={json.dumps(d.CAL_ALIAS, ensure_ascii=False)},LO=Date.now()-{d.ANNOUNCED_DAYS}*864e5,"
          f"SRC={json.dumps(EARN_LIVE_SRC[0][1])};\n{CAL_HIDE_JS}\n}})();</script>")
    i = html.lower().rfind("</body>")
    return html[:i] + js + html[i:] if i >= 0 else html + js


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
    html = with_cal_hide(daily_grid3(html))
    nhd = next((p for p in dated_dirs(DAILY) if (p / "newhighs.html").exists()), None)
    if nhd:
        html = with_newhighs(html, f"../{nhd.name}/newhighs.html", newhighs_count(nhd))
    # 사이트 빌드(예약 실행)가 늦거나 멈춰도 카드 시세는 us-live 의 1분 시세로 계속 바뀌게 한다 (이 화면을 만든 시각 이후 시세만)
    html = with_us_live(html, now.strftime("%Y-%m-%d %H:%M"))  # now 는 KST
    (dest / "index.html").write_text(with_nav(html, "../../", "daily/"), encoding="utf-8")
    (dest / "embed.html").write_text(embed_html(html, btc_live=True), encoding="utf-8")
    return dict(at=now, embed="daily/live/embed.html")


# ---------- 방문자 집계 (나만 보는 화면) ----------
# 정적 사이트(GitHub Pages)라 서버가 없다 → 숫자만 세어 주는 무료 카운터(Abacus)에 날짜별로 올린다.
# 방문자(v-날짜)는 브라우저당 하루 한 번, 조회수(p-날짜)는 열 때마다. 관리자(brian-admin)는 세지 않는다.
VISIT_NS = "brian-tujanote-k7q2"
VISIT_API = "https://abacus.jasoncameron.dev"
VISIT_JS = """<script>
(function(){if(window.top!==window)return;  /* 홈에 끼워 넣은 리포트(iframe)는 세지 않는다 */
 if(location.pathname.indexOf('/visits/')>=0)return;  /* 방문자 현황 화면 자신은 세지 않는다 */
 try{if(localStorage.getItem('brian-admin')==='1')return}catch(e){}  /* 내 방문은 빼고 */
 var d=new Date(Date.now()+9*36e5).toISOString().slice(0,10).replace(/-/g,'');
 var hit=function(k){try{fetch('{VISIT_API}/hit/{VISIT_NS}/'+k,{mode:'cors',cache:'no-store'}).catch(function(){})}catch(e){}};
 hit('p-'+d);hit('t-p');
 var first=function(){hit('v-'+d);hit('t-v')};
 try{if(localStorage.getItem('brian-seen')!==d){localStorage.setItem('brian-seen',d);first()}}catch(e){first()}
 /* 아티팩트(연금 계산기·라이프 플랜)는 claude.ai 안에서 돌아가 바깥으로 집계를 보내지 못할 수 있다
    → 홈페이지에서 그 링크를 눌러 들어간 횟수를 여기서 센다 */
 var ART={'DQyDxi1Tj5ZZn4xHiwW3dX':'pen','WSirn5BiFzgjdjQyeM2Evt':'life'};
 document.addEventListener('click',function(e){
  var a=e.target&&e.target.closest?e.target.closest('a[href*="claude.ai/artifact/"]'):null;if(!a)return;
  var k=ART[(a.getAttribute('href')||'').split('/artifact/')[1]];if(!k)return;
  hit('c-'+k+'-'+d);hit('t-c-'+k)},true);
 /* 홈 광고 배너 클릭 */
 document.addEventListener('click',function(e){
  var a=e.target&&e.target.closest?e.target.closest('a[data-ad]'):null;if(!a)return;
  var k='ad-'+a.getAttribute('data-ad');hit('c-'+k+'-'+d);hit('t-c-'+k)},true);
})();
</script>""".replace("{VISIT_API}", VISIT_API).replace("{VISIT_NS}", VISIT_NS)


# 홈 맨 위 방문자 띠: 관리 화면(brian-admin)을 켠 기기에서만 보인다. 손님 화면에는 나오지 않는다.
VCNT_CSS = """#vcnt{order:-3;display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 10px;font-size:13px}
#vcnt b{font-size:17px;font-weight:900;font-variant-numeric:tabular-nums;letter-spacing:-.4px}
#vcnt .c{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 12px;display:flex;gap:6px;align-items:center}
#vcnt .k{color:var(--muted);font-weight:700}
#vcnt a{margin-left:auto;color:var(--muted);text-decoration:none;font-weight:700}"""
VCNT_JS = """<script>
(function(){var box=document.getElementById('vcnt');if(!box)return;
 try{if(localStorage.getItem('brian-admin')!=='1')return}catch(e){return}
 var d=new Date(Date.now()+9*36e5).toISOString().slice(0,10).replace(/-/g,'');
 var get=function(k){return fetch('{VISIT_API}/get/{VISIT_NS}/'+k,{cache:'no-store'}).then(function(r){return r.json()})
   .then(function(j){return j&&j.value||0}).catch(function(){return null})};
 Promise.all([get('v-'+d),get('t-v')]).then(function(v){
  if(v[0]===null&&v[1]===null)return;
  var n=function(x){return (x||0).toLocaleString('ko-KR')};
  box.innerHTML='<span class="c"><span class="k">오늘 방문자</span><b>'+n(v[0])+'</b></span>'+
   '<span class="c"><span class="k">누적</span><b>'+n(v[1])+'</b></span>'+
   '<a href="visits/">자세히 ›</a>';
  box.hidden=false})})();
</script>""".replace("{VISIT_API}", VISIT_API).replace("{VISIT_NS}", VISIT_NS)

VISITS_CSS = """
.vz{max-width:720px}
.vz .gate{text-align:center;padding:28px 16px}
.vz .gate input{font:600 16px/1.3 inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);width:180px}
.vz .gate button{font:800 15px/1.3 inherit;padding:10px 18px;border:0;border-radius:10px;background:var(--accent);color:#fff;margin-left:6px;cursor:pointer}
.vz .tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
@media (max-width:520px){.vz .tiles{grid-template-columns:1fr 1fr}}
.vz .tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.vz .tile .k{font-size:13px;color:var(--muted);font-weight:700}
.vz .tile .v{font-size:30px;font-weight:900;letter-spacing:-1px;font-variant-numeric:tabular-nums;margin-top:2px}
.vz .tile .s{font-size:12px;color:var(--muted)}
.vz table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.vz th,.vz td{padding:7px 6px;border-top:1px solid var(--line);text-align:right}
.vz th:first-child,.vz td:first-child{text-align:left}
.vz th{color:var(--muted);font-size:12.5px}
.vz .bar{height:9px;border-radius:5px;background:var(--accent);display:block;min-width:2px}
.vz tr.today td{font-weight:900;background:var(--bg)}
.vz .note{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:14px}
.vz .vzh{font-size:16px;font-weight:900;margin:22px 0 10px}
.vz .vzh:first-child{margin-top:0}
.vz .vzh a{color:inherit;text-decoration:none;border-bottom:2px solid var(--accent)}
"""

VISITS_JS = """<script>
(function(){var API='{VISIT_API}',NS='{VISIT_NS}',DAYS=14,box=document.getElementById('vz');
 var PAGES=[{k:'',t:'투자노트 홈페이지',u:'../'},
            {k:'pen',t:'연금 계산기',u:'https://claude.ai/artifact/DQyDxi1Tj5ZZn4xHiwW3dX'},
            {k:'life',t:'라이프 플랜',u:'https://claude.ai/artifact/WSirn5BiFzgjdjQyeM2Evt'},
            {k:'ad-manbo',t:'광고 · 제주 만보농장',u:'https://www.band.us/@manbofarm',ad:1},
            {k:'quiz',t:'오늘의 주식 퀴즈',u:'../#quiz',ad:1,lab:'참여',note:'퀴즈를 푼 사람 수 (기기당 하루 한 번)'},
            {k:'game',t:'놀이터 게임',u:'../play/',ad:1,lab:'플레이',note:'놀이터를 열고 게임을 시작한 횟수'}];
 function kst(off){var d=new Date(Date.now()+9*36e5-(off||0)*864e5);return d.toISOString().slice(0,10)}
 function n(v){return (v||0).toLocaleString('ko-KR')}
 function get(k){return fetch(API+'/get/'+NS+'/'+k,{cache:'no-store'}).then(function(r){return r.json()})
   .then(function(j){return j&&j.value||0}).catch(function(){return null})}
 function admin(){try{return localStorage.getItem('brian-admin')==='1'}catch(e){return false}}
 function gate(){box.innerHTML='<div class="gate"><p>관리 비밀번호를 넣어 주세요.</p>'+
   '<input id="vzpw" type="password" autocomplete="off"><button id="vzgo">확인</button></div>';
  var go=function(){if((document.getElementById('vzpw').value||'').trim()==='brian'){
    try{localStorage.setItem('brian-admin','1')}catch(e){} load()}else{alert('비밀번호가 다릅니다.')}};
  document.getElementById('vzgo').onclick=go;
  document.getElementById('vzpw').onkeydown=function(e){if(e.key==='Enter')go()}}
 var days=[];for(var i=0;i<DAYS;i++)days.push(kst(i));
 function keys(pg){var out=[];
  if(!pg.k){days.forEach(function(d){var y=d.replace(/-/g,'');out.push('v-'+y,'p-'+y)});out.push('t-v','t-p');return out}
  days.forEach(function(d){var y=d.replace(/-/g,'');out.push('c-'+pg.k+'-'+y,'v-'+pg.k+'-'+y)});
  out.push('t-c-'+pg.k,'t-v-'+pg.k);return out}
 function block(pg,vals){
  var TV=vals[vals.length-2],TP=vals[vals.length-1],V=[],P=[];
  for(var i=0;i<DAYS;i++){V.push(vals[i*2]||0);P.push(vals[i*2+1]||0)}
  var wk=V.slice(0,7).reduce(function(a,b){return a+b},0),mx=Math.max.apply(0,V.concat([1]));
  var wd='일월화수목금토';
  var rows=days.map(function(d,i){var dt=new Date(d+'T00:00:00+09:00');
    return '<tr'+(i?'':' class="today"')+'><td>'+d.slice(5)+'('+wd[dt.getUTCDay()]+')</td>'+
     '<td>'+n(V[i])+'</td><td>'+n(P[i])+'</td>'+
     '<td style="width:40%"><i class="bar" style="width:'+Math.round(V[i]/mx*100)+'%"></i></td></tr>'}).join('');
  if(pg.ad){var rws=days.map(function(d,i){var dt=new Date(d+'T00:00:00+09:00');
     return '<tr'+(i?'':' class="today"')+'><td>'+d.slice(5)+'('+wd[dt.getUTCDay()]+')</td><td>'+n(V[i])+'</td>'+
      '<td style="width:55%"><i class="bar" style="width:'+Math.round(V[i]/mx*100)+'%"></i></td></tr>'}).join('');
   return '<h2 class="vzh"><a href="'+pg.u+'" target="_blank" rel="noopener">'+pg.t+'</a></h2>'+
    '<div class="tiles">'+
    '<div class="tile"><div class="k">오늘 '+(pg.lab||'배너 클릭')+'</div><div class="v">'+n(V[0])+'</div><div class="s">'+days[0]+'</div></div>'+
    '<div class="tile"><div class="k">최근 7일 '+(pg.lab||'클릭')+'</div><div class="v">'+n(wk)+'</div><div class="s">어제 '+n(V[1])+'회</div></div>'+
    '<div class="tile"><div class="k">누적 '+(pg.lab||'클릭')+'</div><div class="v">'+n(TV)+'</div><div class="s">'+(pg.note||'홈페이지 배너를 누른 횟수')+'</div></div></div>'+
    '<section class="panel"><table><thead><tr><th>날짜</th><th>'+(pg.lab||'클릭')+'</th><th></th></tr></thead><tbody>'+rws+'</tbody></table></section>'}
  var art=!!pg.k;
  return '<h2 class="vzh"><a href="'+pg.u+'"'+(art?' target="_blank" rel="noopener"':'')+'>'+pg.t+'</a></h2>'+
   '<div class="tiles">'+
   '<div class="tile"><div class="k">'+(art?'오늘 들어간 횟수':'오늘 방문자')+'</div><div class="v">'+n(V[0])+'</div><div class="s">'+days[0]+'</div></div>'+
   '<div class="tile"><div class="k">'+(art?'오늘 화면 자체 집계':'오늘 조회수')+'</div><div class="v">'+n(P[0])+'</div><div class="s">'+(art?'링크로 바로 온 사람 포함':'열어 본 횟수')+'</div></div>'+
   '<div class="tile"><div class="k">'+(art?'최근 7일':'최근 7일 방문자')+'</div><div class="v">'+n(wk)+'</div><div class="s">어제 '+n(V[1])+(art?'회':'명')+'</div></div>'+
   '<div class="tile"><div class="k">누적</div><div class="v">'+n(TV)+'</div><div class="s">'+(art?'화면 자체 집계 '+n(TP):'조회수 '+n(TP)+'회')+'</div></div></div>'+
   '<section class="panel"><table><thead><tr><th>날짜</th><th>'+(art?'들어간 횟수':'방문자')+'</th><th>'+(art?'자체 집계':'조회수')+'</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></section>';
 }
 function seq(pgs,all){if(!pgs.length)return Promise.resolve(all);
  return Promise.all(keys(pgs[0]).map(get)).then(function(v){all.push(v);return seq(pgs.slice(1),all)})}
 function load(){box.innerHTML='<p class="note">불러오는 중…</p>';
  seq(PAGES.slice(0),[]).then(function(all){
   if(all[0][0]===null&&all[0][1]===null){box.innerHTML='<p class="note">집계를 불러오지 못했습니다. 잠시 뒤 새로고침해 주세요.</p>';return}
   box.innerHTML=PAGES.map(function(pg,i){return block(pg,all[i])}).join('')+
     '<p class="note">· 방문자는 브라우저 하나당 하루 한 번, 조회수는 페이지를 열 때마다 셉니다.<br>'+
     '· 연금 계산기·라이프 플랜의 “들어간 횟수”는 <b>홈페이지에서 그 링크를 누른 횟수</b>입니다. 링크를 직접 받아 들어간 사람은 빠집니다.<br>'+
     '· 그 옆 “자체 집계”는 아티팩트 화면 안에서 직접 세는 숫자인데, claude.ai 안에서 돌아가 바깥 카운터로 못 보낼 수 있어 0으로 남을 수 있습니다.<br>'+
     '· 관리 화면을 켠 기기(내 휴대폰·PC)의 홈페이지 방문·클릭은 세지 않고, 연금 계산기·라이프 플랜은 내 계정으로 열었을 때 세지 않습니다.<br>'+
     '· 숫자만 세는 무료 카운터를 쓰므로 누가 왔는지(아이피·지역·사람)는 알 수 없습니다.<br>'+
     '· 이 주소는 메뉴에 없고 비밀번호로 잠겨 있지만, 주소와 비밀번호를 아는 사람은 볼 수 있습니다.</p>'})}
 admin()?load():gate()})();
</script>""".replace("{VISIT_API}", VISIT_API).replace("{VISIT_NS}", VISIT_NS)


def build_visits(now):
    """방문자 현황 (메뉴에 없는 숨은 주소 + 관리 비밀번호)."""
    body = f'<style>{VISITS_CSS}</style><div class="vz" id="vz"></div>{VISITS_JS}'
    (OUT / "visits").mkdir(parents=True, exist_ok=True)
    (OUT / "visits" / "index.html").write_text(
        page("방문자 현황", body, "../", "", "VISITS", f"{now:%Y-%m-%d} 기준 · 나만 보는 화면"), encoding="utf-8")


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
.site-extra .more{margin-top:10px}
.site-extra .more>summary{cursor:pointer;display:inline-block;list-style:none;font-size:14px;font-weight:700;color:#e8590c;
 padding:6px 12px;border:1px solid #ffd8a8;border-radius:999px;background:#fff8f0}
.site-extra .more>summary::-webkit-details-marker{display:none}
.site-extra .more>summary::after{content:" ▾"}
.site-extra .more[open]>summary::after{content:" ▴"}
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
/* 등락률을 크게 (가격과 같은 크기), 포인트 변화는 옆에 작게 */
.fut .badge2 .fu .c{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:6px}.fut .badge2 .fu .pc{font-style:normal;font-size:24px;font-weight:900;letter-spacing:-.4px;line-height:1.2}
.fut .badge2 .fu .k{color:#15803d;font-size:14px;font-weight:800}
.fut .badge2 .up{background:#fff0f0}.fut .badge2 .up b,.fut .badge2 .up .c{color:#e03131}
.fut .badge2 .dn{background:#eef4ff}.fut .badge2 .dn b,.fut .badge2 .dn .c{color:#1c6dd0}
.fut .g.up{color:#e03131}.fut .g.dn{color:#1c6dd0}
.fut .lg{margin:0 0 8px;font-size:13px;color:#6b7385;line-height:1.5}
.fut .note{margin:6px 0 0;font-size:12px;color:#8a92a3}
.fut .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#e03131;margin-right:5px;animation:futp 1.4s infinite}
@keyframes futp{50%{opacity:.25}}
.fut .ftab{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:0 0 10px}
.fut .ftab button{font:800 13.5px/1.3 'Malgun Gothic',system-ui,sans-serif;padding:8px 4px;word-break:keep-all;border-radius:10px;border:1px solid #d6dae2;background:#fff;color:#1c2330;cursor:pointer}
.fut .ftab button.on{background:#1c2330;color:#fff;border-color:#1c2330}
</style>"""
# 선물 교차 차트: 장마감 페이지(저장된 json)와 홈 실시간 박스(flow-live 브랜치)에서 같은 함수로 그린다.
FUT_JS = r"""<script>
/* 교차차트 3종을 위 버튼으로 바꿔 본다: 외국인 선물 × KOSPI200 선물 / 외국인 코스피 현물 × 코스피 / 외국인 코스닥 현물 × 코스닥.
   d.idx = {코스피:{p:전일 종가, pts:[[HHMM,값],…]}, 코스닥:…}, 현물 누적은 flows 의 '외국인·코스피'·'외국인·코스닥' (2026-10-27 기록부터) */
function futIdx(it){var o={};[['KGG01P','코스피'],['QGG01P','코스닥']].forEach(function(k){var v=it&&it[k[0]],pts=((v&&v.points)||[]).filter(function(p){return p.c!=null}).map(function(p){return [p.t,p.c]});
 if(pts.length>1&&v.prev_close)o[k[1]]={p:v.prev_close,pts:pts}});return o}
function futChart(el,d,live){
 var tm=function(t){t=String(t);while(t.length<4)t='0'+t;return (+t.slice(0,2))*60+(+t.slice(2,4))-525};
 var ok=function(m){return m>=0&&m<=420};
 var IX=d.idx||{},S=el._s&&IX[el._s]?el._s:'fut';el._d=d;el._live=live;
 el.onclick=function(e){var b=e.target.closest('[data-fs]');if(!b)return;el._s=b.dataset.fs;futChart(el,el._d,el._live)};
 var fbars=(d.bars||[]).filter(function(b){return b.c!=null});
 var bars=(S==='fut'?fbars.map(function(b){return [tm(b.t),b.c]}):IX[S].pts.map(function(p){return [tm(p[0]),p[1]]})).filter(function(p){return ok(p[0])});
 var NM=S==='fut'?'KOSPI200 선물':S,FK=S==='fut'?'외국인':'외국인·'+S,FN=S==='fut'?'외국인 선물':'외국인 '+S+' 현물';
 var fl=(d.flows||[]).filter(function(r){return r[FK]!=null}).map(function(r){return [tm(r.t),r[FK]]}).filter(function(p){return ok(p[0])});
 if(bars.length<2)return false;
 var hf=fl.length>=2,cf=d.current_flows||{},lf=bars[bars.length-1],last=lf[1];
 var fg=hf?fl[fl.length-1][1]:cf[FK];
 var F=d.futures||{},prev=S!=='fut'?IX[S].p:(F.price!=null&&F.change!=null)?F.price-F.change:null;
 /* 장중에는 가로축을 08:45~(마지막 기록+30분)으로 줄여 지금까지의 흐름을 넓게 보여 준다. 장 마감 뒤엔 하루 전체 */
 var lastM=Math.max(lf[0],hf?fl[fl.length-1][0]:0),END=live?Math.min(420,Math.max(lastM+30,90)):420;
 var W=640,H=310,L=92,R=548,T=14,B=262,x=function(m){return L+(R-L)*m/END};
 var sc=function(v){var lo=Math.min.apply(0,v),hi=Math.max.apply(0,v);if(hi==lo){hi+=1;lo-=1}var pd=(hi-lo)*.06;lo-=pd;hi+=pd;
   return {lo:lo,hi:hi,y:function(a){return B-(B-T)*(a-lo)/(hi-lo)}}};
 var sf=sc(bars.map(function(p){return p[1]})),sg=hf?sc(fl.map(function(p){return p[1]})):null;
 /* 두 축의 비율 고정: 선물 지수 2포인트 = 외국인 200억(1포인트 = 100억). 더 크게 움직인 쪽에 맞춰 둘 다 같은 비율로 */
 if(hf&&S==='fut'){var RATIO=100,span=Math.max(sf.hi-sf.lo,(sg.hi-sg.lo)/RATIO),fm=(sf.hi+sf.lo)/2,gm=(sg.hi+sg.lo)/2;
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
 var svg='<svg viewBox="0 0 '+W+' '+H+'" width="100%" role="img" aria-label="'+NM+'과 외국인 선물 순매수 누적 교차 차트" style="font:15px \'Malgun Gothic\',sans-serif;fill:#6b7385;display:block">'+
  '<rect x="'+L+'" y="'+T+'" width="'+(R-L)+'" height="'+(B-T)+'" fill="#fafbfc" stroke="#e3e6ec"/>'+grid+
  '<text x="'+(L-6)+'" y="'+(T+12)+'" text-anchor="end">'+f2(sf.hi)+'</text><text x="'+(L-6)+'" y="'+(B+4)+'" text-anchor="end">'+f2(sf.lo)+'</text>'+
  '<path d="'+path(bars,sf.y)+'" fill="none" stroke="#1c2330" stroke-width="1.4" stroke-linejoin="round" opacity=".7"/>'+fsvg+'</svg>';
 var ch=prev!=null?last-prev:null,pct=ch!=null&&prev?ch/prev*100:0,cls=ch>0?'up':ch<0?'dn':'';
 var back=hf?fl.filter(function(p){return p[0]<=fl[fl.length-1][0]-30}):[],d30=back.length?fg-back[back.length-1][1]:null;
 var gc=fg>0?'up':fg<0?'dn':'';
 var badge='<div class="badge2">'+(fg!=null?'<div class="fg '+gc+'"><span class="k">'+FN+' 누적'+(S==='fut'?' · 주간장':'')+(hf?'':' (마감)')+'</span><b>'+sg0(fg)+'억</b>'+
  '<span class="c">'+(fg>0?'순매수':fg<0?'순매도':'')+(d30!=null?' · 30분 '+(d30>0?'▲':d30<0?'▼':'')+n0(Math.abs(d30))+'억 '+(d30>0?'사는 중':d30<0?'파는 중':''):'')+'</span></div>':'')+
  (ch!=null?'<div class="fu '+cls+'"><span class="k">'+NM+'</span><b>'+f2(last)+'</b><span class="c"><em class="pc">'+(pct>0?'+':'')+pct.toFixed(2)+'%</em> '+
  (ch>0?'▲':ch<0?'▼':'')+f2(Math.abs(ch))+'</span></div>':'')+'</div>';
 var rest=hf?(d.flows||[]).slice(-1)[0]||{}:cf,oth=['기관계','개인'].filter(function(k){return rest[k]!=null}).map(function(k){return k+' '+sg0(rest[k])}).join(' · ');
 var hh=lf[0]+525,hhmm=Math.floor(hh/60)+':'+('0'+hh%60).slice(-2);
 var tabs=Object.keys(IX).length?'<div class="ftab">'+[['fut','외국인 선물<br>× K200 선물']].concat(Object.keys(IX).map(function(k){return [k,'외국인 '+k+'<br>× '+k+' 지수']})).map(function(t){
   return '<button type="button" data-fs="'+t[0]+'"'+(t[0]===S?' class="on"':'')+'>'+t[1]+'</button>'}).join('')+'</div>':'';
 el.innerHTML=tabs+badge+'<p class="lg">'+(hf?'<b style="color:#e03131">━ '+FN+' 순매수 누적</b> (우, 억원) · ':'')+
  '<b style="color:#495057">━ '+NM+'</b> (좌) '+f2(last)+'<br><span style="font-size:12px">'+(S==='fut'?'※ 주간장 기준(08:45~15:45) · 야간장 미포함 — MTS·HTS 투자자동향(야간 포함)과 다를 수 있음':
  '※ 정규장 당일 누적(억원) · 두 선은 각자 범위에 맞춰 그림'+(hf?'':' · 외국인 현물 분 단위 기록은 10/27 장부터 쌓여요'))+'</span></p>'+svg+
  '<p class="note">'+(live?'<span class="dot"></span>'+hhmm+' 기준 · 1분마다 기록, 화면은 1~2분마다 자동 갱신':
  (hf?'회사 PC 서버가 08:45~15:45 1분마다 기록한 값 (서버가 꺼져 있던 시간은 비어 있음)':'외국인 분 단위 추이는 회사 PC 기록이 있는 날부터 함께 그려집니다'))+'</p>';
 return true}
</script>"""


def _fut_data(d):
    keep = ("t", "외국인", "기관계", "개인", "외국인·코스피", "외국인·코스닥")
    return {"futures": d.get("futures"), "bars": [{"t": b["t"], "c": b.get("c")} for b in d.get("bars") or []],
            "flows": [{k: r[k] for k in keep if k in r} for r in d.get("flows") or []],
            "current_flows": {k: v for k, v in (d.get("current_flows") or {}).items() if k in keep}, "idx": d.get("idx") or {}}


def _idx_data(it):
    """/api/indices/intraday → {코스피: {p: 전일 종가, pts: [[HHMM, 값], …]}, 코스닥: …} (JS futIdx 와 같은 모양)."""
    out = {}
    for code, name in (("KGG01P", "코스피"), ("QGG01P", "코스닥")):
        v = (it or {}).get(code) or {}
        pts = [[p["t"], p["c"]] for p in v.get("points") or [] if p.get("c") is not None]
        if len(pts) > 1 and v.get("prev_close"):
            out[name] = {"p": v["prev_close"], "pts": pts}
    return out


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
    fx = next((r for r in m.get("investors") or [] if r.get("name") == "외국인"), {})
    spot = {f"외국인·{n}": fx.get(k) for k, n in (("kospi", "코스피"), ("kosdaq", "코스닥")) if fx.get(k) is not None}
    if not any(fin.get(k) for k in ("외국인", "기관계", "개인")):  # 장 마감 약 1시간 뒤 KB가 0으로 초기화한 값은 쓰지 않는다
        return
    cur = raw.setdefault("current_flows", {})
    cur.update({k: v for k, v in fin.items()})
    cur.update(spot)
    fl = raw.get("flows") or []
    keys = ("외국인", "기관계", "개인")
    last = {"t": "1545", **{k: fin[k] for k in keys if k in fin}, **(spot if any(k in r for r in fl for k in spot) else {})}
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
        h = next(day_dir.glob("*.html"), None)
        txt = h.read_text(encoding="utf-8") if h else ""
        i = txt.find('"/api/indices/intraday": {')
        if i >= 0:
            raw["idx"] = _idx_data(json.JSONDecoder().raw_decode(txt[txt.index("{", i):])[0])
        data = json.dumps(_fut_data(raw), ensure_ascii=False).replace("</", "<\\/")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""
    return (f'{FUT_CSS}<div class="box fut" id="futbox"><h3>외국인 수급 × 지수 교차차트 (분 단위)</h3><div></div></div>{FUT_JS}'
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
  if(f&&window.futIdx){f=Object.assign({},f,{idx:futIdx(j.data['/api/indices/intraday'])})}
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
 var last=pts[pts.length-1].c,color=last>=prev?'var(--up)':'var(--down)',lx=x(pts[pts.length-1].t);
 // 전일 종가(기준선) 위는 빨강, 아래는 파랑: 기준선과 만나는 곳에서 선을 잘라 토막마다 색을 준다
 var base=y(prev),segs=[],seg=null,up=null;
 pts.forEach(function(p){var q={x:x(p.t),y:y(p.c),up:p.c>=prev};
  if(seg&&q.up!==up){var a=seg[seg.length-1],cx=a.x+(q.x-a.x)*((base-a.y)/((q.y-a.y)||1));
   seg.push({x:cx,y:base});segs.push({up:up,pts:seg});seg=[{x:cx,y:base}]}
  (seg=seg||[]).push(q);up=q.up});
 if(seg&&seg.length>1)segs.push({up:up,pts:seg});
 var col=function(u){return u?'var(--up)':'var(--down)'};
 var path=function(s){return s.pts.map(function(p){return p.x+','+p.y}).join(' ')};
 svg.innerHTML=segs.map(function(s){return '<polygon points="'+s.pts[0].x+','+base+' '+path(s)+' '+s.pts[s.pts.length-1].x+','+base+'" fill="'+col(s.up)+'" opacity=".12"/>'}).join('')+
  '<line x1="0" x2="'+W+'" y1="'+base+'" y2="'+base+'" stroke="var(--muted)" stroke-dasharray="3 3" opacity=".7"/>'+
  segs.map(function(s){return '<polyline fill="none" stroke="'+col(s.up)+'" stroke-width="1.8" stroke-linejoin="round" points="'+path(s)+'"/>'}).join('')+
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
    chip = lambda p: f'<li><a href="{prefix}{p.name}/"{" class=on" if p.name == cur else ""}>{label(p.name)}</a></li>'
    head, rest_days = days[:2], days[2:]  # 최근 두 개만 펴 두고 나머지는 접는다
    more = ""
    if rest_days:
        # 지금 보고 있는 날짜가 접힌 쪽에 있으면 펴서 보여 준다
        open_ = " open" if any(p.name == cur for p in rest_days) else ""
        more = (f'<details class="more"{open_}><summary>지난 리포트 더 보기 ({len(rest_days)})</summary>'
                f'<ul class="dates">{"".join(chip(p) for p in rest_days)}</ul></details>')
    return (f'{EXTRA_CSS}{HIDE_IDX_JS}{ISSUE_JS}{map_btn(prefix + "../map/")}<div class="site-extra">{chart}{body}'
            f'<div class="box"><h3>날짜별 장마감 리포트</h3>'
            f'<ul class="dates">{"".join(chip(p) for p in head)}</ul>{more}</div></div>')


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
    # 리포트가 있는 날만 (장마감 리포트가 빠진 날엔 15:46 선물 기록 futures_flow.json 만 있는 폴더가 생긴다 →
    # 그 폴더를 '최신'으로 잡으면 홈 장마감·장중 실시간 수급 칸이 통째로 비었다: 2026-10-29~30)
    days = [p for p in dated_dirs(CLOSE) if any(p.glob("*.html")) or (p / "본문_장마감수급.txt").exists()]
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
# kb-market-report Actions가 평일 08:40·21:00에 consensus/YYYY-MM-DD.json 을 올린다 (consensus_report.py).
# 원문(PDF) 링크가 있는 제목 옆 '<-- 원문링크는 터치' (실적속보·강세종목의 '터치!!'처럼 좌우로 움직인다)
TP_TAP = '<i class="tp-tap">&lt;-- 원문링크는 터치</i>'


def one_tap(html):
    """'<-- 원문링크는 터치'는 페이지(칸)마다 첫 종목 한 줄에만 남긴다. 한 줄에 제목이 두 번(휴대폰용·PC용) 들어가 첫 두 개를 둔다."""
    parts = html.split(TP_TAP)
    return TP_TAP.join(parts[:3]) + "".join(parts[3:])
TARGET_CSS = """
.tp .tp-tap{font-style:normal;color:#E5484D;font-weight:800;font-size:12.5px;white-space:nowrap;display:inline-block;
 margin-left:12px;animation:tp-tap .9s ease-in-out infinite}
@keyframes tp-tap{0%,100%{transform:translateX(0)}50%{transform:translateX(-8px)}}
@media print{.tp .tp-tap{animation:none}}
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
            title = f'<a href="{escape(it["pdf"])}" target="_blank" rel="noopener">{title}</a>{TP_TAP}'
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
            title = f'<a href="{escape(it["pdf"])}" target="_blank" rel="noopener">{title}</a>{TP_TAP}'
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
        body = one_tap(body + all_reports(items))
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
                                             "../", "target/", "TARGET PRICE", "평일 오전 8시 40분·오후 9시, 증권사 리포트 목표주가 상향·하향"),
                                        encoding="utf-8")
    return first


# ---------- 해외주식 리포트 (국내 증권사 미국주식 리포트 요약) ----------
# us_reports.py 가 us_reports/YYYY-MM-DD.json 을 만든다(us-live 작업이 평일 08:40·21:00에 모아 us-reports 브랜치에 저장) (연합인포맥스 글로벌모니터 목록 = 한국투자증권 미국주식 리서치 메뉴).
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
                                             "../", "us/", "US EQUITY RESEARCH", "국내 증권사 미국주식 리포트 · 평일 오전 8시 40분·오후 9시"),
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


# ---------- 해외주식 강세종목 리포트 (날짜별) ----------
# Claude 프로젝트에서 만든 종목 리포트(KB 리서치 스타일 HTML)를 us_strong/ 에 넣고 index.json 에 한 줄 추가하면
# /strong/ 목록(날짜 최신순, 같은 날은 등락률 높은 순)과 리포트 페이지가 생긴다.
# index.json 항목: date, ticker, exchange, name, nameEn, sector, price, changePct, priceNote, headline, tags, file
STRONG_CSS = """
.st-day{margin:18px 0 6px;font-size:15px;font-weight:800;color:var(--muted);display:flex;flex-wrap:wrap;align-items:baseline;column-gap:12px}
.st{display:block;background:var(--card);border:1px solid var(--line);border-left:5px solid #F2A900;border-radius:12px;
  padding:12px 14px;margin-top:8px;text-decoration:none}
a.st:hover{border-color:#F2A900}
.st .nm{font-size:17px;font-weight:800;display:flex;flex-wrap:wrap;align-items:center;column-gap:10px;row-gap:6px}.st .nm small{font-size:12.5px;color:var(--muted);font-weight:600}
.st .px{float:right;text-align:right;font-variant-numeric:tabular-nums;font-weight:800;margin-left:10px}
.st .px b{display:block;font-size:16px}.st .px .up{color:var(--up)}.st .px .down{color:var(--down)}
.st .hl{font-size:14px;margin-top:4px;line-height:1.55}.st .pn{font-size:12.5px;color:var(--muted);margin-top:3px}
.st .tg{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}.st .tg span{font-size:11.5px;font-weight:700;padding:1px 7px;border-radius:5px;
  background:#FBE7B0;color:#3D3A35}
.st-note{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:16px}
/* 미국 외 시장 종목(index.json 의 region): 카드 왼쪽 띠를 빨강으로 바꾸고 '🇨🇳 중국시장' 배지를 종목명 앞에 둔다 */
.st.rg{border-left-color:#D7263D}.st .rgb{display:inline-block;font-size:13px;font-weight:900;padding:2px 9px;border-radius:6px;background:#D7263D;color:#fff;white-space:nowrap}
.st .rgb.us{background:#1F4E9E}
.st .go{display:inline-flex;align-items:center;gap:8px}
.st .go b{display:inline-block;white-space:nowrap;padding:5px 12px;border-radius:10px;background:#F2A900;color:#3D3A35;font-size:14px;font-weight:800}
.st .go i{font-style:normal;color:#E5484D;font-weight:800;font-size:14px;white-space:nowrap;display:inline-block;animation:rpt-tap .9s ease-in-out infinite}
/* '<-- 터치!!' 좌우 움직임: 윈도우·휴대폰의 '애니메이션 줄이기' 설정과 관계없이 항상 움직인다 (8px 정도라 부담 없음) */
@keyframes rpt-tap{0%,100%{transform:translateX(0)}50%{transform:translateX(-8px)}}
.st-mk{font-size:13.5px;font-weight:700;color:var(--muted)}.st-mk+.st-mk{margin-left:4px}.st-mk>span{white-space:nowrap}.st-mk b{margin-left:3px}.st-mk .up{color:var(--up)}.st-mk .down{color:var(--down)}
.sec-h.st-h{flex-wrap:wrap;justify-content:flex-start;column-gap:12px}.sec-h.st-h>a{margin-left:auto}
/* 홈: 광고·핵심 이슈·실적속보(order:-2)와 장중 수급(order:-1)보다 위. 17시 뒤 #strong-low 안으로 옮겨지면 이 값은 상관없다 */
.home>#strong{order:-3;margin-top:0;margin-bottom:12px}
"""


def strong_items():
    try:
        items = json.loads((US_STRONG / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = [x for x in items if DATE_RE.match(x.get("date", "")) and x.get("file") and (US_STRONG / x["file"]).is_file()]
    return sorted(items, key=lambda x: (x["date"], x.get("changePct") or 0), reverse=True)


def strong_card(it, href):
    chg = it.get("changePct")
    pct = f'<span class="{"up" if chg > 0 else "down"}">{chg:+.2f}%</span>' if chg is not None else ""
    cur = escape(it.get("currency", "$"))  # 미국 외 종목은 index.json 에 currency(예: "¥") 를 적는다
    dp = 0 if cur == "₩" else 2  # 한국 종목(원)은 소수점 없이
    px = f'<div class="px"><b>{cur}{it["price"]:,.{dp}f}</b>{pct}</div>' if it.get("price") else ""
    tags = "".join(f"<span>{escape(t)}</span>" for t in it.get("tags", []))
    rg = f'<span class="rgb">{escape(it["region"])}</span>' if it.get("region") else ""
    # region 이 없는 항목은 미국 종목: 파란 '🇺🇸 미국시장' 배지 (2026-10-28 요청, 카드 띠 색은 그대로)
    us = "" if rg else '<span class="rgb us">🇺🇸 미국시장</span>'
    return (f'<a class="st{" rg" if rg else ""}" href="{escape(href)}">{px}<div class="nm">{rg or us}{escape(it.get("name", ""))}'
            f'<small>{escape(it["ticker"])} · {escape(it.get("exchange", ""))} · {escape(it.get("sector", ""))}</small>'
            # 리포트 버튼은 종목명 줄 바로 옆 (좁으면 다음 줄로)
            '<span class="go"><b>📑 실시간 작성된 리포트</b><i>&lt;-- 터치!!</i></span></div>'
            f'<div class="hl">{escape(it.get("headline", ""))}</div>'
            + (f'<div class="pn">{escape(it["priceNote"])}</div>' if it.get("priceNote") else "")
            + (f'<div class="tg">{tags}</div>' if tags else "")
            + '</a>')


def strong_market(its):
    """제목 옆 전일 지수 등락 (index.json 의 market: day, nasdaq, sp500, idx, source).
    같은 날 카드가 여러 시장(예: 중국 + 미국)이면 시장마다 지수를 모두 붙인다."""
    if isinstance(its, dict):
        its = [its]
    out, seen, days = [], set(), set()
    for it in its:
        m = it.get("market") or {}
        key = json.dumps(m, sort_keys=True, ensure_ascii=False)
        if not m or key in seen:
            continue
        seen.add(key)
        html = _strong_market_one(m, show_day=m.get("day") not in days)
        if html:
            days.add(m.get("day"))
            out.append(html)
    return "".join(out)


def _strong_market_one(m, show_day=True):
    parts = [f'{n}<b class="{"up" if m[k] > 0 else "down"}">{m[k]:+.2f}%</b>'
             for k, n in (("nasdaq", "나스닥"), ("sp500", "S&amp;P500")) if m.get(k) is not None]
    parts += [f'{escape(n)}<b class="{"up" if v > 0 else "down"}">{v:+.2f}%</b>' for n, v in m.get("idx", [])]
    if not parts:
        return ""
    day = escape(m.get("day", "")[5:].replace("-", "/"))
    parts = [f"<span>{x}</span>" for x in parts]  # 지수가 많아 좁은 화면에서 넘치면 지수 단위로 줄을 바꾼다
    return (f'<span class="st-mk" title="{escape(m.get("source", ""))}">' + (f"<span>{day}</span> " if show_day else "· ")
            + f'{" · ".join(parts)}</span>')


def strong_bar(it):
    """강세종목 리포트 페이지 메뉴 아래 막대: 전일 나스닥·S&P500 등락 + 목록으로 (홈 제목 옆과 같은 값)."""
    m = it.get("market") or {}
    parts = [f'{n} <b style="color:{"#ff6b6b" if m[k] > 0 else "#74c0fc"}">{m[k]:+.2f}%</b>'
             for k, n in (("nasdaq", "나스닥"), ("sp500", "S&amp;P500")) if m.get(k) is not None]
    parts += [f'{escape(n)} <b style="color:{"#ff6b6b" if v > 0 else "#74c0fc"}">{v:+.2f}%</b>' for n, v in m.get("idx", [])]
    where = escape(m.get("label", "전일 미국장"))
    mk = (f'<span style="margin-right:10px">{where} {escape(m.get("day", "")[5:].replace("-", "/"))} · {" · ".join(parts)}</span>'
          if parts else "")
    close = ('<a href="./" class="st-close-bar" style="margin-left:auto;background:#F2A900;color:#3D3A35;font-weight:900;'
             'text-decoration:none;padding:5px 14px;border-radius:16px" '
             'onclick="event.preventDefault();if(history.length>1){history.back()}else{window.close();'
             'setTimeout(function(){location.href=\'./\'},200)}">✕ 닫기</a>')
    return (f'<div style="{SUB_STYLE}">{mk}<a href="./" style="{SUB_LINK}">← 강세종목 목록</a>{close}</div>')


# 강세종목 리포트 페이지에 덧붙이는 것 (리포트 원본은 Claude가 만들어 모양이 조금씩 달라도 같게 적용):
#  - 큰 닫기 버튼(오른쪽 아래 고정) + 오른쪽 위 닫기(처음엔 메뉴 아래 막대 오른쪽, 스크롤하면 화면 오른쪽 위에 고정): 이전 화면 → 창 닫기 → 강세종목 목록
#  - 인쇄·PDF: 배경색 유지, 섹션마다 쪽을 나누지 않고 이어서 (빈 쪽·큰 여백 금지), 차트·표 한 덩어리만 안 잘리게, 쪽번호
STRONG_FIX = """<style>
.st-close{position:fixed;right:16px;bottom:18px;z-index:50;height:56px;padding:0 22px;border-radius:28px;background:#F2A900;color:#3D3A35!important;
 font:900 18px/56px 'Noto Sans KR',sans-serif;text-decoration:none!important;box-shadow:0 4px 14px rgba(0,0,0,.3)}
.st-close.st-top{top:12px;bottom:auto;z-index:10000;height:40px;padding:0 16px;border-radius:20px;font-size:15px;line-height:40px;opacity:0;pointer-events:none;transition:opacity .2s}
.st-close.st-top.on{opacity:1;pointer-events:auto}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
@page{size:A4;margin:10mm 9mm 13mm;@bottom-right{content:counter(page) " / " counter(pages);font:9pt 'Noto Sans KR',sans-serif;color:#7A746A}}
@media print{.st-close,.st-close-bar,.topnav,nav{display:none!important}
 *{break-before:auto!important;page-break-before:auto!important}
 .page,.sec,section{break-after:auto!important;page-break-after:auto!important;min-height:0!important;height:auto!important;box-shadow:none!important;margin-bottom:6mm!important}
 svg,.chart,figure,.keydata,.photos,.mixbar,.legend,tr{break-inside:avoid} h2,h3,.figt{break-after:avoid}}
</style><a class="st-close st-top" href="./" onclick="event.preventDefault();if(history.length>1){history.back()}else{window.close();setTimeout(function(){location.href='./'},200)}">✕ 닫기</a><a class="st-close" href="./" onclick="event.preventDefault();if(history.length>1){history.back()}else{window.close();setTimeout(function(){location.href='./'},200)}">✕ 닫기</a><script>(function(){var t=document.querySelector('.st-close.st-top'),b=document.querySelector('.st-close-bar');
var n=document.querySelector('nav');
function f(){var nb=n?Math.max(0,n.getBoundingClientRect().bottom):0,r=b?b.getBoundingClientRect().bottom:0;t.style.top=(nb+10)+'px';t.classList.toggle('on',r<nb)}addEventListener('scroll',f,{passive:true});f()})()</script>"""


def build_strong():
    out = OUT / "strong"
    out.mkdir(parents=True, exist_ok=True)
    items = strong_items()
    rows, last = [], ""
    for it in items:
        if it["date"] != last:
            last = it["date"]
            rows.append(f'<div class="st-day">{label(last)}{strong_market([x for x in items if x["date"] == last])}</div>')
        rows.append(strong_card(it, it["file"]))
        # 리포트 원본(Artifact용 조각 HTML)을 온전한 페이지로 감싸고 맨 위에 메뉴를 붙인다
        src = (US_STRONG / it["file"]).read_text(encoding="utf-8")
        if not re.search(r"<body", src, re.I):
            src = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                   '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"></head>'
                   f'<body>{src}</body></html>')
        src = re.sub(r"</body>", lambda _: STRONG_FIX + "</body>", src, count=1, flags=re.I) if re.search(r"</body>", src, re.I) else src + STRONG_FIX
        (out / it["file"]).write_text(with_nav(src, "../", "strong/", extra=strong_bar(it)), encoding="utf-8")
    body = (f'<style>{STRONG_CSS}</style>'
            + ("".join(rows) or '<p class="err">아직 올린 강세종목 리포트가 없습니다.</p>')
            + '<div class="st-note">전일 미국장에서 강세를 보인 종목을 골라 만든 종목 리포트입니다. 재무는 SEC 공시(10-K·10-Q), '
              '주가는 각 리포트에 적힌 출처와 기준 시각을 따릅니다. 미국 종목은 파란 🇺🇸 미국시장 배지, 미국 외 시장 종목(예: 🇨🇳 중국시장, 🇰🇷 한국시장)은 빨간 배지로 표시하고, 재무는 그 나라 공시(한국은 OpenDART)를 씁니다. 매수·매도 추천이 아닌 판단 근거 정리이며, 투자 판단의 참고 자료입니다.'
              + ('<br>날짜 옆 지수(나스닥·S&amp;P500, 중국 종목은 상하이종합·과창판50 등): 전일 종가 기준 등락(Yahoo Finance)' if any(it.get("market") for it in items) else '') + '</div>')
    (out / "index.html").write_text(page("🚀 전일 미국장 강세종목", body, "../", "strong/", "US STRONG STOCKS",
                                         "날짜별 · 같은 날은 등락률 높은 순"), encoding="utf-8")
    return items


def _strong_title(its):
    """그날 카드가 전부 미국 외 시장(예: 중국)이면 제목에서 '미국'을 빼고 시장 이름을 붙인다."""
    rgs = sorted({it.get("region", "") for it in its})
    return "🚀 전일 미국시장 강세종목" if rgs == [""] else ("🚀 전일 강세종목 · " + " · ".join(escape(r) for r in rgs if r) if "" not in rgs else "🚀 전일 강세종목")


def kr_until(it):
    """한국시장 강세종목을 홈에서 내릴 시각: 올린 시각(posted, KST) 다음에 오는 첫 장 마감(평일 15:30).
    posted 가 없으면 등록일 다음 평일 15:30 (일찍 내리지 않게)."""
    if it.get("posted"):
        t = datetime.strptime(it["posted"][:16], "%Y-%m-%d %H:%M")
        d = t.date() if t.strftime("%H:%M") < "15:30" else t.date() + timedelta(days=1)
    else:
        d = datetime.strptime(it["date"], "%Y-%m-%d").date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return f"{d}T15:30:00+09:00"


def strong_home(items):
    if not items:
        return ""
    day = items[0]["date"]
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    # 그날 것 + 앞서 올린 한국시장 종목 중 아직 장 마감 전인 것 (다음 날 아침 미국 종목이 올라와도 15:30까지는 함께)
    today = [it for it in items if it["date"] == day or ("한국" in (it.get("region") or "") and kr_until(it) > now)]
    # 한국시장 종목(전일 국내장 강세)은 올린 뒤 첫 장 마감(15:30)이 지나면 홈에서 내린다 (/strong/ 목록에는 남는다).
    kr = [it for it in today if "한국" in (it.get("region") or "")]
    rest = [it for it in today if it not in kr]
    tag = lambda html, u: html.replace("<a ", f'<a data-kr-until="{u}" ', 1)
    cards = "".join(tag(strong_card(it, "strong/" + it["file"]), kr_until(it)) if it in kr else strong_card(it, "strong/" + it["file"]) for it in today)
    mk = strong_market(rest) + (f'<span data-kr-until="{max(kr_until(it) for it in kr)}">{strong_market(kr)}</span>' if kr and strong_market(kr) else "")
    # 전일 미국장 강세종목이라 등록일 17:00(KST)까지는 홈 맨 위에 두고, 그 뒤로는 해외주식 리포트 아래(#strong-low)로 내린다.
    # 사이트를 다시 빌드하지 않아도 되게 보는 사람 브라우저 시각으로 옮긴다.
    until = max([f"{day}T17:00:00+09:00"] + [kr_until(it) for it in kr])  # 한국 종목이 남아 있으면 그때까지 맨 위에
    return (f'<section class="sec" id="strong" data-until="{until}"'
            + (f' data-title-after="{_strong_title(rest)}"' if kr and rest else "") + f'><style>{STRONG_CSS}</style>'
            f'<div class="sec-h st-h"><h2>{_strong_title(today)}</h2>{mk}'
            f'<a href="strong/">{escape(day[5:].replace("-", "/"))} · 전체</a></div>{cards}'
            + ('<div class="st-note" style="margin-top:6px">지수: 전일 종가 기준 등락(Yahoo Finance)</div>'
               if strong_market(today) else "") + '</section>')


STRONG_LOW_JS = """<div id="strong-low"></div><script>(function(){var s=document.getElementById('strong'),l=document.getElementById('strong-low');
 if(s&&l&&Date.now()>=Date.parse(s.dataset.until))l.appendChild(s);
 /* 한국시장 강세종목은 그날 15:30 장 마감 뒤 내린다. 남은 카드가 없으면 칸째로 */
 function kr(){if(!s)return;var gone=0;s.querySelectorAll('[data-kr-until]').forEach(function(e){if(Date.now()>=Date.parse(e.dataset.krUntil)){e.remove();gone=1}});
  if(!gone)return;if(!s.querySelector('a.st'))s.remove();else if(s.dataset.titleAfter&&!s.querySelector('a.st[data-kr-until]')){var h=s.querySelector('h2');if(h)h.textContent=s.dataset.titleAfter}}
 kr();setInterval(kr,60000)})()</script>"""


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


# 실시간 작성 종목 보고서: 국내 실적 급증 카드가 나간 종목마다 kb-market-report surge-report 작업이 만드는 PDF.
# 목록은 surge-reports 브랜치 reports/index.json (최신순) → 화면에서 바로 읽어 날짜별로 보여 준다(사이트 다시 빌드 필요 없음).
REPORT_SRC = ("https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/reports/index.json?ref=surge-reports",
              "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/surge-reports/reports/index.json")
REPORT_CSS = """
.rp-day{margin:18px 0 6px;font-size:15px;font-weight:800;color:var(--muted)}
.rp{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;background:var(--card);border:1px solid var(--line);border-left:5px solid #F2A900;
  border-radius:12px;padding:12px 14px;margin-top:8px}
.rp .nm{font-size:16.5px;font-weight:800;flex:1 1 100%;min-width:0}.rp .op{flex:1 1 auto}.rp .nm small{font-size:12.5px;color:var(--muted);font-weight:600;margin-left:6px}
.rp .ds{flex:1 1 100%;font-size:13.5px;line-height:1.45;color:var(--text);margin-top:-2px;word-break:keep-all}
.rp .ds:empty{display:none}
.rp .op{font-size:14px;font-weight:700}.rp .op b.up{color:var(--up)}.rp .op span{font-size:12px;color:var(--muted);font-weight:600}
.rp a.go{padding:7px 12px;border-radius:9px;background:#F2A900;color:#3D3A35;font-weight:800;text-decoration:none;font-size:14px;white-space:nowrap}
.rp-note{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:16px}
"""
REPORT_JS = r"""<script>
(function(){var SRC=%s,DESC=%s,box=document.getElementById('rp');
 function rp(u){var m=/\/surge-reports\/reports\/(\d{4}-\d{2}-\d{2}\/\w+)\.pdf/.exec(u||'');return m?'view.html?f='+m[1]:u}
 function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function eok(v){return v==null?'-':(Math.abs(v)>=1e4?(v/1e4).toFixed(2)+'조':Math.round(v).toLocaleString()+'억')}
 function draw(rows){if(!rows||!rows.length){box.innerHTML='<p class="err">아직 만든 보고서가 없습니다. 실적 급증 카드가 나가면 몇 분 뒤 여기에 생깁니다.</p>';return}
  var last='',h='';rows.forEach(function(r){if(r.day!==last){last=r.day;h+='<div class="rp-day">'+e(r.day)+'</div>'}
   var chg=r.turn?'<b class="up">흑자전환</b>':(r.chg!=null?'<b class="up">'+(r.chg>0?'+':'')+r.chg.toFixed(1)+'%%</b>':'');
   h+='<div class="rp"><div class="nm">'+e(r.name)+'<small>'+e(r.code)+(r.period?' · '+e(r.period)+' 잠정':'')+'</small></div>'+
    '<div class="ds" data-day="'+e(r.day)+'" data-code="'+e(r.code)+'">'+e(DESC[r.code]||'')+'</div>'+
    (r.op!=null?'<div class="op">영업이익 '+eok(r.op)+' '+chg+(r.basis?' <span>'+e(r.basis)+'</span>':'')+'</div>':'')+
    '<a class="go" href="'+e(rp(r.pdf))+'" target="_blank" rel="noopener">📑 보고서 열기</a></div>'});box.innerHTML=h;
  box.querySelectorAll('.ds:empty').forEach(biz)}
 /* 한 줄 설명이 없는 종목: 보고서(HTML)의 '주요 사업' 첫 문장을 가져온다 */
 function biz(el){if(!/^\d{4}-\d{2}-\d{2}$/.test(el.dataset.day)||!/^\w{6}$/.test(el.dataset.code))return;
  fetch('https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/surge-reports/reports/'+el.dataset.day+'/'+el.dataset.code+'.html')
  .then(function(r){if(!r.ok)throw 0;return r.text()}).then(function(t){var m=/<b>주요 사업<\/b>([^<]*)/.exec(t);if(!m)return;
   var d=document.createElement('textarea');d.innerHTML=m[1];var s=d.value.replace(/\s+/g,' ').replace(/^당사는\s*/,'').split(/(?<=다\.)/)[0].replace(/매출 구성.*$/,'').trim();
   if(s.length>70)s=s.slice(0,68)+'…';el.textContent=s}).catch(function(){})}
 function get(i){if(i>=SRC.length)return draw(null);
  fetch(i?SRC[i]+'?t='+Date.now():SRC[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(draw).catch(function(){get(i+1)})}
 get(0);
})();
</script>""" % (json.dumps(REPORT_SRC), json.dumps(KR_COMPANY, ensure_ascii=False))


# 보고서 PDF 바로 열기: surge-reports 브랜치의 PDF를 raw 주소에서 받아 브라우저 PDF 화면으로 연다
# (GitHub 화면이 아니라 파일 자체가 보이게). view.html?f=2026-10-22/300120
REPORT_VIEW = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>종목 보고서</title><style>
*{box-sizing:border-box}body{margin:0;background:#E9E5DC;color:#3D3A35;font:16px/1.5 'Noto Sans KR',sans-serif}
.bar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:10px 14px;background:#3D3A35;color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.bar .t{flex:1;min-width:0;font-weight:800;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar a{flex:none;display:inline-flex;align-items:center;justify-content:center;height:44px;padding:0 16px;border-radius:12px;font-weight:800;font-size:16px;text-decoration:none}
.sv{background:#5A564F;color:#fff}.cl{background:#F2A900;color:#3D3A35;min-width:96px}
#pg{max-width:900px;margin:0 auto;padding:12px 8px 96px}#pg canvas{display:block;width:100%;height:auto;margin:0 0 10px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.15)}
#m{padding:40px 16px;text-align:center}
.fab{position:fixed;right:16px;bottom:18px;z-index:6;height:56px;padding:0 22px;border-radius:28px;background:#F2A900;color:#3D3A35;font-weight:900;font-size:18px;
 display:inline-flex;align-items:center;text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.3)}
</style></head><body>
<div class="bar"><span class="t" id="t">📑 종목 보고서</span><a class="sv" id="sv" href="#" hidden>PDF 저장</a><a class="cl" href="#" data-close>✕ 닫기</a></div>
<div id="pg"><div id="m">보고서 여는 중…</div></div><a class="fab" href="#" data-close>✕ 닫기</a>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script>
(function(){var f=(new URLSearchParams(location.search).get('f')||'').replace(/[^0-9A-Za-z_\/-]/g,''),m=document.getElementById('m'),pg=document.getElementById('pg');
 document.querySelectorAll('[data-close]').forEach(function(a){a.onclick=function(e){e.preventDefault();  /* 이전 화면 → 창 닫기 → 홈 */
  if(history.length>1){history.back();return}window.close();setTimeout(function(){location.href='../'},200)}});
 if(!/^\d{4}-\d{2}-\d{2}\/[0-9A-Za-z]{6}$/.test(f)){m.textContent='보고서 주소가 올바르지 않습니다.';return}
 var raw='https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/surge-reports/reports/'+f+'.pdf',name=f.replace('/','_')+'_종목보고서.pdf';
 fetch(raw+'?t='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw r.status;return r.arrayBuffer()}).then(function(buf){
  var u=URL.createObjectURL(new Blob([buf],{type:'application/pdf'})),sv=document.getElementById('sv');sv.href=u;sv.download=name;sv.hidden=false;
  if(!window.pdfjsLib){location.replace(u);return}  /* 그림 엔진을 못 받으면 브라우저 PDF 화면으로 */
  pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  return pdfjsLib.getDocument({data:buf}).promise.then(function(doc){m.remove();var w=Math.min(pg.clientWidth-16,900),dpr=Math.min(window.devicePixelRatio||1,2.5),chain=Promise.resolve();
   for(var i=1;i<=doc.numPages;i++)(function(i){chain=chain.then(function(){return doc.getPage(i).then(function(p){var v0=p.getViewport({scale:1}),v=p.getViewport({scale:w/v0.width*dpr}),
    c=document.createElement('canvas');c.width=v.width;c.height=v.height;pg.appendChild(c);return p.render({canvasContext:c.getContext('2d'),viewport:v}).promise})})})(i);
   return chain})})
 .catch(function(s){m.innerHTML=(s===404?'보고서를 아직 만드는 중입니다. 5~10분 뒤 다시 열어 주세요.':'보고서를 불러오지 못했습니다.')})})();
</script></body></html>"""


def build_reports():
    body = (f'<style>{REPORT_CSS}</style><div id="rp"><p class="err">불러오는 중…</p></div>'
            '<div class="rp-note">국내 실적 급증 카드(전분기 대비 영업이익 +50% 이상 또는 흑자전환)가 나간 종목마다 자동으로 만든 요약 보고서입니다. '
            '일봉·수급(KB증권 Open API), 10년·분기 영업이익, 미상환 CB·BW·EB, 주요 사업·매출처(OpenDART)를 담았습니다. '
            '추정치는 컨센서스가 아닌 산출값이며, 투자 판단의 참고 자료입니다.</div>' + REPORT_JS)
    dest = OUT / "reports"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "view.html").write_text(REPORT_VIEW, encoding="utf-8")
    (dest / "index.html").write_text(page("📑 실시간 작성된 종목 보고서", body, "../", "reports/", "SURGE REPORT",
                                          "실적 급증 카드가 나간 종목 · 최신순"), encoding="utf-8")


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
# 홈 한 페이지에서 스크롤만으로 오전 데일리 → 장마감 수급 등을 모두 본다.
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


TOOLS_CSS = """.home>#tools{order:99}  /* 계산기·공부는 시간대(장중 수급 맨 위 등)와 상관없이 항상 홈 맨 아래 */
.tools-g{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:520px){.tools-g{grid-template-columns:1fr}}
.tool{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.tool:active{background:var(--line)}
.tool b{display:block;font-size:17px}
.tool span{display:block;font-size:13px;color:var(--muted);margin-top:4px;line-height:1.45}
.tool em{display:block;font-size:12px;color:var(--accent);font-style:normal;font-weight:700;margin-top:8px}"""
# 아티팩트로 만든 계산기 두 가지 (주소는 MENU 와 같은 것을 쓴다)
TOOLS = (("연금 계산기", "💰", "퇴직연금·개인연금을 연금으로 받을 때 내는 세금과 해마다의 수령한도를 계산합니다."),
         ("라이프 플랜", "🗓️", "소득·지출·교육비·주택을 넣어 평생 현금흐름과 자산 흐름을 그려 봅니다."),
         ("재무제표 공부", "📒", "재무제표로 지뢰 종목 거르기, 업종별 체크리스트, 용어사전, 사례노트."),
         ("놀이터", "🎮", "⏱ 60초 챌린지 · 시가총액 · 차트 · 차트 다음은? · 업종 · 주가 · 1년 수익률 · 실적 대결 — 게임 9가지와 등급·오늘의 미션!"))  # 전략 검증(lab/)은 2026-10-27 멈춤 — 돌파매매 전략으로 바꿔 다시 연다


# 홈 왼쪽 날개 광고 (제주 만보농장). 본문(1080px) 왼쪽 빈 공간에만 작게 띄우고, 공간이 없는 화면(휴대폰·좁은 창)에서는 숨긴다.
# 누르면 새 탭으로 밴드가 열리고, 클릭 수는 방문자 현황(c-ad-manbo)에서 본다.
AD_URL = "https://www.band.us/@manbofarm"
AD_CSS = """.wing{display:none;word-break:keep-all}
@media (min-width:1440px){
.wing{display:block;position:fixed;top:120px;width:150px;z-index:5;text-decoration:none;color:inherit;background:var(--card);
 border:1px solid var(--line);border-radius:12px;padding:8px;box-shadow:0 2px 10px rgba(0,0,0,.06);font-size:12px;line-height:1.4}
.wing.l{right:calc(50% + 540px + 24px)}
.wing:hover{border-color:#2f7d32}
.wing img{display:block;width:100%;height:auto;border-radius:6px;background:#fff}
.wing .wt{display:block;margin-top:6px;font-weight:800;color:#2f7d32}
.wing .wp{display:block;margin-top:2px;font-weight:700}.wing .wp strong{color:#e8590c;font-size:14px}
.wing .wg{display:flex;justify-content:space-between;align-items:center;margin-top:4px;color:var(--muted);font-size:11px}
.wing .wg i{font-style:normal;border:1px solid var(--line);border-radius:999px;padding:0 6px}
.wing .wg b{color:#2f7d32}}
@media (min-width:1320px) and (max-width:1439px){
.wing{display:block;position:fixed;top:120px;width:100px;z-index:5;text-decoration:none;color:inherit;background:var(--card);
 border:1px solid var(--line);border-radius:10px;padding:6px;font-size:11px;line-height:1.35}
.wing.l{right:calc(50% + 540px + 8px)}
.wing img{display:block;width:100%;height:auto;border-radius:5px;background:#fff}
.wing .wt{display:block;margin-top:4px;font-weight:800;color:#2f7d32}
.wing .wp{display:block;margin-top:2px;font-weight:700}.wing .wp strong{color:#e8590c;font-size:12px}
.wing .wg{display:flex;justify-content:space-between;align-items:center;margin-top:3px;color:var(--muted);font-size:10px}
.wing .wg i{font-style:normal;border:1px solid var(--line);border-radius:999px;padding:0 5px}
.wing .wg b{color:#2f7d32}}
.wing-m{display:none}
@media (max-width:1319px){
/* 휴대폰 광고 띠는 항상 홈 맨 위: 다른 칸(방문자 띠 -3, 미국 강세 -3, 실적속보 -2, 장중 수급 -1)보다 작은 order */
.home .wing-m{order:-9;display:flex;align-items:center;gap:2px;margin:0 0 12px;background:var(--card);border:1px solid var(--line);
 border-left:4px solid #2f7d32;border-radius:12px;padding:6px 10px 6px 6px;word-break:keep-all}
.wing-m a{flex:1;display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit;min-width:0}
.wing-m img{width:36px;height:auto;border-radius:4px;flex:none;background:#fff}
.wing-m .t{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:8px;row-gap:1px;font-size:12.5px;line-height:1.35;min-width:0}
.wing-m .t b{font-size:13px;color:#2f7d32}.wing-m .t strong{color:#e8590c}
.wing-m .t i{font-style:normal;color:var(--muted);font-size:11px}
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .wing-m .t b{color:#69db7c}:root:not([data-theme=light]) .wing-m .t strong{color:#ff922b}}
:root[data-theme=dark] .wing-m .t b{color:#69db7c}:root[data-theme=dark] .wing-m .t strong{color:#ff922b}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .wing .wt,:root:not([data-theme=light]) .wing .wg b{color:#69db7c}
 :root:not([data-theme=light]) .wing .wp strong{color:#ff922b}}
:root[data-theme=dark] .wing .wt,:root[data-theme=dark] .wing .wg b{color:#69db7c}
:root[data-theme=dark] .wing .wp strong{color:#ff922b}"""


def ad_home():
    """홈 왼쪽 날개 배너 (포스터)."""
    a = f'href="{AD_URL}" target="_blank" rel="noopener sponsored" data-ad="manbo" aria-label="제주 만보농장 황금향 특가 (광고)"'
    foot = '<span class="wg"><i>광고</i><b>밴드 주문 ›</b></span>'
    return (f'<a class="wing l" {a}><img src="assets/ad-manbo.webp" width="300" height="427" loading="lazy" alt="제주 만보농장 황금향 비상품 특별 이벤트 포스터">'
            f'<span class="wt">🍊 제주 만보농장</span><span class="wp">황금향 비상품 특가</span>{foot}</a>')


def ad_strip():
    """휴대폰·좁은 화면: 홈 맨 위 한 줄 광고 띠 (내용을 가리지 않아 닫기 버튼은 두지 않는다). 넓은 화면에선 숨기고 왼쪽 날개를 쓴다."""
    a = f'href="{AD_URL}" target="_blank" rel="noopener sponsored" data-ad="manbo" aria-label="제주 만보농장 황금향 특가 (광고)"'
    return (f'<style>{AD_CSS}</style><div class="wing-m" id="wingm"><a {a}><img src="assets/ad-manbo.webp" width="300" height="427" loading="lazy" alt="">'
            '<span class="t"><b>🍊 제주 만보농장</b><span>황금향 5kg <strong>3만원</strong> · 10kg <strong>5만5천원</strong></span><i>광고 · 밴드 주문 ›</i></span></a>'
            '</div>')


# ---------- 오늘의 주식 퀴즈 (홈, 계산기·공부 바로 위) ----------
# 날마다 3문제: quiz/questions.json(주식 상식, "퀴즈 추가해줘"로 늘린다) 2개 + study/terms.json(용어사전)으로 만든 용어 문제 1개.
# 문제는 보는 사람 브라우저가 한국 날짜로 고르므로 사이트를 다시 만들지 않아도 자정(KST)에 바뀐다. 푼 기록은 그 기기에만 남는다.
QUIZ_FILE = ROOT / "quiz" / "questions.json"
QUIZ_CSS = """.home>#quiz{order:98}
#quiz .qz{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-top:10px}
#quiz .qz-top{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--muted)}
#quiz .qz-top b{color:var(--text)}
#quiz .qc{display:inline-block;font-size:11.5px;font-weight:800;padding:2px 8px;border-radius:6px;background:#FBE7B0;color:#3D3A35}
#quiz .qq{font-size:16.5px;font-weight:800;line-height:1.5;margin:8px 0 10px;word-break:keep-all}
#quiz .qd{font-size:15px;font-weight:600;line-height:1.55;margin:-2px 0 10px;padding:10px 12px;border-radius:10px;background:var(--bg);word-break:keep-all}
#quiz .qo{display:grid;gap:7px}
#quiz .qo button{font:600 15px/1.4 inherit;text-align:left;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);
 color:var(--text);cursor:pointer;word-break:keep-all}
#quiz .qo button:hover:enabled{border-color:#F2A900}
#quiz .qo button.ok{background:#e6f6ec;border-color:#2f9e44;color:#1b5e2b;font-weight:800}
#quiz .qo button.no{background:#fdecec;border-color:#e03131;color:#a51d1d}
#quiz .qo button:disabled{cursor:default}
#quiz .qx{display:none;margin-top:10px;font-size:14px;line-height:1.6;padding:10px 12px;border-left:4px solid #F2A900;background:var(--bg);border-radius:0 10px 10px 0;word-break:keep-all}
#quiz .qz.done .qx{display:block}
#quiz .qx b.r{color:#2f9e44}#quiz .qx b.w{color:#e03131}
#quiz .qsum a{font-size:13.5px;color:inherit}
#quiz .qsum{margin-top:12px;font-size:15px;font-weight:800;text-align:center;padding:10px;border-radius:12px;background:#FBE7B0;color:#3D3A35}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) #quiz .qo button.ok{background:#16301f;color:#8ce99a}
 :root:not([data-theme=light]) #quiz .qo button.no{background:#3a1c1c;color:#ffa8a8}}
:root[data-theme=dark] #quiz .qo button.ok{background:#16301f;color:#8ce99a}:root[data-theme=dark] #quiz .qo button.no{background:#3a1c1c;color:#ffa8a8}"""
QUIZ_JS = r"""(function(){var box=document.getElementById('qzb');if(!box)return;
var day=new Date(Date.now()+9*36e5).toISOString().slice(0,10),seed=0;
for(var i=0;i<day.length;i++)seed=(seed*31+day.charCodeAt(i))>>>0;
function rnd(){seed=(seed+0x6D2B79F5)>>>0;var t=seed;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296}
function pick(a){return a[Math.floor(rnd()*a.length)]}
function shuf(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(rnd()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
var qs=[];
function mk(b,id,cat){return{id:id,cat:cat||b.cat,q:b.q,o:shuf(b.choices.map(function(c,i){return{t:c,ok:i===b.answer}})),x:b.explain,link:b.link}}
var grp=function(id){var g=id.split(':')[0];return g==='px'?'ef':g},used={};
shuf(NEWS).sort(function(a,b){return (b.day||'').localeCompare(a.day||'')}).forEach(function(n){if(qs.length<3&&!used[grp(n.id)]){used[grp(n.id)]=1;qs.push(mk(n,n.id,'오늘의 소식 · '+n.cat))}});
var bank=shuf(QB.map(function(b,i){return[b,i]})),useTerm=TERMS.length>=4&&(qs.length<3||(seed&1)),bi=0;
while(qs.length<(useTerm?3:4)&&bi<bank.length){qs.push(mk(bank[bi][0],'b'+bank[bi][1]));bi++}
if(useTerm){var t=pick(TERMS),same=TERMS.filter(function(x){return x.cat===t.cat&&x.term!==t.term}),
 rest=TERMS.filter(function(x){return x.term!==t.term}),pool=same.length>=3?same:rest,dis=shuf(pool).slice(0,3);
 var core=t.term.split(/[\s(]/)[0],d=t.def;[t.term,core].forEach(function(w){if(w&&w.length>1)d=d.split(w).join('○○')});
 qs.push({id:'t:'+t.term,cat:'용어 · '+t.cat,q:'다음 설명에 맞는 용어는?',d:d,o:shuf([{t:t.term,ok:true}].concat(dis.map(function(x){return{t:x.term,ok:false}}))),
  x:'<b>'+esc(t.term)+'</b>'+(t.formula?' · '+esc(t.formula):'')+(t.point?'<br>'+esc(t.point):'')+' <a href="study/#term">용어사전 ›</a>',xh:1})}
var KEY='quiz2-'+day,saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(e){}}
function streak(){try{var s=JSON.parse(localStorage.getItem('quiz-streak')||'{}'),y=new Date(Date.parse(day)-864e5).toISOString().slice(0,10);
 if(s.last===day)return s.n;s={last:day,n:s.last===y?(s.n||0)+1:1};localStorage.setItem('quiz-streak',JSON.stringify(s));return s.n}catch(e){return 1}}
function count(){try{if(localStorage.getItem('brian-admin')==='1'||saved.c)return;saved.c=1;save();var d=day.replace(/-/g,'');
 ['c-quiz-'+d,'t-c-quiz'].forEach(function(k){fetch(QAPI+'/hit/'+QNS+'/'+k,{cache:'no-store'}).catch(function(){})})}catch(e){}}
function sum(){var n=0,a=0;qs.forEach(function(q){if(saved[q.id]!=null){a++;if(q.o[saved[q.id]]&&q.o[saved[q.id]].ok)n++}});var el=document.getElementById('qzs');
 if(a<qs.length){el.hidden=true;return}el.hidden=false;
 el.innerHTML=(n===qs.length?'🎉 ':'')+qs.length+'문제 중 '+n+'개 정답'+' · 연속 '+streak()+'일째 · 내일 새 문제가 나와요'+
 '<br><a href="study/#quiz">더 풀어 보기: 재무제표 공부 퀴즈 ›</a>'}
function show(i){var q=qs[i],c=document.getElementById('qz'+i),bs=c.querySelectorAll('.qo button'),s=saved[q.id];if(!q.o[s])return;
 c.classList.add('done');bs.forEach(function(b,j){b.disabled=true;if(q.o[j].ok)b.classList.add('ok');else if(j===s)b.classList.add('no')});
 c.querySelector('.qx').innerHTML=(q.o[s].ok?'<b class="r">정답!</b> ':'<b class="w">아쉬워요.</b> ')+(q.xh?q.x:esc(q.x))+(q.link?' <a href="'+esc(q.link)+'">자세히 보기 ›</a>':'')}
box.innerHTML=qs.map(function(q,i){return '<div class="qz" id="qz'+i+'"><div class="qz-top"><span class="qc">'+esc(q.cat)+'</span><span>'+(i+1)+' / '+qs.length+'</span></div>'+
 '<div class="qq">Q'+(i+1)+'. '+esc(q.q)+'</div>'+(q.d?'<div class="qd">'+esc(q.d)+'</div>':'')+
 '<div class="qo">'+q.o.map(function(o,j){return '<button type="button" data-i="'+i+'" data-j="'+j+'">'+'①②③④'[j]+' '+esc(o.t)+'</button>'}).join('')+'</div>'+
 '<div class="qx"></div></div>'}).join('')+'<div class="qsum" id="qzs" hidden></div>';
box.addEventListener('click',function(e){var b=e.target.closest('button[data-i]');if(!b||b.disabled)return;var i=+b.dataset.i;
 saved[qs[i].id]=+b.dataset.j;save();count();show(i);sum()});
qs.forEach(function(q,i){if(saved[q.id]!=null)show(i)});sum();
document.getElementById('qzd').textContent=day.slice(5).replace('-','/')})();"""


# 오늘 홈페이지에 올라온 내용(강세종목·실적 속보·국내 영업이익 급증·목표주가 변동)으로 만드는 문제.
# 사이트를 만들 때(2시간마다) 새로 만들고, 정답·해설은 그 자료의 숫자를 그대로 쓴다. 최근 3일 안의 자료만 쓴다.
NQ_FRESH_DAYS = 3
NQ_SECTORS = ["반도체 장비", "바이오 신약", "2차전지 소재", "클라우드 소프트웨어", "뷰티 전문 리테일", "전기차",
              "온라인 광고 플랫폼", "원자력 발전(SMR)", "데이터센터 전력 장비", "우주 발사체", "게임", "조선"]
NQ_KR_POOL = ["삼성전자", "SK하이닉스", "현대차", "NAVER", "카카오", "LG화학", "셀트리온", "KB금융", "POSCO홀딩스", "삼성SDI"]


def _nq_fresh(day, now):
    try:
        return 0 <= (now.date() - datetime.strptime(day[:10], "%Y-%m-%d").date()).days <= NQ_FRESH_DAYS
    except (TypeError, ValueError):
        return False


def _nq(qid, cat, q, right, wrong, explain, link="", day=""):
    wrong = [w for w in dict.fromkeys(wrong) if w and w != right][:3]
    if len(wrong) < 3:
        return None
    return {"id": qid, "cat": cat, "q": q, "choices": [right] + wrong, "answer": 0, "explain": explain, "link": link, "day": day}


def news_quiz(now, target=None, strong=None):
    """오늘의 소식 문제 목록 [{id, cat, q, choices(정답이 0번), answer, explain, link, day}]. 자료가 없으면 빈 목록."""
    out = []
    md = lambda day: f"{int(day[5:7])}/{int(day[8:10])}"
    # 1) 전일 미국장 강세종목: 어떤 회사인가
    for it in (strong or [])[:1]:
        if _nq_fresh(it.get("date", ""), now) and it.get("sector"):
            others = [x.get("sector") for x in strong[1:]] + NQ_SECTORS
            out.append(_nq(f"st:{it['file']}", "강세종목", f"오늘 강세종목 리포트로 다룬 {it['name']}은(는) 어떤 회사일까요?",
                           it["sector"], random.Random(it["file"]).sample(others, len(others)),
                           f"{it['name']}({it['ticker']}) · {it['sector']} · 전일 {it.get('changePct', 0):+.2f}%. {it.get('headline', '')}",
                           "strong/" + it["file"], it["date"]))
    # 2) 실적 속보 카드: 컨센서스 대비, 발표 뒤 주가
    for f in sorted(d.FLASH_DIR.glob("*.json"), reverse=True)[:3] if d.FLASH_DIR.is_dir() else []:
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _nq_fresh(c.get("day", ""), now):
            continue
        row = next((r for r in c.get("rows") or [] if len(r) > 3 and r[3] in ("상회", "부합", "하회")), None)
        if row:
            opts = {"상회": "예상보다 높았다(상회)", "부합": "예상과 비슷했다(부합)", "하회": "예상보다 낮았다(하회)"}
            right = opts[row[3]]
            out.append(_nq(f"ef:{f.stem}:{row[0]}", "실적 속보", f"{c['company']} {c.get('period', '')} {row[0]}은(는) 시장 예상(컨센서스)과 비교해 어땠을까요?",
                           right, [v for v in opts.values() if v != right] + ["실적을 발표하지 않았다"],
                           f"{row[0]} {row[1]} · {row[2]}. {c.get('verdict', '')}", "#earn", c["day"]))
        px = (c.get("px") or [None])[0] or {}
        ch = px.get("d1") if px.get("d1") is not None else px.get("c")
        if ch is not None:
            buckets = ["5% 넘게 올랐다", "0~5% 올랐다", "0~5% 내렸다", "5% 넘게 내렸다"]
            right = buckets[0 if ch > 5 else 1 if ch >= 0 else 2 if ch > -5 else 3]
            when = "발표 뒤 첫 정규장" if px.get("d1") is not None else f"{px.get('s', '발표 뒤')}({px.get('t', '')})"
            out.append(_nq(f"px:{f.stem}", "실적 속보", f"실적 발표 뒤 {c['company']} 주가는 어떻게 움직였을까요? ({when} 기준)",
                           right, [b for b in buckets if b != right],
                           f"{px.get('l', c['company'])}: 발표 전 종가 대비 {ch:+.2f}% ({when}). {c.get('verdict', '')}", "#earn", c["day"]))
    # 3) 국내 잠정실적 영업이익 급증 (kb earnings-live)
    try:
        with urllib.request.urlopen(urllib.request.Request(d.EARN_FEED, headers={"User-Agent": d.UA}), timeout=15) as r:
            feed = json.loads(r.read())
    except Exception as e:
        print("퀴즈: earnings-live 읽기 실패:", type(e).__name__, e, file=sys.stderr)
        feed = {}
    surge = [i for i in feed.get("items") or [] if str(i.get("surge")) in ("True", "true") and _nq_fresh(i.get("day", ""), now)]
    names = {i.get("name") for i in surge}
    for it in surge[:2]:
        pool = [x["company"] for x in (target or {}).get("up", []) + (target or {}).get("down", [])] + NQ_KR_POOL
        pool = [p for p in pool if p not in names]
        cons = it.get("cons") or []
        out.append(_nq(f"kr:{it['key']}", "국내 실적 공시", f"{md(it['day'])} 잠정실적 공시에서 영업이익이 전분기보다 크게 늘어 '영업이익 급증' 카드에 오른 회사는?",
                       it["name"], random.Random(it["key"]).sample(pool, len(pool)),
                       f"{it['name']}: " + " · ".join(cons[:2] if isinstance(cons, list) else [str(cons)]),
                       it.get("report") or "#earn", it["day"]))
    # 4) 목표주가 변동: 가장 크게 올린·내린 종목
    if target and _nq_fresh(target.get("day", ""), now):
        for key, word in (("up", "올린"), ("down", "내린")):
            best = {}
            for x in target.get(key) or []:
                if x["company"] not in best:
                    best[x["company"]] = x  # 이미 상승률(하락률) 순으로 정렬돼 있어 처음 것이 그 종목의 최대폭
            ranked = list(best.values())
            if len(ranked) >= 2 and abs(ranked[0]["pct"]) > abs(ranked[1]["pct"]):
                t0 = ranked[0]
                other = "down" if key == "up" else "up"  # 오답은 같은 쪽 다음 순위 → 반대쪽 종목 → 대형주 순으로 채운다
                wrong = [x["company"] for x in ranked[1:]] + [x["company"] for x in target.get(other) or []] + NQ_KR_POOL
                out.append(_nq(f"tp:{target['day']}:{key}", "목표주가 변동", f"{md(target['day'])} 증권사 리포트에서 목표주가를 가장 크게 {word} 종목은?",
                               t0["company"], wrong,
                               f"{t0['company']}: {t0['broker']} {t0.get('prev_target') or 0:,}원 → {t0.get('target') or 0:,}원 ({t0['pct']:+.1f}%) · '{t0.get('title', '')}'",
                               "target/", target["day"]))
    try:
        out += market_quiz(now, target)
    except Exception as e:  # 시장 자료 문제가 실패해도 퀴즈는 나머지로 만든다
        print("퀴즈: 시장 자료 문제 실패:", type(e).__name__, e, file=sys.stderr)
    return [q for q in out if q]


# ---- 시장 자료로 만드는 문제 (상한가 · 영업이익률 · 이자보상비율 · 실적 발표 예정 · 미국 신고가) ----
KB_LIVE_RAW = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/"
STUDY_FIN_RAW = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/study-fin/fin/"
US_BIG = ["애플", "마이크로소프트", "엔비디아", "아마존", "알파벳", "메타", "테슬라", "브로드컴", "넷플릭스", "오라클",
          "코스트코", "월마트", "JP모건", "비자", "일라이릴리", "AMD", "팔란티어", "마이크론"]


def _get_json(url, timeout=15):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": d.UA}), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _fin(codes):
    """study-fin 의 종목별 재무 숫자 {코드: (영업이익률 %, 이자보상배율, 기준 설명)} (금융업·숫자 없는 종목은 뺀다)."""
    from concurrent.futures import ThreadPoolExecutor
    def one(code):
        j = _get_json(STUDY_FIN_RAW + f"{code}.json", timeout=10)
        if not j or j.get("fin"):
            return code, None
        v, b = j.get("v") or {}, j.get("basis") or {}
        rev, op, it = (v.get("rev") or [None])[0], (v.get("op") or [None])[0], v.get("int")
        if not rev or op is None:
            return code, None
        icr = op / it if it and it > 0 else None
        return code, (op / rev * 100, icr, f"{b.get('now', '')} {b.get('fs', '')}".strip(), op, it)
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {c: r for c, r in ex.map(one, dict.fromkeys(codes)) if r}


def market_quiz(now, target=None):
    out = []
    md = lambda day: f"{int(day[5:7])}/{int(day[8:10])}"
    # 1) 상한가: 장마감 업종 지도(map.json, 네이버 증권 종목 등락률)
    m = _get_json(KB_LIVE_RAW + "map.json")
    if m and m.get("date") and _nq_fresh(f"{m['date'][:4]}-{m['date'][4:6]}-{m['date'][6:8]}", now):
        day = f"{m['date'][:4]}-{m['date'][4:6]}-{m['date'][6:8]}"
        etf = re.compile(r"^(KODEX|TIGER|RISE|ACE|SOL|KIWOOM|HANARO|ARIRANG|PLUS|KOSEF|TIMEFOLIO|KBSTAR|WON|BNK|1Q|마이티|에셋플러스|TRUSTON|UNICORN|파워)\b|ETN|레버리지|인버스|스팩")
        rows = [(st["n"], st["p"], sec["s"]) for mk in m["data"] for sec in m["data"][mk] for st in sec["st"]
                if st.get("p") is not None and not etf.search(st["n"])]  # ETF·ETN·스팩은 뺀다
        lim = [r for r in rows if 29.5 <= r[1] <= 30.0]
        near = [r for r in rows if 8 <= r[1] < 25]
        if lim and len(near) >= 3:
            rnd = random.Random(day)
            a, wrong = rnd.choice(lim), rnd.sample(near, 3)
            out.append(_nq(f"lim:{day}", "상한가", f"{md(day)} 상한가(+30%)로 마감한 종목은?", a[0], [w[0] for w in wrong],
                           f"{a[0]} +{a[1]:.2f}% ({a[2]}). 다른 보기는 크게 올랐지만 상한가는 아니었습니다: "
                           + ", ".join(f"{w[0]} +{w[1]:.1f}%" for w in wrong) + f" · 이날 상한가 {len(lim)}종목", "map/", day))
    # 2·3) 영업이익률 20% 넘는 종목 / 이자보상비율 1 미만 (study-fin 의 DART 정기보고서 숫자)
    snap = _get_json(KB_LIVE_RAW + "snapshot.json") or {}
    themes = (((snap.get("data") or {}).get("/api/themes") or {}).get("themes") or [])
    sday = str(snap.get("date") or "")
    sday = f"{sday[:4]}-{sday[4:6]}-{sday[6:8]}" if len(sday) == 8 else ""
    theme_st = {l["code"]: (l["name"], l.get("change_pct"), t["name"]) for t in themes[:12] for l in t.get("leaders") or []
                if l.get("code") and (l.get("change_pct") or 0) > 0}
    tgt = {x["code"]: x["company"] for x in (target or {}).get("up", []) + (target or {}).get("down", []) if x.get("code")} \
        if target and _nq_fresh(target.get("day", ""), now) else {}
    fin = _fin(list(theme_st) + list(tgt)) if (theme_st or tgt) else {}
    names = {**{c: v[0] for c, v in theme_st.items()}, **tgt}
    hi = [c for c, f in fin.items() if f[0] >= 20]
    lo = [c for c, f in fin.items() if 0 < f[0] < 12]
    if hi and len(lo) >= 3:
        rnd = random.Random(f"opm{now:%Y%m%d}")
        a, wrong = rnd.choice(hi), rnd.sample(lo, 3)
        out.append(_nq(f"opm:{now:%Y-%m-%d}:{a}", "재무 숫자", "오늘 홈페이지(상승 테마·목표주가 리포트)에 나온 종목 중 영업이익률이 20%를 넘는 종목은?",
                       names[a], [names[w] for w in wrong],
                       " · ".join(f"{names[c]} {fin[c][0]:.1f}%" for c in [a] + wrong) + f" (영업이익 ÷ 매출, {fin[a][2]}, DART 정기보고서)",
                       "study/#check", f"{now:%Y-%m-%d}"))
    tc = [c for c in theme_st if c in fin]
    bad = [c for c in tc if fin[c][1] is not None and fin[c][1] < 1]
    good = [c for c in tc if fin[c][1] is not None and fin[c][1] >= 3]
    if bad and len(good) >= 3 and _nq_fresh(sday, now):
        rnd = random.Random(f"icr{sday}")
        a, wrong = rnd.choice(bad), rnd.sample(good, 3)
        f = lambda c: (f"{names[c]} {fin[c][1]:.1f}배" if fin[c][3] >= 0 else f"{names[c]} 영업적자")
        out.append(_nq(f"icr:{sday}:{a}", "재무 숫자", f"{md(sday)} 상승 테마 종목 중 이자보상비율(영업이익 ÷ 이자비용)이 1이 안 되는 종목은?",
                       names[a], [names[w] for w in wrong],
                       " · ".join(f(c) for c in [a] + wrong) + f". 1 미만이면 영업으로 번 돈으로 이자도 못 낸다는 뜻 ({fin[a][2]}, DART)",
                       "study/#check", sday))
    # 거래대금 상위 10위 안에 들지 않은 종목 (kb 장마감 리포트의 거래대금 상위, 네이버 증권)
    tv = (snap.get("data") or {}).get("/api/top-value") or {}
    top = [x["name"] for x in tv.get("kospi") or [] if x.get("name")]
    if len(top) >= 10 and m and _nq_fresh(sday, now):
        caps = sorted(((st.get("v") or 0, st["n"]) for sec in m["data"].get("kospi", []) for st in sec["st"]
                       if st["n"] not in top and not st["n"].endswith("우")), reverse=True)[:15]  # 시가총액 큰 종목 중 상위 10위 밖
        if caps:
            rnd = random.Random(f"tv{sday}")
            a, ins = rnd.choice(caps)[1], rnd.sample(tv["kospi"][:10], 3)
            won = lambda v: f"{v / 10000:.2f}조" if v >= 10000 else f"{v:,}억"
            out.append(_nq(f"tv:{sday}:{a}", "거래대금", f"{md(sday)} 코스피 거래대금 상위 10위 안에 들지 않은 종목은?", a, [x["name"] for x in ins],
                           f"{a}은(는) 10위 밖이었습니다. " + " · ".join(f"{x['name']} {top.index(x['name']) + 1}위 {won(x['value_eok'] or 0)}" for x in ins)
                           + f" (1위 {top[0]}, ETF 제외, 네이버 증권)", "close/", sday))
    # 4) 앞으로 7일 안에 실적 발표가 예정된 회사 (증시 캘린더, 이미 발표한 회사는 뺀다)
    cal = d._calendar()
    try:
        ann = d.announced(now, sec=False)
    except Exception:
        ann = {}
    per = {}
    for k, items in cal.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", k):
            continue
        for e in ([items] if isinstance(items, str) else items):
            mm = d.CAL_EARN.match(str(e).strip())
            for n in (mm.group(2).split("·") if mm else []):
                per.setdefault(n.strip(), []).append(k)
    today = now.date()
    dd = lambda k: (datetime.strptime(k, "%Y-%m-%d").date() - today).days
    soon = [(n, min(k for k in ks if 0 <= dd(k) <= 7)) for n, ks in per.items()
            if any(0 <= dd(k) <= 7 for k in ks) and d.cal_norm(n) not in ann]
    far = [n for n, ks in per.items() if all(abs(dd(k)) >= 12 for k in ks)]
    if soon and len(far) >= 3:
        rnd = random.Random(f"cal{today}")
        (a, ak), wrong = rnd.choice(soon), rnd.sample(far, 3)
        out.append(_nq(f"cal:{today}:{a}", "실적 일정", "앞으로 7일 안에 실적 발표가 예정된 회사는? (증시 캘린더 기준)", a, wrong,
                       f"{a}: {md(ak)} 실적 예정. " + " · ".join(f"{w} {md(min(per[w], key=lambda k: abs(dd(k))))}" for w in wrong)
                       + " — 다른 보기는 발표가 이미 지났거나 한참 뒤입니다. 미국 회사 날짜는 현지 기준", "#daily", f"{today}"))
    # 5) 이번 주 미국 52주 신고가에 오르지 않은 종목 (아침 데일리의 신고가 화면)
    monday = today - timedelta(days=today.weekday())
    week = [p for p in sorted((ROOT / "archive" / "daily").glob("*/newhighs.html"))
            if DATE_RE.match(p.parent.name) and monday <= datetime.strptime(p.parent.name, "%Y-%m-%d").date() <= today]
    seen = {}
    for p in week:
        for nm in re.findall(r'<div class="nm"><a [^>]*>([^<]+)</a></div>', p.read_text(encoding="utf-8")):
            seen.setdefault(unescape(nm).strip(), p.parent.name)
    if len(week) >= 2 and len(seen) >= 3:
        big = [n for n in US_BIG if n in seen][:8] or list(seen)[:8]
        miss = [n for n in US_BIG if n not in seen]
        if len(big) >= 3 and miss:
            rnd = random.Random(f"nh{today}")
            a, ins = rnd.choice(miss), rnd.sample(big, 3)
            out.append(_nq(f"nh:{today}:{a}", "미국 신고가", f"이번 주({md(week[0].parent.name)}~{md(week[-1].parent.name)} 아침 데일리) 미국 52주 신고가 종목이 아닌 것은?",
                           a, ins, f"{a}은(는) 이번 주 신고가 목록에 없었습니다. " + " · ".join(f"{n} {md(seen[n])}" for n in ins)
                           + f" 신고가 (시총 상위 종목, 이번 주 신고가 {len(seen)}종목)", f"daily/{week[-1].parent.name}/newhighs.html", f"{today}"))
    return [q for q in out if q]


def quiz_home(news=()):
    """오늘의 주식 퀴즈 칸: 오늘의 소식 문제(news) 2개 + 주식 상식·용어 1개. 소식이 모자라면 상식 문제로 채운다."""
    try:
        bank = json.loads(QUIZ_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bank = []
    bank = [q for q in bank if len(q.get("choices") or []) == 4 and isinstance(q.get("answer"), int)]
    try:
        terms = [{k: t.get(k, "") for k in ("term", "cat", "def", "formula", "point")}
                 for t in json.loads((ROOT / "study" / "terms.json").read_text(encoding="utf-8")) if t.get("term") and t.get("def")]
    except (OSError, ValueError):
        terms = []
    if len(bank) < 2:
        return ""
    data = (f"var NEWS={json.dumps(list(news), ensure_ascii=False)},QB={json.dumps(bank, ensure_ascii=False)},TERMS={json.dumps(terms, ensure_ascii=False)},"
            f"QAPI={json.dumps(VISIT_API)},QNS={json.dumps(VISIT_NS)};").replace("</", "<\\/")
    return (f'<section class="sec" id="quiz"><style>{QUIZ_CSS}</style>'
            '<div class="sec-h"><h2>🧠 오늘의 주식 퀴즈</h2><span class="mt" id="qzd"></span></div>'
            '<div id="qzb"><p class="err">퀴즈를 불러오는 중…</p></div>'
            f'<script>{data}\n{QUIZ_JS}</script></section>')


def tools_home():
    """퇴직연금 계산기·라이프 플랜(아티팩트)로 가는 카드. 눌러서 새 탭으로 연다."""
    url = dict((label, href) for href, label in MENU)
    ext = ' target="_blank" rel="noopener"'
    cards = "".join(f'<a class="tool" href="{url[name]}"{ext if url[name].startswith("http") else ""}>'
                    f'<b>{icon} {name}</b><span>{desc}</span><em>눌러서 열기 ›</em></a>'
                    for name, icon, desc in TOOLS if name in url)
    return (f'<section class="sec" id="tools"><style>{TOOLS_CSS}</style>'
            f'<div class="sec-h"><h2>🧮 계산기·공부</h2></div><div class="tools-g">{cards}</div></section>')


def target_home(target):
    if not target:
        return ""
    up, down = target["up"], target["down"]
    inner = (f'<div class="tp-sum"><b>리포트 {target["n"]}건</b><b class="up">상향 {len(up)}</b><b class="down">하향 {len(down)}</b></div>'
             f'<h3>🔺 상향 상위</h3>{target_rows(up, "up", 5)}<h3>🔻 하향 상위</h3>{target_rows(down, "down", 5)}'
             + (f'<div class="tp-one">▶ {escape(target["one"])}</div>' if target["one"] else "")
             + f'<a class="btn" href="target/#all">전체 리포트 {target["n"]}건 보기 (신규·유지 포함)</a>')
    inner = one_tap(inner)
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


# 실적 속보: earnings_flash/YYYYMMDD-회사.json (발표 직후 수동 정리). 발표 6시간까지 맨 위(핵심 이슈 아래),
# 그 뒤 24시간까지는 데일리(오늘의 증시 캘린더) 칸 바로 아래로 내려가고 그 뒤 사라진다 (EARN_JS).
EARN_CSS = """
#earn{order:-2}.earn{background:var(--card);border:1px solid var(--line);border-left:5px solid #2f6fdb;border-radius:14px;padding:14px 16px;margin-top:10px}
.earn h2{margin:0 0 2px;font-size:18px}.earn h2 small{display:inline-block;font-size:14.5px;color:var(--text);opacity:.8;font-weight:700;margin-left:8px}
#earn-h{order:-2;margin-bottom:-4px}#earn-h h2{margin:0;font-size:20px;font-weight:900}#earn-h h2 small{font-size:14px;color:var(--muted);font-weight:700;margin-left:8px}
.earn.prev{border-left-color:var(--muted)}
.earn h2 .pvb{display:inline-block;font-size:12px;font-weight:800;color:#fff;background:var(--muted);border-radius:999px;padding:2px 8px;margin-right:6px;vertical-align:2px}
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
.earn .pxr{font-size:13.5px;line-height:1.75}.earn .pl{font-weight:700}.earn .ps,.earn .pr{font-size:12px;color:var(--muted)}
.earn .pxr b{font-size:16px;font-variant-numeric:tabular-nums}
.earn .pxr b.up,.earn .pxr b.down{font-size:21px;font-weight:900;letter-spacing:-.3px}
.earn .up{color:var(--up)}.earn .down{color:var(--down)}
.earn .rptw{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0 4px}
.earn .rpt-tap{color:#E5484D;font-weight:800;font-size:14.5px;white-space:nowrap;display:inline-block;animation:rpt-tap .9s ease-in-out infinite}
@keyframes rpt-tap{0%,100%{transform:translateX(0)}50%{transform:translateX(-8px)}}
@media print{.earn .rpt-tap{animation:none}}
.earn .rpt{display:inline-block;margin:0;padding:8px 14px;border-radius:10px;background:#F2A900;color:#3D3A35;font-weight:800;font-size:14.5px;text-decoration:none}
"""
EARN_JS = """<script>/* 실적 속보: 오늘(한국 날짜) 발표는 하루 종일 맨 위 '오늘의 실적속보'에 두고, 날이 바뀌면 데일리(오늘의 증시 캘린더) 칸
   바로 아래로 내려 '전일 실적 발표' 표를 붙인 뒤 발표 다음 날 오전 10시에 지운다.
   (예전엔 발표 6시간 뒤에 내려서, 아침 8시에 나온 실적이 오후 2시면 아래로 밀려났다) */
window.earnKst=function(ms){return new Date(ms+9*36e5).toISOString().slice(0,10)};
window.earnKeep=function(ts){var t=Date.parse(ts);return isNaN(t)||Date.now()<Date.parse(earnKst(t)+'T10:00:00+09:00')+864e5};
window.earnPrev=function(ts){var t=Date.parse(ts);return !isNaN(t)&&earnKst(t)!==earnKst(Date.now())};
window.earnPlace=function(){var now=Date.now(),daily=document.getElementById('daily'),old=document.getElementById('earn-old'),top=document.getElementById('earn');
 var hd0=document.getElementById('earn-h');if(!top&&hd0){top=document.createElement('section');top.className='sec';top.id='earn';hd0.insertAdjacentElement('afterend',top)}
 if(!old&&daily){old=document.createElement('section');old.className='sec';old.id='earn-old';daily.insertAdjacentElement('afterend',old)}
 if(old&&daily)old.style.order=getComputedStyle(daily).order;
 document.querySelectorAll('.earn[data-ts]').forEach(function(c){var ts=c.dataset.ts;
  if(!earnKeep(ts)){c.remove();return}
  if(earnPrev(ts)&&old&&c.parentNode!==old)old.appendChild(c);
  else if(!earnPrev(ts)&&top&&c.parentNode!==top)top.appendChild(c);  /* 수동·자동 카드를 한 칸에 모아 */
  var h=c.querySelector('h2');if(!h)return;
  if(earnPrev(ts)){c.classList.add('prev');
   if(!h.querySelector('.pvb')){var b=document.createElement('span');b.className='pvb';b.textContent='전일 실적 발표';h.insertBefore(b,h.firstChild)}}
  else{c.classList.remove('prev');var o=h.querySelector('.pvb');if(o)o.remove()}});
 if(top)Array.prototype.slice.call(top.querySelectorAll(':scope>.earn')).sort(function(a,b){return Date.parse(b.dataset.ts)-Date.parse(a.dataset.ts)})
  .forEach(function(c){top.appendChild(c)});  /* 오늘 발표는 발표 시각 순, 최신이 위 */
 ['earn','earn-live','earn-old'].forEach(function(id){var x=document.getElementById(id);if(x)x.hidden=!x.querySelector('.earn')});
 var hd=document.getElementById('earn-h');if(hd)hd.hidden=!document.querySelector('#earn .earn,#earn-live .earn')};
earnPlace();setInterval(earnPlace,300000)</script>"""


# 자동 실적 속보: kb-market-report earnings-watch 워크플로가 10분마다 갱신하는 earnings-live/earnings.json
# (★ 실적·주요 반도체 실적 발표 감지 → 컨센서스 + 기사 제목). 수동 정리 카드(earnings_flash)가 있으면 그 회사는 뺀다.
# 두 곳을 합쳐 보여 준다: kb-market-report 실적 감시(노트북) + market-dashboard earnings-quick(시간외 감시가 SEC 실적 공시로 5분마다)
EARN_LIVE_SRC = (("https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/earnings.json?ref=earnings-live",
                  "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json"),
                 ("https://api.github.com/repos/Sunbong-oh/market-dashboard/contents/earnings.json?ref=earnings-quick",
                  "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/earnings-quick/earnings.json"))
EARN_LIVE_JS = r"""<script>
(function(){var SRC=%s,box=document.getElementById('earn-live');if(!box)return;
 function rp(u){var m=/\/surge-reports\/reports\/(\d{4}-\d{2}-\d{2}\/\w+)\.pdf/.exec(u||'');return m?'reports/view.html?f='+m[1]:u}
 function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 function pc(v){return v==null?'':'<b class="'+(v>0?'up':v<0?'down':'')+'">'+(v>0?'+':'')+Number(v).toFixed(2)+'%%</b>'}
 function px(i){if(!(i.px||[]).length)return '';return '<div class="px"><div class="pxh">📈 실적 발표 후 주가 반응</div>'+i.px.map(function(r){
   return '<div class="pxr"><span class="pl">'+e(r.l)+'</span> <span class="ps">'+e(r.s)+' '+e(r.t||'')+'</span> <b>'+e(r.p)+'</b> '+
    (r.c!=null?'<span class="pr">'+e(r.ref)+' 대비</span> '+pc(r.c):'')+(r.d1!=null?' <span class="pr">· 첫 정규장</span> '+pc(r.d1):'')+'</div>'}).join('')+'</div>'}
 function draw(j){var now=Date.now(),manual={},mname={};document.querySelectorAll('.earn[data-key]').forEach(function(c){manual[c.dataset.key]=c;
   mname[c.dataset.key.split('-').slice(1).join('-')]=c});  /* 키 날짜 기준이 달라도(미국 날짜·한국 날짜) 회사 이름으로 같은 카드 */
  (j&&j.items||[]).forEach(function(i){var c=manual[i.key]||mname[i.name];if(!c)return;var o=c.querySelector('.px');if(o)o.remove();
   var h=px(i);if(h){var t=c.querySelector('table');(t||c.querySelector('.vd')).insertAdjacentHTML('afterend',h)}});  /* 수동 카드에는 주가 반응만 */
  var ts=function(i){return i.first_iso||(i.detected.replace(' ','T')+':00+09:00')};
  var its=(j&&j.items||[]).filter(function(i){return (window.earnKeep?earnKeep(ts(i)):now-Date.parse(ts(i))<864e5)&&!manual[i.key]&&!mname[i.name]})
   .sort(function(a,b){return Date.parse(ts(b))-Date.parse(ts(a))});  /* 두 곳(국내·미국 감시)을 합친 뒤 최근 발표가 위로 */
  document.querySelectorAll('#earn .earn.auto,#earn-old .earn.auto').forEach(function(c){c.remove()});  /* 다시 그리기 전에 옮겨 둔 자동 카드 정리 */
  box.innerHTML=its.map(function(i){return '<div class="earn auto" data-ts="'+e(ts(i))+'"><h2>'+e(i.icon||'⚡')+' '+e(i.head||'실적 발표')+' · '+e(i.name)+'<small>'+e(i.first)+' 감지 · 자동</small></h2>'+
   (i.item&&i.item!==i.name?'<div class="cal">'+e(i.note||'캘린더')+': '+e(i.item)+'</div>':'')+
   (i.cons||[]).map(function(c){return '<div class="cons">▶ '+e(c)+'</div>'}).join('')+
   (i.report?'<div class="rptw"><a class="rpt" href="'+e(rp(i.report))+'" target="_blank" rel="noopener">📑 실시간 작성된 종목 보고서</a><span class="rpt-tap">&lt;-- 터치!!</span></div>':'')+px(i)+
   '<ul>'+(i.news||[]).map(function(a){return '<li><a href="'+e(a.u)+'" target="_blank" rel="noopener">'+e(a.t)+'</a> <span>'+e(a.o)+' '+e(a.dt)+'</span></li>'}).join('')+'</ul></div>'}).join('');
  if(window.earnPlace)earnPlace();else box.hidden=!its.length}
 function get(g,i,cb){if(i>=g.length)return cb(null);
  fetch(i?g[i]+'?t='+Date.now():g[i],{headers:i?{}:{Accept:'application/vnd.github.raw'},cache:'no-store'})
  .then(function(r){if(!r.ok)throw 0;return r.json()}).then(cb).catch(function(){get(g,i+1,cb)})}
 function load(){var n=SRC.length,out=[],seen={};
  SRC.forEach(function(g){get(g,0,function(j){(j&&j.items||[]).forEach(function(i){if(!seen[i.key]){seen[i.key]=1;out.push(i)}});
   if(--n===0)draw({items:out})})})}
 load();setInterval(function(){if(!document.hidden)load()},300000);
})();
</script>""" % json.dumps([list(g) for g in EARN_LIVE_SRC])


def earn_px_html(item):
    """실적 발표 후 주가 반응 [{l,s,t,p,c,ref,d1}] (earnings_px.py · kb-market-report 실적 감시가 쓰는 형식)."""
    rows = (item or {}).get("px") or []
    if not rows:
        return ""

    def pc(v):
        if v is None:
            return ""
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<b class="{cls}">{v:+.2f}%</b>'
    e = escape
    out = "".join(f'<div class="pxr"><span class="pl">{e(r.get("l", ""))}</span> <span class="ps">{e(r.get("s", ""))} {e(r.get("t") or "")}</span> '
                  f'<b>{e(r.get("p", ""))}</b> '
                  + (f'<span class="pr">{e(r.get("ref", ""))} 대비</span> {pc(r.get("c"))}' if r.get("c") is not None else "")
                  + (f' <span class="pr">· 첫 정규장</span> {pc(r.get("d1"))}' if r.get("d1") is not None else "") + "</div>"
                  for r in rows)
    return f'<div class="px"><div class="pxh">📈 실적 발표 후 주가 반응</div>{out}</div>'


def earn_card(e, key):
    """실적 속보 카드 한 장 (홈페이지와 텔레그램 이미지 earnings_notify.py 가 같이 쓴다)."""
    rows = "".join(f'<tr><td>{escape(r[0])}</td><td class="v">{escape(r[1])}</td><td class="c">'
                   f'{f"<b class=j>{escape(r[3])}</b><br>" if r[3] else ""}{escape(r[2])}</td></tr>' for r in e.get("rows") or [])
    guide = "".join(f"<li>{escape(g)}</li>" for g in e.get("guidance") or [])
    src = " · ".join(f'<a href="{escape(u)}" target="_blank" rel="noopener">{escape(t)}</a>' for t, u in e.get("sources") or [])
    ts = f'{e["day"]}T{e.get("time") or "00:00"}:00+09:00'
    return (f'<div class="earn" data-day="{escape(e["day"])}" data-ts="{escape(ts)}" data-key="{escape(key)}"><h2>📊 실적 속보 · {escape(e["company"])}'
            f'<small>{escape(e["period"])} · {escape(e["day"][5:].replace("-", "/"))} {escape(e.get("time", ""))} 발표</small></h2>'
            f'<div class="vd">{escape(e.get("verdict", ""))}</div><table>{rows}</table>{earn_px_html(e)}'
            + (f"<h3>향후 가이던스</h3><ul>{guide}</ul>" if guide else "")
            + (f'<div class="src">출처: {src}</div>' if src else "") + "</div>")


def earnings_home(now):
    cards = []
    for f in sorted((ROOT / "earnings_flash").glob("*.json"), reverse=True):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (now.date() - datetime.strptime(e["day"], "%Y-%m-%d").date()).days > 1:
            continue
        cards.append(earn_card(e, f.stem))
    live = f'<section class="sec" id="earn-live" hidden></section>'
    head = '<div class="sec-h" id="earn-h" hidden><h2>📊 오늘의 실적속보<small>발표 시각 순 · 최신이 위</small></h2></div>'
    if not cards:
        return f'<style>{EARN_CSS}</style>{head}{live}'
    return f'<style>{EARN_CSS}</style>{head}<section class="sec" id="earn">{"".join(cards)}</section>{live}'


# 음성 브리핑(팟캐스트) 구독 주소: 고객이 주소를 복사해 팟캐스트 앱에 'URL로 추가'하거나, 바로 최신 회차를 듣는다
PODCASTS = (
    ("출근길 미국증시 브리핑", "평일 아침 7시", "https://sunbong-oh.github.io/market-dashboard/podcast/feed.xml"),
    ("퇴근길 장마감 브리핑", "평일 오후 4시", "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/podcast/feed.xml"),
)
POD_CSS = """
.pod{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 16px}
.pod h2{margin:0 0 8px;font-size:17px}.pod h2 small{font-size:12.5px;font-weight:400;color:var(--muted);margin-left:6px}
.pod-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:8px 0;border-top:1px solid var(--line)}
.pod-row:first-of-type{border-top:0}
.pod-name{font-weight:800;min-width:150px}.pod-name small{display:block;font-weight:400;font-size:12.5px;color:var(--muted)}
.pod-url{flex:1 1 260px;min-width:0;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);
  font:12.5px/1.3 ui-monospace,Menlo,Consolas,monospace}
.pod button{padding:7px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text);font-weight:700;cursor:pointer}
.pod button.copy{background:var(--accent);border-color:var(--accent);color:#fff}
.pod audio{width:100%;margin-top:6px}.pod .help{font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.5}
"""
POD_JS = """<script>
document.querySelectorAll('.pod .copy').forEach(b => b.addEventListener('click', async () => {
  const inp = b.parentElement.querySelector('.pod-url');
  try { await navigator.clipboard.writeText(inp.value); } catch (e) { inp.select(); document.execCommand('copy'); }
  const t = b.textContent; b.textContent = '복사됨 ✓'; setTimeout(() => b.textContent = t, 1500);
}));
document.querySelectorAll('.pod .play').forEach(b => b.addEventListener('click', async () => {
  const row = b.parentElement, url = row.querySelector('.pod-url').value;
  let au = row.querySelector('audio');
  if (au) { au.paused ? au.play() : au.pause(); return; }
  b.textContent = '불러오는 중…';
  try {  // 피드의 첫 회차(최신) MP3를 바로 재생
    const xml = new DOMParser().parseFromString(await (await fetch(url + '?t=' + Date.now())).text(), 'text/xml');
    const item = xml.querySelector('item');
    au = document.createElement('audio'); au.controls = true; au.src = item.querySelector('enclosure').getAttribute('url');
    row.appendChild(au); au.play().catch(() => {});
    b.textContent = '▶ ' + item.querySelector('title').textContent;
  } catch (e) { b.textContent = '아직 회차가 없습니다'; }
}));
</script>"""


def podcast_home():
    rows = "".join(
        f'<div class="pod-row"><div class="pod-name">🎧 {escape(name)}<small>{escape(when)} 업데이트</small></div>'
        f'<input class="pod-url" readonly value="{escape(url)}" aria-label="{escape(name)} RSS 주소" onfocus="this.select()">'
        f'<button class="copy" type="button">주소 복사</button><button class="play" type="button">▶ 최신 회차 듣기</button></div>'
        for name, when, url in PODCASTS)
    return (f'<style>{POD_CSS}</style><section class="sec pod" id="podcast"><h2>🎧 음성 브리핑<small>운전·출퇴근길에 들어 보세요</small></h2>'
            f'{rows}<div class="help">구독: 주소를 복사해 팟캐스트 앱에 붙여 넣으세요. '
            f'안드로이드 <b>AntennaPod·Podcast Addict</b>: ＋ → URL로 추가 · 아이폰 <b>Apple 팟캐스트</b>: 보관함 → ⋯ → URL로 쇼 팔로우. '
            f'구독해 두면 새 회차가 자동으로 내려받아져 안드로이드 오토·카플레이에서 바로 재생됩니다.</div></section>{POD_JS}')


def build_home(now, daily, close, live=None, target=None, us=None, strong=None, kospi_hist=None):
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
    body = (f'<style>{HOME_CSS}{ISSUE_CSS}{VCNT_CSS}</style>{CLOSE_FIRST_JS}<div class="home">'
            f'<div id="vcnt" hidden></div>'
            f'{strong_home(strong)}'
            f'{ad_strip()}'
            f'{podcast_home()}'
            f'<section class="sec" id="issue" hidden></section>'
            f'{earnings_home(now)}'
            f'<section class="sec" id="daily">{s1}</section>'
            f'{target_home(target)}{us_home(us)}{STRONG_LOW_JS if strong else ""}'
            f'<section class="sec" id="close"><div class="sec-h"><h2>📊 장마감 수급</h2>{more3}</div>{s3}</section>'
            f'{play_page.home_section(kospi_hist or [], VISIT_API, VISIT_NS)}{quiz_home(news_quiz(now, target, strong))}{tools_home()}</div>'
            f'{ad_home()}{FIT_JS}{LIVE_HOME_JS}{ISSUE_JS}{EARN_JS}{EARN_LIVE_JS}{VCNT_JS}')
    (OUT / "index.html").write_text(page(SITE_NAME, body, "", "", hero=False),
                                    encoding="utf-8")


# ---------- Brian's memo (생각거리) ----------
# 종목 리포트가 아닌 시장 점검·생각거리 글. memo/ 에 리포트 HTML(+ 내려받을 PDF·PPT)을 넣고 memo/index.json 에 한 줄 추가하면
# /memo/ 목록(최신순)과 글 페이지가 생긴다. index.json 항목: date, title, sub, headline, tags, file, downloads[[이름, 파일]]
MEMO_CSS = STRONG_CSS + """
.st .dl{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}.st .dl a{font-size:12.5px;font-weight:800;padding:4px 10px;border-radius:8px;
  border:1px solid #F2A900;color:var(--fg,#3D3A35);text-decoration:none;background:transparent}
"""


MEMO_PAGE_CSS = ("<style>body{margin:0!important;padding:0 0 24px!important}body>section.page:first-of-type{margin-top:24px}"
                 "@media(max-width:952px){body>section.page{margin-left:16px;margin-right:16px}}</style>")


def memo_items():
    try:
        items = json.loads((MEMO / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = [x for x in items if DATE_RE.match(x.get("date", "")) and x.get("file") and (MEMO / x["file"]).is_file()]
    return sorted(items, key=lambda x: x["date"], reverse=True)


def memo_card(it, prefix=""):
    tags = "".join(f"<span>{escape(t)}</span>" for t in it.get("tags", []))
    dls = "".join(f'<a href="{escape(prefix + f)}" download>⬇ {escape(n)}</a>' for n, f in it.get("downloads", []) if (MEMO / f).is_file())
    return (f'<div class="st"><a href="{escape(prefix + it["file"])}" style="text-decoration:none;color:inherit;display:block">'
            f'<div class="nm">{escape(it["title"])}<small>{escape(it.get("sub", ""))}</small>'
            '<span class="go"><b>📝 메모 읽기</b><i>&lt;-- 터치!!</i></span></div>'
            f'<div class="hl">{escape(it.get("headline", ""))}</div>'
            + (f'<div class="tg">{tags}</div>' if tags else "") + '</a>'
            + (f'<div class="dl">{dls}</div>' if dls else "") + '</div>')


def build_memo():
    out = OUT / "memo"
    out.mkdir(parents=True, exist_ok=True)
    items = memo_items()
    rows, last = [], ""
    for it in items:
        if it["date"] != last:
            last = it["date"]
            rows.append(f'<div class="st-day">{label(last)}</div>')
        rows.append(memo_card(it))
        src = (MEMO / it["file"]).read_text(encoding="utf-8")
        # 리포트 본문의 바깥 여백 때문에 메뉴가 좁아지지 않게: 여백은 지면(.page)에 준다
        src = re.sub(r"</head>", lambda _: MEMO_PAGE_CSS + "</head>", src, count=1, flags=re.I)
        src = re.sub(r"</body>", lambda _: STRONG_FIX + "</body>", src, count=1, flags=re.I) if re.search(r"</body>", src, re.I) else src + STRONG_FIX
        bar = ('<div style="' + SUB_STYLE + '"><a href="./" style="' + SUB_LINK + '">← 메모 목록</a>'
               '<a href="./" class="st-close-bar" style="margin-left:auto;background:#F2A900;color:#3D3A35;font-weight:900;text-decoration:none;padding:5px 14px;border-radius:16px" '
               'onclick="event.preventDefault();if(history.length>1){history.back()}else{window.close();setTimeout(function(){location.href=\'./\'},200)}">✕ 닫기</a></div>')
        (out / it["file"]).write_text(with_nav(src, "../", "memo/", extra=bar), encoding="utf-8")
        for _, f in it.get("downloads", []):
            if (MEMO / f).is_file():
                shutil.copy(MEMO / f, out / f)
    body = (f'<style>{MEMO_CSS}</style>'
            + ("".join(rows) or '<p class="err">아직 올린 메모가 없습니다.</p>')
            + '<div class="st-note">Brian의 생각거리: 시장 흐름을 자산·수급·지표로 점검한 메모입니다. 숫자의 출처와 기준 시각은 각 글에 적혀 있습니다. '
              '매수·매도 추천이 아닌 판단 근거 정리이며, 투자 판단의 참고 자료입니다.</div>')
    (out / "index.html").write_text(page("📝 Brian's memo", body, "../", "memo/", "BRIAN'S MEMO", "생각거리 · 최신순"), encoding="utf-8")
    return items


def main():
    now = datetime.now(d.KST)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / ".nojekyll").write_text("")
    write_app_files()
    daily = build_daily()
    close = build_close()
    target = build_target()
    us = build_us()
    strong = build_strong()
    build_memo()
    live = build_live(now)
    build_visits(now)
    build_map()
    build_reports()
    study = study_page.build(OUT, page)
    play_page.build(OUT, page, now, VISIT_API, VISIT_NS)
    play_page.build_lab(OUT, page)
    build_home(now, daily, close, live, target, us, strong, play_page.kospi_history())
    print(json.dumps({"out": str(OUT), "daily": daily and daily["day"], "close": close and close["day"], "target": target and target["day"],
                      "us": us and us["day"], "study": study,
                      "live": bool(live)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
