"""생각정리 팟캐스트: 홈페이지 Brian's memo(/memo/) 글을 음성으로 만들어 별도 피드에 올린다.

- 출근길 브리핑과 다른 팟캐스트(피드)다. 파일은 memo-podcast 브랜치(feed.xml, episodes/, episodes.json).
  휴대폰 팟캐스트 앱은 FEED_URL(raw.githubusercontent) 을 구독한다.
- memo/index.json 의 글마다 한 회차. 글 내용이 바뀌면(본문 해시가 다르면) 그 회차를 새로 만든다.
- 음성·발음 처리는 briefing.py 와 같다(내 목소리 Secrets 가 있으면 그 목소리, 없으면 기본 음성).

실행: python memo_pod.py --pod DIR [--text-only] [--only 파일이름]
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import briefing  # noqa: E402
from briefing import HOST, PAUSE, mp3_seconds, speakable, synth  # noqa: E402

KST = timezone(timedelta(hours=9))
MEMO = ROOT / "memo"
SITE = "https://sunbong-oh.github.io/market-dashboard"
RAW = "https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/memo-podcast"
FEED_URL = f"{RAW}/feed.xml"
SHOW_TITLE = "생각정리 · Brian's memo"


# ---------- 글 → 원고 ----------
def _text(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _say(t: str) -> str:
    """기호·숫자를 소리 내어 읽기 좋게 (speakable 에 메모용 규칙을 더한다)."""
    t = t.replace("24/7", "투웬티포세븐")
    t = re.sub(r"\((?:\d{6}|\d{14})\)|\s*\d{14}", "", t)  # 종목코드·공시 접수번호는 읽지 않는다
    t = re.sub(r"(?<!\d)([1-4])Q(\d{2})(?!\d)", r"\2년 \1분기", t)  # 3Q26 -> 26년 3분기
    t = re.sub(r"(?<!\d)([1-4])Q(?![\w])", r"\1분기", t)
    t = re.sub(r"(\d{4})\.(\d{2})\.(\d{2})\.?", lambda m: f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일", t)
    for a, b in (("YoY", "전년 대비"), ("QoQ", "전분기 대비"), ("OPM", "영업이익률"), ("TTM", "최근 12개월"),
                 ("ASP", "평균판매가격"), ("~", "에서 "), ("* ", "")):
        t = t.replace(a, b)
    t = re.sub(r"[①-⑳]\s*", "", t)
    t = re.sub(r"(\d{4})-(\d{2})-(\d{2})", lambda m: f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일", t)
    t = re.sub(r"(?<![\d/])(1[0-2]|0?[1-9])/([12]\d|3[01]|0?[1-9])(?![\d/])",
               lambda m: f"{int(m.group(1))}월 {int(m.group(2))}일", t)  # 11/4 -> 11월 4일
    t = re.sub(r"(?<![\w.])-(?=\d)", "마이너스 ", t)
    t = re.sub(r"(\d)\s*bp\b", r"\1 베이시스포인트", t)
    t = re.sub(r"(?<![\w.])[−–](?=\d)", "마이너스 ", t)
    t = re.sub(r"(?<![\w.])\+(?=\d)", "플러스 ", t)
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)  # 5,384 -> 5384
    t = t.replace("−", " 마이너스 ").replace("≈", "약 ").replace("±", "플러스마이너스 ")
    t = speakable(t)
    return t


def script(html: str, item: dict) -> tuple[str, str]:
    """(음성 원고, 피드 설명용 글)."""
    b = re.sub(r"(?s)<style.*?</style>|<script.*?</script>|<svg.*?</svg>|<aside.*?</aside>", "", html)
    b = re.sub(r"(?s)<div class='pf'>.*?</div>|<div class=\"pf\">.*?</div>", "", b)  # 출처·쪽번호 줄
    b = re.sub(r"(?s)<div class='ph'>.*?</div>|<div class=\"ph\">.*?</div>", "", b)  # 머리 띠
    b = re.sub(r"(?s)<p class=['\"](?:src|figt)['\"][^>]*>.*?</p>|<div class=['\"]legend['\"][^>]*>.*?</div>", "", b)
    b = re.sub(r"(?s)<span class=['\"]eyebrow['\"][^>]*>.*?</span>", "", b)
    out: list[str] = []
    seen: set[str] = set()
    b = re.sub(r"(?s)<table.*?</table>", "", b)  # 표는 소리로 읽으면 숫자만 줄줄이 나와서 뺀다(본문이 표의 요점을 말한다)
    for m in re.finditer(r"(?s)<(h1|h2|h3|p|li|div class=['\"]callout['\"])[^>]*>(.*?)</(?:h1|h2|h3|p|li|div)>", b):
        tag, inner = m.group(1), m.group(2)
        if tag == "tr":
            cells = [_text(c) for c in re.findall(r"(?s)<t[hd][^>]*>(.*?)</t[hd]>", inner)]
            cells = [c for c in cells if c]
            if not cells or re.search(r"<th", inner) and not re.search(r"<td", inner):
                continue  # 표 머리 줄은 건너뛴다
            t = ", ".join(cells)
        else:
            t = _text(inner)
        if not t or t in seen or len(t) < 2 or re.match(r"(자료|출처|주)\s*[:：]", t):
            continue
        seen.add(t)
        if tag.startswith("h1"):
            continue  # 제목은 여는 말에서 읽는다
        if tag in ("h2", "h3") and re.match(r"(그림|표)\s*\d", t):
            continue  # 그림 제목은 건너뛴다(그림 설명 문장은 읽는다)
        if tag in ("h2", "h3"):
            out.append(PAUSE * 2 + _say(t) + "." + PAUSE)
        else:
            out.append(_say(t) + ".")
    d = datetime.fromisoformat(item["date"])
    title = item["title"]
    intro = (f"{HOST}의 생각정리입니다. {d.month}월 {d.day}일에 쓴 메모, {_say(title)}. 같이 보시죠." + PAUSE * 2)
    outro = (PAUSE * 2 + "이 메모는 개인적인 생각 정리이고 매수나 매도를 권하는 글이 아닙니다. "
             "숫자와 출처는 홈페이지 메모 원문에서 확인해 주세요. 이상 " + HOST + "이었습니다.")
    body = re.sub(r"\.\.+", ".", "\n".join(out))
    text = intro + "\n" + body + "\n" + outro
    desc = item.get("headline") or item.get("sub") or title
    return text, desc


# 한 회차(MP3 파일)의 크기 한도. GitHub raw 는 10MiB(10,485,760바이트)를 넘는 파일을 audio/mpeg 가 아닌 application/octet-stream 으로 내려 줘서,
# 팟캐스트 앱이 그 회차를 못 받는다(2026-11-22 13.4MB 회차가 앱에 안 보임). 그래서 긴 메모는 문단 사이에서 여러 회차(1/2부…)로 나눈다.
TARGET_BYTES = 7_500_000   # 이만큼 넘으면 다음 문단부터 새 회차(기본 음성 48kbps 로 약 21분)
LIMIT_BYTES = 9_000_000    # 어떤 경우에도 넘지 않는 한도(약 25분)
MIN_TAIL_BYTES = 1_500_000  # 마지막 회차가 이보다 작으면 앞 회차에 합친다(한도 안일 때)


# ---------- 음성 (조각마다 다시 시도) ----------
async def _piece(text: str, rate: str) -> bytes:
    """한 조각을 읽는다. 실패하면 잠깐 쉬고 3번까지 다시, 그래도 안 되면 문장으로 쪼개 읽고 안 되는 문장만 건너뛴다.
    (긴 메모는 조각이 많아 중간에 NoAudioReceived 가 한 번만 나도 briefing.synth 는 처음부터 다시 했다 → 2026-11-06 두 편 실패)"""
    import asyncio
    import edge_tts
    for i in range(3):
        try:
            buf = bytearray()
            async for ch in edge_tts.Communicate(text, briefing.VOICE, rate=rate, pitch=briefing.PITCH).stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            if buf:
                return bytes(buf)
        except Exception as e:
            print(f"  조각 실패({i + 1}/3): {type(e).__name__} {text[:40]!r}", file=sys.stderr)
        await asyncio.sleep(5 * (i + 1))
    sents = re.split(r"(?<=[.?!])\s+", text)
    if len(sents) <= 1:
        print(f"  건너뜀(읽을 수 없음): {text[:80]!r}", file=sys.stderr)
        return b""
    return b"".join([await _piece(x, rate) for x in sents if x.strip()])


def synth_robust(text: str, path: Path) -> tuple[int, list[Path]] | None:
    """음성을 만들어 (비트레이트 kbps, [파일 경로…])로 돌려준다. 길면 문단 사이에서 여러 파일로 나눈다(TARGET_BYTES). 실패하면 None."""
    import asyncio
    if not briefing.load_env("ELEVENLABS_API_KEY"):  # 내 목소리가 없으면 기본 음성을 조각마다 다시 시도하며 만든다
        for a, b in briefing.NAME_SPLIT.items():
            text = text.replace(a, b)
        for pat, b in briefing.SOUND:
            text = re.sub(pat, b, text)
        silence = briefing.SILENCE.read_bytes() if briefing.SILENCE.exists() else b""

        async def run() -> list[bytes]:
            parts: list[bytearray] = [bytearray()]
            for piece in re.split(f"({PAUSE}+)", text):
                cur = parts[-1]
                if piece.startswith(PAUSE):
                    if cur:
                        cur += silence * len(piece)
                        if len(cur) >= TARGET_BYTES:  # 문단이 끝났고 충분히 찼으면 여기서 한 회차를 닫는다
                            parts.append(bytearray())
                    continue
                if re.search(r"[0-9A-Za-z가-힣]", piece):
                    cur += await _piece(piece.strip(), briefing.RATE)
                    if len(cur) >= LIMIT_BYTES:  # 문단 하나가 아주 길어도 한도는 넘지 않게
                        parts.append(bytearray())
            if len(parts) > 1 and len(parts[-1]) < MIN_TAIL_BYTES and len(parts[-2]) + len(parts[-1]) <= LIMIT_BYTES:
                tail = parts.pop()
                parts[-1] += tail
            return [bytes(x) for x in parts if len(x) > 10000]

        chunks = asyncio.run(run())
        if not chunks:
            return None
        out = []
        for i, b in enumerate(chunks, 1):
            f = path.with_name(f"{path.stem}_{i}.mp3")
            f.write_bytes(b)
            out.append(f)
        print(f"음성: 기본 음성({briefing.VOICE}) · {len(out)}개 파일 ({', '.join(f'{f.stat().st_size / 1e6:.1f}MB' for f in out)})")
        return briefing.EDGE_KBPS, out
    kbps = synth(text, path)  # 내 목소리(ElevenLabs): 나누지 않는다(지금은 안 씀)
    return (kbps, [path]) if kbps else None


# ---------- 피드 ----------
def write_feed(pod: Path, eps: list[dict]) -> None:
    now = datetime.now(KST)
    items = "".join(f'''
  <item>
   <title>{escape(e["title"])}</title>
   <description>{escape(e["desc"])}</description>
   <link>{SITE}/memo/{escape(e["memo"])}</link>
   <pubDate>{format_datetime(datetime.fromisoformat(e["pub"]))}</pubDate>
   <guid isPermaLink="false">{e["guid"]}</guid>
   <enclosure url="{RAW}/episodes/{e["file"]}" length="{e["bytes"]}" type="audio/mpeg"/>
   <itunes:duration>{e["secs"]}</itunes:duration>
  </item>''' for e in eps)
    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
 <channel>
  <title>{escape(SHOW_TITLE)}</title>
  <link>{SITE}/memo/</link>
  <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>
  <language>ko-kr</language>
  <description>홈페이지 Brian's memo(시장 점검·생각거리)를 음성으로 읽어 드립니다. 개인적인 생각 정리이며 투자 권유가 아닙니다.</description>
  <itunes:author>market-dashboard</itunes:author>
  <itunes:explicit>false</itunes:explicit>
  <itunes:image href="https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/main/assets/pod-memo.png"/>
  <image><url>https://raw.githubusercontent.com/Sunbong-oh/market-dashboard/main/assets/pod-memo.png</url><title>{escape(SHOW_TITLE)}</title><link>https://sunbong-oh.github.io/market-dashboard/</link></image>
  <itunes:block>Yes</itunes:block>
  <lastBuildDate>{format_datetime(now)}</lastBuildDate>{items}
 </channel>
</rss>
'''
    (pod / "feed.xml").write_text(feed, encoding="utf-8")


def main() -> int:
    pod = Path(sys.argv[sys.argv.index("--pod") + 1]) if "--pod" in sys.argv else ROOT / "_memo_pod"
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    text_only = "--text-only" in sys.argv
    index = json.loads((MEMO / "index.json").read_text(encoding="utf-8"))
    ep_dir = pod / "episodes"
    ep_dir.mkdir(parents=True, exist_ok=True)
    meta_p = pod / "episodes.json"
    try:
        eps = json.loads(meta_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        eps = []
    by_memo: dict[str, list[dict]] = {}  # 메모 하나가 여러 회차(1/2부…)일 수 있다
    for e in eps:
        by_memo.setdefault(e["memo"], []).append(e)
    made = 0
    for item in index:
        f = item["file"]
        if only and f != only:
            continue
        src = MEMO / f
        if not src.exists():
            print("메모 파일 없음:", f)
            continue
        text, desc = script(src.read_text(encoding="utf-8"), item)
        digest = hashlib.sha1(text.encode()).hexdigest()[:10]
        old = by_memo.get(f) or []
        # 글이 그대로이고 파일이 다 있고 한도 안이면 건너뛴다(예전에 한도를 넘게 만든 회차는 다시 만든다)
        if old and all(o.get("hash") == digest and (ep_dir / o["file"]).exists() and o.get("bytes", 0) <= LIMIT_BYTES for o in old) and not text_only:
            continue
        plain = re.sub(f"{PAUSE}+", " ", text).strip()
        print(f"\n=== {f}: 원고 {len(plain)}자 (약 {len(plain) / 330:.1f}분)")
        if text_only:
            print(plain)
            continue
        stem = f.rsplit(".", 1)[0]
        tmp = pod / "_tmp.mp3"
        res = synth_robust(text, tmp)
        if not res:
            print("음성 생성 실패:", f)
            continue
        kbps, files = res
        n = len(files)
        d = datetime.fromisoformat(item["date"])
        base = datetime.fromisoformat((old[0].get("pub") if old else None) or datetime(d.year, d.month, d.day, 21, 0, tzinfo=KST).isoformat())
        new_eps = []
        for i, src_f in enumerate(files, 1):
            name = f"{stem}-{digest}.mp3" if n == 1 else f"{stem}-{digest}-p{i}.mp3"
            shutil.move(src_f, ep_dir / name)
            # 앱은 최신순으로 보여 주므로 1부가 위에 오게 1부일수록 발행 시각을 늦게 둔다
            pub = (base + timedelta(minutes=n - i)).isoformat() if n > 1 else base.isoformat()
            new_eps.append(dict(memo=f, file=name, hash=digest, pub=pub, part=i, parts=n,
                                title=f"{d.month}/{d.day} {item['title']}" + (f" ({i}/{n}부)" if n > 1 else ""),
                                desc=desc if n == 1 else f"({i}/{n}부) {desc}",
                                bytes=(ep_dir / name).stat().st_size, secs=mp3_seconds(ep_dir / name, kbps),
                                guid=str(uuid.uuid5(uuid.NAMESPACE_URL, name))))
            print("음성:", name, f"{new_eps[-1]['bytes'] / 1e6:.1f}MB", new_eps[-1]["secs"], "초")
        for o in old:  # 이름이 바뀐 옛 파일은 지운다
            if o["file"] not in {e["file"] for e in new_eps}:
                (ep_dir / o["file"]).unlink(missing_ok=True)
        by_memo[f] = new_eps
        made += 1
    if text_only:
        return 0
    live = {i["file"] for i in index}
    for f, es in list(by_memo.items()):  # 홈페이지에서 지운 메모는 피드에서도 뺀다
        if f not in live:
            for e in es:
                (ep_dir / e["file"]).unlink(missing_ok=True)
            del by_memo[f]
    eps = sorted((e for es in by_memo.values() for e in es), key=lambda e: (e["pub"], e["memo"]), reverse=True)
    meta_p.write_text(json.dumps(eps, ensure_ascii=False, indent=1), encoding="utf-8")
    write_feed(pod, eps)
    print(f"\n피드: {len(eps)}회차 (이번에 새로 만든 것 {made})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
