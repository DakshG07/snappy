import SwiftUI

private struct FolderEditor: Identifiable {
    let id = UUID()
    let category: Category?
    var initialName: String { category?.name ?? "" }
}

private enum FolderRoute: Hashable {
    case folder(Int)
    case document(Int)
}

struct FoldersView: View {
    @Environment(AppState.self) private var state
    @State private var editor: FolderEditor?
    @State private var deleting: Category?

    private var visibleCategories: [Category] {
        state.categories.filter { !$0.isSystem || $0.documentCount > 0 }
    }

    var body: some View {
        Group {
            if visibleCategories.isEmpty {
                ContentUnavailableView("No folders yet", systemImage: "folder", description: Text("Create a folder to organize your scans."))
            } else {
                List(visibleCategories) { category in
                    NavigationLink(value: FolderRoute.folder(category.id)) {
                        HStack(spacing: 14) {
                            Image(systemName: category.isSystem ? "folder.fill.badge.questionmark" : "folder.fill")
                                .font(.title2).foregroundStyle(category.isSystem ? Color.reviewYellow : Color.scannyRed)
                                .frame(width: 38, height: 38).background((category.isSystem ? Color.reviewYellow : Color.scannyRed).opacity(0.12), in: RoundedRectangle(cornerRadius: 9))
                            VStack(alignment: .leading, spacing: 3) {
                                Text(category.name).font(.headline)
                                Text("\(category.documentCount) \(category.documentCount == 1 ? "document" : "documents")").font(.caption).foregroundStyle(.secondary)
                            }
                        }.padding(.vertical, 5)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if !category.isSystem {
                            Button("Delete", systemImage: "trash", role: .destructive) { deleting = category }.disabled(category.documentCount > 0)
                            Button("Rename", systemImage: "pencil") { editor = FolderEditor(category: category) }.tint(.orange)
                        }
                    }
                    .contextMenu {
                        if !category.isSystem {
                            Button("Rename", systemImage: "pencil") { editor = FolderEditor(category: category) }
                            Button("Delete", systemImage: "trash", role: .destructive) { deleting = category }.disabled(category.documentCount > 0)
                        }
                    }
                }
                .listStyle(.insetGrouped).refreshable { await state.refresh() }
            }
        }
        .navigationTitle("Folders")
        .navigationDestination(for: FolderRoute.self) { route in
            switch route {
            case .folder(let categoryID): FolderDocumentsView(categoryID: categoryID)
            case .document(let documentID): DocumentDetailView(documentID: documentID)
            }
        }
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("New folder", systemImage: "folder.badge.plus") { editor = FolderEditor(category: nil) } } }
        .sheet(item: $editor) { FolderEditorView(editor: $0) }
        .alert("Delete folder?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
            Button("Cancel", role: .cancel) { deleting = nil }
            Button("Delete", role: .destructive) { if let deleting { delete(deleting) } }
        } message: { Text("Only empty folders can be deleted.") }
    }

    private func delete(_ category: Category) {
        Task {
            do { try await state.categoryService.delete(category.id); deleting = nil; await state.refresh(silently: true) }
            catch { state.errorMessage = error.localizedDescription }
        }
    }
}

private struct FolderEditorView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let editor: FolderEditor
    @State private var name: String
    @State private var saving = false
    @State private var error: String?

    init(editor: FolderEditor) { self.editor = editor; _name = State(initialValue: editor.initialName) }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Folder name", text: $name)
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            }
            .navigationTitle(editor.category == nil ? "New Folder" : "Rename Folder").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save() }.disabled(saving || name.trimmingCharacters(in: .whitespaces).isEmpty) }
            }
        }.presentationDetents([.medium])
    }

    private func save() {
        saving = true
        Task {
            do {
                if let category = editor.category { _ = try await state.categoryService.rename(category.id, name: name) }
                else { _ = try await state.categoryService.create(name: name) }
                await state.refresh(silently: true); dismiss()
            } catch { self.error = error.localizedDescription }
            saving = false
        }
    }
}

struct FolderDocumentsView: View {
    @Environment(AppState.self) private var state
    let categoryID: Int
    private var category: Category? { state.categories.first { $0.id == categoryID } }
    private var documents: [ScannyDocument] { state.documents.filter { $0.categoryId == categoryID } }

    var body: some View {
        Group {
            if documents.isEmpty { ContentUnavailableView("Folder is empty", systemImage: "folder") }
            else {
                List(documents) { document in
                    if category?.isSystem == true || document.category.isSystem {
                        VStack(spacing: 0) {
                            NavigationLink(value: FolderRoute.document(document.id)) {
                                DocumentRow(document: document)
                            }
                            Divider().padding(.vertical, 4)
                            CategoryAssignmentPrompt(document: document, compact: true)
                        }
                        .padding(.vertical, 5)
                    } else {
                        NavigationLink(value: FolderRoute.document(document.id)) { DocumentRow(document: document) }
                    }
                }
                    .listStyle(.plain).refreshable { await state.refresh() }
            }
        }
        .navigationTitle(category?.name ?? "Folder")
    }
}
