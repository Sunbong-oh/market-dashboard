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
- 퀴즈: 실전 문제는 `study/quiz.json` {id, cat, q, c[보기 4개], a(정답 0~3), exp(해설), ref(용어·사례 이름)}. 사용자가 "퀴즈 문제 추가해줘" 하면 여기에 넣는다(정답은 출처로 확인, 보기 순서는 화면에서 섞이니 아무 순서). 용어 문제는 terms.json 에서 자동 생성.
- 페이지에서 직접 추가한 것은 그 기기에만 저장된다(localStorage). 다른 기기와 함께 보려면 위 방식으로 JSON 에 올린다.
- 5분 체크 종목 불러오기: `study_fin.py` 가 OpenDART 에서 상장사별 최근 정기보고서 숫자를 받아 study-fin 브랜치(index.json, fin/<종목코드>.json)에 저장(study-fin.yml, 매일 21:40, Secret DART_API_KEY 필요). 이어서 KB증권 Open API 현재가(IVU10140)로 PER·PBR·주가를 px 에 넣는다(Secret KB_OPENAPI_APP_KEY·KB_OPENAPI_APP_SECRET, 없으면 건너뜀). site.yml 이 /study/fin/ 에 붙인다. 실행 결과(DART 호출 수·KB 성공/실패·첫 오류)는 study-fin 브랜치의 log.json 에서 본다 (Actions 로그는 이 환경에서 못 읽음).
- 확인: `python -c "import build_site as b, study_page; from pathlib import Path; print(study_page.build(Path('_site'), b.page))"`

## 실적발표 종목 (/reports/) 한 줄 설명
- 종목명 아래 설명은 `company_ko.py` 의 `KR_COMPANY`(종목코드 → 한 줄, 약 40자)에서 온다. 새 보고서 종목이 생기면 한 줄 추가하고 merge 한다.
- 없는 종목은 화면이 보고서 HTML 의 '주요 사업' 첫 문장을 대신 보여 준다(길면 잘림).

## 오늘의 주식 퀴즈 (홈, 계산기·공부 바로 위)
- 날마다 4문제: **오늘의 소식** 3개 + 주식 상식(`quiz/questions.json`) 또는 용어(`study/terms.json`) 1개. 보는 사람 브라우저가 한국 날짜로 골라 자정에 바뀐다.
- 오늘의 소식 문제는 사이트를 만들 때(`news_quiz()`·`market_quiz()`) 최근 3일 자료로 자동 생성. 가장 최근 소식부터, 같은 종류는 하루 한 문제. 모자라면 상식 문제로 채운다.
  - 홈페이지 내용: 강세종목(어떤 회사?), 실적 속보 카드(컨센서스 대비·발표 뒤 주가), 국내 '영업이익 급증' 공시, 목표주가 최대 상향·하향
  - 시장 자료: 상한가 종목(kb flow-live map.json, ETF·스팩 제외), 영업이익률 20% 넘는 종목·이자보상비율 1 미만 종목(상승 테마·목표주가 종목을
    study-fin 의 DART 숫자로), 앞으로 7일 실적 발표 예정(증시 캘린더, 이미 발표한 회사 제외), 이번 주 미국 52주 신고가가 아닌 종목(아침 데일리 신고가)
  - 거래대금 상위 10위 밖 종목(kb 장마감 리포트·flow-live snapshot.json 의 `/api/top-value`, 2026-10-26 장부터 쌓임)
- 사용자가 "퀴즈 추가해줘"라고 하면 `quiz/questions.json` 끝에 {cat, q, choices[보기 4개], answer(정답 번호 0~3), explain} 를 넣고 merge 한다. 사실은 출처로 확인하고, 정답이 하나만 맞도록 보기를 쓴다(보기 순서는 화면에서 섞인다).
- 참여 수는 방문자 현황(/visits/)의 '오늘의 주식 퀴즈' 칸(c-quiz)에서 본다. 코드: build_site.py 의 `quiz_home()`·`QUIZ_JS`.

## 놀이터 (/play/) · 코스피 오를까 내릴까? (홈, 퀴즈 바로 위)
- 코드 `play_page.py`. 홈 투표: 다음 거래일 코스피가 직전 종가보다 오를지 내릴지(그날 09:00 마감). 채점은 야후 ^KS11 일봉(사이트 만들 때 넣음)으로 보는 사람 브라우저가 한다.
  다른 사람 투표 수는 Abacus `vote-YYYYMMDD-u/d`, 내 기록은 그 기기(localStorage `pd-votes`).
- 게임: 시가총액 대결 · 오늘 더 오른 종목 맞히기. 자료는 kb flow-live `map.json`(시가총액 상위 500, ETF·우선주 제외)을 사이트 만들 때 넣는다. 최고 기록은 그 기기에만, 플레이 수는 방문자 현황 '놀이터 게임'(c-game).
