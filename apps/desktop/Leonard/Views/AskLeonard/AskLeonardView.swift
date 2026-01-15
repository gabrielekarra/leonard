import SwiftUI

struct AskLeonardView: View {
    @Bindable var viewModel: ChatViewModel

    var body: some View {
        VStack(spacing: 0) {
            // Header with New Chat button
            if !viewModel.messages.isEmpty {
                HStack {
                    Spacer()
                    Button(action: {
                        Task { await viewModel.clearMessages() }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "plus.bubble")
                            Text("New Chat")
                        }
                        .font(.system(size: AppTypography.captionSize))
                        .foregroundColor(AppColors.accent)
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, AppSpacing.medium)
                    .padding(.vertical, AppSpacing.small)
                }
                .background(AppColors.backgroundSecondary)
            }

            if !viewModel.isCoreConnected {
                CoreNotRunningBanner()
            }

            if viewModel.messages.isEmpty {
                EmptyStateView()
            } else {
                MessageList(messages: viewModel.messages, isLoading: viewModel.isLoading)
            }

            if let error = viewModel.errorMessage {
                ErrorBanner(message: error)
            }

            ChatInput(
                text: $viewModel.inputText,
                isLoading: viewModel.isLoading,
                onSend: {
                    Task {
                        await viewModel.sendMessage()
                    }
                }
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppColors.background)
    }
}

struct CoreNotRunningBanner: View {
    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)
            Text("Leonard Core is not running. Start the core server to enable chat.")
                .font(.system(size: AppTypography.captionSize))
                .foregroundColor(AppColors.textSecondary)
            Spacer()
        }
        .padding(AppSpacing.small)
        .background(AppColors.backgroundSecondary)
    }
}

struct EmptyStateView: View {
    var body: some View {
        VStack(spacing: AppSpacing.medium) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 48))
                .foregroundColor(AppColors.textSecondary.opacity(0.5))
            Text("Start a conversation with Leonard")
                .font(.system(size: AppTypography.bodySize))
                .foregroundColor(AppColors.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack {
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
            Text(message)
                .font(.system(size: AppTypography.captionSize))
                .foregroundColor(AppColors.textSecondary)
            Spacer()
        }
        .padding(AppSpacing.small)
        .background(Color.red.opacity(0.1))
    }
}

#Preview {
    AskLeonardView(viewModel: ChatViewModel())
        .frame(width: 700, height: 500)
        .preferredColorScheme(.dark)
}
