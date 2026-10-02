/**
 * @file FrameSource.cpp
 * @brief 読み込み元の選択処理。
 */
#include "core/FrameSource.h"

#include "core/MediaFoundationSource.h"

#include <utility>

namespace frameplayer {

std::unique_ptr<FrameSource> openFrameSource(const std::wstring& path, int maxWidth, std::shared_ptr<GpuDevice> gpu,
                                             std::wstring& error, SourcePurpose purpose) {
    // 現在はMedia Foundationだけ。連番画像などはここで拡張子を見て振り分ける。
    return MediaFoundationSource::open(path, maxWidth, std::move(gpu), error, purpose);
}

}  // namespace frameplayer
