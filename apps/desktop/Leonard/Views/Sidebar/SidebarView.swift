import SwiftUI

struct SidebarView: View {
    @Binding var selectedTab: NavigationTab

    var body: some View {
        VStack(spacing: 0) {
            // Logo/Title
            HStack {
                Text("Leonard")
                    .font(.system(size: AppTypography.titleSize, weight: .semibold))
                    .foregroundColor(AppColors.textPrimary)
                Spacer()
            }
            .padding(.horizontal, AppSpacing.medium)
            .padding(.top, AppSpacing.large)
            .padding(.bottom, AppSpacing.medium)

            Divider()
                .background(AppColors.border)

            // Navigation Items
            VStack(spacing: AppSpacing.small) {
                ForEach(NavigationTab.allCases, id: \.self) { tab in
                    SidebarButton(
                        tab: tab,
                        isSelected: selectedTab == tab,
                        action: { selectedTab = tab }
                    )
                }
            }
            .padding(.horizontal, AppSpacing.small)
            .padding(.top, AppSpacing.medium)

            Spacer()

            // Version
            Text("v\(AppConfig.version)")
                .font(.system(size: AppTypography.captionSize))
                .foregroundColor(AppColors.textSecondary)
                .padding(.bottom, AppSpacing.medium)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppColors.backgroundSecondary)
    }
}

struct SidebarButton: View {
    let tab: NavigationTab
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: AppSpacing.small) {
                Image(systemName: tab.icon)
                    .font(.system(size: 16))
                    .frame(width: 24)
                Text(tab.title)
                    .font(.system(size: AppTypography.bodySize))
                Spacer()
            }
            .foregroundColor(isSelected ? AppColors.textPrimary : AppColors.textSecondary)
            .padding(.horizontal, AppSpacing.small)
            .padding(.vertical, AppSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: AppSpacing.small)
                    .fill(isSelected ? AppColors.accent.opacity(0.2) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppSpacing.small)
                    .stroke(isSelected ? AppColors.accent.opacity(0.5) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    SidebarView(selectedTab: .constant(.chat))
        .frame(width: 200, height: 500)
        .preferredColorScheme(.dark)
}
