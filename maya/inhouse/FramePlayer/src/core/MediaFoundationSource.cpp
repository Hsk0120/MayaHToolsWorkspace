/**
 * @file MediaFoundationSource.cpp
 * @brief Media Foundationで動画を読む処理の実装。
 */
#include "core/MediaFoundationSource.h"

#include "core/TraceLog.h"
#include "core/Util.h"

#include <d3d11.h>
#include <mfapi.h>
#include <mferror.h>
#include <propvarutil.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <future>
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

/**
 * @brief Source Readerが挟んだVideo Processor MFTのフレームレート変換を止める。
 * @param reader 出力形式を設定し終えたSource Reader。
 * @note 色変換や縮小のためにVideo Processorが挟まると、可変フレームレート(VFR)の動画では出力の時刻が
 *       平均フレームレートの等間隔に付け直される(Xbox Game Barの録画などで確認)。すると目次の時刻と照合できず、
 *       約半分のコマが表示されない(コマ落ちに見える)。MF_XVP_DISABLE_FRCで変換を止め、元の時刻をそのまま使う。
 *       Video Processorが挟まらない場合は何もしない。
 */
void disableFrameRateConversion(IMFSourceReader* reader) {
    ComPtr<IMFSourceReaderEx> readerEx;
    if (FAILED(reader->QueryInterface(IID_PPV_ARGS(&readerEx)))) {
        return;
    }
    for (DWORD i = 0;; ++i) {
        GUID category{};
        ComPtr<IMFTransform> transform;
        if (FAILED(readerEx->GetTransformForStream(kVideoStream, i, &category, &transform))) {
            break;
        }
        ComPtr<IMFAttributes> attributes;
        if (category == MFT_CATEGORY_VIDEO_PROCESSOR && SUCCEEDED(transform->GetAttributes(&attributes))) {
            const HRESULT hr = attributes->SetUINT32(MF_XVP_DISABLE_FRC, TRUE);
            traceLog("video processor %lu disable FRC hr=0x%08lX", static_cast<unsigned long>(i),
                     static_cast<unsigned long>(hr));
        }
    }
}

/**
 * @brief Source Readerがデコーダーの後にWindowsの映像処理(Video Processor)を挟んだかを返す。
 * @param reader 出力形式を設定し終えたSource Reader。
 * @return 挟んでいればtrue。
 * @note 求めた形式をデコーダーがそのまま出せないときだけ挟まる(8bitの動画でP010を求めたときなど)。
 */
bool hasVideoProcessor(IMFSourceReader* reader) {
    ComPtr<IMFSourceReaderEx> readerEx;
    if (FAILED(reader->QueryInterface(IID_PPV_ARGS(&readerEx)))) {
        return false;
    }
    for (DWORD i = 0;; ++i) {
        GUID category{};
        ComPtr<IMFTransform> transform;
        if (FAILED(readerEx->GetTransformForStream(kVideoStream, i, &category, &transform))) {
            return false;
        }
        if (category == MFT_CATEGORY_VIDEO_PROCESSOR) {
            return true;
        }
    }
}

/**
 * @brief Media Foundationの形式の属性から分かる色の情報を当てはめる。
 * @param type 形式。
 * @param info 当てはめる先。分かった項目だけを差し替え、出所をFileにする。
 * @return 行列・色域・伝達関数のどれかが分かったらtrue(範囲だけならデコーダーの既定値のことがあるのでfalse)。
 */
bool applyMediaTypeColor(IMFMediaType* type, ColorInfo& info) {
    auto get = [type](const GUID& key) {
        UINT32 value = 0;
        return SUCCEEDED(type->GetUINT32(key, &value)) ? static_cast<int>(value) : -1;
    };
    bool described = false;
    switch (get(MF_MT_YUV_MATRIX)) {
    case MFVideoTransferMatrix_BT709:
        info.matrix = ColorMatrix::Bt709;
        info.matrixSource = ColorSource::File;
        described = true;
        break;
    case MFVideoTransferMatrix_BT601:
        info.matrix = ColorMatrix::Bt601;
        info.matrixSource = ColorSource::File;
        described = true;
        break;
    case MFVideoTransferMatrix_SMPTE240M:
        info.matrix = ColorMatrix::Smpte240m;
        info.matrixSource = ColorSource::File;
        described = true;
        break;
    case MFVideoTransferMatrix_BT2020_10:
    case MFVideoTransferMatrix_BT2020_12:
        info.matrix = ColorMatrix::Bt2020;
        info.matrixSource = ColorSource::File;
        described = true;
        break;
    default:
        break;
    }
    bool knownPrimaries = true;
    switch (get(MF_MT_VIDEO_PRIMARIES)) {
    case MFVideoPrimaries_BT709:
        info.primaries = ColorPrimaries::Bt709;
        break;
    case MFVideoPrimaries_BT470_2_SysBG:
    case MFVideoPrimaries_EBU3213:
        info.primaries = ColorPrimaries::Bt601_625;
        break;
    case MFVideoPrimaries_SMPTE170M:
    case MFVideoPrimaries_SMPTE240M:
    case MFVideoPrimaries_SMPTE_C:
        info.primaries = ColorPrimaries::Bt601_525;
        break;
    case MFVideoPrimaries_BT2020:
        info.primaries = ColorPrimaries::Bt2020;
        break;
    case MFVideoPrimaries_DCI_P3:
        info.primaries = ColorPrimaries::DciP3;
        break;
    case 13:  // MFVideoPrimaries_Display_P3(新しいSDKだけにある名前)。
        info.primaries = ColorPrimaries::DisplayP3;
        break;
    default:
        knownPrimaries = false;  // 不明・未対応は変えない。
        break;
    }
    if (knownPrimaries) {
        info.primariesSource = ColorSource::File;
        described = true;
    }
    switch (const int transfer = get(MF_MT_TRANSFER_FUNCTION)) {
    case MFVideoTransFunc_10:
    case 17:  // MFVideoTransFunc_10_rel
        info.transfer = TransferFunction::Linear;
        info.transferSource = ColorSource::File;
        described = true;
        break;
    case MFVideoTransFunc_2084:
        info.transfer = TransferFunction::Pq;
        info.transferSource = ColorSource::File;
        described = true;
        break;
    case MFVideoTransFunc_HLG:
        info.transfer = TransferFunction::Hlg;
        info.transferSource = ColorSource::File;
        described = true;
        break;
    default:
        if (transfer > 0) {
            info.transfer = TransferFunction::Sdr;  // ガンマ・BT.709・sRGBなど、SDRの曲線。
            info.transferSource = ColorSource::File;
            described = true;
        }
        break;
    }
    switch (get(MF_MT_VIDEO_NOMINAL_RANGE)) {
    case MFNominalRange_0_255:
        info.range = ColorRange::Full;
        info.rangeSource = ColorSource::File;
        break;
    case MFNominalRange_16_235:
        info.range = ColorRange::Limited;
        info.rangeSource = ColorSource::File;
        break;
    default:
        break;
    }
    switch (get(MF_MT_VIDEO_CHROMA_SITING)) {
    case MFVideoChromaSubsampling_MPEG2:
        info.siting = ChromaSiting::Left;
        break;
    case MFVideoChromaSubsampling_MPEG1:
        info.siting = ChromaSiting::Center;
        break;
    case MFVideoChromaSubsampling_Cosited:
        info.siting = ChromaSiting::TopLeft;
        break;
    default:
        break;
    }
    const int maxContent = get(MF_MT_MAX_LUMINANCE_LEVEL);
    const int maxMastering = get(MF_MT_MAX_MASTERING_LUMINANCE);
    if (maxContent > 0) {
        info.maxContentNits = static_cast<float>(maxContent);
    } else if (maxMastering > 0) {
        info.maxContentNits = static_cast<float>(maxMastering);
    }
    return described;
}

}  // namespace

std::unique_ptr<MediaFoundationSource> MediaFoundationSource::open(const std::wstring& path, int maxWidth,
                                                                   std::shared_ptr<GpuDevice> gpu, std::wstring& error,
                                                                   SourcePurpose purpose) {
    std::unique_ptr<MediaFoundationSource> source(new MediaFoundationSource());

    // MFStartupは参照カウント式なので、読み込み元ごとに開始・終了してよい。
    HRESULT hr = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    if (FAILED(hr)) {
        source->setError(L"Media Foundationを開始できません", hr);
        error = source->error_;
        return nullptr;
    }
    source->started_ = true;
    source->gpu_ = std::move(gpu);
    source->path_ = path;
    source->maxWidth_ = maxWidth;
    // 縮小画像はキーフレームを1つずつ読むので、先の数コマまで命令しておくと無駄なデコードになる。
    source->pipelineDepth_ = purpose == SourcePurpose::Thumbnails ? 1 : kGpuPipelineDepth;

    // 目次の作成(圧縮されたままのコマやmp4の目次を読む)と、デコーダーの準備は互いに依存しないので並行して行う。
    // 目次は別の読み込み元(indexer)で作り、できあがったらこの読み込み元へ移す(同じメンバーを2つのスレッドで
    // 触らないようにするため)。目次が要るのは、試しに1コマ読んで番号を照合するときから。
    std::unique_ptr<MediaFoundationSource> indexer(new MediaFoundationSource());
    const LONGLONG indexStart = nowTicks();
    std::future<bool> indexTask = std::async(std::launch::async, [&indexer, &path] {
        const HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        const bool built = indexer->buildIndex(path);
        if (SUCCEEDED(com)) {
            CoUninitialize();
        }
        return built;
    });
    bool indexReady = false;
    auto waitForIndex = [&] {
        if (!indexReady) {
            indexReady = true;
            if (!indexTask.get()) {
                source->error_ = indexer->error_;
                return false;
            }
            source->timestamps_ = std::move(indexer->timestamps_);
            source->keyFrames_ = std::move(indexer->keyFrames_);
            source->tolerance_ = indexer->tolerance_;
            source->frameRate_ = indexer->frameRate_;
            source->indexMethod_ = std::move(indexer->indexMethod_);
            source->mp4Color_ = indexer->mp4Color_;
            traceLog("open index %.1f ms frames=%d", (nowTicks() - indexStart) * 1000.0 / ticksPerSecond(),
                     source->frameCount());
        }
        return !source->timestamps_.empty();
    };

    // 速い方式から順に試し、先頭のコマを実際に読めたものを採用する。
    //   1. GPUでデコードし、YUVのままGPUのメモリに置く(主メモリへ写さない。キャッシュもGPU)
    //   2. GPUでデコードし、YUVのまま主メモリへ写す
    //   3. CPUでデコードする
    // どの方式もYUVのまま受け取り、RGBへの変換は描画のときに自前のシェーダーで行う(FrameRenderer)。
    std::vector<Mode> modes;
    if (purpose == SourcePurpose::Playback && source->gpu_ && source->gpu_->supportsNv12()) {
        modes.push_back(Mode::GpuTexture);
    }
    if (source->gpu_) {
        modes.push_back(Mode::GpuReadback);
    }
    modes.push_back(Mode::Cpu);
    for (Mode mode : modes) {
        const LONGLONG readerStart = nowTicks();
        const bool created = source->createReader(path, maxWidth, mode);
        const LONGLONG readerEnd = nowTicks();
        if (!waitForIndex()) {
            error = source->error_.empty() ? L"目次を作れません" : source->error_;
            return nullptr;
        }
        if (created) {
            // 試しに先頭のコマを読み、読めた方式を採用する。読んだコマは捨てずに持っておき、最初のreadNext()で返す
            // (先頭へ戻して同じコマをもう一度デコードする手間を省く)。
            const LONGLONG probeStart = nowTicks();
            Frame probe;
            int probeIndex = -1;
            if (source->readNext(probe, probeIndex)) {
                source->heldFrame_ = std::move(probe);
                source->heldIndex_ = probeIndex;
                source->hasHeldFrame_ = true;
                traceLog("open reader mode=%d %.1f ms (wait index %.1f ms) probe %.1f ms", static_cast<int>(mode),
                         (readerEnd - readerStart) * 1000.0 / ticksPerSecond(),
                         (probeStart - readerEnd) * 1000.0 / ticksPerSecond(),
                         (nowTicks() - probeStart) * 1000.0 / ticksPerSecond());
                return source;
            }
        }
        source->clearPending();
        source->stagingPool_.clear();
        source->reader_.Reset();
    }
    error = source->error_.empty() ? L"動画をデコードできません" : source->error_;
    return nullptr;
}

bool MediaFoundationSource::createReader(const std::wstring& path, int maxWidth, Mode mode) {
    (void)maxWidth;  // 縮小はデコードの後に自前で行う(Windowsの映像処理を通さないため)。
    error_.clear();
    reader_.Reset();
    mode_ = Mode::Cpu;
    colorChecked_ = false;
    const bool useGpu = mode != Mode::Cpu;

    ComPtr<IMFAttributes> attributes;
    HRESULT hr = MFCreateAttributes(&attributes, 3);
    if (FAILED(hr)) {
        setError(L"属性を作成できません", hr);
        return false;
    }
    // デコーダーがNV12・P010を出さない形式(MJPEGのYUY2など)だけ、Windowsの映像処理でNV12へ並べ替える。
    // デコーダーがそのまま出せるときは映像処理は挟まらない(色の変換・縮小はさせない)。
    attributes->SetUINT32(MF_SOURCE_READER_ENABLE_ADVANCED_VIDEO_PROCESSING, TRUE);
    if (useGpu) {
        // 共有のGPUデバイスを渡すと、GPUでデコードする。
        gpu_->device()->GetImmediateContext(context_.ReleaseAndGetAddressOf());
        hr = attributes->SetUnknown(MF_SOURCE_READER_D3D_MANAGER, gpu_->manager());
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
    // 動画の形式(圧縮されたまま)に付いている色の情報を覚えておく。
    nativeColor_ = ColorInfo{};
    nativeDescribed_ = false;
    codec_ = GUID_NULL;
    ComPtr<IMFMediaType> nativeType;
    if (SUCCEEDED(reader_->GetNativeMediaType(kVideoStream, 0, &nativeType))) {
        nativeDescribed_ = applyMediaTypeColor(nativeType.Get(), nativeColor_);
        nativeType->GetGUID(MF_MT_SUBTYPE, &codec_);
    }

    // 10bitの動画はP010のまま受け取りたいが、8bitの動画でP010を求めるとWindowsの映像処理が挟まって変換される。
    // そこでまずP010を求め、映像処理が挟まらなければ(デコーダーがP010を出せる=10bitの動画)P010を使い、
    // 挟まったらNV12に戻す。GPUのメモリにP010を置けない場合はNV12にしない(10bitを8bitに落とさないため)。
    auto setOutput = [&](const GUID& subtype) {
        ComPtr<IMFMediaType> outputType;
        HRESULT result = MFCreateMediaType(&outputType);
        if (SUCCEEDED(result)) {
            result = outputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        }
        if (SUCCEEDED(result)) {
            result = outputType->SetGUID(MF_MT_SUBTYPE, subtype);
        }
        if (SUCCEEDED(result)) {
            result = reader_->SetCurrentMediaType(kVideoStream, nullptr, outputType.Get());
        }
        return result;
    };
    layout_ = PixelLayout::P010;
    hr = setOutput(MFVideoFormat_P010);
    if (FAILED(hr) || hasVideoProcessor(reader_.Get())) {
        layout_ = PixelLayout::Nv12;
        hr = setOutput(MFVideoFormat_NV12);
    } else if (mode == Mode::GpuTexture && !gpu_->supportsP010()) {
        setError(L"GPUのメモリに10bitのコマを置けません", E_FAIL);
        return false;  // 次の方式(主メモリへ写す)で読む。
    }
    if (FAILED(hr)) {
        setError(L"出力形式を設定できません", hr);
        return false;
    }
    disableFrameRateConversion(reader_.Get());
    mode_ = mode;
    if (!updateFormat()) {
        mode_ = Mode::Cpu;
        return false;
    }
    return true;
}

MediaFoundationSource::~MediaFoundationSource() {
    heldFrame_ = Frame{};
    pending_.clear();  // MFShutdownより先に読み込み本体とGPUの資源を解放する。
    stagingPool_.clear();
    copyTexture_.Reset();
    scaler_.reset();
    reader_.Reset();
    context_.Reset();
    gpu_.reset();
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
    // 色の情報(colr)は、目次として使えない場合でも読めていれば使う。
    mp4Color_ = {table.colorPrimaries, table.transferCharacteristics, table.matrixCoefficients, table.fullRange};
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
    const wchar_t* decode = mode_ == Mode::GpuTexture    ? L"デコード: GPU(キャッシュもGPU)"
                            : mode_ == Mode::GpuReadback ? L"デコード: GPU"
                                                         : L"デコード: CPU";
    return std::wstring(decode) + L" / 目次: " + indexMethod_ + L" / 色: " + describeColor(color_);
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

void MediaFoundationSource::releaseDecoder() {
    if (!reader_) {
        return;
    }
    // 開いたときに読んだコマ・先読み中のコマ・使い回しのテクスチャ・読み込み本体(デコーダー)の順に手放す。
    hasHeldFrame_ = false;
    heldFrame_ = Frame{};
    // mode_は残しておき、作り直すときに同じ方式で作る。
    clearPending();
    stagingPool_.clear();
    copyTexture_.Reset();
    reader_.Reset();
}

bool MediaFoundationSource::seekToKeyFrame(int keyIndex) {
    error_.clear();
    hasHeldFrame_ = false;  // 位置を移すので、開いたときに読んだコマはもう返さない。
    heldFrame_ = Frame{};
    if (!reader_) {
        // releaseDecoder()で閉じていれば、前と同じ方式で作り直す。
        const Mode mode = mode_;
        if (!createReader(path_, maxWidth_, mode)) {
            return false;
        }
    }
    keyIndex = std::clamp(keyIndex, 0, frameCount() - 1);
    PROPVARIANT position;
    InitPropVariantFromInt64(timestamps_[static_cast<size_t>(keyIndex)], &position);
    // Media Foundationの呼び出し(シーク・デコード)は鍵で囲まない。GPUのデコーダーは別のスレッドでも
    // GPUを使うことがあり、ここで鍵を持ったまま待つと互いに待ち合って止まる(デッドロック)ため。
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

    // 明るさの面の1行のバイト数。属性が無ければ幅から求める(NV12・P010は上の行から並ぶ)。
    UINT32 stride = 0;
    if (SUCCEEDED(type->GetUINT32(MF_MT_DEFAULT_STRIDE, &stride))) {
        defaultStride_ = static_cast<LONG>(stride);
    } else {
        defaultStride_ = static_cast<LONG>(bufferWidth_ * (layout_ == PixelLayout::P010 ? 2 : 1));
    }

    // H.264の1080pは1088行で届くことがあるため、表示範囲の指定があれば切り出す。
    // YUV 4:2:0は色の画素が2×2に1つなので、位置と大きさを偶数に揃える。
    RECT visible{0, 0, static_cast<LONG>(bufferWidth_), static_cast<LONG>(bufferHeight_)};
    MFVideoArea area{};
    UINT32 blobSize = 0;
    if (SUCCEEDED(type->GetBlob(MF_MT_MINIMUM_DISPLAY_APERTURE, reinterpret_cast<UINT8*>(&area), sizeof(area),
                                &blobSize)) &&
        blobSize == sizeof(area)) {
        RECT r{area.OffsetX.value, area.OffsetY.value, area.OffsetX.value + area.Area.cx,
               area.OffsetY.value + area.Area.cy};
        if (r.left >= 0 && r.top >= 0 && r.right <= static_cast<LONG>(bufferWidth_) &&
            r.bottom <= static_cast<LONG>(bufferHeight_) && r.right > r.left && r.bottom > r.top) {
            visible = r;
        }
    }
    visible.left &= ~1L;
    visible.top &= ~1L;
    visible.right = visible.left + ((visible.right - visible.left) & ~1L);
    visible.bottom = visible.top + ((visible.bottom - visible.top) & ~1L);
    if (visible.right <= visible.left || visible.bottom <= visible.top) {
        setError(L"映像が小さすぎます", E_FAIL);
        return false;
    }
    visible_ = visible;
    updateColor(type.Get());
    return true;
}

void MediaFoundationSource::updateColor(IMFMediaType* outputType) {
    // 優先順(後のものほど優先): 大きさからの推定 → デコーダーの出力の形式 → 動画の形式 → mp4/movのcolr。
    ColorInfo color = guessColorInfo(visible_.right - visible_.left, visible_.bottom - visible_.top);
    // MJPEG(JPEG)は色の画素が中間にある。H.264・HEVCなどは左寄せが既定。
    if (codec_ == MFVideoFormat_MJPG) {
        color.siting = ChromaSiting::Center;
        color.range = ColorRange::Full;  // JPEGは全範囲。
    }
    if (outputType) {
        ColorInfo decoded = color;
        // デコーダーの出力は、動画に色の指定が無くても範囲だけ既定値を入れることがある。
        // 行列・色域・伝達関数のどれかが分かったときだけ、動画の指定として扱う。
        if (applyMediaTypeColor(outputType, decoded)) {
            color = decoded;
        } else {
            color.maxContentNits = decoded.maxContentNits;
        }
    }
    if (nativeDescribed_) {
        // 動画の形式の値で、分かっている項目だけを上書きする。
        if (nativeColor_.matrixSource == ColorSource::File) {
            color.matrix = nativeColor_.matrix;
            color.matrixSource = ColorSource::File;
        }
        if (nativeColor_.rangeSource == ColorSource::File) {
            color.range = nativeColor_.range;
            color.rangeSource = ColorSource::File;
        }
        if (nativeColor_.primariesSource == ColorSource::File) {
            color.primaries = nativeColor_.primaries;
            color.primariesSource = ColorSource::File;
        }
        if (nativeColor_.transferSource == ColorSource::File) {
            color.transfer = nativeColor_.transfer;
            color.transferSource = ColorSource::File;
        }
    }
    if (nativeColor_.maxContentNits > 0.0f) {
        color.maxContentNits = nativeColor_.maxContentNits;
    }
    applyH273(color, mp4Color_[0], mp4Color_[1], mp4Color_[2], mp4Color_[3]);
    color.bitDepth = layout_ == PixelLayout::P010 ? 10 : 8;
    color_ = color;
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
        if (!colorChecked_) {
            // デコーダーは最初のコマをデコードしてから、動画の中の色の情報を出力の形式に入れる(movなど)。
            colorChecked_ = true;
            ComPtr<IMFMediaType> current;
            if (SUCCEEDED(reader_->GetCurrentMediaType(kVideoStream, &current))) {
                updateColor(current.Get());
            }
        }
        // 目次と照合して番号を決める。照合できないコマや、シーク位置より前のコマは返さない。
        index = indexOfTimestamp(timestamp);
        if (index >= minimumIndex_) {
            return 1;
        }
        if (index < 0) {
            // 照合できないコマは表示しない(別のコマとして見せないため)。原因を調べられるよう時刻を記録する。
            traceLog("decode unmatched timestamp=%lld (tolerance=%lld)", static_cast<long long>(timestamp),
                     static_cast<long long>(tolerance_));
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
    if (desc.Format != DXGI_FORMAT_NV12 && desc.Format != DXGI_FORMAT_P010) {
        return false;
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
        if (FAILED(gpu_->device()->CreateTexture2D(&stagingDesc, nullptr, &staging))) {
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
    // NV12・P010のステージングは、明るさの面(テクスチャの高さ分の行)の直後に色の面が続く。
    RECT visible = pending.visible;
    visible.right = std::min<LONG>(visible.right, static_cast<LONG>(desc.Width) & ~1L);
    visible.bottom = std::min<LONG>(visible.bottom, static_cast<LONG>(desc.Height) & ~1L);
    const auto* luma = static_cast<const BYTE*>(mapped.pData);
    copyPlanes(luma, luma + static_cast<std::size_t>(mapped.RowPitch) * desc.Height, static_cast<LONG>(mapped.RowPitch),
               visible, out);
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
    // NV12・P010は、明るさの面(デコード結果の高さ分の行)の直後に色の面が同じ行の間隔で続く。
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
        scan0 = raw;
        pitch = defaultStride_;
    }
    if (pitch <= 0) {
        setError(L"コマのデータの並びに対応していません", E_FAIL);
    } else {
        copyPlanes(scan0, scan0 + static_cast<std::size_t>(pitch) * bufferHeight_, pitch, visible, out);
    }
    if (locked2d) {
        buffer2d->Unlock2D();
    } else {
        buffer->Unlock();
    }
    return pitch > 0;
}

void MediaFoundationSource::copyPlanes(const BYTE* luma, const BYTE* chroma, LONG pitch, const RECT& visible,
                                       Frame& out) const {
    const std::size_t valueBytes = layout_ == PixelLayout::P010 ? 2 : 1;
    out.width = visible.right - visible.left;
    out.height = visible.bottom - visible.top;
    out.layout = layout_;
    out.color = color_;
    out.pixels.clear();
    out.texture.Reset();
    out.chroma.Reset();
    const std::size_t row = static_cast<std::size_t>(out.width) * valueBytes;
    out.planes.resize(row * out.height * 3 / 2);
    // 明るさの面は1画素1つ、色の面は横2画素で1組(U,V)なので、行のバイト数はどちらも幅×値のバイト数。
    for (int y = 0; y < out.height; ++y) {
        std::memcpy(out.planes.data() + row * y,
                    luma + static_cast<std::size_t>(pitch) * (visible.top + y) + visible.left * valueBytes, row);
    }
    BYTE* chromaOut = out.planes.data() + row * out.height;
    for (int y = 0; y < out.height / 2; ++y) {
        std::memcpy(chromaOut + row * y,
                    chroma + static_cast<std::size_t>(pitch) * (visible.top / 2 + y) + visible.left * valueBytes, row);
    }
}

bool MediaFoundationSource::readNext(Frame& out, int& index) {
    error_.clear();
    if (hasHeldFrame_) {
        // 開いたときに試しに読んだ先頭のコマ(デコーダーはその次から読める位置にある)。
        out = std::move(heldFrame_);
        index = heldIndex_;
        heldFrame_ = Frame{};
        hasHeldFrame_ = false;
        return true;
    }
    if (!reader_) {
        error_ = L"デコーダーを閉じています(先に読み込み位置を移す必要があります)";
        return false;
    }
    if (mode_ == Mode::GpuTexture) {
        // デコード(ReadSample)は鍵で囲まない(シークの説明を参照)。自分で出すGPUの命令(写し)だけを囲む。
        ComPtr<IMFSample> sample;
        const int status = readDecodedSample(sample, index);
        if (status <= 0) {
            return false;
        }
        auto lock = gpu_->lock();
        return copyToTexture(sample.Get(), out);
    }

    // GPUのときは数コマ先までデコードと主メモリへの写しを命令しておき、古いものから受け取る。
    // GPUは命令を順に並行して処理するので、1コマずつ完了を待つより何倍も速い。
    const bool useGpu = mode_ == Mode::GpuReadback;
    const std::size_t depth = useGpu ? pipelineDepth_ : 1;
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
        bool enqueued = false;
        if (useGpu) {
            auto lock = gpu_->lock();
            enqueued = enqueueGpuCopy(sample.Get(), sampleIndex);
        }
        if (!enqueued) {
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
    if (pending.staging) {
        auto lock = gpu_->lock();
        return copyFromStaging(pending, out);
    }
    return copyFromSample(pending.sample.Get(), pending.visible, out);
}

bool MediaFoundationSource::copyToTexture(IMFSample* sample, Frame& out) {
    ComPtr<IMFMediaBuffer> buffer;
    ComPtr<IMFDXGIBuffer> dxgiBuffer;
    ComPtr<ID3D11Texture2D> texture;
    UINT subresource = 0;
    HRESULT hr = sample->GetBufferByIndex(0, &buffer);
    if (SUCCEEDED(hr)) {
        hr = buffer.As(&dxgiBuffer);
    }
    if (SUCCEEDED(hr)) {
        hr = dxgiBuffer->GetResource(IID_PPV_ARGS(&texture));
    }
    if (SUCCEEDED(hr)) {
        hr = dxgiBuffer->GetSubresourceIndex(&subresource);
    }
    if (FAILED(hr)) {
        setError(L"GPU上のコマを取り出せません", hr);
        return false;
    }
    D3D11_TEXTURE2D_DESC sourceDesc{};
    texture->GetDesc(&sourceDesc);
    const DXGI_FORMAT format = layout_ == PixelLayout::P010 ? DXGI_FORMAT_P010 : DXGI_FORMAT_NV12;
    if (sourceDesc.Format != format) {
        setError(L"GPU上のコマがNV12・P010ではありません", E_FAIL);
        return false;
    }

    // デコーダーの出力はデコーダーが使い回すので、表示範囲だけをシェーダーから読めるテクスチャへ写す。
    const UINT width = static_cast<UINT>(visible_.right - visible_.left);
    const UINT height = static_cast<UINT>(visible_.bottom - visible_.top);
    // キャッシュの最大幅より大きければ、写した後に自前のシェーダーで縮小する(写す先は使い回す)。
    const bool shrink = maxWidth_ > 0 && width > static_cast<UINT>(maxWidth_);
    ComPtr<ID3D11Texture2D> copy;
    if (shrink && copyTexture_) {
        D3D11_TEXTURE2D_DESC existing{};
        copyTexture_->GetDesc(&existing);
        if (existing.Width == width && existing.Height == height && existing.Format == format) {
            copy = copyTexture_;
        }
    }
    if (!copy) {
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = width;
        desc.Height = height;
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = format;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DEFAULT;
        desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        hr = gpu_->device()->CreateTexture2D(&desc, nullptr, &copy);
        if (FAILED(hr)) {
            setError(L"GPUのメモリにコマを置けません", hr);
            return false;
        }
        if (shrink) {
            copyTexture_ = copy;
        }
    }
    const D3D11_BOX box{static_cast<UINT>(visible_.left), static_cast<UINT>(visible_.top), 0,
                        static_cast<UINT>(visible_.left) + width, static_cast<UINT>(visible_.top) + height, 1};
    context_->CopySubresourceRegion(copy.Get(), 0, 0, 0, 0, texture.Get(), subresource, &box);

    out.color = color_;
    out.pixels.clear();
    out.planes.clear();
    if (shrink) {
        if (!scaler_) {
            scaler_ = std::make_unique<FrameRenderer>();
            if (!scaler_->create(gpu_->device())) {
                scaler_.reset();
            }
        }
        // 縦横比を保ち、偶数に揃える。
        const int targetWidth = maxWidth_ & ~1;
        const int targetHeight = std::max(2, static_cast<int>((static_cast<long long>(height) * targetWidth / width + 1) & ~1LL));
        if (!scaler_ || !scaler_->downscale(context_.Get(), copy.Get(), layout_, static_cast<int>(width),
                                            static_cast<int>(height), color_.siting, targetWidth, targetHeight, out)) {
            setError(L"コマを縮小できません", E_FAIL);
            return false;
        }
        return true;
    }
    out.width = static_cast<int>(width);
    out.height = static_cast<int>(height);
    out.layout = layout_;
    out.texture = std::move(copy);
    out.chroma.Reset();
    return true;
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
