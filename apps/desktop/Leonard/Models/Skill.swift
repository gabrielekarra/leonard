import Foundation

struct Skill: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let description: String
    var active: Bool
}
