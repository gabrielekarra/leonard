import Foundation

struct AIModel: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let description: String
    let size: String
    var installed: Bool
}
