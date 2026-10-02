/**
 * @file VideoView.cpp
 * @brief 映像表示用の子ウィンドウと描画スレッドの実装。
 */
#include "app/VideoView.h"

#include <objbase.h>

#include <algorithm>
#include <cmath>

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

constexpr wchar_t kClassName[] = L"FramePlayerVideoView";
const D2D1_COLOR_F kBackground = {32 / 255.0f, 32 / 255.0f, 32 / 255.0f, 1.0f};
const D2D1_COLOR_F kText = {230 / 255.0f, 230 / 255.0f, 230 / 255.0f, 1.0f};
const D2D1_COLOR_F kBox = {58 / 255.0f, 58 / 255.0f, 58 / 255.0f, 0.9f};
constexpr UINT kSwapChainFlags = DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;

/**
 * @brief QueryPerformanceCounterの現在値を返す。
 * @return 高精度タイマーの値。
 */
LONGLONG nowTicks() {
    LARGE_INTEGER value;
    QueryPerformanceCounter(&value);
    return value.QuadPart;
}

/**
 * @brief QueryPerformanceCounterの1秒あたりの値を返す。
 * @return 1秒あたりの値。
 */
LONGLONG ticksPerSecond() {
    LARGE_INTEGER value;
    QueryPerformanceFrequency(&value);
    return value.QuadPart;
}

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

}  // namespace

VideoView::~VideoView() {
    shutdown();
    if (wakeEvent_) {
        CloseHandle(wakeEvent_);
    }
}

bool VideoView::create(HINSTANCE instance, HWND parent, UINT notifyMessage) {
    parent_ = parent;
    notifyMessage_ = notifyMessage;

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

void VideoView::setClip(std::shared_ptr<Clip> clip) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        clip_ = std::move(clip);
        requested_ = 0;
        playRequested_ = false;
    }
    playing_ = false;
    current_ = 0;
    wake();
}

void VideoView::showFrame(int index, Clip::Direction direction) {
    std::shared_ptr<Clip> clip;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        clip = clip_;
        if (!clip) {
            return;
        }
        requested_ = std::clamp(index, 0, clip->frameCount() - 1);
        playRequested_ = false;
        index = requested_;
    }
    playing_ = false;
    current_ = index;
    clip->setPlayhead(index, direction, false);
    wake();
}

void VideoView::play(double rate) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!clip_ || clip_->frameCount() <= 1) {
            return;
        }
        int start = current_;
        if (start >= clip_->frameCount() - 1) {
            start = 0;  // 最後のコマで再生を始めたら先頭から。
        }
        requested_ = start;
        playStartFrame_ = start;
        playStartTicks_ = 0;  // 描画スレッドが最初の画面更新の時刻で決める。
        rate_ = rate > 0.0 ? rate : 24.0;
        playRequested_ = true;
    }
    dropped_ = 0;
    playing_ = true;
    wake();
}

void VideoView::stop() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        playRequested_ = false;
        requested_ = current_;
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
    swapChain_.Reset();
    context_.Reset();
    target_.Reset();
    frameBitmap_.Reset();
    frameBitmapSource_.reset();
    device_.Reset();
    if (frameWaitable_) {
        CloseHandle(frameWaitable_);
        frameWaitable_ = nullptr;
    }

    // GPUで作れなければ、Windowsに入っているCPU用の代わり(WARP)で作る(リモートデスクトップ等)。
    HRESULT hr = E_FAIL;
    for (D3D_DRIVER_TYPE type : {D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP}) {
        hr = D3D11CreateDevice(nullptr, type, nullptr, D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
                               &device_, nullptr, nullptr);
        if (SUCCEEDED(hr)) {
            break;
        }
    }
    if (FAILED(hr)) {
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
    hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, __uuidof(ID2D1Factory1), &options,
                           reinterpret_cast<void**>(d2dFactory_.ReleaseAndGetAddressOf()));
    ComPtr<ID2D1Device> d2dDevice;
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
    }
    return createTarget();
}

bool VideoView::createTarget() {
    ComPtr<IDXGISurface> surface;
    if (FAILED(swapChain_->GetBuffer(0, IID_PPV_ARGS(&surface)))) {
        return false;
    }
    const D2D1_BITMAP_PROPERTIES1 properties = D2D1::BitmapProperties1(
        D2D1_BITMAP_OPTIONS_TARGET | D2D1_BITMAP_OPTIONS_CANNOT_DRAW,
        D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE), 96.0f, 96.0f);
    if (FAILED(context_->CreateBitmapFromDxgiSurface(surface.Get(), &properties, &target_))) {
        return false;
    }
    context_->SetTarget(target_.Get());
    return true;
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
    if (FAILED(swapChain_->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, kSwapChainFlags))) {
        return false;
    }
    swapWidth_ = width;
    swapHeight_ = height;
    return createTarget();
}

bool VideoView::draw(const Clip* clip, const std::shared_ptr<const Frame>& frame, bool loading, bool broken) {
    context_->BeginDraw();
    context_->SetTransform(D2D1::Matrix3x2F::Identity());
    context_->Clear(kBackground);
    const D2D1_RECT_F area = D2D1::RectF(0, 0, static_cast<float>(swapWidth_), static_cast<float>(swapHeight_));

    ComPtr<ID2D1SolidColorBrush> textBrush;
    context_->CreateSolidColorBrush(kText, &textBrush);
    if (!clip && textFormat_) {
        static const wchar_t message[] = L"動画ファイルをドロップしてください";
        context_->DrawText(message, static_cast<UINT32>(std::size(message) - 1), textFormat_.Get(), area,
                           textBrush.Get());
    }

    if (frame && frame->width > 0 && frame->height > 0) {
        // 表示する画像が変わったときだけGPUへ写す(再生中も同じコマを描き直すことがあるため)。
        if (frameBitmapSource_ != frame) {
            const D2D1_SIZE_U size = D2D1::SizeU(static_cast<UINT32>(frame->width), static_cast<UINT32>(frame->height));
            if (!frameBitmap_ || frameBitmap_->GetPixelSize().width != size.width ||
                frameBitmap_->GetPixelSize().height != size.height) {
                const D2D1_BITMAP_PROPERTIES1 properties = D2D1::BitmapProperties1(
                    D2D1_BITMAP_OPTIONS_NONE, D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE),
                    96.0f, 96.0f);
                frameBitmap_.Reset();
                context_->CreateBitmap(size, nullptr, 0, &properties, &frameBitmap_);
            }
            if (frameBitmap_) {
                frameBitmap_->CopyFromMemory(nullptr, frame->pixels.data(), static_cast<UINT32>(frame->width) * 4);
                frameBitmapSource_ = frame;  // 保持しておくと、同じアドレスの別の画像と取り違えない。
            }
        }
        if (frameBitmap_) {
            // 拡大縮小はGPUの高画質な補間で行う(再生中も画質を落とさない)。
            context_->DrawBitmap(frameBitmap_.Get(), fitRect(area, frame->width, frame->height), 1.0f,
                                 D2D1_INTERPOLATION_MODE_HIGH_QUALITY_CUBIC, nullptr);
        }
    }

    if ((loading || broken) && textFormat_) {
        // 表示中のコマが無いときは、直前の画像の上に知らせを重ねる(別のコマをそのコマとして見せないため)。
        const float scale = GetDpiForWindow(hwnd_) / 96.0f;
        const float cx = (area.left + area.right) / 2;
        const float cy = (area.top + area.bottom) / 2;
        const D2D1_RECT_F box = D2D1::RectF(cx - 130 * scale, cy - 20 * scale, cx + 130 * scale, cy + 20 * scale);
        ComPtr<ID2D1SolidColorBrush> boxBrush;
        context_->CreateSolidColorBrush(kBox, &boxBrush);
        context_->FillRectangle(box, boxBrush.Get());
        const wchar_t* label = broken ? L"このコマはデコードできません" : L"読み込み中…";
        context_->DrawText(label, static_cast<UINT32>(wcslen(label)), textFormat_.Get(), box, textBrush.Get());
    }

    if (context_->EndDraw() == static_cast<HRESULT>(D2DERR_RECREATE_TARGET)) {
        return false;
    }
    // 次の垂直同期で表示する。ウィンドウが隠れているときは描いても見えないので少し休む。
    const HRESULT hr = swapChain_->Present(1, 0);
    if (hr == DXGI_ERROR_DEVICE_REMOVED || hr == DXGI_ERROR_DEVICE_RESET) {
        return false;
    }
    if (hr == DXGI_STATUS_OCCLUDED) {
        Sleep(16);
    }
    return true;
}

void VideoView::renderLoop() {
    // Direct2D・DirectWriteはCOMの仕組みで作られるので、このスレッドでも初期化しておく。
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const LONGLONG frequency = ticksPerSecond();
    bool ready = createDevice();

    int shown = -1;                          // 最後に描いたコマ番号。
    std::shared_ptr<const Frame> shownFrame;  // 最後に描いた画像。
    const Clip* shownClip = nullptr;
    bool shownLoading = false;
    for (;;) {
        std::shared_ptr<Clip> clip;
        bool playing = false;
        int requested = 0;
        int startFrame = 0;
        LONGLONG startTicks = 0;
        double rate = 24.0;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stopThread_) {
                break;
            }
            clip = clip_;
            playing = playRequested_ && clip;
            requested = requested_;
            startFrame = playStartFrame_;
            startTicks = playStartTicks_;
            rate = rate_;
        }
        if (!ready) {
            // デバイスを作れなかった(または失われた)。少し待って作り直す。
            WaitForSingleObject(wakeEvent_, 500);
            ready = createDevice();
            continue;
        }

        if (!playing) {
            // 停止中は、表示が変わるときだけ描く。それ以外は合図を待つ(大きさの変更も合図で知る)。
            const std::shared_ptr<const Frame> frame = clip ? clip->frame(requested) : nullptr;
            RECT client;
            GetClientRect(hwnd_, &client);
            const bool resized = static_cast<UINT>(std::max(1L, client.right - client.left)) != swapWidth_ ||
                                 static_cast<UINT>(std::max(1L, client.bottom - client.top)) != swapHeight_;
            const bool changed = clip.get() != shownClip || requested != shown || (frame && frame != shownFrame) ||
                                 shownLoading != (clip && !frame) || resized;
            if (!changed) {
                WaitForSingleObject(wakeEvent_, 250);
                continue;
            }
            WaitForSingleObject(frameWaitable_, 100);
            if (!resizeIfNeeded()) {
                ready = false;
                continue;
            }
            if (frame) {
                shownFrame = frame;
            } else if (clip.get() != shownClip) {
                shownFrame.reset();
            }
            shownClip = clip.get();
            shown = requested;
            shownLoading = clip && !frame;
            current_ = requested;
            ready = draw(clip.get(), shownFrame, shownLoading, shownLoading && clip->isBroken(requested));
            notifyParent();
            continue;
        }

        // 再生中は画面更新ごとに1回描く。待機用オブジェクトが合図されるまで待つ。
        WaitForSingleObject(frameWaitable_, 100);
        if (!resizeIfNeeded()) {
            ready = false;
            continue;
        }
        const LONGLONG now = nowTicks();
        if (startTicks == 0) {
            // 再生開始の時刻を、コマの境目が画面更新と画面更新の中間に来るよう半コマ分ずらして決める。
            // 境目と画面更新が重なると、わずかな揺れでコマが飛んだり重なったりするため。
            startTicks = now - static_cast<LONGLONG>(frequency * 0.5 / rate);
            std::lock_guard<std::mutex> lock(mutex_);
            if (playRequested_ && playStartFrame_ == startFrame) {
                playStartTicks_ = startTicks;
            }
        }
        const int count = clip->frameCount();
        const long long advanced = static_cast<long long>(static_cast<double>(now - startTicks) * rate / frequency);
        const int target = static_cast<int>((startFrame + advanced) % count);
        clip->setPlayhead(target, Clip::Direction::Forward, true);

        // リアルタイム優先: 目標のコマがキャッシュに無ければ、今のコマを表示したまま待つ。
        // 届いたときには途中のコマを飛ばして目標へ移る(その分をコマ落ちとして数える)。
        const std::shared_ptr<const Frame> frame = clip->frame(target);
        if (frame && (target != shown || clip.get() != shownClip)) {
            if (shown >= 0 && clip.get() == shownClip) {
                const int step = (target - shown + count) % count;
                if (step > 1) {
                    dropped_ += step - 1;
                }
            }
            shown = target;
            shownFrame = frame;
            shownClip = clip.get();
            shownLoading = false;
            current_ = target;
            notifyParent();
        }
        ready = draw(clip.get(), shownFrame, false, false);
    }

    // 後片付けは作ったスレッドで行う。
    frameBitmapSource_.reset();
    frameBitmap_.Reset();
    target_.Reset();
    context_.Reset();
    swapChain_.Reset();
    device_.Reset();
    if (frameWaitable_) {
        CloseHandle(frameWaitable_);
        frameWaitable_ = nullptr;
    }
    if (SUCCEEDED(comResult)) {
        CoUninitialize();
    }
}

}  // namespace frameplayer
