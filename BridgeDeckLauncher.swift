import Cocoa
import Foundation

if CommandLine.arguments.contains("--self-test") {
    print("BridgeDeckLauncher OK")
    exit(0)
}

let appURL = "http://127.0.0.1:8899"
let uiPort = 8899
let bridgePort = 8876

let bundle = Bundle.main
let resourceURL = bundle.resourceURL ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let bridgeDeckScript = resourceURL.appendingPathComponent("bridgedeck.py").path
let localBridgeScript = resourceURL.appendingPathComponent("local_codex_bridge.py").path
let logURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library")
    .appendingPathComponent("Logs")
    .appendingPathComponent("bridgedeck-app.log")
let installStateURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library")
    .appendingPathComponent("Application Support")
    .appendingPathComponent("BridgeDeck")
    .appendingPathComponent("install-state.json")

func ensureLogFile() {
    let dir = logURL.deletingLastPathComponent()
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    if !FileManager.default.fileExists(atPath: logURL.path) {
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
    }
}

func log(_ message: String) {
    ensureLogFile()
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
    let line = "\(formatter.string(from: Date())) launcher: \(message)\n"
    if let data = line.data(using: .utf8), let handle = try? FileHandle(forWritingTo: logURL) {
        _ = try? handle.seekToEnd()
        _ = try? handle.write(contentsOf: data)
        _ = try? handle.close()
    }
}

func pythonBin() -> String {
    for candidate in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"] {
        if FileManager.default.isExecutableFile(atPath: candidate) {
            return candidate
        }
    }
    return "/usr/bin/python3"
}

@discardableResult
func runProcess(_ executable: String, _ arguments: [String], environment: [String: String]? = nil, wait: Bool = true, logOutput: Bool = false) -> Int32 {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    if let environment {
        process.environment = ProcessInfo.processInfo.environment.merging(environment) { _, new in new }
    }
    var handle: FileHandle?
    if logOutput {
        ensureLogFile()
        handle = try? FileHandle(forWritingTo: logURL)
        _ = try? handle?.seekToEnd()
        process.standardOutput = handle
        process.standardError = handle
    } else {
        handle = FileHandle(forWritingAtPath: "/dev/null")
        process.standardOutput = handle
        process.standardError = handle
    }
    do {
        try process.run()
    } catch {
        log("process_failed executable=\(executable) error=\(error)")
        _ = try? handle?.close()
        return 127
    }
    if wait {
        process.waitUntilExit()
        _ = try? handle?.close()
        return process.terminationStatus
    }
    return 0
}

func processOutput(_ executable: String, _ arguments: [String]) -> String {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.standardOutput = pipe
    process.standardError = Pipe()
    do {
        try process.run()
    } catch {
        return ""
    }
    process.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    return String(data: data, encoding: .utf8) ?? ""
}

func uiRunning() -> Bool {
    if runProcess("/usr/bin/curl", ["-fsS", "-H", "X-CCSBT-Token: probe", "\(appURL)/"], wait: true) == 0 {
        return true
    }
    return uiPortOwnerCommands().contains { $0.contains("bridgedeck.py") }
}

func uiPortOwnerCommands() -> [String] {
    let output = processOutput("/usr/sbin/lsof", ["-tiTCP:\(uiPort)", "-sTCP:LISTEN"])
    var commands: [String] = []
    for line in output.split(whereSeparator: \.isWhitespace) {
        guard Int32(line) != nil else { continue }
        let command = processOutput("/bin/ps", ["-p", "\(line)", "-o", "command="])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !command.isEmpty {
            commands.append(command)
        }
    }
    return commands
}

func openUI() {
    let openURL = "\(appURL)/?t=\(Int(Date().timeIntervalSince1970))"
    log("open_ui \(openURL)")
    if let url = URL(string: openURL) {
        NSWorkspace.shared.open(url)
    }
}

func startUI() {
    log("start_ui")
    if uiRunning() {
        openUI()
        return
    }
    runProcess(pythonBin(), [bridgeDeckScript, "--host", "127.0.0.1", "--port", "\(uiPort)"], wait: false, logOutput: true)
    for _ in 0..<40 {
        if uiRunning() {
            openUI()
            return
        }
        Thread.sleep(forTimeInterval: 0.2)
    }
    let owners = uiPortOwnerCommands()
    if !owners.isEmpty {
        showInfo("8899 端口已被占用，BridgeDeck UI 未启动。\n\n\(owners.joined(separator: "\n"))")
        return
    }
    showInfo("BridgeDeck UI 启动超时。请查看 ~/Library/Logs/bridgedeck-app.log。")
}

func stopUIKeepBridge() {
    log("stop_ui_keep_bridge")
    let output = processOutput("/usr/sbin/lsof", ["-tiTCP:\(uiPort)", "-sTCP:LISTEN"])
    for line in output.split(whereSeparator: \.isWhitespace) {
        guard let pid = Int32(line) else { continue }
        let command = processOutput("/bin/ps", ["-p", "\(pid)", "-o", "command="])
        if command.contains("bridgedeck.py") {
            Darwin.kill(pid, SIGTERM)
        }
    }
}

func startBridgeOnly() {
    log("start_bridge_only")
    runProcess(
        pythonBin(),
        [bridgeDeckScript, "--local-bridge", "start"],
        environment: ["CODEX_BRIDGE_SCRIPT": localBridgeScript],
        wait: true,
        logOutput: true
    )
}

func showAlert(title: String, message: String, buttons: [String]) -> NSApplication.ModalResponse {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    for button in buttons {
        alert.addButton(withTitle: button)
    }
    NSApplication.shared.setActivationPolicy(.regular)
    NSApplication.shared.activate(ignoringOtherApps: true)
    alert.window.level = .floating
    alert.window.orderFrontRegardless()
    return alert.runModal()
}

func showInfo(_ message: String) {
    _ = showAlert(title: "BridgeDeck", message: message, buttons: ["OK"])
}

func writeInstallState(status: String, ok: Bool) {
    let payload: [String: Any] = [
        "status": status,
        "ok": ok,
        "checked_at": ISO8601DateFormatter().string(from: Date()),
        "root": resourceURL.path,
    ]
    let dir = installStateURL.deletingLastPathComponent()
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) {
        try? data.write(to: installStateURL)
    }
}

func runInstallScanInBackground() {
    log("install_scan_background")
    runProcess(
        pythonBin(),
        [bridgeDeckScript, "--install-scan", "--write-install-state"],
        wait: false,
        logOutput: true
    )
}

func firstInstallScanPrompt() {
    if FileManager.default.fileExists(atPath: installStateURL.path) {
        return
    }
    let response = showAlert(
        title: "BridgeDeck 安装扫描",
        message: "首次打开 BridgeDeck。建议先运行安装扫描：Python 编译检查、打包脚本语法检查、/Applications 版本检查。",
        buttons: ["直接打开 UI", "后台扫描并打开 UI", "取消"]
    )
    if response == .alertFirstButtonReturn {
        writeInstallState(status: "skipped", ok: true)
    } else if response == .alertSecondButtonReturn {
        writeInstallState(status: "pending", ok: true)
        runInstallScanInBackground()
    } else {
        exit(0)
    }
}

firstInstallScanPrompt()

let running = uiRunning()
log("launcher_start ui_running=\(running ? 1 : 0)")

if running {
    let response = showAlert(
        title: "BridgeDeck",
        message: "BridgeDeck UI (8899) 已在运行。",
        buttons: ["打开 UI", "关闭 UI 保留 Bridge", "取消"]
    )
    if response == .alertFirstButtonReturn {
        openUI()
    } else if response == .alertSecondButtonReturn {
        stopUIKeepBridge()
        showInfo("BridgeDeck UI 已关闭；8876 Local Bridge 继续运行。")
    }
} else {
    let response = showAlert(
        title: "BridgeDeck",
        message: "BridgeDeck UI 未运行。要打开配置页，还是只启动 8876 Local Bridge？",
        buttons: ["打开 UI", "只启动 Bridge", "取消"]
    )
    if response == .alertFirstButtonReturn {
        startUI()
    } else if response == .alertSecondButtonReturn {
        startBridgeOnly()
        showInfo("8876 Local Bridge 已启动或已在运行。")
    }
}
