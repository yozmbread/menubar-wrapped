// Claude Usage: a menu bar app showing Claude plan limits, today's tokens, model and effort.
// The icon is Claude Code's pixel mascot: grey when Claude is closed, orange when open,
// and walking in place while Claude works.
// Data comes from usage_feed.py (bundled in Resources), which prints a JSON line on every change.
import AppKit
import UserNotifications

struct Limit: Decodable {
    let label: String
    let used: Double
    let resets: String
    let timeLeft: Double
    var resetsAt: Double? = nil  // epoch; nil when the reset time isn't known
    var fetched: Double = 0  // epoch the % was read
    var source = ""  // Claude Code | Claude app | status line
}

struct Snapshot: Decodable {
    let state: String  // off | on | busy
    let limits: [Limit]
    let limitsNote: String?  // a problem worth showing, e.g. Claude Code signed out
    let today: String
    let todayDetail: [String]
    let model: String?
    let effort: String?
    let context: String?
    let weekTotal: String
    let week: [String]
}

// Claude Code's pixel mascot, 12x8 cells. While Claude works it cycles through these:
// arms up with one pair of legs lifted, back to rest, arms down with the other pair lifted.
let mascotRest = [
    "..########..",
    "..#.####.#..",
    "############",
    "############",
    "..########..",
    "..########..",
    "..#.#..#.#..",
    "..#.#..#.#..",
]
let mascotWalk = [
    mascotRest,
    ["..########..",
     "###.####.###",
     "############",
     "..########..",
     "..########..",
     "..########..",
     "..#.#..#.#..",
     "....#....#.."],
    mascotRest,
    ["..########..",
     "..#.####.#..",
     "..########..",
     "############",
     "############",
     "..########..",
     "..#.#..#.#..",
     "..#....#...."],
]
let claudeOrange = NSColor(srgbRed: 217 / 255, green: 119 / 255, blue: 87 / 255, alpha: 1)
let usagePage = URL(string: "https://claude.ai/settings/usage")!
let alertLevels: [Double] = [80, 95]

/// One mascot frame, 2 pt per cell (24x16 pt), drawn as crisp squares.
func mascotImage(_ rows: [String], color: NSColor) -> NSImage {
    let cell: CGFloat = 2
    return NSImage(size: NSSize(width: 12 * cell, height: 8 * cell), flipped: true) { _ in
        color.setFill()
        for (y, row) in rows.enumerated() {
            for (x, c) in row.enumerated() where c == "#" {
                NSRect(x: CGFloat(x) * cell, y: CGFloat(y) * cell, width: cell, height: cell).fill()
            }
        }
        return true
    }
}

/// One plan limit, laid out like Claude's usage panel: label, reset time and %, then an
/// hourglass (time left in the window) and a progress bar (% used).
final class LimitView: NSView {
    let limit: Limit
    init(_ limit: Limit) {
        self.limit = limit
        super.init(frame: NSRect(x: 0, y: 0, width: 300, height: 44))
    }
    required init?(coder: NSCoder) { fatalError() }
    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        let font = NSFont.menuFont(ofSize: 13)
        let left: CGFloat = 14, right = bounds.width - 14
        (limit.label as NSString).draw(at: NSPoint(x: left, y: 4),
                                       withAttributes: [.font: font, .foregroundColor: NSColor.labelColor])
        let status = "\(limit.resets)   \(Int(limit.used.rounded()))%" as NSString
        let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.secondaryLabelColor]
        status.draw(at: NSPoint(x: right - status.size(withAttributes: attrs).width, y: 4), withAttributes: attrs)

        drawHourglass(in: NSRect(x: left, y: 23, width: 9, height: 14), timeLeft: limit.timeLeft)
        let track = NSRect(x: left + 16, y: 27, width: right - left - 16, height: 6)
        NSColor.tertiaryLabelColor.setFill()
        NSBezierPath(roundedRect: track, xRadius: 3, yRadius: 3).fill()
        let used = min(max(limit.used, 0), 100) / 100
        if used > 0 {
            (limit.used >= 90 ? NSColor.systemRed : NSColor.systemBlue).setFill()
            var fill = track
            fill.size.width = max(6, track.width * used)
            NSBezierPath(roundedRect: fill, xRadius: 3, yRadius: 3).fill()
        }
    }

    private func drawHourglass(in r: NSRect, timeLeft: Double) {
        let t = CGFloat(min(max(timeLeft, 0), 1))
        let mid = r.midY, half = r.height / 2 - 1.5
        let glass = NSBezierPath()  // two triangles meeting at the neck
        glass.move(to: NSPoint(x: r.minX + 0.5, y: r.minY + 1.5))
        glass.line(to: NSPoint(x: r.maxX - 0.5, y: r.minY + 1.5))
        glass.line(to: NSPoint(x: r.midX + 0.4, y: mid))
        glass.line(to: NSPoint(x: r.maxX - 0.5, y: r.maxY - 1.5))
        glass.line(to: NSPoint(x: r.minX + 0.5, y: r.maxY - 1.5))
        glass.line(to: NSPoint(x: r.midX - 0.4, y: mid))
        glass.close()
        NSGraphicsContext.saveGraphicsState()
        glass.addClip()
        NSColor(srgbRed: 217 / 255, green: 119 / 255, blue: 87 / 255, alpha: 1).setFill()  // Claude orange
        let top = half * sqrt(t), bottom = half * (1 - sqrt(t))  // bulbs are ~triangles: area ~ height^2
        NSRect(x: r.minX, y: mid - top, width: r.width, height: top).fill()
        NSRect(x: r.minX, y: r.maxY - 1.5 - bottom, width: r.width, height: bottom).fill()
        NSGraphicsContext.restoreGraphicsState()
        NSColor.secondaryLabelColor.setStroke()
        glass.lineWidth = 1
        glass.stroke()
        NSBezierPath.strokeLine(from: NSPoint(x: r.minX, y: r.minY + 0.5), to: NSPoint(x: r.maxX, y: r.minY + 0.5))
        NSBezierPath.strokeLine(from: NSPoint(x: r.minX, y: r.maxY - 0.5), to: NSPoint(x: r.maxX, y: r.maxY - 0.5))
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let frames = mascotWalk.map { mascotImage($0, color: claudeOrange) }
    let offIcon = mascotImage(mascotRest, color: .systemGray)
    var snapshot: Snapshot?
    var feed: Process?
    var spinTimer: Timer?
    var frame = 0
    var quitting = false
    var menuOpen = false

    func applicationDidFinishLaunching(_ note: Notification) {
        item.button?.image = offIcon
        let menu = NSMenu()
        menu.delegate = self
        menu.autoenablesItems = false
        item.menu = menu
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        startFeed()
    }

    func startFeed() {
        guard let script = Bundle.main.path(forResource: "usage_feed", ofType: "py") else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [script]
        let pipe = Pipe()
        process.standardOutput = pipe
        var buffer = Data()
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            buffer.append(handle.availableData)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer[buffer.startIndex..<nl]
                buffer.removeSubrange(buffer.startIndex...nl)
                if let snap = try? JSONDecoder().decode(Snapshot.self, from: line) {
                    DispatchQueue.main.async { self?.apply(snap) }
                }
            }
        }
        process.terminationHandler = { [weak self] _ in  // keep the feed alive if python dies
            pipe.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                if self?.quitting == false { self?.startFeed() }
            }
        }
        try? process.run()
        feed = process
    }

    func apply(_ snap: Snapshot) {
        snapshot = snap
        checkAlerts(snap.limits)
        // Live-refresh an open menu, unless a submenu is showing (rebuilding would close it)
        if menuOpen, let menu = item.menu, menu.highlightedItem?.submenu == nil { menuNeedsUpdate(menu) }
        if snap.state == "busy" {
            if spinTimer == nil {
                let timer = Timer(timeInterval: 1.0 / 6, repeats: true) { [weak self] _ in  // pixel-art pace
                    guard let self else { return }
                    self.frame = (self.frame + 1) % self.frames.count
                    self.item.button?.image = self.frames[self.frame]
                }
                RunLoop.main.add(timer, forMode: .common)  // keep walking while the menu is open
                spinTimer = timer
            }
        } else {
            spinTimer?.invalidate()
            spinTimer = nil
            item.button?.image = snap.state == "on" ? frames[0] : offIcon
        }
    }

    func menuWillOpen(_ menu: NSMenu) { menuOpen = true }
    func menuDidClose(_ menu: NSMenu) { menuOpen = false }

    // Rebuilt each time the menu opens and on every new snapshot while open
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        guard let s = snapshot else {
            menu.addItem(withTitle: "Loading…", action: nil, keyEquivalent: "")
            addFooter(menu)
            return
        }
        menu.addItem(header("Plan usage limits"))
        for limit in s.limits {
            let row = NSMenuItem()
            row.view = LimitView(limit)
            menu.addItem(row)
        }
        if let newest = s.limits.max(by: { $0.fetched < $1.fetched }) {
            let minutes = Int(Date().timeIntervalSince1970 - newest.fetched) / 60
            let age = minutes < 1 ? "just now" : minutes < 60 ? "\(minutes) min ago" : "\(minutes / 60) h \(minutes % 60) min ago"
            menu.addItem(header("Updated \(age) · from \(newest.source)"))
        }
        if let note = s.limitsNote { menu.addItem(header(note)) }
        menu.addItem(.separator())
        menu.addItem(row("Today", s.today, submenu: s.todayDetail))
        if let model = s.model { menu.addItem(row("Model", model)) }
        if let effort = s.effort { menu.addItem(row("Effort", effort)) }
        if let context = s.context { menu.addItem(row("Context", context)) }
        menu.addItem(.separator())
        menu.addItem(row("Last 7 days", s.weekTotal, submenu: s.week, mono: true))
        addFooter(menu)
    }

    func addFooter(_ menu: NSMenu) {
        menu.addItem(.separator())
        menu.addItem(withTitle: "Open usage page", action: #selector(openUsage), keyEquivalent: "u").target = self
        menu.addItem(withTitle: "Refresh", action: #selector(refresh), keyEquivalent: "r").target = self
        menu.addItem(withTitle: "Quit Claude Usage", action: #selector(quit), keyEquivalent: "q").target = self
    }

    func header(_ text: String) -> NSMenuItem {
        let item = NSMenuItem()
        item.attributedTitle = NSAttributedString(string: text, attributes: [
            .font: NSFont.menuFont(ofSize: 12), .foregroundColor: NSColor.secondaryLabelColor])
        return item
    }

    /// "Label ........ value" with the value right-aligned
    func row(_ label: String, _ value: String, submenu: [String] = [], mono: Bool = false) -> NSMenuItem {
        let style = NSMutableParagraphStyle()
        style.tabStops = [NSTextTab(textAlignment: .right, location: 272)]
        let item = NSMenuItem()
        item.attributedTitle = NSAttributedString(string: "\(label)\t\(value)", attributes: [
            .font: NSFont.menuFont(ofSize: 13), .paragraphStyle: style])
        if !submenu.isEmpty {
            let sub = NSMenu()
            sub.autoenablesItems = false
            let font = mono ? NSFont.monospacedSystemFont(ofSize: 12, weight: .regular) : NSFont.menuFont(ofSize: 13)
            for line in submenu {
                let entry = NSMenuItem()
                entry.attributedTitle = NSAttributedString(string: line, attributes: [.font: font])
                sub.addItem(entry)
            }
            item.submenu = sub
        }
        return item
    }

    @objc func refresh() { feed?.terminate() }  // the termination handler restarts it with fresh data

    @objc func openUsage() { NSWorkspace.shared.open(usagePage) }

    /// One notification per level (80%, 95%) per limit window. A window is its reset time, or a
    /// 5-hour bucket while the reset time is unknown.
    func checkAlerts(_ limits: [Limit]) {
        var fired = UserDefaults.standard.stringArray(forKey: "firedAlerts") ?? []
        for limit in limits {
            let window = limit.resetsAt.map { String(Int($0)) } ?? "t\(Int(limit.fetched) / 18000)"
            for level in alertLevels where limit.used >= level {
                let key = "\(limit.label)-\(Int(level))-\(window)"
                guard !fired.contains(key) else { continue }
                fired.append(key)
                notify("Claude \(limit.label.lowercased()) limit \(Int(limit.used.rounded()))% used", limit.resets)
            }
        }
        UserDefaults.standard.set(Array(fired.suffix(40)), forKey: "firedAlerts")
    }

    func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request) { error in
            guard error != nil else { return }
            // Notifications not allowed for this ad-hoc signed app: let AppleScript post it instead
            let script = "display notification \(Self.quoted(body)) with title \(Self.quoted(title))"
            _ = try? Process.run(URL(fileURLWithPath: "/usr/bin/osascript"), arguments: ["-e", script])
        }
    }

    static func quoted(_ s: String) -> String {
        "\"" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
    }

    @objc func quit() {
        quitting = true
        feed?.terminate()
        NSApp.terminate(nil)
    }
}

/// --preview out.png: draw the mascot frames and sample limit rows (dark mode) to check the drawing.
func renderPreview(to path: String) {
    let canvas = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 140))
    canvas.appearance = NSAppearance(named: .darkAqua)
    canvas.wantsLayer = true
    canvas.layer?.backgroundColor = NSColor(white: 0.16, alpha: 1).cgColor
    let icons = mascotWalk.map { mascotImage($0, color: claudeOrange) } + [mascotImage(mascotRest, color: .systemGray)]
    for (i, image) in icons.enumerated() {
        let icon = NSImageView(frame: NSRect(x: 14 + CGFloat(i) * 56, y: 104, width: 48, height: 32))
        icon.image = image
        icon.imageScaling = .scaleProportionallyUpOrDown
        canvas.addSubview(icon)
    }
    let session = LimitView(Limit(label: "Session", used: 22, resets: "resets in 4h 11m", timeLeft: 0.84))
    let weekly = LimitView(Limit(label: "Weekly", used: 93, resets: "resets in 9h 41m", timeLeft: 0.06))
    if CommandLine.arguments.contains("--test-alert") {  // posts one sample notification
        let d = AppDelegate()
        d.notify("Claude session limit 80% used", "resets in 1h 20m")
        RunLoop.main.run(until: Date().addingTimeInterval(3))
    }
    session.frame.origin = NSPoint(x: 0, y: 52)
    weekly.frame.origin = NSPoint(x: 0, y: 6)
    canvas.addSubview(session)
    canvas.addSubview(weekly)
    guard let rep = canvas.bitmapImageRepForCachingDisplay(in: canvas.bounds) else { return }
    canvas.cacheDisplay(in: canvas.bounds, to: rep)
    try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
}

if let i = CommandLine.arguments.firstIndex(of: "--preview"), i + 1 < CommandLine.arguments.count {
    renderPreview(to: CommandLine.arguments[i + 1])
    exit(0)
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
