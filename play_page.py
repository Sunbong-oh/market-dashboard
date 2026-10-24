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
function start(){score=0;A=pick();B=pair(A);draw()}
box.addEventListener('click',function(e){var g=e.target.closest('[data-g]'),c=e.target.closest('button.gm-card');
 if(g&&g.dataset.g==='again'){start();return}
 if(busy)return;
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
        data = (f"var S={json.dumps(rows, ensure_ascii=False, separators=(',', ':'))},DAY={json.dumps(dlab)},"
                f"PAPI={json.dumps(api)},PNS={json.dumps(ns)};").replace("</", "<\\/")
        body = (f'<style>{GAME_CSS}</style>'
                '<div class="gm-tabs"><button type="button" class="on" data-m="cap">💰 시가총액 대결</button>'
                '<button type="button" data-m="chg">📈 오늘 더 오른 종목</button></div>'
                '<div class="gm" id="gm"></div>'
                f'<p class="gm-note">· 자료: 네이버 증권 업종별 종목 시가총액·등락률 ({escape(day)} 기준, 시가총액 상위 {len(rows)}종목, ETF·우선주 제외).<br>'
                '· 틀릴 때까지 계속 이어집니다. 최고 기록은 이 기기에만 저장돼요.<br>'
                '· 홈의 <a href="../#predict">🎯 코스피 오를까 내릴까?</a>에서 다음 장을 맞혀 보세요.</p>'
                f'<script>{data}\n{GAME_JS}</script>')
    (out / "play" / "index.html").write_text(page("🎮 놀이터", body, "../", "play/", "PLAYGROUND",
                                                  "시가총액 대결 · 오늘 더 오른 종목 맞히기"), encoding="utf-8")
    return len(rows)
