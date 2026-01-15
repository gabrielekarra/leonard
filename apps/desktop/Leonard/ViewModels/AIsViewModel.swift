import Foundation

@Observable
class AIsViewModel {
    // Local registry models
    var models: [AIModel] = []
    var tools: [Tool] = []
    var skills: [Skill] = []

    // HuggingFace search
    var searchText: String = ""
    var searchResults: [HFSearchResult] = []
    var isSearching: Bool = false
    var showSearchResults: Bool = false

    // Featured models (shown by default)
    var featuredModels: [HFSearchResult] = []
    var isLoadingFeatured: Bool = false

    // Download tracking
    var activeDownloads: [String: DownloadProgress] = [:]

    // Tools settings
    var toolsEnabled: Bool = true

    var isLoading: Bool = false
    var errorMessage: String?

    var filteredModels: [AIModel] {
        guard !searchText.isEmpty else { return models }
        return models.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    struct DownloadProgress: Identifiable {
        let id: String
        let repoId: String
        let filename: String
        var status: String
        var progressPercent: Double = 0.0
        var downloadedBytes: Int = 0
        var totalBytes: Int = 0
        var isComplete: Bool = false
        var isCancelled: Bool = false
        var error: String?

        var progressFormatted: String {
            if totalBytes > 0 {
                let downloadedMB = Double(downloadedBytes) / 1_000_000
                let totalMB = Double(totalBytes) / 1_000_000
                return String(format: "%.0f / %.0f MB", downloadedMB, totalMB)
            }
            return "\(Int(progressPercent))%"
        }
    }

    // Featured model queries to show popular models
    static let featuredQueries = ["llama 3.2", "qwen2.5", "mistral", "phi-4", "deepseek"]

    var filteredTools: [Tool] {
        guard !searchText.isEmpty else { return tools }
        return tools.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    var filteredSkills: [Skill] {
        guard !searchText.isEmpty else { return skills }
        return skills.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    init() {
        Task {
            await loadAll()
            await loadFeaturedModels()
        }
    }

    @MainActor
    func loadAll() async {
        isLoading = true
        errorMessage = nil

        async let modelsTask = loadModels()
        async let toolsTask = loadTools()
        async let skillsTask = loadSkills()

        _ = await (modelsTask, toolsTask, skillsTask)
        isLoading = false
    }

    @MainActor
    func loadFeaturedModels() async {
        guard featuredModels.isEmpty else { return }

        isLoadingFeatured = true

        // Load one model from each featured query
        var featured: [HFSearchResult] = []

        for query in Self.featuredQueries {
            do {
                let results = try await CoreAPI.shared.searchHuggingFace(query: query, limit: 1)
                if let first = results.first {
                    // Avoid duplicates
                    if !featured.contains(where: { $0.repoId == first.repoId }) {
                        featured.append(first)
                    }
                }
            } catch {
                // Continue with other queries
            }

            // Stop at 5 models
            if featured.count >= 5 { break }
        }

        featuredModels = featured
        isLoadingFeatured = false
    }

    @MainActor
    private func loadModels() async {
        do {
            models = try await CoreAPI.shared.getModels()
        } catch {
            handleError(error)
        }
    }

    @MainActor
    private func loadTools() async {
        do {
            tools = try await CoreAPI.shared.getTools()
        } catch {
            handleError(error)
        }
    }

    @MainActor
    private func loadSkills() async {
        do {
            skills = try await CoreAPI.shared.getSkills()
        } catch {
            handleError(error)
        }
    }

    @MainActor
    func installModel(_ model: AIModel) async {
        do {
            let success = try await CoreAPI.shared.installModel(model.id)
            if success {
                if let index = models.firstIndex(where: { $0.id == model.id }) {
                    models[index].installed = true
                }
            }
        } catch {
            handleError(error)
        }
    }

    @MainActor
    func removeModel(_ model: AIModel) async {
        do {
            let success = try await CoreAPI.shared.removeModel(model.id)
            if success {
                // Remove the model from the list entirely
                models.removeAll { $0.id == model.id }
            }
        } catch {
            handleError(error)
        }
    }

    // MARK: - HuggingFace Search

    @MainActor
    func searchHuggingFace() async {
        guard !searchText.trimmingCharacters(in: .whitespaces).isEmpty else {
            searchResults = []
            showSearchResults = false
            return
        }

        isSearching = true
        showSearchResults = true

        do {
            searchResults = try await CoreAPI.shared.searchHuggingFace(query: searchText)
        } catch {
            handleError(error)
            searchResults = []
        }

        isSearching = false
    }

    @MainActor
    func clearSearch() {
        searchText = ""
        searchResults = []
        showSearchResults = false
    }

    // MARK: - Download

    @MainActor
    func downloadModel(result: HFSearchResult, file: GGUFFile) async {
        do {
            let downloadId = try await CoreAPI.shared.downloadModel(
                repoId: result.repoId,
                filename: file.filename
            )

            // Track the download
            activeDownloads[downloadId] = DownloadProgress(
                id: downloadId,
                repoId: result.repoId,
                filename: file.filename,
                status: "downloading"
            )

            // Start polling for status
            Task {
                await pollDownloadStatus(downloadId: downloadId)
            }
        } catch {
            handleError(error)
        }
    }

    @MainActor
    private func pollDownloadStatus(downloadId: String) async {
        while true {
            do {
                try await Task.sleep(nanoseconds: 500_000_000) // 0.5 second for smoother updates

                let status = try await CoreAPI.shared.getDownloadStatus(downloadId: downloadId)

                // Update progress
                activeDownloads[downloadId]?.progressPercent = status.progressPercent
                activeDownloads[downloadId]?.downloadedBytes = status.downloadedBytes
                activeDownloads[downloadId]?.totalBytes = status.totalBytes
                activeDownloads[downloadId]?.status = status.status

                if status.isComplete {
                    activeDownloads[downloadId]?.isComplete = true
                    // Refresh models list
                    await loadModels()
                    // Remove from active downloads after a delay
                    Task {
                        try? await Task.sleep(nanoseconds: 3_000_000_000)
                        await MainActor.run {
                            activeDownloads.removeValue(forKey: downloadId)
                        }
                    }
                    break
                } else if status.isFailed {
                    activeDownloads[downloadId]?.error = status.error
                    activeDownloads[downloadId]?.isCancelled = status.isCancelled
                    // Remove cancelled downloads after a delay
                    Task {
                        try? await Task.sleep(nanoseconds: 2_000_000_000)
                        await MainActor.run {
                            activeDownloads.removeValue(forKey: downloadId)
                        }
                    }
                    break
                }
            } catch {
                activeDownloads[downloadId]?.status = "error"
                activeDownloads[downloadId]?.error = error.localizedDescription
                break
            }
        }
    }

    @MainActor
    func cancelDownload(downloadId: String) async {
        do {
            _ = try await CoreAPI.shared.cancelDownload(downloadId: downloadId)
            activeDownloads[downloadId]?.status = "cancelling"
        } catch {
            handleError(error)
        }
    }

    @MainActor
    func toggleTool(_ tool: Tool) async {
        let newEnabled = !tool.enabled
        do {
            let success = try await CoreAPI.shared.toggleTool(tool.id, enabled: newEnabled)
            if success {
                if let index = tools.firstIndex(where: { $0.id == tool.id }) {
                    tools[index].enabled = newEnabled
                }
            }
        } catch {
            handleError(error)
        }
    }

    @MainActor
    func setToolsEnabled(_ enabled: Bool) async {
        do {
            let result = try await CoreAPI.shared.toggleTools(enabled: enabled)
            toolsEnabled = result
        } catch {
            handleError(error)
            // Revert on error
            toolsEnabled = !enabled
        }
    }

    private func handleError(_ error: Error) {
        if let apiError = error as? CoreAPIError {
            errorMessage = apiError.errorDescription
        } else {
            errorMessage = error.localizedDescription
        }
    }
}
