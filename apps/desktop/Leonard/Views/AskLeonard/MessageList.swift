import SwiftUI

struct MessageList: View {
    let messages: [Message]
    let isLoading: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: AppSpacing.medium) {
                    ForEach(messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if isLoading {
                        TypingIndicator()
                            .id("typing")
                    }
                }
                .padding(AppSpacing.medium)
            }
            .onChange(of: messages.count) { _, _ in
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: isLoading) { _, _ in
                scrollToBottom(proxy: proxy)
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.2)) {
            if isLoading {
                proxy.scrollTo("typing", anchor: .bottom)
            } else if let lastMessage = messages.last {
                proxy.scrollTo(lastMessage.id, anchor: .bottom)
            }
        }
    }
}

struct TypingIndicator: View {
    @State private var animationOffset: CGFloat = 0

    var body: some View {
        HStack(alignment: .top, spacing: AppSpacing.small) {
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(AppColors.textSecondary)
                        .frame(width: 6, height: 6)
                        .offset(y: animationOffset(for: index))
                }
            }
            .padding(.horizontal, AppSpacing.medium)
            .padding(.vertical, AppSpacing.small)
            .background(AppColors.backgroundSecondary)
            .clipShape(RoundedRectangle(cornerRadius: AppSpacing.cornerRadius))

            Spacer()
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) {
                animationOffset = -4
            }
        }
    }

    private func animationOffset(for index: Int) -> CGFloat {
        let delay = Double(index) * 0.15
        return animationOffset * cos(delay * .pi)
    }
}

#Preview {
    MessageList(
        messages: [
            Message(content: "Hello, Leonard!", role: .user),
            Message(content: "Hello! How can I help you today?", role: .assistant),
        ],
        isLoading: false
    )
    .frame(width: 600, height: 400)
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
