import Foundation

@Observable
class ToolsViewModel {
    var toolsEnabled: Bool = true
    var errorMessage: String?

    init() {
        Task { await loadStatus() }
    }

    @MainActor
    func loadStatus() async {
        errorMessage = nil
        do {
            let status = try await CoreAPI.shared.getToolsStatus()
            toolsEnabled = status.enabled
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func toggleTools(_ enabled: Bool) async {
        do {
            let result = try await CoreAPI.shared.toggleTools(enabled: enabled)
            toolsEnabled = result
        } catch {
            errorMessage = error.localizedDescription
            toolsEnabled = !enabled
        }
    }
}
