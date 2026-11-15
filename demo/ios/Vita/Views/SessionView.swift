import SwiftUI
import AVFoundation
import Combine

/// One exercise with the arm: ten guided lifts, pause any time, then a short check-in.
/// shortcut: lift count is simulated (one every 2.2 s); wire it to the robot's live data when the robot API exists.
struct SessionView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var reps = 0
    @State private var paused = false
    @State private var finished = false
    @State private var feel = "Good"
    @State private var askStop = false
    @State private var pausedBeforeAsk = false
    @State private var speech = AVSpeechSynthesizer()
    private let tick = Timer.publish(every: 2.2, on: .main, in: .common).autoconnect()
    private var index: Int { model.nextExercise ?? Sample.exercises.count - 1 }
    private var name: String { Sample.exercises[index].name }

    var body: some View {
        ZStack {
            Vita.page.ignoresSafeArea()
            // Scrolls only when very large text no longer fits the screen, so the buttons stay reachable.
            ViewThatFits(in: .vertical) {
                page
                ScrollView { page }
            }
        }
        .foregroundStyle(Vita.ink)
        .onReceive(tick) { _ in
            guard !paused, !finished, reps < 10 else { return }
            reps += 1
            if model.sounds { AudioServicesPlaySystemSound(1057) }
            // Counted aloud so Anna can watch her arm, not the phone.
            say(reps == 10 ? "Ten. Well done. Tap Finish." : "\(reps)")
        }
        .onAppear {
            UIApplication.shared.isIdleTimerDisabled = true // the screen must not lock mid-exercise
            // Spoken audio plays even with the ring/silent switch on.
            try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            say("\(name). Hold the handle and move your arm with the robot. Ten times.")
        }
        .onDisappear {
            UIApplication.shared.isIdleTimerDisabled = false
            speech.stopSpeaking(at: .immediate)
        }
        // Stopping never waits for this question: the arm is paused first, then we ask.
        .confirmationDialog("Stop this exercise?", isPresented: $askStop, titleVisibility: .visible) {
            Button("Stop for today", role: .destructive) { finished = true }
            Button("Keep going", role: .cancel) { paused = pausedBeforeAsk; if !paused { say("Let's go on.") } }
        } message: { Text("You have done \(reps) of 10. The arm is paused.") }
    }

    @ViewBuilder private var page: some View {
        if finished { done } else { running }
    }

    private var running: some View {
        VStack(spacing: 20) {
            HStack {
                Text("Exercise \(index + 1) of 5").scaledFont(19, .semibold).foregroundStyle(Vita.muted)
                Spacer()
                Button(action: stop) { Image(systemName: "xmark").font(.system(size: 22, weight: .bold)).frame(width: 56, height: 56).background(Vita.card, in: Circle()).overlay(Circle().stroke(Vita.line)) }
                    .accessibilityLabel("Stop exercise")
            }
            Text(name).display(34).frame(maxWidth: .infinity, alignment: .leading)
            Spacer()
            ZStack {
                Circle().stroke(Vita.accentSoft, lineWidth: 20)
                Circle().trim(from: 0, to: CGFloat(reps) / 10).stroke(Vita.accent, style: .init(lineWidth: 20, lineCap: .round))
                    .rotationEffect(.degrees(-90)).animation(.easeOut(duration: 0.6), value: reps)
                VStack(spacing: 0) {
                    Text("\(reps)").font(.display(88)).contentTransition(.numericText())
                    Text("of 10").scaledFont(20, .semibold).foregroundStyle(Vita.muted)
                }
            }
            .frame(width: 250, height: 250)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(reps) of 10 done")
            HStack(spacing: 8) {
                Circle().fill(paused ? Vita.warning : Vita.accent).frame(width: 12, height: 12)
                Text(paused ? "Paused · the arm is holding still" : "Arm \(model.activeRobot ?? "") is helping you")
            }
            .scaledFont(19, .semibold)
            Spacer()
            if reps >= 10 {
                Button("Finish") { model.completeExercise(); finished = true; say("Well done, Anna.") }.buttonStyle(BigButtonStyle())
            } else {
                Button { paused.toggle(); say(paused ? "Paused." : "Let's go on.") } label: {
                    Label(paused ? "Resume" : "Pause", systemImage: paused ? "play.fill" : "pause.fill")
                }
                .buttonStyle(BigButtonStyle())
                Button("Stop for today", action: stop).scaledFont(20, .semibold).foregroundStyle(Vita.muted).frame(minWidth: 200, minHeight: 56)
            }
        }
        .padding(20)
    }

    private var done: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "checkmark").font(.system(size: 44, weight: .heavy))
                .frame(width: 112, height: 112).background(Vita.accent, in: Circle()).foregroundStyle(.white)
            Text(reps >= 10 ? "Well done, Anna" : "Good effort, Anna").display(34)
            Text(reps >= 10 ? "\(name) done · \(model.exercisesDone) of 5 today" : "\(name): \(reps) of 10. You can finish it later.")
                .scaledFont(20).foregroundStyle(Vita.muted).multilineTextAlignment(.center)
            Text("How did that feel?").scaledFont(22, .bold).padding(.top, 12)
            HStack(spacing: 10) {
                ForEach(["Easy", "Good", "Hard"], id: \.self) { f in
                    Button(f) { feel = f }
                        .scaledFont(20, .bold)
                        .frame(maxWidth: .infinity, minHeight: 60)
                        .background(feel == f ? Vita.accentSoft : Vita.card, in: RoundedRectangle(cornerRadius: 18))
                        .overlay(RoundedRectangle(cornerRadius: 18).stroke(feel == f ? Vita.accent : Vita.line, lineWidth: feel == f ? 3 : 1))
                        .foregroundStyle(feel == f ? Vita.primary : Vita.ink)
                        .accessibilityAddTraits(feel == f ? .isSelected : [])
                }
            }
            Spacer()
            Button("Back to home") { model.tab = .home; dismiss() }.buttonStyle(BigButtonStyle())
        }
        .padding(20)
    }

    /// Pause the arm at once, then ask; reps are lost only after "Stop for today".
    private func stop() {
        guard reps > 0 else { dismiss(); return }
        guard reps < 10 else { model.completeExercise(); finished = true; return }
        pausedBeforeAsk = paused
        paused = true
        askStop = true
    }

    private func say(_ text: String) {
        guard model.readAloud else { return }
        speech.stopSpeaking(at: .immediate)
        let u = AVSpeechUtterance(string: text)
        u.voice = AVSpeechSynthesisVoice(language: "en-GB") // the app's text is English, whatever the phone's language
        u.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
        speech.speak(u)
    }
}
