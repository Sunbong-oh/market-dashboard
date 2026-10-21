"""빅테크·반도체 실적 발표를 몇 분 안에 홈페이지와 텔레그램에 알리는 1차 속보.

시간외 감시(afterhours.py)가 5분마다 부른다. SEC 실적 공시(8-K Item 2.02, earnings_sec.recent)가 새로 보이면
  - 텔레그램: ⚡ 실적 발표 감지 + 시간외 주가 반응 + 관련 기사 제목(한국어)
  - 홈페이지: earnings-quick 브랜치의 earnings.json 에 항목을 넣는다 → 홈페이지 '⚡ 실적 발표' 자동 카드
    (kb-market-report 실적 감시와 같은 형식. 같은 key 의 상세 카드 earnings_flash/<key>.json 이 올라오면 그쪽이 대신 보인다)
상세 분석 카드는 매시간 실적 속보 점검(Claude)이 따로 쓴다.
"""
import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import afterhours as ah
import dashboard as d
import earnings_px
import earnings_sec

KST = timezone(timedelta(hours=9))
REPO = os.environ.get("GITHUB_REPOSITORY", "Sunbong-oh/market-dashboard")
BRANCH = "earnings-quick"
PATH = "earnings.json"
API = f"https://api.github.com/repos/{REPO}"
SITE = "https://sunbong-oh.github.io/market-dashboard/"


def gh(method, url, body=None):
    token = os.environ.get("GITHUB_TOKEN")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "earnings-quick",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"{}")


class Quick:
    def __init__(self, dry=False):
        self.dry = dry
        self.sha = None
        self.items = []
        try:
            j = gh("GET", f"{API}/contents/{PATH}?ref={BRANCH}")
            self.sha = j["sha"]
            self.items = json.loads(base64.b64decode(j["content"])).get("items") or []
        except Exception as e:
            print("earnings-quick 브랜치 없음(처음이면 정상):", type(e).__name__, file=sys.stderr)
        self.seen = {i["key"] for i in self.items}

    def save(self):
        now = datetime.now(KST)
        cut = now - timedelta(hours=36)
        self.items = [i for i in self.items if datetime.fromisoformat(i["first_iso"]) >= cut]
        doc = {"updated": now.strftime("%Y-%m-%d %H:%M"), "items": self.items}
        if self.dry:
            print(json.dumps(doc, ensure_ascii=False)[:1500])
            return
        try:
            gh("GET", f"{API}/branches/{BRANCH}")
        except Exception:
            main_sha = gh("GET", f"{API}/git/ref/heads/main")["object"]["sha"]
            gh("POST", f"{API}/git/refs", {"ref": f"refs/heads/{BRANCH}", "sha": main_sha})
        body = {"message": f"earnings-quick {doc['updated']}", "branch": BRANCH,
                "content": base64.b64encode(json.dumps(doc, ensure_ascii=False).encode()).decode()}
        if self.sha:
            body["sha"] = self.sha
        self.sha = gh("PUT", f"{API}/contents/{PATH}", body)["content"]["sha"]

    def check(self):
        """새 실적 공시 → 알림·저장. 기존 항목은 주가 반응만 새로 고친다."""
        new = []
        for r in earnings_sec.recent(hours=12, foreign=False):
            acc = r["acc"].astimezone(KST)
            key = f"{acc:%Y%m%d}-{r['name']}"
            if key in self.seen:
                continue
            self.seen.add(key)
            label = f"{r['name']}(미국 {r['sym']})"
            try:
                px = earnings_px.reaction(r["sym"], label, r["acc"].timestamp())
            except Exception:
                px = None
            arts = []
            try:
                for n in ah.get(f"https://query1.finance.yahoo.com/v1/finance/search?q={r['sym']}&newsCount=8&quotesCount=0").get("news") or []:
                    if n.get("providerPublishTime", 0) >= r["acc"].timestamp() - 3600 and r["sym"] in (n.get("relatedTickers") or []):
                        arts.append({"t": ah.ko(n["title"]), "u": n.get("link", ""), "o": n.get("publisher", ""),
                                     "dt": datetime.fromtimestamp(n["providerPublishTime"], KST).strftime("%m/%d %H:%M")})
            except Exception:
                pass
            item = {"key": key, "day": f"{acc:%Y-%m-%d}", "name": r["name"], "item": r["name"],
                    "detected": f"{datetime.now(KST):%Y-%m-%d %H:%M}", "first": f"{acc:%m/%d %H:%M}",
                    "first_iso": acc.isoformat(timespec="seconds"), "sym": r["sym"],
                    "cons": [f"SEC 실적 공시 {acc:%H:%M} · 상세 분석 카드는 곧 업데이트"],
                    "news": arts[:3] + [{"t": "SEC 공시 원문 (8-K)", "u": r["url"], "o": "SEC", "dt": f"{acc:%m/%d %H:%M}"}],
                    "px": [px] if px else [], "kr": False, "code": None}
            self.items.insert(0, item)
            if datetime.now(timezone.utc) - r["acc"] < timedelta(hours=2):
                new.append(item)          # 늦게 본 공시(2시간 넘음)는 홈페이지에만 올리고 알림은 보내지 않는다
        # 기존 항목 주가 반응 갱신
        for i in self.items:
            if i["key"] in {n["key"] for n in new} or not i.get("sym"):
                continue
            try:
                px = earnings_px.reaction(i["sym"], f"{i['name']}(미국 {i['sym']})",
                                          datetime.fromisoformat(i["first_iso"]).timestamp())
                if px:
                    i["px"] = [px]
            except Exception:
                pass
        if self.items:
            self.save()
        for i in new:
            lines = [f"⚡ 실적 발표 · {i['name']} ({i['first']} 공시)"]
            if i["px"]:
                p = i["px"][0]
                lines.append(f"{p['s']} {p['p']} · 발표 전 종가 대비 {p['c']:+.1f}%")
            lines += [f"└ {a['t']} ({a['o']})" for a in i["news"][:-1][:2]]
            lines += ["", f"상세 분석 카드는 곧 홈페이지에: {SITE}"]
            text = "\n".join(lines)
            if self.dry:
                print(text)
            else:
                d.send_telegram(text)
        return len(new)


if __name__ == "__main__":
    q = Quick(dry=True)
    q.seen = set()     # 확인용: 이미 본 것도 다시
    print("새 공시", q.check())
