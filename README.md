# Menubar Wrapped

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
