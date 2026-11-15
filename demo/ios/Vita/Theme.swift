import SwiftUI

/// Colours of the Flexiv arm's own lights, as in the team's site and web app (demo/ in the hackathon repo):
/// cyan light rings #58E6F2, petrol #0A4552, teal #0B7F91, silver-white surfaces.
/// Chosen for older eyes: dark ink on white, and every text colour at least 7:1 against its background,
/// so the teal used for text is a deeper shade of the arm's teal, and the cyan only ever sits behind dark text.
enum Vita {
    static let page = Color.white
    static let card = Color(hex: 0xF3F8F8)        // silver-white surface
    static let line = Color(hex: 0xD3DFE2)
    static let ink = Color(hex: 0x172224)
    static let muted = Color(hex: 0x4C5A5D)       // 7.2:1 on white
    static let accent = Color(hex: 0x075E6B)      // the arm's teal, deepened to 7.4:1: links, icons, rings, toggles
    static let accentSoft = Color(hex: 0xE0F1F5)  // pale cyan: selected and soft backgrounds
    static let primary = Color(hex: 0x0A4552)     // petrol: main buttons and the today card
    static let mint = Color(hex: 0x58E6F2)        // the arm's cyan light ring; only as a fill behind dark text
    static let onMint = Color(hex: 0x05303A)      // 9.4:1 on the cyan
    static let danger = Color(hex: 0xB42318)
    static let warning = Color(hex: 0x8A4A06)

    static let amberSoft = Color(hex: 0xFEF3E2)
    static let amber = Color(hex: 0xA8620F)
    static let violetSoft = Color(hex: 0xEFEBFF)
    static let violet = Color(hex: 0x5B3FC4)
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

extension Font {
    /// Fixed-size display type (Bricolage Grotesque, as on the website): only for numbers inside fixed shapes.
    /// Text uses `.display(_:)` on the view, which grows.
    static func display(_ size: CGFloat) -> Font { .custom("BricolageGrotesque-ExtraBold", fixedSize: size) }

    /// The website's Inter at the nearest bundled weight.
    static func inter(_ size: CGFloat, _ weight: Weight) -> Font {
        let name = switch weight {
        case .regular, .light, .thin, .ultraLight: "Inter-Regular"
        case .medium: "Inter-Medium"
        case .semibold: "Inter-SemiBold"
        default: "Inter-Bold"
        }
        return .custom(name, fixedSize: size)
    }
}

/// Text at the design size that grows with the phone's text size and the app's Large text setting.
/// Headlines grow like Large Title (gentler), the rest like Body.
private struct ScaledFont: ViewModifier {
    @ScaledMetric private var size: CGFloat
    private let weight: Font.Weight, display: Bool

    init(_ size: CGFloat, _ weight: Font.Weight, display: Bool) {
        _size = ScaledMetric(wrappedValue: size, relativeTo: size >= 24 ? .largeTitle : .body)
        self.weight = weight
        self.display = display
    }

    // Display type is set tight, as on the website (letter-spacing -0.02em).
    func body(content: Content) -> some View {
        content.font(display ? .display(size) : .inter(size, weight)).tracking(display ? -0.02 * size : 0)
    }
}

extension View {
    func scaledFont(_ size: CGFloat, _ weight: Font.Weight = .regular) -> some View { modifier(ScaledFont(size, weight, display: false)) }
    func display(_ size: CGFloat) -> some View { modifier(ScaledFont(size, .heavy, display: true)) }
}

/// The app's main button: full width, 60 pt tall, large bold label (easy to see and tap for older adults).
/// Default is the petrol button; pass `.secondary` colours for the quieter one.
struct BigButtonStyle: ButtonStyle {
    var background: Color = Vita.primary
    var foreground: Color = .white
    @Environment(\.isEnabled) private var enabled

    static let secondary = BigButtonStyle(background: Vita.accentSoft, foreground: Vita.primary)

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaledFont(20, .bold)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 60)
            .background(enabled ? background : Vita.line, in: Capsule())
            .foregroundStyle(enabled ? foreground : Vita.muted)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// A rounded tile on a soft tint, like the website's cards.
struct Tile<Content: View>: View {
    var fill: Color = Vita.card
    var height: CGFloat? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) { content }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: height, alignment: .topLeading)
            .background(fill, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Vita.line))
    }
}

struct Panel<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: 0) { content }
            .padding(.horizontal, 16)
            .padding(.vertical, 4)
            .background(Vita.card, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Vita.line))
    }
}

/// The small heading at the top of a tile.
struct TileLabel: View {
    let text: String
    var body: some View { Text(text).scaledFont(17, .semibold) }
}
