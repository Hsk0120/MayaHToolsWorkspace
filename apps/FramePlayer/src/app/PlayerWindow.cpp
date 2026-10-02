/**
 * @file PlayerWindow.cpp
 * @brief プレイヤーのメインウィンドウの実装。
 */
#include "app/PlayerWindow.h"

#include <windowsx.h>

#include <algorithm>
#include <cstdio>
#include <iterator>

namespace frameplayer {

namespace {

constexpr wchar_t kClassName[] = L"FramePlayerWindow";
constexpr wchar_t kAppName[] = L"FramePlayer";
constexpr int kCacheMaxWidth = 1280;                       ///< キャッシュする画像の最大幅。
constexpr std::size_t kCacheBytes = std::size_t{4} << 30;  ///< キャッシュの上限(4GB)。
constexpr int kLargeStep = 10;                             ///< Shift併用時に移動するコマ数。
constexpr double kDefaultRate = 24.0;                      ///< フレームレートが不明な動画の再生速度。
constexpr UINT kViewFrameMessage = WM_APP + 1;   ///< VideoViewが表示するコマを変えたときの知らせ。
constexpr UINT kFrameReadyMessage = WM_APP + 2;  ///< 裏の読み込みでコマがキャッシュに入ったときの知らせ。
constexpr LONGLONG kCacheBarIntervalMs = 200;    ///< キャッシュ表示を計算し直す最短間隔(ミリ秒)。

constexpr COLORREF kBackground = RGB(32, 32, 32);
constexpr COLORREF kText = RGB(230, 230, 230);
constexpr COLORREF kControlFace = RGB(58, 58, 58);
constexpr COLORREF kSliderFace = RGB(44, 44, 44);
constexpr COLORREF kSliderPlayed = RGB(56, 72, 92);
constexpr COLORREF kTick = RGB(120, 120, 120);
constexpr COLORREF kTickLabel = RGB(170, 170, 170);
constexpr COLORREF kPlayhead = RGB(255, 150, 40);
constexpr COLORREF kCached = RGB(80, 150, 230);

/**
 * @brief 96DPI基準の長さを、ウィンドウのDPIに合わせた長さへ変換する。
 * @param value 96DPIでの長さ(ピクセル)。
 * @param dpi ウィンドウのDPI。
 * @return 変換後の長さ。
 */
int scaled(int value, int dpi) {
    return MulDiv(value, dpi, 96);
}

/**
 * @brief 矩形を単色で塗る。
 * @param dc 描画先。
 * @param rect 塗る範囲。
 * @param color 色。
 */
void fillColor(HDC dc, const RECT& rect, COLORREF color) {
    HBRUSH brush = CreateSolidBrush(color);
    FillRect(dc, &rect, brush);
    DeleteObject(brush);
}

/**
 * @brief 指定サイズのSegoe UIフォントを作る。
 * @param points 文字の大きさ(ポイント)。
 * @param dpi ウィンドウのDPI。
 * @return 作成したフォント。呼び出し元がDeleteObjectで解放する。
 */
HFONT createUiFont(int points, int dpi) {
    return CreateFontW(-MulDiv(points, dpi, 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                       OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Segoe UI");
}

/**
 * @brief 目盛りの間隔を、隣の目盛りとの距離が指定以上になる最小の「きりのよい数」から選ぶ。
 * @param pixelsPerFrame 1コマあたりの横幅(ピクセル)。
 * @param minSpacing 目盛り同士の最小距離(ピクセル)。
 * @return 目盛りの間隔(コマ数)。
 */
int tickStep(double pixelsPerFrame, int minSpacing) {
    static const int kSteps[] = {1,    2,    5,     10,    20,    50,     100,    200,   500,
                                 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000};
    for (int step : kSteps) {
        if (step * pixelsPerFrame >= minSpacing) {
            return step;
        }
    }
    return 500000;
}

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
 * @brief パスからファイル名部分を取り出す。
 * @param path ファイルのパス。
 * @return 最後の区切り文字より後ろ。
 */
std::wstring fileNameOf(const std::wstring& path) {
    const size_t pos = path.find_last_of(L"\\/");
    return pos == std::wstring::npos ? path : path.substr(pos + 1);
}

}  // namespace

bool PlayerWindow::create(HINSTANCE instance, int showCommand) {
    instance_ = instance;
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = &PlayerWindow::windowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    wc.lpszClassName = kClassName;
    // 背景はpaint()で塗るので、ここでは指定しない(ちらつき防止)。
    if (!RegisterClassExW(&wc)) {
        return false;
    }

    // lpParamにthisを渡し、windowProcでウィンドウと結び付ける。
    // WS_CLIPCHILDRENで、親の描画が映像の子ウィンドウを上書きしないようにする。
    hwnd_ = CreateWindowExW(0, kClassName, kAppName, WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT,
                            CW_USEDEFAULT, 1280, 800, nullptr, nullptr, instance, this);
    if (!hwnd_) {
        return false;
    }
    if (!view_.create(instance, hwnd_, kViewFrameMessage)) {
        DestroyWindow(hwnd_);
        return false;
    }
    view_.setBounds(computeLayout().video);
    DragAcceptFiles(hwnd_, TRUE);
    ShowWindow(hwnd_, showCommand);
    UpdateWindow(hwnd_);
    return true;
}

void PlayerWindow::openClip(const std::wstring& path) {
    view_.stop();
    syncPowerRequest();
    endScrub();
    auto clip = std::make_shared<Clip>();
    std::wstring error;
    HCURSOR previousCursor = SetCursor(LoadCursorW(nullptr, IDC_WAIT));

    // 開くときは目次を作って先頭のコマを読むだけで、残りは裏のスレッドが先読みする。
    // 裏のスレッドからの知らせは、描画スレッドを起こす合図と、UIスレッドへのPostMessageにする。
    // UIへの知らせは、処理前のものが残っていれば送らない。
    const bool loaded = clip->open(
        path, kCacheMaxWidth, kCacheBytes,
        [this] {
            view_.wake();
            if (!frameReadyPending_.exchange(true)) {
                PostMessageW(hwnd_, kFrameReadyMessage, 0, 0);
            }
        },
        error);

    SetCursor(previousCursor);
    if (!loaded) {
        updateTitle();
        MessageBoxW(hwnd_, (path + L"\n\n" + error).c_str(), kAppName, MB_OK | MB_ICONWARNING);
        return;
    }
    clip_ = std::move(clip);
    current_ = 0;
    cacheRuns_.clear();
    cacheRunsTrack_ = RECT{};
    view_.setClip(clip_);
    clip_->setPlayhead(0, Clip::Direction::Forward, false);
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
}

LRESULT CALLBACK PlayerWindow::windowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    if (message == WM_NCCREATE) {
        auto* create = reinterpret_cast<CREATESTRUCTW*>(lParam);
        auto* self = static_cast<PlayerWindow*>(create->lpCreateParams);
        self->hwnd_ = hwnd;
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    }
    auto* self = reinterpret_cast<PlayerWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (!self) {
        return DefWindowProcW(hwnd, message, wParam, lParam);
    }
    return self->handleMessage(message, wParam, lParam);
}

LRESULT PlayerWindow::handleMessage(UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
    case WM_PAINT:
        paint();
        return 0;
    case WM_ERASEBKGND:
        return 1;  // paint()で塗るので消去は不要。
    case WM_SIZE:
        view_.setBounds(computeLayout().video);
        InvalidateRect(hwnd_, nullptr, FALSE);
        return 0;
    case WM_KEYDOWN:
        // Spaceの押しっぱなしで再生/停止が繰り返し切り替わらないよう、キーリピートは無視する。
        if (wParam == VK_SPACE && (lParam & (1 << 30))) {
            return 0;
        }
        onKeyDown(wParam);
        return 0;
    case WM_LBUTTONDOWN:
        onLeftButtonDown(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        return 0;
    case WM_MOUSEMOVE:
        onMouseMove(GET_X_LPARAM(lParam));
        return 0;
    case WM_LBUTTONUP:
        endScrub();
        return 0;
    case WM_CAPTURECHANGED:
        // 他のウィンドウにマウスを取られたときもドラッグを終える。
        scrubbing_ = false;
        return 0;
    case kViewFrameMessage:
        onViewFrameChanged();
        return 0;
    case kFrameReadyMessage:
        onFrameReady();
        return 0;
    case WM_DROPFILES:
        onDropFiles(reinterpret_cast<HDROP>(wParam));
        return 0;
    case WM_DPICHANGED: {
        // 別の拡大率のモニターへ移ったときは、Windowsが提案する大きさに合わせる。
        const RECT* suggested = reinterpret_cast<const RECT*>(lParam);
        SetWindowPos(hwnd_, nullptr, suggested->left, suggested->top, suggested->right - suggested->left,
                     suggested->bottom - suggested->top, SWP_NOZORDER | SWP_NOACTIVATE);
        return 0;
    }
    case WM_DESTROY:
        // 描画スレッドを止めてから動画を手放す(手放すと裏の読み込みスレッドも止まる)。
        view_.shutdown();
        view_.setClip(nullptr);
        syncPowerRequest();
        clip_.reset();
        PostQuitMessage(0);
        return 0;
    default:
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    }
}

PlayerWindow::Layout PlayerWindow::computeLayout() const {
    RECT client;
    GetClientRect(hwnd_, &client);
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const int margin = scaled(8, dpi);
    const int barHeight = scaled(44, dpi);
    const int barTop = std::max(static_cast<int>(client.top), static_cast<int>(client.bottom) - barHeight);

    Layout layout;
    layout.video = {client.left + margin, client.top + margin, client.right - margin,
                    std::max(static_cast<int>(client.top) + margin, barTop)};
    layout.bar = {client.left, barTop, client.right, client.bottom};
    const int buttonSize = scaled(32, dpi);
    const int buttonTop = barTop + (barHeight - buttonSize) / 2;
    layout.button = {client.left + margin, buttonTop, client.left + margin + buttonSize, buttonTop + buttonSize};
    const int infoLeft = std::max(static_cast<int>(layout.button.right),
                                  static_cast<int>(client.right) - margin - scaled(320, dpi));
    layout.info = {infoLeft, barTop, client.right - margin, client.bottom};
    layout.slider = {layout.button.right + scaled(10, dpi), barTop + scaled(6, dpi), layout.info.left - scaled(10, dpi),
                     client.bottom - scaled(6, dpi)};
    layout.track = layout.slider;
    InflateRect(&layout.track, -scaled(4, dpi), 0);
    return layout;
}

void PlayerWindow::invalidateBar() {
    const RECT bar = computeLayout().bar;
    InvalidateRect(hwnd_, &bar, FALSE);
}

void PlayerWindow::paint() {
    PAINTSTRUCT ps;
    HDC screen = BeginPaint(hwnd_, &ps);
    const RECT& area = ps.rcPaint;
    const int width = std::max(1L, area.right - area.left);
    const int height = std::max(1L, area.bottom - area.top);

    // 描き直しが必要な範囲だけの裏の画像に描いてから、一度に転送する(ちらつき防止)。
    // 座標はクライアント座標のまま使えるよう、原点をずらす。
    HDC dc = CreateCompatibleDC(screen);
    HBITMAP backBuffer = CreateCompatibleBitmap(screen, width, height);
    HGDIOBJ oldBitmap = SelectObject(dc, backBuffer);
    SetViewportOrgEx(dc, -area.left, -area.top, nullptr);
    RECT client;
    GetClientRect(hwnd_, &client);
    fillColor(dc, client, kBackground);

    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    HFONT font = createUiFont(14, dpi);
    HGDIOBJ oldFont = SelectObject(dc, font);
    SetBkMode(dc, TRANSPARENT);
    paintControls(dc, computeLayout(), dpi);

    SetViewportOrgEx(dc, 0, 0, nullptr);
    BitBlt(screen, area.left, area.top, width, height, dc, 0, 0, SRCCOPY);

    SelectObject(dc, oldFont);
    DeleteObject(font);
    SelectObject(dc, oldBitmap);
    DeleteObject(backBuffer);
    DeleteDC(dc);
    EndPaint(hwnd_, &ps);
}

void PlayerWindow::paintControls(HDC dc, const Layout& layout, int dpi) {
    const bool playing = view_.isPlaying();

    // 再生/停止ボタン。再生中は停止(縦棒2本)、停止中は再生(三角)の記号を出す。
    const RECT& b = layout.button;
    fillColor(dc, b, kControlFace);
    const int cx = (b.left + b.right) / 2;
    const int cy = (b.top + b.bottom) / 2;
    const int icon = (b.bottom - b.top) / 4;
    if (playing) {
        const int barWidth = std::max(2, icon * 2 / 3);
        fillColor(dc, RECT{cx - icon + 1, cy - icon, cx - icon + 1 + barWidth, cy + icon}, kText);
        fillColor(dc, RECT{cx + icon - barWidth, cy - icon, cx + icon, cy + icon}, kText);
    } else {
        const POINT triangle[] = {{cx - icon * 3 / 4, cy - icon}, {cx - icon * 3 / 4, cy + icon}, {cx + icon, cy}};
        HBRUSH brush = CreateSolidBrush(kText);
        HPEN pen = CreatePen(PS_SOLID, 1, kText);
        HGDIOBJ oldBrush = SelectObject(dc, brush);
        HGDIOBJ oldPen = SelectObject(dc, pen);
        Polygon(dc, triangle, 3);
        SelectObject(dc, oldBrush);
        SelectObject(dc, oldPen);
        DeleteObject(brush);
        DeleteObject(pen);
    }

    // タイムスライダー。
    const RECT& s = layout.slider;
    const RECT& t = layout.track;
    if (s.right <= s.left) {
        return;
    }
    fillColor(dc, s, kSliderFace);
    if (!clip_) {
        return;
    }
    const int count = clip_->frameCount();
    const int trackWidth = t.right - t.left;
    auto xOf = [&](int index) {
        return count > 1 ? t.left + static_cast<int>(static_cast<long long>(index) * trackWidth / (count - 1)) : t.left;
    };
    const int playheadX = xOf(current_);
    fillColor(dc, RECT{s.left, s.top, playheadX, s.bottom}, kSliderPlayed);

    // キャッシュ済みのコマを、スライダー下端の細い帯で示す。1画素に複数コマが入る場合は1つでもあれば塗る。
    // 調べるには全コマ(1時間60fpsで21万6千)を見るので、毎回の描画では計算し直さず、
    // 一定間隔(kCacheBarIntervalMs)ごと、またはスライダーの幅が変わったときだけ計算する。
    static const LONGLONG frequency = ticksPerSecond();
    const LONGLONG now = nowTicks();
    if (cacheRunsTrack_.left != t.left || cacheRunsTrack_.right != t.right ||
        (now - lastCacheBarTicks_) * 1000 / frequency >= kCacheBarIntervalMs) {
        clip_->cachedFlags(cacheFlags_);
        lastCacheBarTicks_ = now;
        cacheRunsTrack_ = t;
        cacheRuns_.clear();
        int runStart = -1;
        for (int x = t.left; x <= t.right; ++x) {
            bool cached = false;
            if (x < t.right && count > 0) {
                const long long span = std::max(1, trackWidth);
                const int first = static_cast<int>(static_cast<long long>(x - t.left) * (count - 1) / span);
                const int last = std::max(
                    first, static_cast<int>(static_cast<long long>(x + 1 - t.left) * (count - 1) / span) - 1);
                for (int i = first; i <= std::min(last, count - 1) && !cached; ++i) {
                    cached = cacheFlags_[static_cast<std::size_t>(i)] != 0;
                }
            }
            if (cached && runStart < 0) {
                runStart = x;
            } else if (!cached && runStart >= 0) {
                cacheRuns_.emplace_back(runStart, x);
                runStart = -1;
            }
        }
    }
    const int barHeight = std::max(2, scaled(3, dpi));
    for (const auto& [left, right] : cacheRuns_) {
        fillColor(dc, RECT{left, s.bottom - barHeight, right, s.bottom}, kCached);
    }

    // 目盛り。細かい目盛りは下側に短く、区切りの目盛りは長くしてコマ番号(1始まり)を添える。
    const double pixelsPerFrame = count > 1 ? static_cast<double>(trackWidth) / (count - 1) : trackWidth;
    const int minor = tickStep(pixelsPerFrame, scaled(5, dpi));
    const int major = tickStep(pixelsPerFrame, scaled(48, dpi));
    const int height = s.bottom - s.top;
    HFONT labelFont = createUiFont(8, dpi);
    HGDIOBJ oldFont = SelectObject(dc, labelFont);
    SetTextColor(dc, kTickLabel);
    for (int number = minor; number <= count; number += minor) {
        const int x = xOf(number - 1);
        const bool isMajor = number % major == 0;
        const int tickTop = isMajor ? s.top + height / 2 : s.bottom - height / 4;
        fillColor(dc, RECT{x, tickTop, x + 1, s.bottom}, kTick);
        if (isMajor) {
            wchar_t label[16];
            std::swprintf(label, 16, L"%d", number);
            RECT labelRect{x + scaled(2, dpi), s.top, x + scaled(60, dpi), s.top + height / 2};
            DrawTextW(dc, label, -1, &labelRect, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOCLIP);
        }
    }
    SelectObject(dc, oldFont);
    DeleteObject(labelFont);

    // 再生位置の線。
    const int half = std::max(1, scaled(1, dpi));
    fillColor(dc, RECT{playheadX - half, s.top, playheadX + half + 1, s.bottom}, kPlayhead);

    // コマ番号(1始まり)。再生中は再生開始からのコマ落ち(表示できなかったコマ)の数も出す。
    wchar_t text[128];
    if (playing) {
        std::swprintf(text, 128, L"%d / %d   %.4g fps  コマ落ち %d", current_ + 1, count, playbackRate(),
                      view_.droppedFrames());
    } else {
        std::swprintf(text, 128, L"%d / %d   %.4g fps", current_ + 1, count, playbackRate());
    }
    SetTextColor(dc, kText);
    RECT infoRect = layout.info;
    DrawTextW(dc, text, -1, &infoRect, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

void PlayerWindow::onKeyDown(WPARAM key) {
    if (!clip_) {
        return;
    }
    if (key == VK_SPACE) {
        togglePlayback();
        return;
    }
    const int current = view_.currentFrame();
    const int step = (GetKeyState(VK_SHIFT) < 0) ? kLargeStep : 1;
    switch (key) {
    case VK_RIGHT:
        goToFrame(current + step);
        break;
    case VK_LEFT:
        goToFrame(current - step);
        break;
    case VK_HOME:
        goToFrame(0);
        break;
    case VK_END:
        goToFrame(clip_->frameCount() - 1);
        break;
    default:
        break;
    }
}

void PlayerWindow::onLeftButtonDown(int x, int y) {
    if (!clip_) {
        return;
    }
    const Layout layout = computeLayout();
    const POINT point{x, y};
    if (PtInRect(&layout.button, point)) {
        togglePlayback();
    } else if (PtInRect(&layout.slider, point)) {
        // ドラッグ中にウィンドウ外へ出てもマウスの動きを受け取れるよう、マウスを取り込む。
        scrubbing_ = true;
        SetCapture(hwnd_);
        goToFrame(frameFromX(x));
    }
}

void PlayerWindow::onMouseMove(int x) {
    if (scrubbing_ && clip_) {
        goToFrame(frameFromX(x));
    }
}

void PlayerWindow::endScrub() {
    if (scrubbing_) {
        scrubbing_ = false;
        ReleaseCapture();
    }
}

void PlayerWindow::onDropFiles(HDROP drop) {
    wchar_t path[MAX_PATH * 4];
    const bool hasFile = DragQueryFileW(drop, 0, path, static_cast<UINT>(std::size(path))) > 0;
    DragFinish(drop);
    if (hasFile) {
        openClip(path);
    }
}

int PlayerWindow::frameFromX(int x) const {
    const int count = clip_->frameCount();
    const RECT track = computeLayout().track;
    const int trackWidth = track.right - track.left;
    if (count <= 1 || trackWidth <= 0) {
        return 0;
    }
    // 最も近いコマに合わせる(四捨五入)。
    const long long offset = static_cast<long long>(x - track.left) * (count - 1);
    const long long rounded = offset >= 0 ? offset + trackWidth / 2 : offset - trackWidth / 2;
    return std::clamp(static_cast<int>(rounded / trackWidth), 0, count - 1);
}

void PlayerWindow::goToFrame(int index) {
    const int clamped = std::clamp(index, 0, clip_->frameCount() - 1);
    const bool wasPlaying = view_.isPlaying();
    const int shown = view_.currentFrame();
    if (clamped == shown && !wasPlaying) {
        return;
    }
    // 移動した向きに先読みさせる(←で戻り続けるときは前のコマを先に読む)。
    const auto direction = clamped < shown ? Clip::Direction::Backward : Clip::Direction::Forward;
    view_.showFrame(clamped, direction);
    syncPowerRequest();
    current_ = clamped;
    updateTitle();
    invalidateBar();
}

void PlayerWindow::togglePlayback() {
    if (view_.isPlaying()) {
        view_.stop();
    } else {
        view_.play(playbackRate());
    }
    syncPowerRequest();
    invalidateBar();
}

void PlayerWindow::syncPowerRequest() {
    // 再生中は画面が省電力で消えないようにする(消えると画面の書き換えが止まり、再生も進まなくなる)。
    // ES_CONTINUOUSの指定は呼び出したスレッドに結び付くので、常にUIスレッドから呼ぶ。
    const bool playing = view_.isPlaying();
    if (playing == keepDisplayOn_) {
        return;
    }
    keepDisplayOn_ = playing;
    SetThreadExecutionState(playing ? (ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED) : ES_CONTINUOUS);
}

double PlayerWindow::playbackRate() const {
    return (clip_ && clip_->frameRate() > 0.0) ? clip_->frameRate() : kDefaultRate;
}

void PlayerWindow::onViewFrameChanged() {
    view_.acknowledgeNotify();
    const int shown = view_.currentFrame();
    if (shown != current_) {
        current_ = shown;
        updateTitle();
    }
    invalidateBar();
}

void PlayerWindow::onFrameReady() {
    frameReadyPending_ = false;
    if (!clip_) {
        return;
    }
    // キャッシュ表示の描き直しは間引く(映像の描き直しは描画スレッドが自分で判断する)。
    static const LONGLONG frequency = ticksPerSecond();
    if ((nowTicks() - lastCacheBarTicks_) * 1000 / frequency >= kCacheBarIntervalMs) {
        invalidateBar();
    }
}

void PlayerWindow::updateTitle() {
    if (!clip_) {
        SetWindowTextW(hwnd_, kAppName);
        return;
    }
    wchar_t title[512];
    std::swprintf(title, 512, L"%ls - %ls [%d / %d]", fileNameOf(clip_->path()).c_str(), kAppName, current_ + 1,
                  clip_->frameCount());
    SetWindowTextW(hwnd_, title);
}

}  // namespace frameplayer
