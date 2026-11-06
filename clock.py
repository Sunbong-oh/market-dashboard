"""정시 알람 (us_live.py 이어달리기 안에서 1분마다 tick).

GitHub 자체 schedule 은 이 저장소에서 몇 시간씩 늦게 돌아, 정해진 시각에 워크플로를 깨우는 일을
Claude 예약 작업이 해 왔다. 그 일은 Claude 가 필요 없으므로(파일 하나 올리기·워크플로 실행) 늘 떠 있는
us-live 실행이 대신한다 → Claude 사용 한도와 상관없이 돈다.

- 06:57 KST 화~토   오전 데일리(daily-dashboard.yml, auto=true → '이미 보냄' 검사)
- 07:20 KST 화~토   출근길 음성 점검: 팟캐스트 피드에 오늘 회차가 없으면 음성만(이미 데일리를 보냈으면) 또는 데일리 전체 다시
- 15:57 KST 월~금   KB 장마감 리포트(kb-market-report trigger/close-request.txt 커밋, Secret CLOSE_REPO_TOKEN 필요)
- 21:55 KST 월~금   실시간 시세(live-prices.yml)
- 03:45·15:45 ET 월~금  시간외 급등락 감시(afterhours.yml, 이미 도는 중이면 건너뜀)

같은 알람을 두 번 울리지 않도록, 알람 시각 뒤에 이미 그 워크플로의 workflow_dispatch 실행이 있으면 건너뛴다
(이어달리기 교대 때 새 실행이 다시 울리지 않게). 알람 시각에서 20분이 지나면 울리지 않는다.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
REPO = os.environ.get("GITHUB_REPOSITORY", "Sunbong-oh/market-dashboard")
FEED = "https://sunbong-oh.github.io/market-dashboard/podcast/feed.xml"
LATE = timedelta(minutes=20)

# (이름, 시간대, 요일(월=0), "HH:MM")
ALARMS = [
    ("daily", KST, (1, 2, 3, 4, 5), "06:57"),
    ("podcast", KST, (1, 2, 3, 4, 5), "07:20"),
    ("close", KST, (0, 1, 2, 3, 4), "15:57"),
    ("live", KST, (0, 1, 2, 3, 4), "21:55"),
    ("afterhours", ET, (0, 1, 2, 3, 4), "03:45"),
    ("afterhours", ET, (0, 1, 2, 3, 4), "15:45"),
]

_done: set[str] = set()


def gh(*args: str, token: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, env=env)


def runs_since(wf: str, since: datetime, event: str = "workflow_dispatch") -> list[dict]:
    iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = gh("api", f"repos/{REPO}/actions/workflows/{wf}/runs?event={event}&created=>={iso}&per_page=20")
    if r.returncode:
        raise RuntimeError(r.stderr[-200:])
    return json.loads(r.stdout).get("workflow_runs", [])


def dispatch(wf: str, *fields: str) -> str:
    args = ["workflow", "run", wf, "--repo", REPO, "--ref", "main"]
    for f in fields:
        args += ["-f", f]
    r = gh(*args)
    return "ok" if r.returncode == 0 else "실패 " + r.stderr.strip()[-200:]


def sent_daily_today(now_kst: datetime) -> bool:
    """오늘 아침(05:00 KST 뒤) 데일리 발송 단계를 성공한 실행이 있나."""
    ws = now_kst.replace(hour=5, minute=0, second=0, microsecond=0)
    for ev in ("workflow_dispatch", "push", "schedule"):
        for run in runs_since("daily-dashboard.yml", ws, ev):
            r = gh("api", f"repos/{REPO}/actions/runs/{run['id']}/jobs",
                   "--jq", '[.jobs[].steps[]? | select(.name=="Build dashboard and send to Telegram" and .conclusion=="success")] | length')
            if r.stdout.strip() not in ("", "0"):
                return True
    return False


def podcast_feed(at: datetime) -> str:
    """오늘 회차가 있는지 볼 피드. 홈페이지(/podcast/feed.xml)는 site.yml 이 다시 만들어야 바뀌어서
    07:20에 아직 옛 피드일 때가 있다(2026-11-06: 07:03에 만든 회차를 못 보고 07:21에 다시 만듦)
    → podcast 브랜치의 feed.xml 을 직접 읽고, 못 읽으면 홈페이지 피드를 본다."""
    r = gh("api", f"repos/{REPO}/contents/feed.xml?ref=podcast", "-H", "Accept: application/vnd.github.raw")
    if r.returncode == 0 and "<rss" in r.stdout:
        return r.stdout
    return urllib.request.urlopen(f"{FEED}?t={int(at.timestamp())}", timeout=20).read().decode("utf-8", "replace")


def run_alarm(name: str, at: datetime) -> str:
    if name == "daily":
        if runs_since("daily-dashboard.yml", at - timedelta(minutes=2)):
            return "이미 실행됨"
        return dispatch("daily-dashboard.yml", "auto=true", "telegram=true")
    if name == "podcast":
        d = at.astimezone(KST).strftime("%Y-%m-%d")
        feed = podcast_feed(at)
        if f"episodes/{d}-" in feed:
            return "오늘 회차 있음"
        if runs_since("daily-dashboard.yml", at - timedelta(minutes=2)):
            return "이미 다시 실행함"
        if sent_daily_today(at.astimezone(KST)):
            return "음성만 다시: " + dispatch("daily-dashboard.yml", "podcast_only=true", "telegram=false")
        return "데일리 전체 다시: " + dispatch("daily-dashboard.yml", "auto=true", "telegram=true")
    if name == "live":
        if runs_since("live-prices.yml", at - timedelta(minutes=2)):
            return "이미 실행됨"
        return dispatch("live-prices.yml")
    if name == "afterhours":
        for st in ("in_progress", "queued"):
            r = gh("api", f"repos/{REPO}/actions/workflows/afterhours.yml/runs?status={st}&per_page=5", "--jq", ".total_count")
            if r.stdout.strip() not in ("", "0"):
                return f"이미 {st}"
        if runs_since("afterhours.yml", at - timedelta(minutes=2)):
            return "이미 실행됨"
        return dispatch("afterhours.yml")
    if name == "close":
        return close_report(at)
    return "모르는 알람"


def close_report(at: datetime) -> str:
    """kb-market-report 의 trigger/close-request.txt 를 고쳐 커밋한다(push 가 close-report.yml 을 깨운다).
    GITHUB_TOKEN 커밋은 워크플로를 깨우지 않으므로 Secret CLOSE_REPO_TOKEN(쓰기 권한)이 있어야 한다."""
    token = os.environ.get("CLOSE_REPO_TOKEN", "")
    if not token:
        return "CLOSE_REPO_TOKEN 없음 → 건너뜀"
    repo, path = "Sunbong-oh/kb-market-report", "trigger/close-request.txt"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "clock"}
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        cur = json.loads(urllib.request.urlopen(urllib.request.Request(url + "?ref=main", headers=hdr), timeout=20).read())
        sha = cur.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return f"읽기 실패 HTTP {e.code}"
        sha = None
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"message": f"trigger: close report {ts}", "branch": "main",
            "content": base64.b64encode(f"close report requested at {ts} (UTC) by clock\n".encode()).decode()}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="PUT")
    try:
        urllib.request.urlopen(req, timeout=20)
        return "커밋 ok"
    except urllib.error.HTTPError as e:
        return f"커밋 실패 HTTP {e.code} {e.read()[:150]!r}"


def tick(now: datetime) -> None:
    for name, tz, days, hm in ALARMS:
        local = now.astimezone(tz)
        h, m = map(int, hm.split(":"))
        at = local.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{name}-{at:%Y%m%d%H%M}"
        if local.weekday() not in days or key in _done or not (at <= local < at + LATE):
            continue
        _done.add(key)
        try:
            res = run_alarm(name, at)
        except Exception as e:
            res = f"오류 {type(e).__name__} {e}"
        print(now.astimezone(KST).strftime("%H:%M"), f"⏰ {name} ({hm} {tz.key}):", res, flush=True)


if __name__ == "__main__":  # 시험: python clock.py <name>  → 그 알람을 지금 시각으로 바로 울린다
    import sys
    print(run_alarm(sys.argv[1], datetime.now(KST)))
