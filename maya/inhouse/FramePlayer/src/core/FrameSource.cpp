/**
 * @file FrameSource.cpp
 * @brief 読み込み元の選択処理。
 */
#include "core/FrameSource.h"

#include "core/ImageSequenceSource.h"
#include "core/MediaFoundationSource.h"

#include <algorithm>
#include <atomic>
#include <cwctype>
#include <utility>

namespace frameplayer {

namespace {

/// 連番画像のフレームレート(画像には記録されていない)。
std::atomic<double> g_sequenceFrameRate{ImageSequenceSource::kDefaultFrameRate};

}  // namespace

bool isImageFile(const std::wstring& path) {
    const std::size_t dot = path.find_last_of(L'.');
    if (dot == std::wstring::npos) {
        return false;
    }
    std::wstring extension = path.substr(dot + 1);
    std::transform(extension.begin(), extension.end(), extension.begin(),
                   [](wchar_t c) { return static_cast<wchar_t>(std::towlower(c)); });
    for (const wchar_t* image : ImageSequenceSource::kExtensions) {
        if (extension == image) {
            return true;
        }
    }
    return false;
}

void setImageSequenceFrameRate(double rate) {
    g_sequenceFrameRate = rate > 0.0 ? rate : ImageSequenceSource::kDefaultFrameRate;
}

std::unique_ptr<FrameSource> openFrameSource(const std::wstring& path, int maxWidth, std::shared_ptr<GpuDevice> gpu,
                                             std::wstring& error, SourcePurpose purpose) {
    // 画像は連番画像として、それ以外はMedia Foundationで開く。
    if (isImageFile(path)) {
        return ImageSequenceSource::open(path, g_sequenceFrameRate.load(), maxWidth, error, purpose);
    }
    return MediaFoundationSource::open(path, maxWidth, std::move(gpu), error, purpose);
}

}  // namespace frameplayer
