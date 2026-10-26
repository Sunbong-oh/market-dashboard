"""놀이터: 홈 '코스피 오를까 내릴까?' 투표 + /play/ 게임 9가지(60초 챌린지 · 시가총액 대결 · 오늘 더 오른 종목 · 차트 보고 맞히기 ·
차트 다음은? · 업종 맞히기 · 주가 맞히기 · 1년 수익률 대결 · 실적 대결) + 등급·오늘의 미션(그 기기에만 저장).

- 투표: 다음 거래일 코스피가 직전 종가보다 오를지 내릴지. 그날 09:00 에 마감하고, 결과는 야후 ^KS11 일봉 종가로
  보는 사람 브라우저가 채점한다(사이트를 만들 때 최근 두 달 종가를 넣어 둔다). 다른 사람 투표 수는 Abacus 카운터
  (방문자 집계와 같은 곳)에 vote-YYYYMMDD-u / -d 로 센다. 내 기록(적중률·연속 적중)은 그 기기에만 남는다.
- 게임: kb-market-report flow-live/map.json(네이버 증권 업종별 종목: 시가총액 v 억원, 등락률 p)을 사이트를 만들 때 넣는다.
  ETF·ETN·스팩·우선주는 뺀다. 최고 기록은 그 기기에만 남고, 판 수는 c-game 으로 센다.
"""
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
KOSPI_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?range=3mo&interval=1d"
MAP_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/map.json"
ETF = re.compile(r"^(KODEX|TIGER|RISE|ACE|SOL|KIWOOM|HANARO|ARIRANG|PLUS|KOSEF|TIMEFOLIO|KBSTAR|WON|BNK|1Q|마이티|에셋플러스|TRUSTON|UNICORN|파워)\b"
                 r"|ETN|레버리지|인버스|스팩")


def _get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print("놀이터 자료 실패:", url[:60], type(e).__name__, e)
        return None


def kospi_history():
    """[{d: 'YYYY-MM-DD', c: 종가, p: 전일 대비 %}] 최근 약 3달 (오래된 것부터)."""
    j = _get(KOSPI_URL)
    try:
        r = j["chart"]["result"][0]
        rows = [(datetime.fromtimestamp(t, KST).strftime("%Y-%m-%d"), c)
                for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
    except (TypeError, KeyError, IndexError):
        return []
    out, prev = [], None
    for dday, c in rows:
        if out and out[-1]["d"] == dday:
            continue
        out.append({"d": dday, "c": round(c, 2), "p": round((c / prev - 1) * 100, 2) if prev else None})
        prev = c
    return out


def stocks():
    """게임용 종목 [{n, m(코스피/코스닥), s(업종), c(시가총액 억원), p(등락률)}] 시가총액 500위까지, 기준일."""
    j = _get(MAP_URL)
    if not j or not j.get("data"):
        return [], ""
    rows = []
    for mk, secs in j["data"].items():
        for sec in secs:
            for st in sec.get("st") or []:
                n = st.get("n") or ""
                if not n or ETF.search(n) or re.search(r"우[A-C]?$|우\(전환\)$", n) or not st.get("v") or st.get("p") is None:
                    continue
                rows.append({"n": n, "m": "코스피" if mk == "kospi" else "코스닥", "s": sec.get("s", ""),
                             "c": round(st["v"]), "p": round(st["p"], 2)})
    rows.sort(key=lambda x: -x["c"])
    day = str(j.get("date") or "")
    return rows[:500], (f"{day[:4]}-{day[4:6]}-{day[6:8]} {j.get('time', '')}".strip() if len(day) == 8 else "")


PD_CSS = """.home>#predict{order:97}
#predict .pd{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
#predict .pq{font-size:16.5px;font-weight:800;line-height:1.5;word-break:keep-all}
#predict .pm{font-size:12.5px;color:var(--muted);margin-top:2px}
#predict .pb{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
#predict .pb button{font:800 16px/1.3 inherit;padding:12px 8px;border-radius:12px;border:2px solid var(--line);background:var(--bg);color:var(--text);cursor:pointer}
#predict .pb button.u{border-color:#e03131}#predict .pb button.d{border-color:#1c6dd0}
#predict .pb button.on.u{background:#e03131;color:#fff}#predict .pb button.on.d{background:#1c6dd0;color:#fff}
#predict .pb button:disabled{cursor:default;opacity:.55}#predict .pb button.on:disabled{opacity:1}
#predict .pr{margin-top:12px;font-size:13px}
#predict .bar{display:flex;height:12px;border-radius:7px;overflow:hidden;background:var(--line);margin:6px 0 4px}
#predict .bar i{display:block;background:#e03131}#predict .bar b{display:block;background:#1c6dd0;flex:1}
#predict .bar-l{display:flex;justify-content:space-between;font-size:12.5px;font-weight:700}
#predict .bar-l .u{color:#e03131}#predict .bar-l .d{color:#1c6dd0}
#predict .rec{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);font-size:13.5px;line-height:1.7}
#predict .rec b.ok{color:#2f9e44}#predict .rec b.no{color:#e03131}
#predict .gos{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
#predict .go{display:block;text-align:center;font-weight:800;padding:10px;border-radius:12px;background:#FBE7B0;color:#3D3A35;text-decoration:none}"""

PD_JS = r"""(function(){var box=document.getElementById('pdb');if(!box)return;
var WD='일월화수목금토',now=new Date(Date.now()+9*36e5),iso=function(d){return d.toISOString().slice(0,10)};
function md(s){var d=new Date(s+'T00:00:00Z');return (d.getUTCMonth()+1)+'/'+d.getUTCDate()+'('+WD[d.getUTCDay()]+')'}
function nextSession(){var d=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate()));
 var wd=d.getUTCDay(),before9=now.getUTCHours()<9;if(!(wd>=1&&wd<=5&&before9))d=new Date(d.getTime()+864e5);
 while(d.getUTCDay()===0||d.getUTCDay()===6)d=new Date(d.getTime()+864e5);return iso(d)}
var S=nextSession(),base=null;H.forEach(function(h){if(h.d<S)base=h});
var V={};try{V=JSON.parse(localStorage.getItem('pd-votes')||'{}')}catch(e){}
function save(){try{localStorage.setItem('pd-votes',JSON.stringify(V))}catch(e){}}
var key=function(s,u){return 'vote-'+s.replace(/-/g,'')+'-'+u};
function get(k){return fetch(PAPI+'/get/'+PNS+'/'+k,{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){return j&&j.value||0}).catch(function(){return 0})}
function result(s){var i=-1;H.forEach(function(h,j){if(h.d===s)i=j});if(i>0)return H[i].p;
 var later=H.some(function(h){return h.d>s});return later?'void':null}
function record(){var n=0,ok=0,streak=0,lines=[];Object.keys(V).sort().forEach(function(s){var r=result(s);if(r==null||r==='void'||r===0)return;
  var hitOk=(V[s]==='u')===(r>0);n++;if(hitOk){ok++;streak++}else streak=0;lines.push([s,V[s],r,hitOk])});
 return{n:n,ok:ok,streak:streak,last:lines.slice(-3).reverse()}}
var pending=false;
function render(){var my=V[S],r=record();
 var q='<div class="pq">'+md(S)+' 코스피, '+(base?md(base.d)+' 종가 '+base.c.toLocaleString('ko-KR',{minimumFractionDigits:2})+'보다':'직전 종가보다')+' 오를까요?</div>'+
  '<div class="pm">'+md(S)+' 09:00 마감 · 그날 장이 끝나면 자동으로 채점돼요</div>'+
  '<div class="pb"><button type="button" class="u'+(my==='u'?' on':'')+'" data-v="u"'+(my?' disabled':'')+'>📈 오른다</button>'+
  '<button type="button" class="d'+(my==='d'?' on':'')+'" data-v="d"'+(my?' disabled':'')+'>📉 내린다</button></div><div class="pr" id="pdr"></div>';
 var rec='';if(r.n){rec='<div class="rec">내 기록 <b>'+r.n+'번 중 '+r.ok+'번 적중</b> ('+Math.round(r.ok/r.n*100)+'%)'+(r.streak>1?' · 🔥 '+r.streak+'연속 적중':'')+
  r.last.map(function(x){return '<br>'+md(x[0])+' '+(x[1]==='u'?'상승':'하락')+' 예측 → 코스피 '+(x[2]>0?'+':'')+x[2].toFixed(2)+'% '+(x[3]?'<b class="ok">적중</b>':'<b class="no">빗나감</b>')}).join('')+'</div>'}
 box.innerHTML=q+rec+'<div class="gos"><a class="go" href="play/#rush">⏱ 60초 챌린지 도전 ›</a><a class="go" href="play/">🎮 놀이터 게임 9가지 ›</a></div>';
 if(my&&!pending)counts()}
function counts(){var el=document.getElementById('pdr');el.textContent='다른 사람들은…';
 Promise.all([get(key(S,'u')),get(key(S,'d'))]).then(function(c){var u=c[0],d=c[1],t=u+d;if(!t){el.innerHTML='첫 번째로 투표했어요!';return}
  var pu=Math.round(u/t*100);el.innerHTML='<div class="bar-l"><span class="u">📈 오른다 '+pu+'%</span><span class="d">'+(100-pu)+'% 내린다 📉</span></div>'+
  '<div class="bar"><i style="width:'+pu+'%"></i><b></b></div><div style="color:var(--muted)">'+t+'명 참여</div>'})}
box.addEventListener('click',function(e){var b=e.target.closest('button[data-v]');if(!b||V[S])return;V[S]=b.dataset.v;save();pending=true;render();
 document.getElementById('pdr').textContent='집계 중…';
 var done=function(){pending=false;counts()};
 try{fetch(PAPI+'/hit/'+PNS+'/'+key(S,b.dataset.v),{cache:'no-store'}).then(done,done)}catch(e){done()}});
render()})();"""


def home_section(history, api, ns):
    if not history:
        return ""
    data = (f"var H={json.dumps(history[-60:], ensure_ascii=False)},PAPI={json.dumps(api)},PNS={json.dumps(ns)};").replace("</", "<\\/")
    return (f'<section class="sec" id="predict"><style>{PD_CSS}</style>'
            '<div class="sec-h"><h2>🎯 코스피 오를까 내릴까?</h2><a href="play/">놀이터 ›</a></div>'
            f'<div class="pd" id="pdb"><p class="err">불러오는 중…</p></div><script>{data}\n{PD_JS}</script></section>')


GAME_CSS = """.gm-tabs{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:6px;margin:0 0 12px}
.gm-tabs button.hot{border:2px solid #F2A900}.gm-tabs button.hot.on{background:#F2A900;color:#3D3A35;border-color:#F2A900}
.gm-lv{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0 0 12px;font-size:13.5px}
.gm-lv .lh{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}.gm-lv .lh b{font-size:18px}
.gm-lv .lh span{color:var(--muted);font-size:12.5px}
.gm-lv .bar{height:10px;border-radius:6px;background:var(--line);overflow:hidden;margin:7px 0 9px}.gm-lv .bar i{display:block;height:100%;background:#F2A900}
.gm-lv .ms{display:flex;flex-wrap:wrap;gap:6px}.gm-lv .ms span{padding:4px 9px;border-radius:999px;border:1px solid var(--line);font-size:12.5px;font-weight:700}
.gm-lv .ms span.ok{background:#FBE7B0;color:#3D3A35;border-color:#F2A900}
.gm-top .tm{font-size:18px;color:#e03131}
.cg-opts .os{display:block;font-size:12px;font-weight:600;color:var(--muted);margin-top:2px}
.gm-start{text-align:center;padding:10px 4px;line-height:1.7;font-size:14.5px;word-break:keep-all}
.gm-start button{margin-top:10px;font:900 17px/1 inherit;padding:14px 28px;border-radius:12px;border:0;background:#F2A900;color:#3D3A35;cursor:pointer}
.gm-tabs button{font:800 14px/1.25 inherit;padding:10px 6px;word-break:keep-all;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
.gm-tabs button.on{background:#3D3A35;color:#fff;border-color:#3D3A35}
.gm{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
.gm-top{display:flex;justify-content:space-between;align-items:center;font-size:14px;font-weight:800;margin-bottom:10px}
.gm-top .sc{font-size:22px}.gm-top .best{color:var(--muted);font-weight:700}
.gm-q{font-size:16px;font-weight:800;text-align:center;margin:4px 0 12px;word-break:keep-all}
.gm-row{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:stretch}
.gm-vs{align-self:center;font-weight:900;color:var(--muted)}
.gm-card{border:2px solid var(--line);border-radius:14px;padding:14px 10px;text-align:center;background:var(--bg);display:flex;flex-direction:column;gap:4px;justify-content:center;min-height:150px}
button.gm-card{font:inherit;color:inherit;cursor:pointer}button.gm-card:hover:enabled{border-color:#F2A900}
.gm-card .n{font-size:18px;font-weight:900;word-break:keep-all}.gm-card .s{font-size:12px;color:var(--muted)}
.gm-card .v{font-size:20px;font-weight:900;margin-top:4px;font-variant-numeric:tabular-nums}.gm-card .v.hid{color:var(--muted)}
.gm-card.ok{border-color:#2f9e44;background:#e6f6ec}.gm-card.no{border-color:#e03131;background:#fdecec}
.gm-btns{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.gm-btns button{font:800 15.5px/1.3 inherit;padding:12px 6px;border-radius:12px;border:2px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
.gm-btns button:hover{border-color:#F2A900}
.gm-msg{margin-top:12px;text-align:center;font-size:14.5px;font-weight:700;min-height:22px;word-break:keep-all}
.gm-over{margin-top:12px;text-align:center;padding:14px;border-radius:14px;background:#FBE7B0;color:#3D3A35}
.gm-over b{font-size:20px}.gm-over button{margin-top:10px;font:800 15px/1 inherit;padding:11px 20px;border-radius:10px;border:0;background:#F2A900;color:#3D3A35;cursor:pointer}
.up{color:var(--up)}.down{color:var(--down)}
.gm-note{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:14px}
.cg-tag{display:inline-block;font-size:12px;font-weight:800;padding:2px 9px;border-radius:999px;background:#FBE7B0;color:#3D3A35}
.cg-svg{display:block;width:100%;height:170px;margin:8px 0 6px;background:var(--bg);border-radius:12px}
.cg-info{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13.5px;justify-content:center}.cg-info b{font-size:16px}
.cg-opts{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.cg-opts button{font:800 15px/1.3 inherit;padding:12px 6px;border-radius:12px;border:2px solid var(--line);background:var(--card);color:var(--text);cursor:pointer;word-break:keep-all}
.cg-opts button.ok{border-color:#2f9e44;background:#e6f6ec}.cg-opts button.no{border-color:#e03131;background:#fdecec}
.cg-ex{margin-top:10px;font-size:13.5px;line-height:1.6;padding:10px 12px;border-left:4px solid #F2A900;background:var(--bg);border-radius:0 10px 10px 0;word-break:keep-all}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .gm-card.ok{background:#16301f}:root:not([data-theme=light]) .gm-card.no{background:#3a1c1c}}
:root[data-theme=dark] .gm-card.ok{background:#16301f}:root[data-theme=dark] .gm-card.no{background:#3a1c1c}"""

GAME_JS = r"""(function(){var box=document.getElementById('gm'),mode='cap',A,B,score=0,busy=false,started=false;
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function won(v){return v>=10000?(v/10000).toLocaleString('ko-KR',{maximumFractionDigits:v>=100000?0:1})+'조':Math.round(v).toLocaleString('ko-KR')+'억'}
function pct(p){return '<span class="'+(p>0?'up':p<0?'down':'')+'">'+(p>0?'+':'')+p.toFixed(2)+'%</span>'}
function best(){try{return +localStorage.getItem('gm-best-'+mode)||0}catch(e){return 0}}
function setBest(v){try{localStorage.setItem('gm-best-'+mode,v)}catch(e){}}
function pick(){return S[Math.floor(Math.random()*S.length)]}
function pair(a){for(var k=0;k<200;k++){var b=pick();if(b.n===a.n)continue;
  if(mode==='cap'){var r=b.c/a.c;if(r>0.2&&r<5&&Math.abs(r-1)>0.03)return b}else if(Math.abs(b.p-a.p)>=0.3)return b}return pick()}
function count(){if(started)return;started=true;try{if(localStorage.getItem('brian-admin')==='1')return;var d=new Date(Date.now()+9*36e5).toISOString().slice(0,10).replace(/-/g,'');
 ['c-game-'+d,'t-c-game'].forEach(function(k){fetch(PAPI+'/hit/'+PNS+'/'+k,{cache:'no-store'}).catch(function(){})})}catch(e){}}
function card(x,show,tag,cls){var v=mode==='cap'?(show?won(x.c):'?'):(show?pct(x.p):'?');
 return '<'+tag+' class="gm-card'+(cls?' '+cls:'')+'"'+(tag==='button'?' type="button" data-n="'+esc(x.n)+'"':'')+'><span class="n">'+esc(x.n)+'</span><span class="s">'+esc(x.m)+' · '+esc(x.s)+'</span><span class="v'+(show?'':' hid')+'">'+v+'</span></'+tag+'>'}
function top(){return '<div class="gm-top"><span>점수 <span class="sc">'+score+'</span></span><span class="best">최고 '+best()+'</span></div>'}
function draw(msg){busy=false;
 if(mode==='cap'){box.innerHTML=top()+'<div class="gm-q">오른쪽 회사 시가총액은 왼쪽보다 클까요, 작을까요?</div>'+
  '<div class="gm-row">'+card(A,true,'div')+'<span class="gm-vs">VS</span>'+card(B,false,'div')+'</div>'+
  '<div class="gm-btns"><button type="button" data-g="hi">⬆ 더 크다</button><button type="button" data-g="lo">⬇ 더 작다</button></div><div class="gm-msg">'+(msg||'')+'</div>'}
 else{box.innerHTML=top()+'<div class="gm-q">'+DAY+' 하루 동안 더 많이 오른(덜 내린) 종목은?</div>'+
  '<div class="gm-row">'+card(A,false,'button')+'<span class="gm-vs">VS</span>'+card(B,false,'button')+'</div><div class="gm-msg">'+(msg||'')+'</div>'}}
function over(msg){var b=best();if(score>b)setBest(score);
 box.insertAdjacentHTML('beforeend','<div class="gm-over">'+msg+'<br>이번 판 <b>'+score+'점</b>'+(score>b?' · 🎉 최고 기록!':' · 최고 '+Math.max(b,score)+'점')+'<br><button type="button" data-g="again">다시 하기</button></div>')}
var CQ=[],cq=null;
function cqueue(){var pat=CP.filter(function(x){return x.pat!=='차트'}),gen=CP.filter(function(x){return x.pat==='차트'});
 function sh(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
 pat=sh(pat);gen=sh(gen);var q=[];while(pat.length||gen.length){if(pat.length)q.push(pat.shift());if(gen.length)q.push(gen.shift())}return q}
function svg(p){var w=300,h=120,n=p.pts.length,xs=function(i){return (i/(n-1)*w).toFixed(1)},ys=function(v){return (h-6-v/100*(h-12)).toFixed(1)};
 var line=p.pts.map(function(v,i){return xs(i)+','+ys(v)}).join(' '),col=p.ch>=0?'#e03131':'#1c6dd0';
 return '<svg class="cg-svg" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><polygon points="0,'+h+' '+line+' '+w+','+h+'" fill="'+col+'" opacity=".12"/>'+
  '<polyline points="'+line+'" fill="none" stroke="'+col+'" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>'}
function opts(p){var near=S.filter(function(x){return x.n!==p.n&&x.c>p.c*0.33&&x.c<p.c*3}),o=[p.n];
 while(o.length<4&&near.length){var k=Math.floor(Math.random()*near.length),x=near.splice(k,1)[0];if(o.indexOf(x.n)<0)o.push(x.n)}
 while(o.length<4){var r=pick();if(o.indexOf(r.n)<0)o.push(r.n)}
 for(var i=o.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=o[i];o[i]=o[j];o[j]=t}return o}
function dlab(d){return d.slice(2,4)+'.'+d.slice(4,6)+'.'+d.slice(6,8)}
function drawChart(msg){busy=false;if(!CQ.length)CQ=cqueue();cq=CQ.shift();var p=cq,o=opts(p);cq.o=o;
 box.innerHTML=top()+'<div class="gm-q">이 차트와 가격은 어느 회사일까요? '+(p.pat!=='차트'?'<span class="cg-tag">'+esc(p.pat)+(p.pat==='u자형'?' · 오른쪽 덜 오름':'')+'</span>':'')+'</div>'+svg(p)+
  '<div class="cg-info"><span>현재가 <b>'+p.price.toLocaleString('ko-KR')+'원</b></span><span>1년 '+pct(p.ch)+'</span>'+
  '<span>52주 '+p.lo.toLocaleString('ko-KR')+' ~ '+p.hi.toLocaleString('ko-KR')+'</span><span style="color:var(--muted)">'+dlab(p.d0)+' ~ '+dlab(p.d1)+' 일봉 종가</span></div>'+
  '<div class="cg-opts">'+o.map(function(n){return '<button type="button" data-o="'+esc(n)+'">'+esc(n)+'</button>'}).join('')+'</div><div class="gm-msg">'+(msg||'')+'</div>'}
var TD=new Date(Date.now()+9*36e5).toISOString().slice(0,10),RUN=60,rushEnd=0,timer=null,cur=null;
function lsj(k,d){try{return JSON.parse(localStorage.getItem(k))||d}catch(e){return d}}
function lss(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
var LV=[[0,'🐣 주린이'],[20,'🐜 개미'],[60,'🐜 똑똑한 개미'],[150,'🦸 슈퍼개미'],[300,'🐳 큰손'],[600,'👑 전설의 투자자']];
function day(){var M=lsj('gm-day',{});if(M.d!==TD)M={d:TD,m:[],st:0,run:0,rush:0};return M}
function lvl(){var el=document.getElementById('gmlv');if(!el)return;var P=lsj('gm-prog',{t:0,a:0}),M=day(),i=0;
 while(i+1<LV.length&&P.t>=LV[i+1][0])i++;var nx=LV[i+1],w=nx?Math.round((P.t-LV[i][0])/(nx[0]-LV[i][0])*100):100;
 var ms=[[M.m.length>=3,'게임 3가지 해 보기 ('+Math.min(M.m.length,3)+'/3)'],[M.st>=5,'5문제 연속 정답 ('+Math.min(M.st,5)+'/5)'],[M.rush>=10,'60초 챌린지 10점 ('+Math.min(M.rush,10)+'/10)']],all=ms.every(function(x){return x[0]});
 el.innerHTML='<div class="lh"><b>'+LV[i][1]+'</b><span>누적 정답 '+P.t+'개'+(nx?' · 다음 「'+nx[1]+'」까지 '+(nx[0]-P.t)+'개':' · 최고 등급!')+'</span></div><div class="bar"><i style="width:'+w+'%"></i></div>'+
  '<div class="ms"><span'+(all?' class="ok"':'')+'>'+(all?'🎉 오늘 미션 완료!':'🎯 오늘의 미션')+'</span>'+ms.map(function(x){return '<span'+(x[0]?' class="ok"':'')+'>'+(x[0]?'✅ ':'⬜ ')+x[1]+'</span>'}).join('')+'</div>'}
function track(ok){var P=lsj('gm-prog',{t:0,a:0});P.a++;if(ok)P.t++;lss('gm-prog',P);var M=day();if(M.m.indexOf(mode)<0)M.m.push(mode);
 M.run=ok?M.run+1:0;if(M.run>M.st)M.st=M.run;if(mode==='rush')M.rush=Math.max(M.rush,score);lss('gm-day',M);lvl()}
function shuf(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
function rnd(a){return a[Math.floor(Math.random()*a.length)]}
function sig(v){var e=Math.pow(10,Math.max(0,Math.floor(Math.log10(v))-2));return Math.round(v/e)*e}
function f1(v){return (Math.abs(v)>=100?Math.round(v):v.toFixed(1)).toLocaleString('ko-KR')}
var XN=S.filter(function(x){return X[x.n]}),PO={};
function pool(k){if(!PO[k])PO[k]=XN.filter(function(x){return X[x.n][k]!=null});return PO[k]}
function lab(x,sub){return esc(x.n)+'<span class="os">'+esc(sub)+'</span>'}
function svgRaw(a,cut,full){var w=300,h=120,n=a.length,v=full?a:a.slice(0,cut+1),lo=Math.min.apply(null,v),hi=Math.max.apply(null,v);if(hi<=lo)hi=lo+1;
 var X_=function(i){return (i/(n-1)*w).toFixed(1)},Y=function(x){return (h-6-(x-lo)/(hi-lo)*(h-12)).toFixed(1)};
 var pl=function(s,e){var r=[];for(var i=s;i<=e;i++)r.push(X_(i)+','+Y(a[i]));return r.join(' ')},cx=X_(cut);
 var o='<svg class="cg-svg" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none">'+(full?'':'<rect x="'+cx+'" y="0" width="'+(w-cx)+'" height="'+h+'" fill="rgba(136,136,136,.22)"/>')+
  '<polyline points="'+pl(0,cut)+'" fill="none" style="stroke:var(--muted)" stroke-width="2" vector-effect="non-scaling-stroke"/>';
 if(full)o+='<polyline points="'+pl(cut,n-1)+'" fill="none" stroke="'+(a[n-1]>=a[cut]?'#e03131':'#1c6dd0')+'" stroke-width="3" vector-effect="non-scaling-stroke"/>';
 return o+'<line x1="'+cx+'" x2="'+cx+'" y1="0" y2="'+h+'" stroke="#F2A900" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"/></svg>'}
var FM=[{k:'opm',q:'영업이익률이 더 높은 회사는?',u:'%',hi:1,note:'영업이익률 = 영업이익 ÷ 매출. 100원어치 팔아 본업으로 남긴 돈입니다.'},
 {k:'g',q:'매출이 작년 같은 기간보다 더 많이 늘어난 회사는?',u:'%',hi:1,note:'매출 증가율 = 올해 누적 매출 ÷ 작년 같은 기간 매출 − 1.'},
 {k:'roe',q:'ROE(자기자본이익률)가 더 높은 회사는?',u:'%',hi:1,note:'ROE = 순이익 ÷ 자기자본(1년 기준으로 환산). 주주 돈 100원으로 번 이익입니다.'},
 {k:'per',q:'PER이 더 낮은(이익에 비해 주가가 싼) 회사는?',u:'배',hi:0,note:'PER = 주가 ÷ 주당순이익. 낮을수록 이익에 비해 싸다는 뜻이지만, 성장성·업종에 따라 적정 수준이 다릅니다.'}];
function two(P,k,gap){var a,b;for(var t=0;t<150;t++){a=rnd(P);b=rnd(P);if(a.n!==b.n&&(!k||gap(a,b)))break}return [a,b]}
var G={
 fut:function(){var p=rnd(FU),n=p.cl.length,ch=(p.cl[n-1]/p.cl[p.cut]-1)*100;
  return {q:'회색 칸(약 2달, 40거래일) 뒤 주가는 어떻게 됐을까요?',body:'<div id="cgs">'+svgRaw(p.cl,p.cut,false)+'</div><div class="cg-info"><span>'+dlab(p.d0)+' ~ '+dlab(p.dc)+' 일봉 종가</span><span>마지막 <b>'+p.cl[p.cut].toLocaleString('ko-KR')+'원</b></span></div>',
   o:['⬆ 올랐다','⬇ 내렸다'],a:ch>0?0:1,ex:'<b>'+esc(p.n)+'</b> · '+esc(p.s)+'<br>'+dlab(p.dc)+' '+p.cl[p.cut].toLocaleString('ko-KR')+'원 → '+dlab(p.d1)+' '+p.cl[n-1].toLocaleString('ko-KR')+'원 ('+pct(ch)+')',
   after:function(){document.getElementById('cgs').innerHTML=svgRaw(p.cl,p.cut,true)}}},
 sec:function(){var x=rnd(S),ss=[];S.forEach(function(y){if(y.s&&y.s!==x.s&&ss.indexOf(y.s)<0)ss.push(y.s)});var o=shuf(shuf(ss).slice(0,3).concat([x.s]));
  return {q:'<b>'+esc(x.n)+'</b>은(는) 어느 업종일까요?',body:'<div class="cg-info"><span>'+esc(x.m)+'</span><span>시가총액 <b>'+won(x.c)+'</b></span></div>',o:o.map(esc),a:o.indexOf(x.s),
   ex:'<b>'+esc(x.n)+'</b> 업종: '+esc(x.s)+' (네이버 증권 업종 분류)'}},
 px:function(){var x=rnd(pool('p')),v=X[x.n].p,o=[sig(v)];shuf([0.3,0.45,0.65,1.5,2.2,3.2]).forEach(function(k){var c=sig(v*k);if(o.length<4&&o.indexOf(c)<0)o.push(c)});
  var r=o[0];o=shuf(o);return {q:'<b>'+esc(x.n)+'</b> 지금 주가는 약 얼마일까요?',body:'<div class="cg-info"><span>'+esc(x.m)+' · '+esc(x.s)+'</span></div>',
   o:o.map(function(c){return '약 '+c.toLocaleString('ko-KR')+'원'}),a:o.indexOf(r),ex:'<b>'+esc(x.n)+'</b> 최근 종가 '+v.toLocaleString('ko-KR')+'원 · 시가총액 '+won(x.c)}},
 r1:function(){var ab=two(pool('r'),1,function(a,b){return Math.abs(X[a.n].r-X[b.n].r)>=5}),a=ab[0],b=ab[1];
  return {q:'최근 1년 동안 주가가 더 많이 오른(덜 내린) 종목은?',o:[lab(a,a.s),lab(b,b.s)],a:X[a.n].r>X[b.n].r?0:1,
   ex:'1년 등락 <b>'+esc(a.n)+'</b> '+pct(X[a.n].r)+' · <b>'+esc(b.n)+'</b> '+pct(X[b.n].r)}},
 fin:function(){var ms=FM.filter(function(m){return pool(m.k).length>=10}),m=rnd(ms),k=m.k;
  var ab=two(pool(k),1,function(a,b){var x=X[a.n][k],y=X[b.n][k];return Math.abs(x-y)>=Math.max(2,Math.abs(x)*0.15,Math.abs(y)*0.15)}),a=ab[0],b=ab[1],va=X[a.n][k],vb=X[b.n][k];
  return {q:m.q,o:[lab(a,a.s),lab(b,b.s)],a:m.hi?(va>vb?0:1):(va<vb?0:1),
   ex:'<b>'+esc(a.n)+'</b> '+f1(va)+m.u+' · <b>'+esc(b.n)+'</b> '+f1(vb)+m.u+'<br>'+m.note+'<br><span style="color:var(--muted)">'+(k==='per'?'KB증권 현재가 기준 PER':'DART 최근 정기보고서(누적) 기준')+'</span>'}},
 cap2:function(){var ab=two(S,1,function(a,b){var r=b.c/a.c;return r>0.25&&r<4&&Math.abs(r-1)>0.05}),a=ab[0],b=ab[1];
  return {q:'시가총액이 더 큰 회사는?',o:[lab(a,a.s),lab(b,b.s)],a:a.c>b.c?0:1,ex:'<b>'+esc(a.n)+'</b> '+won(a.c)+' · <b>'+esc(b.n)+'</b> '+won(b.c)}},
 chg2:function(){var ab=two(S,1,function(a,b){return Math.abs(a.p-b.p)>=0.5}),a=ab[0],b=ab[1];
  return {q:DAY+' 하루 더 많이 오른(덜 내린) 종목은?',o:[lab(a,a.s),lab(b,b.s)],a:a.p>b.p?0:1,ex:'<b>'+esc(a.n)+'</b> '+pct(a.p)+' · <b>'+esc(b.n)+'</b> '+pct(b.p)}},
 chart2:function(){var p=rnd(CP),o=opts(p);return {q:'이 차트와 가격은 어느 회사일까요?',body:svg(p)+'<div class="cg-info"><span>현재가 <b>'+p.price.toLocaleString('ko-KR')+'원</b></span><span>1년 '+pct(p.ch)+'</span></div>',
  o:o.map(esc),a:o.indexOf(p.n),ex:'<b>'+esc(p.n)+'</b> · '+esc(p.s)}}};
var RG=['sec','cap2','chg2'].concat(FU.length?['fut']:[],CP.length?['chart2']:[],pool('p').length>=10?['px','r1']:[],FM.some(function(m){return pool(m.k).length>=10})?['fin']:[]);
function rtop(){var left=Math.max(0,Math.ceil((rushEnd-Date.now())/1000));return '<div class="gm-top"><span>점수 <span class="sc">'+score+'</span></span><span class="tm" id="gmt">⏱ '+left+'초</span><span class="best">최고 '+best()+'</span></div>'}
function mcDraw(msg){busy=false;cur=G[mode==='rush'?rnd(RG):mode]();
 box.innerHTML=(mode==='rush'?rtop():top())+'<div class="gm-q">'+cur.q+'</div>'+(cur.body||'')+'<div class="cg-opts">'+cur.o.map(function(t,i){return '<button type="button" data-i="'+i+'">'+t+'</button>'}).join('')+'</div><div class="gm-msg">'+(msg||'')+'</div>'}
function rushStart(){score=0;rushEnd=Date.now()+RUN*1000;clearInterval(timer);timer=setInterval(function(){var el=document.getElementById('gmt'),left=Math.ceil((rushEnd-Date.now())/1000);
  if(el)el.textContent='⏱ '+Math.max(0,left)+'초';if(left<=0){clearInterval(timer);busy=true;box.querySelectorAll('.cg-opts button').forEach(function(x){x.disabled=true});over('⏱ 시간 끝!')}},250);mcDraw()}
function start(){score=0;clearInterval(timer);
 if(mode==='rush'){box.innerHTML='<div class="gm-start"><b style="font-size:18px">⏱ 60초 챌린지</b><br>차트·업종·주가·시가총액·실적 문제가 섞여 나와요.<br>60초 동안 최대한 많이 맞혀 보세요. <b>틀려도 계속!</b><br><span style="color:var(--muted)">최고 '+best()+'점</span><br><button type="button" data-g="go">시작!</button></div>';return}
 if(G[mode]){mcDraw();return}
 if(mode==='chart'){if(!CP.length){box.innerHTML='<p class="gm-msg">차트 자료를 불러오지 못했어요.</p>';return}drawChart();return}A=pick();B=pair(A);draw()}
box.addEventListener('click',function(e){var g=e.target.closest('[data-g]'),c=e.target.closest('button.gm-card'),op=e.target.closest('button[data-o]'),oi=e.target.closest('button[data-i]');
 if(g&&g.dataset.g==='again'){if(mode==='rush')rushStart();else start();return}
 if(g&&g.dataset.g==='go'){count();rushStart();return}
 if(busy)return;
 if(oi&&cur){count();busy=true;var ok=+oi.dataset.i===cur.a;if(ok)score++;
  box.querySelectorAll('.cg-opts button').forEach(function(x,i){x.disabled=true;if(i===cur.a)x.classList.add('ok');else if(x===oi)x.classList.add('no')});
  if(cur.after)cur.after();box.querySelector('.gm-msg').insertAdjacentHTML('beforebegin','<div class="cg-ex">'+cur.ex+'</div>');track(ok);
  if(mode==='rush'){box.querySelector('.sc').textContent=score;setTimeout(function(){if(mode==='rush'&&Date.now()<rushEnd)mcDraw(ok?'✅ 정답!':'❌ 아쉬워요')},ok?(cur.after?1500:800):(cur.after?2400:1800));return}
  var md=mode;if(ok)setTimeout(function(){if(mode===md)mcDraw('✅ 정답!')},cur.after?2400:1600);else over('❌ 아쉬워요');return}
 if(mode==='chart'&&op){count();busy=true;var ok=op.dataset.o===cq.n;
  box.querySelectorAll('.cg-opts button').forEach(function(x){x.disabled=true;if(x.dataset.o===cq.n)x.classList.add('ok');else if(x===op)x.classList.add('no')});
  var ex='<div class="cg-ex"><b>'+esc(cq.n)+'</b> · '+esc(cq.m)+' · '+esc(cq.s)+(PN[cq.pat]?'<br><b>'+esc(cq.pat)+'</b>: '+esc(PN[cq.pat]):'')+'</div>';
  box.querySelector('.gm-msg').insertAdjacentHTML('beforebegin',ex);
  track(ok);if(ok){score++;setTimeout(function(){drawChart('✅ 정답! '+esc(cq.n))},1800)}else over('❌ 정답은 '+esc(cq.n));return}
 if(mode==='cap'&&g){count();busy=true;var ok=(g.dataset.g==='hi')===(B.c>A.c);
  box.querySelectorAll('.gm-card')[1].outerHTML=card(B,true,'div',ok?'ok':'no');box.querySelectorAll('.gm-btns button').forEach(function(x){x.disabled=true});
  if(ok)score++;track(ok);if(ok){var nb=B;setTimeout(function(){A=nb;B=pair(A);draw('✅ 정답! '+esc(nb.n)+' '+won(nb.c))},900)}
  else over('❌ '+esc(B.n)+' 시가총액은 '+won(B.c)+' ('+esc(A.n)+' '+won(A.c)+')')}
 if(mode==='chg'&&c){count();busy=true;var pickA=c.dataset.n===A.n,win=pickA?A.p>B.p:B.p>A.p;
  var row=box.querySelector('.gm-row');row.innerHTML=card(A,true,'div',pickA?(win?'ok':'no'):'')+'<span class="gm-vs">VS</span>'+card(B,true,'div',pickA?'':(win?'ok':'no'));
  if(win)score++;track(win);if(win){setTimeout(function(){A=pick();B=pair(A);draw('✅ 정답!')},1000)}else over('❌ 아쉬워요')}});
function sel(b){mode=b.dataset.m;document.querySelectorAll('.gm-tabs button').forEach(function(x){x.classList.toggle('on',x===b)});start()}
document.querySelector('.gm-tabs').addEventListener('click',function(e){var b=e.target.closest('button[data-m]');if(!b)return;sel(b);
 try{history.replaceState(null,'','#'+mode)}catch(x){}});
var hb=location.hash&&document.querySelector('.gm-tabs button[data-m="'+location.hash.slice(1).replace(/[^a-z0-9]/g,'')+'"]');
lvl();if(hb)sel(hb);else start()})();"""


def build(out, page, now, api, ns):
    """/play/ 페이지. 게임 자료(map.json)가 없으면 안내만 낸다."""
    rows, day = stocks()
    (out / "play").mkdir(parents=True, exist_ok=True)
    if len(rows) < 50:
        body = '<p class="err">게임 자료를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>'
    else:
        d = datetime.strptime(day[:10], "%Y-%m-%d") if day else now
        dlab = f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})"
        try:
            puzzles, nums, future = game_data(rows)
        except Exception as e:  # 차트·숫자 자료가 실패해도 다른 게임은 돈다
            print("차트 문제 실패:", type(e).__name__, e)
            puzzles, nums, future = [], {}, []
        data = (f"var S={json.dumps(rows, ensure_ascii=False, separators=(',', ':'))},DAY={json.dumps(dlab)},"
                f"CP={json.dumps(puzzles, ensure_ascii=False, separators=(',', ':'))},X={json.dumps(nums, ensure_ascii=False, separators=(',', ':'))},"
                f"FU={json.dumps(future, ensure_ascii=False, separators=(',', ':'))},PN={json.dumps(PATTERN_NOTE, ensure_ascii=False)},"
                f"PAPI={json.dumps(api)},PNS={json.dumps(ns)};").replace("</", "<\\/")
        body = (f'<style>{GAME_CSS}</style>'
                '<div class="gm-lv" id="gmlv"></div>'
                '<div class="gm-tabs"><button type="button" class="hot" data-m="rush">⏱ 60초 챌린지</button>'
                '<button type="button" class="on" data-m="cap">💰 시가총액 대결</button>'
                '<button type="button" data-m="chg">📈 오늘 더 오른 종목</button>'
                '<button type="button" data-m="chart">📊 차트 보고 맞히기</button>'
                '<button type="button" data-m="fut">🔮 차트 다음은?</button>'
                '<button type="button" data-m="sec">🏭 업종 맞히기</button>'
                '<button type="button" data-m="px">💵 주가 맞히기</button>'
                '<button type="button" data-m="r1">📅 1년 수익률 대결</button>'
                '<button type="button" data-m="fin">🧾 실적 대결</button></div>'
                '<div class="gm" id="gm"></div>'
                f'<p class="gm-note">· 자료: 네이버 증권 업종별 종목 시가총액·등락률 ({escape(day)} 기준, 시가총액 상위 {len(rows)}종목, ETF·우선주 제외), '
                '네이버 증권 일봉 종가(차트·주가·1년 수익률), DART 최근 정기보고서 누적 숫자·KB증권 현재가 PER(실적 대결).<br>'
                '· 60초 챌린지는 틀려도 계속, 나머지는 틀릴 때까지 이어집니다. 등급·미션·최고 기록은 이 기기에만 저장돼요.<br>'
                '· 홈의 <a href="../#predict">🎯 코스피 오를까 내릴까?</a>에서 다음 장을 맞혀 보세요.</p>'
                f'<script>{data}\n{GAME_JS}</script>')
    (out / "play" / "index.html").write_text(page("🎮 놀이터", body, "../", "play/", "PLAYGROUND",
                                                  "60초 챌린지 · 시가총액 대결 · 차트 · 업종 · 주가 · 실적 대결 등 게임 9가지"), encoding="utf-8")
    return len(rows)


# ---------- 📊 차트 보고 맞히기 (패턴: 52주 신고가 · N자형 · 오른쪽이 덜 오른 u자형) ----------
FCHART = "https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=260&requestType=0"
CODES_URL = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/study-fin/index.json"
PATTERN_NOTE = {
    "신고가": "최근 1년(52주) 가장 높은 가격 근처에서 마감. 위에 매물이 없어 추세가 이어지기 쉬운 자리로 봅니다.",
    "N자형": "한 번 오르고(첫 다리) 눌림을 준 뒤 다시 올라 직전 고점을 넘은 모양. 눌림에서 버틴 매수세를 확인한 돌파로 봅니다.",
    "u자형": "고점에서 크게 빠진 뒤 바닥을 둥글게 다지고 오른쪽이 아직 덜 올라온 모양(컵의 오른쪽 벽이 덜 찬 상태). 왼쪽 고점까지 회복할지가 관전 포인트입니다.",
}


def _closes(code):
    try:
        with urllib.request.urlopen(urllib.request.Request(FCHART.format(code=code), headers=UA), timeout=15) as r:
            xml = r.read().decode("euc-kr", "replace")
    except Exception:
        return []
    out = []
    for d in re.findall(r'<item data="([^"]+)"', xml):
        f = d.split("|")
        try:
            out.append((f[0], float(f[4])))
        except (IndexError, ValueError):
            continue
    return out


def find_pattern(cl):
    """종가 목록(오래된 것부터, 약 1년)에서 패턴 이름. 없으면 None."""
    n = len(cl)
    if n < 200:
        return None
    last = cl[-1]
    # 52주 신고가: 최근 20거래일 안에 1년 최고가를 찍었고, 지금도 그 가격의 95% 이상
    hi = max(cl)
    if cl.index(hi) >= n - 20 and last >= hi * 0.95:
        return "신고가"
    # N자형: 최근 120일 안에 첫 고점(12% 넘게 오른 뒤) → 6% 넘게 눌림 → 최근 15일 안에 첫 고점을 넘음
    w = cl[-120:]
    p1 = max(range(len(w) - 10), key=lambda i: w[i])
    lo0 = min(w[max(0, p1 - 60):p1 + 1])
    tr = min(w[p1:])
    if (w[p1] >= lo0 * 1.12 and tr <= w[p1] * 0.94 and w.index(tr, p1) < len(w) - 3
            and last > w[p1] and any(x <= w[p1] for x in w[-15:-1])):
        return "N자형"
    # u자형(오른쪽 미상승): 90일 넘은 왼쪽 고점 → 25% 넘게 빠진 바닥(가운데쯤, 30일 넘게 지남) → 바닥 근처에서 15일 넘게 다짐
    # → 지금은 바닥보다 8% 넘게 올랐지만 낙폭의 절반도 못 회복, 최근 20일은 오르는 중
    left = max(range(n - 90), key=lambda i: cl[i])
    b = min(range(left, n), key=lambda i: cl[i])
    H, B = cl[left], cl[b]
    base = sum(1 for x in cl[left:] if x <= B * 1.12)
    if (H >= B * 1.33 and b - left >= 30 and n - 1 - b >= 30 and base >= 15
            and B * 1.08 <= last <= B + (H - B) * 0.5 and last > cl[-20]):
        return "u자형"
    return None


FIN_URL = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/study-fin/fin/{code}.json"


def _fin(code):
    try:
        with urllib.request.urlopen(urllib.request.Request(FIN_URL.format(code=code), headers=UA), timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _metrics(j):
    """study-fin 숫자 → 실적 대결용 {opm(영업이익률), g(매출 증가율), roe, per}. 금융사는 영업이익률·매출 증가율을 뺀다."""
    if not j:
        return {}
    v, px, m = j.get("v") or {}, j.get("px") or {}, {}
    rev, op = v.get("rev"), v.get("op")
    if not j.get("fin") and isinstance(rev, list) and isinstance(op, list) and rev and op and rev[0] and rev[0] > 0 and op[0] is not None:
        m["opm"] = round(op[0] / rev[0] * 100, 1)
        if len(rev) > 1 and rev[1] and rev[1] > 0:
            m["g"] = round((rev[0] / rev[1] - 1) * 100, 1)
    if isinstance(v.get("roe"), (int, float)):
        m["roe"] = round(v["roe"], 1)
    if isinstance(px.get("per"), (int, float)) and px["per"] > 0:
        m["per"] = round(px["per"], 1)
    return m


def future_puzzle(r, ser):
    """🔮 차트 다음은?: 약 1년 종가를 이틀 간격 120점으로 줄이고, 마지막 20점(약 40거래일)을 가린다. 5% 넘게 움직인 것만."""
    if len(ser) < 240:
        return None
    pick = ser[::-1][::2][:120][::-1]
    cut = 99
    ch = pick[-1][1] / pick[cut][1] - 1
    if abs(ch) < 0.05:
        return None
    return {"n": r["n"], "s": r["s"], "cl": [round(c) for _, c in pick], "cut": cut,
            "d0": pick[0][0], "dc": pick[cut][0], "d1": pick[-1][0]}


def game_data(rows):
    """시가총액 상위 220종목의 1년 일봉(네이버 fchart)·DART 숫자(study-fin)를 한 번에 받아
    (차트 문제 CP, 종목별 숫자 X{이름: {p 현재가, r 1년 등락, opm, g, roe, per}}, 차트 다음은? 문제 FU)."""
    codes = {}
    j = _get(CODES_URL) or {}
    for code, name, *_ in j.get("list") or []:
        codes[name] = code
    cands = [r for r in rows[:220] if r["n"] in codes]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        series = list(ex.map(lambda r: _closes(codes[r["n"]]), cands))
        fins = list(ex.map(lambda r: _fin(codes[r["n"]]), cands))
    X, FU = {}, []
    for r, ser, fj in zip(cands, series, fins):
        x = _metrics(fj)
        if len(ser) >= 200:
            x["p"] = round(ser[-1][1])
            x["r"] = round((ser[-1][1] / ser[0][1] - 1) * 100, 1)
        if x:
            X[r["n"]] = x
        fu = future_puzzle(r, ser)
        if fu:
            FU.append(fu)
    print("게임 숫자:", len(X), "종목 / 차트 다음은?", len(FU), "문제")
    return chart_puzzles(cands, series), X, FU[:90]


def chart_puzzles(cands, series):
    """게임에 쓸 차트 문제 [{n, m, s, c(시가총액), pat, price, hi, lo, ch(1년 등락 %), pts(0~100 정규화 120점), d0, d1}]."""
    out = []
    for r, ser in zip(cands, series):
        cl = [c for _, c in ser]
        pat = find_pattern(cl) or ("차트" if len(cl) >= 200 else None)  # 패턴이 없는 종목도 '차트 보고 맞히기'로 쓴다
        if not pat:
            continue
        step = max(1, len(cl) // 120)
        pick = cl[::step][-120:]
        lo, hi = min(pick), max(pick)
        pts = [round((x - lo) / (hi - lo) * 100, 1) if hi > lo else 50 for x in pick]
        out.append({"n": r["n"], "m": r["m"], "s": r["s"], "c": r["c"], "pat": pat, "price": cl[-1], "hi": max(cl), "lo": min(cl),
                    "ch": round((cl[-1] / cl[0] - 1) * 100, 1), "pts": pts, "d0": ser[0][0], "d1": ser[-1][0]})
    keep = []
    for pat in list(PATTERN_NOTE) + ["차트"]:  # 패턴마다 시가총액 큰 순으로 12개까지, 패턴 없는 차트는 40개까지
        keep += [x for x in out if x["pat"] == pat][:40 if pat == "차트" else 12]
    print("차트 문제:", {p: sum(1 for x in keep if x["pat"] == p) for p in list(PATTERN_NOTE) + ["차트"]}, "/ 후보", len(cands))
    return keep


# ---------- 🧪 전략 검증 (/lab/): '영업이익 급증' 알림 시각 매수 → 5분 뒤 매도 ----------
FEED_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json"
LAB_CSS = """.lb-sum{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:0 0 12px}
@media (max-width:560px){.lb-sum{grid-template-columns:1fr 1fr}}
.lb-sum div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.lb-sum>div>span{display:block;font-size:12.5px;color:var(--muted);font-weight:700}.lb-sum b{font-size:22px;font-variant-numeric:tabular-nums}
.lb-rule{background:#FBE7B0;color:#3D3A35;border-radius:12px;padding:10px 14px;font-size:14px;line-height:1.6;margin:0 0 12px;word-break:keep-all}
.lb-eq{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:0 0 12px}
.lb-eq svg{display:block;width:100%;height:120px}.lb-eq .t{font-size:13px;color:var(--muted);font-weight:700}
.lb-t{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.lb-t td,.lb-t th{padding:8px 6px;border-top:1px solid var(--line);text-align:right;vertical-align:top}
.lb-t th{font-size:12.5px;color:var(--muted)}.lb-t td:first-child,.lb-t th:first-child{text-align:left}
.lb-t .n{font-weight:800}.lb-t .s{font-size:12px;color:var(--muted)}.lb-t .r{font-weight:900;font-size:16px}
.up{color:var(--up)}.down{color:var(--down)}
.lb-note{font-size:12.5px;color:var(--muted);line-height:1.7;margin-top:14px}"""
LAB_JS = r"""(function(){var box=document.getElementById('lab'),COST=0.25;
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function pc(v,d){return '<span class="'+(v>0?'up':v<0?'down':'')+'">'+(v>0?'+':'')+v.toFixed(d==null?2:d)+'%</span>'}
function hm(s){return s.slice(0,2)+':'+s.slice(2,4)}
function md(iso){return (+iso.slice(5,7))+'/'+(+iso.slice(8,10))+' '+iso.slice(11,16)}
function render(L){var done=L.filter(function(e){return e.ret!=null}),wait=L.filter(function(e){return e.ret==null&&!e.skip}),skip=L.filter(function(e){return e.skip});
 var n=done.length,win=done.filter(function(e){return e.ret>0}).length,avg=n?done.reduce(function(a,e){return a+e.ret},0)/n:0;
 var eq=[100],m=100;done.slice().reverse().forEach(function(e){m*=1+(e.ret-COST)/100;eq.push(m)});
 var sum='<div class="lb-sum"><div><span>매매 건수</span><b>'+n+'</b></div><div><span>승률</span><b>'+(n?Math.round(win/n*100):0)+'%</b></div>'+
  '<div><span>평균 수익률</span><b>'+(n?pc(avg):'-')+'</b></div><div><span>비용 뺀 누적</span><b>'+(n?pc(m-100,1):'-')+'</b></div></div>';
 var chart='';if(n>=2){var w=300,h=100,lo=Math.min.apply(0,eq),hi=Math.max.apply(0,eq);if(hi===lo){hi+=1;lo-=1}
  var pts=eq.map(function(v,i){return (i/(eq.length-1)*w).toFixed(1)+','+(h-6-(v-lo)/(hi-lo)*(h-12)).toFixed(1)}).join(' ');
  var y0=(h-6-(100-lo)/(hi-lo)*(h-12)).toFixed(1);
  chart='<div class="lb-eq"><div class="t">100에서 시작해 매매마다 (수익률 − 비용 '+COST+'%)씩 불린 값 · 지금 '+m.toFixed(1)+'</div>'+
   '<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><line x1="0" x2="'+w+'" y1="'+y0+'" y2="'+y0+'" stroke="#aaa" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>'+
   '<polyline points="'+pts+'" fill="none" stroke="'+(m>=100?'#e03131':'#1c6dd0')+'" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg></div>'}
 var rows=L.map(function(e){var lag=Math.round((Date.parse(e.sent)-Date.parse(e.disclosed))/6e4);
  var res=e.ret!=null?'<span class="r">'+pc(e.ret)+'</span><div class="s">'+hm(e.buy_t)+' '+e.buy.toLocaleString('ko-KR')+' → '+hm(e.sell_t)+' '+e.sell.toLocaleString('ko-KR')+'</div>'
   :e.skip?'<span class="s">'+esc(e.skip)+'</span>':'<span class="s">계산 중 (매도 시각 뒤 다음 감시 때)</span>';
  return '<tr><td><span class="n">'+esc(e.name)+'</span><div class="s">'+esc(e.head||'')+'</div><div class="s">공시 '+md(e.disclosed)+' → 알림 '+md(e.sent).slice(-5)+' ('+lag+'분 뒤)'+(e.note?' · '+esc(e.note):'')+'</div></td><td>'+res+'</td></tr>'}).join('');
 box.innerHTML='<div class="lb-rule">📌 규칙: 국내 <b>영업이익 급증</b> 알림(텔레그램)이 도착한 시각에 <b>다음 1분봉 시가로 매수</b>하고, <b>5분 뒤 1분봉 시가로 매도</b>했다면?</div>'+sum+chart+
  (L.length?'<table class="lb-t"><thead><tr><th>종목 · 공시 → 알림</th><th>5분 수익률</th></tr></thead><tbody>'+rows+'</tbody></table>':'<p class="err">아직 기록이 없습니다.</p>')}
render(SEED);
fetch(FEED+'?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){if(j&&j.strategy&&j.strategy.length)render(j.strategy)}).catch(function(){})})();"""


def build_lab(out, page):
    """전략 검증 페이지. 기록은 kb 실적 감시가 earnings.json 의 strategy 에 쌓는다(사이트를 만들 때 넣고, 볼 때 최신으로 다시 읽음)."""
    seed = (_get(FEED_URL) or {}).get("strategy") or []
    data = (f"var SEED={json.dumps(seed, ensure_ascii=False)},FEED={json.dumps(FEED_URL)};").replace("</", "<\\/")
    body = (f'<style>{LAB_CSS}</style><div id="lab"></div>'
            '<p class="lb-note">· 메시지 시각은 실적 감시가 알림을 보낸 분(分)입니다. 그 다음 1분봉 시가에 사고 5분 뒤 1분봉 시가에 판 것으로 계산합니다(네이버 증권 1분봉).<br>'
            '· 장 시작 전 알림은 09:00 시가에 사서 09:05에 판 것으로, 15:20 이후 알림은 매매하지 않은 것으로 봅니다.<br>'
            '· 누적은 수수료·세금·체결 차이를 합쳐 매매마다 0.25%를 뺀 <b>가정</b>입니다. 실제 체결가는 호가·주문량에 따라 다릅니다.<br>'
            '· 투자 권유가 아닌 전략 점검용 기록입니다. 알림이 나갈 때마다 자동으로 늘어납니다.</p>'
            f'<script>{data}\n{LAB_JS}</script>')
    (out / "lab").mkdir(parents=True, exist_ok=True)
    (out / "lab" / "index.html").write_text(page("🧪 전략 검증", body, "../", "lab/", "STRATEGY LAB",
                                                 "실적 서프라이즈 알림에 사서 5분 뒤에 팔면?"), encoding="utf-8")
    return len(seed)
