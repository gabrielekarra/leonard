import SwiftUI

struct ChatInput: View {
    @Binding var text: String
    let isLoading: Bool
    let onSend: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(spacing: AppSpacing.small) {
            TextField("Ask Leonard...", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: AppTypography.bodySize))
                .foregroundColor(AppColors.textPrimary)
                .focused($isFocused)
                .lineLimit(1...5)
                .onSubmit {
                    if !text.isEmpty && !isLoading {
                        onSend()
                    }
                }
                .padding(.horizontal, AppSpacing.medium)
                .padding(.vertical, AppSpacing.small)
                .background(
                    RoundedRectangle(cornerRadius: AppSpacing.cornerRadius)
                        .fill(AppColors.backgroundSecondary)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: AppSpacing.cornerRadius)
                        .stroke(isFocused ? AppColors.accent.opacity(0.5) : AppColors.border, lineWidth: 1)
                )

            Button(action: onSend) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundColor(canSend ? AppColors.accent : AppColors.textSecondary)
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(AppSpacing.medium)
        .background(AppColors.background)
    }

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isLoading
    }
}

#Preview {
    VStack {
        Spacer()
        ChatInput(text: .constant(""), isLoading: false) {}
        ChatInput(text: .constant("Hello"), isLoading: false) {}
        ChatInput(text: .constant(""), isLoading: true) {}
    }
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
