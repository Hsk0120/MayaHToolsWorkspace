/**
 * @file VideoView.cpp
 * @brief 映像表示用の子ウィンドウと描画スレッドの実装。
 */
#include "app/VideoView.h"

#include "core/Util.h"

#include "core/TraceLog.h"

#include <objbase.h>
#include <wingdi.h>

#include <algorithm>
#include <cmath>
#include <climits>
#include <cstdio>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

constexpr wchar_t kClassName[] = L"FramePlayerVideoView";
const D2D1_COLOR_F kText = {230 / 255.0f, 230 / 255.0f, 230 / 255.0f, 1.0f};
const D2D1_COLOR_F kBox = {58 / 255.0f, 58 / 255.0f, 58 / 255.0f, 0.9f};
constexpr UINT kSwapChainFlags = DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;
constexpr int kPresentRetries = 25;  ///< 表示の順番待ちが詰まっているときにやり直す回数(2msずつ、最大約50ms)。

/**
 * @brief 枠の中に縦横比を保って最大の大きさで収まる矩形を求める。
 * @param area 収める枠。
 * @param width 画像の幅。
 * @param height 画像の高さ。
 * @return 枠の中央に配置した矩形。
 */
D2D1_RECT_F fitRect(const D2D1_RECT_F& area, int width, int height) {
    const float areaWidth = area.right - area.left;
    const float areaHeight = area.bottom - area.top;
    float w = areaWidth;
    float h = w * height / width;
    if (h > areaHeight) {
        h = areaHeight;
        w = h * width / height;
    }
    // 画素の境目に合わせて、拡大縮小の後もにじまないようにする。
    const float left = std::floor(area.left + (areaWidth - w) / 2);
    const float top = std::floor(area.top + (areaHeight - h) / 2);
    return D2D1::RectF(left, top, left + std::floor(w), top + std::floor(h));
}

/**
 * @brief 枠の中に縦横比を保って収めた範囲を、画素の矩形で返す。
 * @param area 収める枠。
 * @param width 画像の幅。
 * @param height 画像の高さ。
 * @return 矩形。
 */
RECT fitPixels(const D2D1_RECT_F& area, int width, int height) {
    const D2D1_RECT_F r = fitRect(area, width, height);
    return RECT{static_cast<LONG>(r.left), static_cast<LONG>(r.top), static_cast<LONG>(r.right),
                static_cast<LONG>(r.bottom)};
}

/**
 * @brief sRGBの値をリニアな値にする(IEC 61966-2-1)。
 * @param v sRGBの値(0〜1)。
 * @return リニアな値。
 */
float srgbToLinear(float v) {
    return v <= 0.04045f ? v / 12.92f : std::pow((v + 0.055f) / 1.055f, 2.4f);
}

/**
 * @brief モニターでWindowsが使うSDRの白の明るさ(HDRが有効なときの「SDRコンテンツの明るさ」の設定)を返す。
 * @param monitor 対象のモニター。
 * @return 明るさ(cd/m²)。分からなければ80。
 */
float sdrWhiteNits(HMONITOR monitor) {
    MONITORINFOEXW info{};
    info.cbSize = sizeof(info);
    if (!GetMonitorInfoW(monitor, &info)) {
        return 80.0f;
    }
    UINT32 pathCount = 0;
    UINT32 modeCount = 0;
    if (GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &pathCount, &modeCount) != ERROR_SUCCESS) {
        return 80.0f;
    }
    std::vector<DISPLAYCONFIG_PATH_INFO> paths(pathCount);
    std::vector<DISPLAYCONFIG_MODE_INFO> modes(modeCount);
    if (QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &pathCount, paths.data(), &modeCount, modes.data(), nullptr) !=
        ERROR_SUCCESS) {
        return 80.0f;
    }
    // GDIの画面の名前(\\.\DISPLAY1など)が同じ経路を探し、その出力先の設定を読む。
    for (UINT32 i = 0; i < pathCount; ++i) {
        DISPLAYCONFIG_SOURCE_DEVICE_NAME source{};
        source.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
        source.header.size = sizeof(source);
        source.header.adapterId = paths[i].sourceInfo.adapterId;
        source.header.id = paths[i].sourceInfo.id;
        if (DisplayConfigGetDeviceInfo(&source.header) != ERROR_SUCCESS ||
            wcscmp(source.viewGdiDeviceName, info.szDevice) != 0) {
            continue;
        }
        DISPLAYCONFIG_SDR_WHITE_LEVEL white{};
        white.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL;
        white.header.size = sizeof(white);
        white.header.adapterId = paths[i].targetInfo.adapterId;
        white.header.id = paths[i].targetInfo.id;
        if (DisplayConfigGetDeviceInfo(&white.header) == ERROR_SUCCESS && white.SDRWhiteLevel > 0) {
            return white.SDRWhiteLevel / 1000.0f * 80.0f;  // 1000が80cd/m²。
        }
    }
    return 80.0f;
}

/**
 * @brief タイムライン上のコマ番号の表示時刻を返す。動画の外は、端のコマから1コマの長さずつ延ばして求める。
 * @param clip 1本目の動画。
 * @param index コマ番号(1本目の1コマ目が0。負や最後のコマより後も可)。
 * @param period 1コマの長さ(100ns単位)。
 * @return 表示時刻(100ns単位)。動画の中ならclip.frameTime()と同じ。
 */
long long timelineTime(const Clip& clip, int index, long long period) {
    const int last = clip.frameCount() - 1;
    if (index < 0) {
        return clip.frameTime(0) + static_cast<long long>(index) * period;
    }
    if (index > last) {
        return clip.frameTime(last) + static_cast<long long>(index - last) * period;
    }
    return clip.frameTime(index);
}

/**
 * @brief 指定した時刻に表示すべきタイムライン上のコマ番号を返す(timelineTime()の逆)。
 * @param clip 1本目の動画。
 * @param time 時刻(100ns単位)。
 * @param period 1コマの長さ(100ns単位)。
 * @return コマ番号。動画より前なら負、後なら最後のコマより大きい値。
 */
int timelineFrameAt(const Clip& clip, long long time, long long period) {
    const int last = clip.frameCount() - 1;
    const long long firstTime = clip.frameTime(0);
    const long long lastTime = clip.frameTime(last);
    if (time < firstTime) {
        return -static_cast<int>((firstTime - time + period - 1) / period);  // 切り下げ(負の側)。
    }
    if (time >= lastTime + period) {
        return last + static_cast<int>((time - lastTime) / period);
    }
    return clip.frameAtTime(time);
}

}  // namespace

VideoView::~VideoView() {
    shutdown();
    if (wakeEvent_) {
        CloseHandle(wakeEvent_);
    }
}

bool VideoView::create(HINSTANCE instance, HWND parent, UINT notifyMessage, std::shared_ptr<GpuDevice> gpu) {
    parent_ = parent;
    notifyMessage_ = notifyMessage;
    gpu_ = std::move(gpu);

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = &VideoView::windowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.lpszClassName = kClassName;
    RegisterClassExW(&wc);  // 2回目以降は失敗するが、登録済みなので問題ない。

    // 子ウィンドウはUIスレッドで作る(メッセージはUIスレッドに届く)。描画だけを描画スレッドで行う。
    hwnd_ = CreateWindowExW(0, kClassName, L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS, 0, 0, 1, 1, parent, nullptr,
                            instance, this);
    if (!hwnd_) {
        return false;
    }
    wakeEvent_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    thread_ = std::thread(&VideoView::renderLoop, this);
    return true;
}

void VideoView::shutdown() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stopThread_ = true;
    }
    wake();
    if (thread_.joinable()) {
        thread_.join();
    }
}

void VideoView::setBounds(const RECT& bounds) {
    MoveWindow(hwnd_, bounds.left, bounds.top, std::max(1L, bounds.right - bounds.left),
               std::max(1L, bounds.bottom - bounds.top), FALSE);
    wake();
}

void VideoView::setClip(std::shared_ptr<Clip> clip, std::shared_ptr<AudioPlayer> audio) {
    std::shared_ptr<AudioPlayer> previousAudio;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        clip_ = std::move(clip);
        compare_.reset();  // 1本目を差し替えたら比較もやめる(呼び出し側が必要なら設定し直す)。
        previousAudio = std::move(audio_);
        audio_ = std::move(audio);
        requested_ = 0;
        playRequested_ = false;
    }
    if (previousAudio) {
        previousAudio->stop();
    }
    playing_ = false;
    current_ = 0;
    wake();
}

void VideoView::setCompareClip(std::shared_ptr<Clip> clip) {
    stop();
    std::shared_ptr<Clip> previous;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        previous = std::move(compare_);
        compare_ = std::move(clip);
        if (compare_) {
            compare_->setPlayhead(std::clamp(requested_ + compareOffset_, 0, compare_->frameCount() - 1),
                                  Clip::Direction::Forward, false);
        }
    }
    wake();
    // 前の2本目はここで手放す(最後の参照なら裏の読み込みスレッドが止まる)。
}

void VideoView::setCompareOffset(int offset) {
    compareOffset_ = offset;
    std::shared_ptr<Clip> compare;
    int requested = 0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        compare = compare_;
        requested = requested_;
    }
    if (compare) {
        compare->setPlayhead(std::clamp(requested + offset, 0, compare->frameCount() - 1), Clip::Direction::Forward,
                             false);
    }
    wake();
}

void VideoView::showFrame(int index, Clip::Direction direction, std::optional<int> compareOffset) {
    std::shared_ptr<Clip> clip;
    std::shared_ptr<Clip> compare;
    std::shared_ptr<AudioPlayer> audio;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        clip = clip_;
        compare = compare_;
        audio = audio_;
        if (!clip) {
            return;
        }
        requested_ = index;
        playRequested_ = false;
        if (compareOffset) {
            compareOffset_ = *compareOffset;
        }
    }
    playing_ = false;
    current_ = index;
    if (audio) {
        audio->stop();  // コマ送り・スライダー操作では音を鳴らさない。
    }
    // 動画の外を表示するときは、近い方の端の周りを先読みしておく(動画の中へ戻ってきたときにすぐ出せるように)。
    clip->setPlayhead(std::clamp(index, 0, clip->frameCount() - 1), direction, false);
    if (compare) {
        compare->setPlayhead(std::clamp(index + compareOffset_, 0, compare->frameCount() - 1), direction, false);
    }
    wake();
}

void VideoView::setPlaybackRange(int first, int last) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        playFirst_ = first;
        playLast_ = std::max(first, last);
    }
    wake();
}

void VideoView::play(double rate) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!clip_ || playLast_ <= playFirst_) {
            return;  // 1コマだけの範囲は再生しない。
        }
        // 再生範囲の外、または範囲の最後のコマで再生を始めたら、範囲の最初から(Mayaと同じ)。
        const int first = playFirst_;
        const int last = playLast_;
        int start = current_;
        if (start < first || start >= last) {
            start = first;
        }
        requested_ = start;
        playStartFrame_ = start;
        ++playSession_;  // 描画スレッドが新しい再生として始める(音声の開始も描画スレッドが行う)。
        rate_ = rate > 0.0 ? rate : 24.0;
        playRequested_ = true;
    }
    dropped_ = 0;
    playing_ = true;
    wake();
}

void VideoView::stop() {
    std::shared_ptr<AudioPlayer> audio;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        playRequested_ = false;
        requested_ = current_;
        audio = audio_;
    }
    if (audio) {
        audio->stop();
    }
    playing_ = false;
    wake();
}

void VideoView::wake() {
    if (wakeEvent_) {
        SetEvent(wakeEvent_);
    }
}

void VideoView::notifyParent() {
    if (!notifyPending_.exchange(true)) {
        PostMessageW(parent_, notifyMessage_, 0, 0);
    }
}

LRESULT CALLBACK VideoView::windowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    if (message == WM_NCCREATE) {
        auto* create = reinterpret_cast<CREATESTRUCTW*>(lParam);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create->lpCreateParams));
    }
    auto* self = reinterpret_cast<VideoView*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    switch (message) {
    case WM_ERASEBKGND:
        return 1;  // 描画スレッドが全面を描くので消去しない。
    case WM_PAINT:
        // 再描画の要求は描画スレッドに任せる。ここでは要求を済んだことにするだけ。
        ValidateRect(hwnd, nullptr);
        if (self) {
            self->wake();
        }
        return 0;
    case WM_NCHITTEST:
        return HTTRANSPARENT;  // マウス操作やファイルのドロップは親ウィンドウで受け取る。
    default:
        return DefWindowProcW(hwnd, message, wParam, lParam);
    }
}

bool VideoView::createDevice() {
    backBuffer_.Reset();
    swapChain_.Reset();
    context_.Reset();
    target_.Reset();
    d3dContext_.Reset();
    scRgb_ = false;
    for (PaneCache& cache : paneCaches_) {
        cache = PaneCache{};
    }
    device_.Reset();
    if (frameWaitable_) {
        CloseHandle(frameWaitable_);
        frameWaitable_ = nullptr;
    }

    // デコード・キャッシュと同じデバイスで描く(GPUのメモリにあるコマをそのまま使うため)。
    // 共有のデバイスが無ければ自分で作り、GPUで作れなければWindowsに入っているCPU用の代わり(WARP)で作る。
    HRESULT hr = E_FAIL;
    if (gpu_) {
        device_ = gpu_->device();
        hr = S_OK;
    } else {
        for (D3D_DRIVER_TYPE type : {D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP}) {
            hr = D3D11CreateDevice(nullptr, type, nullptr, D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0,
                                   D3D11_SDK_VERSION, &device_, nullptr, nullptr);
            if (SUCCEEDED(hr)) {
                break;
            }
        }
    }
    if (FAILED(hr)) {
        return false;
    }
    device_->GetImmediateContext(&d3dContext_);
    if (!renderer_.create(device_.Get())) {
        return false;
    }

    ComPtr<IDXGIDevice> dxgiDevice;
    ComPtr<IDXGIAdapter> adapter;
    ComPtr<IDXGIFactory2> factory;
    hr = device_.As(&dxgiDevice);
    if (SUCCEEDED(hr)) {
        hr = dxgiDevice->GetAdapter(&adapter);
    }
    if (SUCCEEDED(hr)) {
        hr = adapter->GetParent(IID_PPV_ARGS(&factory));
    }
    if (FAILED(hr)) {
        return false;
    }

    // フリップ方式のスワップチェーン。待機用オブジェクトで「次の画面更新に描ける時」を知り、遅延を1コマに抑える。
    RECT client;
    GetClientRect(hwnd_, &client);
    DXGI_SWAP_CHAIN_DESC1 desc{};
    desc.Width = std::max<UINT>(1, client.right - client.left);
    desc.Height = std::max<UINT>(1, client.bottom - client.top);
    desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.BufferCount = 2;
    desc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
    desc.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
    desc.Flags = kSwapChainFlags;
    ComPtr<IDXGISwapChain1> swapChain1;
    hr = factory->CreateSwapChainForHwnd(device_.Get(), hwnd_, &desc, nullptr, nullptr, &swapChain1);
    if (SUCCEEDED(hr)) {
        hr = swapChain1.As(&swapChain_);
    }
    if (FAILED(hr)) {
        return false;
    }
    factory->MakeWindowAssociation(hwnd_, DXGI_MWA_NO_ALT_ENTER);
    swapChain_->SetMaximumFrameLatency(1);
    frameWaitable_ = swapChain_->GetFrameLatencyWaitableObject();
    swapWidth_ = desc.Width;
    swapHeight_ = desc.Height;

    // Direct2Dは描画スレッドだけが使うので、単一スレッド用で作る。
    D2D1_FACTORY_OPTIONS options{};
    hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, __uuidof(ID2D1Factory3), &options,
                           reinterpret_cast<void**>(d2dFactory_.ReleaseAndGetAddressOf()));
    ComPtr<ID2D1Device2> d2dDevice;
    if (SUCCEEDED(hr)) {
        hr = d2dFactory_->CreateDevice(dxgiDevice.Get(), &d2dDevice);
    }
    if (SUCCEEDED(hr)) {
        hr = d2dDevice->CreateDeviceContext(D2D1_DEVICE_CONTEXT_OPTIONS_NONE, &context_);
    }
    if (FAILED(hr)) {
        return false;
    }
    context_->SetDpi(96.0f, 96.0f);  // 座標を画素単位で扱う。

    if (!writeFactory_) {
        DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED, __uuidof(IDWriteFactory),
                            reinterpret_cast<IUnknown**>(writeFactory_.GetAddressOf()));
    }
    if (writeFactory_) {
        const float size = 14.0f * GetDpiForWindow(hwnd_) / 72.0f;
        writeFactory_->CreateTextFormat(L"Segoe UI", nullptr, DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_STYLE_NORMAL,
                                        DWRITE_FONT_STRETCH_NORMAL, size, L"ja-jp", textFormat_.ReleaseAndGetAddressOf());
        if (textFormat_) {
            textFormat_->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
            textFormat_->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
        }
        writeFactory_->CreateTextFormat(L"Segoe UI", nullptr, DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_STYLE_NORMAL,
                                        DWRITE_FONT_STRETCH_NORMAL, size * 0.8f, L"ja-jp",
                                        labelFormat_.ReleaseAndGetAddressOf());
        writeFactory_->CreateTextFormat(L"Segoe UI", nullptr, DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_STYLE_NORMAL,
                                        DWRITE_FONT_STRETCH_NORMAL, size * 0.7f, L"ja-jp",
                                        detailFormat_.ReleaseAndGetAddressOf());
        if (detailFormat_) {
            detailFormat_->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
            detailFormat_->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
        }
        if (labelFormat_) {
            labelFormat_->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
            labelFormat_->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
            labelFormat_->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP);
        }
        writeFactory_->CreateTextFormat(L"Segoe UI", nullptr, DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_STYLE_NORMAL,
                                        DWRITE_FONT_STRETCH_NORMAL, size * 0.7f, L"ja-jp",
                                        infoFormat_.ReleaseAndGetAddressOf());
        if (infoFormat_) {
            infoFormat_->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
            infoFormat_->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_NEAR);
            infoFormat_->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP);
        }
    }
    return createTarget();
}

bool VideoView::createTarget() {
    // 映像はDirect3Dで、文字と枠はDirect2Dで、同じ裏画面に描く。
    ComPtr<ID3D11Texture2D> buffer;
    ComPtr<IDXGISurface> surface;
    if (FAILED(swapChain_->GetBuffer(0, IID_PPV_ARGS(&buffer))) || FAILED(buffer.As(&surface)) ||
        FAILED(device_->CreateRenderTargetView(buffer.Get(), nullptr, &backBuffer_))) {
        return false;
    }
    const DXGI_FORMAT format = scRgb_ ? DXGI_FORMAT_R16G16B16A16_FLOAT : DXGI_FORMAT_B8G8R8A8_UNORM;
    const D2D1_BITMAP_PROPERTIES1 properties = D2D1::BitmapProperties1(
        D2D1_BITMAP_OPTIONS_TARGET | D2D1_BITMAP_OPTIONS_CANNOT_DRAW, D2D1::PixelFormat(format, D2D1_ALPHA_MODE_IGNORE),
        96.0f, 96.0f);
    if (FAILED(context_->CreateBitmapFromDxgiSurface(surface.Get(), &properties, &target_))) {
        return false;
    }
    context_->SetTarget(target_.Get());
    // 16bit浮動小数点の描画先ではClearTypeが使えないので、文字は白黒の濃淡で滑らかにする。
    context_->SetTextAntialiasMode(scRgb_ ? D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE : D2D1_TEXT_ANTIALIAS_MODE_DEFAULT);
    return true;
}

bool VideoView::setOutputFormat(bool scRgb) {
    // 裏画面への参照をすべて外してから形式を変える(外さないとResizeBuffersが失敗する)。
    context_->SetTarget(nullptr);
    target_.Reset();
    backBuffer_.Reset();
    d3dContext_->OMSetRenderTargets(0, nullptr, nullptr);
    d3dContext_->Flush();
    auto apply = [&](bool wide) {
        const DXGI_FORMAT format = wide ? DXGI_FORMAT_R16G16B16A16_FLOAT : DXGI_FORMAT_B8G8R8A8_UNORM;
        if (FAILED(swapChain_->ResizeBuffers(0, swapWidth_, swapHeight_, format, kSwapChainFlags))) {
            return false;
        }
        // scRGBはリニアなBT.709(1.0が80cd/m²)、8bitはsRGB(Windowsの既定)として画面に合成してもらう。
        const DXGI_COLOR_SPACE_TYPE space =
            wide ? DXGI_COLOR_SPACE_RGB_FULL_G10_NONE_P709 : DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709;
        UINT support = 0;
        if (FAILED(swapChain_->CheckColorSpaceSupport(space, &support)) ||
            !(support & DXGI_SWAP_CHAIN_COLOR_SPACE_SUPPORT_FLAG_PRESENT) || FAILED(swapChain_->SetColorSpace1(space))) {
            return !wide;  // 8bitは既定の色空間のままでよい。
        }
        return true;
    };
    bool ok = apply(scRgb);
    if (!ok && scRgb) {
        scRgbUnavailable_ = true;  // 以後は8bitの描画先に、画面に合わせた値を出す。
        ok = apply(false);
        scRgb = false;
    }
    scRgb_ = scRgb;
    traceLog("output format scRGB=%d ok=%d", scRgb ? 1 : 0, ok ? 1 : 0);
    return ok && createTarget() && scRgb_ == scRgb;
}

void VideoView::updateDisplayState() {
    const HMONITOR monitor = MonitorFromWindow(hwnd_, MONITOR_DEFAULTTONEAREST);
    const bool stale = displayDirty_.exchange(false) || monitor != displayMonitor_ || !displayFactory_ ||
                       !displayFactory_->IsCurrent();
    if (!stale) {
        return;
    }
    displayMonitor_ = monitor;
    // 画面の構成が変わると古い工場は古い状態を返すので、毎回作り直してモニターを探す。
    displayFactory_.Reset();
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&displayFactory_)))) {
        return;
    }
    bool hdr = false;
    ComPtr<IDXGIAdapter1> adapter;
    for (UINT a = 0; displayFactory_->EnumAdapters1(a, adapter.ReleaseAndGetAddressOf()) == S_OK; ++a) {
        ComPtr<IDXGIOutput> output;
        for (UINT o = 0; adapter->EnumOutputs(o, output.ReleaseAndGetAddressOf()) == S_OK; ++o) {
            ComPtr<IDXGIOutput6> output6;
            DXGI_OUTPUT_DESC1 desc{};
            if (SUCCEEDED(output.As(&output6)) && SUCCEEDED(output6->GetDesc1(&desc)) && desc.Monitor == monitor) {
                hdr = desc.ColorSpace == DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020;
            }
        }
    }
    display_.hdr = hdr;
    display_.sdrWhiteNits = hdr ? sdrWhiteNits(monitor) : 80.0f;
    displayHdr_ = hdr;
    traceLog("display hdr=%d sdrWhite=%.0f", hdr ? 1 : 0, display_.sdrWhiteNits);
}

D2D1_COLOR_F VideoView::uiColor(const D2D1_COLOR_F& color) const {
    if (!scRgb_) {
        return color;
    }
    const float scale = display_.hdr ? display_.sdrWhiteNits / 80.0f : 1.0f;
    return D2D1::ColorF(srgbToLinear(color.r) * scale, srgbToLinear(color.g) * scale, srgbToLinear(color.b) * scale,
                        color.a);
}

std::wstring VideoView::colorInfoText(const ColorInfo& color, FrameRenderer::Output output) const {
    std::wstring text = L"色: " + describeColor(color) + L"\n出力: ";
    wchar_t buffer[160];
    switch (output) {
    case FrameRenderer::Output::Direct8:
        text += L"値をそのまま(8bit)";
        break;
    case FrameRenderer::Output::Encoded8:
        text += L"画面に合わせて変換(8bit)";
        break;
    case FrameRenderer::Output::ScRgb:
    default:
        if (color.isHdr() && display_.hdr) {
            text += L"HDRの画面へ明るさそのまま(scRGB)";
        } else if (color.isHdr()) {
            const float peak = color.maxContentNits > 0.0f ? color.maxContentNits : 1000.0f;
            std::swprintf(buffer, 160, L"SDRの画面に収める(最大%.0fcd/m²→基準の白203cd/m²、BT.2390)", peak);
            text += buffer;
        } else if (display_.hdr) {
            std::swprintf(buffer, 160, L"HDRの画面のSDRの白(%.0fcd/m²)で(scRGB)", display_.sdrWhiteNits);
            text += buffer;
        } else {
            text += color.isPassThrough() ? L"値をそのまま(scRGB)" : L"色域をBT.709へ変換(scRGB)";
        }
        break;
    }
    return text;
}

bool VideoView::resizeIfNeeded() {
    RECT client;
    GetClientRect(hwnd_, &client);
    const UINT width = std::max<UINT>(1, client.right - client.left);
    const UINT height = std::max<UINT>(1, client.bottom - client.top);
    if (width == swapWidth_ && height == swapHeight_) {
        return true;
    }
    // 裏画面への参照をすべて外してから大きさを変える(外さないとResizeBuffersが失敗する)。
    context_->SetTarget(nullptr);
    target_.Reset();
    backBuffer_.Reset();
    d3dContext_->OMSetRenderTargets(0, nullptr, nullptr);
    d3dContext_->Flush();
    if (FAILED(swapChain_->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, kSwapChainFlags))) {
        return false;
    }
    swapWidth_ = width;
    swapHeight_ = height;
    return createTarget();
}

bool VideoView::draw(const PaneState* panes, int paneCount, int compareOffset) {
    // 共有のGPUデバイスを使うときは、描画1回分が裏の読み込み(GPUへの写し・縮小)と混ざらないよう鍵で囲む。
    std::unique_ptr<GpuDevice::Lock> lock;
    if (gpu_) {
        lock = gpu_->lockPtr();
    }
    updateDisplayState();

    // 各表示枠の色の解釈(手動の指定を当てはめたもの)と、描画先の形式を決める。
    ColorInfo colors[2];
    bool wantScRgb = false;
    for (int i = 0; i < paneCount; ++i) {
        const PaneState& pane = panes[i];
        if (pane.clip && pane.frame && !pane.outOfRange) {
            colors[i] = applyOverride(pane.frame->color, pane.clip->colorOverride());
            wantScRgb = wantScRgb || FrameRenderer::needsScRgb(colors[i], display_);
        }
    }
    wantScRgb = wantScRgb && !scRgbUnavailable_;
    if (wantScRgb != scRgb_ && !setOutputFormat(wantScRgb) && !target_) {
        return false;
    }

    // 表示枠の配置。比較中は左右に分けて並べ(間に少し隙間)、各枠の下に文字の行を取る。
    const float scaleDpi = GetDpiForWindow(hwnd_) / 96.0f;
    const D2D1_RECT_F area = D2D1::RectF(0, 0, static_cast<float>(swapWidth_), static_cast<float>(swapHeight_));
    D2D1_RECT_F imageAreas[2] = {area, area};
    D2D1_RECT_F labelAreas[2] = {};
    if (paneCount == 2) {
        const float gap = 6.0f * scaleDpi;
        const float middle = (area.left + area.right) / 2;
        const D2D1_RECT_F halves[2] = {D2D1::RectF(area.left, area.top, middle - gap / 2, area.bottom),
                                       D2D1::RectF(middle + gap / 2, area.top, area.right, area.bottom)};
        for (int i = 0; i < 2; ++i) {
            labelAreas[i] = D2D1::RectF(halves[i].left, halves[i].bottom - 24 * scaleDpi, halves[i].right, halves[i].bottom);
            imageAreas[i] = D2D1::RectF(halves[i].left, halves[i].top, halves[i].right, labelAreas[i].top);
        }
    }

    // 映像(Direct3D)。
    const float black[4] = {0.0f, 0.0f, 0.0f, 1.0f};  // Keyframe Proと同じく映像の周りは黒。
    d3dContext_->ClearRenderTargetView(backBuffer_.Get(), black);
    if (panes[0].clip) {
        for (int i = 0; i < paneCount; ++i) {
            drawPaneImage(panes[i], colors[i], paneCaches_[i], imageAreas[i]);
        }
    }

    // 文字と枠(Direct2D)。
    context_->BeginDraw();
    context_->SetTransform(D2D1::Matrix3x2F::Identity());
    if (!panes[0].clip && textFormat_) {
        ComPtr<ID2D1SolidColorBrush> textBrush;
        context_->CreateSolidColorBrush(uiColor(kText), &textBrush);
        static const wchar_t message[] = L"動画ファイルをドロップしてください";
        context_->DrawText(message, static_cast<UINT32>(std::size(message) - 1), textFormat_.Get(), area,
                           textBrush.Get());
    } else {
        for (int i = 0; i < paneCount; ++i) {
            const PaneState& pane = panes[i];
            std::wstring label;
            if (paneCount == 2) {
                wchar_t text[512];
                const std::wstring name = pane.clip ? fileNameOf(pane.clip->path()) : std::wstring();
                const int count = pane.clip ? pane.clip->frameCount() : 0;
                if (i == 0 && pane.outOfRange) {
                    std::swprintf(text, 512, L"%ls   範囲外 / %d", name.c_str(), count - 1 + frameNumberStart_);
                } else if (i == 0) {
                    std::swprintf(text, 512, L"%ls   %d / %d", name.c_str(), pane.index + frameNumberStart_,
                                  count - 1 + frameNumberStart_);
                } else if (pane.outOfRange) {
                    std::swprintf(text, 512, L"%ls   範囲外 / %d   (オフセット %+df)", name.c_str(),
                                  count - 1 + frameNumberStart_, compareOffset);
                } else {
                    std::swprintf(text, 512, L"%ls   %d / %d   (オフセット %+df)", name.c_str(),
                                  pane.index + frameNumberStart_, count - 1 + frameNumberStart_, compareOffset);
                }
                label = text;
            }
            std::wstring info;
            if (showColorInfo_ && pane.clip && pane.frame && !pane.outOfRange) {
                info = colorInfoText(colors[i], FrameRenderer::chooseOutput(colors[i], display_, scRgb_));
            }
            drawPaneText(pane, imageAreas[i], labelAreas[i], label, outOfRangeDetail(pane, i == 0 ? 0 : -compareOffset),
                         info);
        }
    }
    if (context_->EndDraw() == static_cast<HRESULT>(D2DERR_RECREATE_TARGET)) {
        return false;
    }
    // 表示する。画面の書き換えへの合わせ込みは、描く前にframeWaitable_で(眠って)待つことで行い、
    // Present自体は画面の書き換えを待たない指定(同期間隔0)にする。同期間隔1で待たせると、画面の合成が
    // 遅い環境(リモート接続や仮想ディスプレイで1秒に数回しか合成されない場合など)では、ドライバーが
    // 1回あたり約250msもCPUを使い続けて待つことを確かめた(待たない指定DO_NOT_WAITも効かなかった)。
    // ウィンドウ表示ではWindowsの画面合成が最新のコマを次の書き換えで表示するので、画面が裂けることはない。
    // 表示の順番待ちが詰まっていれば、少し眠ってからやり直す。
    HRESULT hr = swapChain_->Present(0, DXGI_PRESENT_DO_NOT_WAIT);
    const LONGLONG retryTicks = ticksPerSecond() / 500;  // 2ms。
    for (int retry = 0; hr == DXGI_ERROR_WAS_STILL_DRAWING && retry < kPresentRetries; ++retry) {
        sleepTicks(retryTicks, false);
        hr = swapChain_->Present(0, DXGI_PRESENT_DO_NOT_WAIT);
    }
    if (hr == DXGI_ERROR_WAS_STILL_DRAWING) {
        return true;  // 合成が追いつかない。このコマの表示は見送り、次のコマで描き直す。
    }
    if (hr == DXGI_ERROR_DEVICE_REMOVED || hr == DXGI_ERROR_DEVICE_RESET) {
        return false;
    }
    if (hr == DXGI_STATUS_OCCLUDED) {
        Sleep(16);
    }
    return true;
}

std::wstring VideoView::outOfRangeDetail(const PaneState& pane, int shift) const {
    if (!pane.outOfRange || !pane.clip) {
        return std::wstring();
    }
    const long long first = static_cast<long long>(frameNumberStart_) + shift;
    wchar_t text[96];
    std::swprintf(text, 96, L"動画は %lld〜%lld", first, first + pane.clip->frameCount() - 1);
    return text;
}

void VideoView::drawPaneImage(const PaneState& pane, const ColorInfo& color, PaneCache& cache,
                              const D2D1_RECT_F& area) {
    const std::shared_ptr<const Frame>& frame = pane.outOfRange ? nullptr : pane.frame;
    if (!frame || frame->width <= 0 || frame->height <= 0) {
        return;
    }
    // コマが変わったとき(または色の解釈を変えたとき)だけRGBへ戻し直す。拡大縮小と画面への合わせ込みは毎回行う。
    if (renderer_.prepare(d3dContext_.Get(), frame, color, cache.image)) {
        renderer_.present(d3dContext_.Get(), backBuffer_.Get(), fitPixels(area, frame->width, frame->height),
                          cache.image, FrameRenderer::chooseOutput(color, display_, scRgb_), display_);
    }
}

void VideoView::drawPaneText(const PaneState& pane, const D2D1_RECT_F& area, const D2D1_RECT_F& labelArea,
                             const std::wstring& label, const std::wstring& detail, const std::wstring& info) {
    const float scaleDpi = GetDpiForWindow(hwnd_) / 96.0f;
    ComPtr<ID2D1SolidColorBrush> textBrush;
    context_->CreateSolidColorBrush(uiColor(kText), &textBrush);
    ComPtr<ID2D1SolidColorBrush> boxBrush;
    context_->CreateSolidColorBrush(uiColor(kBox), &boxBrush);
    // 表示中のコマが無いときは、直前の画像の上に知らせを重ねる(別のコマをそのコマとして見せないため)。
    const wchar_t* notice = pane.outOfRange ? L"範囲外"
                            : pane.broken   ? L"このコマはデコードできません"
                            : pane.loading  ? L"読み込み中…"
                                            : nullptr;
    if (notice && textFormat_) {
        const float cx = (area.left + area.right) / 2;
        const float cy = (area.top + area.bottom) / 2;
        const float halfWidth = std::min(130 * scaleDpi, (area.right - area.left) / 2);
        // 説明を添えるときは箱を下へ広げ、知らせの下に小さく出す。
        const bool hasDetail = !detail.empty() && detailFormat_;
        const float half = 20 * scaleDpi;
        const D2D1_RECT_F box =
            D2D1::RectF(cx - halfWidth, cy - half, cx + halfWidth, cy + half + (hasDetail ? 18 * scaleDpi : 0));
        context_->FillRectangle(box, boxBrush.Get());
        const D2D1_RECT_F noticeArea = D2D1::RectF(box.left, box.top, box.right, cy + half - (hasDetail ? 6 * scaleDpi : 0));
        context_->DrawText(notice, static_cast<UINT32>(wcslen(notice)), textFormat_.Get(), noticeArea, textBrush.Get());
        if (hasDetail) {
            const D2D1_RECT_F detailArea = D2D1::RectF(box.left, noticeArea.bottom, box.right, box.bottom - 6 * scaleDpi);
            context_->DrawText(detail.c_str(), static_cast<UINT32>(detail.size()), detailFormat_.Get(), detailArea,
                               textBrush.Get());
        }
    }

    if (!label.empty() && labelFormat_) {
        context_->DrawText(label.c_str(), static_cast<UINT32>(label.size()), labelFormat_.Get(), labelArea,
                           textBrush.Get());
    }

    // 色の情報は左上に、読みやすいよう半透明の箱の上に出す。
    if (!info.empty() && infoFormat_ && writeFactory_) {
        ComPtr<IDWriteTextLayout> layout;
        const float margin = 8 * scaleDpi;
        if (SUCCEEDED(writeFactory_->CreateTextLayout(info.c_str(), static_cast<UINT32>(info.size()), infoFormat_.Get(),
                                                      std::max(1.0f, area.right - area.left - margin * 2),
                                                      std::max(1.0f, area.bottom - area.top - margin * 2), &layout))) {
            DWRITE_TEXT_METRICS metrics{};
            layout->GetMetrics(&metrics);
            const float padding = 4 * scaleDpi;
            const D2D1_RECT_F box = D2D1::RectF(area.left + margin - padding, area.top + margin - padding,
                                                area.left + margin + metrics.width + padding,
                                                area.top + margin + metrics.height + padding);
            context_->FillRectangle(box, boxBrush.Get());
            context_->DrawTextLayout(D2D1::Point2F(area.left + margin, area.top + margin), layout.Get(), textBrush.Get());
        }
    }
}

void VideoView::sleepTicks(LONGLONG ticks, bool wakeOnSignal) {
    if (ticks <= 0) {
        return;
    }
    // 待機タイマーは100ns単位で、負の値は「今からの相対時間」を表す。
    LARGE_INTEGER due;
    due.QuadPart = -std::max<LONGLONG>(1, ticks * 10000000 / ticksPerSecond());
    if (!timer_ || !SetWaitableTimer(timer_, &due, 0, nullptr, nullptr, FALSE)) {
        Sleep(static_cast<DWORD>(std::max<LONGLONG>(1, ticks * 1000 / ticksPerSecond())));
        return;
    }
    const HANDLE handles[] = {timer_, wakeEvent_};
    WaitForMultipleObjects(wakeOnSignal ? 2 : 1, handles, FALSE, INFINITE);
}

void VideoView::renderLoop() {
    // Direct2D・DirectWriteはCOMの仕組みで作られるので、このスレッドでも初期化しておく。
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const LONGLONG frequency = ticksPerSecond();
    // 高精度の待機タイマー(Windows 10 1803以降)。作れなければ通常の精度のタイマーを使う。
    timer_ = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    if (!timer_) {
        timer_ = CreateWaitableTimerExW(nullptr, nullptr, 0, TIMER_ALL_ACCESS);
    }
    bool ready = createDevice();

    PaneState drawn[2];   // 最後に描いた内容(停止中に描き直しが必要かの判断に使う)。
    std::shared_ptr<AudioPlayer> sessionAudio;  // 今の再生で鳴らしている音声(途中で鳴らせなくなったら止める)。
    int drawnOffset = 0;
    int drawnGeneration = -1;  // 最後に描いたときのredrawGeneration_。
    int drawnPaneCount = 0;
    UINT drawnWidth = 0;
    UINT drawnHeight = 0;
    int shown = 0;            // 再生中に最後に表示した1本目のコマ番号(コマ落ちの計算用)。
    bool shownValid = false;  // shownが有効か(コマ番号は負もあり得るので、別に持つ)。
    const Clip* shownClip = nullptr;

    // 再生中の時計。sessionStartMedia(動画の時刻)をsessionStartTicks(PCの時刻)に再生し始めたものとして、
    // 経過時間から今表示すべき動画の時刻を求める。音声があれば、音声の再生位置に少しずつ合わせる。
    int session = -1;                 // 処理中の再生の番号(VideoView::playSession_と比べる)。
    long long sessionStartMedia = 0;  // 再生を始めた動画の時刻(100ns単位)。
    LONGLONG sessionStartTicks = 0;   // その時刻を表示し始めたPCの時刻(半コマ分早めてある。下記)。
    bool waitingForAudio = false;     // 音声が鳴り始めるのを待っている間はtrue(映像を進めない)。
    LONGLONG audioWaitSince = 0;

    // キャッシュに無いコマの代わりに、読み込み中に表示する画像を選ぶ。直前に描いた画像と、
    // キーフレームの縮小画像のうち、表示すべきコマに近い方を使う(1コマ送りなら直前の画像、
    // スライダーで遠くへ動かしたなら縮小画像になる)。
    auto choosePlaceholder = [](PaneState& pane, const Clip* clip, const PaneState& previous) {
        const bool hasPrevious = previous.clip == clip && previous.frame;
        const long long previousDistance =
            hasPrevious ? std::llabs(static_cast<long long>(previous.imageIndex) - pane.index) : LLONG_MAX;
        int previewIndex = -1;
        std::shared_ptr<const Frame> preview = clip->preview(pane.index, &previewIndex);
        const long long previewDistance =
            preview ? std::llabs(static_cast<long long>(previewIndex) - pane.index) : LLONG_MAX;
        if (preview && previewDistance < previousDistance) {
            pane.frame = std::move(preview);
            pane.imageIndex = previewIndex;
        } else if (hasPrevious) {
            pane.frame = previous.frame;
            pane.imageIndex = previous.imageIndex;
        } else {
            pane.imageIndex = -1;
        }
    };

    // 1本目のコマ番号から、2本目に表示する内容を作る(オフセットを足した結果が範囲外なら「範囲外」)。
    auto comparePane = [&](const Clip* compare, int primaryIndex, int offset, const PaneState& previous) {
        PaneState pane;
        pane.clip = compare;
        const int index = primaryIndex + offset;
        pane.index = std::clamp(index, 0, compare->frameCount() - 1);
        pane.outOfRange = index < 0 || index >= compare->frameCount();
        if (!pane.outOfRange) {
            pane.frame = compare->frame(index);
            pane.imageIndex = index;
            pane.loading = !pane.frame;
            pane.broken = pane.loading && compare->isBroken(index);
            if (!pane.frame) {
                choosePlaceholder(pane, compare, previous);
            }
        }
        return pane;
    };

    for (;;) {
        std::shared_ptr<Clip> clip;
        std::shared_ptr<Clip> compare;
        std::shared_ptr<AudioPlayer> audio;
        bool playing = false;
        int requested = 0;
        int offset = 0;
        int startFrame = 0;
        int playSession = 0;
        double rate = 24.0;
        int rangeFirst = 0;
        int rangeLast = 0;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stopThread_) {
                break;
            }
            clip = clip_;
            compare = clip_ ? compare_ : nullptr;
            // 比較中は音声を鳴らさない(PCの時計で進める)。
            audio = (audio_ && audio_->hasAudio() && !compare) ? audio_ : nullptr;
            playing = playRequested_ && clip;
            requested = requested_;
            offset = compareOffset_;  // 表示するコマと同じ鍵の中で読む(showFrame()で両方を同時に変えるため)。
            startFrame = playStartFrame_;
            playSession = playSession_;
            rate = rate_;
            rangeFirst = playFirst_;
            rangeLast = std::max(playFirst_, playLast_);
            // 音声は動画の中にしか無いので、再生範囲が動画の外にかかるときはPCの時計で進める。
            if (audio && clip && (rangeFirst < 0 || rangeLast >= clip->frameCount())) {
                audio = nullptr;
            }
        }
        if (sessionAudio && sessionAudio != audio) {
            sessionAudio->stop();  // 再生中に範囲が動画の外へ広がった・比較を始めたなど。
            sessionAudio = nullptr;
        }
        const int paneCount = compare ? 2 : 1;
        if (!ready) {
            // デバイスを作れなかった(または失われた)。少し待って作り直す。
            WaitForSingleObject(wakeEvent_, 500);
            ready = createDevice();
            continue;
        }

        if (!playing) {
            // 停止中は、表示が変わるときだけ描く。それ以外は合図を待つ(大きさの変更も合図で知る)。
            PaneState panes[2];
            panes[0].clip = clip.get();
            panes[0].index = requested;
            panes[0].outOfRange = clip && (requested < 0 || requested >= clip->frameCount());
            if (clip && !panes[0].outOfRange) {
                panes[0].frame = clip->frame(requested);
                panes[0].imageIndex = requested;
                panes[0].loading = !panes[0].frame;
                panes[0].broken = panes[0].loading && clip->isBroken(requested);
                if (!panes[0].frame) {
                    choosePlaceholder(panes[0], clip.get(), drawn[0]);
                }
            }
            if (compare) {
                panes[1] = comparePane(compare.get(), requested, offset, drawn[1]);
            }
            RECT client;
            GetClientRect(hwnd_, &client);
            const UINT width = static_cast<UINT>(std::max(1L, client.right - client.left));
            const UINT height = static_cast<UINT>(std::max(1L, client.bottom - client.top));
            const int generation = redrawGeneration_;
            const bool changed = !panes[0].same(drawn[0]) || (compare && !panes[1].same(drawn[1])) ||
                                 paneCount != drawnPaneCount || offset != drawnOffset || width != drawnWidth ||
                                 height != drawnHeight || generation != drawnGeneration;
            if (!changed) {
                WaitForSingleObject(wakeEvent_, 250);
                continue;
            }
            WaitForSingleObject(frameWaitable_, 100);
            if (!resizeIfNeeded()) {
                ready = false;
                continue;
            }
            drawn[0] = panes[0];
            drawn[1] = compare ? panes[1] : PaneState{};
            drawnPaneCount = paneCount;
            drawnOffset = offset;
            drawnWidth = width;
            drawnHeight = height;
            drawnGeneration = generation;
            // 停止中の表示コマ(current_)はshowFrame()が決める。ここで書き戻すと、描き始めた後に
            // 新しい指示が来た場合に古い番号へ戻ってしまう(スライダーのドラッグ中に行ったり来たりして見える)。
            ready = draw(panes, paneCount, offset);
            traceLog("present stopped %d image=%d loading=%d", panes[0].index, panes[0].imageIndex,
                    panes[0].loading ? 1 : 0);
            notifyParent();
            continue;
        }

        // 再生中は、表示するコマが変わったときだけ描く。変わらない間は次のコマの時刻までタイマーで眠る
        // (画面更新のたびに同じコマを描き直したり、画面更新を待ってCPUを使い続けたりしないため)。
        RECT client;
        GetClientRect(hwnd_, &client);
        const UINT width = static_cast<UINT>(std::max(1L, client.right - client.left));
        const UINT height = static_cast<UINT>(std::max(1L, client.bottom - client.top));
        const LONGLONG now = nowTicks();
        // 半コマ分の長さ。時計を半コマ早めておくと、コマの境目が画面更新と画面更新の中間に来る。
        // 境目と画面更新が重なると、わずかな揺れでコマが飛んだり重なったりするため。
        const LONGLONG halfFrameTicks = static_cast<LONGLONG>(frequency * 0.5 / rate);
        const long long halfFrameMedia = static_cast<long long>(10000000 * 0.5 / rate);
        const long long period = std::max<long long>(1, static_cast<long long>(10000000 / rate));  // 動画の外の1コマ。
        auto beginSession = [&](int fromFrame) {
            sessionStartMedia = timelineTime(*clip, fromFrame, period);
            sessionStartTicks = now - halfFrameTicks;
            waitingForAudio = audio != nullptr;
            audioWaitSince = now;
            sessionAudio = audio;
            if (audio) {
                audio->start(sessionStartMedia);
            }
        };
        if (session != playSession) {
            session = playSession;
            beginSession(startFrame);
        }

        if (audio) {
            long long audioTime = 0;
            if (audio->position(audioTime)) {
                // 音声に合わせる。差が大きければすぐ合わせ、小さければ少しずつ合わせる(映像がガクつかないように)。
                const long long videoTime =
                    sessionStartMedia + (now - sessionStartTicks) * 10000000 / frequency - halfFrameMedia;
                const long long error = audioTime - videoTime;
                const long long correction = waitingForAudio || std::llabs(error) > 4 * halfFrameMedia ? error : error / 10;
                sessionStartTicks -= correction * frequency / 10000000;
                waitingForAudio = false;
            } else if (waitingForAudio && (now - audioWaitSince) < frequency) {
                // 音声が鳴り始めるまでは最初のコマのまま待つ(1秒たっても鳴らなければ、PCの時計で進める)。
                sessionStartTicks = now - halfFrameTicks;
            }
        }

        // 今表示すべき動画の時刻と、そのコマ。再生範囲の最後のコマを表示し終えたら、範囲の最初から繰り返す。
        // 再生中に範囲が変わり、今の時刻が範囲より前になった場合も範囲の最初からにする。
        long long mediaNow = sessionStartMedia + (now - sessionStartTicks) * 10000000 / frequency;
        const long long endTime = timelineTime(*clip, rangeLast, period) + 2 * halfFrameMedia;
        if (mediaNow >= endTime || mediaNow < timelineTime(*clip, rangeFirst, period) - 2 * halfFrameMedia) {
            beginSession(rangeFirst);
            mediaNow = sessionStartMedia + halfFrameMedia;
        }
        const int frameCount = clip->frameCount();
        const int target = std::clamp(timelineFrameAt(*clip, mediaNow, period), rangeFirst, rangeLast);
        const bool targetInClip = target >= 0 && target < frameCount;
        // 先読みの位置: 動画の中ならそのコマ。動画より前なら1コマ目(これから入る所)。動画より後なら、
        // ループで戻る範囲の最初(動画の中に無ければ1コマ目)。
        const int prefetch = targetInClip ? target
                             : target < 0 ? 0
                                          : std::clamp(rangeFirst, 0, frameCount - 1);
        clip->setPlayhead(prefetch, Clip::Direction::Forward, true);
        if (compare) {
            compare->setPlayhead(std::clamp(target + offset, 0, compare->frameCount() - 1), Clip::Direction::Forward,
                                 false);
        }

        // リアルタイム優先: 目標のコマがキャッシュに無ければ、今のコマを表示したまま待つ。
        // 届いたときには途中のコマを飛ばして目標へ移る(その分をコマ落ちとして数える)。
        // 比較中は左右両方のコマがそろってから進める(片方だけ進んでずれて見えないように)。
        // 動画の外のコマは、待たずに「範囲外」として進める。
        const std::shared_ptr<const Frame> frame = targetInClip ? clip->frame(target) : nullptr;
        const bool primaryReady = !targetInClip || frame;
        PaneState comparePaneState;
        bool compareReady = true;
        if (compare) {
            comparePaneState = comparePane(compare.get(), target, offset, drawn[1]);
            compareReady = comparePaneState.outOfRange || !comparePaneState.loading;
        }
        const bool advance = primaryReady && compareReady && (target != shown || clip.get() != shownClip);
        if (advance) {
            if (shownValid && clip.get() == shownClip) {
                const int length = rangeLast - rangeFirst + 1;
                const int step = ((target - shown) % length + length) % length;
                if (step > 1) {
                    dropped_ += step - 1;
                }
            }
            shown = target;
            shownValid = true;
            shownClip = clip.get();
            drawn[0] = PaneState{};
            drawn[0].clip = clip.get();
            drawn[0].frame = frame;
            drawn[0].index = target;
            drawn[0].imageIndex = targetInClip ? target : -1;
            drawn[0].outOfRange = !targetInClip;
            drawn[1] = compare ? comparePaneState : PaneState{};
            current_ = target;
            notifyParent();
        }
        const int generation = redrawGeneration_;
        if (advance || width != drawnWidth || height != drawnHeight || paneCount != drawnPaneCount ||
            offset != drawnOffset || generation != drawnGeneration) {
            // 描ける状態(表示の順番待ちに空き)になるまで眠って待ち、次の画面更新に合わせて描く。
            WaitForSingleObject(frameWaitable_, 100);
            if (!resizeIfNeeded()) {
                ready = false;
                continue;
            }
            drawnPaneCount = paneCount;
            drawnOffset = offset;
            drawnWidth = width;
            drawnHeight = height;
            drawnGeneration = generation;
            ready = draw(drawn, paneCount, offset);
            traceLog("present playing %d", drawn[0].index);
            continue;
        }

        // 次に表示が変わる時刻(次のコマの表示時刻)まで眠る。目標のコマがまだ届いていないときは、
        // 届いた合図(wake)で起きる(合図を逃しても10msで確かめ直す)。操作の合図でも起きる。
        LONGLONG waitTicks = frequency / 100;
        if (primaryReady) {
            const long long nextMedia = target + 1 <= rangeLast ? timelineTime(*clip, target + 1, period) : endTime;
            const LONGLONG nextTicks = sessionStartTicks + (nextMedia - sessionStartMedia) * frequency / 10000000;
            waitTicks = std::max<LONGLONG>(1, nextTicks - nowTicks());
        }
        sleepTicks(waitTicks, true);
    }

    // 後片付けは作ったスレッドで行う。
    for (PaneCache& cache : paneCaches_) {
        cache = PaneCache{};
    }
    target_.Reset();
    context_.Reset();
    backBuffer_.Reset();
    swapChain_.Reset();
    renderer_ = FrameRenderer{};
    d3dContext_.Reset();
    device_.Reset();
    if (frameWaitable_) {
        CloseHandle(frameWaitable_);
        frameWaitable_ = nullptr;
    }
    if (timer_) {
        CloseHandle(timer_);
        timer_ = nullptr;
    }
    if (SUCCEEDED(comResult)) {
        CoUninitialize();
    }
}

}  // namespace frameplayer
