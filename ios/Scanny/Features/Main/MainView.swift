import SwiftUI

private enum MainTab: Hashable {
    case recent
    case folders
    case search
}

struct MainView: View {
    @Environment(AppState.self) private var state
    @State private var selectedTab: MainTab = .recent

    var body: some View {
        @Bindable var state = state
        ZStack(alignment: .bottomTrailing) {
            TabView(selection: $selectedTab) {
                NavigationStack { RecentView() }
                    .tabItem { Label("Recent", systemImage: "clock") }
                    .tag(MainTab.recent)
                NavigationStack { FoldersView() }
                    .tabItem { Label("Folders", systemImage: "folder") }
                    .tag(MainTab.folders)
                NavigationStack { SearchView() }
                    .tabItem { Label("Search", systemImage: "magnifyingglass") }
                    .tag(MainTab.search)
            }
            if selectedTab != .search {
                FloatingCameraButton { state.cameraPresented = true }
                    .padding(.trailing, 20).padding(.bottom, 72)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.18), value: selectedTab)
        .fullScreenCover(isPresented: $state.cameraPresented) { CameraView() }
        .task { await state.pollingLoop() }
    }
}
