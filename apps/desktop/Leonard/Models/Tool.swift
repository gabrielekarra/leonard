import Foundation

struct Tool: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let description: String
    let icon: String
    var enabled: Bool
}

struct ToolUpdateRequest: Codable {
    let enabled: Bool
}
