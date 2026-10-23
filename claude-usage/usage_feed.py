#!/usr/bin/env python3
"""Data feed for the Claude Usage menu bar app.

Prints one JSON line whenever something changes: app state (off/on/busy), plan limits,
today's tokens, current model and effort. The Swift app draws it.
--once prints a single snapshot, --selfcheck runs the tests.
"""
import collections
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

PROJECTS = os.path.expanduser("~/.claude/projects")
STATUS_FILE = os.path.expanduser("~/.cache/claude-usage/status.json")  # written by statusline.sh
# Live numbers come from Claude Code's own /usage command, run as whoever uses this app:
# it reads and renews *their* Claude login itself and makes no model call. No keys live here.
# Apps started at login get a minimal PATH, so also look where Claude Code installs usually go.
CLAUDE_DIRS = ["~/.local/bin", "~/.claude/local", "/opt/homebrew/bin", "/usr/local/bin", "~/.npm-global/bin",
               "~/.bun/bin"]
LIVE_CACHE = os.path.expanduser("~/.cache/claude-usage/live.json")  # last good live numbers
LOG = os.path.expanduser("~/.cache/claude-usage/feed.log")  # errors from the background refresh
LIVE_EVERY = 60  # s between live usage fetches; the endpoint rate-limits (429) if polled hard
MAX_BACKOFF = 900  # s; longest wait after failures
DATA_EVERY = 5  # s between re-reading transcripts
DAYS = 7
BUSY_LINGER = 3  # s the mascot keeps walking after a turn ends
BUSY_WINDOW = 300  # s; a turn with no transcript write for this long counts as stopped
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def model_name(model_id):
    """claude-opus-5-5 -> Opus 5.5"""
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-|$)", model_id or "")
    if not m:
        return model_id or "?"
    return f"{m[1].title()} {m[2]}" + (f".{m[3]}" if m[3] else "")


def transcripts():
    """(path, stat) of every transcript. Claude Code deletes and rewrites these while we scan,
    so a file that vanishes mid-walk is skipped instead of crashing the scan."""
    for base, _, files in os.walk(PROJECTS):
        for f in files:
            if f.endswith(".jsonl"):
                path = os.path.join(base, f)
                try:
                    yield path, os.stat(path)
                except OSError:
                    continue


def read_records(since):
    """One record per API response (transcripts repeat a response once per content block)."""
    seen = {}
    for path, st in transcripts():
        if st.st_mtime < since.timestamp():
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    rec = parse(line)
                    if rec and rec["time"] >= since:
                        seen[rec["id"]] = rec
        except OSError:
            continue
    return sorted(seen.values(), key=lambda r: r["time"])


def parse(line):
    try:
        d = json.loads(line)
    except ValueError:
        return None
    msg = d.get("message")
    if d.get("type") != "assistant" or not isinstance(msg, dict) or not msg.get("usage"):
        return None
    if msg.get("model") == "<synthetic>":
        return None
    u = msg["usage"]
    t = dt.datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    return {
        "id": msg.get("id") or d.get("uuid"),
        "time": t,
        "model": msg.get("model"),
        "effort": d.get("effort"),
        "fast": u.get("speed") == "fast",
        "sub": d.get("isSidechain", False),
        **{k: u.get(k) or 0 for k in TOKEN_KEYS},
    }


def total(recs):
    return sum(r[k] for r in recs for k in TOKEN_KEYS)


def fmt(n):
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def until(reset, now):
    """4h 50m / 2d 3h / 12m"""
    mins = int((reset - now).total_seconds() // 60)
    d, h, m = mins // 1440, mins % 1440 // 60, mins % 60
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


_live = {"next": 0.0, "backoff": LIVE_EVERY, "problem": None}

# Shown instead of the limit bars when there are none to show
PROBLEMS = {
    "no-claude": "Install Claude Code to see plan limits",
    "no-plan": "Plan limits need Claude Code signed in to a Pro or Max plan",
    None: "Loading plan limits…",
}


def find_claude():
    path = os.pathsep.join([os.environ.get("PATH", "")] + [os.path.expanduser(d) for d in CLAUDE_DIRS])
    return shutil.which("claude", path=path)


def live_limits():
    """(limits, retry_after, problem): plan usage from `claude -p /usage`; limits is None on failure."""
    claude = find_claude()
    if not claude:
        return None, None, "no-claude"
    try:
        os.makedirs(os.path.dirname(LIVE_CACHE), exist_ok=True)
        out = subprocess.run([claude, "-p", "--no-session-persistence", "/usage"], cwd=os.path.dirname(LIVE_CACHE),
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    limits = parse_usage(out, dt.datetime.now())
    # No limit lines: signed out, or signed in with an API key (pay-as-you-go has no plan limits)
    return limits, None, None if limits else "no-plan"


USAGE_LINES = {"five_hour": r"Current session: ([\d.]+)% used · resets (.+?) \(",
               "seven_day": r"Current week \(all models\): ([\d.]+)% used · resets (.+?) \("}


def parse_usage(text, now):
    """/usage text -> {five_hour: {used_percentage, resets_at}}; reset times are local, year implied."""
    out = {}
    for key, pattern in USAGE_LINES.items():
        m = re.search(pattern, text)
        if not m:
            continue
        for form in ("%b %d at %I:%M%p %Y", "%b %d at %I%p %Y"):  # "1:59pm" or "2pm"
            try:
                reset = dt.datetime.strptime(f"{m[2]} {now.year}", form)
                break
            except ValueError:
                reset = None
        if reset is None:
            continue
        if reset < now - dt.timedelta(days=1):  # e.g. a January reset seen in December
            reset = reset.replace(year=now.year + 1)
        out[key] = {"used_percentage": float(m[1]), "resets_at": reset.timestamp()}
    return out or None


def load_cache():
    try:
        with open(LIVE_CACHE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"t": 0, "limits": None}


def save_cache(cache):
    os.makedirs(os.path.dirname(LIVE_CACHE), exist_ok=True)
    with open(LIVE_CACHE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    os.replace(LIVE_CACHE + ".tmp", LIVE_CACHE)


def next_backoff(current, retry_after):
    """Wait the server's Retry-After if given, else double the wait, capped at MAX_BACKOFF."""
    return min(retry_after if retry_after else current * 2, MAX_BACKOFF)


def iso_ts(text):
    """ISO time -> epoch; drops fractions and accepts Z (python 3.9's fromisoformat is strict)."""
    return dt.datetime.fromisoformat(re.sub(r"\.\d+", "", text).replace("Z", "+00:00")).timestamp()


def read_limits():
    """(limits, source, fetched_at). Live numbers are cached on disk so restarts don't refetch;
    after a failure we back off. Falls back to what statusline.sh saved."""
    now = time.time()
    cache = load_cache()
    if now >= _live["next"] and now - cache["t"] >= LIVE_EVERY:
        limits, retry_after, _live["problem"] = live_limits()
        if limits:
            cache = {"t": now, "limits": limits}
            save_cache(cache)
            _live["backoff"] = LIVE_EVERY
        else:
            _live["backoff"] = next_backoff(_live["backoff"], retry_after)
        _live["next"] = now + _live["backoff"]
    if cache["limits"] and now - cache["t"] < 6 * 3600:
        return cache["limits"], "live", cache["t"]
    try:
        with open(STATUS_FILE, encoding="utf-8") as fh:
            saved = json.load(fh).get("rate_limits")
        return (saved, "saved", os.path.getmtime(STATUS_FILE)) if saved else (None, "none", 0)
    except (OSError, ValueError):
        return None, "none", 0


def limit_rows(limits, now):
    rows = []
    for key, label, length in (("five_hour", "Session", 5 * 3600), ("seven_day", "Weekly", 7 * 86400)):
        w = (limits or {}).get(key)
        if not w:
            continue
        reset = dt.datetime.fromtimestamp(w["resets_at"])
        if reset > now:
            rows.append({"label": label, "used": w["used_percentage"], "resets": f"resets in {until(reset, now)}",
                         "timeLeft": (reset - now).total_seconds() / length})
        else:  # window rolled over since the numbers were saved
            rows.append({"label": label, "used": 0, "resets": "new window", "timeLeft": 1.0})
    return rows


def data():
    now = dt.datetime.now()
    recs = read_records(dt.datetime.combine(now.date() - dt.timedelta(days=DAYS - 1), dt.time()))
    today = [r for r in recs if r["time"].date() == now.date()]
    main = [r for r in recs if not r["sub"]]
    last = main[-1] if main else (recs[-1] if recs else None)
    limits, source, fetched = read_limits()
    by_model = collections.Counter()
    for r in today:
        by_model[model_name(r["model"])] += total([r])
    per_day = collections.Counter()
    for r in recs:
        per_day[r["time"].date()] += total([r])
    top = max(per_day.values(), default=1)
    week = []
    for i in range(DAYS - 1, -1, -1):
        day = now.date() - dt.timedelta(days=i)
        n = per_day.get(day, 0)
        week.append(f"{day:%a %d}  {'█' * round(10 * n / top) if n else '·'} {fmt(n)}")
    return {
        "limits": limit_rows(limits, now),
        "limitsSource": source,
        "limitsFetched": fetched,  # epoch; the app shows how old the numbers are
        "limitsNote": PROBLEMS[_live["problem"]],
        "today": f"{fmt(total(today))} tokens",        "todayDetail": [
            f"Output: {fmt(sum(r['output_tokens'] for r in today))}",
            f"Fresh input: {fmt(sum(r['input_tokens'] + r['cache_creation_input_tokens'] for r in today))}",
            f"Cache reads: {fmt(sum(r['cache_read_input_tokens'] for r in today))}",
            f"Replies: {len(today)}",
        ] + [f"{m}: {fmt(n)}" for m, n in by_model.most_common()],
        "model": (model_name(last["model"]) + (" (fast)" if last["fast"] else "")) if last else None,
        "effort": (last["effort"] or "default") if last else None,
        "context": f"{fmt(sum(last[k] for k in TOKEN_KEYS if k != 'output_tokens'))} tokens" if last else None,
        "weekTotal": f"{fmt(total(recs))} tokens",
        "week": week,
    }


def claude_running():
    """The Claude desktop app, or a terminal `claude` session."""
    for args in subprocess.run(["ps", "-axo", "args="], capture_output=True, text=True).stdout.splitlines():
        exe = args.split(" ", 1)[0]
        if exe == "/Applications/Claude.app/Contents/MacOS/Claude" or os.path.basename(exe) == "claude":
            return True
    return False


# User records that close a turn instead of waiting on Claude
NOT_A_PROMPT = ("[Request interrupted", "<local-command", "<command-name>")


def turn_open(lines, now):
    """True if the last user/assistant record is an unfinished turn from the last BUSY_WINDOW s."""
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("type")
        if kind not in ("user", "assistant"):
            continue  # app bookkeeping (cost-state, mode, ...) is written even when idle
        if now - iso_ts(d.get("timestamp") or "1970-01-01T00:00:00Z") > BUSY_WINDOW:
            return False
        msg = d.get("message") or {}
        if kind == "assistant":
            return msg.get("stop_reason") != "end_turn"
        content = msg.get("content")
        texts = [content] if isinstance(content, str) else [
            c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        return not any(t.lstrip().startswith(NOT_A_PROMPT) for t in texts)
    return False


def busy():
    """Any transcript whose latest turn is still open."""
    now = time.time()
    for path, st in transcripts():
        if st.st_mtime <= now - BUSY_WINDOW:
            continue
        try:
            with open(path, "rb") as fh:
                fh.seek(max(0, st.st_size - 200_000))
                tail = fh.read().decode("utf-8", "replace").splitlines()[1:]
        except OSError:
            continue
        if turn_open(tail, now):
            return True
    return False


def state():
    # Quitting Claude can leave a turn open in a transcript, so "off" wins over "busy"
    if not claude_running():
        return "off"
    return "busy" if busy() else "on"


def last_write():
    """Newest transcript mtime; moves on every reply Claude writes."""
    return max((st.st_mtime_ns for _, st in transcripts()), default=0)


def log_error():
    """Append the current traceback to LOG, keeping the file small."""
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 100_000:
            os.remove(LOG)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"--- {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n{traceback.format_exc()}")
    except OSError:
        pass


def stream():
    """State every half second; data on every transcript write, else every DATA_EVERY s; a JSON line on change."""
    latest = {"data": data()}

    def refresh():
        seen, stamp = last_write(), time.time()
        while True:
            time.sleep(1)
            # A crash here used to kill this thread silently and freeze the menu for good
            try:
                now = last_write()
                if now != seen or time.time() - stamp >= DATA_EVERY:
                    seen, stamp = now, time.time()
                    latest["data"] = data()
            except Exception:
                log_error()

    threading.Thread(target=refresh, daemon=True).start()
    last, busy_until = None, 0.0
    while True:
        st = state()
        # Short replies (a few seconds) would barely flash; keep walking BUSY_LINGER s after the last busy check
        if st == "busy":
            busy_until = time.time() + BUSY_LINGER
        elif st == "on" and time.time() < busy_until:
            st = "busy"
        line = json.dumps({"state": st, **latest["data"]})
        if line != last:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            last = line
        time.sleep(0.5)


def selfcheck():
    assert model_name("claude-opus-5-5") == "Opus 5.5"
    assert model_name("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert model_name("claude-sonnet-4-20250514") == "Sonnet 4"
    assert model_name("claude-fable-5-1") == "Fable 5.1"
    line = json.dumps({"type": "assistant", "timestamp": "2026-10-21T10:00:00Z", "effort": "high",
                       "message": {"id": "m1", "model": "claude-opus-5-5",
                                   "usage": {"input_tokens": 2, "output_tokens": 100,
                                             "cache_read_input_tokens": 1000, "speed": "fast"}}})
    r = parse(line)
    assert (r["effort"], r["fast"], total([r])) == ("high", True, 1102)
    assert parse('{"type":"user"}') is None and parse("not json") is None
    assert fmt(1234) == "1.2k" and fmt(2_500_000) == "2.5M" and fmt(12) == "12"
    now = dt.datetime(2026, 10, 21, 19, 40)
    assert until(dt.datetime(2026, 10, 22, 0, 30), now) == "4h 50m"
    assert until(dt.datetime(2026, 10, 23, 22, 0), now) == "2d 2h"
    assert until(dt.datetime(2026, 10, 21, 19, 52), now) == "12m"
    usage = ("Current session: 8% used · resets Oct 22 at 1:59pm (UTC)\n"
             "Current week (all models): 2.5% used · resets Oct 29 at 7am (UTC)\n")
    lim = parse_usage(usage, dt.datetime(2026, 10, 22, 9, 0))
    assert lim["five_hour"] == {"used_percentage": 8.0, "resets_at": dt.datetime(2026, 10, 22, 13, 59).timestamp()}
    assert lim["seven_day"]["resets_at"] == dt.datetime(2026, 10, 29, 7, 0).timestamp()
    assert parse_usage(usage, dt.datetime(2026, 12, 30))["seven_day"]["resets_at"] == dt.datetime(2027, 10, 29, 7).timestamp()
    assert parse_usage("Please log in", dt.datetime(2026, 10, 22)) is None
    assert next_backoff(60, None) == 120 and next_backoff(600, None) == MAX_BACKOFF
    assert next_backoff(60, 300) == 300
    assert iso_ts("2026-11-05T07:59:00Z") == iso_ts("2026-11-05T07:59:00.123456+00:00")
    reset = dt.datetime(2026, 10, 21, 22, 10)
    rows = limit_rows({"five_hour": {"used_percentage": 8, "resets_at": reset.timestamp()}}, now)
    assert rows == [{"label": "Session", "used": 8, "resets": "resets in 2h 30m", "timeLeft": 0.5}]
    assert limit_rows({"five_hour": {"used_percentage": 8, "resets_at": 0}}, now)[0]["resets"] == "new window"
    t0 = iso_ts("2026-10-21T20:00:00Z")

    def rec(kind, stop=None, content=None, ts="2026-10-21T20:00:00Z"):
        return json.dumps({"type": kind, "timestamp": ts, "message": {"stop_reason": stop, "content": content}})
    assert turn_open([rec("user", content="hi"), rec("assistant", "tool_use")], t0)
    assert not turn_open([rec("user"), rec("assistant", "end_turn"), '{"type":"cost-state"}'], t0)
    assert turn_open([rec("assistant", "end_turn"), rec("user", content=[{"type": "tool_result"}])], t0)
    assert not turn_open([rec("user", content="hi")], t0 + BUSY_WINDOW + 1)  # stale: Claude stopped
    assert not turn_open([rec("user", content=[{"type": "text", "text": "[Request interrupted by user]"}])], t0)
    assert not turn_open([rec("user", content="<local-command-stdout>Set model</local-command-stdout>")], t0)
    assert not turn_open([], t0)
    import tempfile
    global PROJECTS
    saved, PROJECTS = PROJECTS, tempfile.mkdtemp()
    try:
        for name in ("a.jsonl", "b.jsonl"):
            open(os.path.join(PROJECTS, name), "w").close()
        walk = transcripts()
        next(walk)
        for name in ("a.jsonl", "b.jsonl"):  # Claude Code removes files while we scan
            if os.path.exists(os.path.join(PROJECTS, name)):
                os.remove(os.path.join(PROJECTS, name))
        assert list(walk) == [] and last_write() == 0 and read_records(dt.datetime(2026, 1, 1)) == []
    finally:
        PROJECTS = saved
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif "--once" in sys.argv:
        print(json.dumps({"state": state(), **data()}, indent=1))
    else:
        stream()
