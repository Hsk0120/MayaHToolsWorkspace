/**
 * @file ImageSequenceSource.cpp
 * @brief 連番画像の読み込み元の実装。
 */
#include "core/ImageSequenceSource.h"

#include <ppl.h>

#include <windows.h>
#include <objbase.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cwchar>
#include <cwctype>
#include <thread>

#include "core/Clip.h"
#include "core/ExrReader.h"
#include "core/TraceLog.h"

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

/**
 * @brief 文字列を小文字にする。
 * @param text 文字列。
 * @return 小文字にしたもの。
 */
std::wstring lower(std::wstring text) {
    std::transform(text.begin(), text.end(), text.begin(), [](wchar_t c) { return static_cast<wchar_t>(std::towlower(c)); });
    return text;
}

/**
 * @brief 拡張子(小文字、点なし)を返す。
 * @param path パス。
 * @return 拡張子。無ければ空。
 */
std::wstring extensionOf(const std::wstring& path) {
    const std::size_t slash = path.find_last_of(L"\\/");
    const std::size_t dot = path.find_last_of(L'.');
    if (dot == std::wstring::npos || (slash != std::wstring::npos && dot < slash)) {
        return std::wstring();
    }
    return lower(path.substr(dot + 1));
}

/**
 * @brief sRGBの値をリニアな値にする/リニアな値をsRGBの値にする(縮小画像用)。
 * @param v リニアな値。
 * @return sRGBの値(0〜1に切る)。
 */
float linearToSrgb(float v) {
    v = std::clamp(v, 0.0f, 1.0f);
    return v <= 0.0031308f ? v * 12.92f : 1.055f * std::pow(v, 1.0f / 2.4f) - 0.055f;
}

/**
 * @brief 1画素64bitのRGBAの画像を、幅maxWidthまで面積の平均で縮める。
 * @param frame 縮める画像(書き換える)。
 * @param maxWidth 最大幅。
 */
void shrinkRgba64(Frame& frame, int maxWidth) {
    if (maxWidth <= 0 || frame.width <= maxWidth) {
        return;
    }
    const int width = maxWidth;
    const int height = std::max(1, static_cast<int>(static_cast<long long>(frame.height) * width / frame.width));
    const bool half = frame.layout == PixelLayout::RgbaHalf;
    const auto* source = reinterpret_cast<const std::uint16_t*>(frame.planes.data());
    std::vector<std::uint8_t> result(static_cast<std::size_t>(width) * height * 8);
    auto* target = reinterpret_cast<std::uint16_t*>(result.data());
    // 半精度から32bit浮動小数点への変換は表で引く(片付けない。終了の途中の裏の作業でも使えるように)。
    static const float* const toFloat = [] {
        auto* table = new float[65536];
        for (int bits = 0; bits < 65536; ++bits) {
            table[bits] = halfToFloat(static_cast<std::uint16_t>(bits));
        }
        return table;
    }();
    // 行ごとに並行して縮める(4Kの画像を1つのコアで縮めると、デコードより時間がかかるため)。
    concurrency::parallel_for(0, height, [&](int y) {
        const int y0 = static_cast<int>(static_cast<long long>(y) * frame.height / height);
        const int y1 = std::max(y0 + 1, static_cast<int>(static_cast<long long>(y + 1) * frame.height / height));
        for (int x = 0; x < width; ++x) {
            const int x0 = static_cast<int>(static_cast<long long>(x) * frame.width / width);
            const int x1 = std::max(x0 + 1, static_cast<int>(static_cast<long long>(x + 1) * frame.width / width));
            double sum[4] = {};
            for (int sy = y0; sy < y1; ++sy) {
                for (int sx = x0; sx < x1; ++sx) {
                    const std::uint16_t* p = source + (static_cast<std::size_t>(sy) * frame.width + sx) * 4;
                    for (int c = 0; c < 4; ++c) {
                        sum[c] += half ? toFloat[p[c]] : p[c];
                    }
                }
            }
            const double count = static_cast<double>(x1 - x0) * (y1 - y0);
            std::uint16_t* o = target + (static_cast<std::size_t>(y) * width + x) * 4;
            for (int c = 0; c < 4; ++c) {
                const double v = sum[c] / count;
                o[c] = half ? floatToHalf(static_cast<float>(v)) : static_cast<std::uint16_t>(v + 0.5);
            }
        }
    });
    frame.planes = std::move(result);
    frame.width = width;
    frame.height = height;
}

}  // namespace

void convertToBgra8(Frame& frame) {
    if (!frame.isRgba64()) {
        return;
    }
    const bool half = frame.layout == PixelLayout::RgbaHalf;
    const auto* source = reinterpret_cast<const std::uint16_t*>(frame.planes.data());
    frame.pixels.resize(static_cast<std::size_t>(frame.width) * frame.height);
    for (std::size_t i = 0; i < frame.pixels.size(); ++i) {
        const std::uint16_t* p = source + i * 4;
        std::uint32_t bytes[3];
        for (int c = 0; c < 3; ++c) {
            const float v = half ? linearToSrgb(halfToFloat(p[c])) : p[c] / 65535.0f;
            bytes[c] = static_cast<std::uint32_t>(std::clamp(v, 0.0f, 1.0f) * 255.0f + 0.5f);
        }
        frame.pixels[i] = 0xFF000000u | (bytes[0] << 16) | (bytes[1] << 8) | bytes[2];
    }
    frame.planes.clear();
    frame.layout = PixelLayout::Bgra8;
    if (half) {
        frame.color.transfer = TransferFunction::Sdr;  // sRGBの値にしたので、描画ではそのまま出す。
    }
}

namespace {

/**
 * @brief WICで画像を読む。
 * @param path パス。
 * @param result 格納先。
 * @return 読めたらtrue。
 */
bool decodeWic(const std::wstring& path, ImageSequenceSource::Decoded& result) {
    ComPtr<IWICImagingFactory> factory;
    ComPtr<IWICBitmapDecoder> decoder;
    ComPtr<IWICBitmapFrameDecode> source;
    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
    if (SUCCEEDED(hr)) {
        hr = factory->CreateDecoderFromFilename(path.c_str(), nullptr, GENERIC_READ, WICDecodeMetadataCacheOnDemand,
                                                &decoder);
    }
    if (SUCCEEDED(hr)) {
        hr = decoder->GetFrame(0, &source);
    }
    UINT width = 0;
    UINT height = 0;
    if (SUCCEEDED(hr)) {
        hr = source->GetSize(&width, &height);
    }
    if (FAILED(hr) || width == 0 || height == 0) {
        result.error = L"Cannot read the image (Windows may not support this format)";
        return false;
    }
    // 元の形式のビット数と値の種類から、受け取る形式を決める(8bitを超える値は8bitに落とさない)。
    WICPixelFormatGUID format{};
    source->GetPixelFormat(&format);
    UINT bitsPerPixel = 0;
    UINT channels = 0;
    WICPixelFormatNumericRepresentation numeric = WICPixelFormatNumericRepresentationUnspecified;
    ComPtr<IWICComponentInfo> info;
    ComPtr<IWICPixelFormatInfo2> formatInfo;
    if (SUCCEEDED(factory->CreateComponentInfo(format, &info)) && SUCCEEDED(info.As(&formatInfo))) {
        formatInfo->GetBitsPerPixel(&bitsPerPixel);
        formatInfo->GetChannelCount(&channels);
        formatInfo->GetNumericRepresentation(&numeric);
    }
    const bool floating = numeric == WICPixelFormatNumericRepresentationFloat ||
                          numeric == WICPixelFormatNumericRepresentationFixed;
    const bool deep = channels > 0 && bitsPerPixel / channels > 8;
    Frame& frame = result.frame;
    frame.width = static_cast<int>(width);
    frame.height = static_cast<int>(height);
    frame.color = ColorInfo{};
    frame.color.rgb = true;
    frame.color.range = ColorRange::Full;
    frame.color.primariesSource = ColorSource::Guess;  // 画像はsRGB(BT.709)とみなす。
    frame.color.transferSource = ColorSource::Guess;
    WICPixelFormatGUID target = GUID_WICPixelFormat32bppBGRA;
    UINT bytesPerPixel = 4;
    if (floating) {
        // WICの浮動小数点の形式はリニア(scRGB)。
        target = GUID_WICPixelFormat64bppRGBAHalf;
        bytesPerPixel = 8;
        frame.layout = PixelLayout::RgbaHalf;
        frame.color.transfer = TransferFunction::Linear;
        frame.color.bitDepth = 16;
    } else if (deep) {
        target = GUID_WICPixelFormat64bppRGBA;
        bytesPerPixel = 8;
        frame.layout = PixelLayout::Rgba16;
        frame.color.bitDepth = 16;
    } else {
        frame.layout = PixelLayout::Bgra8;
        frame.color.bitDepth = 8;
    }
    ComPtr<IWICFormatConverter> converter;
    hr = factory->CreateFormatConverter(&converter);
    if (SUCCEEDED(hr)) {
        hr = converter->Initialize(source.Get(), target, WICBitmapDitherTypeNone, nullptr, 0.0,
                                   WICBitmapPaletteTypeCustom);
    }
    const UINT stride = width * bytesPerPixel;
    const std::size_t size = static_cast<std::size_t>(stride) * height;
    if (SUCCEEDED(hr)) {
        if (frame.layout == PixelLayout::Bgra8) {
            frame.pixels.resize(static_cast<std::size_t>(width) * height);
            hr = converter->CopyPixels(nullptr, stride, static_cast<UINT>(size), reinterpret_cast<BYTE*>(frame.pixels.data()));
        } else {
            frame.planes.resize(size);
            hr = converter->CopyPixels(nullptr, stride, static_cast<UINT>(size), frame.planes.data());
        }
    }
    if (FAILED(hr)) {
        result.error = L"Cannot read the image pixels";
        return false;
    }
    // 形式の名前(説明の表示用)。
    GUID container{};
    decoder->GetContainerFormat(&container);
    ComPtr<IWICBitmapDecoderInfo> decoderInfo;
    wchar_t name[64] = {};
    UINT nameLength = 0;
    if (SUCCEEDED(decoder->GetDecoderInfo(&decoderInfo))) {
        decoderInfo->GetFriendlyName(64, name, &nameLength);
    }
    result.format = std::wstring(name) + L" " +
                    (floating ? L"float" : std::to_wstring(channels ? bitsPerPixel / channels : 8) + L"bit");
    return true;
}

/**
 * @brief パスの番号の部分を見つける(ファイル名の拡張子より前で、最も後ろの数字の並び)。
 * @param name ファイル名。
 * @param start 数字の始まりの格納先。
 * @param length 数字の長さの格納先。
 * @return 見つかればtrue。
 */
bool findNumber(const std::wstring& name, std::size_t& start, std::size_t& length) {
    std::size_t end = name.find_last_of(L'.');
    if (end == std::wstring::npos) {
        end = name.size();
    }
    std::size_t i = end;
    while (i > 0 && !std::iswdigit(name[i - 1])) {
        --i;
    }
    if (i == 0) {
        return false;
    }
    const std::size_t last = i;
    while (i > 0 && std::iswdigit(name[i - 1])) {
        --i;
    }
    start = i;
    length = last - i;
    return length > 0 && length <= 9;
}

}  // namespace

ImageSequenceSource::Decoded decodeImageFile(const std::wstring& path, int maxWidth, bool bgra,
                                             const std::atomic<bool>* cancel) {
    // 作業スレッドからも呼ぶので、そのスレッドでCOMを初期化しておく(WICはCOMの部品。解除はしない)。
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    ImageSequenceSource::Decoded result;
    if (extensionOf(path) == L"exr") {
        ExrImage image;
        if (!readExr(path, image, result.error, cancel)) {
            return result;
        }
        Frame& frame = result.frame;
        frame.width = image.width;
        frame.height = image.height;
        frame.layout = PixelLayout::RgbaHalf;
        frame.planes.resize(image.pixels.size() * 2);
        std::memcpy(frame.planes.data(), image.pixels.data(), frame.planes.size());
        frame.pixelAspect = image.pixelAspect;
        frame.color = ColorInfo{};
        frame.color.rgb = true;
        frame.color.range = ColorRange::Full;
        frame.color.transfer = TransferFunction::Linear;  // EXRはシーンのリニアな値。
        frame.color.transferSource = ColorSource::File;
        frame.color.primaries = image.primaries;
        frame.color.primariesSource = image.primariesFromFile ? ColorSource::File : ColorSource::Guess;
        frame.color.bitDepth = 16;
        result.format = L"OpenEXR half";
    } else if (!decodeWic(path, result)) {
        return result;
    }
    if (result.frame.layout == PixelLayout::Bgra8) {
        if (maxWidth > 0 && result.frame.width > maxWidth) {
            result.frame = shrinkToWidth(result.frame, maxWidth);
        }
    } else {
        shrinkRgba64(result.frame, maxWidth);
        if (bgra) {
            convertToBgra8(result.frame);
        }
    }
    return result;
}

std::unique_ptr<ImageSequenceSource> ImageSequenceSource::open(const std::wstring& path, double frameRate,
                                                               int maxWidth, std::wstring& error,
                                                               SourcePurpose purpose) {
    std::unique_ptr<ImageSequenceSource> source(new ImageSequenceSource());
    source->frameRate_ = frameRate > 0.0 ? frameRate : kDefaultFrameRate;
    source->maxWidth_ = maxWidth;
    source->purpose_ = purpose;
    const unsigned cores = std::max(1u, std::thread::hardware_concurrency());
    source->depth_ = purpose == SourcePurpose::Thumbnails ? 1 : static_cast<int>(std::clamp(cores / 2, 2u, 8u));

    const std::size_t slash = path.find_last_of(L"\\/");
    const std::wstring directory = slash == std::wstring::npos ? std::wstring() : path.substr(0, slash + 1);
    const std::wstring name = slash == std::wstring::npos ? path : path.substr(slash + 1);
    std::size_t start = 0;
    std::size_t length = 0;
    if (findNumber(name, start, length)) {
        // 同じフォルダで、番号の前後が同じファイルを集める(番号の桁数は問わない)。
        const std::wstring prefix = name.substr(0, start);
        const std::wstring suffix = name.substr(start + length);
        std::map<int, std::wstring> numbered;
        WIN32_FIND_DATAW found{};
        HANDLE find = FindFirstFileExW((directory + prefix + L"*" + suffix).c_str(), FindExInfoBasic, &found,
                                       FindExSearchNameMatch, nullptr, FIND_FIRST_EX_LARGE_FETCH);
        if (find != INVALID_HANDLE_VALUE) {
            do {
                if (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                    continue;
                }
                const std::wstring candidate = found.cFileName;
                if (candidate.size() <= prefix.size() + suffix.size() ||
                    _wcsnicmp(candidate.c_str(), prefix.c_str(), prefix.size()) != 0 ||
                    _wcsicmp(candidate.c_str() + candidate.size() - suffix.size(), suffix.c_str()) != 0) {
                    continue;
                }
                const std::wstring digits = candidate.substr(prefix.size(), candidate.size() - prefix.size() - suffix.size());
                if (digits.empty() || digits.size() > 9 ||
                    !std::all_of(digits.begin(), digits.end(), [](wchar_t c) { return std::iswdigit(c) != 0; })) {
                    continue;
                }
                numbered.emplace(std::stoi(digits), directory + candidate);
            } while (FindNextFileW(find, &found));
            FindClose(find);
        }
        if (!numbered.empty()) {
            source->numbered_ = true;
            source->first_ = numbered.begin()->first;
            const int last = numbered.rbegin()->first;
            source->files_.resize(static_cast<std::size_t>(last - source->first_) + 1);
            for (auto& [number, file] : numbered) {
                source->files_[static_cast<std::size_t>(number - source->first_)] = std::move(file);
            }
            source->missing_ = static_cast<int>(source->files_.size() - numbered.size());
        }
    }
    if (source->files_.empty()) {
        source->files_.push_back(path);  // 番号の無い画像は1枚だけ。
    }

    // 最初のファイルを試しに読み、読めない形式なら開かない。
    const std::wstring& firstFile = *std::find_if(source->files_.begin(), source->files_.end(),
                                                  [](const std::wstring& f) { return !f.empty(); });
    Decoded probe = decodeImageFile(firstFile, maxWidth, purpose == SourcePurpose::Thumbnails);
    if (!probe.error.empty()) {
        error = probe.error;
        return nullptr;
    }
    source->format_ = probe.format;
    traceLog("open image sequence frames=%d missing=%d", source->frameCount(), source->missing_);
    return source;
}

long long ImageSequenceSource::frameTime(int index) const {
    return std::llround(index * 10000000.0 / frameRate_);
}

ImageSequenceSource::~ImageSequenceSource() {
    // 裏のデコードが読み込み元より長く生きないよう、終わるまで待つ
    // (プログラムの終了時に、デコードが使う表などが先に片付けられるのを防ぐ)。
    releaseDecoder();
    for (auto& task : retired_) {
        task.wait();
    }
}

void ImageSequenceSource::releaseDecoder() {
    for (auto& [index, pending] : pending_) {
        *pending.cancel = true;
        retire(std::move(pending.task));
    }
    pending_.clear();
}

void ImageSequenceSource::retire(concurrency::task<std::shared_ptr<Decoded>> task) {
    retired_.erase(std::remove_if(retired_.begin(), retired_.end(), [](const auto& t) { return t.is_done(); }),
                   retired_.end());
    retired_.push_back(std::move(task));
}

bool ImageSequenceSource::isMissing(int index) const {
    return index >= 0 && index < frameCount() && files_[static_cast<std::size_t>(index)].empty();
}

bool ImageSequenceSource::seekToKeyFrame(int keyIndex) {
    error_.clear();
    const int target = std::clamp(keyIndex, 0, frameCount() - 1);
    if (target != next_) {
        // 飛んだ直後は、表示するコマを先に仕上げるため先読みを止める(ほかのコマとCPUを取り合わないように)。
        ramp_ = 1;
    }
    next_ = target;
    // 新しい位置から遠い先読みは捨てる(打ち切れる形式は打ち切り、ほかは最後まで走るが結果は使わない)。
    for (auto it = pending_.begin(); it != pending_.end();) {
        if (it->first < next_ || it->first >= next_ + depth_ * 2) {
            *it->second.cancel = true;
            retire(std::move(it->second.task));
            it = pending_.erase(it);
        } else {
            ++it;
        }
    }
    return true;
}

void ImageSequenceSource::schedule(int index) {
    int scheduled = 0;
    for (int i = index; i < frameCount() && scheduled < ramp_; ++i) {
        if (files_[static_cast<std::size_t>(i)].empty()) {
            continue;
        }
        ++scheduled;
        if (pending_.count(i)) {
            continue;
        }
        const std::wstring file = files_[static_cast<std::size_t>(i)];
        const int maxWidth = maxWidth_;
        const bool bgra = purpose_ == SourcePurpose::Thumbnails;
        auto cancel = std::make_shared<std::atomic<bool>>(false);
        Pending pending{concurrency::create_task([file, maxWidth, bgra, cancel] {
                            if (*cancel) {
                                return std::make_shared<Decoded>();  // 始まる前に捨てられた。
                            }
                            return std::make_shared<Decoded>(decodeImageFile(file, maxWidth, bgra, cancel.get()));
                        }),
                        cancel};
        pending_.emplace(i, std::move(pending));
    }
}

bool ImageSequenceSource::readNext(Frame& out, int& index) {
    error_.clear();
    // 欠けているコマは飛ばす(呼び出し元は番号が飛んだことで欠けを知る)。
    while (next_ < frameCount() && files_[static_cast<std::size_t>(next_)].empty()) {
        ++next_;
    }
    if (next_ >= frameCount()) {
        return false;
    }
    schedule(next_);
    index = next_;
    auto it = pending_.find(index);
    const std::shared_ptr<Decoded> decoded = it->second.task.get();  // デコードが終わっていなければ待つ。
    pending_.erase(it);
    ++next_;
    if (!decoded->error.empty()) {
        error_ = files_[static_cast<std::size_t>(index)] + L": " + decoded->error;
        return false;
    }
    out = std::move(decoded->frame);
    ramp_ = std::min(depth_, ramp_ * 2);  // 順に読み進めているので、先読みを増やす。
    schedule(next_);  // 次のコマの先読みを続ける。
    return true;
}

std::wstring ImageSequenceSource::description() const {
    wchar_t text[256];
    const int images = frameCount() - missing_;
    std::swprintf(text, 256, L"Image sequence: %d %ls (%d missing) / %ls / %.4g fps", images,
                  images == 1 ? L"image" : L"images", missing_, format_.c_str(), frameRate_);
    return text;
}

}  // namespace frameplayer
