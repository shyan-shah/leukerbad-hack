import SwiftUI

@main
struct VitaApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                // Here, not in RootView, so full-screen covers get it too. Large text sets a floor well above
                // the iPhone default; off, the phone's own text size applies.
                .dynamicTypeSize(model.largeText ? .xxLarge ... .accessibility2 : .xSmall ... .accessibility2)
                .preferredColorScheme(.light)
        }
    }
}
