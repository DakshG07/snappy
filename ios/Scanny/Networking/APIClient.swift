import Foundation

enum APIError: LocalizedError, Equatable {
    case invalidBaseURL
    case invalidResponse
    case unauthorized
    case server(status: Int, message: String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL: "The Scanny server address is invalid."
        case .invalidResponse: "Scanny returned an invalid response."
        case .unauthorized: "Please sign in again."
        case .server(_, let message): message
        case .transport(let message): message
        }
    }
}

final class APIClient: @unchecked Sendable {
    private let session: URLSession
    private let encoder: JSONEncoder
    private(set) var baseURL: URL

    init(baseURL: URL = APIClient.configuredBaseURL()) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.default
        configuration.httpCookieStorage = .shared
        configuration.httpShouldSetCookies = true
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 120
        session = URLSession(configuration: configuration)
        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractional.date(from: value) { return date }
            let standard = ISO8601DateFormatter()
            if let date = standard.date(from: value) { return date }
            for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
                let parser = DateFormatter()
                parser.locale = Locale(identifier: "en_US_POSIX")
                parser.dateFormat = format
                if let date = parser.date(from: value) { return date }
            }
            throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: "Invalid date: \(value)")
        }
        return decoder
    }

    static func configuredBaseURL() -> URL {
        if let override = UserDefaults.standard.string(forKey: "ScannyBaseURL"), let url = URL(string: override) {
            return url
        }
        let configured = Bundle.main.object(forInfoDictionaryKey: "SCANNY_API_BASE_URL") as? String
        return URL(string: configured ?? "http://127.0.0.1:8000")!
    }

    func updateBaseURL(_ value: String) throws {
        guard let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = url.scheme, ["http", "https"].contains(scheme), url.host != nil
        else { throw APIError.invalidBaseURL }
        baseURL = url
        UserDefaults.standard.set(url.absoluteString, forKey: "ScannyBaseURL")
    }

    func url(for path: String) -> URL? {
        if let absolute = URL(string: path), absolute.scheme != nil { return absolute }
        return URL(string: path, relativeTo: baseURL)?.absoluteURL
    }

    func get<T: Decodable & Sendable>(_ path: String) async throws -> T {
        try await request(path: path, method: "GET", body: Optional<String>.none)
    }

    func send<T: Decodable & Sendable, Body: Encodable>(_ path: String, method: String, body: Body) async throws -> T {
        try await request(path: path, method: method, body: body)
    }

    func sendWithoutResponse<Body: Encodable>(_ path: String, method: String, body: Body? = nil) async throws {
        let request = try makeRequest(path: path, method: method, body: body)
        let (_, response) = try await perform(request)
        try validate(response: response, data: Data())
    }

    func data(from path: String) async throws -> Data {
        guard let url = url(for: path) else { throw APIError.invalidBaseURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        let (data, response) = try await perform(request)
        try validate(response: response, data: data)
        return data
    }

    func uploadJPEG(_ data: Data) async throws -> ScannyDocument {
        guard let url = url(for: "/api/documents") else { throw APIError.invalidBaseURL }
        let boundary = "Scanny-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let body = await Task.detached(priority: .utility) {
            var body = Data()
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"image\"; filename=\"scan.jpg\"\r\n")
            body.append("Content-Type: image/jpeg\r\n\r\n")
            body.append(data)
            body.append("\r\n--\(boundary)--\r\n")
            return body
        }.value
        request.httpBody = body
        let (responseData, response) = try await perform(request)
        try validate(response: response, data: responseData)
        return try await decode(ScannyDocument.self, from: responseData)
    }

    private func request<T: Decodable & Sendable, Body: Encodable>(path: String, method: String, body: Body?) async throws -> T {
        let request = try makeRequest(path: path, method: method, body: body)
        let (data, response) = try await perform(request)
        try validate(response: response, data: data)
        return try await decode(T.self, from: data)
    }

    private func decode<T: Decodable & Sendable>(_ type: T.Type, from data: Data) async throws -> T {
        do {
            return try await Task.detached(priority: .userInitiated) {
                try APIClient.makeDecoder().decode(T.self, from: data)
            }.value
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw APIError.transport("Scanny returned data the app could not read: \(error.localizedDescription)")
        }
    }

    private func makeRequest<Body: Encodable>(path: String, method: String, body: Body?) throws -> URLRequest {
        guard let url = url(for: path) else { throw APIError.invalidBaseURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if let body {
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do { return try await session.data(for: request) }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError.transport(error.localizedDescription) }
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            if http.statusCode == 401 { throw APIError.unauthorized }
            let detail = (try? JSONDecoder().decode(ErrorEnvelope.self, from: data).detail)
            throw APIError.server(status: http.statusCode, message: detail ?? "Scanny server error (\(http.statusCode)).")
        }
    }
}

private struct ErrorEnvelope: Decodable { let detail: String }
private extension Data {
    mutating func append(_ string: String) { append(Data(string.utf8)) }
}
