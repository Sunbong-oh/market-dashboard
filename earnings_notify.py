"""실적 속보 카드(earnings_flash/*.json)를 홈페이지 카드와 같은 모양의 이미지로 텔레그램에 보낸다.

earnings-flash.yml 이 main 에 카드가 새로 올라오거나 고쳐질 때 실행한다.
  python earnings_notify.py --diff <before_sha> <after_sha>   # 그 push 에서 추가·수정된 카드만
  python earnings_notify.py earnings_flash/20261015-TSMC.json  # 지정한 카드 (확인용)
  python earnings_notify.py --dry ...                          # 보내지 않고 메시지만 출력
이미지는 build_site.earn_card + EARN_CSS 를 Playwright(Chromium)로 찍는다. 실패하면 글로 보낸다.
카드에 "notify": false 가 있거나 발표일이 2일보다 오래됐으면 보내지 않는다.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import build_site as b
import dashboard as d

ROOT = Path(__file__).resolve().parent
SITE = "https://sunbong-oh.github.io/market-dashboard/"
EARN_LIVE = "https://raw.githubusercontent.com/Sunbong-oh/kb-market-report/earnings-live/earnings.json"
SHOT_W = 480   # 폰 화면 폭(CSS px). 2배율로 찍어 글씨를 선명하게


def live_items():
    """kb-market-report 실적 감시의 주가 반응(px). 홈페이지처럼 카드에 붙인다."""
    try:
        with urllib.request.urlopen(EARN_LIVE, timeout=15) as r:
            return {i.get("key"): i for i in json.loads(r.read()).get("items") or []}
    except Exception as e:
        print("주가 반응 조회 실패:", type(e).__name__, file=sys.stderr)
        return {}


def px_html(item):
    rows = (item or {}).get("px") or []
    if not rows:
        return ""

    def pc(v):
        if v is None:
            return ""
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<b class="{cls}">{v:+.2f}%</b>'
    e = escape
    out = "".join(f'<div class="pxr"><span class="pl">{e(r.get("l", ""))}</span> <span class="ps">{e(r.get("s", ""))} {e(r.get("t") or "")}</span> '
                  f'<b>{e(r.get("p", ""))}</b> '
                  + (f'<span class="pr">{e(r.get("ref", ""))} 대비</span> {pc(r.get("c"))}' if r.get("c") is not None else "")
                  + (f' <span class="pr">· 첫 정규장</span> {pc(r.get("d1"))}' if r.get("d1") is not None else "") + "</div>"
                  for r in rows)
    return f'<div class="px"><div class="pxh">📈 실적 발표 후 주가 반응</div>{out}</div>'


def card_page(c, key, item=None):
    card = b.earn_card(c, key)
    px = px_html(item)
    if px:
        card = card.replace("</table>", "</table>" + px, 1)
    root = b.CSS[b.CSS.index(":root{"):].split("}", 1)[0] + "}"
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{root}{b.EARN_CSS}'
            f'body{{margin:0;padding:10px;background:var(--bg);color:var(--text);width:{SHOT_W}px;box-sizing:border-box;word-break:keep-all;'
            f'font-family:"Noto Sans CJK KR","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif}}'
            f'.earn{{margin:0}}.earn a{{text-decoration:none}}.brand{{font-size:11.5px;color:var(--muted);text-align:right;margin-top:6px}}'
            f'</style></head><body>{card}<div class="brand">Brian\'s 투자노트 · sunbong-oh.github.io/market-dashboard</div></body></html>')


def shoot(html, png):
    """카드 HTML -> PNG. CHROME_PATH 가 있으면 그 브라우저를 쓴다."""
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROME_PATH") or None
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=exe)
        pg = br.new_page(viewport={"width": SHOT_W, "height": 400}, device_scale_factor=2)
        pg.set_content(html, wait_until="load")
        pg.screenshot(path=str(png), full_page=True)
        br.close()
    return Path(png).stat().st_size > 5000


def changed(before, after):
    """push 범위에서 추가(A)·수정(M)된 카드 경로와 상태."""
    if not before or set(before) == {"0"}:
        cmd = ["git", "show", "--name-status", "--format=", after]
    else:
        cmd = ["git", "diff", "--name-status", before, after]
    out = subprocess.run(cmd + ["--", "earnings_flash/"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    res = []
    for line in out.splitlines():
        st, _, path = line.partition("\t")
        if st[:1] in "AM" and path.endswith(".json"):
            res.append((ROOT / path, st[:1]))
    return res


def caption(c, update=False):
    head = "🔄 실적 속보 업데이트" if update else "📊 실적 속보"
    t = f"{head} · {c['company']} {c.get('period', '')}".rstrip()
    if c.get("verdict"):
        t += f"\n▶ {c['verdict']}"
    return f"{t}\n자세히: {SITE}"[:1000]


def message(c, update=False):
    head = "🔄 실적 속보 업데이트" if update else "📊 실적 속보"
    lines = [f"{head} · {c['company']} {c.get('period', '')}".rstrip(),
             f"{c.get('day', '')} {c.get('time', '')} 발표".strip()]
    if c.get("verdict"):
        lines += ["", f"▶ {c['verdict']}"]
    if c.get("rows"):
        lines.append("")
        for r in c["rows"]:
            label, value = r[0], r[1]
            comp = r[2] if len(r) > 2 else ""
            judge = r[3] if len(r) > 3 else ""
            s = f"• {label} {value}"
            if judge:
                s += f" — {judge}"
            lines.append(s)
            if comp:
                lines.append(f"   ({comp})")
    if c.get("guidance"):
        lines += ["", "[가이던스·코멘트]"] + [f"• {g}" for g in c["guidance"]]
    lines += ["", f"자세히: {SITE}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--dry", action="store_true", help="보내지 않고 이미지(out_earn/)와 메시지만 만든다")
    ap.add_argument("--text", action="store_true", help="이미지 대신 글로 보낸다")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    items = changed(*a.diff) if a.diff else [(Path(f), "A") for f in a.files]
    today = datetime.now(d.KST).date()
    ok = True
    live = live_items() if items else {}
    shots = ROOT / "out_earn"
    for path, st in items:
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print("카드 읽기 실패:", path, e, file=sys.stderr)
            continue
        if c.get("notify") is False:
            print("notify=false, 건너뜀:", path.name)
            continue
        try:
            if today - date.fromisoformat(c["day"]) > timedelta(days=2):
                print("오래된 카드, 건너뜀:", path.name)
                continue
        except Exception:
            pass
        update = st == "M"
        png = None
        if not a.text:
            shots.mkdir(exist_ok=True)
            png = shots / f"{path.stem}.png"
            try:
                if not shoot(card_page(c, path.stem, live.get(path.stem)), png):
                    png = None
            except Exception as e:
                print("카드 이미지 실패, 글로 보냄:", type(e).__name__, e, file=sys.stderr)
                png = None
        if a.dry:
            print(png or message(c, update), "\n" + caption(c, update), "\n" + "-" * 40)
        elif png:
            ok = d.send_telegram_photo(png, caption(c, update)) and ok
        else:
            ok = d.send_telegram(message(c, update)[:4000]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
