import Foundation

struct Message: Identifiable, Codable, Equatable {
    let id: String
    let content: String
    let role: MessageRole
    let timestamp: Date
    let modelUsed: String?
    let modelName: String?
    let routingReason: String?

    init(
        id: String = UUID().uuidString,
        content: String,
        role: MessageRole,
        timestamp: Date = Date(),
        modelUsed: String? = nil,
        modelName: String? = nil,
        routingReason: String? = nil
    ) {
        self.id = id
        self.content = content
        self.role = role
        self.timestamp = timestamp
        self.modelUsed = modelUsed
        self.modelName = modelName
        self.routingReason = routingReason
    }
}

enum MessageRole: String, Codable {
    case user
    case assistant
}

struct ChatRequest: Codable {
    let message: String
    let conversationId: String?
    let stream: Bool

    init(message: String, conversationId: String? = nil, stream: Bool = false) {
        self.message = message
        self.conversationId = conversationId
        self.stream = stream
    }

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
        case stream
    }
}

struct ChatResponse: Codable {
    let id: String
    let content: String
    let role: String
    let modelUsed: String?
    let modelName: String?
    let routingReason: String?

    enum CodingKeys: String, CodingKey {
        case id
        case content
        case role
        case modelUsed = "model_used"
        case modelName = "model_name"
        case routingReason = "routing_reason"
    }
}
