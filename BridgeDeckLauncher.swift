import Cocoa
import Foundation

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

if CommandLine.arguments.contains("--self-test") {
    print("BridgeDeckLauncher OK")
    exit(0)
}

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
        process.standardOutput = Pipe()
        process.standardError = Pipe()
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
    runProcess("/usr/bin/curl", ["-fsS", "-H", "X-CCSBT-Token: probe", "\(appURL)/"], wait: true) == 0
}

func openUI() {
    log("open_ui \(appURL)")
    if let url = URL(string: appURL) {
        NSWorkspace.shared.open(url)
    }
}

func startUI() {
    log("start_ui")
    runProcess("/usr/bin/python3", [bridgeDeckScript, "--host", "127.0.0.1", "--port", "\(uiPort)"], wait: false, logOutput: true)
    for _ in 0..<20 {
        if uiRunning() {
            openUI()
            return
        }
        Thread.sleep(forTimeInterval: 0.2)
    }
    openUI()
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
        "/usr/bin/python3",
        [bridgeDeckScript, "--local-bridge", "start"],
        environment: ["CODEX_BRIDGE_SCRIPT": localBridgeScript],
        wait: true,
        logOutput: true
    )
}

func showAlert(title: String, message: String, buttons: [String]) -> NSApplication.ModalResponse {
    NSApplication.shared.setActivationPolicy(.accessory)
    NSApplication.shared.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    for button in buttons {
        alert.addButton(withTitle: button)
    }
    return alert.runModal()
}

func showInfo(_ message: String) {
    _ = showAlert(title: "BridgeDeck", message: message, buttons: ["OK"])
}

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
