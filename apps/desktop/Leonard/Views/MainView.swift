import SwiftUI

enum NavigationTab: String, CaseIterable {
    case askLeonard = "askLeonard"
    case ais = "AIs"

    var icon: String {
        switch self {
        case .askLeonard:
            return "bubble.left.and.bubble.right"
        case .ais:
            return "cpu"
        }
    }

    var title: String {
        rawValue
    }
}

struct MainView: View {
    @State private var selectedTab: NavigationTab = .askLeonard
    @State private var chatViewModel = ChatViewModel()
    @State private var aisViewModel = AIsViewModel()

    var body: some View {
        NavigationSplitView {
            SidebarView(selectedTab: $selectedTab)
                .navigationSplitViewColumnWidth(AppConfig.sidebarWidth)
        } detail: {
            contentView
                .frame(minWidth: AppConfig.minWidth - AppConfig.sidebarWidth)
        }
        .frame(minWidth: AppConfig.minWidth, minHeight: AppConfig.minHeight)
        .background(AppColors.background)
    }

    @ViewBuilder
    private var contentView: some View {
        switch selectedTab {
        case .askLeonard:
            AskLeonardView(viewModel: chatViewModel)
        case .ais:
            AIsView(viewModel: aisViewModel)
        }
    }
}

#Preview {
    MainView()
        .preferredColorScheme(.dark)
}
