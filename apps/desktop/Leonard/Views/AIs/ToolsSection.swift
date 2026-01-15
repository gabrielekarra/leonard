import SwiftUI

struct ToolsSection: View {
    @Binding var toolsEnabled: Bool
    @Binding var isExpanded: Bool
    var onToggle: ((Bool) -> Void)?

    var body: some View {
        CollapsibleSection(
            title: "Tools",
            count: nil,
            isExpanded: $isExpanded
        ) {
            VStack(spacing: AppSpacing.medium) {
                // Main toggle
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("System Interaction")
                            .font(.system(size: AppTypography.bodySize, weight: .medium))
                            .foregroundColor(AppColors.textPrimary)

                        Text("Allow Leonard to read files, run commands, and interact with your system")
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(AppColors.textSecondary)
                    }

                    Spacer()

                    Toggle("", isOn: $toolsEnabled)
                        .toggleStyle(.switch)
                        .labelsHidden()
                        .onChange(of: toolsEnabled) { _, newValue in
                            onToggle?(newValue)
                        }
                }
                .padding(AppSpacing.medium)
                .background(AppColors.backgroundSecondary)
                .clipShape(RoundedRectangle(cornerRadius: AppSpacing.cornerRadius))

                // Tool categories info
                if toolsEnabled {
                    VStack(alignment: .leading, spacing: AppSpacing.small) {
                        ToolCategoryRow(
                            icon: "folder",
                            title: "File Operations",
                            description: "Read, write, move, copy, and delete files",
                            color: .blue
                        )

                        ToolCategoryRow(
                            icon: "terminal",
                            title: "Shell Commands",
                            description: "Execute terminal commands",
                            color: .orange
                        )

                        ToolCategoryRow(
                            icon: "info.circle",
                            title: "System Info",
                            description: "Get system information",
                            color: .green
                        )
                    }
                    .padding(AppSpacing.small)
                    .background(AppColors.backgroundSecondary)
                    .clipShape(RoundedRectangle(cornerRadius: AppSpacing.cornerRadius))

                    // Warning
                    HStack(spacing: AppSpacing.small) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)

                        Text("Dangerous operations will ask for confirmation before executing")
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(AppColors.textSecondary)
                    }
                    .padding(AppSpacing.small)
                }
            }
        }
    }
}

struct ToolCategoryRow: View {
    let icon: String
    let title: String
    let description: String
    let color: Color

    var body: some View {
        HStack(spacing: AppSpacing.small) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(color)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: AppTypography.captionSize, weight: .medium))
                    .foregroundColor(AppColors.textPrimary)

                Text(description)
                    .font(.system(size: 11))
                    .foregroundColor(AppColors.textSecondary)
            }

            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .font(.system(size: 14))
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    ToolsSection(
        toolsEnabled: .constant(true),
        isExpanded: .constant(true),
        onToggle: { _ in }
    )
    .padding()
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
