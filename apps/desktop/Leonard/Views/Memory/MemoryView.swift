import SwiftUI

struct MemoryView: View {
    @Bindable var viewModel: MemoryViewModel
    @Bindable var toolsViewModel: ToolsViewModel
    @State private var toolsExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: AppSpacing.large) {
            // Header
            Text("Document Memory")
                .font(.system(size: AppTypography.titleSize, weight: .semibold))
                .foregroundColor(AppColors.textPrimary)

            Text("When enabled, Leonard can search your Documents, Desktop, and Downloads folders to answer questions about your files.")
                .font(.system(size: AppTypography.bodySize))
                .foregroundColor(AppColors.textSecondary)

            // Toggle
            VStack(alignment: .leading, spacing: AppSpacing.small) {
                Toggle(isOn: Binding(
                    get: { viewModel.enabled },
                    set: { newValue in
                        Task { await viewModel.toggle(newValue) }
                    }
                )) {
                    Text("Enable Document Memory")
                        .font(.system(size: AppTypography.bodySize, weight: .medium))
                        .foregroundColor(AppColors.textPrimary)
                }
                .toggleStyle(.switch)
            }
            .padding(AppSpacing.medium)
            .background(AppColors.backgroundSecondary)
            .cornerRadius(AppSpacing.small)

            // Status
            if viewModel.isIndexing {
                HStack(spacing: AppSpacing.small) {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Indexing your documents...")
                        .font(.system(size: AppTypography.bodySize))
                        .foregroundColor(AppColors.textSecondary)
                }
                .padding(AppSpacing.medium)
                .background(AppColors.accent.opacity(0.1))
                .cornerRadius(AppSpacing.small)
            } else if viewModel.enabled && viewModel.indexed {
                HStack(spacing: AppSpacing.small) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Ready - Your documents are indexed")
                        .font(.system(size: AppTypography.bodySize))
                        .foregroundColor(AppColors.textSecondary)
                }
                .padding(AppSpacing.medium)
                .background(AppColors.backgroundSecondary)
                .cornerRadius(AppSpacing.small)
            }

            ToolsSection(
                toolsEnabled: $toolsViewModel.toolsEnabled,
                isExpanded: $toolsExpanded,
                onToggle: { enabled in
                    Task { await toolsViewModel.toggleTools(enabled) }
                }
            )

            Spacer()
        }
        .padding(AppSpacing.large)
        .background(AppColors.background)
        .onAppear {
            Task {
                await viewModel.loadStatus()
                await toolsViewModel.loadStatus()
            }
        }
    }
}

#Preview {
    MemoryView(viewModel: MemoryViewModel(), toolsViewModel: ToolsViewModel())
        .frame(width: 500, height: 400)
        .preferredColorScheme(.dark)
}
