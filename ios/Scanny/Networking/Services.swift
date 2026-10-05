import Foundation

struct Credentials: Encodable { let email: String; let password: String }
struct CategoryPayload: Encodable { let name: String }
struct DocumentUpdatePayload: Encodable { let title: String?; let categoryId: Int? }
struct DocumentAdjustmentPayload: Encodable { let corners: ScanCorners; let scanMode: ScanMode }

struct AuthService: Sendable {
    let api: APIClient
    func me() async throws -> User { try await api.get("/api/auth/me") }
    func login(email: String, password: String) async throws -> User {
        try await api.send("/api/auth/login", method: "POST", body: Credentials(email: email, password: password))
    }
    func register(email: String, password: String) async throws -> User {
        try await api.send("/api/auth/register", method: "POST", body: Credentials(email: email, password: password))
    }
    func logout() async throws { try await api.sendWithoutResponse("/api/auth/logout", method: "POST", body: Optional<String>.none) }
}

struct DocumentService: Sendable {
    let api: APIClient
    func list(categoryID: Int? = nil) async throws -> [ScannyDocument] {
        let suffix = categoryID.map { "?category_id=\($0)" } ?? ""
        return try await api.get("/api/documents\(suffix)")
    }
    func get(_ id: Int) async throws -> ScannyDocument { try await api.get("/api/documents/\(id)") }
    func search(_ query: String) async throws -> [DocumentSearchResult] {
        var components = URLComponents()
        components.path = "/api/search"
        components.queryItems = [URLQueryItem(name: "q", value: query)]
        guard let path = components.string else { throw APIError.invalidBaseURL }
        let response: DocumentSearchResponse = try await api.get(path)
        return response.results
    }
    func upload(_ jpeg: Data) async throws -> ScannyDocument { try await api.uploadJPEG(jpeg) }
    func update(_ id: Int, title: String? = nil, categoryID: Int? = nil) async throws -> ScannyDocument {
        try await api.send("/api/documents/\(id)", method: "PATCH", body: DocumentUpdatePayload(title: title, categoryId: categoryID))
    }
    func adjust(_ id: Int, corners: ScanCorners, mode: ScanMode) async throws -> ScannyDocument {
        try await api.send("/api/documents/\(id)/adjust", method: "POST", body: DocumentAdjustmentPayload(corners: corners, scanMode: mode))
    }
    func delete(_ id: Int) async throws { try await api.sendWithoutResponse("/api/documents/\(id)", method: "DELETE", body: Optional<String>.none) }
}

struct CategoryService: Sendable {
    let api: APIClient
    func list() async throws -> [Category] { try await api.get("/api/categories") }
    func create(name: String) async throws -> Category {
        try await api.send("/api/categories", method: "POST", body: CategoryPayload(name: name))
    }
    func rename(_ id: Int, name: String) async throws -> Category {
        try await api.send("/api/categories/\(id)", method: "PATCH", body: CategoryPayload(name: name))
    }
    func delete(_ id: Int) async throws { try await api.sendWithoutResponse("/api/categories/\(id)", method: "DELETE", body: Optional<String>.none) }
}
