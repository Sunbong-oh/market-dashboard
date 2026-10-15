"""실적 속보 카드(earnings_flash/*.json)를 텔레그램으로 보낸다.

earnings-flash.yml 이 main 에 카드가 새로 올라오거나 고쳐질 때 실행한다.
  python earnings_notify.py --diff <before_sha> <after_sha>   # 그 push 에서 추가·수정된 카드만
  python earnings_notify.py earnings_flash/20261015-TSMC.json  # 지정한 카드 (확인용)
  python earnings_notify.py --dry ...                          # 보내지 않고 메시지만 출력
카드에 "notify": false 가 있거나 발표일이 2일보다 오래됐으면 보내지 않는다.
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import dashboard as d

ROOT = Path(__file__).resolve().parent
SITE = "https://sunbong-oh.github.io/market-dashboard/"


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
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    items = changed(*a.diff) if a.diff else [(Path(f), "A") for f in a.files]
    today = datetime.now(d.KST).date()
    ok = True
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
        text = message(c, update=(st == "M"))
        if a.dry:
            print(text, "\n" + "-" * 40)
        else:
            ok = d.send_telegram(text[:4000]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
