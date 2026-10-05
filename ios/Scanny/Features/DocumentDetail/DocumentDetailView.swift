import SwiftUI
import UIKit

struct DocumentDetailView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let documentID: Int
    @State private var loaded: ScannyDocument?
    @State private var scanImage: UIImage?
    @State private var showingEditor = false
    @State private var showingAdjuster = false
    @State private var showingShare = false
    @State private var confirmingDelete = false
    @State private var error: String?

    private var document: ScannyDocument? { state.documents.first { $0.id == documentID } ?? loaded }

    var body: some View {
        Group {
            if let document {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let scanImage {
                            ZoomableImage(image: scanImage).frame(height: 480)
                                .background(Color(.secondarySystemBackground)).clipShape(RoundedRectangle(cornerRadius: 12))
                        } else {
                            RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)).frame(height: 420).overlay(ProgressView())
                        }
                        if document.category.isSystem {
                            CategoryAssignmentPrompt(document: document)
                        }
                        HStack { CategoryBadge(category: document.category); Spacer(); Text(document.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary) }
                        if document.processingStatus != .complete { StatusBadge(status: document.processingStatus) }
                        if document.processingStatus == .needsReview {
                            Button("Adjust Scan", systemImage: "viewfinder") { showingAdjuster = true }
                                .buttonStyle(.borderedProminent).tint(.scannyRed)
                        }
                        if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                    }.padding()
                }
                .navigationTitle(document.title).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button("Edit", systemImage: "pencil") { showingEditor = true }
                        Menu {
                            Button("Share", systemImage: "square.and.arrow.up") { showingShare = true }
                                .disabled(scanImage == nil)
                            Button("Print", systemImage: "printer") { if let scanImage { printImage(scanImage, title: document.title) } }
                                .disabled(scanImage == nil)
                            Button("Adjust Scan", systemImage: "viewfinder") { showingAdjuster = true }
                                .disabled(document.processingStatus.isActive)
                            Divider()
                            Button("Delete", systemImage: "trash", role: .destructive) { confirmingDelete = true }
                                .disabled(document.processingStatus.isActive)
                        } label: { Image(systemName: "ellipsis.circle") }
                    }
                }
                .sheet(isPresented: $showingEditor) { DocumentEditorView(document: document) }
                .fullScreenCover(isPresented: $showingAdjuster) { AdjustScanView(document: document) }
                .sheet(isPresented: $showingShare) { if let scanImage { ShareSheet(items: [scanImage]) } }
                .alert("Delete this scan?", isPresented: $confirmingDelete) {
                    Button("Cancel", role: .cancel) {}
                    Button("Delete", role: .destructive) { deleteDocument() }
                } message: { Text("This permanently removes the document and its images.") }
                .task(id: document.scannedImageUrl) { await loadImage(path: document.scannedImageUrl) }
            } else { ProgressView().task { await loadDocument() } }
        }
    }

    private func loadDocument() async {
        do { loaded = try await state.documentService.get(documentID) }
        catch { self.error = error.localizedDescription }
    }

    private func loadImage(path: String) async {
        do {
            let data = try await state.api.data(from: path)
            scanImage = await Task.detached(priority: .utility) { UIImage(data: data) }.value
        }
        catch { self.error = error.localizedDescription }
    }

    private func deleteDocument() {
        Task {
            do { try await state.documentService.delete(documentID); await state.refresh(silently: true); dismiss() }
            catch { self.error = error.localizedDescription }
        }
    }

    private func printImage(_ image: UIImage, title: String) {
        let controller = UIPrintInteractionController.shared
        let info = UIPrintInfo(dictionary: nil)
        info.jobName = title; info.outputType = .photo
        controller.printInfo = info; controller.printingItem = image
        controller.present(animated: true)
    }
}

private struct DocumentEditorView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let document: ScannyDocument
    @State private var title: String
    @State private var categoryID: Int
    @State private var saving = false
    @State private var error: String?

    init(document: ScannyDocument) {
        self.document = document
        _title = State(initialValue: document.title)
        _categoryID = State(initialValue: document.categoryId)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Title") { TextField("Document title", text: $title) }
                Section("Folder") {
                    Picker("Folder", selection: $categoryID) {
                        ForEach(state.categories) { category in Text(category.name).tag(category.id) }
                    }.pickerStyle(.inline).labelsHidden()
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("Edit Document").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save() }.disabled(saving || title.trimmingCharacters(in: .whitespaces).isEmpty) }
            }
        }
    }

    private func save() {
        saving = true
        Task {
            do {
                let updated = try await state.documentService.update(document.id, title: title, categoryID: categoryID)
                state.replace(updated); await state.refresh(silently: true); dismiss()
            } catch { self.error = error.localizedDescription }
            saving = false
        }
    }
}

private struct ZoomableImage: UIViewRepresentable {
    let image: UIImage
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> UIScrollView {
        let scroll = UIScrollView()
        scroll.delegate = context.coordinator; scroll.minimumZoomScale = 1; scroll.maximumZoomScale = 5
        scroll.showsVerticalScrollIndicator = false; scroll.showsHorizontalScrollIndicator = false
        let imageView = context.coordinator.imageView
        imageView.contentMode = .scaleAspectFit; imageView.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(imageView)
        NSLayoutConstraint.activate([
            imageView.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor), imageView.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor),
            imageView.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor), imageView.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor),
            imageView.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor), imageView.heightAnchor.constraint(equalTo: scroll.frameLayoutGuide.heightAnchor)
        ])
        return scroll
    }
    func updateUIView(_ scroll: UIScrollView, context: Context) { context.coordinator.imageView.image = image }
    final class Coordinator: NSObject, UIScrollViewDelegate {
        let imageView = UIImageView()
        func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }
    }
}
