# Menubar Wrapped

Two small macOS menu bar tools built from your own data.

## Claude Usage (native app)

Claude Code's pixel mascot in the menu bar: grey when Claude is closed, orange when it's
open, walking while Claude works. Click it for:

- **Plan usage limits**: session and weekly %, time until reset, a progress bar and an
  hourglass, the same numbers as Claude's own usage panel, with where and when they were read
- **Today**: what today's Claude Code work would cost at API list prices, with tokens,
  replies and per-model detail
- **Model, Effort, Context** of your latest Claude Code reply
- **Last 7 days**: cost per day
- **Open usage page**: Claude's own usage settings in your browser
- A notification when a limit passes 80% and 95% (once per window; allow notifications
  for Claude Usage in System Settings > Notifications)

```bash
cd claude-usage && ./build.sh install
```

`install` copies the app to `~/Applications` and adds a login item (a LaunchAgent) so it
starts with your Mac; plain `./build.sh` only builds `build/Claude Usage.app`. It builds
with the Command Line Tools' `swiftc`; Xcode isn't needed.

The mascot walks whenever Claude Code is working anywhere on your Mac: the terminal, the
VS Code or JetBrains extension, or the Claude app's Code tab (they all write transcripts to
`~/.claude/projects`). Plain chats in the Claude app, claude.ai, the Chrome extension or other
apps that call Claude keep nothing on your Mac, so the mascot can't see them.

**It uses your own Claude account. No keys or logins are stored in this repo or the app.**
Plan limits come from whichever of these is newest:

1. Claude Code's own `claude -p /usage` (no model call, no saved session). Claude Code signs in
   with *your* login and renews it itself. Usage only changes when Claude replies, so it runs
   5 s and 30 s after a Claude turn ends, every 30 s while Claude works, every 5 minutes when
   idle, and right away when you open the menu or press Refresh (never twice within 15 s).
2. The usage the Claude desktop app records in
   `~/Library/Application Support/Claude/plan-usage-history.json` (every ~15 minutes and
   whenever its usage panel opens). This keeps the bars right even if Claude Code is signed out.
3. The numbers your Claude Code status line last saved, if you set that up (`usage_feed.py`).

If Claude Code is signed out, the menu says so: run `claude auth login`. Token counts and
costs come from your Claude Code transcripts in `~/.claude/projects`, read locally. The cost
is an estimate at API list prices (including cache reads and writes); on a Pro or Max plan
it's what the same work would cost on the API, not your bill.

Requirements: macOS 13+, the Command Line Tools (`xcode-select --install`), and
[Claude Code](https://docs.claude.com/en/docs/claude-code) signed in. Plan limits need a Pro
or Max plan; with an API key the menu still shows cost, model and effort.

## Wrapped (SwiftBar plugin)

Your commit streak, today's calendar and D-days in the macOS menu bar, plus a
Spotify Wrapped-style year-in-review page built from your own local data.

```
🔥 12d · 3 commits · D-315
```

- **Coding**: commits today and this week, current streak, per-repo counts (click to open the repo)
- **Calendar**: what's left today, total hours booked this week
- **D-day**: countdowns to whatever you care about
- **Open My Wrapped**: one click builds a full-screen, swipeable page of your year: total commits, top project, the weekday and hour you code most, longest streak, busiest calendar month, and a commit heatmap

Everything is local. No accounts, no API tokens, nothing leaves your Mac.
The Wrapped page only contains counts, never your event titles.

## Install

```bash
brew install --cask swiftbar
brew install ical-buddy   # optional, for the calendar section
git clone https://github.com/yozmbread/menubar-wrapped.git
```

Point SwiftBar's plugin folder at the cloned folder (or symlink `wrapped.5m.py` into it).
The `.5m.` in the filename means it refreshes every 5 minutes.

## Configure

Edit the constants at the top of `wrapped.5m.py`:

```python
REPO_ROOTS = ["~/Desktop/Projects"]   # scanned 2 levels deep for git repos
AUTHOR_EMAIL = ""                     # empty = your global git user.email
DDAYS = {"Internship": "2027-09-01"}
```

## Run by hand

```bash
python3 wrapped.5m.py              # menu output
python3 wrapped.5m.py --wrapped    # build and open the year page
python3 wrapped.5m.py --selfcheck  # tests
```

Pure Python standard library, works with the macOS system `python3`.

## License

MIT
