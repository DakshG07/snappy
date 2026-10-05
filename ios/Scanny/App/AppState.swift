import Foundation
import Observation
import SwiftUI
import UIKit

enum SessionState: Equatable {
    case loading
    case signedOut
    case signedIn(User)
}

@MainActor @Observable
final class AppState {
    let api: APIClient
    let auth: AuthService
    let documentService: DocumentService
    let categoryService: CategoryService
    let captureQueue: CaptureQueue

    var session: SessionState = .loading
    var documents: [ScannyDocument] = []
    var categories: [Category] = []
    var errorMessage: String?
    var isRefreshing = false
    var cameraPresented = false

    init(api: APIClient = APIClient()) {
        self.api = api
        auth = AuthService(api: api)
        documentService = DocumentService(api: api)
        categoryService = CategoryService(api: api)
        captureQueue = CaptureQueue(service: DocumentService(api: api))
        captureQueue.onDocumentChanged = { [weak self] in
            await self?.refresh(silently: true)
        }
    }

    func restoreSession() async {
        do {
            let user = try await auth.me()
            session = .signedIn(user)
            captureQueue.activate(userID: user.id)
            await refresh(silently: true)
        } catch APIError.unauthorized {
            session = .signedOut
        } catch {
            session = .signedOut
            errorMessage = error.localizedDescription
        }
    }

    func login(email: String, password: String) async throws {
        let user = try await auth.login(email: email, password: password)
        session = .signedIn(user)
        captureQueue.activate(userID: user.id)
        await refresh(silently: true)
    }

    func register(email: String, password: String) async throws {
        let user = try await auth.register(email: email, password: password)
        session = .signedIn(user)
        captureQueue.activate(userID: user.id)
        await refresh(silently: true)
    }

    func logout() async {
        try? await auth.logout()
        captureQueue.pause()
        captureQueue.deactivate()
        documents = []
        categories = []
        session = .signedOut
    }

    func refresh(silently: Bool = false) async {
        if !silently { isRefreshing = true }
        defer { isRefreshing = false }
        do {
            async let fetchedDocuments = documentService.list()
            async let fetchedCategories = categoryService.list()
            let (documents, categories) = try await (fetchedDocuments, fetchedCategories)
            withAnimation(.easeInOut(duration: 0.2)) {
                self.documents = documents
                self.categories = categories
            }
        } catch APIError.unauthorized {
            session = .signedOut
        } catch {
            if !silently { errorMessage = error.localizedDescription }
        }
    }

    func pollingLoop() async {
        while !Task.isCancelled {
            let serverActive = documents.contains { $0.processingStatus.isActive }
            let localActive = captureQueue.items.contains { [.captured, .uploading, .processing].contains($0.state) }
            if serverActive || localActive { await refresh(silently: true) }
            try? await Task.sleep(for: .seconds(serverActive || localActive ? 1.5 : 12))
        }
    }

    func replace(_ document: ScannyDocument) {
        if let index = documents.firstIndex(where: { $0.id == document.id }) { documents[index] = document }
        else { documents.insert(document, at: 0) }
    }

    func monitorDocument(_ id: Int) async {
        while !Task.isCancelled {
            do {
                let document = try await documentService.get(id)
                replace(document)
                if !document.processingStatus.isActive {
                    await refresh(silently: true)
                    return
                }
                try await Task.sleep(for: .seconds(1.25))
            } catch is CancellationError {
                return
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }
    }
}

@MainActor @Observable
final class CaptureQueue {
    let service: DocumentService
    private var records: [PendingCapture] = []
    private var currentUserID: Int?
    var items: [PendingCapture] { records.filter { $0.ownerUserID == currentUserID } }
    var onDocumentChanged: (@MainActor () async -> Void)?
    @ObservationIgnored private var tasks: [UUID: Task<Void, Never>] = [:]
    @ObservationIgnored private let directory: URL
    @ObservationIgnored private let metadataURL: URL

    init(service: DocumentService) {
        self.service = service
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        directory = support.appendingPathComponent("ScannyUploads", isDirectory: true)
        metadataURL = directory.appendingPathComponent("queue.json")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = try? Data(contentsOf: metadataURL), let saved = try? JSONDecoder().decode([PendingCapture].self, from: data) {
            records = saved.map { item in
                var restored = item
                if restored.state == .uploading { restored.state = .captured }
                return restored
            }
        }
    }

    var activeCount: Int { items.filter { $0.state == .captured || $0.state == .uploading || $0.state == .processing }.count }
    var failedCount: Int { items.filter { $0.state == .failed }.count }

    func activate(userID: Int) {
        currentUserID = userID
        resumePending()
    }

    func deactivate() { currentUserID = nil }

    func enqueue(jpeg: Data) {
        guard let currentUserID else { return }
        let id = UUID()
        let filename = "\(id.uuidString).jpg"
        do {
            try jpeg.write(to: directory.appendingPathComponent(filename), options: .atomic)
            records.insert(PendingCapture(id: id, filename: filename, capturedAt: .now, state: .captured, progress: 0.05, ownerUserID: currentUserID), at: 0)
            persist()
            start(id)
        } catch {
            records.insert(PendingCapture(id: id, filename: filename, capturedAt: .now, state: .failed, progress: 0, error: "Could not save this capture.", ownerUserID: currentUserID), at: 0)
        }
    }

    func resumePending() {
        for item in items where item.state == .captured || item.state == .processing { start(item.id) }
    }

    func retry(_ id: UUID) {
        update(id) { $0.state = $0.resultingDocumentID == nil ? .captured : .processing; $0.error = nil }
        start(id)
    }

    func pause() {
        tasks.values.forEach { $0.cancel() }
        tasks.removeAll()
    }

    private func start(_ id: UUID) {
        guard tasks[id] == nil else { return }
        tasks[id] = Task { [weak self] in
            await self?.process(id)
            self?.tasks[id] = nil
        }
    }

    private func process(_ id: UUID) async {
        guard let initial = records.first(where: { $0.id == id && $0.ownerUserID == currentUserID }) else { return }
        do {
            var documentID = initial.resultingDocumentID
            if documentID == nil {
                let fileURL = directory.appendingPathComponent(initial.filename)
                let data = try await Task.detached(priority: .utility) {
                    try Data(contentsOf: fileURL)
                }.value
                update(id) { $0.state = .uploading; $0.progress = 0.3 }
                let document = try await service.upload(data)
                documentID = document.id
                update(id) { $0.state = .processing; $0.progress = 0.65; $0.resultingDocumentID = document.id }
                await onDocumentChanged?()
            }
            guard let documentID else { return }
            while !Task.isCancelled {
                let document = try await service.get(documentID)
                await onDocumentChanged?()
                if document.processingStatus.isActive {
                    update(id) { $0.state = .processing; $0.progress = min(0.92, $0.progress + 0.04) }
                    try await Task.sleep(for: .seconds(1.25))
                    continue
                }
                if document.processingStatus == .failed {
                    throw APIError.server(status: 500, message: "The server could not process this scan.")
                }
                update(id) { $0.state = .complete; $0.progress = 1; $0.error = nil }
                try? FileManager.default.removeItem(at: directory.appendingPathComponent(initial.filename))
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                return
            }
        } catch is CancellationError {
            return
        } catch {
            update(id) { $0.state = .failed; $0.error = error.localizedDescription }
        }
    }

    private func update(_ id: UUID, change: (inout PendingCapture) -> Void) {
        guard let index = records.firstIndex(where: { $0.id == id }) else { return }
        change(&records[index])
        persist()
    }

    private func persist() {
        let retained = Array(records.prefix(60))
        if let data = try? JSONEncoder().encode(retained) { try? data.write(to: metadataURL, options: .atomic) }
    }
}
