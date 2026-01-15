import SwiftUI

struct ModelsSection: View {
    let models: [AIModel]
    @Binding var isExpanded: Bool
    let onInstall: (AIModel) -> Void
    let onRemove: (AIModel) -> Void

    var body: some View {
        CollapsibleSection(
            title: "Installed Models",
            count: models.count,
            isExpanded: $isExpanded
        ) {
            VStack(spacing: 0) {
                ForEach(Array(models.enumerated()), id: \.element.id) { index, model in
                    ModelRow(
                        model: model,
                        onInstall: { onInstall(model) },
                        onRemove: { onRemove(model) }
                    )
                    if index < models.count - 1 {
                        Divider()
                            .background(AppColors.border)
                    }
                }
            }
            .background(AppColors.backgroundSecondary)
            .clipShape(RoundedRectangle(cornerRadius: AppSpacing.cornerRadius))
        }
    }
}

struct ModelRow: View {
    let model: AIModel
    let onInstall: () -> Void
    let onRemove: () -> Void
    @State private var showDeleteConfirmation = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Circle()
                        .fill(model.installed ? Color.green : AppColors.textSecondary)
                        .frame(width: 8, height: 8)
                    Text(model.name)
                        .font(.system(size: AppTypography.bodySize, weight: .medium))
                        .foregroundColor(AppColors.textPrimary)
                }
                Text(model.description)
                    .font(.system(size: AppTypography.captionSize))
                    .foregroundColor(AppColors.textSecondary)
            }

            Spacer()

            Text(model.size)
                .font(.system(size: AppTypography.captionSize))
                .foregroundColor(AppColors.textSecondary)
                .padding(.trailing, AppSpacing.small)

            if model.installed {
                Button(action: { showDeleteConfirmation = true }) {
                    HStack(spacing: 4) {
                        Image(systemName: "trash")
                        Text("Remove")
                    }
                }
                .buttonStyle(DangerButtonStyle())
            } else {
                Button("Install") {
                    onInstall()
                }
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .padding(AppSpacing.medium)
        .alert("Remove Model", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Remove", role: .destructive) {
                onRemove()
            }
        } message: {
            Text("Are you sure you want to remove \"\(model.name)\"? The model file will be deleted from disk.")
        }
    }
}

struct DangerButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: AppTypography.captionSize, weight: .medium))
            .foregroundColor(.red)
            .padding(.horizontal, AppSpacing.medium)
            .padding(.vertical, AppSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: AppSpacing.small)
                    .stroke(Color.red.opacity(0.5), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: AppTypography.captionSize, weight: .medium))
            .foregroundColor(.white)
            .padding(.horizontal, AppSpacing.medium)
            .padding(.vertical, AppSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: AppSpacing.small)
                    .fill(AppColors.accent)
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: AppTypography.captionSize, weight: .medium))
            .foregroundColor(AppColors.textSecondary)
            .padding(.horizontal, AppSpacing.medium)
            .padding(.vertical, AppSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: AppSpacing.small)
                    .stroke(AppColors.border, lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

#Preview {
    ModelsSection(
        models: [
            AIModel(id: "1", name: "Llama 3.2 3B", description: "Fast, general purpose", size: "2.1 GB", installed: true),
            AIModel(id: "2", name: "Mistral 7B", description: "Balanced performance", size: "4.1 GB", installed: false),
        ],
        isExpanded: .constant(true),
        onInstall: { _ in },
        onRemove: { _ in }
    )
    .padding()
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
