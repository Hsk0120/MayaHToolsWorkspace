/**
 * @file MediaFoundationSource.cpp
 * @brief Media Foundationで動画を読む処理の実装。
 */
#include "core/MediaFoundationSource.h"

#include <mfapi.h>
#include <mferror.h>

#include <cstdio>
#include <cstring>

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

/// 読む対象のストリーム(最初の映像ストリーム)。
constexpr DWORD kVideoStream = static_cast<DWORD>(MF_SOURCE_READER_FIRST_VIDEO_STREAM);

}  // namespace

std::unique_ptr<MediaFoundationSource> MediaFoundationSource::open(const std::wstring& path,
                                                                   std::wstring& error) {
    std::unique_ptr<MediaFoundationSource> source(new MediaFoundationSource());

    // MFStartupは参照カウント式なので、読み込み元ごとに開始・終了してよい。
    HRESULT hr = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    if (FAILED(hr)) {
        source->setError(L"Media Foundationを開始できません", hr);
        error = source->error_;
        return nullptr;
    }
    source->started_ = true;

    // 映像処理を有効にすると、Source ReaderがYUVからRGB32への変換まで行う。
    // ADVANCEDの方がVideo Processor MFTを使うため、通常版より大幅に速い(1080pで約3倍を確認)。
    ComPtr<IMFAttributes> attributes;
    hr = MFCreateAttributes(&attributes, 1);
    if (SUCCEEDED(hr)) {
        hr = attributes->SetUINT32(MF_SOURCE_READER_ENABLE_ADVANCED_VIDEO_PROCESSING, TRUE);
    }
    if (SUCCEEDED(hr)) {
        hr = MFCreateSourceReaderFromURL(path.c_str(), attributes.Get(), &source->reader_);
    }
    if (FAILED(hr)) {
        source->setError(L"動画ファイルを開けません(Windowsが対応していない形式の可能性があります)", hr);
        error = source->error_;
        return nullptr;
    }

    // 音声などは読まない。映像だけを選択する。
    source->reader_->SetStreamSelection(static_cast<DWORD>(MF_SOURCE_READER_ALL_STREAMS), FALSE);
    hr = source->reader_->SetStreamSelection(kVideoStream, TRUE);
    if (FAILED(hr)) {
        source->setError(L"映像ストリームがありません", hr);
        error = source->error_;
        return nullptr;
    }

    // フレームレートは変換前の形式から取る(変換後の形式には無いことがある)。
    ComPtr<IMFMediaType> nativeType;
    if (SUCCEEDED(source->reader_->GetNativeMediaType(kVideoStream, 0, &nativeType))) {
        UINT32 numerator = 0;
        UINT32 denominator = 0;
        if (SUCCEEDED(MFGetAttributeRatio(nativeType.Get(), MF_MT_FRAME_RATE, &numerator, &denominator)) &&
            denominator != 0) {
            source->frameRate_ = static_cast<double>(numerator) / denominator;
        }
    }

    ComPtr<IMFMediaType> outputType;
    hr = MFCreateMediaType(&outputType);
    if (SUCCEEDED(hr)) {
        hr = outputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
    }
    if (SUCCEEDED(hr)) {
        hr = outputType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_RGB32);
    }
    if (SUCCEEDED(hr)) {
        hr = source->reader_->SetCurrentMediaType(kVideoStream, nullptr, outputType.Get());
    }
    if (FAILED(hr)) {
        source->setError(L"RGBへの変換を設定できません", hr);
        error = source->error_;
        return nullptr;
    }

    if (!source->updateFormat()) {
        error = source->error_;
        return nullptr;
    }
    return source;
}

MediaFoundationSource::~MediaFoundationSource() {
    reader_.Reset();  // MFShutdownより先に読み込み本体を解放する。
    if (started_) {
        MFShutdown();
    }
}

bool MediaFoundationSource::updateFormat() {
    ComPtr<IMFMediaType> type;
    HRESULT hr = reader_->GetCurrentMediaType(kVideoStream, &type);
    if (SUCCEEDED(hr)) {
        hr = MFGetAttributeSize(type.Get(), MF_MT_FRAME_SIZE, &bufferWidth_, &bufferHeight_);
    }
    if (FAILED(hr) || bufferWidth_ == 0 || bufferHeight_ == 0) {
        setError(L"映像の大きさを取得できません", FAILED(hr) ? hr : E_FAIL);
        return false;
    }

    // 行の間隔。属性が無ければ形式と幅から求める(負なら下の行から並ぶ)。
    UINT32 stride = 0;
    if (SUCCEEDED(type->GetUINT32(MF_MT_DEFAULT_STRIDE, &stride))) {
        defaultStride_ = static_cast<LONG>(stride);
    } else if (FAILED(MFGetStrideForBitmapInfoHeader(MFVideoFormat_RGB32.Data1, bufferWidth_, &defaultStride_))) {
        defaultStride_ = static_cast<LONG>(bufferWidth_ * 4);
    }

    // H.264の1080pは1088行で届くことがあるため、表示範囲の指定があれば切り出す。
    visible_ = {0, 0, static_cast<LONG>(bufferWidth_), static_cast<LONG>(bufferHeight_)};
    MFVideoArea area{};
    UINT32 blobSize = 0;
    if (SUCCEEDED(type->GetBlob(MF_MT_MINIMUM_DISPLAY_APERTURE, reinterpret_cast<UINT8*>(&area), sizeof(area),
                                &blobSize)) &&
        blobSize == sizeof(area)) {
        RECT r{area.OffsetX.value, area.OffsetY.value, area.OffsetX.value + area.Area.cx,
               area.OffsetY.value + area.Area.cy};
        if (r.left >= 0 && r.top >= 0 && r.right <= static_cast<LONG>(bufferWidth_) &&
            r.bottom <= static_cast<LONG>(bufferHeight_) && r.right > r.left && r.bottom > r.top) {
            visible_ = r;
        }
    }
    return true;
}

bool MediaFoundationSource::readNext(Frame& out) {
    error_.clear();
    for (;;) {
        DWORD flags = 0;
        LONGLONG timestamp = 0;
        ComPtr<IMFSample> sample;
        HRESULT hr = reader_->ReadSample(kVideoStream, 0, nullptr, &flags, &timestamp, &sample);
        if (FAILED(hr)) {
            setError(L"コマの読み込みに失敗しました", hr);
            return false;
        }
        if (flags & MF_SOURCE_READERF_ENDOFSTREAM) {
            return false;
        }
        if ((flags & MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED) && !updateFormat()) {
            return false;
        }
        if (!sample) {
            // 映像の途切れを示す通知(STREAMTICK)などはコマとして数えない。
            continue;
        }

        ComPtr<IMFMediaBuffer> buffer;
        hr = sample->ConvertToContiguousBuffer(&buffer);
        if (FAILED(hr)) {
            setError(L"コマのデータを取り出せません", hr);
            return false;
        }

        // 2Dバッファなら行の先頭と間隔を正しく返してくれる。そうでなければ形式の情報から求める。
        BYTE* scan0 = nullptr;
        LONG pitch = 0;
        ComPtr<IMF2DBuffer> buffer2d;
        BYTE* raw = nullptr;
        bool locked2d = SUCCEEDED(buffer.As(&buffer2d)) && SUCCEEDED(buffer2d->Lock2D(&scan0, &pitch));
        if (!locked2d) {
            DWORD maxLength = 0;
            DWORD currentLength = 0;
            hr = buffer->Lock(&raw, &maxLength, &currentLength);
            if (FAILED(hr)) {
                setError(L"コマのデータを読めません", hr);
                return false;
            }
            pitch = defaultStride_;
            scan0 = pitch < 0 ? raw + static_cast<LONGLONG>(-pitch) * (bufferHeight_ - 1) : raw;
        }

        out.width = visible_.right - visible_.left;
        out.height = visible_.bottom - visible_.top;
        out.pixels.resize(static_cast<size_t>(out.width) * out.height);
        for (int y = 0; y < out.height; ++y) {
            const BYTE* src = scan0 + static_cast<LONGLONG>(pitch) * (visible_.top + y) + visible_.left * 4;
            std::uint32_t* dst = out.pixels.data() + static_cast<size_t>(y) * out.width;
            std::memcpy(dst, src, static_cast<size_t>(out.width) * 4);
            // RGB32の4バイト目は未定義なので、不透明として埋める。
            for (int x = 0; x < out.width; ++x) {
                dst[x] |= 0xFF000000u;
            }
        }

        if (locked2d) {
            buffer2d->Unlock2D();
        } else {
            buffer->Unlock();
        }
        return true;
    }
}

void MediaFoundationSource::setError(const wchar_t* message, HRESULT hr) {
    wchar_t text[512];
    std::swprintf(text, 512, L"%ls (HRESULT 0x%08lX)", message, static_cast<unsigned long>(hr));
    error_ = text;
}

}  // namespace frameplayer
