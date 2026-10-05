import Foundation

struct User: Codable, Equatable, Sendable {
    let id: Int
    let email: String
}

struct Category: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    var name: String
    let createdAt: Date
    let isSystem: Bool
    var documentCount: Int
}

enum ProcessingStatus: String, Codable, Sendable {
    case uploaded, processing, complete, needsReview = "needs_review", failed

    var label: String {
        switch self {
        case .uploaded: "Uploading"
        case .processing: "Processing"
        case .complete: "Ready"
        case .needsReview: "Needs Review"
        case .failed: "Failed"
        }
    }

    var isActive: Bool { self == .uploaded || self == .processing }
}

struct CategoryBrief: Codable, Hashable, Sendable {
    let id: Int
    let name: String
    let isSystem: Bool
}

enum ScanMode: String, Codable, CaseIterable, Sendable {
    case color
    case blackAndWhite = "black_and_white"

    var label: String { self == .color ? "Color" : "B&W" }
}

struct ScanCorners: Codable, Hashable, Sendable {
    var topLeft: [Double]
    var topRight: [Double]
    var bottomRight: [Double]
    var bottomLeft: [Double]

}

struct ScannyDocument: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    var title: String
    var categoryId: Int
    var category: CategoryBrief
    let createdAt: Date
    let originalImageUrl: String
    let scannedImageUrl: String
    let processingStatus: ProcessingStatus
    let detectedCorners: ScanCorners?
    let scanMode: ScanMode
}

struct DocumentSearchResult: Codable, Sendable {
    let document: ScannyDocument
    let score: Double
}

struct DocumentSearchResponse: Codable, Sendable {
    let query: String
    let results: [DocumentSearchResult]
}

enum PendingCaptureState: String, Codable, Sendable {
    case captured, uploading, processing, complete, failed
}

struct PendingCapture: Codable, Identifiable, Sendable {
    let id: UUID
    let filename: String
    let capturedAt: Date
    var state: PendingCaptureState
    var progress: Double
    var resultingDocumentID: Int?
    var error: String?
    var ownerUserID: Int?
}
