import SwiftUI
import Charts

struct ProgressTab: View {
    @Environment(\.dynamicTypeSize) private var textSize

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Your progress").display(32)
                VStack(alignment: .leading, spacing: 4) {
                    TileLabel(text: "Arm lift")
                    VStack(alignment: .leading, spacing: 0) {
                        Text("110°").display(52).foregroundStyle(Vita.ink)
                        Text("15° higher than in week 1").scaledFont(19, .bold).foregroundStyle(Vita.accent)
                    }
                    Chart {
                        ForEach(Array(Sample.liftHistory.enumerated()), id: \.offset) { i, v in
                            AreaMark(x: .value("Week", i), yStart: .value("Base", 90), yEnd: .value("Lift", v)).foregroundStyle(Vita.accent.opacity(0.12))
                            LineMark(x: .value("Week", i), y: .value("Lift", v)).foregroundStyle(Vita.accent).lineStyle(.init(lineWidth: 4))
                        }
                        RuleMark(y: .value("Goal", Sample.goal))
                            .foregroundStyle(Vita.muted).lineStyle(.init(lineWidth: 1.5, dash: [5, 4]))
                            .annotation(position: .top, alignment: .trailing) { Text("Goal 120°").scaledFont(17, .bold).foregroundStyle(Vita.ink) }
                    }
                    .chartYScale(domain: 90...124)
                    .chartXAxis(.hidden).chartYAxis(.hidden)
                    .frame(height: 150)
                    .padding(.top, 24) // room for the goal label above the chart
                    .accessibilityLabel("Arm lift from 95 degrees on 5 October to 110 degrees on 12 November, goal 120")
                    HStack { Text("5 Oct"); Spacer(); Text("12 Nov") }.scaledFont(17).foregroundStyle(Vita.muted)
                }
                .padding(18)
                .background(Vita.accentSoft, in: RoundedRectangle(cornerRadius: 28, style: .continuous))

                // Side by side normally; stacked once the text is too big for two columns.
                (textSize >= .xxxLarge ? AnyLayout(VStackLayout(spacing: 10)) : AnyLayout(HStackLayout(spacing: 10))) {
                    Tile {
                        TileLabel(text: "Grip strength")
                        Text("18.4 kg").display(32).padding(.top, 8)
                        Text("32% stronger").scaledFont(17, .bold).foregroundStyle(Vita.accent)
                    }
                    Tile {
                        TileLabel(text: "Pain after")
                        Text("3 of 10").display(32).padding(.top, 8)
                        Text("It was 6").scaledFont(17, .bold).foregroundStyle(Vita.accent)
                    }
                }
                Panel {
                    milestone("Arm lifted to shoulder height", done: true)
                    Divider().overlay(Vita.line)
                    milestone("Reach a cup on the kitchen shelf", done: false)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 24)
        }
    }

    private func milestone(_ text: String, done: Bool) -> some View {
        HStack(spacing: 14) {
            Image(systemName: done ? "checkmark" : "flag.fill").font(.system(size: 18, weight: .heavy))
                .frame(width: 44, height: 44)
                .background(done ? Vita.accent : Vita.accentSoft, in: Circle())
                .foregroundStyle(done ? .white : Vita.accent)
            VStack(alignment: .leading) {
                Text(text).scaledFont(19, .semibold)
                Text(done ? "Reached in week 5" : "Next goal").scaledFont(17).foregroundStyle(Vita.muted)
            }
            Spacer()
        }
        .frame(minHeight: 72)
    }
}
