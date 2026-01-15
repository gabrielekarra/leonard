import Foundation

/// CoreBridge handles direct process communication with the Python core.
/// For the MVP, we use HTTP via CoreAPI. This class is a placeholder for
/// future direct process communication (e.g., stdin/stdout, Unix sockets).
class CoreBridge {
    static let shared = CoreBridge()

    private init() {}

    /// Check if the core process is running
    func isCoreRunning() async -> Bool {
        await CoreAPI.shared.checkHealth()
    }
}
