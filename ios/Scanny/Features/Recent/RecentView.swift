import SwiftUI

struct RecentView: View {
    @Environment(AppState.self) private var state

    private var localOnly: [PendingCapture] {
        state.captureQueue.items.filter { $0.resultingDocumentID == nil && $0.state != .complete }
    }

    var body: some View {
        Group {
            if state.documents.isEmpty && localOnly.isEmpty && !state.isRefreshing {
                ContentUnavailableView("No scans yet", systemImage: "doc.viewfinder", description: Text("Tap the camera button and point at a document."))
            } else {
                List {
                    if !localOnly.isEmpty {
                        Section("Captures") {
                            ForEach(localOnly) { item in
                                PendingCaptureRow(item: item) { state.captureQueue.retry(item.id) }
                            }
                        }
                    }
                    Section(state.documents.isEmpty ? "" : "Documents") {
                        ForEach(state.documents) { document in
                            NavigationLink(value: document.id) { DocumentRow(document: document) }
                        }
                    }
                }
                .listStyle(.plain)
                .refreshable { await state.refresh() }
            }
        }
        .navigationTitle("Recent")
        .navigationDestination(for: Int.self) { id in DocumentDetailView(documentID: id) }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    if case .signedIn(let user) = state.session { Text(user.email) }
                    Button("Refresh", systemImage: "arrow.clockwise") { Task { await state.refresh() } }
                    Divider()
                    Button("Log Out", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive) { Task { await state.logout() } }
                } label: { Image(systemName: "person.crop.circle") }
            }
        }
        .overlay(alignment: .top) {
            if let message = state.errorMessage {
                Button { state.errorMessage = nil } label: {
                    Text(message).font(.caption).lineLimit(2).padding(10).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
                }.buttonStyle(.plain).padding()
            }
        }
    }

}
