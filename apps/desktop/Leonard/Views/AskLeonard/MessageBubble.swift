import SwiftUI

struct MessageBubble: View {
    let message: Message

    private var isUser: Bool {
        message.role == .user
    }

    var body: some View {
        HStack(alignment: .top, spacing: AppSpacing.small) {
            if isUser {
                Spacer(minLength: 60)
            }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                // Model indicator for assistant messages
                if !isUser, let modelName = message.modelName {
                    HStack(spacing: 4) {
                        Image(systemName: "cpu")
                            .font(.system(size: 10))
                        Text(modelName)
                            .font(.system(size: 11, weight: .medium))
                    }
                    .foregroundColor(AppColors.accent)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(
                        Capsule()
                            .fill(AppColors.accent.opacity(0.15))
                    )
                }

                Text(message.content)
                    .font(.system(size: AppTypography.bodySize))
                    .foregroundColor(AppColors.textPrimary)
                    .textSelection(.enabled)
                    .padding(.horizontal, AppSpacing.medium)
                    .padding(.vertical, AppSpacing.small)
                    .background(
                        RoundedRectangle(cornerRadius: AppSpacing.cornerRadius)
                            .fill(isUser ? AppColors.userBubble : AppColors.backgroundSecondary)
                    )
            }

            if !isUser {
                Spacer(minLength: 60)
            }
        }
    }
}

#Preview {
    VStack(spacing: 16) {
        MessageBubble(message: Message(content: "Hello, how are you?", role: .user))
        MessageBubble(message: Message(
            content: "I'm doing well, thank you for asking! How can I help you today?",
            role: .assistant,
            modelName: "Qwen 2.5 1.5B"
        ))
        MessageBubble(message: Message(
            content: "Can you help me write some Python code?",
            role: .user
        ))
        MessageBubble(message: Message(
            content: "Of course! I'd be happy to help you write Python code. What would you like to create?",
            role: .assistant,
            modelName: "CodeLlama 7B"
        ))
    }
    .padding()
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
