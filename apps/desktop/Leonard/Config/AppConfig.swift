import SwiftUI

enum AppConfig {
    static let appName = "Leonard"
    static let version = "0.1.0"

    // API
    static let coreBaseURL = "http://localhost:7878"
    static let apiPrefix = "/api"

    // Window
    static let minWidth: CGFloat = 900
    static let minHeight: CGFloat = 600
    static let sidebarWidth: CGFloat = 200
}

enum AppColors {
    static let background = Color(hex: "1C1C1E")
    static let backgroundSecondary = Color(hex: "2C2C2E")
    static let accent = Color(hex: "6366F1")
    static let textPrimary = Color(hex: "F5F5F7")
    static let textSecondary = Color(hex: "8E8E93")
    static let userBubble = Color(hex: "3A3A3C")
    static let border = Color(hex: "3A3A3C")
}

enum AppTypography {
    static let titleSize: CGFloat = 20
    static let bodySize: CGFloat = 14
    static let captionSize: CGFloat = 12
}

enum AppSpacing {
    static let small: CGFloat = 8
    static let medium: CGFloat = 16
    static let large: CGFloat = 24
    static let cornerRadius: CGFloat = 12
}

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3:
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
