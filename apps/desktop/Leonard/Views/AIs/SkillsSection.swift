import SwiftUI

struct SkillsSection: View {
    let skills: [Skill]
    @Binding var isExpanded: Bool

    var body: some View {
        CollapsibleSection(
            title: "Skills",
            count: skills.count,
            isExpanded: $isExpanded
        ) {
            VStack(spacing: 0) {
                ForEach(Array(skills.enumerated()), id: \.element.id) { index, skill in
                    SkillRow(skill: skill)
                    if index < skills.count - 1 {
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

struct SkillRow: View {
    let skill: Skill

    var body: some View {
        HStack {
            Image(systemName: skillIcon)
                .font(.system(size: 16))
                .foregroundColor(AppColors.accent)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 4) {
                Text(skill.name)
                    .font(.system(size: AppTypography.bodySize, weight: .medium))
                    .foregroundColor(AppColors.textPrimary)
                Text(skill.description)
                    .font(.system(size: AppTypography.captionSize))
                    .foregroundColor(AppColors.textSecondary)
            }

            Spacer()

            Text(skill.active ? "Active" : "Add")
                .font(.system(size: AppTypography.captionSize, weight: .medium))
                .foregroundColor(skill.active ? Color.green : AppColors.textSecondary)
                .padding(.horizontal, AppSpacing.small)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: AppSpacing.small)
                        .fill(skill.active ? Color.green.opacity(0.1) : AppColors.border.opacity(0.3))
                )
        }
        .padding(AppSpacing.medium)
    }

    private var skillIcon: String {
        switch skill.name.lowercased() {
        case "summarizer":
            return "doc.text"
        case "translator":
            return "globe"
        default:
            return "star.fill"
        }
    }
}

struct CollapsibleSection<Content: View>: View {
    let title: String
    let count: Int?
    @Binding var isExpanded: Bool
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(spacing: AppSpacing.small) {
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            }) {
                HStack {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(AppColors.textSecondary)
                        .frame(width: 16)
                    Text(title)
                        .font(.system(size: AppTypography.bodySize, weight: .semibold))
                        .foregroundColor(AppColors.textPrimary)
                    if let count = count {
                        Text("(\(count))")
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(AppColors.textSecondary)
                    }
                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                content()
            }
        }
    }
}

#Preview {
    SkillsSection(
        skills: [
            Skill(id: "1", name: "Summarizer", description: "Summarize documents and text", active: true),
            Skill(id: "2", name: "Translator", description: "Translate between languages", active: false),
        ],
        isExpanded: .constant(true)
    )
    .padding()
    .background(AppColors.background)
    .preferredColorScheme(.dark)
}
