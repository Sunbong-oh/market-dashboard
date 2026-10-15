"""출근길 음성 브리핑: 오전 데일리(dashboard.py가 남긴 briefing.json)를 2분 안팎의 라디오 원고로 바꿔
한국어 음성(MP3)으로 만들고, 팟캐스트 피드(feed.xml)를 갱신한다.

실행: python briefing.py [--pod DIR] [--notify]
  --pod DIR  팟캐스트 폴더(podcast 브랜치 체크아웃). 오늘 회차 MP3를 넣고 feed.xml을 다시 쓴다.
  --notify   텔레그램으로도 MP3를 보낸다(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
원고만 보고 싶으면 인자 없이 실행 -> briefing.txt, briefing.mp3 생성.

음성: ElevenLabs 키가 있으면 내 목소리(음성 복제), 없으면 Microsoft Edge 온라인 TTS(edge-tts, 키 불필요). 차에서는 팟캐스트 앱(AntennaPod 등)이
FEED_URL을 구독해 두면 안드로이드 오토에서 바로 재생된다.
"""
import asyncio
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, date, timedelta, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from dashboard import load_env  # noqa: E402  (환경변수 또는 .env)
DATA = ROOT / "briefing.json"
TXT = ROOT / "briefing.txt"
MP3 = ROOT / "briefing.mp3"
KST = timezone(timedelta(hours=9))

VOICE = "ko-KR-HyunsuMultilingualNeural"  # 굵은 남성 음성(아나운서 톤)
RATE = "+15%"  # 1.15배속
PITCH = "-8Hz"  # 조금 낮게
SITE = "https://sunbong-oh.github.io/market-dashboard"
FEED_URL = f"{SITE}/podcast/feed.xml"
KEEP = 14  # 피드에 남길 회차 수(오래된 MP3는 지운다)
SHOW_TITLE = "출근길 미국 증시 브리핑"

HOST = "주식쟁이봉"
AI_MOVE = 5.0  # AI 기업 급등락 기준(전일 대비 %)
NH_READ = 15   # 52주 신고가는 시총 큰 순으로 이만큼 이름을 읽고 나머지는 'N종목'으로
# AI 밸류체인 종목(티커: 읽을 이름). 기사 검색에도 이 이름을 쓴다
AI_STOCKS = {
    "NVDA": "엔비디아", "MSFT": "마이크로소프트", "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타",
    "TSLA": "테슬라", "AVGO": "브로드컴", "AMD": "AMD", "MU": "마이크론", "SKHY": "SK하이닉스 ADR",
    "TSM": "TSMC", "INTC": "인텔", "ARM": "ARM", "ASML": "ASML", "MRVL": "마벨", "ORCL": "오라클",
    "PLTR": "팔란티어", "CRWV": "코어위브", "NBIS": "네비우스", "IREN": "아이렌", "SMCI": "슈퍼마이크로",
    "DELL": "델", "ANET": "아리스타", "VRT": "버티브", "LITE": "루멘텀", "COHR": "코히런트",
    "CLS": "셀레스티카", "SNDK": "샌디스크", "WDC": "웨스턴디지털", "STX": "시게이트",
}


# ---------- 읽기 좋은 문장으로 ----------
def speakable(t):
    """기사 제목·캘린더 항목의 한자·기호를 소리 내어 읽기 좋게 바꾼다."""
    t = re.sub(r"\s+:\s+\S+$", "", t)  # '… : 금융' 같은 섹션 꼬리
    t = re.sub(r"\(([\u4e00-\u9fff]+)\)", "", t)  # 조(兆) -> 조
    t = re.sub(r"([가-힣])\s*\([A-Z]{2,6}\)", r"\1", t)  # 아이렌(IREN) -> 아이렌
    t = t.replace("行", "행").replace("發", "발").replace("對", "대").replace("與", "여")
    t = re.sub(r"€([\d.]+)~([\d.]+)억", r"\1억에서 \2억 유로", t)
    t = re.sub(r"€([\d.]+)(억|조)?", lambda m: f"{m.group(1)}{m.group(2) or ''} 유로", t)
    t = re.sub(r"(\d)~(\d)", r"\1에서 \2", t)
    t = re.sub(r"\(~(\d+일)\)", r", \1까지", t)  # (~16일) -> , 16일까지
    t = re.sub(r"\$(\d[\d.,]*)", r"\1달러", t)
    t = re.sub(r"\.{2,}", ", ", t)
    t = t.replace(" / ", ", ").replace("EPS", "주당순이익")
    t = re.sub(r"(^|\s)미 ", r"\1미국 ", t)
    for a, b in (("美", "미국 "), ("中", "중국 "), ("日", "일본 "), ("韓", "한국 "), ("北", "북한 "), ("英", "영국 "),
                 ("獨", "독일 "), ("EU", "유럽연합 "), ("↑", " 상승"), ("↓", " 하락"), ("株", "주"), ("…", ", "),
                 ("⋯", ", "), ("·", ", "), ("&", " 앤 "), ("%p", "%포인트"), ("vs", "대"), ("→", "에서 ")):
        t = t.replace(a, b)
    t = re.sub(r"[\"'“”‘’<>《》「」『』\[\]]", "", t)
    t = re.sub(r"\s*,(\s*,)*", ",", t)
    return re.sub(r"\s+", " ", t).strip(" ,.")


def num(v, d=2):
    """TTS가 자릿수 쉼표를 엉뚱하게 읽지 않도록 쉼표 없이."""
    return f"{v:.{d}f}"


def pct(v, d=2):
    return f"{abs(v):.{d}f}%"


def updown(v, up="올랐", down="내렸", flat="보합이었"):
    return up if v > 0.005 else down if v < -0.005 else flat


def q_of(data, sym):
    return next((q for q in data["quotes"] if q["sym"] == sym), None)


def chg(q):
    return (q["last"] / q["prev"] - 1) * 100


def josa(word, a="은", b="는"):
    """받침 여부로 조사를 고른다. 영문은 읽는 소리(엘·엠·엔·알 등)로, 숫자는 일·삼·육·칠·팔·영으로 판단."""
    c = word.strip()[-1:]
    if "가" <= c <= "힣":
        return a if (ord(c) - 0xAC00) % 28 else b
    return a if c in "013678LMNRlmnr" else b


def gram(t):
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def distinct(titles, seen=(), limit=2, thr=0.4):
    """제목끼리 글자 2-gram이 많이 겹치면(같은 시황 기사의 받아쓰기) 하나만 남긴다."""
    picked, grams = [], [gram(t) for t in seen]
    for t in titles:
        g = gram(t)
        if g and all(len(g & h) / min(len(g), len(h) or 1) < thr for h in grams):
            picked.append(t)
            grams.append(g)
        if len(picked) >= limit:
            break
    return picked


def cleanup_recap(t):
    """'뉴욕증시, ' 머리와 '…나스닥 1.88% 하락' 같은 지수 등락 꼬리를 뗀다(지수는 앞에서 이미 읽음)."""
    t = re.sub(r"^(美|미국)?\s*(뉴욕증시|美증시|뉴욕 증시)\s*[,:]?\s*", "", t)
    t = re.sub(r"\s*(…|⋯|\.{2,}|,)\s*[^…⋯,]*\d+(\.\d+)?%[^…⋯,]*$", "", t)
    return t.strip(" ,.")


# ---------- 원고 ----------
def build_script(data):
    """순서: 나스닥과 이유(+어젯밤 지표 결과) -> 풋콜 -> 주요 지표 -> 실적 -> AI 급등락과 이유(+공통 키워드 해설)
    -> 52주 신고가 -> 오늘·내일 일정."""
    now = datetime.fromisoformat(data["now"])
    sday = date.fromisoformat(data["session_day"])
    wd = "월화수목금토일"
    out = []
    say = out.append

    say(f"{HOST}입니다. {now.month}월 {now.day}일 {wd[now.weekday()]}요일 미증시 브리핑 들어보시죠.")
    expected = now.date() - timedelta(days=1)  # 직전 미국 평일
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    if sday < expected:
        say(f"어젯밤 미국 증시는 쉬었습니다. 마지막 거래일인 {sday.month}월 {sday.day}일 기준입니다.")

    # 1) 나스닥 + 이유 + 어젯밤 발표된 지표 결과(이유가 'CPI 충격'이면 CPI가 실제로 어떻게 나왔는지)
    nas = q_of(data, "^IXIC")
    if nas:
        c = chg(nas)
        word = "상승" if c > 0.005 else "하락" if c < -0.005 else "보합"
        say(f"먼저 나스닥입니다. 나스닥 종합지수는 {pct(c)} {word}한 {nas['last']:.0f}포인트로 마감했습니다.")
    reasons = [cleanup_recap(data["headline"])] if data.get("headline") else []
    reasons += distinct([cleanup_recap(t) for t in data.get("news") or []], seen=reasons, limit=1)
    reasons = [speakable(r) for r in reasons if r]
    if reasons:
        say(f"{'상승' if nas and chg(nas) > 0 else '하락' if nas and chg(nas) < 0 else '등락'} 이유는 "
            + ", 그리고 ".join(reasons) + ", 이렇게 정리됩니다.")
    for item, val in data.get("cal_done") or []:
        say(release_sentence(item, val))

    # 2) 풋콜 비율(수치만)
    pc = data.get("putcall")
    if pc:
        say(f"풋콜 비율은 {num(pc['value'])}입니다.")

    # 3) 주요 지표 등락
    parts = []
    for sym, name in (("^DJI", "다우"), ("^GSPC", "S&P500"), ("^VIX", "VIX"), ("CL=F", "WTI 유가"),
                      ("GC=F", "금"), ("BTC-USD", "비트코인")):
        q = q_of(data, sym)
        if q:
            c = chg(q)
            parts.append(f"{name} {pct(c)} {'상승' if c > 0.005 else '하락' if c < -0.005 else '보합'}")
    t = q_of(data, "^TNX")
    if t:
        bp = (t["last"] - t["prev"]) * 100
        parts.insert(2, f"미국 10년물 금리 {num(t['last'], 2)}%, {abs(bp):.0f}bp {'상승' if bp >= 0.5 else '하락' if bp <= -0.5 else '보합'}"
                     .replace("bp", " 베이시스포인트"))
    if parts:
        say("주요 지표입니다. " + ", ".join(parts) + "입니다.")

    # 4) 실적: 실적 속보(earnings_flash) + 미국 장 전후 발표 대형주
    earn = earnings_sentences(data)
    if earn:
        say("실적 소식입니다.")
        out.extend(earn)

    # 5) AI 기업 급등락 + 이유 + 여러 종목에 겹친 키워드 해설
    movers = data.get("ai_movers")
    if movers:
        say(f"AI 기업 중 {AI_MOVE:.0f}% 넘게 움직인 종목입니다.")
        for m in movers:
            s = f"{m['name']} {pct(m['chg'], 1)} {'급등' if m['chg'] > 0 else '급락'}."
            if m.get("why"):
                s += f" 관련 기사는, {speakable(m['why'])}" + ("" if m["why"].endswith("?") else ".")
            say(s)
        th = data.get("theme")
        if th and th.get("heads"):
            say(f"여러 종목 기사에 공통으로 나온 키워드는 {th['key']}입니다. 기사 흐름을 따라가 보면, "
                + " ".join(f"{speakable(h)}." for h in th["heads"]))
    elif movers is not None:
        say(f"AI 기업 중 {AI_MOVE:.0f}% 넘게 움직인 종목은 없었습니다.")
    if data.get("notes"):  # 아침 루틴이 조사해 둔 해설(briefing_notes/날짜.txt)
        say("자세히 짚어 보겠습니다. " + data["notes"])

    # 6) 52주 신고가(종목명만)
    nh = data.get("new_highs")
    if nh is not None:
        names = nh["names"]
        if names:
            more = len(names) - NH_READ
            say(f"미국 52주 신고가 종목은 {len(names)}개입니다. " + ", ".join(spoken_co(n) for n in names[:NH_READ])
                + (f", 외 {more}종목입니다." if more > 0 else "입니다."))
        else:
            say("미국 52주 신고가 종목은 없었습니다.")

    # 7) 오늘·내일 일정: ★ 핵심 항목만, 수치는 첫 예상치 하나만
    days = []
    for label, items in (("오늘", data.get("cal_today")), ("내일", data.get("cal_tomorrow"))):
        hot = [short_event(e, v) for e, v in items or [] if e.startswith("★")]
        if hot:
            days.append(f"{label}은 " + ", ".join(hot))
    if days:
        say("핵심 일정입니다. " + ". ".join(days) + "입니다.")

    say(f"이상 {HOST}{josa(HOST, '이었', '였')}습니다. 오늘도 안전 운전하세요.")
    return "\n".join(out)


def short_event(item, val):
    """'★TSMC 실적', 'EPS 예상 $4.45' -> 'TSMC 실적, 주당순이익 예상 4.45달러'. 괄호 설명과 둘째 이후 수치는 뺀다."""
    name = speakable(re.sub(r"\([^)]*\)", "", item.lstrip("★")))
    m = re.search(r"(?:\S+\s+)?예상\s+[^,/]+", val or "")
    return f"{name}, {speakable(m.group(0))}" if m else name


REL = re.compile(r"(?:(\S+)\s+)?실제\s+(-?[\d.]+)(%?)(?:,\s*예상\s+(-?[\d.]+)%?)?")


def release_sentence(item, val):
    """'미 9월 소비자물가(CPI)', '실제 3.7%, 예상 3.6%, 이전 3.4% / 근원 실제 2.6%, 예상 2.5%, ...'
    -> '어젯밤 발표된 미국 9월 소비자물가는 3.7%로 예상 3.6%보다 높았고, 근원은 2.6%로 예상 2.5%보다 높았습니다.'"""
    name = speakable(re.sub(r"\([^)]*\)", "", item.lstrip("★")))
    parts = []
    for seg in val.split(" / "):
        m = REL.search(seg)
        if not m:
            continue
        label, act, unit, est = m.group(1), float(m.group(2)), m.group(3), m.group(4)
        s = f"{label + '은 ' if label else ''}{m.group(2)}{unit}"
        if est is not None:
            e = float(est)
            s += f"로 예상 {est}{unit}" + ("보다 높았" if act > e else "보다 낮았" if act < e else "에 부합했")
        else:
            s += "였"
        parts.append(s)
    if not parts:
        return f"어젯밤 발표된 {name}{josa(name)} {speakable(val)}."
    return f"어젯밤 발표된 {name}{josa(name)} " + "고, ".join(parts) + "습니다."


def earnings_sentences(data):
    out, seen = [], set()
    for f in data.get("flashes") or []:
        seen.add(f["company"].upper())
        s = f"{f['company']} {f.get('period', '')} 실적입니다. {f['verdict']}."
        g = (f.get("guidance") or [])[:1]
        if g:
            s += f" 가이던스는 {g[0]}."
        out.append(speakable(s) + ".")
    e = data.get("earnings")
    if e and e["name"].upper() not in seen and e["sym"].upper() not in seen:
        s = f"{e['name']}{josa(e['name'])} {e['when']} 실적을 발표했습니다."
        if e.get("eps_act") is not None and e.get("eps_est"):
            diff = (e["eps_act"] / e["eps_est"] - 1) * 100
            s += (f" 주당순이익은 {num(e['eps_act'])}달러로 예상 {num(e['eps_est'])}달러를 "
                  + ("웃돌았습니다." if diff > 0.05 else "밑돌았습니다." if diff < -0.05 else "충족했습니다."))
        if e.get("px_pct") is not None:
            s += f" 주가는 {e['px_label']} {pct(e['px_pct'])} {updown(e['px_pct'])}습니다."
        out.append(s)
    return out


# ---------- AI 기업 급등락 · 52주 신고가 ----------
CO_CUT = re.compile(r"[\s,]+(S\.p\.A\.|S\.A\.|N\.V\.|p\.l\.c\.|plc|AG|SE|ADS|ADR|Company|Corporation|Incorporated|"
                    r"International|Group|Limited|Ltd\.?|Co\.?|& Co).*$", re.I)


def spoken_co(name):
    """영문 회사명의 법인 꼬리(S.A., p.l.c., International 등)를 떼어 짧게 읽는다."""
    return CO_CUT.sub("", name).strip() or name

def ai_movers(session_day):
    """AI 종목 중 전일 대비 AI_MOVE% 이상 움직인 종목(큰 순, 최대 4개)과 이유가 될 만한 오늘 기사 제목."""
    import dashboard as d
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        qs = list(ex.map(d.fetch_quote, [(n, s, "price", "", "") for s, n in AI_STOCKS.items()]))
    day = lambda t: datetime.fromtimestamp(t, d.US_DAY_TZ).date()
    out = []
    for q in qs:
        if q["ok"] and day(q["pts"][-1][0]) == session_day:  # 그날 거래한 종목만(상장폐지·거래정지 제외)
            c = (q["pts"][-1][1] / q["pts"][-2][1] - 1) * 100
            if abs(c) >= AI_MOVE:
                out.append(dict(sym=q["sym"], name=q["name"], chg=c))
    out = sorted(out, key=lambda m: -abs(m["chg"]))[:4]
    for m in out:
        m["why"], m["heads"] = move_reason(m["name"], m["chg"])
    return out


THEME_STOP = {"주가", "급등", "급락", "폭등", "폭락", "상승", "하락", "미국", "뉴욕증시", "증시", "나스닥", "종목", "투자",
              "AI", "이유", "기업", "오늘", "전망", "우려", "약세", "강세", "마감", "특징주", "시간외", "관련주", "수혜"}


def theme(movers):
    """급등락 종목 2개 이상의 기사에 공통으로 나온 키워드(종목 이름 포함)와, 그 키워드가 든 서로 다른 기사 제목 최대 3개.
    예: 코어위브 회사채 금리 급등 -> 코어위브·네비우스·아이렌이 함께 급락하면 '코어위브' 기사 흐름을 읽는다."""
    if len(movers) < 2:
        return None
    words = lambda t: set(re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", t)) - THEME_STOP
    count = {}
    for m in movers:
        for w in set().union(*(words(h) for h in m["heads"])) if m["heads"] else ():
            count[w] = count.get(w, 0) + 1
    common = [w for w, n in sorted(count.items(), key=lambda x: -x[1]) if n >= 2]
    if not common:
        return None
    key = common[0]
    heads = distinct([h for m in movers for h in m["heads"] if key in h], limit=3, thr=0.35)
    return dict(key=key, heads=heads)


MOVE_WORD = re.compile(r"급등|급락|폭등|폭락|주가|상승|하락|강세|약세|↑|↓|%|뛰|떨어|날개|추락|치솟|곤두박질")


def move_reason(name, c):
    """('{종목} 주가 when:1d' 국내 기사 중 종목명과 주가 움직임이 함께 나온 제목, 그 종목의 오늘 기사 제목들)."""
    import dashboard as d
    items = sorted(d.google_news(f"{name} 주가 when:1d"), key=lambda n: -n["ts"])
    heads = [n["title"] for n in items[:12]]
    why = next((t for t in heads if name.split()[0] in t and MOVE_WORD.search(t)), heads[0] if heads else None)
    return why, heads


def earnings_flashes(now):
    """earnings_flash/*.json(실적 속보) 중 어제·오늘(KST) 발표분."""
    out = []
    for f in sorted((ROOT / "earnings_flash").glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if j.get("day") in (f"{now:%Y-%m-%d}", f"{now - timedelta(days=1):%Y-%m-%d}") and j.get("verdict"):
            out.append(j)
    return out


def calendar_next(now):
    """market_calendar.json에서 내일(다음 평일, KST) 일정과 예상치. [(항목, 수치)]"""
    try:
        cal = json.loads((ROOT / "market_calendar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    d = now.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    ev = cal.get(f"{d:%Y-%m-%d}") or []
    ev = [ev] if isinstance(ev, str) else [str(x) for x in ev]
    try:
        from econ_values import values
    except ImportError:
        values = lambda *_: ""
    return [(e, values(d, e)) for e in ev]


def briefing_notes(now):
    """아침 루틴이 조사해 남긴 해설 briefing_notes/YYYY-MM-DD.txt(있을 때만)."""
    f = ROOT / "briefing_notes" / f"{now:%Y-%m-%d}.txt"
    try:
        return re.sub(r"\s+", " ", f.read_text(encoding="utf-8")).strip() or None
    except OSError:
        return None


def new_highs_names(session_day):
    """newhighs.py가 아침 발송 때 남긴 newhighs.json(같은 기준일)을 쓰고, 없으면 직접 스캔한다. 실패하면 None."""
    import newhighs
    try:
        j = json.loads(newhighs.NAMES_JSON.read_text(encoding="utf-8"))
        if j.get("asof") == f"{session_day:%Y-%m-%d}":
            return j
    except (OSError, ValueError):
        pass
    try:
        return newhighs.scan_names()
    except Exception as e:
        print("신고가 스캔 실패:", type(e).__name__, e, file=sys.stderr)
        return None


# ---------- 음성 ----------
# 내 목소리(ElevenLabs 음성 복제): Secrets에 ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID가 있으면 이걸 먼저 쓰고,
# 없거나 실패하면 기본 음성(edge-tts)으로 만든다. 출력은 둘 다 고정 비트레이트 MP3라 크기로 길이를 계산한다.
ELEVEN_MODEL = "eleven_multilingual_v2"  # 한국어 지원 모델. Secret/환경변수 ELEVENLABS_MODEL로 바꿀 수 있다
ELEVEN_FORMAT, ELEVEN_KBPS = "mp3_44100_64", 64
EDGE_KBPS = 48


def eleven_tts(text, path):
    key, voice = load_env("ELEVENLABS_API_KEY"), load_env("ELEVENLABS_VOICE_ID")
    if not key or not voice:
        return False
    body = json.dumps(dict(text=text, model_id=load_env("ELEVENLABS_MODEL") or ELEVEN_MODEL,
                           voice_settings=dict(stability=0.5, similarity_boost=0.85, style=0.0,
                                               use_speaker_boost=True))).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice)}?output_format={ELEVEN_FORMAT}",
        body, {"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            path.write_bytes(r.read())
    except urllib.error.HTTPError as e:  # 키가 틀렸거나(401) 이번 달 글자 수를 다 썼을 때(401/429) 등
        print("내 목소리(ElevenLabs) 실패:", e.code, e.read()[:300].decode("utf-8", "replace"), file=sys.stderr)
        return False
    except Exception as e:
        print("내 목소리(ElevenLabs) 실패:", type(e).__name__, file=sys.stderr)
        return False
    return path.stat().st_size > 10000


async def _edge(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH).save(str(path))


def synth(text, path, attempts=3):
    """음성 파일을 만들고 비트레이트(kbps)를 돌려준다. 실패하면 None."""
    if eleven_tts(text, path):
        print("음성: 내 목소리(ElevenLabs)")
        return ELEVEN_KBPS
    for i in range(attempts):
        try:
            asyncio.run(_edge(text, path))
            if path.exists() and path.stat().st_size > 10000:
                print(f"음성: 기본 음성({VOICE})")
                return EDGE_KBPS
        except Exception as e:
            print(f"TTS 실패({i + 1}/{attempts}):", type(e).__name__, e, file=sys.stderr)
    return None


def mp3_seconds(path, kbps):
    return round(path.stat().st_size * 8 / (kbps * 1000))


# ---------- 팟캐스트 피드 ----------
def update_feed(pod, mp3, text, now, kbps):
    ep_dir = pod / "episodes"
    ep_dir.mkdir(parents=True, exist_ok=True)
    # 파일명·제목·guid를 회차마다 다르게 한다. 팟캐스트 앱(AntennaPod 등)은 주소나 제목이 같으면
    # 같은 회차로 보고 예전에 받은 파일을 계속 틀기 때문이다.
    name = f"{now:%Y-%m-%d-%H%M}.mp3"
    shutil.copyfile(mp3, ep_dir / name)
    meta_p = pod / "episodes.json"
    try:
        eps = json.loads(meta_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        eps = []
    wd = "월화수목금토일"[now.weekday()]
    title = f"{now.month}/{now.day}({wd}) 미국 증시 브리핑"
    same_day = [e for e in eps if e["file"].startswith(f"{now:%Y-%m-%d}")]
    if same_day:  # 같은 날 다시 만들면 앞의 것을 지우고 새 회차로 바꿔 끼운다
        title += f" ({now:%H:%M} 업데이트)"
        for e in same_day:
            if e["file"] != name:
                (ep_dir / e["file"]).unlink(missing_ok=True)
        eps = [e for e in eps if e not in same_day]
    eps.append(dict(file=name, title=title, pub=now.isoformat(),
                    bytes=(ep_dir / name).stat().st_size, secs=mp3_seconds(ep_dir / name, kbps),
                    desc=text.split("\n")[1] if "\n" in text else text,
                    guid=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}@{now.isoformat()}"))))
    eps.sort(key=lambda e: e["pub"], reverse=True)
    for old in eps[KEEP:]:
        (ep_dir / old["file"]).unlink(missing_ok=True)
    eps = eps[:KEEP]
    meta_p.write_text(json.dumps(eps, ensure_ascii=False, indent=1), encoding="utf-8")

    items = "".join(f'''
  <item>
   <title>{escape(e["title"])}</title>
   <description>{escape(e["desc"])}</description>
   <pubDate>{format_datetime(datetime.fromisoformat(e["pub"]))}</pubDate>
   <guid isPermaLink="false">{e["guid"]}</guid>
   <enclosure url="{SITE}/podcast/episodes/{e["file"]}" length="{e["bytes"]}" type="audio/mpeg"/>
   <itunes:duration>{e["secs"]}</itunes:duration>
  </item>''' for e in eps)
    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
 <channel>
  <title>{SHOW_TITLE}</title>
  <link>{SITE}/</link>
  <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>
  <language>ko-kr</language>
  <description>평일 아침 7시, 나스닥·주요 지표·AI 기업 급등락·52주 신고가를 음성으로 짚어 드립니다. 투자 판단의 참고용입니다.</description>
  <itunes:author>market-dashboard</itunes:author>
  <itunes:explicit>false</itunes:explicit>
  <itunes:block>Yes</itunes:block>
  <lastBuildDate>{format_datetime(now)}</lastBuildDate>{items}
 </channel>
</rss>
'''
    (pod / "feed.xml").write_text(feed, encoding="utf-8")
    print(f"피드 갱신: {len(eps)}회차, 최신 {name}")


# ---------- 텔레그램 ----------
def send_audio(mp3, title):
    from dashboard import split_targets
    token, chat = load_env("TELEGRAM_BOT_TOKEN"), load_env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("텔레그램 설정 없음 -> 음성 발송 건너뜀", file=sys.stderr)
        return
    for target in split_targets(chat):
        bnd = uuid.uuid4().hex
        body = b""
        for k, v in (("chat_id", target), ("title", title), ("performer", SHOW_TITLE)):
            body += f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body += (f'--{bnd}\r\nContent-Disposition: form-data; name="audio"; filename="{mp3.name}"\r\n'
                 f'Content-Type: audio/mpeg\r\n\r\n').encode() + mp3.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendAudio", body,
                                     {"Content-Type": f"multipart/form-data; boundary={bnd}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                ok = json.loads(r.read()).get("ok", False)
        except Exception as e:  # 토큰이 URL에 있어 예외 메시지는 출력하지 않는다
            print("텔레그램 음성 발송 실패:", target, type(e).__name__, getattr(e, "code", ""), file=sys.stderr)
            ok = False
        print(f"텔레그램 음성 발송 {'완료' if ok else '실패'}: {target}")


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(data["now"])
    sday = date.fromisoformat(data["session_day"])
    try:
        data["ai_movers"] = ai_movers(sday)
    except Exception as e:  # 이 칸이 빠져도 나머지 브리핑은 나간다
        print("AI 급등락 실패:", type(e).__name__, e, file=sys.stderr)
    data["new_highs"] = new_highs_names(sday)
    data["theme"] = theme(data.get("ai_movers") or [])
    data["flashes"] = earnings_flashes(now)
    data["cal_tomorrow"] = calendar_next(now)
    data["notes"] = briefing_notes(now)
    text = build_script(data)
    TXT.write_text(text, encoding="utf-8")
    print(f"원고 {len(text)}자 (약 {len(text) / 330:.1f}분)\n" + text)
    if "--text-only" in sys.argv:
        return
    kbps = synth(text, MP3)
    if not kbps:
        sys.exit("음성 생성 실패")
    secs = mp3_seconds(MP3, kbps)
    print(f"음성 생성: {MP3} ({MP3.stat().st_size // 1024}KB, 약 {secs // 60}분 {secs % 60}초)")
    if "--pod" in sys.argv:
        update_feed(Path(sys.argv[sys.argv.index("--pod") + 1]), MP3, text, now, kbps)
    if "--notify" in sys.argv:
        send_audio(MP3, f"{now.month}/{now.day} 출근길 미국 증시 브리핑")


if __name__ == "__main__":
    main()
