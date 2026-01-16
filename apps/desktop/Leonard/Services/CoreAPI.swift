import Foundation

enum CoreAPIError: Error, LocalizedError {
    case networkError(Error)
    case invalidResponse
    case serverError(Int)
    case coreNotRunning

    var errorDescription: String? {
        switch self {
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .invalidResponse:
            return "Invalid response from server"
        case .serverError(let code):
            return "Server error: \(code)"
        case .coreNotRunning:
            return "Leonard Core is not running"
        }
    }
}

struct SuccessResponse: Codable {
    let success: Bool
    let message: String?
}

struct HealthResponse: Codable {
    let status: String
    let version: String
}

actor CoreAPI {
    static let shared = CoreAPI()

    private let baseURL: String
    private let session: URLSession

    private init() {
        self.baseURL = "\(AppConfig.coreBaseURL)\(AppConfig.apiPrefix)"
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300 // Increased for model inference
        self.session = URLSession(configuration: config)
    }

    // MARK: - Health Check

    func checkHealth() async -> Bool {
        do {
            let _: HealthResponse = try await request(endpoint: "/health", method: "GET")
            return true
        } catch {
            return false
        }
    }

    // MARK: - Chat

    func sendMessage(_ content: String, conversationId: String? = nil) async throws -> Message {
        let request = ChatRequest(message: content, conversationId: conversationId)
        let response: ChatResponse = try await self.request(
            endpoint: "/chat",
            method: "POST",
            body: request
        )
        return Message(
            id: response.id,
            content: response.content,
            role: .assistant,
            modelUsed: response.modelUsed,
            modelName: response.modelName,
            routingReason: response.routingReason
        )
    }

    /// Stream a message response as chunks arrive
    func streamMessage(_ content: String, conversationId: String? = nil) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    guard let url = URL(string: baseURL + "/chat") else {
                        continuation.finish(throwing: CoreAPIError.invalidResponse)
                        return
                    }

                    var urlRequest = URLRequest(url: url)
                    urlRequest.httpMethod = "POST"
                    urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    urlRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                    let chatRequest = ChatRequest(message: content, conversationId: conversationId, stream: true)
                    urlRequest.httpBody = try JSONEncoder().encode(chatRequest)

                    let (bytes, response) = try await session.bytes(for: urlRequest)

                    guard let httpResponse = response as? HTTPURLResponse else {
                        continuation.finish(throwing: CoreAPIError.invalidResponse)
                        return
                    }

                    guard (200...299).contains(httpResponse.statusCode) else {
                        continuation.finish(throwing: CoreAPIError.serverError(httpResponse.statusCode))
                        return
                    }

                    // Parse SSE format: "data: {chunk}\n\n"
                    for try await line in bytes.lines {
                        if line.hasPrefix("data: ") {
                            let data = String(line.dropFirst(6))
                            if data == "[DONE]" {
                                break
                            }
                            continuation.yield(data)
                        }
                    }

                    continuation.finish()
                } catch {
                    if (error as NSError).code == NSURLErrorCannotConnectToHost ||
                       (error as NSError).code == NSURLErrorNetworkConnectionLost {
                        continuation.finish(throwing: CoreAPIError.coreNotRunning)
                    } else {
                        continuation.finish(throwing: CoreAPIError.networkError(error))
                    }
                }
            }
        }
    }

    func clearConversation() async throws {
        let _: [String: String] = try await request(
            endpoint: "/chat/clear",
            method: "POST"
        )
    }

    // MARK: - Models

    func getModels() async throws -> [AIModel] {
        let response: ModelsResponse = try await request(endpoint: "/models", method: "GET")
        return response.models.map { modelData in
            AIModel(
                id: modelData.id,
                name: modelData.name,
                description: modelData.capabilities.map { "\($0.key): \(Int($0.value * 100))%" }.joined(separator: ", "),
                size: modelData.isDownloaded ? "Downloaded" : "Not downloaded",
                installed: modelData.isDownloaded
            )
        }
    }

    func installModel(_ id: String) async throws -> Bool {
        let response: SuccessResponse = try await request(
            endpoint: "/models/\(id)/install",
            method: "POST"
        )
        return response.success
    }

    func removeModel(_ id: String) async throws -> Bool {
        let _: DeleteResponse = try await request(
            endpoint: "/models/\(id)",
            method: "DELETE"
        )
        return true
    }

    // MARK: - HuggingFace Search & Download

    func searchHuggingFace(query: String, limit: Int = 10) async throws -> [HFSearchResult] {
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let response: HFSearchResponse = try await request(
            endpoint: "/models/search?q=\(encodedQuery)&limit=\(limit)",
            method: "GET"
        )
        return response.models
    }

    func downloadModel(repoId: String, filename: String) async throws -> String {
        let body = DownloadRequest(repoId: repoId, filename: filename)
        let response: DownloadStartResponse = try await request(
            endpoint: "/models/download",
            method: "POST",
            body: body
        )
        return response.downloadId
    }

    func getDownloadStatus(downloadId: String) async throws -> DownloadStatus {
        let encodedId = downloadId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? downloadId
        return try await request(
            endpoint: "/models/download/\(encodedId)/status",
            method: "GET"
        )
    }

    func cancelDownload(downloadId: String) async throws -> Bool {
        let encodedId = downloadId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? downloadId
        let response: CancelResponse = try await request(
            endpoint: "/models/download/\(encodedId)/cancel",
            method: "POST"
        )
        return response.status == "cancelling"
    }

    // MARK: - Tools

    func getTools() async throws -> [Tool] {
        try await request(endpoint: "/tools", method: "GET")
    }

    func getToolsStatus() async throws -> ToolsStatus {
        try await request(endpoint: "/chat/tools", method: "GET")
    }

    func toggleTool(_ id: String, enabled: Bool) async throws -> Bool {
        let body = ToolUpdateRequest(enabled: enabled)
        let response: SuccessResponse = try await request(
            endpoint: "/tools/\(id)",
            method: "PUT",
            body: body
        )
        return response.success
    }

    // MARK: - Skills

    func getSkills() async throws -> [Skill] {
        try await request(endpoint: "/skills", method: "GET")
    }

    // MARK: - Tools

    func toggleTools(enabled: Bool) async throws -> Bool {
        let body = ToolsToggleRequest(enabled: enabled)
        let response: ToolsToggleResponse = try await request(
            endpoint: "/chat/tools/toggle",
            method: "POST",
            body: body
        )
        return response.enabled
    }

    // MARK: - Memory (Simplified)

    func getMemoryStatus() async throws -> MemoryStatus {
        try await request(endpoint: "/memory/status", method: "GET")
    }

    func toggleMemory(enabled: Bool) async throws -> MemoryStatus {
        let body = ToggleMemoryRequest(enabled: enabled)
        return try await request(
            endpoint: "/memory/toggle",
            method: "POST",
            body: body
        )
    }

    // MARK: - Private

    private func request<T: Decodable>(
        endpoint: String,
        method: String,
        body: (any Encodable)? = nil
    ) async throws -> T {
        guard let url = URL(string: baseURL + endpoint) else {
            throw CoreAPIError.invalidResponse
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let body = body {
            urlRequest.httpBody = try JSONEncoder().encode(body)
        }

        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            if (error as NSError).code == NSURLErrorCannotConnectToHost ||
               (error as NSError).code == NSURLErrorNetworkConnectionLost {
                throw CoreAPIError.coreNotRunning
            }
            throw CoreAPIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw CoreAPIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw CoreAPIError.serverError(httpResponse.statusCode)
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw CoreAPIError.invalidResponse
        }
    }
}

// MARK: - Response Models

private struct ModelsResponse: Codable {
    let models: [ModelData]
}

private struct ModelData: Codable {
    let id: String
    let name: String
    let repoId: String
    let filename: String
    let role: String
    let capabilities: [String: Double]
    let contextLength: Int
    let isDownloaded: Bool
    let localPath: String?

    enum CodingKeys: String, CodingKey {
        case id, name, role, capabilities, filename
        case repoId = "repo_id"
        case contextLength = "context_length"
        case isDownloaded = "is_downloaded"
        case localPath = "local_path"
    }
}

private struct DeleteResponse: Codable {
    let status: String
}

// MARK: - HuggingFace Models

struct HFSearchResponse: Codable {
    let models: [HFSearchResult]
}

struct HFSearchResult: Codable, Identifiable {
    let repoId: String
    let name: String
    let author: String
    let downloads: Int
    let likes: Int
    let ggufFiles: [GGUFFile]
    let tags: [String]

    var id: String { repoId }

    enum CodingKeys: String, CodingKey {
        case repoId = "repo_id"
        case name, author, downloads, likes, tags
        case ggufFiles = "gguf_files"
    }

    /// Auto-generated description based on model name
    var modelDescription: String {
        let lower = name.lowercased()

        // Coding models
        if lower.contains("coder") || lower.contains("code") {
            return "Optimized for code generation, debugging, and programming tasks"
        }
        // Math models
        if lower.contains("math") {
            return "Specialized in mathematical reasoning and calculations"
        }
        // Instruct/Chat models
        if lower.contains("instruct") {
            return "Fine-tuned for following instructions and helpful responses"
        }
        // Specific model families
        if lower.contains("llama") {
            return "Meta's open-source LLM, great for general tasks and reasoning"
        }
        if lower.contains("mistral") || lower.contains("mixtral") {
            return "Fast and efficient model with strong reasoning capabilities"
        }
        if lower.contains("qwen") {
            return "Alibaba's multilingual model, excellent for diverse tasks"
        }
        if lower.contains("phi") {
            return "Microsoft's compact model, optimized for efficiency"
        }
        if lower.contains("deepseek") {
            return "Strong reasoning and coding capabilities"
        }
        if lower.contains("gemma") {
            return "Google's lightweight model for general use"
        }

        return "General-purpose language model for various tasks"
    }

    /// Estimated RAM requirement based on model name
    var ramRequired: String {
        let lower = name.lowercased()
        let patterns: [(String, String)] = [
            ("70b", "64+ GB RAM"), ("72b", "64+ GB RAM"),
            ("34b", "32+ GB RAM"), ("33b", "32+ GB RAM"),
            ("13b", "16+ GB RAM"), ("14b", "16+ GB RAM"),
            ("7b", "8+ GB RAM"), ("8b", "10+ GB RAM"),
            ("3b", "6+ GB RAM"), ("4b", "6+ GB RAM"),
            ("1.5b", "4+ GB RAM"), ("1b", "4+ GB RAM"),
        ]
        for (pattern, ram) in patterns {
            if lower.contains(pattern) {
                return ram
            }
        }
        return "4+ GB RAM"
    }

    /// Incompatible architecture patterns
    private static let incompatiblePatterns = [
        "falcon-h1", "mamba", "rwkv", "jamba", "griffin",
        "recurrentgemma", "-ssm", "image", "vision",
        "vl-", "-vl", "llava", "minicpm-v", "qwen-vl",
        "cogvlm", "internvl"
    ]

    /// Check if this model is compatible with llama.cpp
    var isCompatible: Bool {
        let lower = repoId.lowercased()
        for pattern in Self.incompatiblePatterns {
            if lower.contains(pattern) {
                return false
            }
        }

        // Check tags for incompatible types
        let incompatibleTags = ["mamba", "rwkv", "vision", "image-to-text", "image-text-to-text"]
        for tag in tags {
            if incompatibleTags.contains(tag.lowercased()) {
                return false
            }
        }

        return true
    }

    /// Reason why the model is incompatible (if any)
    var incompatibilityReason: String? {
        let lower = repoId.lowercased()

        if lower.contains("falcon-h1") {
            return "Falcon Hybrid architecture not supported"
        }
        if lower.contains("mamba") || tags.contains(where: { $0.lowercased() == "mamba" }) {
            return "Mamba (State Space) architecture not supported"
        }
        if lower.contains("rwkv") {
            return "RWKV architecture not supported"
        }
        if lower.contains("jamba") {
            return "Jamba hybrid architecture not supported"
        }
        if lower.contains("image") || lower.contains("vision") || lower.contains("llava") ||
           lower.contains("-vl") || lower.contains("vl-") {
            return "Vision/multimodal models not supported"
        }

        return nil
    }
}

struct GGUFFile: Codable, Identifiable {
    let filename: String
    let size: Int
    let quantization: String

    var id: String { filename }

    var sizeFormatted: String {
        if size == 0 { return estimateSizeFromFilename() }
        let gb = Double(size) / 1_000_000_000
        if gb >= 1 {
            return String(format: "%.1f GB", gb)
        }
        let mb = Double(size) / 1_000_000
        return String(format: "%.0f MB", mb)
    }

    /// Estimate size from filename patterns like "7B", "3B", "70B"
    private func estimateSizeFromFilename() -> String {
        let patterns: [(String, String)] = [
            ("70b", "~40 GB"), ("72b", "~42 GB"),
            ("34b", "~20 GB"), ("33b", "~19 GB"),
            ("13b", "~8 GB"), ("14b", "~8 GB"),
            ("7b", "~4 GB"), ("8b", "~5 GB"),
            ("3b", "~2 GB"), ("4b", "~2.5 GB"),
            ("1.5b", "~1 GB"), ("1b", "~0.7 GB"),
        ]
        let lower = filename.lowercased()
        for (pattern, size) in patterns {
            if lower.contains(pattern) {
                return size
            }
        }
        return "Unknown"
    }

    /// RAM required to run this model (rule: ~1.2x model size + 2GB overhead)
    var ramRequired: String {
        // Try to estimate from filename
        let lower = filename.lowercased()
        let patterns: [(String, String)] = [
            ("70b", "64+ GB"), ("72b", "64+ GB"),
            ("34b", "32+ GB"), ("33b", "32+ GB"),
            ("13b", "16+ GB"), ("14b", "16+ GB"),
            ("7b", "8+ GB"), ("8b", "10+ GB"),
            ("3b", "6+ GB"), ("4b", "6+ GB"),
            ("1.5b", "4+ GB"), ("1b", "4+ GB"),
        ]
        for (pattern, ram) in patterns {
            if lower.contains(pattern) {
                return ram
            }
        }
        return "4+ GB"
    }
}

struct DownloadRequest: Codable {
    let repoId: String
    let filename: String

    enum CodingKeys: String, CodingKey {
        case repoId = "repo_id"
        case filename
    }
}

struct DownloadStartResponse: Codable {
    let status: String
    let downloadId: String

    enum CodingKeys: String, CodingKey {
        case status
        case downloadId = "download_id"
    }
}

struct DownloadStatus: Codable {
    let status: String
    let downloadedBytes: Int
    let totalBytes: Int
    let progressPercent: Double
    let path: String?
    let error: String?
    let modelId: String?
    let capabilities: [String: Double]?

    enum CodingKeys: String, CodingKey {
        case status, path, error
        case downloadedBytes = "downloaded_bytes"
        case totalBytes = "total_bytes"
        case progressPercent = "progress_percent"
        case modelId = "model_id"
        case capabilities
    }

    var isComplete: Bool { status == "completed" }
    var isFailed: Bool { status == "error" || status == "cancelled" }
    var isCancelled: Bool { status == "cancelled" }
    var isInProgress: Bool { status == "downloading" || status == "detecting_capabilities" || status == "registering" || status == "starting" }

    var progressFormatted: String {
        if totalBytes > 0 {
            let downloadedMB = Double(downloadedBytes) / 1_000_000
            let totalMB = Double(totalBytes) / 1_000_000
            return String(format: "%.0f / %.0f MB", downloadedMB, totalMB)
        }
        return "\(Int(progressPercent))%"
    }
}

struct CancelResponse: Codable {
    let status: String
    let downloadId: String?

    enum CodingKeys: String, CodingKey {
        case status
        case downloadId = "download_id"
    }
}

// MARK: - Tools Models

struct ToolsToggleRequest: Codable {
    let enabled: Bool
}

struct ToolsToggleResponse: Codable {
    let enabled: Bool
    let message: String
}

struct ToolsStatus: Codable {
    let tools: [Tool]
    let enabled: Bool
}

// MARK: - Memory Models (Simplified)

struct ToggleMemoryRequest: Codable {
    let enabled: Bool
}

struct MemoryStatus: Codable {
    let enabled: Bool
    let indexed: Bool
    let indexing: Bool
}
