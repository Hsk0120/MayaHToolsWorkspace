/**
 * @file KeyframeThumbnails.cpp
 * @brief キーフレームの縮小画像の作成と検索の実装。
 */
#include "core/KeyframeThumbnails.h"

#include <windows.h>
#include <objbase.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <new>

#include "core/Clip.h"
#include "core/ThreadQos.h"

namespace frameplayer {

namespace {

/// 開いた直後は再生用の先読みにデコーダーを譲るため、作成を始めるまで待つ時間。
constexpr auto kStartDelay = std::chrono::milliseconds(1500);

/**
 * @brief BGRAの1画素をRGB565(赤5・緑6・青5ビット)へ詰める。
 * @param pixel メモリ上でB,G,R,Aの順に並ぶ画素。
 * @return 2バイトの画素。
 */
std::uint16_t toRgb565(std::uint32_t pixel) {
    const std::uint32_t b = pixel & 0xFF;
    const std::uint32_t g = (pixel >> 8) & 0xFF;
    const std::uint32_t r = (pixel >> 16) & 0xFF;
    return static_cast<std::uint16_t>(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

/**
 * @brief RGB565の1画素を不透明なBGRAへ戻す。
 * @param pixel 2バイトの画素。
 * @return メモリ上でB,G,R,Aの順に並ぶ画素。
 */
std::uint32_t fromRgb565(std::uint16_t pixel) {
    const std::uint32_t r5 = (pixel >> 11) & 0x1F;
    const std::uint32_t g6 = (pixel >> 5) & 0x3F;
    const std::uint32_t b5 = pixel & 0x1F;
    // 上位ビットを下位へ繰り返すと、0〜255の全範囲に広がる(31→255、0→0)。
    const std::uint32_t r = (r5 << 3) | (r5 >> 2);
    const std::uint32_t g = (g6 << 2) | (g6 >> 4);
    const std::uint32_t b = (b5 << 3) | (b5 >> 2);
    return 0xFF000000u | (r << 16) | (g << 8) | b;
}

}  // namespace

KeyframeThumbnails::~KeyframeThumbnails() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stop_ = true;
    }
    wake_.notify_all();
    if (thread_.joinable()) {
        thread_.join();
    }
}

void KeyframeThumbnails::start(const std::wstring& path, int frameCount, double frameRate, int width,
                               std::size_t budgetBytes, std::shared_ptr<GpuDevice> gpu, NotifyCallback notify) {
    frameCount_ = frameCount;
    frameRate_ = frameRate;
    width_ = std::max(16, width);
    budgetBytes_ = budgetBytes;
    notify_ = std::move(notify);
    thread_ = std::thread(&KeyframeThumbnails::run, this, path, std::move(gpu));
}

void KeyframeThumbnails::setPaused(bool paused) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        paused_ = paused;
    }
    wake_.notify_all();
}

bool KeyframeThumbnails::progress(int& done, int& total) const {
    std::lock_guard<std::mutex> lock(mutex_);
    total = static_cast<int>(positions_.size());
    done = static_cast<int>(std::count_if(images_.begin(), images_.end(), [](const auto& image) { return !image.empty(); }));
    return finished_;
}

std::size_t KeyframeThumbnails::bytes() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return bytes_;
}

std::shared_ptr<const Frame> KeyframeThumbnails::nearest(int index, int* imageIndex) const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (positions_.empty()) {
        return nullptr;
    }
    // indexの左右で、作成済みの最も近い画像を探す。
    const int count = static_cast<int>(positions_.size());
    const int right0 = static_cast<int>(std::lower_bound(positions_.begin(), positions_.end(), index) - positions_.begin());
    int left = right0 - 1;
    while (left >= 0 && images_[static_cast<std::size_t>(left)].empty()) {
        --left;
    }
    int right = right0;
    while (right < count && images_[static_cast<std::size_t>(right)].empty()) {
        ++right;
    }
    int chosen = -1;
    if (left >= 0 && right < count) {
        chosen = (index - positions_[static_cast<std::size_t>(left)]) <= (positions_[static_cast<std::size_t>(right)] - index)
                     ? left
                     : right;
    } else if (left >= 0) {
        chosen = left;
    } else if (right < count) {
        chosen = right;
    }
    if (chosen < 0) {
        return nullptr;
    }
    if (imageIndex) {
        *imageIndex = positions_[static_cast<std::size_t>(chosen)];
    }
    if (chosen == lastPosition_ && lastFrame_) {
        return lastFrame_;
    }
    // 描画側はBGRAの画像を描くので、選んだ1枚だけを戻して渡す(1枚は約0.2MB、変換は1ms未満)。
    auto frame = std::make_shared<Frame>();
    frame->width = imageWidth_;
    frame->height = imageHeight_;
    frame->color = imageColor_;  // 値は動画の色域・伝達関数のままなので、描画で画面に合わせるために付ける。
    frame->pixelAspect = imageAspect_;
    const std::vector<std::uint16_t>& image = images_[static_cast<std::size_t>(chosen)];
    frame->pixels.resize(image.size());
    std::transform(image.begin(), image.end(), frame->pixels.begin(), fromRgb565);
    lastPosition_ = chosen;
    lastFrame_ = std::move(frame);
    return lastFrame_;
}

bool KeyframeThumbnails::waitWhilePaused(FrameSource& source) {
    std::unique_lock<std::mutex> lock(mutex_);
    if (paused_ && !stop_) {
        // 止めている間はデコーダー(GPUのメモリを含む)を返しておく。再開後の最初のシークで作り直される。
        lock.unlock();
        source.releaseDecoder();
        lock.lock();
        wake_.wait(lock, [&] { return !paused_ || stop_; });
    }
    return stop_;
}

void KeyframeThumbnails::run(std::wstring path, std::shared_ptr<GpuDevice> gpu) {
    // ほかのアプリや再生用の先読みの邪魔をしないよう、このスレッドはずっと「裏の作業」として動かす。
    setBackgroundWork(true);
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool stopping = false;
    {
        std::unique_lock<std::mutex> lock(mutex_);
        wake_.wait_for(lock, kStartDelay, [&] { return stop_; });
        wake_.wait(lock, [&] { return !paused_ || stop_; });
        stopping = stop_;
    }

    // 開くときはロックを外しておく(形式によっては目次作りに時間がかかるため)。
    std::wstring error;
    std::unique_ptr<FrameSource> source;
    if (!stopping) {
        source = openFrameSource(path, width_, std::move(gpu), error, SourcePurpose::Thumbnails);
    }

    // キーフレームを1つデコードし、縮小画像にする。
    auto decode = [&](int keyIndex, Frame& out) {
        if (!source->seekToKeyFrame(keyIndex)) {
            return false;
        }
        int index = -1;
        Frame decoded;
        try {
            if (!source->readNext(decoded, index) || decoded.onGpu()) {
                return false;
            }
            if (decoded.isYuv()) {
                // YUVのまま届くので、BGRAにする。縮める画像は、仕上がりの2倍の幅まで間引いてから面積の平均で縮める。
                Frame rgb;
                rgb.width = std::min(decoded.width, width_ * 2);
                rgb.height = std::max(1, static_cast<int>(static_cast<long long>(decoded.height) * rgb.width / decoded.width));
                rgb.color = decoded.color;
                rgb.pixelAspect = decoded.pixelAspect;
                rgb.pixels.resize(static_cast<std::size_t>(rgb.width) * rgb.height);
                convertPlanesToBgra(decoded.planes.data(), decoded.width, decoded.height, decoded.layout,
                                    decoded.color, rgb.width, rgb.height,
                                    rgb.pixels.data());
                decoded = std::move(rgb);
            }
            if (decoded.pixels.empty()) {
                return false;
            }
            out = decoded.width > width_ ? shrinkToWidth(decoded, width_) : std::move(decoded);
        } catch (const std::bad_alloc&) {
            return false;
        }
        return true;
    };
    auto pack = [](const Frame& frame) {
        std::vector<std::uint16_t> image(frame.pixels.size());
        std::transform(frame.pixels.begin(), frame.pixels.end(), image.begin(), toRgb565);
        return image;
    };

    Frame first;
    if (source && source->frameCount() == frameCount_ && decode(0, first)) {
        // 1枚の大きさが分かったので、上限に収まるよう間隔を決めてキーフレームを選ぶ。
        const std::size_t imageBytes = std::max<std::size_t>(1, static_cast<std::size_t>(first.width) * first.height * 2);
        const int maxCount = static_cast<int>(std::max<std::size_t>(1, budgetBytes_ / imageBytes));
        const int oneSecond = std::max(1, static_cast<int>(std::lround(frameRate_ > 0 ? frameRate_ : 24.0)));
        const int minGap = std::max(oneSecond, (frameCount_ + maxCount - 1) / maxCount);
        std::vector<int> keys;
        for (int key = source->keyFrameAtOrBefore(frameCount_ - 1);; key = source->keyFrameAtOrBefore(key - 1)) {
            keys.push_back(key);
            if (key <= 0) {
                break;
            }
        }
        std::reverse(keys.begin(), keys.end());
        std::vector<int> positions;
        for (int key : keys) {
            if (positions.empty() || key - positions.back() >= minGap) {
                positions.push_back(key);
            }
        }

        // キーフレームの情報が無い形式(常に先頭から読む)では、仮表示に使えないので作らない。
        if (positions.size() >= 2) {
            std::vector<int> order;  // 粗い間隔から順に埋める(2のべき乗の間隔で半分ずつ細かくする)。
            {
                const int n = static_cast<int>(positions.size());
                std::vector<char> queued(static_cast<std::size_t>(n), 0);
                int step = 1;
                while (step < n) {
                    step *= 2;
                }
                for (; step >= 1; step /= 2) {
                    for (int i = 0; i < n; i += step) {
                        if (!queued[static_cast<std::size_t>(i)]) {
                            queued[static_cast<std::size_t>(i)] = 1;
                            order.push_back(i);
                        }
                    }
                }
            }
            {
                std::lock_guard<std::mutex> lock(mutex_);
                positions_ = positions;
                images_.assign(positions.size(), {});
                imageWidth_ = first.width;
                imageHeight_ = first.height;
                imageColor_ = first.color;
                imageAspect_ = first.pixelAspect;
                images_[0] = pack(first);
                bytes_ = images_[0].size() * sizeof(std::uint16_t);
            }
            if (notify_) {
                notify_();
            }
            for (int position : order) {
                if (position == 0) {
                    continue;
                }
                if (waitWhilePaused(*source)) {
                    break;
                }
                Frame frame;
                if (!decode(positions[static_cast<std::size_t>(position)], frame) || frame.width != first.width ||
                    frame.height != first.height) {
                    continue;  // 読めないキーフレームは飛ばす(近くの画像で代わりに仮表示される)。
                }
                std::vector<std::uint16_t> image = pack(frame);
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    bytes_ += image.size() * sizeof(std::uint16_t);
                    images_[static_cast<std::size_t>(position)] = std::move(image);
                }
                if (notify_) {
                    notify_();
                }
            }
        }
    }

    // 作り終えたらデコーダーを閉じ、GPUのメモリを返す(画像は持ち続ける)。
    source.reset();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        finished_ = true;
    }
    if (SUCCEEDED(comResult)) {
        CoUninitialize();
    }
}

}  // namespace frameplayer
