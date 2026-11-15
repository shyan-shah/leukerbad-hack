import SwiftUI
import Observation

enum Tab: Hashable { case home, exercises, scan, progress, me }

/// App state. Patient data is sample data (Anna, from the design) until a real backend sends it.
@MainActor @Observable
final class AppModel {
    enum ScanState: Equatable { case idle, working(String), done(robot: String, demo: Bool), failed(String) }

    /// Launch argument `-startTab scan|exercises|progress|me` opens that tab (for screenshots and testing).
    var tab: Tab = ["exercises": .exercises, "scan": .scan, "progress": .progress, "me": .me][UserDefaults.standard.string(forKey: "startTab") ?? ""] ?? .home
    var sessionOpen = false
    /// What was typed in "Type the code instead", kept so a typo does not mean typing both again.
    var typedRobot = ""
    var typedCode = ""
    var scan: ScanState = .idle

    /// The arm unlocked by the last scan. Kept across launches.
    var activeRobot: String? = UserDefaults.standard.string(forKey: "activeRobot") {
        didSet { UserDefaults.standard.set(activeRobot, forKey: "activeRobot") }
    }
    var demoRobot = UserDefaults.standard.bool(forKey: "demoRobot") {
        didSet { UserDefaults.standard.set(demoRobot, forKey: "demoRobot") }
    }

    /// Today's plan progress: how many of the 5 exercises are done, and sessions done this programme (sample start: 1 and 26).
    var exercisesDone = UserDefaults.standard.object(forKey: "exercisesDone") as? Int ?? 1 { didSet { UserDefaults.standard.set(exercisesDone, forKey: "exercisesDone") } }
    var sessionsDone = UserDefaults.standard.object(forKey: "sessionsDone") as? Int ?? 26 { didSet { UserDefaults.standard.set(sessionsDone, forKey: "sessionsDone") } }
    var nextExercise: Int? { exercisesDone < Sample.exercises.count ? exercisesDone : nil }

    /// Called when an exercise is finished; the last one completes today's session.
    func completeExercise() {
        guard exercisesDone < Sample.exercises.count else { return }
        exercisesDone += 1
        if exercisesDone == Sample.exercises.count { sessionsDone += 1 }
    }

    var largeText = UserDefaults.standard.object(forKey: "largeText") as? Bool ?? false { didSet { save("largeText", largeText) } }
    var readAloud = UserDefaults.standard.object(forKey: "readAloud") as? Bool ?? true { didSet { save("readAloud", readAloud) } }
    var sounds = UserDefaults.standard.object(forKey: "sounds") as? Bool ?? false { didSet { save("sounds", sounds) } }
    var shareWithFamily = UserDefaults.standard.object(forKey: "shareWithFamily") as? Bool ?? true { didSet { save("shareWithFamily", shareWithFamily) } }

    private func save(_ key: String, _ value: Bool) { UserDefaults.standard.set(value, forKey: key) }

    /// Unlocks the arm named in a scanned code. With a server set up it asks the server;
    /// without one it runs in demo mode so the app can be tried on its own.
    func activate(_ raw: String) async {
        guard let code = ActivationCode.parse(raw) else {
            scan = .failed("That code did not work. Check the arm number and the code printed on the sticker, and try again.")
            return
        }
        scan = .working(code.robot)
        if let api = APIClient.saved() {
            do {
                try await api.activate(code)
                finish(code.robot, demo: false)
            } catch {
                scan = .failed(error.localizedDescription)
            }
        } else {
            try? await Task.sleep(for: .milliseconds(900))
            finish(code.robot, demo: true)
        }
    }

    private func finish(_ robot: String, demo: Bool) {
        activeRobot = robot
        demoRobot = demo
        scan = .done(robot: robot, demo: demo)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
    }

    func disconnect() {
        activeRobot = nil
        scan = .idle
    }

    /// "Start session" needs an unlocked arm; without one it sends you to the scanner.
    func startSession() {
        if activeRobot == nil { scan = .idle; tab = .scan } else { sessionOpen = true }
    }
}

/// Sample patient data from the design, for an arm programme.
enum Sample {
    static let liftHistory: [Double] = [95, 97, 99, 100, 102, 103, 105, 106, 107, 108, 109, 110]
    static let goal: Double = 120
    static let exercises: [(name: String, meta: String)] = [
        ("Shoulder rolls", "2 min · warm-up"),
        ("Seated arm lift", "10 lifts · the arm helps you"),
        ("Forward reach", "8 reaches · the arm guides you"),
        ("Grip and release", "3 × 30 s · hold the handle"),
        ("Cool-down breathing", "3 min"),
    ]
}
