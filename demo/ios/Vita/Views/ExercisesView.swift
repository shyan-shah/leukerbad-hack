import SwiftUI

struct ExercisesView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Today's exercises").display(32)
                    Text("Arm strength · \(model.exercisesDone) of 5 done").scaledFont(19).foregroundStyle(Vita.muted)
                }
                HStack(spacing: 4) {
                    ForEach(0..<5, id: \.self) { i in Capsule().fill(i < model.exercisesDone ? Vita.accent : Vita.line).frame(height: 10) }
                }
                .accessibilityLabel("\(model.exercisesDone) of 5 exercises done")
                VStack(spacing: 8) {
                    ForEach(Array(Sample.exercises.enumerated()), id: \.offset) { i, e in row(i, e) }
                }
                if let next = model.nextExercise {
                    Button(action: model.startSession) { Label("Start exercise \(next + 1)", systemImage: "play.fill") }
                        .buttonStyle(BigButtonStyle())
                        .padding(.top, 4)
                } else {
                    Text("All done for today. See you tomorrow.").scaledFont(20, .bold).foregroundStyle(Vita.accent)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 24)
        }
    }

    private func row(_ i: Int, _ e: (name: String, meta: String)) -> some View {
        let done = i < model.exercisesDone, next = i == model.exercisesDone
        return HStack(spacing: 14) {
            Group { if done { Image(systemName: "checkmark") } else { Text("\(i + 1)") } }
                .font(.inter(19, .bold))
                .frame(width: 48, height: 48)
                .background(done ? Vita.accent : next ? Vita.primary : Vita.page, in: Circle())
                .overlay(Circle().stroke(done || next ? .clear : Vita.line, lineWidth: 2))
                .foregroundStyle(done || next ? .white : Vita.muted)
            VStack(alignment: .leading, spacing: 0) {
                Text(e.name).scaledFont(20, .bold)
                Text(e.meta).scaledFont(17).foregroundStyle(Vita.muted)
            }
            Spacer()
        }
        .padding(.vertical, 14).padding(.horizontal, 14)
        .background(next ? Vita.accentSoft : Vita.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(next ? Vita.accent : Vita.line, lineWidth: next ? 2 : 1))
        .accessibilityElement(children: .combine)
        .accessibilityValue(done ? "Done" : next ? "Next" : "To do")
    }
}
