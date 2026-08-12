import SwiftUI
import AppKit

// Path contract: $ZERO_ROOT env var, falling back to ~/zero.
// Mirrors zero/nspath.py — if one side moves, move both.
enum Namespace {
    static let root: URL = {
        let env = ProcessInfo.processInfo.environment["ZERO_ROOT"]
        let base = env ?? (NSHomeDirectory() + "/zero")
        return URL(fileURLWithPath: base).appendingPathComponent("namespace")
    }()

    static var statusFile: URL { root.appendingPathComponent("status/current") }
    static var actionFile: URL { root.appendingPathComponent("action/current") }
    static var answerFile: URL { root.appendingPathComponent("answer/current") }
    static var thinkingFile: URL { root.appendingPathComponent("thinking/current") }
    static var inboxDir: URL { root.appendingPathComponent("command/inbox") }

    /// The agent rewrites status at least every 10s, so a stale file means it
    /// is gone. Without this the menubar shows a green IDLE dot for an agent
    /// that was never started — the likeliest first experience of all.
    static func isAlive() -> Bool {
        guard let m = try? FileManager.default.attributesOfItem(atPath: statusFile.path)[.modificationDate] as? Date
        else { return false }
        return Date().timeIntervalSince(m) < 30
    }

    static func readStatus() -> String {
        guard isAlive() else { return "asleep" }
        let raw = (try? String(contentsOf: statusFile, encoding: .utf8)) ?? "idle"
        // Writers strip trailing newlines, but `echo x > current` from a shell
        // is a supported debug path — always trim on read.
        return raw.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func readAnswer() -> String {
        guard let data = try? Data(contentsOf: answerFile),
              let doc = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let payload = doc["payload"] as? [String: Any]
        else { return "" }
        return (payload["text"] as? String) ?? ""
    }

    static func readThinking() -> String {
        ((try? String(contentsOf: thinkingFile, encoding: .utf8)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func readLastAction() -> String {
        guard let data = try? Data(contentsOf: actionFile),
              let doc = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              doc["v"] as? Int == 1,
              let payload = doc["payload"] as? [String: Any]
        else { return "" }
        if let tool = payload["tool"] as? String {
            let args = payload["args"] as? [String: Any] ?? [:]
            let argText = args.isEmpty ? "" : " \(args)"
            return "\(tool)\(argText)"
        }
        return (payload["text"] as? String) ?? ""
    }

    /// One file per submission — a queue, so two fast submissions never
    /// clobber each other. The agent claims files by renaming them out.
    static func submitCommand(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        try? FileManager.default.createDirectory(at: inboxDir, withIntermediateDirectories: true)
        let doc: [String: Any] = [
            "v": 1,
            "ts": Date().timeIntervalSince1970,
            "writer": "human",
            "payload": ["text": trimmed],
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: doc) else { return }
        let name = String(format: "%.6f.json", Date().timeIntervalSince1970)
        try? data.write(to: inboxDir.appendingPathComponent(name), options: .atomic)
    }
}

struct AgentState {
    var status: String
    var answer: String
    var thinking: String

    var alive: Bool { status != "asleep" }

    /// Plain-language status. A novice should never have to decode a state name.
    var headline: String {
        switch status {
        case "asleep":    return "Zero isn't running"
        case "waking":    return "Waking up…"
        case "thinking":  return "Thinking…"
        case "executing": return "Working on it…"
        case "error":     return "Something went wrong"
        default:          return "Ready"
        }
    }

    var light: Color {
        switch status {
        case "asleep": return .gray
        case "thinking", "executing", "waking": return .orange
        case "error": return .red
        default: return .green
        }
    }

    static func load() -> AgentState {
        AgentState(status: Namespace.readStatus(),
                   answer: Namespace.readAnswer(),
                   thinking: Namespace.readThinking())
    }
}

class ZeroState: ObservableObject {
    @Published var agent = AgentState.load()
    // lives here (not @State in the view) because the CommandLineTools
    // toolchain lacks the SwiftUI macros plugin that @State now requires
    @Published var inputText: String = ""
    /// Echo what the user just said, immediately — silence after pressing
    /// return reads as "it didn't hear me".
    @Published var lastAsked: String = ""
    private var timer: Timer?

    init() {
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            self.agent = AgentState.load()
        }
    }
}

@main
struct ZeroApp: App {
    @StateObject private var state = ZeroState()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        WindowGroup(id: "dashboard") { dashboard }
            .windowStyle(.hiddenTitleBar)

        MenuBarExtra(state.agent.headline, systemImage: state.agent.alive
                     ? (state.agent.status == "idle" ? "circle.fill" : "brain.head.profile")
                     : "moon.zzz") {
            Button("Open Zero") {
                openWindow(id: "dashboard")
                NSApp.activate(ignoringOtherApps: true)
            }
            Divider()
            Button("Quit Zero UI") {
                NSApplication.shared.terminate(nil)
            }
        }

    }

    @ViewBuilder private var dashboard: some View {

            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Circle().fill(state.agent.light).frame(width: 9, height: 9)
                    Text(state.agent.headline)
                        .font(.callout.weight(.medium))
                    Spacer()
                }

                if state.agent.status == "waking" {
                    Text("Loading its brain — this takes about a minute the first time.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if !state.agent.alive {
                    Text("Start it from a terminal with  zero start")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if !state.lastAsked.isEmpty {
                    Text("You: \(state.lastAsked)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // while it thinks, show that it is thinking — not dead air
                if state.agent.status == "thinking", !state.agent.thinking.isEmpty {
                    Text(state.agent.thinking)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                        .lineLimit(2)
                } else if !state.agent.answer.isEmpty {
                    Text(state.agent.answer)
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                }

                TextField("Ask Zero anything", text: $state.inputText)
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(.ultraThinMaterial)
                    .cornerRadius(10)
                    .onSubmit {
                        let text = state.inputText
                        Namespace.submitCommand(text)
                        state.lastAsked = text
                        state.inputText = ""
                    }
            }
            .padding(24)
            .frame(width: 420, alignment: .leading)
            .background(.ultraThinMaterial)
    }
}
