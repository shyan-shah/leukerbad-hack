import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        ZStack {
            Vita.page.ignoresSafeArea()
            Group {
                switch model.tab {
                case .home: HomeView()
                case .exercises: ExercisesView()
                case .scan: ScanView()
                case .progress: ProgressTab()
                case .me: MeView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .safeAreaInset(edge: .bottom) { TabBar() }
        .fullScreenCover(isPresented: $model.sessionOpen) { SessionView() }
        .foregroundStyle(Vita.ink)
    }
}

/// Bottom tabs: a white bar with big icons and labels; the open tab sits on a pale cyan pill that slides.
/// Scan sits in the middle so the scanner is always one tap away.
struct TabBar: View {
    @Environment(AppModel.self) private var model
    @Namespace private var pill

    var body: some View {
        HStack(spacing: 2) {
            item(.home, "Home", "house.fill")
            item(.exercises, "Exercises", "figure.arms.open")
            item(.scan, "Scan", "qrcode.viewfinder")
            item(.progress, "Progress", "chart.bar.fill")
            item(.me, "Me", "person.fill")
        }
        .padding(6)
        .background(Vita.page, in: Capsule())
        .overlay(Capsule().stroke(Vita.line))
        .shadow(color: Vita.primary.opacity(0.12), radius: 12, y: 4)
        .padding(.horizontal, 12)
        .padding(.bottom, 4)
        .animation(.spring(response: 0.45, dampingFraction: 0.75), value: model.tab)
        .dynamicTypeSize(...DynamicTypeSize.xxLarge) // five labels must fit one row; VoiceOver and large-content still read them
    }

    private func item(_ tab: Tab, _ label: String, _ icon: String) -> some View {
        let on = model.tab == tab
        return Button {
            if tab == .scan { model.scan = .idle }
            model.tab = tab
        } label: {
            VStack(spacing: 3) {
                Image(systemName: icon).font(.system(size: 24, weight: .semibold))
                Text(label).scaledFont(15, .bold).lineLimit(1).minimumScaleFactor(0.75)
            }
            .frame(maxWidth: .infinity, minHeight: 64)
            .foregroundStyle(on ? Vita.primary : Vita.muted)
            .background {
                if on { Capsule().fill(Vita.accentSoft).matchedGeometryEffect(id: "pill", in: pill) }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(tab == .scan ? "Scan the code on your arm" : label)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
