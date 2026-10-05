import SwiftUI
import UIKit

struct StatusBadge: View {
    let status: ProcessingStatus
    var body: some View {
        HStack(spacing: 4) {
            if status.isActive { ProgressView().controlSize(.mini) }
            else { Image(systemName: status == .failed ? "exclamationmark.circle.fill" : status == .needsReview ? "exclamationmark.triangle.fill" : "checkmark.circle.fill") }
            Text(status.label)
        }
        .font(.caption2.weight(.semibold))
        .foregroundStyle(status == .failed ? .red : status == .needsReview ? .orange : status.isActive ? Color.scannyRed : .secondary)
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(.thinMaterial, in: Capsule())
    }
}

struct CategoryBadge: View {
    let category: CategoryBrief
    var body: some View {
        Text(category.name).font(.caption.weight(.medium)).lineLimit(1)
            .foregroundStyle(category.isSystem ? .orange : Color.scannyRed)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background((category.isSystem ? Color.reviewYellow : Color.scannyRed).opacity(0.13), in: Capsule())
    }
}

struct AuthenticatedImage: View {
    @Environment(AppState.self) private var state
    let path: String
    var contentMode: ContentMode = .fill
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        Group {
            if let image { Image(uiImage: image).resizable().aspectRatio(contentMode: contentMode) }
            else if failed { Image(systemName: "doc.text.image").font(.title2).foregroundStyle(.tertiary) }
            else { ProgressView().controlSize(.small) }
        }
        .task(id: path) {
            do {
                let data = try await state.api.data(from: path)
                let decoded = await Task.detached(priority: .utility) { UIImage(data: data) }.value
                try Task.checkCancellation()
                image = decoded
                failed = decoded == nil
            } catch is CancellationError {
                return
            } catch {
                failed = true
            }
        }
    }
}

struct DocumentRow: View {
    let document: ScannyDocument
    var body: some View {
        HStack(spacing: 13) {
            AuthenticatedImage(path: document.scannedImageUrl)
                .frame(width: 66, height: 82).background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 9)).clipped()
            VStack(alignment: .leading, spacing: 7) {
                Text(document.title).font(.headline).lineLimit(2)
                HStack { CategoryBadge(category: document.category); Spacer(minLength: 4) }
                Text(document.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if document.processingStatus != .complete { StatusBadge(status: document.processingStatus) }
        }
        .padding(.vertical, 5).contentShape(Rectangle())
    }
}

struct CategoryAssignmentPrompt: View {
    @Environment(AppState.self) private var state
    let document: ScannyDocument
    var compact = false
    @State private var saving = false
    @State private var error: String?

    private var availableCategories: [Category] {
        state.categories.filter { !$0.isSystem }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 10 : 14) {
            HStack(alignment: .top, spacing: 11) {
                Image(systemName: "folder.fill.badge.questionmark")
                    .font(compact ? .body : .title3)
                    .foregroundStyle(.orange)
                    .frame(width: compact ? 30 : 36, height: compact ? 30 : 36)
                    .background(Color.reviewYellow.opacity(0.2), in: RoundedRectangle(cornerRadius: 9))
                VStack(alignment: .leading, spacing: 3) {
                    Text("What category is this?")
                        .font(compact ? .subheadline.weight(.semibold) : .headline)
                    if !compact {
                        Text("Choose a folder to finish organizing this document.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Menu {
                ForEach(availableCategories) { category in
                    Button(category.name) { assign(to: category) }
                }
            } label: {
                HStack {
                    if saving { ProgressView().controlSize(.small) }
                    Text(saving ? "Saving…" : availableCategories.isEmpty ? "No categories available" : "Choose category")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down").font(.caption2.weight(.bold))
                }
                .foregroundStyle(.orange)
                .padding(.horizontal, 13)
                .frame(height: 42)
                .background(Color.reviewYellow.opacity(0.16), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.reviewYellow.opacity(0.5), lineWidth: 1))
            }
            .disabled(saving || availableCategories.isEmpty)

            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            } else if availableCategories.isEmpty {
                Text("Create a folder from the Folders tab first.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(compact ? 12 : 16)
        .background(Color.reviewYellow.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.reviewYellow.opacity(0.38), lineWidth: 1))
    }

    private func assign(to category: Category) {
        guard !saving else { return }
        saving = true
        error = nil
        Task {
            do {
                let updated = try await state.documentService.update(document.id, categoryID: category.id)
                withAnimation(.easeInOut(duration: 0.2)) { state.replace(updated) }
                await state.refresh(silently: true)
            } catch {
                self.error = error.localizedDescription
                saving = false
            }
        }
    }
}

struct PendingCaptureRow: View {
    let item: PendingCapture
    let retry: () -> Void
    var body: some View {
        HStack(spacing: 13) {
            RoundedRectangle(cornerRadius: 9).fill(Color(.secondarySystemBackground)).frame(width: 66, height: 82)
                .overlay(Image(systemName: "doc.viewfinder").foregroundStyle(Color.scannyRed))
            VStack(alignment: .leading, spacing: 8) {
                Text(item.state == .failed ? "Upload failed" : "New scan").font(.headline)
                ProgressView(value: item.progress).tint(.scannyRed)
                Text(item.error ?? item.state.rawValue.capitalized).font(.caption).foregroundStyle(item.state == .failed ? .red : .secondary).lineLimit(2)
            }
            if item.state == .failed { Button("Retry", action: retry).buttonStyle(.bordered).controlSize(.small) }
        }.padding(.vertical, 5)
    }
}

struct FloatingCameraButton: View {
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: "camera.fill").font(.system(size: 23, weight: .semibold)).foregroundStyle(.white)
                .frame(width: 62, height: 62).background(Color.scannyRed, in: Circle())
                .shadow(color: .black.opacity(0.22), radius: 9, y: 4)
        }
        .accessibilityLabel("Scan a document")
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
