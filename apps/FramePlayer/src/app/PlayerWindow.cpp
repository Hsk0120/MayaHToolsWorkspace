/**
 * @file PlayerWindow.cpp
 * @brief プレイヤーのメインウィンドウの実装。
 */
#include "app/PlayerWindow.h"

#include <shobjidl.h>
#include <windowsx.h>
#include <wrl/client.h>

#include <algorithm>
#include <cstdio>
#include <iterator>

namespace frameplayer {

namespace {

constexpr wchar_t kClassName[] = L"FramePlayerWindow";
constexpr wchar_t kAppName[] = L"FramePlayer";
constexpr int kCacheMaxWidth = 1280;                       ///< キャッシュする画像の最大幅。
constexpr std::size_t kCacheBytes = std::size_t{4} << 30;  ///< 主メモリにキャッシュするときの上限(4GB)。
constexpr std::size_t kGpuCacheMaxBytes = std::size_t{8} << 30;      ///< GPUのメモリにキャッシュするときの上限の最大(8GB)。
constexpr std::size_t kGpuCacheDefaultBytes = std::size_t{2} << 30;  ///< GPUのメモリの予算が分からないときの上限(2GB)。
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
constexpr COLORREF kDisabled = RGB(110, 110, 110);
constexpr wchar_t kSettingsKey[] = L"Software\\FramePlayer";  ///< 設定の保存先(HKEY_CURRENT_USERの下)。
constexpr float kVolumeStep = 0.05f;                             ///< ↑↓キーで変える音量の幅。
constexpr int kCompareLargeShift = 10;                           ///< Shift+[ ]で変える2本目のずらしの幅。
constexpr std::size_t kMaxRecentFiles = 8;                       ///< 「最近使ったファイル」に残す数。

/// ファイルのメニューの項目の番号。
enum MenuCommand : UINT {
    kMenuOpen = 1,
    kMenuOpenCompare,
    kMenuCloseCompare,
    kMenuClearRecent,
    kMenuExit,
    kMenuRecentFirst = 100,  ///< 最近使ったファイルの1つ目(以降、順に番号を振る)。
};

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
    loadAudioSettings();
    loadRecentFiles();
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
    // GPUが使えれば、デコード・キャッシュ・描画で同じデバイスを使う(GPUのメモリにあるコマをそのまま描くため)。
    gpu_ = GpuDevice::create();
    if (!view_.create(instance, hwnd_, kViewFrameMessage, gpu_)) {
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
    resumeAfterScrub_ = false;  // 別の動画を開くときは、ドラッグ前の再生を引き継がない。
    endScrub();
    auto clip = std::make_shared<Clip>();
    std::wstring error;
    HCURSOR previousCursor = SetCursor(LoadCursorW(nullptr, IDC_WAIT));

    // 開くときは目次を作って先頭のコマを読むだけで、残りは裏のスレッドが先読みする。
    // 裏のスレッドからの知らせは、描画スレッドを起こす合図と、UIスレッドへのPostMessageにする。
    // UIへの知らせは、処理前のものが残っていれば送らない。
    const bool loaded = clip->open(
        path, kCacheMaxWidth, kCacheBytes, gpuCacheBytes(), gpu_,
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
    // 音声は無くても動画は再生できる(音声なしとして扱う)。
    auto audio = std::make_shared<AudioPlayer>();
    audio->open(path);
    audio->setVolume(volume_);
    audio->setMuted(muted_);

    clip_ = std::move(clip);
    audio_ = std::move(audio);
    addRecentFile(path);
    current_ = 0;
    cacheRuns_.clear();
    cacheRunsTrack_ = RECT{};
    view_.setClip(clip_, audio_);
    clip_->setPlayhead(0, Clip::Direction::Forward, false);
    if (compareClip_) {
        // 比較中に1本目を差し替えた場合は、比較を続ける(キャッシュは半分ずつ)。
        clip_->setCacheLimit(cacheLimitFor(clip_->cachesOnGpu(), true));
        view_.setCompareClip(compareClip_);
    }
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
        // 他のウィンドウにマウスを取られたときもドラッグを終える(endScrub()の中で外したときは何もしない)。
        if (scrubbing_ || volumeDragging_) {
            const bool resume = scrubbing_ && resumeAfterScrub_;
            scrubbing_ = false;
            volumeDragging_ = false;
            resumeAfterScrub_ = false;
            if (resume) {
                resumePlayback();
            }
        }
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
        compareClip_.reset();
        clip_.reset();
        audio_.reset();
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
    layout.fileButton = {client.left + margin, buttonTop, client.left + margin + scaled(72, dpi), buttonTop + buttonSize};
    const int playLeft = layout.fileButton.right + scaled(8, dpi);
    layout.button = {playLeft, buttonTop, playLeft + buttonSize, buttonTop + buttonSize};
    const int infoLeft = std::max(static_cast<int>(layout.button.right),
                                  static_cast<int>(client.right) - margin - scaled(300, dpi));
    layout.info = {infoLeft, barTop, client.right - margin, client.bottom};
    // 音量(スピーカーのボタンと音量スライダー)はコマ番号の左に置く。
    const int volumeRight = layout.info.left - scaled(12, dpi);
    const int volumeLeft = volumeRight - scaled(90, dpi);
    layout.volumeSlider = {volumeLeft, barTop + barHeight / 2 - scaled(3, dpi), volumeRight,
                           barTop + barHeight / 2 + scaled(3, dpi)};
    const int speakerSize = scaled(24, dpi);
    const int speakerTop = barTop + (barHeight - speakerSize) / 2;
    layout.volumeButton = {volumeLeft - scaled(6, dpi) - speakerSize, speakerTop, volumeLeft - scaled(6, dpi),
                           speakerTop + speakerSize};
    const int compareWidth = scaled(52, dpi);
    const int compareHeight = scaled(26, dpi);
    const int compareTop = barTop + (barHeight - compareHeight) / 2;
    layout.compareButton = {layout.volumeButton.left - scaled(12, dpi) - compareWidth, compareTop,
                            layout.volumeButton.left - scaled(12, dpi), compareTop + compareHeight};
    layout.slider = {layout.button.right + scaled(10, dpi), barTop + scaled(6, dpi),
                     layout.compareButton.left - scaled(12, dpi), client.bottom - scaled(6, dpi)};
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
    paintVolume(dc, layout, dpi);

    // 「ファイル」ボタン。押すとファイルのメニューを出す。
    {
        RECT b = layout.fileButton;
        fillColor(dc, b, kControlFace);
        HFONT buttonFont = createUiFont(9, dpi);
        HGDIOBJ oldButtonFont = SelectObject(dc, buttonFont);
        SetTextColor(dc, kText);
        DrawTextW(dc, L"ファイル \u25BE", -1, &b, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        SelectObject(dc, oldButtonFont);
        DeleteObject(buttonFont);
    }

    // 「比較」ボタン。比較中は色を付けて、押すと比較をやめることを示す。
    {
        RECT b = layout.compareButton;
        fillColor(dc, b, compareClip_ ? kSliderPlayed : kControlFace);
        HFONT buttonFont = createUiFont(9, dpi);
        HGDIOBJ oldButtonFont = SelectObject(dc, buttonFont);
        SetTextColor(dc, kText);
        DrawTextW(dc, compareClip_ ? L"比較 ×" : L"比較", -1, &b, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        SelectObject(dc, oldButtonFont);
        DeleteObject(buttonFont);
    }

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
    } else if (compareClip_) {
        std::swprintf(text, 128, L"%d / %d   %.4g fps  ずらし %+d", current_ + 1, count, playbackRate(),
                      view_.compareOffset());
    } else {
        std::swprintf(text, 128, L"%d / %d   %.4g fps", current_ + 1, count, playbackRate());
    }
    SetTextColor(dc, kText);
    RECT infoRect = layout.info;
    DrawTextW(dc, text, -1, &infoRect, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

void PlayerWindow::onKeyDown(WPARAM key) {
    const bool shift = GetKeyState(VK_SHIFT) < 0;
    // Ctrl+O: 1本目をファイル選択画面で開く。Ctrl+Shift+O: 2本目(比較)を開く。
    if (key == 'O' && GetKeyState(VK_CONTROL) < 0) {
        const std::wstring path = chooseVideoFile(shift ? L"比較する動画を選択" : L"動画を選択");
        if (!path.empty()) {
            if (shift) {
                openCompare(path);
            } else {
                openClip(path);
            }
        }
        return;
    }
    // [ ]: 比較中の2本目のずらしを1コマ(Shift併用で10コマ)変える。
    if ((key == VK_OEM_4 || key == VK_OEM_6) && compareClip_) {
        const int amount = shift ? kCompareLargeShift : 1;
        shiftCompare(key == VK_OEM_4 ? -amount : amount);
        return;
    }
    // 音量の操作は動画を開いていなくても受け付ける。
    switch (key) {
    case 'M':
        toggleMute();
        return;
    case VK_UP:
        setVolume(volume_ + kVolumeStep);
        return;
    case VK_DOWN:
        setVolume(volume_ - kVolumeStep);
        return;
    default:
        break;
    }
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
    const Layout layout = computeLayout();
    const POINT point{x, y};
    // 音量スライダーは細いので、操作部の高さいっぱいまで当たり判定を広げる。
    RECT volumeHit = layout.volumeSlider;
    volumeHit.top = layout.bar.top;
    volumeHit.bottom = layout.bar.bottom;
    InflateRect(&volumeHit, scaled(4, static_cast<int>(GetDpiForWindow(hwnd_))), 0);
    if (PtInRect(&layout.fileButton, point)) {
        showFileMenu();
        return;
    }
    if (PtInRect(&layout.volumeButton, point)) {
        toggleMute();
        return;
    }
    if (PtInRect(&layout.compareButton, point)) {
        if (compareClip_) {
            closeCompare();
        } else {
            const std::wstring path = chooseVideoFile(L"比較する動画を選択");
            if (!path.empty()) {
                openCompare(path);
            }
        }
        return;
    }
    if (PtInRect(&volumeHit, point)) {
        volumeDragging_ = true;
        SetCapture(hwnd_);
        setVolume(volumeFromX(x));
        return;
    }
    if (!clip_) {
        return;
    }
    if (PtInRect(&layout.button, point)) {
        togglePlayback();
    } else if (PtInRect(&layout.slider, point)) {
        // ドラッグ中にウィンドウ外へ出てもマウスの動きを受け取れるよう、マウスを取り込む。
        // 再生中に触った場合は、ドラッグ中はそのコマを表示し、離したらその位置から再生を続ける(YouTubeと同じ)。
        resumeAfterScrub_ = view_.isPlaying();
        scrubbing_ = true;
        SetCapture(hwnd_);
        goToFrame(frameFromX(x));
    }
}

void PlayerWindow::onMouseMove(int x) {
    if (volumeDragging_) {
        setVolume(volumeFromX(x));
    } else if (scrubbing_ && clip_) {
        goToFrame(frameFromX(x));
    }
}

void PlayerWindow::endScrub() {
    const bool resume = scrubbing_ && resumeAfterScrub_;
    if (scrubbing_ || volumeDragging_) {
        // ReleaseCapture()はWM_CAPTURECHANGEDをすぐ送ってくるので、先に状態を戻しておく。
        scrubbing_ = false;
        volumeDragging_ = false;
        resumeAfterScrub_ = false;
        ReleaseCapture();
    }
    if (resume) {
        resumePlayback();
    }
}

void PlayerWindow::resumePlayback() {
    if (clip_ && !view_.isPlaying()) {
        view_.play(playbackRate());
        syncPowerRequest();
        invalidateBar();
    }
}

void PlayerWindow::paintVolume(HDC dc, const Layout& layout, int dpi) {
    // 比較中は音声を鳴らさないので、音声なしと同じく薄く表示する。
    const bool hasAudio = audio_ && audio_->hasAudio() && !compareClip_;
    // 音声の無い動画のときは、操作はできるが薄い色で描く(設定は次の動画に引き継がれる)。
    const COLORREF ink = (clip_ && !hasAudio) ? kDisabled : kText;

    // スピーカーの形(四角+台形)。消音中は×、そうでなければ音の大きさに応じて弧を描く。
    const RECT& b = layout.volumeButton;
    const int cy = (b.top + b.bottom) / 2;
    const int unit = std::max(1, static_cast<int>((b.bottom - b.top) / 8));
    const int left = b.left + unit;
    const POINT speaker[] = {{left, cy - unit},         {left + 2 * unit, cy - unit}, {left + 4 * unit, cy - 3 * unit},
                             {left + 4 * unit, cy + 3 * unit}, {left + 2 * unit, cy + unit}, {left, cy + unit}};
    HBRUSH brush = CreateSolidBrush(ink);
    HPEN pen = CreatePen(PS_SOLID, std::max(1, scaled(2, dpi) / 2 + 1), ink);
    HGDIOBJ oldBrush = SelectObject(dc, brush);
    HGDIOBJ oldPen = SelectObject(dc, pen);
    Polygon(dc, speaker, static_cast<int>(std::size(speaker)));
    SelectObject(dc, GetStockObject(NULL_BRUSH));
    const int waveX = left + 5 * unit;
    if (muted_) {
        MoveToEx(dc, waveX, cy - 2 * unit, nullptr);
        LineTo(dc, waveX + 3 * unit, cy + 2 * unit);
        MoveToEx(dc, waveX + 3 * unit, cy - 2 * unit, nullptr);
        LineTo(dc, waveX, cy + 2 * unit);
    } else {
        const int waves = volume_ <= 0.0f ? 0 : (volume_ < 0.5f ? 1 : 2);
        for (int i = 1; i <= waves; ++i) {
            const int r = (i + 1) * unit + unit / 2;
            Arc(dc, waveX - r, cy - r, waveX + r, cy + r, waveX + r, cy + r, waveX + r, cy - r);
        }
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(brush);
    DeleteObject(pen);

    // 音量スライダー。消音中は塗りを薄くする。
    const RECT& s = layout.volumeSlider;
    fillColor(dc, s, kSliderFace);
    const int filled = s.left + static_cast<int>((s.right - s.left) * volume_ + 0.5f);
    fillColor(dc, RECT{s.left, s.top, filled, s.bottom}, (muted_ || !hasAudio) ? kDisabled : kCached);
    const int knob = std::max(2, scaled(3, dpi));
    fillColor(dc, RECT{filled - knob, s.top - knob, filled + knob, s.bottom + knob}, ink);
}

void PlayerWindow::setVolume(float volume) {
    volume_ = std::clamp(volume, 0.0f, 1.0f);
    muted_ = false;  // 音量を変えたら消音は解除する(一般的なプレイヤーと同じ)。
    if (audio_) {
        audio_->setVolume(volume_);
        audio_->setMuted(false);
    }
    saveAudioSettings();
    invalidateBar();
}

void PlayerWindow::toggleMute() {
    muted_ = !muted_;
    if (audio_) {
        audio_->setMuted(muted_);
    }
    saveAudioSettings();
    invalidateBar();
}

float PlayerWindow::volumeFromX(int x) const {
    const RECT s = computeLayout().volumeSlider;
    const int width = std::max(1L, s.right - s.left);
    return std::clamp(static_cast<float>(x - s.left) / width, 0.0f, 1.0f);
}

void PlayerWindow::loadAudioSettings() {
    DWORD value = 0;
    DWORD size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"Volume", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
        ERROR_SUCCESS) {
        volume_ = std::clamp(static_cast<float>(value) / 100.0f, 0.0f, 1.0f);
    }
    size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"Muted", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
        ERROR_SUCCESS) {
        muted_ = value != 0;
    }
}

void PlayerWindow::saveAudioSettings() const {
    const DWORD volume = static_cast<DWORD>(volume_ * 100.0f + 0.5f);
    const DWORD muted = muted_ ? 1 : 0;
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, L"Volume", REG_DWORD, &volume, sizeof(volume));
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, L"Muted", REG_DWORD, &muted, sizeof(muted));
}

void PlayerWindow::onDropFiles(HDROP drop) {
    const UINT count = DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
    std::vector<std::wstring> paths;
    for (UINT i = 0; i < std::min(count, 2u); ++i) {
        wchar_t path[MAX_PATH * 4];
        if (DragQueryFileW(drop, i, path, static_cast<UINT>(std::size(path))) > 0) {
            paths.emplace_back(path);
        }
    }
    POINT point{};
    DragQueryPoint(drop, &point);  // 落とした位置(クライアント座標)。
    DragFinish(drop);
    if (paths.empty()) {
        return;
    }
    if (paths.size() >= 2) {
        openClip(paths[0]);
        if (clip_) {
            openCompare(paths[1]);
        }
        return;
    }
    // 1つだけなら、1本目を開いている状態で映像の右半分へ落としたときは2本目(比較)にする。
    const RECT video = computeLayout().video;
    const bool rightHalf = PtInRect(&video, point) && point.x >= (video.left + video.right) / 2;
    if (clip_ && rightHalf) {
        openCompare(paths[0]);
    } else {
        openClip(paths[0]);
    }
}

void PlayerWindow::showFileMenu() {
    HMENU menu = CreatePopupMenu();
    HMENU recent = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, kMenuOpen, L"動画を開く...\tCtrl+O");
    AppendMenuW(menu, MF_STRING | (clip_ ? 0 : MF_GRAYED), kMenuOpenCompare, L"比較する動画を開く...\tCtrl+Shift+O");
    AppendMenuW(menu, MF_STRING | (compareClip_ ? 0 : MF_GRAYED), kMenuCloseCompare, L"比較を終了");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    // 最近使ったファイル。左にファイル名、右(タブの後ろ)にフォルダーを出す。
    for (std::size_t i = 0; i < recentFiles_.size(); ++i) {
        const std::wstring& path = recentFiles_[i];
        const size_t slash = path.find_last_of(L"\\/");
        const std::wstring name = slash == std::wstring::npos ? path : path.substr(slash + 1);
        const std::wstring folder = slash == std::wstring::npos ? std::wstring() : path.substr(0, slash);
        // &はメニューでは下線の印になるので、&&にして文字として出す。
        std::wstring label;
        for (wchar_t c : name) {
            label += c;
            if (c == L'&') {
                label += L'&';
            }
        }
        label += L"\t" + folder;
        AppendMenuW(recent, MF_STRING, kMenuRecentFirst + static_cast<UINT>(i), label.c_str());
    }
    if (!recentFiles_.empty()) {
        AppendMenuW(recent, MF_SEPARATOR, 0, nullptr);
    }
    AppendMenuW(recent, MF_STRING | (recentFiles_.empty() ? MF_GRAYED : 0), kMenuClearRecent, L"一覧を消去");
    AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(recent), L"最近使ったファイル");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, kMenuExit, L"終了");

    // 操作部は画面の下にあるので、ボタンの上端から上向きに開く。選ぶか閉じるまで戻らない。
    const RECT b = computeLayout().fileButton;
    POINT corner{b.left, b.top};
    ClientToScreen(hwnd_, &corner);
    const UINT command = static_cast<UINT>(TrackPopupMenu(
        menu, TPM_RETURNCMD | TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_NONOTIFY, corner.x, corner.y, 0, hwnd_, nullptr));
    DestroyMenu(menu);  // 中の「最近使ったファイル」も一緒に破棄される。

    switch (command) {
    case kMenuOpen: {
        const std::wstring path = chooseVideoFile(L"動画を選択");
        if (!path.empty()) {
            openClip(path);
        }
        break;
    }
    case kMenuOpenCompare: {
        const std::wstring path = chooseVideoFile(L"比較する動画を選択");
        if (!path.empty()) {
            openCompare(path);
        }
        break;
    }
    case kMenuCloseCompare:
        closeCompare();
        break;
    case kMenuClearRecent:
        recentFiles_.clear();
        saveRecentFiles();
        break;
    case kMenuExit:
        PostMessageW(hwnd_, WM_CLOSE, 0, 0);
        break;
    default:
        if (command >= kMenuRecentFirst && command < kMenuRecentFirst + recentFiles_.size()) {
            const std::wstring path = recentFiles_[command - kMenuRecentFirst];  // openClipで一覧が変わるので写す。
            openClip(path);
        }
        break;
    }
}

void PlayerWindow::addRecentFile(const std::wstring& path) {
    // 同じファイルは先頭へ移す(大文字小文字を区別しない)。
    recentFiles_.erase(std::remove_if(recentFiles_.begin(), recentFiles_.end(),
                                      [&](const std::wstring& item) { return _wcsicmp(item.c_str(), path.c_str()) == 0; }),
                       recentFiles_.end());
    recentFiles_.insert(recentFiles_.begin(), path);
    if (recentFiles_.size() > kMaxRecentFiles) {
        recentFiles_.resize(kMaxRecentFiles);
    }
    saveRecentFiles();
}

void PlayerWindow::loadRecentFiles() {
    // REG_MULTI_SZ(文字列を\0で区切って並べ、最後に\0をもう1つ置いたもの)で保存してある。
    DWORD size = 0;
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", RRF_RT_REG_MULTI_SZ, nullptr, nullptr, &size) !=
            ERROR_SUCCESS ||
        size == 0) {
        return;
    }
    std::vector<wchar_t> buffer(size / sizeof(wchar_t) + 1, L'\0');
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", RRF_RT_REG_MULTI_SZ, nullptr, buffer.data(),
                     &size) != ERROR_SUCCESS) {
        return;
    }
    recentFiles_.clear();
    for (const wchar_t* p = buffer.data(); *p && recentFiles_.size() < kMaxRecentFiles; p += wcslen(p) + 1) {
        recentFiles_.emplace_back(p);
    }
}

void PlayerWindow::saveRecentFiles() const {
    std::wstring data;
    for (const std::wstring& path : recentFiles_) {
        data += path;
        data += L'\0';
    }
    data += L'\0';
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", REG_MULTI_SZ, data.data(),
                    static_cast<DWORD>(data.size() * sizeof(wchar_t)));
}

std::wstring PlayerWindow::chooseVideoFile(const wchar_t* title) {
    // Windows標準のファイル選択画面(COMの部品)。UIスレッドはCOM初期化済み(main.cpp)。
    Microsoft::WRL::ComPtr<IFileOpenDialog> dialog;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog)))) {
        return std::wstring();
    }
    const COMDLG_FILTERSPEC types[] = {
        {L"動画ファイル", L"*.mp4;*.mov;*.m4v;*.avi;*.wmv;*.mkv;*.mts;*.m2ts"},
        {L"すべてのファイル", L"*.*"},
    };
    dialog->SetFileTypes(static_cast<UINT>(std::size(types)), types);
    dialog->SetTitle(title);
    if (FAILED(dialog->Show(hwnd_))) {
        return std::wstring();  // 取り消された。
    }
    Microsoft::WRL::ComPtr<IShellItem> item;
    PWSTR path = nullptr;
    if (FAILED(dialog->GetResult(&item)) || FAILED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
        return std::wstring();
    }
    std::wstring result = path;
    CoTaskMemFree(path);
    return result;
}

std::size_t PlayerWindow::cacheLimitFor(bool onGpu, bool comparing) const {
    const std::size_t limit = onGpu ? gpuCacheBytes() : kCacheBytes;
    return comparing ? limit / 2 : limit;
}

void PlayerWindow::openCompare(const std::wstring& path) {
    if (!clip_) {
        openClip(path);
        return;
    }
    view_.stop();
    syncPowerRequest();
    auto clip = std::make_shared<Clip>();
    std::wstring error;
    HCURSOR previousCursor = SetCursor(LoadCursorW(nullptr, IDC_WAIT));
    // 2本目は最初から半分の上限で開く(1本目も下で半分にする)。音声は開かない(比較中は鳴らさない)。
    const bool loaded = clip->open(
        path, kCacheMaxWidth, cacheLimitFor(false, true), cacheLimitFor(true, true), gpu_,
        [this] {
            view_.wake();
            if (!frameReadyPending_.exchange(true)) {
                PostMessageW(hwnd_, kFrameReadyMessage, 0, 0);
            }
        },
        error);
    SetCursor(previousCursor);
    if (!loaded) {
        MessageBoxW(hwnd_, (path + L"\n\n" + error).c_str(), kAppName, MB_OK | MB_ICONWARNING);
        return;
    }
    compareClip_ = std::move(clip);
    addRecentFile(path);
    clip_->setCacheLimit(cacheLimitFor(clip_->cachesOnGpu(), true));
    view_.setCompareOffset(0);
    view_.setCompareClip(compareClip_);
    view_.showFrame(view_.currentFrame(), Clip::Direction::Forward);
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::closeCompare() {
    view_.setCompareClip(nullptr);
    compareClip_.reset();
    if (clip_) {
        clip_->setCacheLimit(cacheLimitFor(clip_->cachesOnGpu(), false));
    }
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::shiftCompare(int delta) {
    view_.setCompareOffset(view_.compareOffset() + delta);
    invalidateBar();
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

std::size_t PlayerWindow::gpuCacheBytes() const {
    // 他のアプリや画面表示にもGPUのメモリが要るので、予算の半分までにする。
    const std::size_t budget = gpu_ ? gpu_->localMemoryBudget() : 0;
    return budget > 0 ? std::min(kGpuCacheMaxBytes, budget / 2) : kGpuCacheDefaultBytes;
}

void PlayerWindow::updateTitle() {
    if (!clip_) {
        SetWindowTextW(hwnd_, kAppName);
        return;
    }
    wchar_t title[1024];
    std::wstring names = fileNameOf(clip_->path());
    if (compareClip_) {
        names += L" | " + fileNameOf(compareClip_->path());
    }
    std::swprintf(title, 1024, L"%ls - %ls [%d / %d]", names.c_str(), kAppName, current_ + 1, clip_->frameCount());
    SetWindowTextW(hwnd_, title);
}

}  // namespace frameplayer
