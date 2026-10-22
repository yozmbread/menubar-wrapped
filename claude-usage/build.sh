#!/bin/sh
# Builds build/Claude Usage.app with the Command Line Tools' swiftc (no Xcode needed).
# ./build.sh install  also copies it to ~/Applications and starts it at every login.
set -e
cd "$(dirname "$0")"
APP="build/Claude Usage.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -o "$APP/Contents/MacOS/ClaudeUsage" main.swift
cp Info.plist "$APP/Contents/"
cp usage_feed.py "$APP/Contents/Resources/"
xattr -cr "$APP"  # codesign refuses files carrying Finder metadata
codesign --force --sign - "$APP"  # ad-hoc signature so macOS will launch it
echo "$APP"

[ "$1" = install ] || exit 0
DEST="$HOME/Applications/Claude Usage.app"
AGENT="$HOME/Library/LaunchAgents/com.yozmbread.claudeusage.plist"
launchctl bootout "gui/$(id -u)" "$AGENT" 2>/dev/null || true
pkill -f 'Claude Usage.app/Contents/MacOS/ClaudeUsage' || true
mkdir -p "$HOME/Applications" "$HOME/Library/LaunchAgents"
rm -rf "$DEST"
cp -R "$APP" "$DEST"
# RunAtLoad: start at login. KeepAlive on failure only: relaunch after a crash, but Quit stays quit.
cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.yozmbread.claudeusage</string>
    <key>ProgramArguments</key><array><string>$DEST/Contents/MacOS/ClaudeUsage</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$AGENT"
echo "installed: $DEST (starts at login; remove $AGENT to stop that)"
