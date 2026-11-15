import Foundation

/// Talks to the Vita server (or the robot itself on the home network).
///
/// Contract (see ios/README.md):
///   GET  {base}/v1/health                      -> 2xx when the key is accepted
///   POST {base}/v1/robots/{robot}/activate     body {"code": "..."} -> 2xx when the arm is unlocked
/// Every request carries `Authorization: Bearer <API key>`.
struct APIClient {
    enum Failure: LocalizedError {
        case notConfigured, badURL, insecure, http(Int), offline(String)
        var errorDescription: String? {
            switch self {
            case .notConfigured: return "No server connected yet."
            case .badURL: return "That server address is not valid."
            case .insecure: return "Use an https address. Plain http only works for a robot on your home network."
            case .http(401), .http(403): return "The server did not accept the API key."
            case .http(404): return "The server does not know this arm."
            case .http(let code): return "The server answered with error \(code)."
            case .offline(let why): return "Could not reach the server. \(why)"
            }
        }
    }

    let baseURL: URL
    let apiKey: String

    /// Builds a client from the saved settings, or nil when no server is set up (the app then runs in demo mode).
    static func saved() -> APIClient? {
        guard let s = UserDefaults.standard.string(forKey: "serverURL"), !s.isEmpty,
              let url = URL(string: s), let key = Keychain.read("apiKey"), !key.isEmpty else { return nil }
        return APIClient(baseURL: url, apiKey: key)
    }

    /// Only https, or http to a host on the local network: the API key must never cross the internet unencrypted.
    static func check(_ text: String) throws -> URL {
        guard let url = URL(string: text.trimmingCharacters(in: .whitespaces)), let scheme = url.scheme?.lowercased(),
              let host = url.host, !host.isEmpty else { throw Failure.badURL }
        if scheme == "https" { return url }
        guard scheme == "http" else { throw Failure.badURL }
        let local = host == "localhost" || host.hasSuffix(".local") || host.hasPrefix("10.") || host.hasPrefix("192.168.")
            || host == "127.0.0.1" || (host.hasPrefix("172.") && (16...31).contains(Int(host.split(separator: ".").dropFirst().first ?? "") ?? 0))
        if local { return url }
        throw Failure.insecure
    }

    func health() async throws {
        _ = try await send(request("v1/health", method: "GET"))
    }

    func activate(_ code: ActivationCode) async throws {
        var req = request("v1/robots/\(code.robot)/activate", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["code": code.code])
        _ = try await send(req)
    }

    private func request(_ path: String, method: String) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(path), timeoutInterval: 15)
        req.httpMethod = method
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        return req
    }

    private func send(_ req: URLRequest) async throws -> Data {
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(status) else { throw Failure.http(status) }
            return data
        } catch let f as Failure {
            throw f
        } catch {
            throw Failure.offline(error.localizedDescription)
        }
    }
}
