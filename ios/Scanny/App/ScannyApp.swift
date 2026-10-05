import SwiftUI

@main
struct ScannyApp: App {
    @State private var state = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(state)
                .tint(Color.scannyRed)
                .task { await state.restoreSession() }
        }
    }
}

struct RootView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        Group {
            switch state.session {
            case .loading:
                VStack(spacing: 14) {
                    Image(systemName: "doc.viewfinder").font(.system(size: 42, weight: .semibold)).foregroundStyle(Color.scannyRed)
                    ProgressView()
                }
            case .signedOut: AuthView()
            case .signedIn: MainView()
            }
        }
        .animation(.easeInOut(duration: 0.22), value: state.session)
    }
}

extension Color {
    static let scannyRed = Color(red: 250 / 255, green: 57 / 255, blue: 57 / 255)
    static let reviewYellow = Color(red: 1, green: 0.72, blue: 0.18)
}
