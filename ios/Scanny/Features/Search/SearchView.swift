import SwiftUI

struct SearchView: View {
    @Environment(AppState.self) private var state
    @State private var query = ""
    @State private var results: [ScannyDocument] = []
    @State private var isSearching = false
    @State private var hasSearched = false
    @State private var searchUnavailable = false
    @State private var searchTask: Task<Void, Never>?
    @FocusState private var searchFocused: Bool

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        Group {
            if hasSearched && !results.isEmpty {
                List(results) { document in
                    NavigationLink(value: document.id) { DocumentRow(document: document) }
                }
                .listStyle(.plain)
                .scrollDismissesKeyboard(.interactively)
            } else {
                ScrollView {
                    searchStatus
                        .frame(maxWidth: .infinity)
                        .containerRelativeFrame(.vertical)
                }
                .scrollDismissesKeyboard(.interactively)
                .scrollBounceBehavior(.always)
            }
        }
        .navigationTitle("Search")
        .navigationDestination(for: Int.self) { id in DocumentDetailView(documentID: id) }
        .safeAreaInset(edge: .bottom) {
            searchControls
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
        .onChange(of: query) { _, newValue in
            if newValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                searchTask?.cancel()
                results = []
                isSearching = false
                hasSearched = false
                searchUnavailable = false
            }
        }
    }

    private var searchFieldContent: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Search your documents", text: $query)
                .focused($searchFocused)
                .submitLabel(.search)
                .onSubmit(submitSearch)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(false)
            if !query.isEmpty {
                Button {
                    query = ""
                    searchFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 52)
    }

    private var searchButton: some View {
        Button(action: submitSearch) {
            Group {
                if isSearching {
                    ProgressView().tint(.white)
                } else {
                    Image(systemName: "magnifyingglass")
                }
            }
            .font(.system(size: 18, weight: .semibold))
            .frame(width: 26, height: 26)
        }
    }

    @ViewBuilder
    private var searchControls: some View {
#if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: 12) {
                HStack(spacing: 12) {
                    searchFieldContent
                        .glassEffect(.regular, in: Capsule())
                    configuredSearchButton
                        .buttonStyle(.glassProminent)
                }
            }
        } else {
            fallbackSearchControls
        }
#else
        fallbackSearchControls
#endif
    }

    @ViewBuilder
    private var searchStatus: some View {
        if isSearching {
            ProgressView("Searching…")
        } else if searchUnavailable {
            ContentUnavailableView(
                "Search is temporarily unavailable.",
                systemImage: "exclamationmark.magnifyingglass"
            )
        } else if hasSearched {
            ContentUnavailableView("No relevant documents found.", systemImage: "doc.text.magnifyingglass")
        } else {
            ContentUnavailableView(
                "Find a document",
                systemImage: "magnifyingglass",
                description: Text("Search by topic, title, folder, or something you remember.")
            )
        }
    }

    private var configuredSearchButton: some View {
        searchButton
            .buttonBorderShape(.circle)
            .controlSize(.large)
            .tint(.scannyRed)
            .disabled(trimmedQuery.count < 2 || isSearching)
            .accessibilityLabel("Search")
    }

    private var fallbackSearchControls: some View {
        HStack(spacing: 12) {
            searchFieldContent
                .background(.regularMaterial, in: Capsule())
                .overlay(Capsule().stroke(Color(.separator).opacity(0.22), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.08), radius: 8, y: 3)
            configuredSearchButton
                .buttonStyle(.borderedProminent)
                .shadow(color: Color.scannyRed.opacity(0.22), radius: 8, y: 3)
        }
    }

    private func submitSearch() {
        let submittedQuery = trimmedQuery
        guard submittedQuery.count >= 2, !isSearching else { return }
        searchTask?.cancel()
        searchFocused = false
        isSearching = true
        hasSearched = true
        searchUnavailable = false
        searchTask = Task {
            do {
                let response = try await state.documentService.search(submittedQuery)
                try Task.checkCancellation()
                withAnimation(.easeInOut(duration: 0.18)) {
                    results = response.map(\.document)
                    isSearching = false
                }
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                results = []
                isSearching = false
                searchUnavailable = true
            }
        }
    }
}
