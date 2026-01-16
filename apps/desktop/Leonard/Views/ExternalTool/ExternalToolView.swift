import SwiftUI

struct ExternalToolView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: AppSpacing.large) {
            Text("External Tool")
                .font(.system(size: AppTypography.titleSize, weight: .semibold))
                .foregroundColor(AppColors.textPrimary)

            Text("Connect external tools to extend Leonard with third-party capabilities.")
                .font(.system(size: AppTypography.bodySize))
                .foregroundColor(AppColors.textSecondary)

            VStack(alignment: .leading, spacing: AppSpacing.small) {
                Text("No external tools configured")
                    .font(.system(size: AppTypography.bodySize, weight: .medium))
                    .foregroundColor(AppColors.textPrimary)

                Text("Add a tool connection to get started.")
                    .font(.system(size: AppTypography.captionSize))
                    .foregroundColor(AppColors.textSecondary)
            }
            .padding(AppSpacing.medium)
            .background(AppColors.backgroundSecondary)
            .cornerRadius(AppSpacing.small)

            Spacer()
        }
        .padding(AppSpacing.large)
        .background(AppColors.background)
    }
}

#Preview {
    ExternalToolView()
        .frame(width: 500, height: 400)
        .preferredColorScheme(.dark)
}
