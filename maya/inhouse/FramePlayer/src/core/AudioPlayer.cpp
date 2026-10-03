/**
 * @file AudioPlayer.cpp
 * @brief 音声再生の実装。
 */
#include "core/AudioPlayer.h"

#include "core/Util.h"

#include <audioclient.h>
#include <mfapi.h>
#include <mmdeviceapi.h>
#include <mmreg.h>
#include <ks.h>
#include <ksmedia.h>
#include <propvarutil.h>

#include <algorithm>
#include <cstring>

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

/// 読む対象のストリーム(最初の音声ストリーム)。
constexpr DWORD kAudioStream = static_cast<DWORD>(MF_SOURCE_READER_FIRST_AUDIO_STREAM);
/// WASAPIのバッファの長さ(100ns単位)。短いほど開始が速いが、途切れやすくなる。
constexpr REFERENCE_TIME kBufferDuration = 1000000;  // 100ms

}  // namespace

AudioPlayer::~AudioPlayer() {
    if (thread_.joinable()) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            command_ = Command::Quit;
        }
        SetEvent(commandEvent_);
        thread_.join();
    }
    if (commandEvent_) {
        CloseHandle(commandEvent_);
    }
    reader_.Reset();
    if (started_) {
        MFShutdown();
    }
}

bool AudioPlayer::open(const std::wstring& path) {
    if (FAILED(MFStartup(MF_VERSION, MFSTARTUP_LITE))) {
        return false;
    }
    started_ = true;
    if (FAILED(MFCreateSourceReaderFromURL(path.c_str(), nullptr, &reader_))) {
        return false;
    }
    reader_->SetStreamSelection(static_cast<DWORD>(MF_SOURCE_READER_ALL_STREAMS), FALSE);
    if (FAILED(reader_->SetStreamSelection(kAudioStream, TRUE))) {
        reader_.Reset();
        return false;  // 音声ストリームが無い。
    }
    ComPtr<IMFMediaType> nativeType;
    if (FAILED(reader_->GetNativeMediaType(kAudioStream, 0, &nativeType))) {
        reader_.Reset();
        return false;
    }
    const UINT32 nativeRate = MFGetAttributeUINT32(nativeType.Get(), MF_MT_AUDIO_SAMPLES_PER_SECOND, 48000);
    const UINT32 nativeChannels = MFGetAttributeUINT32(nativeType.Get(), MF_MT_AUDIO_NUM_CHANNELS, 2);

    // 32bit浮動小数点のPCMにデコードさせる。チャンネル数はまず2(ステレオ)を試し、だめなら元のまま。
    // サンプリング周波数は変えず、出力先の形式との違いはWASAPIの自動変換に任せる。
    HRESULT hr = E_FAIL;
    for (UINT32 channels : {2u, nativeChannels}) {
        ComPtr<IMFMediaType> type;
        hr = MFCreateMediaType(&type);
        if (SUCCEEDED(hr)) {
            type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio);
            type->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_Float);
            type->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, channels);
            type->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, nativeRate);
            type->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 32);
            type->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, channels * 4);
            type->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, nativeRate * channels * 4);
            hr = reader_->SetCurrentMediaType(kAudioStream, nullptr, type.Get());
        }
        if (SUCCEEDED(hr)) {
            break;
        }
    }
    ComPtr<IMFMediaType> currentType;
    if (FAILED(hr) || FAILED(reader_->GetCurrentMediaType(kAudioStream, &currentType))) {
        reader_.Reset();
        return false;
    }
    sampleRate_ = MFGetAttributeUINT32(currentType.Get(), MF_MT_AUDIO_SAMPLES_PER_SECOND, 0);
    channels_ = MFGetAttributeUINT32(currentType.Get(), MF_MT_AUDIO_NUM_CHANNELS, 0);
    if (sampleRate_ == 0 || channels_ == 0) {
        reader_.Reset();
        return false;
    }

    // 出力の準備は出力スレッドで行い(WASAPIの部品はそのスレッドで作って使う)、その結果を待つ。
    commandEvent_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    thread_ = std::thread(&AudioPlayer::outputLoop, this);
    bool ok = false;
    {
        std::unique_lock<std::mutex> lock(mutex_);
        initDone_.wait(lock, [this] { return initState_ != 0; });
        ok = initState_ > 0;
    }
    if (!ok) {
        thread_.join();  // 初期化に失敗したスレッドはすぐ終わる。
        return false;
    }
    hasAudio_ = true;
    return true;
}

void AudioPlayer::start(long long mediaTime) {
    if (!hasAudio_) {
        return;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        command_ = Command::Start;
        commandTime_ = mediaTime;
        positionValid_ = false;
    }
    SetEvent(commandEvent_);
}

void AudioPlayer::stop() {
    if (!hasAudio_) {
        return;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        command_ = Command::Stop;
        positionValid_ = false;
    }
    SetEvent(commandEvent_);
}

bool AudioPlayer::position(long long& mediaTime) const {
    static const LONGLONG frequency = ticksPerSecond();
    std::lock_guard<std::mutex> lock(mutex_);
    if (!playing_ || !positionValid_) {
        return false;
    }
    // 最後に測った値から、測った後に経過した時間だけ進める。
    mediaTime = positionMedia_ + (nowTicks() - positionQpc_) * 10000000 / frequency;
    return true;
}

void AudioPlayer::setVolume(float volume) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        volume_ = std::clamp(volume, 0.0f, 1.0f);
        volumeDirty_ = true;
    }
    if (commandEvent_) {
        SetEvent(commandEvent_);
    }
}

void AudioPlayer::setMuted(bool muted) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        muted_ = muted;
        volumeDirty_ = true;
    }
    if (commandEvent_) {
        SetEvent(commandEvent_);
    }
}

void AudioPlayer::seek(long long mediaTime) {
    PROPVARIANT position;
    InitPropVariantFromInt64(std::max<long long>(0, mediaTime), &position);
    reader_->SetCurrentPosition(GUID_NULL, position);
    PropVariantClear(&position);
    pending_.clear();
    pendingOffset_ = 0;
    skipBefore_ = mediaTime;
    endOfStream_ = false;
}

void AudioPlayer::fill(float* dest, UINT32 frames) {
    std::size_t needed = static_cast<std::size_t>(frames) * channels_;
    while (needed > 0) {
        const std::size_t available = pending_.size() - pendingOffset_;
        if (available > 0) {
            const std::size_t count = std::min(available, needed);
            std::memcpy(dest, pending_.data() + pendingOffset_, count * sizeof(float));
            dest += count;
            pendingOffset_ += count;
            needed -= count;
            continue;
        }
        if (endOfStream_) {
            std::fill(dest, dest + needed, 0.0f);  // 音声の終わり以降は無音。
            return;
        }

        // デコード済みが尽きたので次を読む。
        pending_.clear();
        pendingOffset_ = 0;
        DWORD flags = 0;
        LONGLONG timestamp = 0;
        ComPtr<IMFSample> sample;
        if (FAILED(reader_->ReadSample(kAudioStream, 0, nullptr, &flags, &timestamp, &sample)) ||
            (flags & MF_SOURCE_READERF_ENDOFSTREAM)) {
            endOfStream_ = true;
            continue;
        }
        if (!sample) {
            continue;
        }
        ComPtr<IMFMediaBuffer> buffer;
        if (FAILED(sample->ConvertToContiguousBuffer(&buffer))) {
            continue;
        }
        BYTE* data = nullptr;
        DWORD length = 0;
        if (FAILED(buffer->Lock(&data, nullptr, &length))) {
            continue;
        }
        const std::size_t samples = length / sizeof(float);
        std::size_t skip = 0;
        // シーク直後は、目的の時刻より前のサンプルを捨てる(シークは手前の区切りに移るため)。
        if (skipBefore_ > timestamp) {
            const long long skipFrames = (skipBefore_ - timestamp) * sampleRate_ / 10000000;
            skip = std::min(samples, static_cast<std::size_t>(skipFrames) * channels_);
        }
        pending_.assign(reinterpret_cast<const float*>(data) + skip, reinterpret_cast<const float*>(data) + samples);
        buffer->Unlock();
        if (skip < samples) {
            skipBefore_ = 0;  // 目的の時刻に届いたので、以後は捨てない。
        }
    }
}

void AudioPlayer::outputLoop() {
    // WASAPIの部品はこのスレッドで作り、このスレッドだけで使う。
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    ComPtr<IMMDeviceEnumerator> enumerator;
    ComPtr<IMMDevice> device;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioRenderClient> render;
    ComPtr<IAudioClock> clock;
    ComPtr<ISimpleAudioVolume> volume;
    HANDLE bufferEvent = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    UINT32 bufferFrames = 0;
    UINT64 clockFrequency = 1;

    HRESULT hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(&enumerator));
    if (SUCCEEDED(hr)) {
        hr = enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &device);
    }
    if (SUCCEEDED(hr)) {
        hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                              reinterpret_cast<void**>(client.GetAddressOf()));
    }
    if (SUCCEEDED(hr)) {
        // デコード結果の形式(浮動小数点・元の周波数)のまま渡し、出力装置の形式への変換はWindowsに任せる。
        WAVEFORMATEXTENSIBLE format{};
        format.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
        format.Format.nChannels = static_cast<WORD>(channels_);
        format.Format.nSamplesPerSec = sampleRate_;
        format.Format.wBitsPerSample = 32;
        format.Format.nBlockAlign = static_cast<WORD>(channels_ * 4);
        format.Format.nAvgBytesPerSec = sampleRate_ * channels_ * 4;
        format.Format.cbSize = sizeof(WAVEFORMATEXTENSIBLE) - sizeof(WAVEFORMATEX);
        format.Samples.wValidBitsPerSample = 32;
        format.dwChannelMask = channels_ == 1 ? SPEAKER_FRONT_CENTER
                               : channels_ == 2 ? (SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT)
                                                : 0;
        format.SubFormat = KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
        hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                                AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
                                    AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                                kBufferDuration, 0, &format.Format, nullptr);
    }
    if (SUCCEEDED(hr)) {
        hr = client->SetEventHandle(bufferEvent);
    }
    if (SUCCEEDED(hr)) {
        hr = client->GetBufferSize(&bufferFrames);
    }
    if (SUCCEEDED(hr)) {
        hr = client->GetService(IID_PPV_ARGS(&render));
    }
    if (SUCCEEDED(hr)) {
        hr = client->GetService(IID_PPV_ARGS(&clock));
    }
    if (SUCCEEDED(hr)) {
        hr = clock->GetFrequency(&clockFrequency);
    }
    if (SUCCEEDED(hr)) {
        client->GetService(IID_PPV_ARGS(&volume));  // 音量の部品が無くても再生はできる。
    }

    // open()へ初期化の結果を知らせる。失敗(出力装置が無いなど)なら音声なしとして扱い、スレッドを終える。
    {
        std::lock_guard<std::mutex> lock(mutex_);
        initState_ = SUCCEEDED(hr) ? 1 : -1;
    }
    initDone_.notify_all();
    if (FAILED(hr)) {
        CloseHandle(bufferEvent);
        if (SUCCEEDED(comResult)) {
            CoUninitialize();
        }
        return;
    }

    static const LONGLONG qpcFrequency = ticksPerSecond();
    bool playing = false;
    for (;;) {
        const HANDLE handles[] = {commandEvent_, bufferEvent};
        WaitForMultipleObjects(2, handles, FALSE, 50);

        Command command;
        long long commandTime;
        bool applyVolume;
        float volumeLevel;
        bool mutedNow;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            command = command_;
            command_ = Command::None;
            commandTime = commandTime_;
            applyVolume = volumeDirty_;
            volumeDirty_ = false;
            volumeLevel = volume_;
            mutedNow = muted_;
        }
        if (command == Command::Quit) {
            break;
        }
        if (applyVolume && volume) {
            volume->SetMasterVolume(volumeLevel, nullptr);
            volume->SetMute(mutedNow, nullptr);
        }
        if (command == Command::Stop || command == Command::Start) {
            client->Stop();
            client->Reset();  // 出力装置に残っている音を捨て、再生位置を0に戻す。
            playing = false;
            std::lock_guard<std::mutex> lock(mutex_);
            playing_ = false;
            positionValid_ = false;
        }
        if (command == Command::Start) {
            seek(commandTime);
            // 始める前にバッファを満たしておく(始めた直後に音が途切れないように)。
            BYTE* data = nullptr;
            if (SUCCEEDED(render->GetBuffer(bufferFrames, &data))) {
                fill(reinterpret_cast<float*>(data), bufferFrames);
                render->ReleaseBuffer(bufferFrames, 0);
            }
            client->Start();
            playing = true;
            std::lock_guard<std::mutex> lock(mutex_);
            playing_ = true;
            startMediaTime_ = commandTime;
        }
        if (!playing) {
            continue;
        }

        // 再生中は、空いた分だけデコードした音声を書き足す。
        UINT32 padding = 0;
        if (SUCCEEDED(client->GetCurrentPadding(&padding)) && padding < bufferFrames) {
            const UINT32 frames = bufferFrames - padding;
            BYTE* data = nullptr;
            if (SUCCEEDED(render->GetBuffer(frames, &data))) {
                fill(reinterpret_cast<float*>(data), frames);
                render->ReleaseBuffer(frames, 0);
            }
        }
        // 今スピーカーから出ている位置を測り、映像側が読めるように記録する。
        UINT64 devicePosition = 0;
        UINT64 qpcPosition = 0;  // 100ns単位の時刻(QueryPerformanceCounterを換算したもの)
        if (SUCCEEDED(clock->GetPosition(&devicePosition, &qpcPosition)) && devicePosition > 0) {
            std::lock_guard<std::mutex> lock(mutex_);
            positionMedia_ = startMediaTime_ +
                             static_cast<long long>(devicePosition * 10000000 / clockFrequency);
            positionQpc_ = static_cast<long long>(qpcPosition * qpcFrequency / 10000000);
            positionValid_ = true;
        }
    }

    client->Stop();
    CloseHandle(bufferEvent);
    if (SUCCEEDED(comResult)) {
        CoUninitialize();
    }
}

}  // namespace frameplayer
