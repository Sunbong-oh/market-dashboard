"""출근길 음성 브리핑: 오전 데일리(dashboard.py가 남긴 briefing.json)를 5분 안팎의 라디오 원고로 바꿔
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

VOICE = "ko-KR-InJoonNeural"  # 남성 음성
RATE = "+25%"  # 1.25배속
SITE = "https://sunbong-oh.github.io/market-dashboard"
FEED_URL = f"{SITE}/podcast/feed.xml"
KEEP = 14  # 피드에 남길 회차 수(오래된 MP3는 지운다)
SHOW_TITLE = "출근길 미국 증시 브리핑"

STOCKS = ("AMD", "MU", "SKHY", "PANW", "SPCX", "LITE")
SPOKEN_NAME = {"SKHY": "SK하이닉스 ADR", "SPCX": "스페이스X", "PANW": "팔로알토", "LITE": "루멘텀",
               "MU": "마이크론", "AMD": "AMD"}


# ---------- 읽기 좋은 문장으로 ----------
def speakable(t):
    """기사 제목·캘린더 항목의 한자·기호를 소리 내어 읽기 좋게 바꾼다."""
    t = re.sub(r"\s+:\s+\S+$", "", t)  # '… : 금융' 같은 섹션 꼬리
    t = re.sub(r"\(([\u4e00-\u9fff]+)\)", "", t)  # 조(兆) -> 조
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
    now = datetime.fromisoformat(data["now"])
    sday = date.fromisoformat(data["session_day"])
    wd = "월화수목금토일"
    out = []
    say = out.append

    say(f"KB증권 오선봉 과장입니다. {now.month}월 {now.day}일 {wd[now.weekday()]}요일 미증시 브리핑 들어보시죠.")
    expected = now.date() - timedelta(days=1)  # 직전 미국 평일
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    if sday < expected:
        say(f"어젯밤 미국 증시는 쉬었습니다. 마지막 거래일인 {sday.month}월 {sday.day}일 기준으로 전해 드립니다.")

    # 1) 지수
    idx = [(n, q_of(data, s)) for n, s in (("다우", "^DJI"), ("S&P500", "^GSPC"), ("나스닥", "^IXIC"))]
    idx = [(n, q) for n, q in idx if q]
    if idx:
        parts = [f"{n} {pct(chg(q))} {'상승' if chg(q) > 0.005 else '하락' if chg(q) < -0.005 else '보합'}" for n, q in idx]
        say("먼저 지수입니다. 뉴욕증시 3대 지수는 " + ", ".join(parts) + "으로 마감했습니다.")
        nas = q_of(data, "^IXIC")
        if nas:
            say(f"나스닥 종합지수는 {nas['last']:.0f}포인트입니다.")
        weeks = [f"{n} {pct(q['w1'], 1)} {'상승' if q['w1'] > 0 else '하락'}" for n, q in idx[1:] if q.get("w1") is not None]
        if weeks:
            say("최근 일주일로 보면 " + ", ".join(weeks) + "입니다.")
    if data.get("headline"):
        say(f"오늘 아침 시황 기사 제목은 이렇습니다. {speakable(data['headline'])}.")

    # 2) 뉴스
    news = distinct([cleanup_recap(t) for t in data.get("news") or []], seen=[data.get("headline") or ""])
    if news:
        say("다른 기사들은 " + ", 그리고 ".join(speakable(t) for t in news) + ", 이런 요인들을 짚었습니다.")

    # 3) 금리·변동성·원자재·코인
    say("다음은 주요 지표입니다.")
    t = q_of(data, "^TNX")
    if t:
        d = t["last"] - t["prev"]
        say(f"미국 10년물 국채 금리는 {num(t['last'], 3)}%로, 전날보다 {abs(d * 100):.1f}bp "
            f"{'올랐' if d > 0.0005 else '내렸' if d < -0.0005 else '변동이 없었'}습니다.".replace("bp", " 베이시스포인트"))
    v = q_of(data, "^VIX")
    if v:
        lv = v["last"]
        mood = "안정" if lv < 15 else "보통" if lv < 20 else "불안" if lv < 30 else "공포"
        say(f"변동성 지수 VIX는 {num(lv)}로 {pct(chg(v))} {updown(chg(v))}고, {mood} 구간입니다.")
    for sym, name in (("CL=F", "WTI 유가"), ("GC=F", "금 값"), ("BTC-USD", "비트코인")):
        q = q_of(data, sym)
        if q:
            d0 = 0 if sym == "BTC-USD" else 2
            c = chg(q)
            move = f"{pct(c)} {updown(c)}습니다" if abs(c) >= 0.005 else "전날과 비슷합니다"
            say(f"{name}{josa(name)} {num(q['last'], d0)}달러로 {move}.")

    # 4) 심리
    fg, pc = data.get("fear_greed"), data.get("putcall")
    if fg and fg.get("score") is not None:
        s = f"CNN 공포탐욕지수는 {round(fg['score'])}, {fg['rating']} 단계입니다."
        if fg.get("prev") is not None:
            s += f" 전날은 {round(fg['prev'])}, 일주일 전은 {round(fg['week'])}였습니다."
        say(s)
    if pc:
        sig = {"sell": " 콜옵션 쏠림이 커서 과열 신호, 적극 매도 구간입니다.",
               "buy": " 풋옵션 쏠림이 커서 공포 신호, 적극 매수 구간입니다."}.get(pc["signal"], " 정상 범위입니다.")
        say(f"풋콜 비율은 {num(pc['value'])}로{sig}")

    # 5) 관심 종목
    qs = [(SPOKEN_NAME[s], chg(q)) for s in STOCKS for q in [q_of(data, s)] if q]
    if qs:
        ups = [f"{n} {pct(c)}" for n, c in sorted(qs, key=lambda x: -x[1]) if c > 0.005]
        downs = [f"{n} {pct(c)}" for n, c in sorted(qs, key=lambda x: x[1]) if c < -0.005]
        say("관심 종목입니다.")
        if ups:
            say("오른 종목은 " + ", ".join(ups) + " 상승.")
        if downs:
            say("내린 종목은 " + ", ".join(downs) + " 하락.")
        big = max(qs, key=lambda x: abs(x[1]))
        if abs(big[1]) >= 5:
            say(f"특히 {big[0]}{josa(big[0], '이', '가')} {pct(big[1], 1)} {'급등' if big[1] > 0 else '급락'}한 점이 눈에 띕니다.")

    # 6) 실적
    e = data.get("earnings")
    if e:
        s = f"실적 소식입니다. {e['name']}{josa(e['name'])} {e['when']} 실적을 발표했습니다."
        if e.get("eps_act") is not None and e.get("eps_est"):
            diff = (e["eps_act"] / e["eps_est"] - 1) * 100
            word = "웃돌았" if diff > 0.05 else "밑돌았" if diff < -0.05 else "부합했"
            s += (f" 주당순이익은 {num(e['eps_act'])}달러로, 시장 예상 {num(e['eps_est'])}달러를 "
                  + (f"{pct(diff, 1)} {word}습니다." if word != "부합했" else "부합했습니다."))
        elif e.get("eps_est"):
            s += f" 주당순이익 예상치는 {num(e['eps_est'])}달러이고, 실제치는 아직 집계 전입니다."
        if e.get("rev"):
            s += f" 매출은 {e['rev'] / 1e8:.0f}억 달러입니다."
        if e.get("px_pct") is not None:
            s += f" 주가는 {e['px_label']} 기준 {pct(e['px_pct'])} {updown(e['px_pct'])}습니다."
        say(s)

    # 7) 어젯밤 발표 결과, 한국 시장 영향 뉴스, 오늘 일정
    done = data.get("cal_done") or []
    if done:
        say("어젯밤 발표된 지표 결과입니다.")
        for item, val in done:
            say(f"{speakable(item.lstrip('★'))}, {speakable(val)}.")
    kr = [speakable(t) for t in data.get("kr") or []]
    if kr:
        say("오늘 한국 시장에 영향을 줄 만한 뉴스입니다. " + " ".join(f"{t}." for t in kr))
    today = data.get("cal_today") or []
    if today:
        say("오늘 챙겨 볼 일정입니다. 한국 시간으로 오늘 밤부터 내일 새벽 사이 발표가 많습니다.")
        for item, val in today:
            hot = "핵심 일정, " if item.startswith("★") else ""
            say(f"{hot}{speakable(item.lstrip('★'))}" + (f", {speakable(val)}" if val else "") + ".")

    rest = week_rest(now)
    if rest:
        say("이번 주 남은 일정도 짚어 보겠습니다. " + " ".join(rest))

    say(wrap_up(data))
    say("이상 출근길 미국 증시 브리핑이었습니다. 자료는 투자 판단의 참고용입니다. 오늘도 안전 운전하세요.")
    return "\n".join(out)


def week_rest(now):
    """market_calendar.json에서 내일부터 이번 주 금요일까지의 ★ 핵심 일정(없으면 첫 항목)."""
    try:
        cal = json.loads((ROOT / "market_calendar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out, d = [], now.date() + timedelta(days=1)
    while d.weekday() < 5:
        ev = cal.get(f"{d:%Y-%m-%d}") or []
        ev = [ev] if isinstance(ev, str) else ev
        hot = [e.lstrip("★") for e in ev if e.startswith("★")] or ev[:1]
        if hot:
            out.append(f"{d.day}일 {'월화수목금토일'[d.weekday()]}요일은 {speakable(', '.join(hot))}.")
        d += timedelta(days=1)
    return out


def wrap_up(data):
    """한 줄 정리: 나스닥 방향 + 금리·VIX·공포탐욕으로 본 분위기."""
    nas, vix, tnx = q_of(data, "^IXIC"), q_of(data, "^VIX"), q_of(data, "^TNX")
    if not nas:
        return "오늘도 지표와 일정 확인하시면서 차분하게 대응하시기 바랍니다."
    c = chg(nas)
    tone = ("기술주 중심으로 크게 밀린" if c <= -1 else "약세를 보인" if c < -0.2 else
            "강하게 오른" if c >= 1 else "강세를 보인" if c > 0.2 else "방향 없이 쉬어 간")
    s = f"정리하면, 어젯밤 미국 증시는 {tone} 하루였습니다."
    if vix and chg(vix) >= 8:
        s += " 변동성 지수가 크게 뛰어 불안 심리가 커진 만큼, 오늘 국내 증시도 개장 초 변동성에 유의하시기 바랍니다."
    elif tnx and abs(tnx["last"] - tnx["prev"]) >= 0.05:
        s += " 금리 움직임이 컸던 만큼 성장주 흐름을 함께 살펴보시기 바랍니다."
    else:
        s += " 오늘 국내 증시에서는 반도체 등 관련 업종의 흐름을 함께 확인해 보시기 바랍니다."
    return s


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
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))


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
    name = f"{now:%Y-%m-%d}.mp3"
    shutil.copyfile(mp3, ep_dir / name)
    meta_p = pod / "episodes.json"
    try:
        eps = json.loads(meta_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        eps = []
    wd = "월화수목금토일"[now.weekday()]
    eps = [e for e in eps if e["file"] != name]
    eps.append(dict(file=name, title=f"{now.month}/{now.day}({wd}) 미국 증시 브리핑", pub=now.isoformat(),
                    bytes=(ep_dir / name).stat().st_size, secs=mp3_seconds(ep_dir / name, kbps),
                    desc=text.split("\n")[1] if "\n" in text else text, guid=str(uuid.uuid5(uuid.NAMESPACE_URL, name))))
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
  <description>평일 아침 7시, 오전 데일리 마켓을 5분 음성으로 읽어 드립니다. 투자 판단의 참고용입니다.</description>
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
