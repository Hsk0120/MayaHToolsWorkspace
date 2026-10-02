/**
 * @file MediaFoundationSource.cpp
 * @brief Media Foundationで動画を読む処理の実装。
 */
#include "core/MediaFoundationSource.h"

#include <d3d11.h>
#include <mfapi.h>
#include <mferror.h>
#include <propvarutil.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <limits>
#include <utility>

#include "core/Mp4SampleTable.h"

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

/// 読む対象のストリーム(最初の映像ストリーム)。
constexpr DWORD kVideoStream = static_cast<DWORD>(MF_SOURCE_READER_FIRST_VIDEO_STREAM);

/// GPUのときに先読みしておくコマ数(デコードと主メモリへの写しを並行させる深さ)。
constexpr std::size_t kGpuPipelineDepth = 4;

/**
 * @brief 映像ストリームだけを読むように選択する。
 * @param reader 対象のSource Reader。
 * @return 成功ならS_OK。
 */
HRESULT selectVideoOnly(IMFSourceReader* reader) {
    reader->SetStreamSelection(static_cast<DWORD>(MF_SOURCE_READER_ALL_STREAMS), FALSE);
    return reader->SetStreamSelection(kVideoStream, TRUE);
}

}  // namespace

std::unique_ptr<MediaFoundationSource> MediaFoundationSource::open(const std::wstring& path, int maxWidth,
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

    if (!source->buildIndex(path)) {
        error = source->error_;
        return nullptr;
    }

    // まずGPUでのデコードを試し、先頭のコマを実際に読めたら採用する。
    // 使えない環境(GPUが無い・形式が非対応など)では、CPUでのデコードに切り替える。
    if (source->createReader(path, maxWidth, true)) {
        Frame probe;
        int probeIndex = -1;
        if (source->readNext(probe, probeIndex) && source->seekToKeyFrame(0)) {
            return source;
        }
    }
    source->clearPending();
    source->stagingPool_.clear();
    source->reader_.Reset();
    source->context_.Reset();
    source->manager_.Reset();
    source->device_.Reset();
    if (!source->createReader(path, maxWidth, false)) {
        error = source->error_;
        return nullptr;
    }
    return source;
}

bool MediaFoundationSource::createReader(const std::wstring& path, int maxWidth, bool useGpu) {
    error_.clear();
    reader_.Reset();
    usingGpu_ = false;

    ComPtr<IMFAttributes> attributes;
    HRESULT hr = MFCreateAttributes(&attributes, 3);
    if (FAILED(hr)) {
        setError(L"属性を作成できません", hr);
        return false;
    }
    // 映像処理を有効にすると、YUVからRGB32への変換まで行う。
    // ADVANCEDの方がVideo Processor MFTを使うため、通常版より大幅に速い(1080pで約3倍を確認)。
    attributes->SetUINT32(MF_SOURCE_READER_ENABLE_ADVANCED_VIDEO_PROCESSING, TRUE);
    if (useGpu) {
        // GPU(Direct3D 11)を渡すと、デコード・色変換・縮小をGPUで行う。結果はLock2Dで主メモリへ写す。
        // 読み込み本体はUIスレッドで作り裏のスレッドで使うので、デバイスを複数スレッド対応にしておく。
        static const D3D_FEATURE_LEVEL levels[] = {D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0,
                                                   D3D_FEATURE_LEVEL_10_1, D3D_FEATURE_LEVEL_10_0};
        hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
                               D3D11_CREATE_DEVICE_VIDEO_SUPPORT | D3D11_CREATE_DEVICE_BGRA_SUPPORT, levels,
                               static_cast<UINT>(std::size(levels)), D3D11_SDK_VERSION, &device_, nullptr, nullptr);
        ComPtr<ID3D10Multithread> multithread;
        if (SUCCEEDED(hr)) {
            hr = device_.As(&multithread);
        }
        if (SUCCEEDED(hr)) {
            multithread->SetMultithreadProtected(TRUE);
            UINT resetToken = 0;
            hr = MFCreateDXGIDeviceManager(&resetToken, &manager_);
            if (SUCCEEDED(hr)) {
                hr = manager_->ResetDevice(device_.Get(), resetToken);
            }
        }
        if (SUCCEEDED(hr)) {
            device_->GetImmediateContext(&context_);
            hr = attributes->SetUnknown(MF_SOURCE_READER_D3D_MANAGER, manager_.Get());
        }
        if (SUCCEEDED(hr)) {
            hr = attributes->SetUINT32(MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS, TRUE);
        }
        if (FAILED(hr)) {
            setError(L"GPUを使う準備ができません", hr);
            return false;
        }
    }

    hr = MFCreateSourceReaderFromURL(path.c_str(), attributes.Get(), &reader_);
    if (SUCCEEDED(hr)) {
        hr = selectVideoOnly(reader_.Get());
    }
    if (FAILED(hr)) {
        setError(L"動画ファイルを開けません", hr);
        return false;
    }

    // GPUのときは、表示範囲を縦横比を保ってmaxWidthに縮めた大きさで受け取る(縮小もGPUで行う)。
    UINT32 outputWidth = 0;
    UINT32 outputHeight = 0;
    ComPtr<IMFMediaType> nativeType;
    if (useGpu && maxWidth > 0 && SUCCEEDED(reader_->GetNativeMediaType(kVideoStream, 0, &nativeType))) {
        UINT32 width = 0;
        UINT32 height = 0;
        MFGetAttributeSize(nativeType.Get(), MF_MT_FRAME_SIZE, &width, &height);
        MFVideoArea area{};
        UINT32 blobSize = 0;
        if (SUCCEEDED(nativeType->GetBlob(MF_MT_MINIMUM_DISPLAY_APERTURE, reinterpret_cast<UINT8*>(&area),
                                          sizeof(area), &blobSize)) &&
            blobSize == sizeof(area) && area.Area.cx > 0 && area.Area.cy > 0) {
            width = static_cast<UINT32>(area.Area.cx);
            height = static_cast<UINT32>(area.Area.cy);
        }
        if (width > static_cast<UINT32>(maxWidth) && height > 0) {
            outputWidth = static_cast<UINT32>(maxWidth);
            outputHeight = std::max<UINT32>(2, (height * outputWidth / width + 1) & ~1u);  // 偶数に丸める。
        }
    }

    // RGB32(BGRX)を優先し、受け付けられなければARGB32(BGRA)を試す。どちらも並びは同じ。
    for (const GUID& subtype : {MFVideoFormat_RGB32, MFVideoFormat_ARGB32}) {
        ComPtr<IMFMediaType> outputType;
        hr = MFCreateMediaType(&outputType);
        if (SUCCEEDED(hr)) {
            hr = outputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        }
        if (SUCCEEDED(hr)) {
            hr = outputType->SetGUID(MF_MT_SUBTYPE, subtype);
        }
        if (SUCCEEDED(hr) && outputWidth > 0) {
            hr = MFSetAttributeSize(outputType.Get(), MF_MT_FRAME_SIZE, outputWidth, outputHeight);
        }
        if (SUCCEEDED(hr)) {
            hr = reader_->SetCurrentMediaType(kVideoStream, nullptr, outputType.Get());
        }
        if (SUCCEEDED(hr)) {
            break;
        }
    }
    if (FAILED(hr)) {
        setError(L"RGBへの変換を設定できません", hr);
        return false;
    }
    if (!updateFormat()) {
        return false;
    }
    usingGpu_ = useGpu;
    return true;
}

MediaFoundationSource::~MediaFoundationSource() {
    pending_.clear();  // MFShutdownより先に読み込み本体とGPUの資源を解放する。
    stagingPool_.clear();
    reader_.Reset();
    context_.Reset();
    manager_.Reset();
    device_.Reset();
    if (started_) {
        MFShutdown();
    }
}

bool MediaFoundationSource::buildIndex(const std::wstring& path) {
    // 出力形式を指定しないSource Readerは、圧縮されたままのコマを返す(デコードしないので速い)。
    ComPtr<IMFSourceReader> indexReader;
    HRESULT hr = MFCreateSourceReaderFromURL(path.c_str(), nullptr, &indexReader);
    if (SUCCEEDED(hr)) {
        hr = selectVideoOnly(indexReader.Get());
    }
    if (FAILED(hr)) {
        setError(L"動画ファイルを開けません(Windowsが対応していない形式の可能性があります)", hr);
        return false;
    }

    ComPtr<IMFMediaType> nativeType;
    if (SUCCEEDED(indexReader->GetNativeMediaType(kVideoStream, 0, &nativeType))) {
        UINT32 numerator = 0;
        UINT32 denominator = 0;
        if (SUCCEEDED(MFGetAttributeRatio(nativeType.Get(), MF_MT_FRAME_RATE, &numerator, &denominator)) &&
            denominator != 0) {
            frameRate_ = static_cast<double>(numerator) / denominator;
        }
    }

    // mp4/movなら、ファイル内の目次(サンプルテーブル)を直接読めば映像データを読まずに済む。
    // ただしMedia Foundationが返す時刻と食い違うと番号がずれるので、先頭の一部だけ実際に読んで照合する。
    Mp4SampleTable table;
    const bool haveTable = readMp4SampleTable(path, table);
    const std::size_t probeCount = haveTable ? std::min<std::size_t>(table.presentationTimes.size(), 240) : 0;

    // 圧縮されたコマはデコード順に届く。表示時刻と「キーフレームか」を集める。
    std::vector<std::pair<LONGLONG, bool>> samples;
    std::vector<std::uint8_t> hasKeyFlag;
    bool reachedEnd = false;
    auto readSamples = [&](std::size_t limit) {
        while (samples.size() < limit) {
            DWORD flags = 0;
            LONGLONG timestamp = 0;
            ComPtr<IMFSample> sample;
            hr = indexReader->ReadSample(kVideoStream, 0, nullptr, &flags, &timestamp, &sample);
            if (FAILED(hr)) {
                setError(L"目次の作成中に読み込みに失敗しました", hr);
                return false;
            }
            if (flags & MF_SOURCE_READERF_ENDOFSTREAM) {
                reachedEnd = true;
                return true;
            }
            if (!sample) {
                continue;
            }
            UINT32 cleanPoint = 0;
            const bool hasFlag = SUCCEEDED(sample->GetUINT32(MFSampleExtension_CleanPoint, &cleanPoint));
            samples.emplace_back(timestamp, hasFlag && cleanPoint != 0);
            hasKeyFlag.push_back(hasFlag ? 1 : 0);
        }
        return true;
    };

    if (haveTable) {
        if (!readSamples(probeCount)) {
            return false;
        }
        // 先頭のコマの差を「ずれ」(編集リストなどによる)とし、残りのコマも同じずれで一致するか確かめる。
        bool matches = !samples.empty() && (!reachedEnd || samples.size() == table.presentationTimes.size());
        const LONGLONG offset = matches ? samples[0].first - table.presentationTimes[0] : 0;
        for (std::size_t i = 0; matches && i < samples.size(); ++i) {
            const LONGLONG expected = table.presentationTimes[i] + offset;
            matches = std::abs(samples[i].first - expected) <= 2 &&
                      (!hasKeyFlag[i] || samples[i].second == (table.isKeyFrame[i] != 0));
        }
        if (matches) {
            std::vector<std::pair<LONGLONG, bool>> all(table.presentationTimes.size());
            for (std::size_t i = 0; i < all.size(); ++i) {
                all[i] = {table.presentationTimes[i] + offset, table.isKeyFrame[i] != 0};
            }
            indexMethod_ = L"mp4/movの目次";
            return setIndex(std::move(all), true);
        }
    }

    // 目次を直接読めない形式、または照合が合わなかった場合は、全コマを読んで目次を作る。
    if (!reachedEnd && !readSamples(std::numeric_limits<std::size_t>::max())) {
        return false;
    }
    bool anyKeyFlag = false;
    for (std::uint8_t flag : hasKeyFlag) {
        anyKeyFlag = anyKeyFlag || flag != 0;
    }
    indexMethod_ = L"全体を読んで作成";
    return setIndex(std::move(samples), anyKeyFlag);
}

bool MediaFoundationSource::setIndex(std::vector<std::pair<LONGLONG, bool>> samples, bool anyKeyFlag) {
    if (samples.empty()) {
        setError(L"コマが1つもありません", E_FAIL);
        return false;
    }
    // 表示時刻の順に並べたものがコマ番号順になる。
    std::sort(samples.begin(), samples.end());
    timestamps_.clear();
    keyFrames_.clear();
    timestamps_.reserve(samples.size());
    for (const auto& [timestamp, isKey] : samples) {
        if (!timestamps_.empty() && timestamps_.back() == timestamp) {
            continue;  // 同じ表示時刻のコマは1つとして扱う。
        }
        if (isKey) {
            keyFrames_.push_back(static_cast<int>(timestamps_.size()));
        }
        timestamps_.push_back(timestamp);
    }
    // キーフレームの情報が無い形式では、安全のため常に先頭から読む。
    if (!anyKeyFlag || keyFrames_.empty() || keyFrames_.front() != 0) {
        keyFrames_.insert(keyFrames_.begin(), 0);
        if (!anyKeyFlag) {
            keyFrames_.resize(1);
        }
    }

    // 照合の誤差は、隣り合うコマの最小間隔の半分未満にする(隣のコマと取り違えないため)。
    LONGLONG minimumGap = 0;
    for (std::size_t i = 1; i < timestamps_.size(); ++i) {
        const LONGLONG gap = timestamps_[i] - timestamps_[i - 1];
        if (minimumGap == 0 || gap < minimumGap) {
            minimumGap = gap;
        }
    }
    tolerance_ = std::max<LONGLONG>(1, minimumGap / 2 - 1);
    return true;
}

std::wstring MediaFoundationSource::description() const {
    return std::wstring(usingGpu_ ? L"デコード: GPU" : L"デコード: CPU") + L" / 目次: " + indexMethod_;
}

int MediaFoundationSource::keyFrameAtOrBefore(int index) const {
    const auto it = std::upper_bound(keyFrames_.begin(), keyFrames_.end(), index);
    return it == keyFrames_.begin() ? 0 : *(it - 1);
}

int MediaFoundationSource::indexOfTimestamp(LONGLONG timestamp) const {
    const auto it = std::lower_bound(timestamps_.begin(), timestamps_.end(), timestamp);
    int best = -1;
    LONGLONG bestDistance = 0;
    for (auto candidate : {it, it == timestamps_.begin() ? it : it - 1}) {
        if (candidate == timestamps_.end()) {
            continue;
        }
        const LONGLONG distance = std::abs(*candidate - timestamp);
        if (best < 0 || distance < bestDistance) {
            best = static_cast<int>(candidate - timestamps_.begin());
            bestDistance = distance;
        }
    }
    return (best >= 0 && bestDistance <= tolerance_) ? best : -1;
}

bool MediaFoundationSource::seekToKeyFrame(int keyIndex) {
    error_.clear();
    keyIndex = std::clamp(keyIndex, 0, frameCount() - 1);
    PROPVARIANT position;
    InitPropVariantFromInt64(timestamps_[static_cast<size_t>(keyIndex)], &position);
    const HRESULT hr = reader_->SetCurrentPosition(GUID_NULL, position);
    PropVariantClear(&position);
    if (FAILED(hr)) {
        setError(L"読み込み位置を移動できません", hr);
        return false;
    }
    minimumIndex_ = keyIndex;
    clearPending();  // 移動前に先読みしていたコマは捨てる。
    return true;
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

int MediaFoundationSource::readDecodedSample(ComPtr<IMFSample>& sample, int& index) {
    for (;;) {
        DWORD flags = 0;
        LONGLONG timestamp = 0;
        sample.Reset();
        const HRESULT hr = reader_->ReadSample(kVideoStream, 0, nullptr, &flags, &timestamp, &sample);
        if (FAILED(hr)) {
            setError(L"コマの読み込みに失敗しました", hr);
            return -1;
        }
        if (flags & MF_SOURCE_READERF_ENDOFSTREAM) {
            return 0;
        }
        if ((flags & MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED) && !updateFormat()) {
            return -1;
        }
        if (!sample) {
            // 映像の途切れを示す通知(STREAMTICK)などはコマとして数えない。
            continue;
        }
        // 目次と照合して番号を決める。照合できないコマや、シーク位置より前のコマは返さない。
        index = indexOfTimestamp(timestamp);
        if (index >= minimumIndex_) {
            return 1;
        }
    }
}

bool MediaFoundationSource::enqueueGpuCopy(IMFSample* sample, int index) {
    if (!context_) {
        return false;
    }
    ComPtr<IMFMediaBuffer> buffer;
    ComPtr<IMFDXGIBuffer> dxgiBuffer;
    ComPtr<ID3D11Texture2D> texture;
    UINT subresource = 0;
    if (FAILED(sample->GetBufferByIndex(0, &buffer)) || FAILED(buffer.As(&dxgiBuffer)) ||
        FAILED(dxgiBuffer->GetResource(IID_PPV_ARGS(&texture))) ||
        FAILED(dxgiBuffer->GetSubresourceIndex(&subresource))) {
        return false;  // GPU上のコマではない。
    }
    D3D11_TEXTURE2D_DESC desc{};
    texture->GetDesc(&desc);
    if (desc.Format != DXGI_FORMAT_B8G8R8A8_UNORM && desc.Format != DXGI_FORMAT_B8G8R8X8_UNORM) {
        return false;  // RGBへの変換がされていない。
    }

    // 主メモリから読めるテクスチャ(ステージング)へ写す命令だけを出し、完了は待たない。
    // 使い終わったステージングは使い回す(毎回作ると遅いため)。
    ComPtr<ID3D11Texture2D> staging;
    while (!stagingPool_.empty() && !staging) {
        ComPtr<ID3D11Texture2D> candidate = std::move(stagingPool_.back());
        stagingPool_.pop_back();
        D3D11_TEXTURE2D_DESC existing{};
        candidate->GetDesc(&existing);
        if (existing.Width == desc.Width && existing.Height == desc.Height && existing.Format == desc.Format) {
            staging = std::move(candidate);
        }
    }
    if (!staging) {
        D3D11_TEXTURE2D_DESC stagingDesc{};
        stagingDesc.Width = desc.Width;
        stagingDesc.Height = desc.Height;
        stagingDesc.MipLevels = 1;
        stagingDesc.ArraySize = 1;
        stagingDesc.Format = desc.Format;
        stagingDesc.SampleDesc.Count = 1;
        stagingDesc.Usage = D3D11_USAGE_STAGING;
        stagingDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        if (FAILED(device_->CreateTexture2D(&stagingDesc, nullptr, &staging))) {
            return false;
        }
    }
    context_->CopySubresourceRegion(staging.Get(), 0, 0, 0, 0, texture.Get(), subresource, nullptr);
    context_->Flush();  // 命令をすぐGPUへ送り、次のコマのデコードと並行して進める。

    PendingFrame pending;
    pending.index = index;
    pending.visible = visible_;
    pending.staging = std::move(staging);
    pending_.push_back(std::move(pending));
    return true;
}

bool MediaFoundationSource::copyFromStaging(PendingFrame& pending, Frame& out) {
    D3D11_TEXTURE2D_DESC desc{};
    pending.staging->GetDesc(&desc);
    D3D11_MAPPED_SUBRESOURCE mapped{};
    // 写し終わっていなければ、ここで完了を待つ。先読みしている分だけ待ち時間は短くなる。
    const HRESULT hr = context_->Map(pending.staging.Get(), 0, D3D11_MAP_READ, 0, &mapped);
    if (FAILED(hr)) {
        setError(L"GPUからコマを読み出せません", hr);
        return false;
    }
    RECT visible = pending.visible;
    visible.right = std::min<LONG>(visible.right, static_cast<LONG>(desc.Width));
    visible.bottom = std::min<LONG>(visible.bottom, static_cast<LONG>(desc.Height));
    copyRows(static_cast<const BYTE*>(mapped.pData), static_cast<LONG>(mapped.RowPitch), visible, out);
    context_->Unmap(pending.staging.Get(), 0);
    stagingPool_.push_back(std::move(pending.staging));
    return true;
}

bool MediaFoundationSource::copyFromSample(IMFSample* sample, const RECT& visible, Frame& out) {
    ComPtr<IMFMediaBuffer> buffer;
    HRESULT hr = sample->ConvertToContiguousBuffer(&buffer);
    if (FAILED(hr)) {
        setError(L"コマのデータを取り出せません", hr);
        return false;
    }

    // 2Dバッファなら行の先頭と間隔を正しく返してくれる。そうでなければ形式の情報から求める。
    BYTE* scan0 = nullptr;
    LONG pitch = 0;
    ComPtr<IMF2DBuffer> buffer2d;
    BYTE* raw = nullptr;
    const bool locked2d = SUCCEEDED(buffer.As(&buffer2d)) && SUCCEEDED(buffer2d->Lock2D(&scan0, &pitch));
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
    copyRows(scan0, pitch, visible, out);
    if (locked2d) {
        buffer2d->Unlock2D();
    } else {
        buffer->Unlock();
    }
    return true;
}

void MediaFoundationSource::copyRows(const BYTE* scan0, LONG pitch, const RECT& visible, Frame& out) {
    out.width = visible.right - visible.left;
    out.height = visible.bottom - visible.top;
    out.pixels.resize(static_cast<size_t>(out.width) * out.height);
    for (int y = 0; y < out.height; ++y) {
        const BYTE* src = scan0 + static_cast<LONGLONG>(pitch) * (visible.top + y) + visible.left * 4;
        std::uint32_t* dst = out.pixels.data() + static_cast<size_t>(y) * out.width;
        std::memcpy(dst, src, static_cast<size_t>(out.width) * 4);
        // RGB32の4バイト目は未定義なので、不透明として埋める。
        for (int x = 0; x < out.width; ++x) {
            dst[x] |= 0xFF000000u;
        }
    }
}

bool MediaFoundationSource::readNext(Frame& out, int& index) {
    error_.clear();
    // GPUのときは数コマ先までデコードと主メモリへの写しを命令しておき、古いものから受け取る。
    // GPUは命令を順に並行して処理するので、1コマずつ完了を待つより何倍も速い。
    const std::size_t depth = usingGpu_ ? kGpuPipelineDepth : 1;
    while (!endOfStream_ && pending_.size() < depth) {
        ComPtr<IMFSample> sample;
        int sampleIndex = -1;
        const int status = readDecodedSample(sample, sampleIndex);
        if (status < 0) {
            return false;
        }
        if (status == 0) {
            endOfStream_ = true;
            break;
        }
        if (!usingGpu_ || !enqueueGpuCopy(sample.Get(), sampleIndex)) {
            PendingFrame pending;
            pending.index = sampleIndex;
            pending.visible = visible_;
            pending.sample = std::move(sample);
            pending_.push_back(std::move(pending));
        }
    }
    if (pending_.empty()) {
        return false;  // 終端。
    }
    PendingFrame pending = std::move(pending_.front());
    pending_.pop_front();
    index = pending.index;
    return pending.staging ? copyFromStaging(pending, out) : copyFromSample(pending.sample.Get(), pending.visible, out);
}

void MediaFoundationSource::clearPending() {
    for (PendingFrame& pending : pending_) {
        if (pending.staging) {
            stagingPool_.push_back(std::move(pending.staging));
        }
    }
    pending_.clear();
    endOfStream_ = false;
}

void MediaFoundationSource::setError(const wchar_t* message, HRESULT hr) {
    wchar_t text[512];
    std::swprintf(text, 512, L"%ls (HRESULT 0x%08lX)", message, static_cast<unsigned long>(hr));
    error_ = text;
}

}  // namespace frameplayer
