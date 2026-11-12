"""홈: 네이버 기준 실시간 수급(KB 화면과 비교용) · 글로벌 지수 (2026-11-12 시작).

자료는 kb-market-report 의 naver_flow.py(naver-flow.yml, GitHub 서버)가 평일 08:30~17:20 1분마다
naver-live 브랜치 naver.json 에 올린다. 화면은 보는 사람 브라우저가 1분마다 읽어 다시 그린다(KB 접속 없음).
교차차트는 장마감 리포트와 같은 futChart(build_site.FUT_JS)로 그린다.
KB 값(flow-live snapshot.json)이 오늘 것이면 아래에 'KB vs 네이버' 비교 표를 붙인다.
"""
import json

NAVER_SRC = ("https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/naver-live/naver.json",
             "https://api.github.com/repos/Sunbong-oh/kb-market-report/contents/naver.json?ref=naver-live")
KB_SRC = ("https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/snapshot.json",)

CSS = """<style>
.home>#naver,.home>#world{order:0}
.close-first .home>#naver,.close-first .home>#world{order:-1}
.nvb{background:#fff;color:#1c2330;border:1px solid #e3e6ec;border-radius:14px;padding:16px 18px;font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif}
.nvb+.nvb{margin-top:12px}
.nvb h3{margin:0 0 4px;font-size:17px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.nvb h3 small{font-size:12.5px;font-weight:600;color:#7a828c}
.nvb h4{margin:14px 0 4px;font-size:15px;display:flex;justify-content:space-between;align-items:baseline}
.nvb h4 small{font-size:12.5px;font-weight:600;color:#7a828c}
.nvb .mk{margin:12px 0 4px;font-size:16px;font-weight:800;color:#15803d}.nvb .mk small{font-size:12px;font-weight:500;color:#7a828c;margin-left:6px}
.nvb .row{display:grid;grid-template-columns:64px 1fr 104px;align-items:center;gap:8px;padding:5px 0;font-size:14px;font-weight:700}
.nvb .tr{position:relative;height:14px;background:#f1f3f6;border-radius:7px}
.nvb .tr::after{content:"";position:absolute;left:50%;top:0;bottom:0;width:1px;background:#d6dae2}
.nvb .tr i{position:absolute;top:0;bottom:0;border-radius:4px}
.nvb .tr i.p{left:50%;background:#e03131}.nvb .tr i.n{right:50%;background:#2f6fdb}
.nvb .v{text-align:right;font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}
.nvb .up{color:#e03131}.nvb .dn{color:#2f6fdb}
.nvb .two{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
@media(max-width:620px){.nvb .two{grid-template-columns:1fr}}
.nvb .note{margin:10px 0 0;font-size:12px;color:#8a92a3;line-height:1.5}
.nvb hr{border:0;border-top:1px solid #e3e6ec;margin:14px 0 4px}
.nvb .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#15803d;margin-right:5px;animation:futp 1.4s infinite}
.nvb table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.nvb th{background:#1c2330;color:#fff;font-weight:700;padding:7px 6px;font-size:13px}
.nvb td{padding:7px 6px;border-bottom:1px solid #e3e6ec;text-align:right;font-weight:700}
.nvb td:first-child{text-align:left;font-weight:800}
.nvb td.df{color:#7a828c;font-weight:600}
.nvb .fut{border:0;padding:0;margin:0;background:none}.nvb .fut h3{margin:0 0 10px;font-size:17px}
.wg{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.wg .w{background:#fff;color:#1c2330;border:1px solid #e3e6ec;border-radius:14px;padding:12px 14px;font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;min-width:0}
.wg .w .h{display:flex;justify-content:space-between;align-items:baseline;gap:6px;font-size:13px;color:#6b7385;font-weight:700}
.wg .w .h b{font-size:15px;color:#1c2330}
.wg .w .p{font-size:22px;font-weight:900;letter-spacing:-.4px;font-variant-numeric:tabular-nums;margin-top:2px}
.wg .w .c{font-size:13.5px;font-weight:800}
.wg .w svg{display:block;width:100%;height:40px;margin-top:6px}
.wg .w .s{font-size:11.5px;color:#8a92a3;margin-top:4px}
.wg .w .live{color:#15803d;font-weight:800}
.wg .up{color:#e03131}.wg .dn{color:#2f6fdb}
.wg .nat{grid-column:1/-1;font-size:14px;font-weight:800;color:var(--muted);margin:6px 0 -4px}
@media(max-width:520px){.wg{grid-template-columns:1fr 1fr}.wg .w{padding:10px 11px}.wg .w .p{font-size:18px}.wg .w .h{flex-direction:column;gap:0}}
</style>"""

JS = r"""<script>
(function(){var SRC=__SRC__,KB=__KB__,box=document.getElementById('naver'),wb=document.getElementById('world');if(!box)return;
 var kst=function(){var n=new Date(Date.now()+9*3600e3);return {d:n.toISOString().slice(0,10).replace(/-/g,''),hm:n.toISOString().slice(11,16),wd:n.getUTCDay()}};
 var n0=function(v){return Math.round(Math.abs(v)).toLocaleString('ko-KR')},sg=function(v){return v==null?'-':(v>0?'+':v<0?'-':'')+n0(v)};
 var cl=function(v){return v>0?'up':v<0?'dn':''};
 var f2=function(v,d){return v==null?'-':v.toLocaleString('ko-KR',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d})};
 var KB_J=null;
 function get(list,cb,i){i=i||0;if(i>=list.length)return cb(null);var x=new XMLHttpRequest();
  x.open('GET',list[i]+(list[i].indexOf('api.github')>0?'':'?t='+Date.now()));if(list[i].indexOf('api.github')>0)x.setRequestHeader('Accept','application/vnd.github.raw');
  x.onload=function(){if(x.status!==200)return get(list,cb,i+1);try{cb(JSON.parse(x.responseText))}catch(e){get(list,cb,i+1)}};
  x.onerror=function(){get(list,cb,i+1)};x.send()}
 function rows(o,keys,scale){return keys.filter(function(k){return o&&o[k]!=null}).map(function(k){var v=o[k],w=Math.min(1,Math.abs(v)/scale)*50;
  return '<div class="row"><span>'+k+'</span><div class="tr"><i class="'+(v>=0?'p':'n')+'" style="width:'+w.toFixed(1)+'%"></i></div><span class="v '+cl(v)+'">'+sg(v)+'</span></div>'}).join('')}
 function mk(n,s){return '<div class="mk">'+n+'<small>막대 기준 '+s+'</small></div>'}
 function inv(j){var I=j.inv||{},K=['외국인','기관계','개인'],today=j.date===kst().d,P=j.prog||{};
  var pmax=Math.max(1000,Math.abs(P['합계']||0),Math.abs(P['차익']||0),Math.abs(P['비차익']||0));
  var dd=j.inv_date?j.inv_date.slice(4,6).replace(/^0/,'')+'/'+j.inv_date.slice(6):'';
  return '<h3>투자자별 매매동향 '+(j.inv_date===kst().d?'(오늘)':'('+dd+')')+'<small>네이버 증권 · 억원</small></h3>'+
   (Object.keys(I).length?'<h4>현물</h4><div class="two"><div>'+mk('코스피','2조')+rows(I['코스피'],K,20000)+'</div><div>'+mk('코스닥','5,000억')+rows(I['코스닥'],K,5000)+'</div></div>'+
   '<hr><h4>선물 (KOSPI200)</h4>'+mk('선물','3조')+rows(I['선물'],K,30000)+
   (P['합계']!=null?'<hr><h4>프로그램 매매 (코스피)</h4>'+rows(P,['차익','비차익','합계'],pmax):'')
   :'<p class="note">오늘 수급은 장 시작(08:45 선물·09:00 현물) 뒤부터 나와요.</p>')+
   '<p class="note">'+(today&&kst().hm<='15:50'?'<span class="dot"></span>':'')+(j.time?j.updated+' 기준':'')+' · GitHub 서버가 네이버 증권에서 1분마다 받음 (KB 접속 없음)<br>'+
   '※ 금융투자 · 콜/풋옵션 투자자별은 네이버가 제공하지 않아 빠져 있어요. 네이버 값은 몇 분 늦게 바뀔 수 있어요.</p>'}
 function cmp(j){var k=KB_J,d=kst().d;if(!k||k.date!==d||j.inv_date!==d||!k.data||!k.data['/api/market'])return '';
  var iv=k.data['/api/market'].investors||[],I=j.inv||{},rs='';
  [['코스피','kospi'],['코스닥','kosdaq'],['선물','futures']].forEach(function(m){['외국인','기관계','개인'].forEach(function(n){
   var r=iv.filter(function(x){return x.name===n})[0],a=r?r[m[1]]:null,b=(I[m[0]]||{})[n];if(a==null&&b==null)return;
   rs+='<tr><td>'+m[0]+' '+n+'</td><td class="'+cl(a)+'">'+sg(a)+'</td><td class="'+cl(b)+'">'+sg(b)+'</td><td class="df">'+(a!=null&&b!=null?sg(b-a):'-')+'</td></tr>'})});
  return rs?'<div class="nvb"><h3>KB vs 네이버 비교<small>억원 · KB '+k.time+' / 네이버 '+j.time+'</small></h3>'+
   '<table><thead><tr><th>항목</th><th>KB증권</th><th>네이버</th><th>차이</th></tr></thead><tbody>'+rs+'</tbody></table>'+
   '<p class="note">두 곳이 값을 받는 시각이 달라 장중에는 차이가 날 수 있어요. 차이 = 네이버 - KB.</p></div>':''}
 function spark(s,up){if(!s||s.length<2)return '';var v=s.map(function(p){return p[1]}),lo=Math.min.apply(0,v),hi=Math.max.apply(0,v),W=200,H=40;if(hi==lo)hi+=1;
  var pts=s.map(function(p,i){return (i*(W-4)/(s.length-1)+2).toFixed(1)+','+(H-3-(H-6)*(p[1]-lo)/(hi-lo)).toFixed(1)}).join(' ');
  return '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" role="img" aria-label="최근 한 달 흐름"><polyline fill="none" stroke="'+(up?'#e03131':'#2f6fdb')+'" stroke-width="2" vector-effect="non-scaling-stroke" points="'+pts+'"/></svg>'}
 function world(j){if(!wb)return;var W=j.world||[];if(!W.length){wb.hidden=true;return}wb.hidden=false;var last='',h='';
  W.forEach(function(w){if(w.nation!==last){h+='<div class="nat">'+({'미국':'🇺🇸','일본':'🇯🇵','중국':'🇨🇳','홍콩':'🇭🇰','대만':'🇹🇼'}[w.nation]||'')+' '+w.nation+'</div>';last=w.nation}
   var c=cl(w.c),open=w.status==='OPEN',sp=w.spark||[],m1=sp.length>1?(sp[sp.length-1][1]/sp[0][1]-1)*100:null;
   h+='<div class="w"><div class="h"><b>'+w.name+'</b><span>'+(open?'<span class="live">● 장중</span>':'마감')+' '+(w.at||'').slice(5,10).replace('-','/')+' '+(w.at||'').slice(11,16)+'</span></div>'+
    '<div class="p '+c+'">'+f2(w.v)+'</div><div class="c '+c+'">'+(w.c>0?'▲':w.c<0?'▼':'')+f2(Math.abs(w.c||0))+' ('+(w.pct>0?'+':'')+f2(w.pct)+'%)</div>'+
    spark(sp,m1==null||m1>=0)+'<div class="s">한 달 '+(m1==null?'-':(m1>0?'+':'')+m1.toFixed(1)+'%')+(w.delay?' · '+w.delay+'분 지연':'')+' · 현지 시각</div></div>'});
  wb.querySelector('.wg').innerHTML=h;var t=wb.querySelector('.wt');if(t)t.textContent='네이버 증권 · '+(j.world_time||'')+' 받음'}
 function draw(j){if(!j)return;var b=box.querySelector('.nv-inv');b.innerHTML=inv(j);
  var f=j.fut,fb=box.querySelector('.nv-fut'),k=kst(),live=j.date===k.d&&k.hm>='08:45'&&k.hm<='15:50';
  if(f&&window.futChart){f=Object.assign({},f,{note:'GitHub 서버가 네이버 증권에서 08:45~15:45 1분마다 받아 쌓은 값 (작업이 꺼져 있던 시간은 비어 있음) · 선물·지수 분봉도 네이버'});
   fb.hidden=!futChart(fb.lastChild,f,live)}else fb.hidden=true;
  box.querySelector('.nv-cmp').innerHTML=cmp(j);
  var h=box.querySelector('.sec-h small');if(h)h.textContent=j.date===k.d?(live?'실시간 · ':'오늘 · ')+j.time+' 기준':'최근 장 · '+(j.date||'').slice(4,6)+'/'+(j.date||'').slice(6);
  world(j)}
 var J=null;
 function tick(){if(document.hidden)return;get(SRC,function(j){if(j){J=j;draw(j)}
  var k=kst();if(k.wd>0&&k.wd<6&&k.hm>='08:00'&&k.hm<='17:30')get(KB,function(s){KB_J=s;if(J)box.querySelector('.nv-cmp').innerHTML=cmp(J)})})}
 tick();setInterval(tick,60000);document.addEventListener('visibilitychange',tick)})();
</script>"""


def home(fut_css: str, fut_js: str) -> str:
    js = JS.replace("__SRC__", json.dumps(NAVER_SRC)).replace("__KB__", json.dumps(KB_SRC))
    return (f'{CSS}{fut_css}'
            '<section class="sec" id="naver"><div class="sec-h"><h2>🟢 네이버 기준 수급 <small style="font-size:13px;color:var(--muted);font-weight:600"></small></h2>'
            '<span style="font-size:12.5px;color:var(--muted)">KB와 비교용</span></div>'
            '<div class="nvb nv-inv"><p class="note">네이버 수급을 불러오는 중…</p></div>'
            '<div class="nvb"><div class="box fut nv-fut"><h3>외국인 수급 × 지수 교차차트 (분 단위)</h3><div></div></div>'
            '</div>'
            '<div class="nv-cmp"></div></section>'
            '<section class="sec" id="world" hidden><div class="sec-h"><h2>🌏 글로벌 지수</h2><span class="wt" style="font-size:12.5px;color:var(--muted)"></span></div>'
            '<div class="wg"></div><p style="font-size:12px;color:var(--muted);margin:8px 2px 0">미국·일본·중국·홍콩·대만 대표 지수 · 그래프는 최근 약 한 달(일별 종가) · 출처 네이버 증권</p></section>'
            f'{fut_js}{js}')
