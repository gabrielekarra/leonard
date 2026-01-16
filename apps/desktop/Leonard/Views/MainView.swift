import SwiftUI

enum NavigationTab: String, CaseIterable {
    case chat = "Chat"
    case ais = "AIs"
    case memory = "Memory"
    case externalTool = "External Tool"

    var icon: String {
        switch self {
        case .chat:
            return "bubble.left.and.bubble.right"
        case .ais:
            return "cpu"
        case .memory:
            return "brain.head.profile"
        case .externalTool:
            return "link"
        }
    }

    var title: String {
        rawValue
    }
}

struct MainView: View {
    @State private var selectedTab: NavigationTab = .chat
    @State private var chatViewModel = ChatViewModel()
    @State private var aisViewModel = AIsViewModel()
    @State private var memoryViewModel = MemoryViewModel()
    @State private var toolsViewModel = ToolsViewModel()

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
        case .chat:
            AskLeonardView(viewModel: chatViewModel)
        case .ais:
            AIsView(viewModel: aisViewModel)
        case .memory:
            MemoryView(viewModel: memoryViewModel, toolsViewModel: toolsViewModel)
        case .externalTool:
            ExternalToolView()
        }
    }
}

#Preview {
    MainView()
        .preferredColorScheme(.dark)
}
