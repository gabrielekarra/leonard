import SwiftUI

struct AIsView: View {
    @Bindable var viewModel: AIsViewModel
    @State private var installedModelsExpanded = true
    @State private var featuredExpanded = true
    @State private var searchResultsExpanded = true
    @State private var toolsExpanded = true

    var body: some View {
        VStack(spacing: 0) {
            // Search Bar with HuggingFace search
            HFSearchBar(
                text: $viewModel.searchText,
                isSearching: viewModel.isSearching,
                onSearch: {
                    Task { await viewModel.searchHuggingFace() }
                },
                onClear: {
                    viewModel.clearSearch()
                }
            )
            .padding(AppSpacing.medium)

            // Active Downloads Banner
            if !viewModel.activeDownloads.isEmpty {
                DownloadsBanner(
                    downloads: Array(viewModel.activeDownloads.values),
                    onCancel: { downloadId in
                        Task { await viewModel.cancelDownload(downloadId: downloadId) }
                    }
                )
                .padding(.horizontal, AppSpacing.medium)
            }

            if viewModel.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(spacing: AppSpacing.medium) {
                        // HuggingFace Search Results (shown when searching)
                        if viewModel.showSearchResults {
                            HFSearchResultsSection(
                                title: "Search Results",
                                results: viewModel.searchResults,
                                isSearching: viewModel.isSearching,
                                isExpanded: $searchResultsExpanded,
                                onDownload: { result, file in
                                    Task { await viewModel.downloadModel(result: result, file: file) }
                                }
                            )
                        }

                        // Installed Models Section
                        if !viewModel.filteredModels.isEmpty {
                            ModelsSection(
                                models: viewModel.filteredModels,
                                isExpanded: $installedModelsExpanded,
                                onInstall: { model in
                                    Task { await viewModel.installModel(model) }
                                },
                                onRemove: { model in
                                    Task { await viewModel.removeModel(model) }
                                }
                            )
                        }

                        // Featured Models Section (shown when not searching)
                        if !viewModel.showSearchResults {
                            HFSearchResultsSection(
                                title: "Popular Models",
                                results: viewModel.featuredModels,
                                isSearching: viewModel.isLoadingFeatured,
                                isExpanded: $featuredExpanded,
                                onDownload: { result, file in
                                    Task { await viewModel.downloadModel(result: result, file: file) }
                                }
                            )
                        }

                        // Tools Section
                        ToolsSection(
                            toolsEnabled: $viewModel.toolsEnabled,
                            isExpanded: $toolsExpanded,
                            onToggle: { enabled in
                                Task { await viewModel.setToolsEnabled(enabled) }
                            }
                        )
                    }
                    .padding(AppSpacing.medium)
                }
            }

            if let error = viewModel.errorMessage {
                ErrorBanner(message: error)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppColors.background)
    }
}

// MARK: - HuggingFace Search Bar

struct HFSearchBar: View {
    @Binding var text: String
    let isSearching: Bool
    let onSearch: () -> Void
    let onClear: () -> Void

    var body: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(AppColors.textSecondary)
            TextField("Search HuggingFace models...", text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: AppTypography.bodySize))
                .foregroundColor(AppColors.textPrimary)
                .onSubmit {
                    onSearch()
                }
            if isSearching {
                ProgressView()
                    .scaleEffect(0.7)
            } else if !text.isEmpty {
                Button(action: onClear) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(AppColors.textSecondary)
                }
                .buttonStyle(.plain)

                Button("Search") {
                    onSearch()
                }
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .padding(AppSpacing.small)
        .background(
            RoundedRectangle(cornerRadius: AppSpacing.small)
                .fill(AppColors.backgroundSecondary)
        )
    }
}

// MARK: - HuggingFace Search Results

struct HFSearchResultsSection: View {
    let title: String
    let results: [HFSearchResult]
    let isSearching: Bool
    @Binding var isExpanded: Bool
    let onDownload: (HFSearchResult, GGUFFile) -> Void

    var body: some View {
        CollapsibleSection(
            title: title,
            count: results.count,
            isExpanded: $isExpanded
        ) {
            VStack(spacing: 0) {
                if isSearching {
                    HStack {
                        ProgressView()
                        Text("Loading models...")
                            .foregroundColor(AppColors.textSecondary)
                    }
                    .padding(AppSpacing.medium)
                } else if results.isEmpty {
                    Text("No models found. Try a different search.")
                        .foregroundColor(AppColors.textSecondary)
                        .padding(AppSpacing.medium)
                } else {
                    ForEach(Array(results.enumerated()), id: \.element.id) { index, result in
                        HFModelRow(result: result, onDownload: { file in
                            onDownload(result, file)
                        })
                        if index < results.count - 1 {
                            Divider()
                                .background(AppColors.border)
                        }
                    }
                }
            }
            .background(AppColors.backgroundSecondary)
            .clipShape(RoundedRectangle(cornerRadius: AppSpacing.cornerRadius))
        }
    }
}

struct HFModelRow: View {
    let result: HFSearchResult
    let onDownload: (GGUFFile) -> Void
    @State private var isExpanded = false

    // Get recommended file (Q4_K_M or similar)
    var recommendedFile: GGUFFile? {
        let preferred = ["Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q8_0"]
        for quant in preferred {
            if let file = result.ggufFiles.first(where: { $0.quantization == quant }) {
                return file
            }
        }
        return result.ggufFiles.first
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppSpacing.small) {
            // Header row with name and stats
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    // Model name
                    HStack(spacing: 6) {
                        Text(result.name)
                            .font(.system(size: AppTypography.bodySize, weight: .semibold))
                            .foregroundColor(result.isCompatible ? AppColors.textPrimary : AppColors.textSecondary)

                        // Incompatible warning badge
                        if !result.isCompatible {
                            HStack(spacing: 2) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                Text("Incompatible")
                            }
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.red)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.red.opacity(0.15))
                            .clipShape(Capsule())
                        }
                    }

                    // Author
                    Text("by \(result.author)")
                        .font(.system(size: AppTypography.captionSize))
                        .foregroundColor(AppColors.textSecondary)

                    // Description or incompatibility reason
                    if let reason = result.incompatibilityReason {
                        Text(reason)
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(.red.opacity(0.8))
                            .lineLimit(2)
                    } else {
                        Text(result.modelDescription)
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(AppColors.textSecondary)
                            .lineLimit(2)
                    }
                }

                Spacer()

                // Right side: RAM requirement and stats
                VStack(alignment: .trailing, spacing: 4) {
                    // RAM requirement badge
                    Text(result.ramRequired)
                        .font(.system(size: AppTypography.captionSize, weight: .medium))
                        .foregroundColor(.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.orange.opacity(0.15))
                        .clipShape(Capsule())

                    // Download stats
                    HStack(spacing: AppSpacing.small) {
                        Label("\(formatNumber(result.downloads))", systemImage: "arrow.down.circle")
                        Label("\(result.likes)", systemImage: "heart")
                    }
                    .font(.system(size: AppTypography.captionSize))
                    .foregroundColor(AppColors.textSecondary)
                }
            }

            // Action row - only show if compatible
            if result.isCompatible {
                HStack {
                    // Quick download button for recommended file
                    if let file = recommendedFile {
                        Button("Download \(file.quantization)") {
                            onDownload(file)
                        }
                        .buttonStyle(PrimaryButtonStyle())

                        Text(file.sizeFormatted)
                            .font(.system(size: AppTypography.captionSize))
                            .foregroundColor(AppColors.textSecondary)
                    }

                    Spacer()

                    // Expand to see all files
                    if result.ggufFiles.count > 1 {
                        Button(action: { isExpanded.toggle() }) {
                            HStack(spacing: 4) {
                                Text(isExpanded ? "Hide options" : "More options")
                                    .font(.system(size: AppTypography.captionSize))
                                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            }
                            .foregroundColor(AppColors.accent)
                        }
                        .buttonStyle(.plain)
                    }
                }

                // Expanded file list
                if isExpanded {
                    VStack(spacing: 6) {
                        ForEach(result.ggufFiles.prefix(10)) { file in
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(file.quantization)
                                        .font(.system(size: AppTypography.captionSize, weight: .medium))
                                        .foregroundColor(AppColors.textPrimary)
                                    Text("\(file.sizeFormatted) • \(file.ramRequired)")
                                        .font(.system(size: 11))
                                        .foregroundColor(AppColors.textSecondary)
                                }
                                Spacer()
                                Button("Download") {
                                    onDownload(file)
                                }
                                .buttonStyle(SecondaryButtonStyle())
                            }
                            .padding(.vertical, 4)
                        }
                        if result.ggufFiles.count > 10 {
                            Text("+ \(result.ggufFiles.count - 10) more files")
                                .font(.system(size: AppTypography.captionSize))
                                .foregroundColor(AppColors.textSecondary)
                        }
                    }
                    .padding(.top, AppSpacing.small)
                    .padding(.leading, AppSpacing.small)
                }
            }
        }
        .padding(AppSpacing.medium)
        .opacity(result.isCompatible ? 1.0 : 0.7)
    }

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 {
            return String(format: "%.1fM", Double(n) / 1_000_000)
        } else if n >= 1_000 {
            return String(format: "%.1fK", Double(n) / 1_000)
        }
        return "\(n)"
    }
}

// MARK: - Downloads Banner

struct DownloadsBanner: View {
    let downloads: [AIsViewModel.DownloadProgress]
    var onCancel: ((String) -> Void)?

    var body: some View {
        VStack(spacing: AppSpacing.small) {
            ForEach(downloads) { download in
                VStack(spacing: 6) {
                    HStack {
                        // Status icon
                        if download.isComplete {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                        } else if download.isCancelled {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.orange)
                        } else if download.error != nil {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.red)
                        } else {
                            Image(systemName: "arrow.down.circle")
                                .foregroundColor(AppColors.accent)
                        }

                        // Info
                        VStack(alignment: .leading, spacing: 2) {
                            Text(download.filename)
                                .font(.system(size: AppTypography.captionSize, weight: .medium))
                                .foregroundColor(AppColors.textPrimary)
                                .lineLimit(1)

                            if let error = download.error {
                                Text(error)
                                    .font(.system(size: 11))
                                    .foregroundColor(.red)
                            } else if download.isComplete {
                                Text("Download complete")
                                    .font(.system(size: 11))
                                    .foregroundColor(.green)
                            } else {
                                Text("\(download.status.capitalized) • \(download.progressFormatted)")
                                    .font(.system(size: 11))
                                    .foregroundColor(AppColors.textSecondary)
                            }
                        }

                        Spacer()

                        // Percentage
                        if !download.isComplete && download.error == nil {
                            Text("\(Int(download.progressPercent))%")
                                .font(.system(size: AppTypography.captionSize, weight: .semibold))
                                .foregroundColor(AppColors.accent)
                                .monospacedDigit()

                            // Cancel button
                            Button(action: {
                                onCancel?(download.id)
                            }) {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(AppColors.textSecondary)
                            }
                            .buttonStyle(.plain)
                            .help("Cancel download")
                        }
                    }

                    // Progress bar
                    if !download.isComplete && download.error == nil {
                        GeometryReader { geometry in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(AppColors.border)
                                    .frame(height: 4)

                                RoundedRectangle(cornerRadius: 2)
                                    .fill(AppColors.accent)
                                    .frame(width: geometry.size.width * CGFloat(download.progressPercent / 100), height: 4)
                            }
                        }
                        .frame(height: 4)
                    }
                }
                .padding(AppSpacing.small)
                .background(AppColors.backgroundSecondary)
                .clipShape(RoundedRectangle(cornerRadius: AppSpacing.small))
            }
        }
    }
}

#Preview {
    AIsView(viewModel: AIsViewModel())
        .frame(width: 700, height: 600)
        .preferredColorScheme(.dark)
}
