"""놀이터: 홈 '코스피 오를까 내릴까?' 투표 + /play/ 게임(시가총액 대결 · 오늘 더 오른 종목).

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
#predict .go{display:block;margin-top:12px;text-align:center;font-weight:800;padding:10px;border-radius:12px;background:#FBE7B0;color:#3D3A35;text-decoration:none}"""

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
 box.innerHTML=q+rec+'<a class="go" href="play/">🎮 놀이터에서 더 놀기: 시가총액 대결 · 오늘 더 오른 종목 ›</a>';
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


GAME_CSS = """.gm-tabs{display:flex;gap:6px;margin:0 0 12px;flex-wrap:wrap}
.gm-tabs button{font:800 15px/1 inherit;padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
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
function start(){score=0;if(mode==='chart'){if(!CP.length){box.innerHTML='<p class="gm-msg">차트 자료를 불러오지 못했어요.</p>';return}drawChart();return}A=pick();B=pair(A);draw()}
box.addEventListener('click',function(e){var g=e.target.closest('[data-g]'),c=e.target.closest('button.gm-card'),op=e.target.closest('button[data-o]');
 if(g&&g.dataset.g==='again'){start();return}
 if(busy)return;
 if(mode==='chart'&&op){count();busy=true;var ok=op.dataset.o===cq.n;
  box.querySelectorAll('.cg-opts button').forEach(function(x){x.disabled=true;if(x.dataset.o===cq.n)x.classList.add('ok');else if(x===op)x.classList.add('no')});
  var ex='<div class="cg-ex"><b>'+esc(cq.n)+'</b> · '+esc(cq.m)+' · '+esc(cq.s)+(PN[cq.pat]?'<br><b>'+esc(cq.pat)+'</b>: '+esc(PN[cq.pat]):'')+'</div>';
  box.querySelector('.gm-msg').insertAdjacentHTML('beforebegin',ex);
  if(ok){score++;setTimeout(function(){drawChart('✅ 정답! '+esc(cq.n))},1800)}else over('❌ 정답은 '+esc(cq.n));return}
 if(mode==='cap'&&g){count();busy=true;var ok=(g.dataset.g==='hi')===(B.c>A.c);
  box.querySelectorAll('.gm-card')[1].outerHTML=card(B,true,'div',ok?'ok':'no');box.querySelectorAll('.gm-btns button').forEach(function(x){x.disabled=true});
  if(ok){score++;var nb=B;setTimeout(function(){A=nb;B=pair(A);draw('✅ 정답! '+esc(nb.n)+' '+won(nb.c))},900)}
  else over('❌ '+esc(B.n)+' 시가총액은 '+won(B.c)+' ('+esc(A.n)+' '+won(A.c)+')')}
 if(mode==='chg'&&c){count();busy=true;var pickA=c.dataset.n===A.n,win=pickA?A.p>B.p:B.p>A.p;
  var row=box.querySelector('.gm-row');row.innerHTML=card(A,true,'div',pickA?(win?'ok':'no'):'')+'<span class="gm-vs">VS</span>'+card(B,true,'div',pickA?'':(win?'ok':'no'));
  if(win){score++;setTimeout(function(){A=pick();B=pair(A);draw('✅ 정답!')},1000)}else over('❌ 아쉬워요')}});
document.querySelector('.gm-tabs').addEventListener('click',function(e){var b=e.target.closest('button[data-m]');if(!b)return;mode=b.dataset.m;
 document.querySelectorAll('.gm-tabs button').forEach(function(x){x.classList.toggle('on',x===b)});start()});
start()})();"""


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
            puzzles = chart_puzzles(rows)
        except Exception as e:  # 차트 문제가 실패해도 다른 게임은 돈다
            print("차트 문제 실패:", type(e).__name__, e)
            puzzles = []
        data = (f"var S={json.dumps(rows, ensure_ascii=False, separators=(',', ':'))},DAY={json.dumps(dlab)},"
                f"CP={json.dumps(puzzles, ensure_ascii=False, separators=(',', ':'))},PN={json.dumps(PATTERN_NOTE, ensure_ascii=False)},"
                f"PAPI={json.dumps(api)},PNS={json.dumps(ns)};").replace("</", "<\\/")
        body = (f'<style>{GAME_CSS}</style>'
                '<div class="gm-tabs"><button type="button" class="on" data-m="cap">💰 시가총액 대결</button>'
                '<button type="button" data-m="chg">📈 오늘 더 오른 종목</button>'
                '<button type="button" data-m="chart">📊 차트 보고 맞히기</button></div>'
                '<div class="gm" id="gm"></div>'
                f'<p class="gm-note">· 자료: 네이버 증권 업종별 종목 시가총액·등락률 ({escape(day)} 기준, 시가총액 상위 {len(rows)}종목, ETF·우선주 제외).<br>'
                '· 틀릴 때까지 계속 이어집니다. 최고 기록은 이 기기에만 저장돼요.<br>'
                '· 홈의 <a href="../#predict">🎯 코스피 오를까 내릴까?</a>에서 다음 장을 맞혀 보세요.</p>'
                f'<script>{data}\n{GAME_JS}</script>')
    (out / "play" / "index.html").write_text(page("🎮 놀이터", body, "../", "play/", "PLAYGROUND",
                                                  "시가총액 대결 · 오늘 더 오른 종목 · 차트 보고 회사 맞히기"), encoding="utf-8")
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


def chart_puzzles(rows):
    """게임에 쓸 차트 문제 [{n, m, s, c(시가총액), pat, price, hi, lo, ch(1년 등락 %), pts(0~100 정규화 120점), d0, d1}]."""
    codes = {}
    j = _get(CODES_URL) or {}
    for code, name, *_ in j.get("list") or []:
        codes[name] = code
    cands = [r for r in rows[:220] if r["n"] in codes]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        series = list(ex.map(lambda r: _closes(codes[r["n"]]), cands))
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
