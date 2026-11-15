import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dynamicTypeSize) private var textSize

    private var greeting: String {
        let h = Calendar.current.component(.hour, from: .now)
        return h < 12 ? "Good morning, Anna" : h < 18 ? "Good afternoon, Anna" : "Good evening, Anna"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 14) {
                    Avatar(initials: "AK", size: 52)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(Date.now.formatted(.dateTime.weekday(.wide).day().month(.wide))).scaledFont(17).foregroundStyle(Vita.muted)
                        Text(greeting).display(26)
                    }
                }
                today
                Text("How you are doing").display(24).padding(.top, 6)
                // Two tiles side by side; one column once the text is too big for two.
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: textSize >= .xxxLarge ? 1 : 2), spacing: 12) {
                    tile(liftTile, "Arm lift 110 degrees, 15 more than at the start")
                    tile(sessionsTile, "\(model.sessionsDone) of 30 sessions done")
                    tile(painTile, "Pain after exercise 3 out of 10, it was 6")
                    tile(helpTile, "The arm now helps 40 percent, it was 80")
                }
                physio
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 24)
        }
    }

    /// Today's session on the dark petrol card: the one thing to do, with one big button.
    private var today: some View {
        VStack(alignment: .leading, spacing: 14) {
            ViewThatFits(in: .horizontal) {
                HStack { Text("Today · 10:00").scaledFont(17, .semibold); Spacer(); chip }
                VStack(alignment: .leading, spacing: 8) { Text("Today · 10:00").scaledFont(17, .semibold); chip }
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("Arm strength").display(34)
                Text("\(model.exercisesDone) of 5 exercises done · week 6 of 12").scaledFont(18, .medium)
            }
            Button(action: model.startSession) {
                Label(model.activeRobot == nil ? "Scan to connect the arm" : model.nextExercise.map { "Start exercise \($0 + 1)" } ?? "All done for today",
                      systemImage: model.activeRobot == nil ? "qrcode.viewfinder" : "play.fill")
            }
            .buttonStyle(BigButtonStyle(background: Vita.mint, foreground: Vita.onMint))
            .disabled(model.activeRobot != nil && model.nextExercise == nil)
        }
        .foregroundStyle(.white)
        .padding(20)
        .background(Vita.primary, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private var chip: some View {
        HStack(spacing: 8) {
            Circle().fill(model.activeRobot == nil ? Color(hex: 0xF6C35A) : Vita.mint).frame(width: 10, height: 10)
            Text(model.activeRobot.map { "Arm \($0) ready" } ?? "Arm not connected")
        }
        .scaledFont(16, .semibold)
        .padding(.horizontal, 12).frame(minHeight: 32)
        .background(Color.white.opacity(0.14), in: Capsule())
    }

    /// Each tile opens Progress and reads as one sentence to VoiceOver.
    private func tile(_ content: some View, _ spoken: String) -> some View {
        Button { model.tab = .progress } label: { content }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spoken)
            .accessibilityHint("Opens your progress")
    }

    private func number(_ big: String, _ small: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(big).display(36)
            Text(small).scaledFont(16, .medium).foregroundStyle(Vita.muted).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var liftTile: some View {
        Tile(fill: Vita.accentSoft, height: 172) {
            TileLabel(text: "Arm lift")
            Spacer(minLength: 10)
            ZStack {
                Circle().trim(from: 0.5, to: 1).stroke(Vita.page, style: .init(lineWidth: 10, lineCap: .round))
                Circle().trim(from: 0.5, to: 0.875).stroke(Vita.accent, style: .init(lineWidth: 10, lineCap: .round))
            }
            .frame(width: 80, height: 80)
            .frame(height: 44, alignment: .top)
            Spacer(minLength: 10)
            number("110°", "15° more than at the start")
        }
    }

    private var sessionsTile: some View {
        let share = Double(model.sessionsDone) / 30
        return Tile(fill: Vita.card, height: 172) {
            TileLabel(text: "Sessions")
            Spacer(minLength: 10)
            ZStack {
                Circle().stroke(Vita.line, lineWidth: 8)
                Circle().trim(from: 0, to: min(share, 1)).stroke(Vita.accent, style: .init(lineWidth: 8, lineCap: .round)).rotationEffect(.degrees(-90))
            }
            .frame(width: 44, height: 44)
            Spacer(minLength: 10)
            number("\(model.sessionsDone) of 30", "2 missed this week")
        }
    }

    private var painTile: some View {
        Tile(fill: Vita.amberSoft, height: 160) {
            TileLabel(text: "Pain after")
            Spacer(minLength: 10)
            HStack(spacing: 3) {
                ForEach(1...10, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 3).fill(i <= 3 ? Vita.amber : Vita.amber.opacity(0.18)).frame(height: 14)
                }
            }
            Spacer(minLength: 10)
            number("3 of 10", "It was 6")
        }
    }

    private var helpTile: some View {
        let help: [Double] = [80, 78, 75, 72, 70, 65, 60, 58, 55, 50, 45, 40]
        return Tile(fill: Vita.violetSoft, height: 160) {
            TileLabel(text: "Arm help")
            Spacer(minLength: 10)
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(help.indices, id: \.self) { i in
                    UnevenRoundedRectangle(topLeadingRadius: 2, topTrailingRadius: 2)
                        .fill(i == help.count - 1 ? Vita.violet : Vita.violet.opacity(0.25))
                        .frame(height: 28 * help[i] / 80)
                }
            }
            .frame(height: 28, alignment: .bottom)
            Spacer(minLength: 10)
            number("40%", "It was 80%")
        }
    }

    private var physio: some View {
        HStack(spacing: 14) {
            Avatar(initials: "LB", size: 52, plain: true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Lukas visits Tuesday").scaledFont(19, .bold)
                Text("14:00 · your physiotherapist").scaledFont(17).foregroundStyle(Vita.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(Vita.card, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Vita.line))
        .accessibilityElement(children: .combine)
    }
}

struct Avatar: View {
    let initials: String
    var size: CGFloat = 44
    var plain = false
    var body: some View {
        Text(initials)
            .font(.inter(size * 0.36, .bold))
            .frame(width: size, height: size)
            .background(plain ? Vita.accentSoft : Vita.primary, in: Circle())
            .foregroundStyle(plain ? Vita.primary : .white)
            .accessibilityHidden(true)
    }
}
