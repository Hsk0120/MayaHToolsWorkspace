/**
 * @file Clip.cpp
 * @brief 動画の全コマ読み込みと縮小の実装。
 */
#include "core/Clip.h"

#include <algorithm>
#include <new>

#include <ppl.h>

#include "core/FrameSource.h"

namespace frameplayer {

bool Clip::load(const std::wstring& path, int maxWidth, const ProgressCallback& progress, std::wstring& error) {
    frames_.clear();
    frames_.shrink_to_fit();
    frameRate_ = 0.0;
    path_.clear();

    std::unique_ptr<FrameSource> source = openFrameSource(path, error);
    if (!source) {
        return false;
    }

    try {
        Frame decoded;
        while (source->readNext(decoded)) {
            frames_.push_back(shrinkToWidth(decoded, maxWidth));
            if (progress) {
                progress(frameCount());
            }
        }
    } catch (const std::bad_alloc&) {
        frames_.clear();
        frames_.shrink_to_fit();
        error = L"メモリが足りません。短い動画にするか、保持する画像の幅を小さくしてください";
        return false;
    }

    if (!source->error().empty()) {
        frames_.clear();
        error = source->error();
        return false;
    }
    if (frames_.empty()) {
        error = L"コマが1つもありません";
        return false;
    }
    frameRate_ = source->frameRate();
    path_ = path;
    return true;
}

Frame shrinkToWidth(const Frame& source, int maxWidth) {
    if (maxWidth <= 0 || source.width <= maxWidth) {
        return source;
    }

    Frame result;
    result.width = maxWidth;
    result.height = std::max(1, static_cast<int>(static_cast<long long>(source.height) * maxWidth / source.width));
    result.pixels.resize(static_cast<size_t>(result.width) * result.height);

    // 縮小先の各列が対応する元の列の範囲[x0, x1)は全行で共通なので、先に求めておく。
    std::vector<int> columnStart(static_cast<size_t>(result.width) + 1);
    for (int x = 0; x <= result.width; ++x) {
        columnStart[static_cast<size_t>(x)] =
            static_cast<int>(static_cast<long long>(x) * source.width / result.width);
    }

    // 行ごとに独立しているので、複数のCPUコアで分担する(PPLはMSVC標準のライブラリ)。
    concurrency::parallel_for(0, result.height, [&](int y) {
        // 縮小先の1行が対応する元の行の範囲[y0, y1)。
        const int y0 = static_cast<int>(static_cast<long long>(y) * source.height / result.height);
        const int y1 = std::max(y0 + 1, static_cast<int>(static_cast<long long>(y + 1) * source.height / result.height));
        std::uint32_t* dst = result.pixels.data() + static_cast<size_t>(y) * result.width;
        for (int x = 0; x < result.width; ++x) {
            const int x0 = columnStart[static_cast<size_t>(x)];
            const int x1 = std::max(x0 + 1, columnStart[static_cast<size_t>(x) + 1]);
            unsigned int b = 0, g = 0, r = 0;
            for (int sy = y0; sy < y1; ++sy) {
                const std::uint32_t* row = source.pixels.data() + static_cast<size_t>(sy) * source.width;
                for (int sx = x0; sx < x1; ++sx) {
                    const std::uint32_t p = row[sx];
                    b += p & 0xFF;
                    g += (p >> 8) & 0xFF;
                    r += (p >> 16) & 0xFF;
                }
            }
            const unsigned int count = static_cast<unsigned int>((y1 - y0) * (x1 - x0));
            dst[x] = 0xFF000000u | ((r / count) << 16) | ((g / count) << 8) | (b / count);
        }
    });
    return result;
}

}  // namespace frameplayer
