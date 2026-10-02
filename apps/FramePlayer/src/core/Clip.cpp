/**
 * @file Clip.cpp
 * @brief 上限付きキャッシュと裏での先読みの実装、および画像の縮小。
 */
#include "core/Clip.h"

#include <windows.h>
#include <objbase.h>

#include <algorithm>
#include <chrono>
#include <new>

#include <ppl.h>

namespace frameplayer {


namespace {

/**
 * @brief キャッシュしたコマが使うバイト数を返す。
 * @param frame 対象のコマ。
 * @return 画素データのバイト数。
 */
std::size_t bytesOf(const Frame& frame) {
    return frame.pixels.size() * sizeof(std::uint32_t);
}

/**
 * @brief デコードしたコマを、キャッシュ用の大きさにする。
 * @param decoded デコードしたコマ。縮小不要ならそのまま移す。
 * @param maxWidth 最大幅。
 * @return キャッシュに入れるコマ。
 */
std::shared_ptr<const Frame> makeCached(Frame&& decoded, int maxWidth) {
    if (maxWidth <= 0 || decoded.width <= maxWidth) {
        return std::make_shared<const Frame>(std::move(decoded));
    }
    return std::make_shared<const Frame>(shrinkToWidth(decoded, maxWidth));
}

}  // namespace

Clip::~Clip() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stop_ = true;
    }
    wake_.notify_all();
    if (worker_.joinable()) {
        worker_.join();
    }
}

bool Clip::open(const std::wstring& path, int maxWidth, std::size_t cacheBytes, NotifyCallback notify,
                std::wstring& error) {
    source_ = openFrameSource(path, maxWidth, error);
    if (!source_) {
        return false;
    }
    path_ = path;
    frameCount_ = source_->frameCount();
    frameRate_ = source_->frameRate();
    description_ = source_->description();
    maxWidth_ = maxWidth;
    cacheBytes_ = cacheBytes;
    notify_ = std::move(notify);
    frames_.assign(static_cast<std::size_t>(frameCount_), nullptr);
    broken_.assign(static_cast<std::size_t>(frameCount_), 0);

    // 先頭のコマをここで読み、1コマの大きさ(キャッシュに入るコマ数の計算に使う)を確定する。
    Frame decoded;
    int index = -1;
    try {
        if (!source_->readNext(decoded, index)) {
            error = source_->error().empty() ? L"コマを読み込めません" : source_->error();
            return false;
        }
        std::shared_ptr<const Frame> first = makeCached(std::move(decoded), maxWidth_);
        frameBytes_ = std::max<std::size_t>(1, bytesOf(*first));
        std::vector<std::shared_ptr<const Frame>> released;
        std::lock_guard<std::mutex> lock(mutex_);
        storeLocked(index, std::move(first), released);
    } catch (const std::bad_alloc&) {
        error = L"メモリが足りません";
        return false;
    }
    firstDecodedNext_ = index + 1;

    worker_ = std::thread(&Clip::workerLoop, this);
    return true;
}

std::shared_ptr<const Frame> Clip::frame(int index) const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (index < 0 || index >= frameCount_) {
        return nullptr;
    }
    return frames_[static_cast<std::size_t>(index)];
}

std::shared_ptr<const Frame> Clip::waitForFrame(int index, Direction direction, int timeoutMs) {
    if (index < 0 || index >= frameCount_) {
        return nullptr;
    }
    std::unique_lock<std::mutex> lock(mutex_);
    playhead_ = index;
    direction_ = direction;
    wake_.notify_one();
    const std::size_t i = static_cast<std::size_t>(index);
    frameStored_.wait_for(lock, std::chrono::milliseconds(timeoutMs),
                          [&] { return frames_[i] || broken_[i] || stop_; });
    return frames_[i];
}

void Clip::setPlayhead(int index, Direction direction, bool wrap) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        playhead_ = std::clamp(index, 0, std::max(0, frameCount_ - 1));
        direction_ = direction;
        wrap_ = wrap;
    }
    wake_.notify_one();
}

void Clip::cachedFlags(std::vector<std::uint8_t>& flags) const {
    std::lock_guard<std::mutex> lock(mutex_);
    flags.resize(frames_.size());
    for (std::size_t i = 0; i < frames_.size(); ++i) {
        flags[i] = frames_[i] ? 1 : 0;
    }
}

bool Clip::isBroken(int index) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return index >= 0 && index < frameCount_ && broken_[static_cast<std::size_t>(index)] != 0;
}

std::wstring Clip::description() const {
    return description_;
}

std::wstring Clip::error() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return error_;
}

int Clip::offsetIndexLocked(int offset) const {
    const int sign = direction_ == Direction::Forward ? 1 : -1;
    long long index = static_cast<long long>(playhead_) + static_cast<long long>(sign) * offset;
    if (wrap_) {
        index %= frameCount_;
        if (index < 0) {
            index += frameCount_;
        }
        return static_cast<int>(index);
    }
    return (index < 0 || index >= frameCount_) ? -1 : static_cast<int>(index);
}

int Clip::findTargetLocked() const {
    // キャッシュに入るコマ数から、向きの先(ahead)と反対側(behind)の先読み範囲を決める。
    // behindをaheadの1/3以下にしておくと、distanceCostLocked()で範囲外のコマが必ず範囲内より遠くなり、
    // 範囲内のコマを入れるために範囲内のコマを捨てる(読み直しを繰り返す)ことが起きない。
    const long long capacity = std::max<long long>(1, static_cast<long long>(cacheBytes_ / frameBytes_));
    int ahead = 0;
    int behind = 0;
    if (capacity >= frameCount_) {
        ahead = frameCount_ - 1;  // 全コマが入るなら全体を読む。
        behind = frameCount_ - 1;
    } else {
        ahead = static_cast<int>((capacity - 1) * 3 / 4);
        behind = ahead / 3;
    }
    if (wrap_) {
        behind = std::min(behind, frameCount_ - 1 - ahead);
    }

    auto missing = [&](int index) {
        return index >= 0 && !frames_[static_cast<std::size_t>(index)] && !broken_[static_cast<std::size_t>(index)];
    };
    for (int offset = 0; offset <= ahead; ++offset) {
        const int index = offsetIndexLocked(offset);
        if (index < 0) {
            break;
        }
        if (missing(index)) {
            return index;
        }
    }
    for (int offset = 1; offset <= behind; ++offset) {
        const int index = offsetIndexLocked(-offset);
        if (index < 0) {
            break;
        }
        if (missing(index)) {
            return index;
        }
    }
    return -1;
}

long long Clip::distanceCostLocked(int index) const {
    const long long sign = direction_ == Direction::Forward ? 1 : -1;
    const long long offset = sign * (static_cast<long long>(index) - playhead_);
    if (wrap_) {
        // ループ時は、先に回り込んで届く距離と、後ろにある距離の近い方で測る。
        long long forward = offset % frameCount_;
        if (forward < 0) {
            forward += frameCount_;
        }
        return std::min(forward, 3 * (frameCount_ - forward));
    }
    return offset >= 0 ? offset : -3 * offset;
}

void Clip::storeLocked(int index, std::shared_ptr<const Frame> frame,
                       std::vector<std::shared_ptr<const Frame>>& released) {
    if (index < 0 || index >= frameCount_) {
        released.push_back(std::move(frame));
        return;
    }
    auto& slot = frames_[static_cast<std::size_t>(index)];
    if (slot) {
        released.push_back(std::move(frame));
        return;
    }
    cachedBytes_ += bytesOf(*frame);
    slot = std::move(frame);
    broken_[static_cast<std::size_t>(index)] = 0;
    cachedIndices_.push_back(index);

    // 上限を超えたら、再生ヘッドから最も遠いコマから捨てる(再生ヘッドのコマは捨てない)。
    // 全コマ(1時間60fpsなら21万6千)ではなく、キャッシュにあるコマ(千数百)だけを調べる。
    while (cachedBytes_ > cacheBytes_) {
        std::size_t victimPosition = cachedIndices_.size();
        long long victimCost = -1;
        for (std::size_t position = 0; position < cachedIndices_.size(); ++position) {
            const int i = cachedIndices_[position];
            if (i == playhead_) {
                continue;
            }
            const long long cost = distanceCostLocked(i);
            if (cost > victimCost) {
                victimPosition = position;
                victimCost = cost;
            }
        }
        if (victimPosition == cachedIndices_.size()) {
            break;
        }
        const int victim = cachedIndices_[victimPosition];
        cachedIndices_[victimPosition] = cachedIndices_.back();
        cachedIndices_.pop_back();
        cachedBytes_ -= bytesOf(*frames_[static_cast<std::size_t>(victim)]);
        // 解放(数MBのメモリを返す処理)はロックの外で行うよう、呼び出し元へ渡す。
        released.push_back(std::move(frames_[static_cast<std::size_t>(victim)]));
    }
}

void Clip::workerLoop() {
    // Media Foundationの呼び出しにCOMが必要なので、このスレッドでも初期化する。
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);

    // デコーダーが次に返すコマ番号。続けて読めば得られる位置を覚えておき、無駄なシークを避ける。-1は不明。
    int next = firstDecodedNext_;
    for (;;) {
        int target = -1;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            wake_.wait(lock, [&] { return stop_ || (target = findTargetLocked()) >= 0; });
            if (stop_) {
                break;
            }
        }

        // 続けて読んでいる位置がキーフレームと目標の間なら、シークせずに読み進める方が速い。
        const int key = source_->keyFrameAtOrBefore(target);
        if (next < key || next > target) {
            if (!source_->seekToKeyFrame(key)) {
                std::lock_guard<std::mutex> lock(mutex_);
                error_ = source_->error();
                broken_[static_cast<std::size_t>(target)] = 1;
                next = -1;
                continue;
            }
            next = key;
        }

        // 目標に届くまで順にデコードし、途中のコマもキャッシュに入れる。
        // 1コマごとに目標を選び直し、再生ヘッドが大きく動いてシークした方が速くなったら切り上げる。
        for (;;) {
            Frame decoded;
            int index = -1;
            bool ok = false;
            try {
                ok = source_->readNext(decoded, index);
            } catch (const std::bad_alloc&) {
                ok = false;
            }
            if (!ok) {
                std::lock_guard<std::mutex> lock(mutex_);
                if (!source_->error().empty()) {
                    error_ = source_->error();
                }
                // 終端または失敗で目標に届かなかった。同じコマを繰り返し試さないよう印を付ける。
                if (!frames_[static_cast<std::size_t>(target)]) {
                    broken_[static_cast<std::size_t>(target)] = 1;
                }
                next = -1;
                break;
            }
            next = index + 1;

            std::shared_ptr<const Frame> cached;
            try {
                cached = makeCached(std::move(decoded), maxWidth_);
            } catch (const std::bad_alloc&) {
                std::lock_guard<std::mutex> lock(mutex_);
                error_ = L"メモリが足りません。キャッシュの上限を小さくしてください";
                broken_[static_cast<std::size_t>(target)] = 1;
                break;
            }

            int nextTarget = -1;
            // 捨てたコマはロックを外してから解放する。ロック中に解放すると、描画側が数ms待たされる。
            std::vector<std::shared_ptr<const Frame>> released;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                storeLocked(index, std::move(cached), released);
                // 目標を通り過ぎても目標が得られなかった(目次と照合できなかった)場合。
                if (index > target && !frames_[static_cast<std::size_t>(target)]) {
                    broken_[static_cast<std::size_t>(target)] = 1;
                }
                nextTarget = stop_ ? -1 : findTargetLocked();
            }
            released.clear();
            frameStored_.notify_all();
            if (notify_) {
                notify_();
            }

            if (nextTarget < 0 || nextTarget < next || source_->keyFrameAtOrBefore(nextTarget) > next) {
                break;  // 先読みの必要が無い、またはシークした方が速い。
            }
            target = nextTarget;
        }
    }

    if (SUCCEEDED(comResult)) {
        CoUninitialize();
    }
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
