# Brian's 투자노트 (market-dashboard) — 작업 규칙

GitHub Pages 주식 홈페이지(https://sunbong-oh.github.io/market-dashboard/) 저장소. 사용자는 한국어로 대화한다. 답도 한국어로, 쉬운 말로.
어느 채팅(프로젝트·세션)에서 작업하든 이 파일의 규칙을 따른다.

## 반영 방식
- 작업 브랜치에서 커밋 → PR → main 에 merge 하면 site.yml 이 홈페이지를 다시 만든다(몇 분 걸림).
- 리포트·실적 카드·홈페이지 갱신은 사용자 검토 없이 merge 해도 된다고 허락받았다.
- merge 할 때는 방금 만든 PR 번호를 그대로 쓴다(추측 금지). expectedHeadSha 는 40자 전체.
- .gitignore 는 화이트리스트다. 새 최상위 파일·폴더는 `!/이름` 줄을 추가해야 올라간다.
- 커밋 메시지·PR 에 모델 이름을 넣지 않는다.

## 리서치 스타일 = KB 스타일 (매번 묻지 말 것)
- 색: 노랑 #F2A900(포인트), 연노랑 #FBE7B0, 먹색 #3D3A35(본문·표 머리), 바탕 #FAF8F3, 보조 글자 #6B665D, 선 #E6E0D2.
- 글꼴 Noto Sans KR. 지면 위에 노란 띠, 아래에 출처·쪽번호. 표 머리는 먹색 바탕 흰 글자.
- 표지 오른쪽 KEY DATA 패널(먹색), 제목 앞 노란 세로 막대, 요점은 노란 네모 글머리.
- 숫자는 출처와 기준 시각을 함께 적는다. 추정·가정은 "가정"이라고 밝힌다. 매수·매도 권유 문구 없이 고지사항을 붙인다.
- 슬라이드(덱)도 같은 색·글꼴.

## 전일 미국장 강세종목 리포트 (/strong/)
- 파일: `us_strong/YYYY-MM-DD_TICKER.html` (date = 등록일, KST) + `us_strong/index.json` 에 한 줄 추가.
- index.json 항목: date, ticker, exchange, name, nameEn, sector, price, changePct, priceNote, headline, tags, file,
  market{day(전일 미국장 날짜), nasdaq, sp500, source}.
- HTML 은 기존 리포트(예: `us_strong/2026-10-23_ULTA.html`)의 `<style>` 과 구조를 그대로 쓴다: `section.page` > `.ph`(머리) / `.pb`(본문) / `.pf`(출처·쪽번호),
  표지 `.cover` + `.keydata`, 그림은 인라인 SVG(`.chart`). 휴대폰 폭(390px)에서 가로 스크롤이 생기지 않게 확인.
- 주가는 Yahoo Finance 일봉 종가, 재무는 SEC 공시(10-K·10-Q·8-K). 리포트 작성 뒤 주가가 크게 움직였으면 표지에 "작성 후 추가" 상자로 적는다.
- 확인: `python -c "import build_site as b; b.build_strong()"` 가 오류 없이 도는지.

## 실적 속보 카드 (earnings_flash/)
- 파일 `earnings_flash/<YYYYMMDD(발표 KST 날짜)>-<한글 회사명>.json`. 형식은 기존 카드(메타·테슬라·넷플릭스)와 같게:
  day, time(KST), company, period, verdict, rows[[항목, 값, 비교, 판정]], guidance[], sym[[야후심볼, 표시 이름]], sources[[제목, URL]], px.
- 수치는 회사 발표문(SEC 8-K) 포함 2곳 이상 교차 확인, 컨센서스와 비교. 콜 전이면 guidance 첫 줄 "컨퍼런스콜(HH:MM 한국시간) 후 업데이트".
- 주가 반응은 `python earnings_px.py <카드>` 로 채운다(c = 발표 전 종가 대비, d1 = 발표 뒤 첫 정규장 종가).
- 실적 발표 감지: `python earnings_sec.py --hours 30` (SEC 8-K Item 2.02 / 해외 6-K). 캘린더 날짜는 틀릴 수 있다.
- main 에 올라가면 earnings-flash.yml 이 카드 이미지를 텔레그램으로 보낸다. 발표 후 12시간 지난 카드는 보내지 않는다.

## 텔레그램·메시지 규칙 (사용자 지시)
- 텔레그램은 실적 카드를 새로 만들거나 고쳤을 때, 시간외 급등락 알림(afterhours.py)만 보낸다. 지난 소식은 보내지 않는다.
- 자동 점검 작업에서 할 일이 없으면 '·' 한 글자만 남긴다(상태 보고 금지).
- 빅테크 실적은 나오는 즉시 홈페이지에 올린다.

## 재무제표 공부 (/study/)
- 내용은 `study/terms.json`(용어) · `study/industries.json`(업종별 체크리스트) · `study/cases.json`(사례노트), 페이지 코드는 `study_page.py`.
- 사용자가 "[재무제표 공부] 용어 추가해줘" / "사례 추가해줘" 글을 붙여 넣거나 그렇게 말하면 해당 JSON 끝에 항목을 넣고 merge 한다.
  - 용어: {term, en, cat, def, formula, point}. cat 은 기존 분류 이름(재무상태표·밸류에이션·금융-은행·수주 등)을 쓴다. 같은 용어가 있으면 새로 넣지 말고 고친다.
  - 사례: {added(오늘 KST), company, industry, period, cell, what, lesson, sources[[제목, URL]]}. 숫자는 출처로 확인해서 넣고, 확인 못 한 숫자는 빼거나 "확인 필요"라고 적는다.
- 페이지에서 직접 추가한 것은 그 기기에만 저장된다(localStorage). 다른 기기와 함께 보려면 위 방식으로 JSON 에 올린다.
- 5분 체크 종목 불러오기: `study_fin.py` 가 OpenDART 에서 상장사별 최근 정기보고서 숫자를 받아 study-fin 브랜치(index.json, fin/<종목코드>.json)에 저장(study-fin.yml, 매일 21:40, Secret DART_API_KEY 필요). 이어서 KB증권 Open API 현재가(IVU10140)로 PER·PBR·주가를 px 에 넣는다(Secret KB_OPENAPI_APP_KEY·KB_OPENAPI_APP_SECRET, 없으면 건너뜀). site.yml 이 /study/fin/ 에 붙인다.
- 확인: `python -c "import build_site as b, study_page; from pathlib import Path; print(study_page.build(Path('_site'), b.page))"`

## 실적발표 종목 (/reports/) 한 줄 설명
- 종목명 아래 설명은 `company_ko.py` 의 `KR_COMPANY`(종목코드 → 한 줄, 약 40자)에서 온다. 새 보고서 종목이 생기면 한 줄 추가하고 merge 한다.
- 없는 종목은 화면이 보고서 HTML 의 '주요 사업' 첫 문장을 대신 보여 준다(길면 잘림).
