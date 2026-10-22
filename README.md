# Menubar Wrapped

Two small macOS menu bar tools built from your own data.

## Claude Usage (native app)

A Claude logo in the menu bar: grey when the Claude app is closed, white when it's open,
spinning while Claude is working. Click it for:

- **Plan usage limits**: session and weekly %, time until reset, a progress bar and an
  hourglass, the same numbers as Claude's own usage panel (refreshed every 30 s)
- **Today**: tokens used today, with output / input / cache / per-model detail
- **Model, Effort, Context** of your latest Claude Code reply
- **Last 7 days** per-day bars

```bash
cd claude-usage && ./build.sh install
```

`install` copies the app to `~/Applications` and adds a login item (a LaunchAgent) so it
starts with your Mac; plain `./build.sh` only builds `build/Claude Usage.app`. It builds
with the Command Line Tools' `swiftc`; Xcode isn't needed.

**It uses your own Claude account. No keys or logins are stored in this repo or the app.**
Limits come from running Claude Code's own `claude -p /usage` once a minute (no model call,
no saved session), so Claude Code signs in with *your* login and renews it itself. Token
counts come from your Claude Code transcripts in `~/.claude/projects`, read locally.

Requirements: macOS 13+, the Command Line Tools (`xcode-select --install`), and
[Claude Code](https://docs.claude.com/en/docs/claude-code) signed in. Plan limits need a Pro
or Max plan; with an API key the menu still shows tokens, model and effort. If `/usage`
fails, the app shows the numbers your status line last saved and says how old they are.

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
git clone https://github.com/<you>/menubar-wrapped.git
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
