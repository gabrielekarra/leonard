import Foundation

@Observable
class MemoryViewModel {
    var enabled: Bool = false
    var indexed: Bool = false
    var isIndexing: Bool = false
    var errorMessage: String?

    init() {}

    @MainActor
    func loadStatus() async {
        errorMessage = nil
        do {
            let status = try await CoreAPI.shared.getMemoryStatus()
            enabled = status.enabled
            indexed = status.indexed
            isIndexing = status.indexing
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func toggle(_ enabled: Bool) async {
        isIndexing = true
        errorMessage = nil
        do {
            let status = try await CoreAPI.shared.toggleMemory(enabled: enabled)
            self.enabled = status.enabled
            self.indexed = status.indexed
            self.isIndexing = status.indexing
        } catch {
            errorMessage = error.localizedDescription
            isIndexing = false
        }
    }
}
