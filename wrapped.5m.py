#!/usr/bin/env python3
# <xbar.title>Menubar Wrapped</xbar.title>
# <xbar.version>v0.1</xbar.version>
# <xbar.author>yozmbread</xbar.author>
# <xbar.author.github>yozmbread</xbar.author.github>
# <xbar.desc>Commit streak, today's calendar and D-days in the menu bar, plus a year-in-review page.</xbar.desc>
# <xbar.dependencies>python3, git, icalBuddy (optional)</xbar.dependencies>
"""SwiftBar plugin. Run with --wrapped to build the year page, --selfcheck to test."""
import collections
import datetime as dt
import html
import os
import re
import shutil
import subprocess
import sys

# ---- config ---------------------------------------------------------------
REPO_ROOTS = ["~/Desktop/Projects"]  # folders scanned (2 levels deep) for git repos
AUTHOR_EMAIL = ""  # empty = your global git user.email
DDAYS = {"Internship": "2027-09-01"}
# ---------------------------------------------------------------------------

EXTRA_PATH = ["/opt/homebrew/bin", "/usr/local/bin"]  # SwiftBar runs with a minimal PATH
OUT_DIR = os.path.expanduser("~/.cache/menubar-wrapped")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def run(cmd, cwd=None):
    env = dict(os.environ, PATH=os.pathsep.join([os.environ.get("PATH", "")] + EXTRA_PATH))
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def find_repos():
    repos = []
    for root in REPO_ROOTS:
        root = os.path.expanduser(root)
        for base, dirs, _ in os.walk(root):
            if ".git" in dirs:
                repos.append(base)
                dirs[:] = []  # don't descend into a repo
            elif base.count(os.sep) - root.count(os.sep) >= 2:
                dirs[:] = []
    return sorted(repos)


def commits(since):
    """[(repo_name, datetime)] for the author since `since` (a date)."""
    email = AUTHOR_EMAIL or run(["git", "config", "--global", "user.email"]).strip()
    out = []
    for repo in find_repos():
        log = run(["git", "log", "--all", f"--author={email}", f"--since={since.isoformat()}",
                   "--pretty=%at"], cwd=repo)
        out += [(os.path.basename(repo), dt.datetime.fromtimestamp(int(t))) for t in log.split()]
    return out


def streak(days, today):
    """Consecutive commit days ending today, or yesterday if nothing yet today."""
    day = today if today in days else today - dt.timedelta(days=1)
    n = 0
    while day in days:
        n += 1
        day -= dt.timedelta(days=1)
    return n


def ddays(today):
    return sorted(((dt.date.fromisoformat(d) - today).days, name) for name, d in DDAYS.items())


EVENT_RE = re.compile(r"(\d{4}-\d{2}-\d{2}) at (\d{2}:\d{2})"
                      r"(?: - (?:(\d{4}-\d{2}-\d{2}) at )?(\d{2}:\d{2}))?\t(.*)")


def parse_events(text):
    """icalBuddy lines -> [(start, end, title)]."""
    events = []
    for line in text.splitlines():
        m = EVENT_RE.match(line.strip())
        if not m:
            continue
        d1, t1, d2, t2, title = m.groups()
        start = dt.datetime.fromisoformat(f"{d1} {t1}")
        end = dt.datetime.fromisoformat(f"{d2 or d1} {t2 or t1}")
        events.append((start, end, title.strip()))
    return events


def calendar(start, end):
    """Timed events between two dates, or None if icalBuddy isn't installed."""
    exe = shutil.which("icalBuddy", path=os.pathsep.join([os.environ.get("PATH", "")] + EXTRA_PATH))
    if not exe:
        return None
    text = run([exe, "-nc", "-nrd", "-ea", "-npn", "-b", "", "-iep", "datetime,title",
                "-po", "datetime,title", "-ps", "|\t|", "-df", "%Y-%m-%d", "-tf", "%H:%M",
                f"eventsFrom:{start.isoformat()}", f"to:{end.isoformat()}"])
    return parse_events(text)


def clean(s):
    return s.replace("|", "/")  # '|' would start SwiftBar params


def menu():
    now = dt.datetime.now()
    today = now.date()
    week_start = today - dt.timedelta(days=today.weekday())
    cs = commits(today - dt.timedelta(days=400))
    days = {t.date() for _, t in cs}
    today_cs = [r for r, t in cs if t.date() == today]
    week_n = sum(t.date() >= week_start for _, t in cs)
    s = streak(days, today)
    dd = ddays(today)
    next_dd = next(((n, name) for n, name in dd if n >= 0), None)

    title = f":flame: {s}d · {len(today_cs)} commits"
    if next_dd:
        title += f" · D-{next_dd[0]}"
    print(title)
    print("---")
    print("Coding | color=gray")
    print(f"Today: {len(today_cs)} commits · This week: {week_n}")
    print(f"Streak: {s} days")
    for repo, n in collections.Counter(today_cs).most_common():
        path = next(p for p in find_repos() if os.path.basename(p) == repo)
        print(f'-- {clean(repo)}: {n} | bash=/usr/bin/open param0="{path}" terminal=false')
    print("---")
    print("Calendar | color=gray")
    events = calendar(week_start, week_start + dt.timedelta(days=6))
    if events is None:
        print("Install icalBuddy: brew install ical-buddy")
    else:
        upcoming = [e for e in events if e[0].date() == today and e[1] >= now][:3]
        for start, _, name in upcoming:
            print(f"{start:%H:%M}  {clean(name)}")
        if not upcoming:
            print("Nothing left today")
        hours = sum((e - b).total_seconds() for b, e, _ in events) / 3600
        print(f"This week: {len(events)} events, {hours:.1f}h")
    print("---")
    print("D-day | color=gray")
    for n, name in dd:
        print(f"{clean(name)}: " + (f"D-{n}" if n > 0 else "today" if n == 0 else f"D+{-n}"))
    print("---")
    me = os.path.abspath(__file__)
    print(f'Open My Wrapped | bash="{sys.executable}" param0="{me}" param1=--wrapped terminal=false')
    print("Refresh | refresh=true")


def heatmap_svg(counts, year):
    cell, gap = 11, 3
    first = dt.date(year, 1, 1)
    start = first - dt.timedelta(days=first.weekday())
    top = max(counts.values(), default=1)
    rects = []
    day = start
    while day.year <= year:
        if day.year == year:
            n = counts.get(day, 0)
            level = 0 if n == 0 else 1 + min(3, int(3 * n / top))
            week = (day - start).days // 7
            rects.append(f'<rect x="{week * (cell + gap)}" y="{day.weekday() * (cell + gap)}" '
                         f'width="{cell}" height="{cell}" rx="2" class="l{level}">'
                         f'<title>{day:%b %d}: {n}</title></rect>')
        day += dt.timedelta(days=1)
    w = 54 * (cell + gap)
    return f'<svg viewBox="0 0 {w} {7 * (cell + gap)}" role="img" aria-label="Commit heatmap">{"".join(rects)}</svg>'


def wrapped_stats(cs, events, year):
    """Plain numbers for the page; no event titles leave this function."""
    cs = [(r, t) for r, t in cs if t.year == year]
    stats = {"total": len(cs), "days": len({t.date() for _, t in cs})}
    if cs:
        stats["repo"], stats["repo_n"] = collections.Counter(r for r, _ in cs).most_common(1)[0]
        stats["weekday"] = WEEKDAYS[collections.Counter(t.weekday() for _, t in cs).most_common(1)[0][0]]
        stats["hour"] = collections.Counter(t.hour for _, t in cs).most_common(1)[0][0]
        stats["longest"] = longest_streak({t.date() for _, t in cs})
    if events:
        month, n = collections.Counter(b.month for b, _, _ in events).most_common(1)[0]
        stats["events"] = len(events)
        stats["event_hours"] = sum((e - b).total_seconds() for b, e, _ in events) / 3600
        stats["busy_month"], stats["busy_month_n"] = MONTHS[month - 1], n
    stats["heat"] = collections.Counter(t.date() for _, t in cs)
    return stats


def longest_streak(days):
    best = 0
    for d in days:
        if d - dt.timedelta(days=1) not in days:
            n = 1
            while d + dt.timedelta(days=n) in days:
                n += 1
            best = max(best, n)
    return best


def wrapped():
    year = dt.date.today().year
    cs = commits(dt.date(year, 1, 1))
    events = calendar(dt.date(year, 1, 1), dt.date(year, 12, 31)) or []
    s = wrapped_stats(cs, events, year)
    cards = [("Your year in code", f"{s['total']}", f"commits across {s['days']} days")]
    if "repo" in s:
        cards += [
            ("Your top project", html.escape(s["repo"]), f"{s['repo_n']} commits"),
            ("You code most on", f"{s['weekday']}s", f"usually around {s['hour']:02d}:00"),
            ("Longest streak", f"{s['longest']}", "days in a row"),
        ]
    if "events" in s:
        cards += [
            ("On your calendar", f"{s['events']}", f"events, {s['event_hours']:.0f} hours"),
            ("Busiest month", s["busy_month"], f"{s['busy_month_n']} events"),
        ]
    for n, name in ddays(dt.date.today()):
        if n >= 0:
            cards.append(("Coming up", html.escape(name), f"in {n} days"))
            break
    body = "".join(f'<section class="card c{i % 4}"><p class="k">{k}</p><h2>{v}</h2><p>{sub}</p></section>'
                   for i, (k, v, sub) in enumerate(cards))
    body += f'<section class="card heat"><p class="k">Every commit of {year}</p>{heatmap_svg(s["heat"], year)}</section>'
    page = PAGE.replace("{{YEAR}}", str(year)).replace("{{BODY}}", body)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "wrapped.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>My {{YEAR}} Wrapped</title>
<style>
:root{--bg:#0b0b10;--fg:#f5f5f7;--muted:#a1a1aa;--l0:#26262e;--l1:#0e4429;--l2:#006d32;--l3:#26a641;--l4:#39d353}
*{box-sizing:border-box}html{scroll-snap-type:y mandatory}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 -apple-system,system-ui,sans-serif}
.card{min-height:100vh;scroll-snap-align:start;display:flex;flex-direction:column;justify-content:center;padding:0 16px;
 max-width:720px;margin:0 auto}
.card h2{font-size:clamp(48px,14vw,120px);margin:0;line-height:1;letter-spacing:-.03em;overflow-wrap:anywhere}
.card p{font-size:clamp(18px,4vw,26px);color:var(--muted);margin:.6em 0}.card .k{text-transform:uppercase;
 letter-spacing:.12em;font-size:14px;font-weight:600}
.c0 h2{color:#1ed760}.c1 h2{color:#ff6ec7}.c2 h2{color:#ffd23f}.c3 h2{color:#7aa2ff}
.heat svg{width:100%;height:auto}.l0{fill:var(--l0)}.l1{fill:var(--l1)}.l2{fill:var(--l2)}.l3{fill:var(--l3)}.l4{fill:var(--l4)}
@media (prefers-reduced-motion:no-preference){.card h2{animation:up .7s ease both;animation-timeline:view();animation-range:entry 0% cover 35%}}
@keyframes up{from{opacity:0;transform:translateY(40px)}}
</style></head><body>{{BODY}}</body></html>"""


def selfcheck():
    d = dt.date(2026, 10, 21)
    one = dt.timedelta(days=1)
    assert streak({d, d - one, d - 2 * one}, d) == 3
    assert streak({d - one, d - 2 * one}, d) == 2  # no commit yet today keeps the streak
    assert streak({d - 2 * one}, d) == 0
    assert longest_streak({d, d + one, d + 3 * one}) == 2
    ev = parse_events("2026-10-21 at 10:00 - 11:30\tStats lecture\n"
                      "2026-10-21 at 23:00 - 2026-10-22 at 01:00\tNight shift\njunk line")
    assert [round((e - b).total_seconds() / 3600, 1) for b, e, _ in ev] == [1.5, 2.0]
    assert ev[0][2] == "Stats lecture"
    s = wrapped_stats([("a", dt.datetime(2026, 3, 2, 14)), ("a", dt.datetime(2026, 3, 3, 14)),
                       ("b", dt.datetime(2025, 3, 3))], ev, 2026)
    assert (s["total"], s["repo"], s["weekday"], s["hour"], s["longest"]) == (2, "a", "Monday", 14, 2)
    assert s["busy_month"] == "October" and "Stats" not in str(s)
    assert heatmap_svg(s["heat"], 2026).count("<rect") == 365
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif "--wrapped" in sys.argv:
        out = wrapped()
        if "--no-open" not in sys.argv:
            subprocess.run(["open", out])
        print(out)
    else:
        menu()
