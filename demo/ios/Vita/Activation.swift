import Foundation

/// What a Vita arm's QR code carries: which robot, and a one-time code that proves you are standing next to it.
struct ActivationCode: Equatable {
    let robot: String
    let code: String

    /// Accepts the three forms a sticker may use:
    ///   vita://activate?robot=R-01&code=8F3K2Q
    ///   https://<any host>/activate?robot=R-01&code=8F3K2Q
    ///   VITA:R-01:8F3K2Q
    /// Anything else (or a robot/code with unexpected characters) is rejected, because the text comes from the camera.
    static func parse(_ raw: String) -> ActivationCode? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        var robot: String?, code: String?
        if text.uppercased().hasPrefix("VITA:"), !text.contains("://") {
            let parts = text.split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count == 3 else { return nil }
            robot = String(parts[1]); code = String(parts[2])
        } else if let url = URLComponents(string: text), let scheme = url.scheme?.lowercased(),
                  ["vita", "https"].contains(scheme) {
            let items = url.queryItems ?? []
            robot = items.first { $0.name == "robot" }?.value
            code = items.first { $0.name == "code" }?.value
        }
        guard let r = robot, let c = code, valid(r, "^[A-Za-z0-9-]{1,32}$"), valid(c, "^[A-Za-z0-9]{4,64}$") else { return nil }
        return ActivationCode(robot: r.uppercased(), code: c)
    }

    private static func valid(_ s: String, _ pattern: String) -> Bool {
        s.range(of: pattern, options: .regularExpression) != nil
    }
}
