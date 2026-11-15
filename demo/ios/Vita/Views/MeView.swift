import SwiftUI

struct MeView: View {
    @Environment(AppModel.self) private var model
    @State private var connection = false
    @State private var confirmDisconnect = false

    var body: some View {
        @Bindable var model = model
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 14) {
                    Avatar(initials: "AK", size: 64)
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Anna Keller").display(30)
                        Text("Arm recovery · since 5 Oct").scaledFont(19).foregroundStyle(Vita.muted)
                    }
                }
                Panel {
                    toggle("Large text", $model.largeText)
                    Divider().overlay(Vita.line)
                    toggle("Read instructions aloud", $model.readAloud)
                    Divider().overlay(Vita.line)
                    toggle("Sounds during exercises", $model.sounds)
                }
                Panel {
                    Toggle(isOn: $model.shareWithFamily) {
                        HStack(spacing: 12) {
                            Avatar(initials: "LK", size: 48, plain: true)
                            VStack(alignment: .leading, spacing: 0) {
                                Text("Share progress with Lea").scaledFont(19, .bold)
                                Text("Your daughter").scaledFont(17).foregroundStyle(Vita.muted)
                            }
                        }
                    }
                    .tint(Vita.accent).frame(minHeight: 72)
                }
                Panel {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 12) {
                            Image(systemName: "dot.radiowaves.left.and.right").font(.system(size: 20, weight: .semibold)).frame(width: 48, height: 48)
                                .background(Vita.accentSoft, in: Circle()).foregroundStyle(Vita.accent)
                            VStack(alignment: .leading, spacing: 0) {
                                Text(model.activeRobot.map { "Arm \($0)" } ?? "No arm connected").scaledFont(19, .bold)
                                Text(model.activeRobot == nil ? "Scan the code on the arm" : "Connected")
                                    .scaledFont(17).foregroundStyle(Vita.muted)
                            }
                            Spacer()
                        }
                        if model.activeRobot != nil {
                            Button("Disconnect") { confirmDisconnect = true }
                                .scaledFont(19, .bold).foregroundStyle(Vita.accent)
                                .frame(minWidth: 56, minHeight: 56)
                                .confirmationDialog("Disconnect arm \(model.activeRobot ?? "")?", isPresented: $confirmDisconnect, titleVisibility: .visible) {
                                    Button("Disconnect", role: .destructive, action: model.disconnect)
                                } message: { Text("You will need to scan the code on the arm again before your next exercise.") }
                        } else {
                            Button("Scan the code") { model.scan = .idle; model.tab = .scan }.scaledFont(19, .bold).foregroundStyle(Vita.accent).frame(minWidth: 56, minHeight: 56)
                        }
                    }
                    .padding(.vertical, 8)
                    Divider().overlay(Vita.line)
                    Button { connection = true } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "key.fill").font(.system(size: 20, weight: .semibold)).frame(width: 48, height: 48)
                                .background(Vita.page, in: Circle()).foregroundStyle(Vita.muted)
                            VStack(alignment: .leading, spacing: 0) {
                                Text("Connection").scaledFont(19, .bold)
                                Text(APIClient.saved() == nil ? "For your care team or family" : "Server connected")
                                    .scaledFont(17).foregroundStyle(Vita.muted)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").foregroundStyle(Vita.muted)
                        }
                        .frame(minHeight: 72)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 24)
        }
        .sheet(isPresented: $connection) { ConnectionView() }
    }

    private func toggle(_ label: String, _ value: Binding<Bool>) -> some View {
        Toggle(label, isOn: value).scaledFont(19, .semibold).tint(Vita.accent).frame(minHeight: 64)
    }
}

/// Server address and API key. The key goes to the Keychain; the address to UserDefaults.
struct ConnectionView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var server = UserDefaults.standard.string(forKey: "serverURL") ?? ""
    @State private var key = ""
    @State private var hasKey = Keychain.read("apiKey") != nil
    @State private var status: String?
    @State private var ok = false
    @State private var busy = false
    @State private var confirmRemove = false

    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Server"), footer: Text("https address of the Vita server, or http://<arm address> on your home Wi-Fi.")) {
                    TextField("https://api.example.com", text: $server)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                }
                Section(header: Text("API key"), footer: Text(hasKey ? "A key is saved in the Keychain. Type a new one to replace it." : "Paste the key from your care team. It is stored in the iOS Keychain on this phone only.")) {
                    SecureField(hasKey ? "•••••••• (saved)" : "Paste API key", text: $key)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    if hasKey {
                        Button("Remove saved key", role: .destructive) { confirmRemove = true }
                            .confirmationDialog("Remove the saved key?", isPresented: $confirmRemove, titleVisibility: .visible) {
                                Button("Remove key", role: .destructive) { Keychain.delete("apiKey"); hasKey = false; status = nil }
                            } message: { Text("Vita cannot reach the server until a key is added again.") }
                    }
                }
                Section(footer: Text(APIClient.saved() == nil ? "Until a server is connected, Vita runs in demo mode: any valid arm code unlocks a pretend arm." : "")) {
                    Button { Task { await saveAndTest() } } label: {
                        Text(busy ? "Testing…" : "Save and test connection").scaledFont(17, .bold).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large).tint(Vita.primary).foregroundStyle(.white)
                    .disabled(busy || server.isEmpty || (key.isEmpty && !hasKey))
                    if let status {
                        Label(status, systemImage: ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(ok ? Vita.accent : Vita.danger)
                    }
                }
            }
            .tint(Vita.accent)
            .navigationTitle("Connection")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    private func saveAndTest() async {
        busy = true; defer { busy = false }
        do {
            let url = try APIClient.check(server)
            UserDefaults.standard.set(url.absoluteString, forKey: "serverURL")
            if !key.isEmpty {
                guard Keychain.save(key.trimmingCharacters(in: .whitespacesAndNewlines), for: "apiKey") else {
                    ok = false; status = "Could not save the key on this phone. Try again; if it keeps failing, restart the app."; return
                }
                key = ""; hasKey = true
            }
            guard let api = APIClient.saved() else { ok = false; status = "Add an API key."; return }
            try await api.health()
            ok = true; status = "Connected. Scans now go to this server."
        } catch {
            ok = false; status = error.localizedDescription
        }
    }
}
