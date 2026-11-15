import SwiftUI
import AVFoundation

/// The middle tab: scan the sticker on the arm to unlock it.
struct ScanView: View {
    @Environment(AppModel.self) private var model
    @State private var camera = AVCaptureDevice.authorizationStatus(for: .video)
    @State private var typing = false
    @State private var scannerID = UUID()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Connect your arm").display(32)
                    Text("Scan the code on the side of your Vita arm.").scaledFont(19).foregroundStyle(Vita.muted)
                }
                switch model.scan {
                case .done(let robot, let demo): success(robot, demo)
                default: scanner
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 24)
        }
        .sheet(isPresented: $typing) { TypeCodeSheet() }
        .task {
            if camera == .notDetermined {
                _ = await AVCaptureDevice.requestAccess(for: .video)
                camera = AVCaptureDevice.authorizationStatus(for: .video)
            }
        }
    }

    @ViewBuilder private var scanner: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 32, style: .continuous).fill(Vita.card)
            if camera == .authorized && QRScanner.hasCamera {
                QRScanner { text in Task { await model.activate(text) } }
                    .id(scannerID)
                    .clipShape(RoundedRectangle(cornerRadius: 32, style: .continuous))
                Viewfinder().padding(48)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "camera.fill").font(.system(size: 40)).foregroundStyle(Vita.muted)
                    Text(camera == .denied || camera == .restricted ? "Vita may not use the camera. Allow it in Settings, or type the code." : "No camera here. Type the code instead.")
                        .scaledFont(19).multilineTextAlignment(.center).foregroundStyle(Vita.ink).padding(.horizontal, 24)
                    if camera == .denied {
                        Button("Open Settings") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }
                            .scaledFont(19, .bold).foregroundStyle(Vita.accent)
                    }
                }
            }
            if case .working(let robot) = model.scan {
                RoundedRectangle(cornerRadius: 32, style: .continuous).fill(.white.opacity(0.85))
                VStack(spacing: 12) { ProgressView().tint(Vita.accent).scaleEffect(1.6); Text("Connecting to arm \(robot)…").scaledFont(19, .semibold) }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityLabel("Camera. Point it at the code on the arm.")

        if case .failed(let why) = model.scan {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Vita.danger)
                Text(why).scaledFont(18)
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(hex: 0xFDECEA), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            if camera == .authorized && QRScanner.hasCamera {
                Button("Scan again") { model.scan = .idle; scannerID = UUID() }.buttonStyle(BigButtonStyle())
            }
        }
        Button { typing = true } label: { Label("Type the code instead", systemImage: "keyboard") }
            .buttonStyle(BigButtonStyle.secondary)
    }

    private func success(_ robot: String, _ demo: Bool) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark").font(.system(size: 44, weight: .heavy))
                .frame(width: 112, height: 112).background(Vita.accent, in: Circle()).foregroundStyle(.white)
                .padding(.top, 24)
            Text("Arm \(robot) is ready").display(30)
            Text("The arm is unlocked for you.").scaledFont(20).foregroundStyle(Vita.muted)
            Button { model.tab = .home; model.startSession() } label: { Label("Start exercise", systemImage: "play.fill") }
                .buttonStyle(BigButtonStyle())
                .padding(.top, 8)
            Button("Scan a different arm") { model.scan = .idle; scannerID = UUID() }
                .scaledFont(20, .semibold).foregroundStyle(Vita.accent).frame(minWidth: 200, minHeight: 60)
        }
        .frame(maxWidth: .infinity)
    }
}

/// Four cyan corners over the camera.
struct Viewfinder: View {
    var body: some View {
        GeometryReader { g in
            let s = g.size, l: CGFloat = 36
            Path { p in
                p.move(to: .init(x: 0, y: l)); p.addLine(to: .zero); p.addLine(to: .init(x: l, y: 0))
                p.move(to: .init(x: s.width - l, y: 0)); p.addLine(to: .init(x: s.width, y: 0)); p.addLine(to: .init(x: s.width, y: l))
                p.move(to: .init(x: s.width, y: s.height - l)); p.addLine(to: .init(x: s.width, y: s.height)); p.addLine(to: .init(x: s.width - l, y: s.height))
                p.move(to: .init(x: l, y: s.height)); p.addLine(to: .init(x: 0, y: s.height)); p.addLine(to: .init(x: 0, y: s.height - l))
            }
            .stroke(Vita.mint, style: .init(lineWidth: 6, lineCap: .round, lineJoin: .round))
        }
        .accessibilityHidden(true)
    }
}

/// Fallback when there is no camera: type the robot number and the code printed under the QR.
struct TypeCodeSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section(header: Text("Arm number").scaledFont(17, .semibold)) {
                    TextField("For example R-01", text: $model.typedRobot).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .scaledFont(20).frame(minHeight: 48)
                }
                Section(header: Text("Code").scaledFont(17, .semibold),
                        footer: Text("Both are printed under the square code on the arm.").scaledFont(16)) {
                    TextField("For example 8F3K2Q", text: $model.typedCode).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .scaledFont(20).frame(minHeight: 48)
                }
                Section {
                    Button("Connect", action: connect)
                        .buttonStyle(BigButtonStyle())
                        .disabled(model.typedRobot.isEmpty || model.typedCode.isEmpty)
                        .opacity(model.typedRobot.isEmpty || model.typedCode.isEmpty ? 0.5 : 1)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets())
                }
            }
            .navigationTitle("Type the code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
        }
        .presentationDetents([.large])
    }

    private func connect() {
        let raw = "VITA:\(model.typedRobot.trimmingCharacters(in: .whitespaces)):\(model.typedCode.trimmingCharacters(in: .whitespaces))"
        dismiss()
        Task { await model.activate(raw) }
    }
}
