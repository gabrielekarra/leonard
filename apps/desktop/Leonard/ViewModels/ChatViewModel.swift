import Foundation

@Observable
class ChatViewModel {
    var messages: [Message] = []
    var inputText: String = ""
    var isLoading: Bool = false
    var isCoreConnected: Bool = false
    var errorMessage: String?
    var useStreaming: Bool = true  // Enable streaming by default

    init() {
        Task {
            await checkCoreConnection()
            // Clear any stale conversation on startup
            try? await CoreAPI.shared.clearConversation()
        }
    }

    @MainActor
    func checkCoreConnection() async {
        isCoreConnected = await CoreAPI.shared.checkHealth()
    }

    @MainActor
    func sendMessage() async {
        let content = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return }
        guard !isLoading else { return }

        let userMessage = Message(content: content, role: .user)
        messages.append(userMessage)
        inputText = ""
        isLoading = true
        errorMessage = nil

        if useStreaming {
            await sendMessageStreaming(content)
        } else {
            await sendMessageNonStreaming(content)
        }

        isLoading = false
    }

    @MainActor
    private func sendMessageStreaming(_ content: String) async {
        // Create a placeholder message that will be updated as chunks arrive
        let placeholderId = UUID().uuidString
        let placeholderMessage = Message(
            id: placeholderId,
            content: "",
            role: .assistant
        )
        messages.append(placeholderMessage)

        var accumulatedContent = ""

        do {
            let stream = await CoreAPI.shared.streamMessage(content)

            for try await chunk in stream {
                accumulatedContent += chunk
                // Update the placeholder message with accumulated content
                if let index = messages.firstIndex(where: { $0.id == placeholderId }) {
                    messages[index] = Message(
                        id: placeholderId,
                        content: accumulatedContent,
                        role: .assistant
                    )
                }
            }
        } catch let error as CoreAPIError {
            errorMessage = error.errorDescription
            if case .coreNotRunning = error {
                isCoreConnected = false
            }
            // Remove placeholder on error
            messages.removeAll { $0.id == placeholderId }
        } catch {
            errorMessage = error.localizedDescription
            // Remove placeholder on error
            messages.removeAll { $0.id == placeholderId }
        }
    }

    @MainActor
    private func sendMessageNonStreaming(_ content: String) async {
        do {
            let response = try await CoreAPI.shared.sendMessage(content)
            messages.append(response)
        } catch let error as CoreAPIError {
            errorMessage = error.errorDescription
            if case .coreNotRunning = error {
                isCoreConnected = false
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func clearMessages() async {
        messages.removeAll()
        errorMessage = nil
        // Also clear server-side conversation
        try? await CoreAPI.shared.clearConversation()
    }
}
