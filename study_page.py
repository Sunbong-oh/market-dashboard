"""재무제표 공부 (/study/) 페이지.

내용은 study/ 폴더의 JSON 세 개에서 읽는다. 내용을 늘릴 때는 JSON 에 항목만 추가하면 된다.
  study/terms.json       재무용어 사전   [{term, en, cat, def, formula, point}]
  study/industries.json  업종별 체크리스트 [{group, lede, items:[{name, warp, cat, rows:[[칸, 내용]]}]}]
  study/cases.json       사례노트       [{added, company, industry, period, cell, what, lesson, sources:[[제목, URL]]}]
  study/quiz.json        퀴즈(실전 문제) [{id, cat, q, c:[보기 4개], a(정답 번호 0~3), exp(해설), ref(용어·사례 이름)}]  용어 문제는 terms.json 에서 자동으로 만든다
페이지에서 직접 추가한 용어·사례·5분 체크 결과는 그 기기(브라우저)에만 저장되고,
'홈페이지에 올리기' 버튼이 Claude 에게 보낼 문장을 복사해 준다 → Claude 가 위 JSON 에 넣어 커밋한다.
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "study"


def _load(name):
    try:
        return json.loads((STUDY / name).read_text(encoding="utf-8"))
    except Exception as e:  # 파일 하나가 깨져도 나머지 사이트는 만든다
        print(f"study/{name} 읽기 실패: {e}")
        return []


def _js(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


CSS = """
.st{--ok:#2b8a3e;--ok-bg:#e6f4ea;--warn:#b7791f;--warn-bg:#fdf3dc;--bad:#c92a2a;--bad-bg:#fde8e8;--soft:#fff4e6;--mark:#ffe8b3;--mine:#1c7ed6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .st{--ok:#69db7c;--ok-bg:#1d3324;--warn:#ffc078;--warn-bg:#3a2c14;--bad:#ff8787;--bad-bg:#3d1d1d;--soft:#2e2414;--mark:#5c4313;--mine:#74c0fc}}
:root[data-theme=dark] .st{--ok:#69db7c;--ok-bg:#1d3324;--warn:#ffc078;--warn-bg:#3a2c14;--bad:#ff8787;--bad-bg:#3d1d1d;--soft:#2e2414;--mark:#5c4313;--mine:#74c0fc}
.st{display:flex;flex-direction:column;gap:14px}
.st [hidden],.sheet[hidden],.sheet [hidden]{display:none!important}
.st-tabs{display:flex;gap:6px;overflow-x:auto;padding-bottom:2px}
.st-tabs button{font:inherit;font-size:15px;font-weight:800;padding:9px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer;white-space:nowrap}
.st-tabs button[aria-selected=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.st button:focus-visible,.st input:focus-visible,.st select:focus-visible,.st textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.st-p{display:flex;flex-direction:column;gap:12px}
.st-lede{margin:0;color:var(--muted);font-size:14.5px}
.st h2{margin:6px 0 0;font-size:19px;display:flex;align-items:center;gap:8px}
.st h2:before{content:"";width:5px;height:18px;border-radius:3px;background:var(--accent)}
.st .panel p{margin:0}
.st .panel{display:flex;flex-direction:column;gap:8px}
.st .panel+.panel{margin-top:0}
.st .panel h3{margin:0;font-size:17px}
.st ul,.st ol{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:3px}
.st .eq{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:700;color:var(--accent);font-size:16px}
.st .how{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.st .how .panel .k{font-size:12px;font-weight:800;letter-spacing:.06em;color:var(--accent)}
.st .how .use{font-size:13.5px;color:var(--muted);border-top:1px dashed var(--line);padding-top:6px}
.st .go{align-self:flex-start;font:inherit;font-size:13.5px;font-weight:700;color:var(--accent);background:none;border:0;padding:0;cursor:pointer}
/* 5분 체크 */
.ck{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:start}
.ck .f{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 10px}
.ck label{display:flex;flex-direction:column;gap:3px;font-size:12.5px;font-weight:700;color:var(--muted);min-width:0}
.ck .full{grid-column:1/-1}
.st input,.st select,.st textarea{font:inherit;font-size:15px;font-weight:400;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 9px;min-width:0;width:100%}
.st textarea{min-height:60px;resize:vertical}
.ck .sep{grid-column:1/-1;font-size:13px;font-weight:800;color:var(--text);border-top:1px solid var(--line);padding-top:8px;margin-top:2px}
.ck>.nm{grid-column:1/-1;gap:6px}
.ck .nmin{display:flex;flex-direction:column;gap:6px}
.ck .nm label{font-size:13px;font-weight:700;color:var(--text)}
.ck .nm label{display:block}
.nmrow{display:flex;gap:6px}.nmrow input{flex:1}
.ck .src{font-size:12.5px;color:var(--muted);line-height:1.5}
.ck .src.ok{color:var(--ok)}.ck .src.bad{color:var(--bad)}
.ck .src a{color:var(--accent)}
.ck input.auto{background:var(--soft)}
.ck .ex{font-size:12.5px;color:var(--warn);background:var(--warn-bg);border-radius:8px;padding:6px 9px}
.sig{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--line)}
.sig:first-of-type{border-top:0}
.dot{flex:none;width:58px;text-align:center;font-size:12.5px;font-weight:800;border-radius:99px;padding:3px 0}
.dot.g{background:var(--ok-bg);color:var(--ok)}.dot.y{background:var(--warn-bg);color:var(--warn)}.dot.r{background:var(--bad-bg);color:var(--bad)}.dot.n{background:var(--bg);color:var(--muted);border:1px solid var(--line)}
.qs{margin-top:10px;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.qs h4{margin:0 0 6px;font-size:14.5px}.qs .tg{display:flex;gap:6px;margin:4px 0 8px;flex-wrap:wrap}
.qs .tg button{font:700 13px/1 inherit;padding:7px 11px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
.qs .tg button.on{background:#3D3A35;color:#fff;border-color:#3D3A35}
.qs .lg{display:flex;gap:12px;font-size:12.5px;color:var(--muted);margin-bottom:2px}.qs .lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.qs svg{display:block;width:100%;max-width:560px;height:auto;margin:0 auto}.qs svg text{font:600 11px/1 system-ui,sans-serif;fill:var(--muted)}
.qs table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px;font-variant-numeric:tabular-nums}
.qs th{background:#3D3A35;color:#fff;font-weight:700;padding:5px 4px}.qs td{padding:5px 4px;border-bottom:1px solid var(--line);text-align:right}.qs td:first-child{text-align:left;white-space:nowrap}
.qs tr.pre td{background:var(--soft);font-weight:700}
.qs .vt{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px}.qs .vt>div{background:var(--bg);border-radius:10px;padding:7px 4px;text-align:center}
.qs .vt small{display:block;font-size:11.5px;color:var(--muted);font-weight:700;word-break:keep-all}.qs .vt b{display:block;font-size:18px;font-variant-numeric:tabular-nums}
.qs p{margin:8px 0 0;font-size:12.5px;color:var(--muted);line-height:1.6}
@media (max-width:520px){.qs .vt{grid-template-columns:repeat(2,1fr)}}
.ck .pre{font-size:12.5px;line-height:1.9}.ck .pre button{font:700 12.5px/1 inherit;padding:5px 9px;border-radius:99px;border:1px solid #F2A900;background:#FBE7B0;color:#3D3A35;cursor:pointer;margin:0 4px 0 0}
.fwd{margin-top:10px;border:2px solid var(--accent);border-radius:12px;padding:10px 12px}
.fwd h4{margin:0 0 8px;font-size:14.5px}.fwd .tl{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.fwd .tl>div{background:var(--bg);border-radius:10px;padding:8px 6px;text-align:center}.fwd .tl small{display:block;font-size:12px;color:var(--muted);font-weight:700}
.fwd .tl b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.fwd .tl i{display:block;font-style:normal;font-size:12px;color:var(--muted)}
.fwd p{margin:8px 0 0;font-size:13px;color:var(--muted);line-height:1.6}
.sig b{display:block;font-size:14.5px}.sig span{font-size:13.5px;color:var(--muted)}
.verdict{font-size:16px;font-weight:800;padding:10px 12px;border-radius:10px}
.verdict.g{background:var(--ok-bg);color:var(--ok)}.verdict.y{background:var(--warn-bg);color:var(--warn)}.verdict.r{background:var(--bad-bg);color:var(--bad)}
.saved{display:flex;flex-direction:column;gap:6px}
.saved .it{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:14px;border-top:1px solid var(--line);padding-top:6px}
.saved .it .when{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
/* 공통 버튼 */
.sb{font:inherit;font-size:14px;font-weight:700;padding:8px 13px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;white-space:nowrap}
.sb.gh{background:transparent;color:var(--accent)}
.sb.sm{font-size:12.5px;padding:4px 9px;border-radius:7px}
.sb.del{border-color:var(--bad);color:var(--bad);background:transparent}
.row-btn{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.msg{font-size:13px;color:var(--ok)}
/* 업종 */
.ind{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.ind summary{list-style:none;cursor:pointer;padding:11px 14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ind summary::-webkit-details-marker{display:none}
.ind summary b{font-size:16px}
.ind .wp{font-size:12.5px;font-weight:700;color:var(--bad);background:var(--bad-bg);padding:2px 8px;border-radius:6px}
.ind .cv{margin-left:auto;color:var(--muted);transition:transform .15s}.ind[open] .cv{transform:rotate(90deg)}
.ind .bd{padding:0 14px 12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px}
.ind dl{margin:0;min-width:0}.ind dt{font-size:12px;font-weight:800;color:var(--accent)}.ind dd{margin:0;font-size:14px}
.ind dl.trap dt{color:var(--bad)}
.ind .ft{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
/* 용어 */
.srch{display:flex;gap:8px}
.srch input{font-size:16px;padding:10px 12px;border-radius:10px}
.chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:3px}
.chip{font:inherit;font-size:13px;padding:4px 10px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:var(--muted);cursor:pointer;white-space:nowrap}
.chip[aria-pressed=true]{background:var(--soft);border-color:var(--accent);color:var(--text);font-weight:700}
.chip i{font-style:normal;opacity:.7;margin-left:3px;font-size:12px;font-variant-numeric:tabular-nums}
.cnt{font-size:13px;color:var(--muted)}
.list{display:flex;flex-direction:column;gap:9px}
.tm{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:5px;min-width:0}
.tm.mine{border-color:var(--mine)}
.tm .hd{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.tm .hd b{font-size:16.5px}.tm .en{font-size:13px;color:var(--muted)}
.tm .ct{margin-left:auto;font-size:11.5px;font-weight:700;padding:1px 8px;border-radius:99px;background:var(--soft);white-space:nowrap}
.tm .ct.mine{background:transparent;border:1px solid var(--mine);color:var(--mine)}
.tm p{margin:0;font-size:14.5px}
.tm .fx{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;background:var(--bg);border:1px dashed var(--line);border-radius:8px;padding:5px 9px;overflow-x:auto;white-space:nowrap}
.tm .pt{font-size:14px;color:var(--muted)}.tm .pt b{color:var(--text)}
.tm .acts{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}
.st mark{background:var(--mark);color:inherit;border-radius:3px}
.empty{padding:22px 14px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:12px}
/* 사례 */
.cs .meta2{font-size:13px;color:var(--muted)}
.cs .cell{font-size:13px;font-weight:700;color:var(--accent)}
.cs .ls{background:var(--soft);border-radius:8px;padding:7px 10px;font-size:14.5px}
.cs .ls b{color:var(--accent)}
.cs .srcs{font-size:12.5px;color:var(--muted)}
/* 추가 창 */
.qz-modes{display:flex;gap:6px;flex-wrap:wrap}
.qz-stat{font-size:13px;color:var(--muted)}
.qz{gap:12px}
.qz .pg{display:flex;justify-content:space-between;gap:8px;font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.qz .bar{height:4px;border-radius:2px;background:var(--line);overflow:hidden}.qz .bar i{display:block;height:100%;background:var(--accent)}
.qz h3{font-size:17.5px;line-height:1.5;margin:0}
.qz .ch{display:flex;flex-direction:column;gap:8px}
.qz .ch button{font:inherit;font-size:15px;text-align:left;padding:11px 13px;border-radius:10px;border:1.5px solid var(--line);background:var(--bg);color:var(--text);cursor:pointer;display:flex;gap:10px;align-items:flex-start}
.qz .ch button b{flex:none;width:22px;height:22px;border-radius:50%;background:var(--card);border:1px solid var(--line);font-size:12px;display:grid;place-items:center}
.qz .ch button:hover:not(:disabled){border-color:var(--accent)}
.qz .ch button:disabled{cursor:default}
.qz .ch button.ok{border-color:var(--ok);background:var(--ok-bg)}.qz .ch button.ok b{background:var(--ok);color:#fff;border-color:var(--ok)}
.qz .ch button.no{border-color:var(--bad);background:var(--bad-bg)}.qz .ch button.no b{background:var(--bad);color:#fff;border-color:var(--bad)}
.qz .ex{border-radius:10px;padding:10px 12px;background:var(--soft);font-size:14.5px;display:flex;flex-direction:column;gap:6px}
.qz .ex .vd{font-weight:800}.qz .ex .vd.ok{color:var(--ok)}.qz .ex .vd.no{color:var(--bad)}
.qz .end{display:flex;flex-direction:column;gap:10px;align-items:flex-start}
.qz .big{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--accent)}
.qz .wl{margin:0;padding-left:18px;font-size:14px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
.sheet{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:flex-end;justify-content:center;z-index:10000;padding:12px 12px calc(12px + env(safe-area-inset-bottom,0px))}
.sheet form{background:var(--card);color:var(--text);border-radius:14px;padding:16px;width:100%;max-width:560px;display:flex;flex-direction:column;gap:9px;max-height:92vh;overflow:auto}
.sheet h3{margin:0;font-size:17px}
.sheet label{display:flex;flex-direction:column;gap:3px;font-size:12.5px;font-weight:700;color:var(--muted)}
.sheet .two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.sheet .note{font-size:12.5px;color:var(--muted)}
@media (max-width:720px){.ck{grid-template-columns:minmax(0,1fr)}.ck>.panel[aria-live]{order:0}.ck>.panel:not(.nm):not([aria-live]){order:1}.ind .bd{grid-template-columns:minmax(0,1fr)}}
@media (max-width:340px){.ck .f,.sheet .two{grid-template-columns:minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){.ind .cv{transition:none}}
"""

HOW = """
<div class="st-p" role="tabpanel" id="p-how" aria-labelledby="t-how">
<p class="st-lede">재무제표는 "좋은 종목 찾는 도구"보다 <b>사면 안 되는 종목을 거르고, 고른 종목이 지금 어디쯤 있는지 확인하는 도구</b>로 쓸 때 가장 쓸모가 큽니다. 아래 다섯 가지 순서로 씁니다.</p>
<div class="how">
 <div class="panel"><div class="k">활용 1 · 사기 전</div><h3>지뢰 거르기</h3>
  <p>다섯 가지 중 하나라도 걸리면 일단 보류합니다.</p>
  <ul><li>감사의견이 적정이 아니다</li><li>영업이익은 흑자인데 영업현금흐름이 2년 넘게 적자</li><li>이자보상배율 1배 미만</li><li>매출채권·계약자산·재고가 매출보다 훨씬 빨리 는다</li><li>CB·유상증자가 잦다 (코스닥이면 법차손 요건까지)</li></ul>
  <div class="use">쓰는 곳: 고객이 테마주를 물어볼 때, 관심 종목에 넣기 전</div>
  <button class="go" type="button" data-go="check">5분 체크로 해 보기 ›</button></div>
 <div class="panel"><div class="k">활용 2 · 뉴스를 봤을 때</div><h3>테마 검증</h3>
  <p>종목이 뉴스에 엮이면 사업보고서 「사업의 내용」에서 그 사업의 <b>매출 비중, 수주잔고, 주요 고객</b>을 확인합니다. 매출 비중이 5%도 안 되면 테마일 뿐입니다.</p>
  <div class="use">쓰는 곳: 장중 급등 종목, 실적발표 종목 메뉴</div></div>
 <div class="panel"><div class="k">활용 3 · 가격 판단</div><h3>업종에 맞는 지표로 위치 보기</h3>
  <div class="eq">PBR = ROE × PER</div>
  <ul><li>금융: ROE 대비 PBR</li><li>반도체·화학 같은 사이클주: PBR 밴드 (이익 정점에서 PER이 가장 낮다)</li><li>성장주: PEG, 이익 성장의 기울기</li><li>수주산업: 수주잔고와 잔고의 마진</li></ul>
  <div class="use">쓰는 곳: 목표주가 변동 메뉴의 상향·하향을 볼 때</div>
  <button class="go" type="button" data-go="ind">업종별 체크리스트 ›</button></div>
 <div class="panel"><div class="k">활용 4 · 팔 때</div><h3>성장이 꺾이는 신호</h3>
  <p>"PER이 높을 때"가 아니라 "성장이 꺾일 때" 판다. 재무제표에서 먼저 보이는 신호입니다.</p>
  <ul><li>재고자산회전일수가 늘어난다</li><li>CAPEX가 감가상각비의 2배 넘는 상태가 이어진다 (업계 증설 경쟁)</li><li>매출총이익률이 꺾인다</li><li>컨센서스 EPS가 내려간다</li></ul>
  <div class="use">쓰는 곳: 보유 종목 점검, 반도체 사이클 매도 전략</div></div>
 <div class="panel"><div class="k">활용 5 · 실적 시즌</div><h3>실적 1장 요약</h3>
  <ul><li>컨센서스 대비 결과</li><li>일회성 손익을 빼고 남는 이익</li><li>영업현금흐름이 이익을 따라왔는가</li></ul>
  <p>배운 점은 사례노트에 남깁니다. 다음 분기, 다음 종목에서 그대로 쓰입니다.</p>
  <div class="use">쓰는 곳: 장마감 리포트, 블로그 글</div>
  <button class="go" type="button" data-go="case">사례노트 ›</button></div>
</div>
<h2>기본기</h2>
<div class="how">
 <div class="panel"><h3>세 표의 연결</h3>
  <ol><li>순이익은 재무상태표의 이익잉여금으로 쌓인다</li><li>감가상각비는 손익에선 비용, 현금흐름표에선 다시 더한다</li><li>매출채권·재고·매입채무 증감이 영업현금흐름을 조정한다</li></ol>
  <p><b>현금흐름 부호(영업·투자·재무)</b><br>+ − − 우량 성숙기업 · + − + 투자 확대 성장기업 · − − + 바이오·초기기업 (런웨이 확인) · − + + 본업 적자를 자산매각·차입으로 메우는 위험 신호</p></div>
 <div class="panel"><h3>DART 사업보고서 읽는 순서</h3>
  <ol><li>감사의견과 핵심감사사항(KAM)</li><li>사업의 내용 (생산능력·수주·가격)</li><li>요약재무정보로 3~5년 추세</li><li>이사의 경영진단(MD&amp;A)</li><li>연결재무제표 본문</li><li>연결 주석: 부문정보·수익 분해·차입금·특수관계자·우발부채</li><li>별도재무제표: 배당가능이익</li></ol></div>
 <div class="panel"><h3>2027년부터 바뀌는 영업이익 (K-IFRS 1118)</h3>
  <p>2027년 1월 1일 이후 시작하는 회계연도부터 손익을 영업·투자·재무·법인세·중단영업으로 나눕니다. 2026년 실적도 비교용으로 다시 작성됩니다.</p>
  <ul><li>2027~2029년엔 옛 기준 영업이익을 주석에 따로 공시. HTS·컨센서스 숫자가 어느 기준인지 먼저 확인</li><li>EBITDA 같은 회사 정의 지표(MPM)는 주석에 정의와 조정내역 공시</li><li>리스부채 이자는 재무 범주로. 항공·유통·해운 영업이익 구성이 달라질 수 있음</li></ul></div>
 <div class="panel"><h3>출발점이 된 영상</h3>
  <p>삼쩜삼캠퍼스 「PER, PBR 다 따졌는데, 왜 내 돈은 물릴까요?」 (2026-10-20)</p>
  <ul><li>PER은 이익 성장의 기울기와 영업현금흐름을 같이 본다</li><li>저PBR은 "이유를 물어라"는 신호: 흑자인가 → 부실 위험이 낮은가 → 주주환원을 하는가</li><li>ROE는 부채로 부풀 수 있어 ROA도 함께. PEG는 저성장 기업에서 왜곡</li></ul>
  <p style="font-size:12.5px;color:var(--muted)">자동자막 기반 정리라 숫자 예시는 원본 확인 필요 · <a href="https://www.youtube.com/watch?v=XDlxzauU1GE" target="_blank" rel="noopener">영상 보기</a></p></div>
</div>
</div>"""

CHECK = """
<div class="st-p" role="tabpanel" id="p-check" aria-labelledby="t-check" hidden>
<p class="st-lede">종목명을 넣고 <b>불러오기</b>를 누르면 DART에 낸 가장 최근 분기 보고서 숫자가 채워지고, 지뢰 다섯 가지를 신호등으로 보여 줍니다. 숫자는 직접 고쳐 넣어도 됩니다. 금융업(은행·보험·증권)은 구조가 달라 이 체크가 맞지 않습니다. 단위는 <b>억원</b>.</p>
<div class="ck">
 <div class="panel nm">  <div class="nmin"><label for="c-name">종목명 · 회사명이나 종목코드를 넣으면 최근 분기 숫자를 불러옵니다</label>
   <div class="nmrow"><input id="c-name" value="예시 기업" list="c-list" autocomplete="off" enterkeyhint="search"><button class="sb" type="button" id="ckLoad">불러오기</button></div>
   <datalist id="c-list"></datalist><div class="pre" id="ckPre"></div><div class="src" id="ckSrc" aria-live="polite"></div></div>
 </div>
 <div class="panel">
  <div class="ex" id="ckEx">처음 보이는 숫자는 사용법을 보여 주는 가상의 예시입니다. 종목 숫자로 바꿔 넣으세요.</div>
  <form class="f" id="ckF" autocomplete="off">
   <label class="full" for="c-audit">최근 감사의견<select id="c-audit"><option value="ok">적정</option><option value="q">한정</option><option value="bad">부적정·의견거절</option><option value="na">확인 필요</option></select></label>
   <div class="sep" id="sepPL">손익·현금흐름 (올해 = 최근 4개 분기 합 또는 최근 사업연도)</div>
   <label for="c-rev1">매출 · 올해<input id="c-rev1" inputmode="decimal" value="5200"></label>
   <label for="c-rev0">매출 · 작년<input id="c-rev0" inputmode="decimal" value="4300"></label>
   <label for="c-op1">영업이익 · 올해<input id="c-op1" inputmode="decimal" value="410"></label>
   <label for="c-op0">영업이익 · 작년<input id="c-op0" inputmode="decimal" value="300"></label>
   <label for="c-cf1">영업현금흐름 · 올해<input id="c-cf1" inputmode="decimal" value="-60"></label>
   <label for="c-cf0">영업현금흐름 · 작년<input id="c-cf0" inputmode="decimal" value="120"></label>
   <label class="full" for="c-int">이자비용 · 올해<input id="c-int" inputmode="decimal" value="95"></label>
   <div class="sep" id="sepBS">재무상태표 (기말 잔액)</div>
   <label for="c-ar1">매출채권+계약자산 · 올해<input id="c-ar1" inputmode="decimal" value="2100"></label>
   <label for="c-ar0">매출채권+계약자산 · 작년<input id="c-ar0" inputmode="decimal" value="1350"></label>
   <label for="c-inv1">재고자산 · 올해<input id="c-inv1" inputmode="decimal" value="900"></label>
   <label for="c-inv0">재고자산 · 작년<input id="c-inv0" inputmode="decimal" value="760"></label>
   <div class="sep">자금 조달 · 상장 요건</div>
   <label for="c-cb">최근 2년 CB·BW·유상증자 횟수<input id="c-cb" inputmode="numeric" value="2"></label>
   <label for="c-mkt">시장<select id="c-mkt"><option value="kospi">코스피</option><option value="kosdaq" selected>코스닥</option></select></label>
   <label for="c-ebt">법인세차감전손실(손실이면 양수)<input id="c-ebt" inputmode="decimal" value="0"></label>
   <label for="c-eq">자기자본<input id="c-eq" inputmode="decimal" value="2600"></label>
   <div class="sep">가격 위치 (두 개만 넣어도 나머지를 계산)</div>
   <label for="c-roe">ROE(%)<input id="c-roe" inputmode="decimal" value="12"></label>
   <label for="c-per">PER(배)<input id="c-per" inputmode="decimal" value="9"></label>
   <label for="c-pbr">PBR(배)<input id="c-pbr" inputmode="decimal" value=""></label>
   <label for="c-type">업종 성격<select id="c-type"><option value="gen">일반 제조·소비재</option><option value="cyc">경기민감 (반도체·화학·철강·해운)</option><option value="gro">성장주 (플랫폼·SaaS·바이오)</option><option value="ord">수주산업 (조선·건설·방산·전력기기)</option></select></label>
   <div class="sep">예상 PER·PBR (내년 영업이익을 넣으면 계산)</div>
   <label for="c-fop">내년 영업이익(예상)<input id="c-fop" inputmode="decimal" value="" placeholder="예: 증권사 컨센서스"></label>
   <label for="c-nr">순이익 ÷ 영업이익(%)<input id="c-nr" inputmode="decimal" value="78"></label>
   <label class="full" for="c-mcap">시가총액<input id="c-mcap" inputmode="decimal" value=""></label>
  </form>
 </div>
 <div class="panel" aria-live="polite">
  <div class="verdict" id="ckV"></div>
  <div id="ckS"></div>
  <div class="qs" id="ckQ" hidden></div>
  <div class="fwd" id="ckFwd" hidden></div>
  <div class="row-btn"><button class="sb" type="button" id="ckSave">이 결과 저장</button><button class="sb gh" type="button" id="ckReset">빈칸으로 시작</button><span class="msg" id="ckMsg"></span></div>
  <div class="saved" id="ckList"></div>
 </div>
</div>
</div>"""

IND = """
<div class="st-p" role="tabpanel" id="p-ind" aria-labelledby="t-ind" hidden>
<p class="st-lede">업종마다 이익이 가장 크게 왜곡되는 칸이 정해져 있습니다. 빨간 꼬리표가 그 칸입니다. 카드를 열어 먼저 볼 칸 → 핵심 지표 → 함정 → 밸류에이션 순으로 확인하세요.</p>
<div id="indL" class="st-p"></div>
</div>"""

TERMS = """
<div class="st-p" role="tabpanel" id="p-term" aria-labelledby="t-term" hidden>
<div class="srch"><input id="q" type="search" placeholder="용어·영문·계산식 검색 (예: CSM, 미청구, ROE)" aria-label="용어 검색"><button class="sb" type="button" id="addT">+ 용어</button></div>
<div class="chips" id="chips" role="group" aria-label="분류"></div>
<div class="cnt" id="cnt"></div>
<div class="list" id="tL"></div>
</div>"""

CASES = """
<div class="st-p" role="tabpanel" id="p-case" aria-labelledby="t-case" hidden>
<p class="st-lede">실제 종목에서 "이 칸을 봤더니 이랬다"를 남기는 곳입니다. 용어를 외우는 것보다 사례가 실전에 오래 남습니다.</p>
<div class="srch"><input id="cq" type="search" placeholder="종목·업종·칸 검색" aria-label="사례 검색"><button class="sb" type="button" id="addC">+ 사례</button></div>
<div class="list" id="cL"></div>
</div>"""

QUIZ = """
<div class="st-p" role="tabpanel" id="p-quiz" aria-labelledby="t-quiz" hidden>
<p class="st-lede">실전 문제는 지뢰 거르기·밸류에이션·업종별 사례에서, 실제 종목 문제는 DART·KB증권 숫자로 그 자리에서 만들고, 용어 문제는 용어사전에서 나옵니다. 틀린 문제는 이 기기에 모아 두었다가 다시 풀 수 있습니다.</p>
<div class="qz-modes" role="group" aria-label="문제 고르기">
 <button class="sb" type="button" data-qm="real">실전 10문제</button>
 <button class="sb gh" type="button" data-qm="co">실제 종목 10문제</button>
 <button class="sb gh" type="button" data-qm="term">용어 10문제</button>
 <button class="sb gh" type="button" data-qm="mix">섞어서 10문제</button>
 <button class="sb gh" type="button" data-qm="wrong" id="qzWrongBtn">틀린 문제 다시</button>
</div>
<div class="qz-stat" id="qzStat"></div>
<div class="panel qz" id="qz" aria-live="polite"></div>
</div>"""

SHEET = """
<div class="sheet" id="sh" hidden><form id="shF" autocomplete="off"></form></div>"""

JS = r"""
<script>
(function(){
var T=__TERMS__, I=__IND__, C=__CASES__;
var $=function(s){return document.querySelector(s)};
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function lsGet(k){try{return JSON.parse(localStorage.getItem(k)||'[]')}catch(e){return []}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));return true}catch(e){return false}}
function copy(text,btn){
  function done(ok){var o=btn.textContent;btn.textContent=ok?'복사됨 · Claude 대화창에 붙여넣기':'복사 안 됨: 아래 글을 직접 선택해 복사';setTimeout(function(){btn.textContent=o},2600)}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(function(){done(true)},function(){fallback()})}else fallback();
  function fallback(){var t=document.createElement('textarea');t.value=text;t.style.cssText='width:100%;min-height:120px;margin-top:6px';btn.insertAdjacentElement('afterend',t);t.select();try{done(document.execCommand('copy'))}catch(e){done(false)}}
}

/* ---- 탭 ---- */
var TABS=['how','check','ind','term','case','quiz'];
function show(id){
  TABS.forEach(function(t){var on=t===id;$('#t-'+t).setAttribute('aria-selected',on);$('#p-'+t).hidden=!on});
  try{localStorage.setItem('st-tab',id)}catch(e){}
  if(history.replaceState)history.replaceState(null,'','#'+id);
}
TABS.forEach(function(t){$('#t-'+t).addEventListener('click',function(){show(t)})});
document.querySelectorAll('[data-go]').forEach(function(b){b.addEventListener('click',function(){show(b.dataset.go);scrollTo(0,0)})});
var h=location.hash.slice(1),st0;try{st0=localStorage.getItem('st-tab')}catch(e){}
show(TABS.indexOf(h)>=0?h:(TABS.indexOf(st0)>=0?st0:'how'));

/* ---- 5분 체크 ---- */
function n(id){var v=($('#'+id).value||'').replace(/,/g,'').trim();if(v==='')return null;v=parseFloat(v);return isFinite(v)?v:null}
function g(a,b){return a!=null&&b!=null&&b!==0?(a-b)/Math.abs(b)*100:null}
function pct(v){return (v>0?'+':'')+v.toFixed(0)+'%'}
var LV={g:'통과',y:'주의',r:'위험',n:'입력 필요'};
function check(){
  var s=[],a=$('#c-audit').value;
  if(a==='na')s.push(['n','감사의견','DART에서 감사의견을 찾지 못했습니다. 최근 사업보고서의 감사보고서에서 확인하세요']);else
  s.push(a==='ok'?['g','감사의견','적정. 최소 조건은 통과']:a==='q'?['y','감사의견','한정. 사유(범위제한·회계기준 위반)를 감사보고서에서 확인. 유가증권시장은 2년 연속 범위제한 한정이면 상장폐지 사유']:['r','감사의견','부적정·의견거절은 상장폐지 사유. 매매 대상에서 제외']);
  var op1=n('c-op1'),op0=n('c-op0'),cf1=n('c-cf1'),cf0=n('c-cf0');
  if(op1==null||cf1==null)s.push(['n','이익 vs 현금','영업이익과 영업현금흐름을 넣어 주세요']);
  else{var bad1=op1>0&&cf1<0,bad0=op0!=null&&cf0!=null&&op0>0&&cf0<0,r=op1>0?cf1/op1:null;
    if(bad1&&bad0)s.push(['r','이익 vs 현금','2년 연속 영업이익 흑자 · 영업현금흐름 적자. 이익이 현금으로 안 들어온다. 매출채권·재고·계약자산 주석 확인']);
    else if(bad1)s.push(['y','이익 vs 현금','올해 영업이익 '+op1+' · 영업현금흐름 '+cf1+'. 한 해는 운전자본 때문일 수 있다. 다음 분기 확인']);
    else if(r!=null&&r<0.5)s.push(['y','이익 vs 현금','영업현금흐름이 영업이익의 '+(r*100).toFixed(0)+'%. 이익의 질이 낮은 편']);
    else s.push(['g','이익 vs 현금',op1>0?'영업현금흐름이 영업이익의 '+(r*100).toFixed(0)+'%':'영업적자 기업. 흑자 전환 시점과 현금 잔고를 따로 본다'])}
  var it=n('c-int');
  if(op1==null||it==null)s.push(['n','이자보상배율','영업이익과 이자비용을 넣어 주세요']);
  else if(it<=0)s.push(['g','이자보상배율','이자비용 없음']);
  else{var icr=op1/it;s.push([icr<1?'r':icr<3?'y':'g','이자보상배율',icr.toFixed(1)+'배 (영업이익 ÷ 이자비용). '+(icr<1?'영업이익으로 이자도 못 낸다. 3년 연속이면 한계기업':icr<3?'금리가 오르면 버티기 어렵다':'이자 부담 낮음')])}
  var gr=g(n('c-rev1'),n('c-rev0')),ga=g(n('c-ar1'),n('c-ar0')),gi=g(n('c-inv1'),n('c-inv0'));
  if(gr==null||(ga==null&&gi==null))s.push(['n','채권·재고 vs 매출','매출과 매출채권·재고를 두 해 모두 넣어 주세요']);
  else{var rel=function(x){return x==null?-1e9:((1+x/100)/Math.max(1+gr/100,0.01)-1)*100};  /* 매출 대비 몇 % 더 빨리 늘었나 (고성장 회사도 공정하게) */
    var gap=Math.max(rel(ga),rel(gi)),parts=['매출 '+pct(gr)];if(ga!=null)parts.push('채권·계약자산 '+pct(ga));if(gi!=null)parts.push('재고 '+pct(gi));
    s.push([gap>25?'r':gap>10?'y':'g','채권·재고 vs 매출',parts.join(' · ')+'. '+(gap>25?'매출보다 훨씬 빨리 는다. 못 받은 돈·안 팔린 물건이 쌓이는 중':gap>10?'매출보다 빨리 는다. 다음 분기에 줄어드는지 확인':'매출과 비슷한 속도')])}
  var cb=n('c-cb'),mkt=$('#c-mkt').value,ebt=n('c-ebt'),eq=n('c-eq'),lv='g',tx=[];
  if(cb!=null){if(cb>=3){lv='r';tx.push('2년간 '+cb+'번 조달. 지분 희석과 오버행 부담')}else if(cb>=1){lv='y';tx.push('2년간 '+cb+'번 조달. 전환가·잔액·리픽싱 조건 확인')}else tx.push('최근 2년 조달 없음')}
  if(mkt==='kosdaq'&&ebt!=null&&ebt>0&&eq){var lr=ebt/eq*100;if(lr>50){lv='r';tx.push('법차손이 자기자본의 '+lr.toFixed(0)+'%. 3년 중 2번이면 관리종목')}else if(lr>30){if(lv==='g')lv='y';tx.push('법차손이 자기자본의 '+lr.toFixed(0)+'%. 50% 넘으면 관리종목 요건')}}
  s.push(cb==null?['n','자금 조달','CB·BW·유상증자 횟수를 넣어 주세요']:[lv,'자금 조달',tx.join('. ')]);
  var reds=s.filter(function(x){return x[0]==='r'}).length,ys=s.filter(function(x){return x[0]==='y'}).length;
  var v=reds?['r','보류 · 위험 '+reds+'개']:ys?['y','주의 '+ys+'개 · 주석 확인 후 판단']:['g','지뢰 5개 통과'];
  /* 가격 위치 */
  var roe=n('c-roe'),per=n('c-per'),pbr=n('c-pbr'),tp=$('#c-type').value,pv='';
  var all3=roe!=null&&per!=null&&pbr!=null&&per>0;
  if(pbr==null&&roe!=null&&per!=null)pbr=roe/100*per;else if(per==null&&roe&&pbr!=null)per=pbr/(roe/100);else if(roe==null&&per&&pbr!=null)roe=pbr/per*100;
  if(roe!=null&&per!=null&&pbr!=null){
    var base;
    if(all3){var ir=pbr/per*100,gp=roe-ir;
      base='ROE '+roe.toFixed(1)+'% · PER '+per.toFixed(1)+'배 · PBR '+pbr.toFixed(2)+'배. PBR ÷ PER로 거꾸로 구한 ROE는 '+ir.toFixed(1)+'%'
        +(Math.abs(gp)>=3?(gp>0?' → 최근 ROE가 PER 기준 이익(지난 실적)보다 높다. 이익이 늘고 있어 PER이 실제보다 높아 보일 수 있다. ':' → 최근 ROE가 PER 기준 이익보다 낮다. 이익이 줄고 있어 PER이 실제보다 낮아 보일 수 있다. '):'로 비슷하다. ');}
    else base='ROE '+roe.toFixed(1)+'% × PER '+per.toFixed(1)+'배 = PBR '+pbr.toFixed(2)+'배. ';
    var tip={gen:roe<8&&pbr<1?'ROE가 낮아 PBR이 낮은 것. 싸다기보다 이유가 있다. 주주환원·자산 가치 확인':roe>=12&&per<10?'수익성 대비 낮은 PER. 이익이 지속 가능한지(일회성·사이클) 확인':'ROE가 유지된다는 전제의 값. ROE 추세를 3년 본다',
      cyc:per<8?'경기민감주의 낮은 PER은 이익 정점일 수 있다. PER보다 PBR 밴드 위치를 본다':'PER보다 PBR 밴드 위치와 제품 가격 방향을 본다',
      gro:'PER보다 이익 성장의 기울기(PEG = PER ÷ EPS 증가율)를 본다. 성장이 꺾이면 높은 PER이 한 번에 깎인다',
      ord:'수주잔고의 마진이 이익으로 바뀌는 속도를 본다. 계약자산이 늘면 PER의 E를 의심'}[tp];
    pv=base+tip}
  $('#ckV').className='verdict '+v[0];$('#ckV').textContent=($('#c-name').value||'이 종목')+' · '+v[1];
  $('#ckS').innerHTML=s.map(function(x){return '<div class="sig"><span class="dot '+x[0]+'">'+LV[x[0]]+'</span><div><b>'+esc(x[1])+'</b><span>'+esc(x[2])+'</span></div></div>'}).join('')
    +(pv?'<div class="sig"><span class="dot n">위치</span><div><b>가격 위치</b><span>'+esc(pv)+'</span></div></div>':'');
  fwd(per,pbr);renderQ();
  return {v:v,s:s,pv:pv};
}
/* 예상 PER·PBR: 내년 영업이익 × (순이익 ÷ 영업이익) = 예상 순이익. 시가총액 ÷ 예상 순이익 = 예상 PER,
   시가총액 ÷ (지금 자기자본 + 예상 순이익) = 예상 PBR (배당·자사주는 빼고 이익이 그대로 자본에 쌓인다는 가정) */
var CUR=null,MDATE='';
/* ---- 분기 실적: 네이버 분기 표(q/<코드>.json, 하루 한 번) + 오늘 나온 잠정실적(kb earnings-live kr_prelim, 10분마다) ---- */
var PRE_URL='https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json',PREP=null,QS={mode:'qoq'};
function prelims(){if(!PREP)PREP=fetch(PRE_URL+'?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():{}}).then(function(j){return j.kr_prelim||{}}).catch(function(){return {}});return PREP}
prelims().then(function(P){var td=new Date(Date.now()+9*36e5),ago=new Date(td-3*864e5).toISOString().slice(0,10);
 var L=Object.keys(P).map(function(k){return P[k]}).filter(function(x){return x.day>=ago}).sort(function(a,b){return a.rcp<b.rcp?1:-1}).slice(0,12);
 if(L.length)$('#ckPre').innerHTML='📢 최근 잠정실적 발표: '+L.map(function(x){return '<button type="button" data-pre="'+esc(x.name)+'">'+esc(x.name)+' <small>'+esc(x.day.slice(5).replace('-','/'))+'</small></button>'}).join('')});
$('#ckPre').addEventListener('click',function(e){var b=e.target.closest('[data-pre]');if(!b)return;$('#c-name').value=b.dataset.pre;loadCo()});
function qkey(k,dq){var y=+k.slice(0,4),m=+k.slice(5,7)+dq*3;while(m>12){m-=12;y++}while(m<1){m+=12;y--}return y+'.'+('0'+m).slice(-2)}
function quarters(qj,pre){/* [{k, r(매출), o(영업이익), n(순이익), p(잠정), c(컨센서스 값 {r,o})}] 오래된 것부터 */
 var M={},cons={};((qj&&qj.q)||[]).forEach(function(x){if(x[4])cons[x[0]]={r:x[1],o:x[2],n:x[3]};else M[x[0]]={k:x[0],r:x[1],o:x[2],n:x[3]}});
 if(pre&&pre.q){var put=function(k,i,src){if(!M[k]||src)M[k]={k:k,r:pre.sales[i],o:pre.op[i],n:pre.net[i],p:!!src}};
  put(pre.q,0,1);put(qkey(pre.q,-1),1);put(qkey(pre.q,-4),2);if(cons[pre.q])M[pre.q].c=cons[pre.q]}
 return Object.keys(M).sort().map(function(k){return M[k]}).filter(function(x){return x.r!=null||x.o!=null})}
function gr(a,b){if(a==null||b==null)return null;if(b<=0)return a>0?'흑전':a<0?'적지':null;if(a<0)return '적전';return (a/b-1)*100}
function qsvg(Q,mode){var rows=Q.map(function(x,i){var b=mode==='qoq'?Q[i-1]:Q.filter(function(y){return y.k===qkey(x.k,-4)})[0];
  return {k:x.k,p:x.p,r:b?gr(x.r,b.r):null,o:b?gr(x.o,b.o):null}}).filter(function(x){return x.r!=null||x.o!=null});
 if(!rows.length)return {svg:'<p>'+(mode==='yoy'?'1년 전 같은 분기 숫자가 없어 전년 동기 대비를 그릴 수 없습니다.':'증가율을 그릴 분기가 부족합니다.')+'</p>',rows:rows};
 var nums=[];rows.forEach(function(x){[x.r,x.o].forEach(function(v){if(typeof v==='number')nums.push(v)})});
 var cap=function(v){return Math.max(-150,Math.min(300,v))},hi=Math.max(10,Math.max.apply(null,nums.map(cap).concat([0]))),lo=Math.min(0,Math.min.apply(null,nums.map(cap).concat([0])));
 var W=340,H=190,T=22,B=H-30,y=function(v){return T+(hi-cap(v))/(hi-lo)*(B-T)},y0=y(0),n=rows.length,gw=W/n,bw=Math.min(26,gw*0.32);
 var o='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="분기 매출액·영업이익 증가율"><line x1="0" x2="'+W+'" y1="'+y0+'" y2="'+y0+'" stroke="var(--line)" stroke-width="1.5"/>';
 rows.forEach(function(x,i){var cx=gw*i+gw/2;[[x.r,'#F2A900',-1],[x.o,'#3D3A35',1]].forEach(function(s){var v=s[0],bx=cx+(s[2]<0?-bw-1:1);
   if(typeof v==='number'){var yy=y(v),top=Math.min(yy,y0),h=Math.max(1,Math.abs(yy-y0));o+='<rect x="'+bx.toFixed(1)+'" y="'+top.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+'" rx="2" fill="'+s[1]+'"/>';
    o+='<text x="'+(bx+bw/2).toFixed(1)+'" y="'+(v>=0?top-4:top+h+11).toFixed(1)+'" text-anchor="middle" style="fill:'+(v>=0?'var(--up)':'var(--down)')+'">'+(Math.abs(v)>=100?Math.round(v):v.toFixed(1))+(Math.abs(v)>300?'↑':'')+'</text>'}
   else if(v)o+='<text x="'+(bx+bw/2).toFixed(1)+'" y="'+(y0-4)+'" text-anchor="middle">'+v+'</text>'});
  o+='<text x="'+cx.toFixed(1)+'" y="'+(H-12)+'" text-anchor="middle">'+x.k.slice(2).replace('.','.')+'</text>'+(x.p?'<text x="'+cx.toFixed(1)+'" y="'+(H-1)+'" text-anchor="middle" style="fill:#e03131">잠정</text>':'')});
 return {svg:o+'</svg>',rows:rows}}
function eok2(v){if(v==null)return '–';var a=Math.abs(v);return a>=10000?(v/10000).toLocaleString('ko-KR',{maximumFractionDigits:a>=100000?0:1})+'조':Math.round(v).toLocaleString('ko-KR')+'억'}
function renderQ(){var el=$('#ckQ'),S=QS.cur;if(!S||S.name!==$('#c-name').value){el.hidden=true;return}
 var Q=quarters(S.qj,S.pre);if(!Q.length){el.hidden=true;return}el.hidden=false;
 var g=qsvg(Q,QS.mode),last=Q[Q.length-1],pre=S.pre&&S.pre.q===last.k?S.pre:null;
 var h='<h4>📊 분기 실적 · '+esc(S.name)+'</h4>'+(pre?'<p style="margin:0 0 4px">📢 <b style="color:var(--text)">'+esc(pre.day)+' 잠정실적 반영</b> ('+esc(pre.consol?'연결':'별도')+', <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+esc(pre.rcp)+'" target="_blank" rel="noopener">DART 공시</a>)'
   +(last.c&&last.c.o?' · 영업이익 컨센서스 '+eok2(last.c.o)+' 대비 <b style="color:'+(last.o>=last.c.o?'var(--up)':'var(--down)')+'">'+((last.o/last.c.o-1)*100>0?'+':'')+((last.o/last.c.o-1)*100).toFixed(1)+'%</b>':'')+'</p>':'')
  +'<div class="tg"><button type="button" data-qm="qoq"'+(QS.mode==='qoq'?' class="on"':'')+'>전분기 대비</button><button type="button" data-qm="yoy"'+(QS.mode==='yoy'?' class="on"':'')+'>전년 동기 대비</button></div>'
  +'<div class="lg"><span><i style="background:#F2A900"></i>매출액 증가율(%)</span><span><i style="background:#3D3A35"></i>영업이익 증가율(%)</span></div>'+g.svg
  +'<table><tr><th>분기</th><th>매출액</th><th>영업이익</th><th>이익률</th></tr>'+Q.slice().reverse().map(function(x){return '<tr'+(x.p?' class="pre"':'')+'><td>'+esc(x.k)+(x.p?' 잠정':'')+'</td><td>'+eok2(x.r)+'</td><td>'+eok2(x.o)+'</td><td>'+(x.r>0&&x.o!=null?(x.o/x.r*100).toFixed(1)+'%':'–')+'</td></tr>'}).join('')+'</table>';
 /* 실적 발표 기준 PER·PBR·ROE: 시가총액 ÷ (최근 4분기 순이익 합 / 이번 분기 순이익 × 4), 자기자본은 최근 정기보고서 */
 var mc=n('c-mcap'),eq=n('c-eq'),act=Q.filter(function(x){return x.n!=null}),l4=act.slice(-4),ttm=l4.length===4?l4.reduce(function(s,x){return s+x.n},0):null,run=act.length?act[act.length-1].n*4:null;
 var ac=((S.qj&&S.qj.a)||[]).filter(function(x){return x[4]&&x[3]})[0];
 var f=function(v,d){return v==null||!isFinite(v)?'–':v.toFixed(d)},t=function(lab,v){return '<div><small>'+lab+'</small><b>'+v+'</b></div>'};
 if(mc){h+='<div class="vt">'+t('PER · 최근 4분기',ttm>0?f(mc/ttm,1)+'배':'–')+t('PER · 이번 분기×4',run>0?f(mc/run,1)+'배':'–')+t('PBR',eq>0?f(mc/eq,2)+'배':'–')+t('ROE · 최근 4분기',eq>0&&ttm!=null?f(ttm/eq*100,1)+'%':'–')+'</div>';
  h+='<p>시가총액 '+fmtEok(mc)+' 기준. 최근 4분기 순이익 합 '+(ttm!=null?fmtEok(ttm)+' ('+l4[0].k+'~'+l4[3].k+')':'– (4분기 자료 부족)')+' · 이번 분기('+esc(act.length?act[act.length-1].k:'')+') 순이익 × 4 = '+(run!=null?fmtEok(run):'–')+'(연환산 가정)'
   +(ac?' · 올해('+esc(ac[0])+') 컨센서스 순이익 '+fmtEok(ac[3])+' 기준 PER '+f(mc/ac[3],1)+'배':'')+'. PBR·ROE의 자기자본은 최근 정기보고서 값입니다.</p>'}
 h+='<p>자료: 네이버 증권 분기 실적(하루 한 번)'+(pre?' + DART 잠정실적 공시(발표 뒤 10분 안에 반영)':'')+'. 잠정실적은 확정 전 숫자입니다.</p>';
 el.innerHTML=h}
$('#ckQ').addEventListener('click',function(e){var b=e.target.closest('[data-qm]');if(!b)return;QS.mode=b.dataset.qm;renderQ()});
function loadQ(code,name){QS.cur=null;$('#ckQ').hidden=true;
 Promise.all([fetch('q/'+code+'.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null}).catch(function(){return null}),prelims()]).then(function(a){
  QS.cur={name:name,qj:a[0],pre:a[1][code]||null};var Q=quarters(a[0],QS.cur.pre),last=Q[Q.length-1];
  var l4=Q.filter(function(x){return x.n!=null}).slice(-4);QS.cur.ttm=l4.length===4?l4.reduce(function(s,x){return s+x.n},0):null;
  if(last&&last.o!=null&&last.n!=null&&last.o>0&&last.n>0)setv('c-nr',Math.max(30,Math.min(150,Math.round(l4.reduce(function(s,x){return s+x.n},0)/Q.slice(-l4.length).reduce(function(s,x){return s+(x.o||0)},0)*100))));
  /* 예상 PER 칸이 비어 있으면 이번 분기 영업이익 × 4 를 넣어 둔다 (연환산 가정, 직접 고치면 된다) */
  if(last&&last.o!=null&&!$('#c-fop').value){setv('c-fop',Math.round(last.o*4))}
  check()})}
function fwd(per,pbr){
  var el=$('#ckFwd'),fop=n('c-fop'),nr=n('c-nr'),mc=n('c-mcap'),eq=n('c-eq');
  if(fop==null){el.hidden=true;return}el.hidden=false;
  if(nr==null)nr=78;var ni=fop*nr/100,h='<h4>📈 내년 예상 PER · PBR</h4>';
  if(!mc){el.innerHTML=h+'<p>시가총액을 넣어 주세요 (불러오기를 하면 네이버 증권 시가총액으로 채웁니다).</p>';return}
  /* '지금' 값도 같은 시가총액·자기자본으로: PER = 시가총액 ÷ 최근 보고서 순이익(연환산), PBR = 시가총액 ÷ 자기자본 */
  var qt=QS.cur&&QS.cur.name===$('#c-name').value&&QS.cur.ttm>0?QS.cur.ttm:null;
  var cur=qt?mc/qt:CUR&&CUR.name===$('#c-name').value&&CUR.ni>0?mc/(CUR.ni*12/CUR.mo):null;if(cur!=null)per=cur;if(eq>0)pbr=mc/eq;
  var fper=ni>0?mc/ni:null,fpbr=eq?mc/(eq+ni):null,froe=eq?ni/(eq+ni/2)*100:null;
  var t=function(lab,v,unit,now){return '<div><small>'+lab+'</small><b>'+(v==null?'–':v.toFixed(unit==='%'?1:unit==='배P'?2:1)+(unit==='배P'?'배':unit))+'</b><i>'+(now!=null?'지금 '+now:'&nbsp;')+'</i></div>'};
  var msg=[];
  if(ni<=0)msg.push('예상 순이익이 0 이하라 PER을 구할 수 없습니다(적자)');
  else if(per>0&&fper!=null){var ch=(fper/per-1)*100;msg.push('지금 PER '+per.toFixed(1)+'배 → 내년 '+fper.toFixed(1)+'배. '+(ch<-10?'이익이 늘어 지금 주가로도 내년엔 '+Math.abs(ch).toFixed(0)+'% 더 싸 보인다. 그 이익 증가가 실제로 나올지가 관건':ch>10?'내년 이익이 줄어 지금 주가가 내년 기준으론 더 비싸 보인다':'지금과 비슷한 수준'))}
  msg.push('예상 순이익 '+fmtEok(ni)+' = 내년 영업이익 '+fmtEok(fop)+' × '+nr.toFixed(0)+'%(순이익 ÷ 영업이익, 가정)');
  if($('#c-fop').classList.contains('auto'))msg.push('내년 영업이익 칸은 이번 분기 영업이익 × 4 로 채운 값(가정)입니다. 증권사 전망치로 바꿔 넣어 보세요');
  msg.push('시가총액 '+fmtEok(mc)+(MDATE&&$('#c-mcap').classList.contains('auto')?' (네이버 증권 '+MDATE+')':'')+' · 지금 PER = 시가총액 ÷ '+(qt?'최근 4분기 순이익 합':'최근 보고서 순이익(연환산)')+', 지금 PBR = 시가총액 ÷ 자기자본');
  msg.push('예상 PBR은 내년 말 자기자본 = 지금 자기자본 + 예상 순이익(배당·자사주 빼지 않은 가정)으로 계산');
  el.innerHTML=h+'<div class="tl">'+t('예상 PER',fper,'배',per>0?per.toFixed(1)+'배':null)+t('예상 PBR',fpbr,'배P',pbr>0?pbr.toFixed(2)+'배':null)+t('예상 ROE',froe,'%',n('c-roe')!=null?n('c-roe').toFixed(1)+'%':null)+'</div>'
   +'<p>'+msg.map(esc).join('<br>')+'</p>';
}
$('#ckF').addEventListener('input',function(){$('#ckEx').hidden=true;check()});
$('#c-name').addEventListener('input',check);
$('#ckF').addEventListener('submit',function(e){e.preventDefault()});
$('#ckReset').addEventListener('click',function(){document.querySelectorAll('#ckF input,#c-name').forEach(function(i){i.value='';i.classList.remove('auto')});$('#sepPL').textContent=PL0;$('#sepBS').textContent=BS0;srcMsg('');$('#ckEx').hidden=true;check();$('#c-name').focus()});
function ckList(){
  var L=lsGet('st-checks');
  $('#ckList').innerHTML=L.length?'<b style="font-size:14px">저장한 체크 (이 기기)</b>'+L.map(function(x,i){return '<div class="it"><span class="dot '+x.v+'">'+LV[x.v]+'</span><b>'+esc(x.name)+'</b><span class="when">'+esc(x.when)+'</span><button class="sb gh sm" type="button" data-load="'+i+'">불러오기</button><button class="sb del sm" type="button" data-rm="'+i+'">지우기</button></div>'}).join(''):'';
}
$('#ckSave').addEventListener('click',function(){
  var r=check(),vals={};document.querySelectorAll('#ckF input,#ckF select,#c-name').forEach(function(i){vals[i.id]=i.value});
  var L=lsGet('st-checks'),d=new Date();L.unshift({name:vals['c-name']||'이름 없음',v:r.v[0],when:d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2),vals:vals});
  $('#ckMsg').textContent=lsSet('st-checks',L.slice(0,50))?'저장했습니다 (이 기기에만)':'이 브라우저는 저장을 막고 있습니다';ckList();
});
$('#ckList').addEventListener('click',function(e){
  var b=e.target.closest('button');if(!b)return;var L=lsGet('st-checks');
  if(b.dataset.load){var x=L[+b.dataset.load];Object.keys(x.vals).forEach(function(k){var el=document.getElementById(k);if(el)el.value=x.vals[k]});$('#ckEx').hidden=true;check();scrollTo(0,0)}
  if(b.dataset.rm){L.splice(+b.dataset.rm,1);lsSet('st-checks',L);ckList()}
});

/* ---- 종목 불러오기 (OpenDART, 매일 밤 study_fin.py 가 만든 fin/*.json) ---- */
var FIN=null,FINP=null,PL0=$('#sepPL').textContent,BS0=$('#sepBS').textContent;
function finIndex(){
  if(!FINP)FINP=fetch('fin/index.json',{cache:'no-cache'}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){FIN=j;
    $('#c-list').innerHTML=j.list.map(function(x){return '<option value="'+esc(x[1])+'">'+esc(x[0]+(x[2]?' · '+x[2]:''))+'</option>'}).join('');return j})
    .catch(function(){FIN={list:[]};return FIN});
  return FINP;
}
function srcMsg(t,cls){var e=$('#ckSrc');e.className='src'+(cls?' '+cls:'');e.innerHTML=t}
function findCo(q){
  q=(q||'').trim().toUpperCase().replace(/\s+/g,'');if(!q||!FIN)return null;var L=FIN.list,i;
  for(i=0;i<L.length;i++)if(L[i][0]===q||L[i][1].toUpperCase().replace(/\s+/g,'')===q)return L[i];
  var hit=L.filter(function(x){return x[1].toUpperCase().replace(/\s+/g,'').indexOf(q)>=0});
  return hit.length===1?hit[0]:(hit.length?hit:null);
}
function setv(id,v){var el=$('#'+id);if(v==null||v===''){el.value='';el.classList.remove('auto');return}el.value=v;el.classList.add('auto')}
function loadCo(){
  var q=$('#c-name').value;
  finIndex().then(function(j){
    if(!j.list.length){srcMsg('자동 불러오기 자료를 준비하는 중입니다. 지금은 숫자를 직접 넣어 주세요.','bad');return}
    var c=findCo(q);
    if(!c){srcMsg('"'+esc(q)+'"을(를) 찾지 못했습니다. 자료는 매일 밤 늘어납니다 (현재 '+j.list.length+'곳). 숫자를 직접 넣어도 됩니다.','bad');return}
    if(Array.isArray(c[0])){srcMsg('여러 종목이 맞습니다: '+c.slice(0,8).map(function(x){return esc(x[1])}).join(', ')+(c.length>8?' 외':'')+'. 목록에서 골라 주세요.');return}
    srcMsg('불러오는 중…');
    fetch('fin/'+c[0]+'.json',{cache:'no-cache'}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(fill).catch(function(){srcMsg('자료를 불러오지 못했습니다. 잠시 뒤 다시 눌러 주세요.','bad')});
  });
}
function fill(d){
  var v=d.v,b=d.basis;$('#ckEx').hidden=true;
  $('#c-name').value=d.name;
  var op=(d.audit&&d.audit.opinion)||'';$('#c-audit').value=!op?'na':/부적정|거절/.test(op)?'bad':/한정/.test(op)?'q':/적정/.test(op)?'ok':'na';
  setv('c-rev1',v.rev[0]);setv('c-rev0',v.rev[1]);setv('c-op1',v.op[0]);setv('c-op0',v.op[1]);setv('c-cf1',v.cf[0]);setv('c-cf0',v.cf[1]);
  setv('c-int',v.int);setv('c-ar1',v.ar[0]);setv('c-ar0',v.ar[1]);setv('c-inv1',v.inv[0]);setv('c-inv0',v.inv[1]);
  setv('c-cb',d.raises?d.raises.length:null);
  $('#c-mkt').value=d.market==='코스닥'?'kosdaq':'kospi';
  setv('c-ebt',v.ebt!=null&&v.ebt<0?Math.abs(v.ebt):(v.ebt!=null?0:null));setv('c-eq',v.eq);
  var px=d.px||{};setv('c-roe',v.roe);setv('c-per',px.per>0?px.per:'');setv('c-pbr',px.pbr>0?px.pbr:'');
  CUR={ni:v.ni,mo:b.months||12,name:d.name};setv('c-mcap','');
  fetch('mcap.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null}).then(function(j){var x=j&&j.m&&j.m[d.name];
   if(x&&$('#c-name').value===d.name){setv('c-mcap',x);MDATE=j.date;check()}}).catch(function(){});
  setv('c-nr',v.ni!=null&&v.op[0]>0&&v.ni>0?Math.max(30,Math.min(150,Math.round(v.ni/v.op[0]*100))):78);
  $('#c-fop').value='';loadQ(d.code,d.name);
  $('#sepPL').textContent='손익·현금흐름 · 올해 = '+b.now+', 작년 = '+b.prev;
  $('#sepBS').textContent='재무상태표 · 올해 = '+b.bs_now+(b.bs_prev?', 작년 = '+b.bs_prev:' (작년 같은 시점 자료 없음)')+' 잔액';
  var f=b.filed||'',notes=[];
  if(d.fin)notes.push('<b>금융업</b>이라 이 체크가 맞지 않습니다. 업종별 탭의 금융 체크리스트를 보세요');
  if(v.int_src&&v.int_src!=='이자비용')notes.push('이자비용 칸은 '+esc(v.int_src)+' 숫자입니다'+(/현금흐름/.test(v.int_src)?' (금융 자회사가 있으면 그 이자도 섞여 이자보상배율이 낮게 나옵니다)':''));
  if(b.months<12)notes.push('법차손·ROE는 '+esc(b.now)+' 기준(ROE는 연환산)입니다');
  if(d.raises&&d.raises.length)notes.push('자금조달: '+d.raises.map(function(x){return esc(x[0].slice(0,4)+'.'+x[0].slice(4,6))+' '+esc(x[1].replace(/^주요사항보고서\(|\)$/g,''))}).join(', '));
  if(px.date)notes.push('PER·PBR은 KB증권 '+esc(px.date)+' 종가 기준'+(px.price?' (주가 '+Number(px.price).toLocaleString('ko-KR')+'원)':'')+(px.per>0?'':' · 적자라 PER 없음'));
  else notes.push('PER·PBR은 HTS에서 넣으면 가격 위치 해석이 나옵니다');
  srcMsg('<b>'+esc(d.name)+'</b> · '+esc(d.market)+' · '+esc(b.year+' '+b.reprt+'보고서')+'('+esc(b.fs)+') · '+f.slice(0,4)+'.'+f.slice(4,6)+'.'+f.slice(6,8)+' 제출 · 감사의견 '+esc((d.audit&&d.audit.year)||'')+' '+esc(op||'확인 필요')
    +' · <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+esc(b.rcept_no)+'" target="_blank" rel="noopener">DART 원문</a><br>'+notes.join(' · '),'ok');
  check();
}
$('#ckLoad').addEventListener('click',loadCo);
$('#c-name').addEventListener('focus',finIndex,{once:true});
$('#c-name').addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();loadCo()}});
$('#c-name').addEventListener('change',function(){if(FIN&&FIN.list.length){var c=findCo(this.value);if(c&&!Array.isArray(c[0]))loadCo()}});
$('#ckF').addEventListener('input',function(e){if(e.target.classList)e.target.classList.remove('auto')});
check();ckList();

/* ---- 업종 ---- */
$('#indL').innerHTML=I.map(function(g){return '<h2>'+esc(g.group)+'</h2><p class="st-lede">'+esc(g.lede)+'</p>'+g.items.map(function(x){
  return '<details class="ind"><summary><b>'+esc(x.name)+'</b><span class="wp">'+esc(x.warp)+'</span><span class="cv" aria-hidden="true">›</span></summary><div class="bd">'
   +x.rows.map(function(r){return '<dl class="'+(/함정/.test(r[0])?'trap':'')+'"><dt>'+esc(r[0])+'</dt><dd>'+esc(r[1])+'</dd></dl>'}).join('')
   +'<div class="ft"><button class="sb gh sm" type="button" data-cat="'+esc(x.cat)+'">'+esc(x.cat)+' 용어 ›</button><button class="sb gh sm" type="button" data-ci="'+esc(x.name)+'">사례 ›</button></div></div></details>'}).join('')}).join('');
$('#indL').addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
  if(b.dataset.cat){cat=b.dataset.cat;$('#q').value='';chips();terms();show('term');scrollTo(0,0)}
  if(b.dataset.ci){$('#cq').value=b.dataset.ci;cases();show('case');scrollTo(0,0)}});

/* ---- 용어 ---- */
var ORDER=['재무제표 구조','재무상태표','손익계산서','현금흐름표','재무비율-안정성','재무비율-수익성','재무비율-활동성','밸류에이션','이익의 질','공시','회계기준','금융-은행','금융-보험','금융-증권','금융-여전','제조','자동차','수주','바이오','플랫폼','유통','리츠','유틸리티','통신','항공해운'];
var cat='전체';
function allT(){return T.map(function(x){return Object.assign({},x)}).concat(lsGet('st-terms').map(function(x,i){return Object.assign({mine:true,idx:i},x)}))}
function chips(){
  var A=allT(),c={},mine=A.filter(function(x){return x.mine}).length;A.forEach(function(x){c[x.cat]=(c[x.cat]||0)+1});
  var cats=['전체'].concat(mine?['내 메모']:[],ORDER.filter(function(k){return c[k]}),Object.keys(c).filter(function(k){return ORDER.indexOf(k)<0}));
  $('#chips').innerHTML=cats.map(function(k){var m=k==='전체'?A.length:k==='내 메모'?mine:c[k];return '<button class="chip" type="button" aria-pressed="'+(k===cat)+'" data-c="'+esc(k)+'">'+esc(k)+'<i>'+m+'</i></button>'}).join('');
}
function hl(t,q){var s=esc(t);if(!q)return s;var re=new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&').replace(/\s+/g,'\\s*'),'gi');return s.replace(re,function(m){return '<mark>'+m+'</mark>'})}
function terms(){
  var q=$('#q').value.trim(),ql=q.toLowerCase().replace(/\s+/g,''),A=allT();
  if(cat==='내 메모')A=A.filter(function(x){return x.mine});else if(cat!=='전체')A=A.filter(function(x){return x.cat===cat});
  if(ql){var sc=function(x){var nm=(x.term+' '+x.en).toLowerCase().replace(/\s+/g,'');if(x.term.toLowerCase().replace(/\s+/g,'')===ql)return 0;if(nm.indexOf(ql)>=0)return 1;if((x.formula||'').toLowerCase().replace(/\s+/g,'').indexOf(ql)>=0)return 2;if((x.def+' '+x.point).toLowerCase().replace(/\s+/g,'').indexOf(ql)>=0)return 3;return 9};
    A=A.map(function(x){return [sc(x),x]}).filter(function(p){return p[0]<9}).sort(function(a,b){return a[0]-b[0]}).map(function(p){return p[1]})}
  $('#cnt').textContent=A.length+'개'+(q?' · "'+q+'"':'')+(cat!=='전체'?' · '+cat:'');
  $('#tL').innerHTML=A.length?A.map(function(x){return '<article class="tm'+(x.mine?' mine':'')+'"><div class="hd"><b>'+hl(x.term,q)+'</b><span class="en">'+hl(x.en,q)+'</span><span class="ct'+(x.mine?' mine':'')+'">'+(x.mine?'내 메모 · ':'')+esc(x.cat)+'</span></div>'
    +'<p>'+hl(x.def,q)+'</p>'+(x.formula?'<div class="fx">'+hl(x.formula,q)+'</div>':'')+(x.point?'<p class="pt"><b>해석</b> '+hl(x.point,q)+'</p>':'')
    +(x.mine?'<div class="acts"><button class="sb gh sm" type="button" data-up="'+x.idx+'">홈페이지에 올리기</button><button class="sb gh sm" type="button" data-ed="'+x.idx+'">고치기</button></div>':'')+'</article>'}).join('')
    :'<div class="empty">'+(q?'"'+esc(q)+'"에 맞는 용어가 없습니다. ':'')+'<b>+ 용어</b>로 직접 추가하세요.</div>';
}
$('#chips').addEventListener('click',function(e){var b=e.target.closest('.chip');if(!b)return;cat=b.dataset.c;chips();terms()});
var tm;$('#q').addEventListener('input',function(){clearTimeout(tm);tm=setTimeout(terms,80)});
$('#tL').addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;var L=lsGet('st-terms');
  if(b.dataset.ed!=null)openT(+b.dataset.ed);
  if(b.dataset.up!=null){var x=L[+b.dataset.up];copy('[재무제표 공부] 용어 추가해줘\n용어: '+x.term+'\n영문: '+(x.en||'')+'\n분류: '+x.cat+'\n정의: '+x.def+'\n계산식: '+(x.formula||'')+'\n해석: '+(x.point||''),b)}});

/* ---- 사례 ---- */
function allC(){return C.map(function(x){return Object.assign({},x)}).concat(lsGet('st-cases').map(function(x,i){return Object.assign({mine:true,idx:i},x)}))}
function cases(){
  var q=$('#cq').value.trim().toLowerCase(),A=allC().reverse();
  if(q)A=A.filter(function(x){return (x.company+' '+x.industry+' '+x.cell+' '+x.what+' '+x.lesson).toLowerCase().indexOf(q)>=0});
  $('#cL').innerHTML=A.length?A.map(function(x){return '<article class="tm cs'+(x.mine?' mine':'')+'"><div class="hd"><b>'+esc(x.company)+'</b><span class="en">'+esc(x.period)+'</span><span class="ct'+(x.mine?' mine':'')+'">'+(x.mine?'내 메모 · ':'')+esc(x.industry)+'</span></div>'
    +'<div class="cell">본 칸 · '+esc(x.cell)+'</div><p>'+esc(x.what)+'</p><div class="ls"><b>배운 점</b> '+esc(x.lesson)+'</div>'
    +((x.sources||[]).length?'<div class="srcs">출처 '+x.sources.map(function(s){return '<a href="'+esc(s[1])+'" target="_blank" rel="noopener">'+esc(s[0])+'</a>'}).join(' · ')+'</div>':'')
    +'<div class="meta2">기록 '+esc(x.added||'')+'</div>'
    +(x.mine?'<div class="acts"><button class="sb gh sm" type="button" data-up="'+x.idx+'">홈페이지에 올리기</button><button class="sb gh sm" type="button" data-ed="'+x.idx+'">고치기</button></div>':'')+'</article>'}).join('')
    :'<div class="empty">맞는 사례가 없습니다. <b>+ 사례</b>로 처음 기록을 남겨 보세요.</div>';
}
$('#cq').addEventListener('input',cases);
$('#cL').addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;var L=lsGet('st-cases');
  if(b.dataset.ed!=null)openC(+b.dataset.ed);
  if(b.dataset.up!=null){var x=L[+b.dataset.up];copy('[재무제표 공부] 사례 추가해줘 (숫자는 출처로 확인해서)\n종목: '+x.company+'\n업종: '+x.industry+'\n시점: '+x.period+'\n본 칸: '+x.cell+'\n무슨 일: '+x.what+'\n배운 점: '+x.lesson+'\n출처: '+((x.sources&&x.sources[0])?x.sources[0][1]:''),b)}});

/* ---- 추가 창 ---- */
var sh=$('#sh'),F=$('#shF');
function field(id,label,val,ta,full){return '<label for="'+id+'"'+(full?' style="grid-column:1/-1"':'')+'>'+label+(ta?'<textarea id="'+id+'">'+esc(val||'')+'</textarea>':'<input id="'+id+'" value="'+esc(val||'')+'">')+'</label>'}
function openSheet(html){F.innerHTML=html;sh.hidden=false;var f=F.querySelector('input,textarea');if(f)f.focus()}
function close(){sh.hidden=true}
sh.addEventListener('click',function(e){if(e.target===sh)close()});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!sh.hidden)close()});
function foot(edit){return '<p class="note">이 기기(브라우저)에만 저장됩니다. 다른 기기에서도 보려면 저장 뒤 <b>홈페이지에 올리기</b>를 눌러 복사한 글을 Claude에게 보내세요.</p><div class="row-btn" style="justify-content:flex-end">'+(edit?'<button class="sb del" type="button" id="fDel">지우기</button>':'')+'<button class="sb gh" type="button" id="fX">닫기</button><button class="sb" type="submit">저장</button></div>'}
function openT(i){
  var L=lsGet('st-terms'),x=i!=null?L[i]:{term:$('#q').value.trim(),cat:cat!=='전체'&&cat!=='내 메모'?cat:'기타'};
  openSheet('<h3>'+(i!=null?'용어 고치기':'용어 추가')+'</h3><div class="two">'+field('fT','용어',x.term)+field('fE','영문',x.en)+'</div>'
    +'<label for="fC">분류<select id="fC">'+ORDER.concat(['기타']).map(function(k){return '<option'+(k===x.cat?' selected':'')+'>'+esc(k)+'</option>'}).join('')+'</select></label>'
    +field('fD','정의',x.def,1)+field('fF','계산식 (없으면 비움)',x.formula)+field('fP','해석 포인트·메모',x.point,1)+foot(i!=null));
  F.onsubmit=function(e){e.preventDefault();var r={term:$('#fT').value.trim(),en:$('#fE').value.trim(),cat:$('#fC').value,def:$('#fD').value.trim(),formula:$('#fF').value.trim(),point:$('#fP').value.trim()};
    if(!r.term||!r.def){$('#fT').focus();return}var L=lsGet('st-terms');if(i!=null)L[i]=r;else L.push(r);lsSet('st-terms',L);close();cat='내 메모';chips();terms()};
  bindFoot('st-terms',i,function(){chips();terms()});
}
function openC(i){
  var L=lsGet('st-cases'),x=i!=null?L[i]:{};
  openSheet('<h3>'+(i!=null?'사례 고치기':'사례 추가')+'</h3><div class="two">'+field('gC','종목',x.company)+field('gI','업종',x.industry)+field('gP','시점 (예: 2026년 3분기)',x.period)+field('gL','본 칸 (예: 계약자산 주석)',x.cell)+'</div>'
    +field('gW','무슨 일이 있었나',x.what,1)+field('gS','배운 점',x.lesson,1)+field('gU','출처 링크',x.sources&&x.sources[0]?x.sources[0][1]:'')+foot(i!=null));
  F.onsubmit=function(e){e.preventDefault();var d=new Date(),u=$('#gU').value.trim();
    var r={added:x.added||d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2),company:$('#gC').value.trim(),industry:$('#gI').value.trim(),period:$('#gP').value.trim(),cell:$('#gL').value.trim(),what:$('#gW').value.trim(),lesson:$('#gS').value.trim(),sources:u?[['출처',u]]:[]};
    if(!r.company||!r.lesson){$('#gC').focus();return}var L=lsGet('st-cases');if(i!=null)L[i]=r;else L.push(r);lsSet('st-cases',L);close();$('#cq').value='';cases()};
  bindFoot('st-cases',i,cases);
}
function bindFoot(key,i,after){
  $('#fX').onclick=close;var d=$('#fDel');
  if(d){var arm=false;d.onclick=function(){if(!arm){arm=true;d.textContent='한 번 더 누르면 지움';setTimeout(function(){arm=false;d.textContent='지우기'},3000);return}
    var L=lsGet(key);L.splice(i,1);lsSet(key,L);close();after()}}
}
$('#addT').addEventListener('click',function(){openT(null)});
$('#addC').addEventListener('click',function(){openC(null)});

chips();terms();cases();

/* ---- 퀴즈 ---- */
var QB=__QUIZ__,qs=[],qi=0,qok=0,qwrong=[],qmode='real',qdone=false;
function shuf(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
function termQ(t){
  var pool=T.filter(function(x){return x.term!==t.term&&x.def&&x.def.length>8}),same=pool.filter(function(x){return x.cat===t.cat}),others=shuf(same.length>=3?same:pool).slice(0,3);
  var esc2=t.term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),mask=function(s){return s.replace(new RegExp(esc2,'g'),'○○')};
  if(Math.random()<0.5){
    var ch=shuf([t].concat(others));
    return {id:'t:'+t.term,cat:'용어 · '+t.cat,q:'다음 설명에 맞는 용어는?\n「'+mask(t.def)+'」',c:ch.map(function(x){return x.term+(x.en?' ('+x.en.split(' (')[0]+')':'')}),a:ch.indexOf(t),exp:(t.formula?'계산식: '+t.formula+'. ':'')+(t.point||''),ref:t.term,shuffled:1};
  }
  var ch2=shuf([t].concat(others));
  return {id:'t:'+t.term,cat:'용어 · '+t.cat,q:'「'+t.term+'」의 뜻으로 맞는 것은?',c:ch2.map(function(x){return x.term===t.term?x.def:x.def.replace(new RegExp(x.term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'),'○○')}),a:ch2.indexOf(t),exp:(t.formula?'계산식: '+t.formula+'. ':'')+(t.point||''),ref:t.term,shuffled:1};
}
/* 실제 종목 문제: fin/<코드>.json (DART 최근 보고서 + KB PER·PBR) 으로 계산 문제를 만든다 */
function fmtEok(v){var a=Math.abs(v),s=v<0?'−':'';if(a>=10000){var jo=Math.floor(a/10000),ek=Math.round(a-jo*10000);return s+jo.toLocaleString('ko-KR')+'조'+(ek?' '+ek.toLocaleString('ko-KR')+'억':'')+'원'}return s+(a<100?a.toFixed(1):Math.round(a).toLocaleString('ko-KR'))+'억원'}
function numChoices(v,fmt,extra){
  var c=[v].concat(extra||[]).concat([v*0.5,v*2,v*1.5,v*0.7,v*1.3,-v]),out=[],seen={};
  var zero=fmt(0),zero2=fmt(-0.0001);
  c.forEach(function(x){if(out.length>=4||!isFinite(x))return;var t=fmt(x);if(seen[t]||(x!==v&&(t===zero||t===zero2)))return;
    if(out.length&&out.some(function(y){return Math.abs(y-x)<Math.max(Math.abs(v)*0.08,1e-9)}))return;seen[t]=1;out.push(x)});
  var ch=shuf(out);return {c:ch.map(fmt),a:ch.indexOf(v)};
}
function coQ(d){
  var v=d.v,b=d.basis,px=d.px||{},nm=d.name+'('+b.now+', '+b.fs+')',T=[];
  if(v.op[0]>=10&&v.int>=1&&v.op[0]/v.int<=200)T.push(function(){var x=v.op[0]/v.int,f=function(y){return y.toFixed(1)+'배'},o=numChoices(x,f,[(v.op[0]-v.int)/v.int]);
    return {t:'icr',q:nm+'의 영업이익은 '+fmtEok(v.op[0])+', 이자비용은 '+fmtEok(v.int)+(v.int_src&&v.int_src!=='이자비용'?'('+v.int_src+')':'')+'입니다. 이자보상배율은?',c:o.c,a:o.a,
      exp:'이자보상배율 = 영업이익 ÷ 이자비용 = '+fmtEok(v.op[0])+' ÷ '+fmtEok(v.int)+' = '+f(x)+'. '+(x<1?'1배 미만이라 영업이익으로 이자도 못 냅니다.':x<3?'3배 미만이라 금리가 오르면 부담이 커집니다.':'이자 부담은 낮은 편입니다.')}});
  if(px.per>0&&px.per<=200&&px.pbr>0)T.push(function(){var x=px.pbr/px.per*100,f=function(y){return y.toFixed(1)+'%'},o=numChoices(x,f,[px.per*px.pbr,px.per/px.pbr]);
    return {t:'roe',q:d.name+'의 PER은 '+px.per.toFixed(2)+'배, PBR은 '+px.pbr.toFixed(2)+'배입니다(KB증권 '+px.date+' 종가 기준). 시장이 보는 ROE는?',c:o.c,a:o.a,
      exp:'ROE = PBR ÷ PER = '+px.pbr.toFixed(2)+' ÷ '+px.per.toFixed(2)+' = '+f(x)+'.'+(v.roe!=null?' DART 최근 보고서로 계산한 ROE(연환산)는 '+v.roe.toFixed(1)+'%'+(Math.abs(v.roe-x)>=3?'로 차이가 큽니다. 이익이 '+(v.roe>x?'늘고':'줄고')+' 있다는 신호입니다.':'로 비슷합니다.'):'')}});
  if(v.op[0]>=10&&v.cf[0]!=null&&Math.abs(v.cf[0]/v.op[0])<=5)T.push(function(){var x=v.cf[0]/v.op[0]*100,f=function(y){return Math.round(y)+'%'},o=numChoices(x,f,[v.op[0]/Math.max(Math.abs(v.cf[0]),1)*100]);
    return {t:'cash',q:nm+'의 영업이익은 '+fmtEok(v.op[0])+', 영업현금흐름은 '+fmtEok(v.cf[0])+'입니다. 영업현금흐름은 영업이익의 몇 %일까요?',c:o.c,a:o.a,
      exp:'영업현금흐름 ÷ 영업이익 = '+f(x)+'. '+(x<0?'이익은 흑자인데 현금은 빠져나갔습니다. 매출채권·재고·계약자산 주석을 확인합니다.':x<50?'절반도 현금으로 안 들어왔습니다. 이익의 질을 의심합니다.':x<80?'대부분 현금으로 들어왔습니다. 몇 분기 추세를 같이 봅니다.':'이익이 현금으로 잘 들어오고 있습니다.')}});
  if(v.rev[0]>=10&&v.rev[1]>=10&&v.rev[0]/v.rev[1]<=4)T.push(function(){var x=(v.rev[0]/v.rev[1]-1)*100,f=function(y){return (y>0?'+':'')+y.toFixed(1)+'%'},o=numChoices(x,f,[(v.rev[1]/v.rev[0]-1)*100,v.rev[0]/v.rev[1]*100]);
    return {t:'grow',q:nm+'의 매출은 '+fmtEok(v.rev[0])+', 전년 같은 기간('+b.prev+')은 '+fmtEok(v.rev[1])+'입니다. 매출 증가율은?',c:o.c,a:o.a,
      exp:'매출 증가율 = (올해 ÷ 작년 − 1) = '+f(x)+'. '+(v.ar[0]!=null&&v.ar[1]>0?(function(){var ga=(v.ar[0]/v.ar[1]-1)*100,rel=((1+ga/100)/Math.max(1+x/100,0.01)-1)*100;return '같은 기간 매출채권+계약자산은 '+f(ga)+'. '+(rel>10?'매출보다 빨리 늘었으니 회수 위험을 확인합니다.':'매출과 비슷하거나 느리게 늘어 무리한 매출은 아닌 것으로 보입니다.')})():'')}});
  if(!T.length)return null;
  var r=T[Math.floor(Math.random()*T.length)]();
  if(r.c.length<4||r.a<0)return null;
  return Object.assign(r,{id:'r:'+d.code+':'+r.t,cat:'실제 종목 · '+d.name,ref:d.name,co:d.name,shuffled:1,
    exp:r.exp+' (출처: '+b.year+' '+b.reprt+'보고서 DART'+(r.t==='roe'?', KB증권':'')+')'});
}
function coQuestions(n){
  return finIndex().then(function(j){
    if(!j.list.length)throw 0;
    var pick=shuf(j.list).slice(0,n*2);
    return Promise.all(pick.map(function(x){return fetch('fin/'+x[0]+'.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null}).catch(function(){return null})}))
  }).then(function(ds){return ds.filter(function(d){return d&&!d.fin}).map(coQ).filter(Boolean).slice(0,n)});
}
function realMap(){try{return JSON.parse(localStorage.getItem('st-quiz-real')||'{}')}catch(e){return {}}}
function prep(x){if(x.shuffled)return x;var o=shuf(x.c.map(function(c,i){return [c,i]}));return Object.assign({},x,{c:o.map(function(p){return p[0]}),a:o.findIndex(function(p){return p[1]===x.a})})}
function termPool(){return T.filter(function(x){return x.def&&x.def.length>8})}
function qwrongIds(){return lsGet('st-quiz-wrong')}
function qstat(){var st={};try{st=JSON.parse(localStorage.getItem('st-quiz-stat')||'{}')}catch(e){}var w=qwrongIds().length;
  $('#qzStat').textContent=(st.n?'지금까지 '+st.n+'문제 · 정답률 '+Math.round(st.ok/st.n*100)+'%':'아직 푼 문제가 없습니다')+(w?' · 다시 볼 문제 '+w+'개':'');
  $('#qzWrongBtn').disabled=!w;$('#qzWrongBtn').style.opacity=w?1:.5;}
function qstart(m){
  qmode=m;qi=0;qok=0;qwrong=[];qdone=false;var tp=termPool();
  document.querySelectorAll('.qz-modes [data-qm]').forEach(function(b){b.classList.toggle('gh',b.dataset.qm!==m)});
  function go(list){qs=list.map(prep);qdraw()}
  if(m==='co'||m==='mix'){
    $('#qz').innerHTML='<div class="empty">실제 종목 숫자를 불러오는 중…</div>';
    coQuestions(m==='co'?10:4).then(function(cq){
      if(m==='co')go(cq);else go(shuf(cq.concat(shuf(QB).slice(0,3),shuf(tp).slice(0,10-cq.length-3).map(termQ))));
    }).catch(function(){if(m==='co')$('#qz').innerHTML='<div class="empty">종목 자료를 불러오지 못했습니다. 잠시 뒤 다시 눌러 주세요.</div>';else go(shuf(shuf(QB).slice(0,5).concat(shuf(tp).slice(0,5).map(termQ))))});
    return;
  }
  if(m==='real')go(shuf(QB).slice(0,10));
  else if(m==='term')go(shuf(tp).slice(0,10).map(termQ));
  else{var ids=qwrongIds(),RM=realMap();go(ids.map(function(id){if(id.indexOf('t:')===0){var t=T.find(function(x){return 't:'+x.term===id});return t?termQ(t):null}if(id.indexOf('r:')===0)return RM[id]||null;return QB.find(function(x){return x.id===id})||null}).filter(Boolean).slice(0,20))}
}
function qdraw(){
  var box=$('#qz');
  if(!qs.length){box.innerHTML='<div class="empty">풀 문제가 없습니다. 다른 묶음을 골라 주세요.</div>';return}
  if(qi>=qs.length){
    var pct=Math.round(qok/qs.length*100);
    box.innerHTML='<div class="end"><div class="pg" style="width:100%"><span>'+({real:'실전',co:'실제 종목',term:'용어',mix:'섞어서',wrong:'틀린 문제 다시'}[qmode])+' 결과</span></div><div class="big">'+qok+' / '+qs.length+'</div><div>'+(pct>=90?'훌륭합니다. 실전에서 바로 쓸 수 있는 수준입니다.':pct>=60?'좋습니다. 틀린 문제의 해설만 다시 읽어 보세요.':'틀린 문제를 다시 풀면서 해설을 읽어 보세요. 용어사전·사례노트와 같이 보면 빨리 늡니다.')+'</div>'
      +(qwrong.length?'<b style="font-size:14px">틀린 문제</b><ol class="wl">'+qwrong.map(function(x){return '<li>'+esc(x.q.split('\n')[0])+'</li>'}).join('')+'</ol>':'')
      +'<div class="row-btn"><button class="sb" type="button" data-qm="'+qmode+'">한 번 더</button>'+(qwrongIds().length?'<button class="sb gh" type="button" data-qm="wrong">틀린 문제 다시</button>':'')+'</div></div>';
    qstat();return;
  }
  var x=qs[qi],qt=esc(x.q).replace(/\n/g,'<br>');
  box.innerHTML='<div class="pg"><span>'+(qi+1)+' / '+qs.length+' · '+esc(x.cat)+'</span><span>맞힘 '+qok+'</span></div><div class="bar"><i style="width:'+(qi/qs.length*100)+'%"></i></div>'
    +'<h3>'+qt+'</h3><div class="ch">'+x.c.map(function(c,i){return '<button type="button" data-ci="'+i+'"><b>'+(i+1)+'</b><span>'+esc(c)+'</span></button>'}).join('')+'</div><div id="qzEx"></div>';
  qdone=false;
}
function qanswer(i){
  if(qdone)return;qdone=true;var x=qs[qi],ok=i===x.a,btns=document.querySelectorAll('#qz .ch button');
  btns.forEach(function(b,k){b.disabled=true;if(k===x.a)b.classList.add('ok');else if(k===i)b.classList.add('no')});
  var W=qwrongIds(),pos=W.indexOf(x.id);
  if(ok){qok++;if(pos>=0)W.splice(pos,1)}else{qwrong.push(x);if(pos<0)W.unshift(x.id)}
  if(x.id.indexOf('r:')===0){var RM=realMap();if(ok)delete RM[x.id];else RM[x.id]=x;var ks=Object.keys(RM);if(ks.length>40)ks.slice(0,ks.length-40).forEach(function(k){delete RM[k]});try{localStorage.setItem('st-quiz-real',JSON.stringify(RM))}catch(e){}}
  lsSet('st-quiz-wrong',W.slice(0,100));
  var st={};try{st=JSON.parse(localStorage.getItem('st-quiz-stat')||'{}')}catch(e){}st.n=(st.n||0)+1;st.ok=(st.ok||0)+(ok?1:0);try{localStorage.setItem('st-quiz-stat',JSON.stringify(st))}catch(e){}
  var hasT=x.ref&&T.some(function(t){return t.term===x.ref}),hasC=x.ref&&C.some(function(c){return c.company===x.ref});
  $('#qzEx').innerHTML='<div class="ex"><span class="vd '+(ok?'ok':'no')+'">'+(ok?'정답입니다':'아쉽습니다 · 정답은 '+(x.a+1)+'번')+'</span>'+(x.exp?'<span>'+esc(x.exp)+'</span>':'')+'</div>'
    +'<div class="row-btn" style="margin-top:10px"><button class="sb" type="button" id="qzNext">'+(qi+1<qs.length?'다음 문제':'결과 보기')+'</button>'
    +(x.co?'<button class="sb gh" type="button" data-qref="k">5분 체크로 「'+esc(x.co)+'」 보기</button>':hasT?'<button class="sb gh" type="button" data-qref="t">용어사전에서 「'+esc(x.ref)+'」</button>':hasC?'<button class="sb gh" type="button" data-qref="c">사례노트에서 「'+esc(x.ref)+'」</button>':'')+'</div>';
  $('#qzNext').focus();
}
$('#p-quiz').addEventListener('click',function(e){
  var b=e.target.closest('button');if(!b)return;
  if(b.dataset.qm){qstart(b.dataset.qm);return}
  if(b.dataset.ci!=null){qanswer(+b.dataset.ci);return}
  if(b.id==='qzNext'){qi++;qdraw();$('#qz').scrollIntoView({block:'nearest'});return}
  if(b.dataset.qref==='k'){$('#c-name').value=qs[qi].co;show('check');scrollTo(0,0);loadCo();return}
  if(b.dataset.qref){var r=qs[qi].ref;if(b.dataset.qref==='t'){cat='전체';$('#q').value=r;chips();terms();show('term')}else{$('#cq').value=r;cases();show('case')}scrollTo(0,0)}
});
document.addEventListener('keydown',function(e){if($('#p-quiz').hidden||!sh.hidden)return;if(/^[1-4]$/.test(e.key)&&!qdone&&qi<qs.length&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))qanswer(+e.key-1)});
qstat();qstart('real');
})();
</script>"""


MAP_URL = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/flow-live/map.json"


def mcap_file(dest):
    """예상 PER·PBR 칸의 시가총액: kb flow-live map.json(네이버 증권 업종별 종목, 시가총액 억원)을 이름 → 시가총액으로 저장."""
    try:
        with urllib.request.urlopen(urllib.request.Request(MAP_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            j = json.loads(r.read())
    except Exception as e:
        print("시가총액 자료 실패:", type(e).__name__, e)
        return 0
    m = {st["n"]: round(st["v"]) for secs in (j.get("data") or {}).values() for sec in secs for st in sec.get("st") or []
         if st.get("n") and st.get("v")}
    d = str(j.get("date") or "")
    (dest / "mcap.json").write_text(json.dumps({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "", "m": m},
                                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(m)


def build(out, page):
    """out: 사이트 출력 폴더, page: build_site.page (메뉴·머리 공통 틀)."""
    terms, inds, cases, quiz = _load("terms.json"), _load("industries.json"), _load("cases.json"), _load("quiz.json")
    n_ind = sum(len(g.get("items", [])) for g in inds)
    tabs = ('<div class="st-tabs" role="tablist" aria-label="재무제표 공부">'
            + "".join(f'<button role="tab" id="t-{k}" aria-controls="p-{k}" aria-selected="false" type="button">{v}</button>'
                      for k, v in (("how", "활용법"), ("check", "5분 체크"), ("ind", "업종별"), ("term", "용어사전"), ("case", "사례노트"), ("quiz", "퀴즈")))
            + "</div>")
    js = JS.replace("__TERMS__", _js(terms)).replace("__IND__", _js(inds)).replace("__CASES__", _js(cases)).replace("__QUIZ__", _js(quiz))
    body = f'<style>{CSS}</style><div class="st">{tabs}{HOW}{CHECK}{IND}{TERMS}{CASES}{QUIZ}</div>{SHEET}{js}'
    dest = out / "study"
    dest.mkdir(parents=True, exist_ok=True)
    mcap_file(dest)
    (dest / "index.html").write_text(
        page("📒 재무제표 공부", body, "../", "study/", "FINANCIAL STATEMENTS",
             f"용어 {len(terms)}개 · 업종 {n_ind}개 · 사례 {len(cases)}개 · 퀴즈 {len(quiz)}문제 · 재무제표를 주식에 쓰는 법"),
        encoding="utf-8")
    return {"terms": len(terms), "industries": n_ind, "cases": len(cases)}
