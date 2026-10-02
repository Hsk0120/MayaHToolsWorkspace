/**
 * @file PlayerWindow.cpp
 * @brief プレイヤーのメインウィンドウの実装。
 */
#include "app/PlayerWindow.h"

#include <dwmapi.h>
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
// キャッシュの上限。MayaやUnreal Engineと同時に使っても邪魔にならないよう、既定は控えめにする。
// 実際の上限は、設定(CacheMB・CacheSeconds)・GPUのメモリの予算の1/4・主メモリの残りのうち最も小さいもの。
constexpr std::size_t kDefaultCacheMegabytes = 1024;  ///< キャッシュの上限の既定値(MB)。
constexpr int kDefaultCacheSeconds = 30;              ///< キャッシュに持つ長さの既定値(秒)。
constexpr std::size_t kMinCacheBytes = std::size_t{64} << 20;     ///< 上限を下げるときの下限(64MB)。
constexpr std::size_t kLowMemoryCacheBytes = std::size_t{256} << 20;  ///< 主メモリが足りないときの上限(256MB)。
constexpr int kThumbnailWidth = 320;                                ///< キーフレームの縮小画像の幅。
constexpr std::size_t kThumbnailBytes = std::size_t{160} << 20;    ///< 縮小画像の合計の上限(1本あたり160MB)。
constexpr UINT_PTR kResourceTimerId = 1;          ///< キャッシュの上限の見直しと休止の判定に使うタイマー。
constexpr UINT kResourceTimerMs = 2000;           ///< そのタイマーの間隔(ミリ秒)。
constexpr ULONGLONG kDormantAfterMinimizedMs = 30 * 1000;    ///< 最小化してから休止に入るまで(30秒)。
constexpr ULONGLONG kDormantAfterInactiveMs = 5 * 60 * 1000;  ///< 背面になってから休止に入るまで(5分)。
constexpr int kLargeStep = 10;                             ///< Shift併用時に移動するコマ数。
constexpr double kDefaultRate = 24.0;                      ///< フレームレートが不明な動画の再生速度。
constexpr UINT kViewFrameMessage = WM_APP + 1;   ///< VideoViewが表示するコマを変えたときの知らせ。
constexpr UINT kFrameReadyMessage = WM_APP + 2;  ///< 裏の読み込みでコマがキャッシュに入ったときの知らせ。
constexpr LONGLONG kCacheBarIntervalMs = 200;    ///< キャッシュ表示を計算し直す最短間隔(ミリ秒)。

// 色はWindows 11標準の「メディア プレーヤー」に合わせる(同じ動画を再生した画面から測った値)。
constexpr COLORREF kBackground = RGB(0, 0, 0);       ///< 映像の周りの背景。
constexpr COLORREF kSurface = RGB(20, 20, 20);       ///< タイトルバー・タイムライン・操作パネルの地(#141414)。
constexpr COLORREF kTrack = RGB(148, 148, 148);      ///< タイムラインのバーのうちキャッシュに無い部分(#949494)。
constexpr COLORREF kAccent = RGB(255, 130, 50);      ///< 強調色(キャッシュの帯・音量・比較中のボタン。#FF8232)。
constexpr COLORREF kIcon = RGB(255, 255, 255);       ///< 移動・再生ボタンの記号。
constexpr COLORREF kSubText = RGB(255, 255, 255);    ///< 補足の文字(コマ数・fps。メディア プレーヤーの時刻と同じ白)。
constexpr COLORREF kVolumeTrack = RGB(69, 69, 69);   ///< 音量の三角形の地(#454545。メディア プレーヤーのつまみの色)。
constexpr COLORREF kText = RGB(255, 255, 255);
constexpr COLORREF kControlFace = RGB(38, 38, 38);    ///< 文字のボタンの地。
constexpr COLORREF kControlBorder = RGB(51, 51, 51);  ///< 文字のボタンの枠。
constexpr COLORREF kDisabled = RGB(106, 106, 106);    ///< 使えない記号(#6A6A6A)。
constexpr DWORD kDwmUseImmersiveDarkMode = 20;  ///< DWMWA_USE_IMMERSIVE_DARK_MODE(古いSDKに無い場合があるので番号で持つ)。
constexpr DWORD kDwmCaptionColor = 35;          ///< DWMWA_CAPTION_COLOR(Windows 11以降)。
constexpr DWORD kDwmTextColor = 36;             ///< DWMWA_TEXT_COLOR(Windows 11以降)。
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
 * @brief 矩形を既存のブラシで塗る。
 * @param dc 描画先。
 * @param rect 塗る範囲。
 * @param brush ブラシ(呼び出し元が持つ)。
 */
void fillColorBrush(HDC dc, const RECT& rect, HBRUSH brush) {
    FillRect(dc, &rect, brush);
}

/**
 * @brief Windows 11の標準の文字(Segoe UI Variable)が使えるか調べる。
 * @return 使えればtrue。結果は最初の1回だけ調べて覚えておく。
 */
bool hasVariableFont() {
    static const bool found = [] {
        HDC dc = GetDC(nullptr);
        LOGFONTW query{};
        query.lfCharSet = DEFAULT_CHARSET;
        wcscpy_s(query.lfFaceName, L"Segoe UI Variable Text");
        bool exists = false;
        EnumFontFamiliesExW(
            dc, &query,
            [](const LOGFONTW*, const TEXTMETRICW*, DWORD, LPARAM param) -> int {
                *reinterpret_cast<bool*>(param) = true;
                return 0;
            },
            reinterpret_cast<LPARAM>(&exists), 0);
        ReleaseDC(nullptr, dc);
        return exists;
    }();
    return found;
}

/**
 * @brief タイトルバーをダークにし、操作部と同じ色にする(Windows 11のアプリと同じ見た目)。
 * @param hwnd 対象のウィンドウ。
 * @note Windows 10では色の指定が効かず、ダークの指定だけが効く(失敗しても表示に支障はない)。
 */
void applyModernTitleBar(HWND hwnd) {
    const BOOL dark = TRUE;
    DwmSetWindowAttribute(hwnd, kDwmUseImmersiveDarkMode, &dark, sizeof(dark));
    const COLORREF caption = kSurface;
    DwmSetWindowAttribute(hwnd, kDwmCaptionColor, &caption, sizeof(caption));
    const COLORREF text = kText;
    DwmSetWindowAttribute(hwnd, kDwmTextColor, &text, sizeof(text));
}

/**
 * @brief 指定サイズのSegoe UIフォントを作る。
 * @param points 文字の大きさ(ポイント)。
 * @param dpi ウィンドウのDPI。
 * @return 作成したフォント。呼び出し元がDeleteObjectで解放する。
 */
HFONT createUiFont(int points, int dpi) {
    return CreateFontW(-MulDiv(points, dpi, 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                       OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH,
                       hasVariableFont() ? L"Segoe UI Variable Text" : L"Segoe UI");
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
    loadCacheSettings();
    // 主メモリが足りなくなるとWindowsが合図するので、タイマーで確かめてキャッシュを減らす。
    lowMemory_ = CreateMemoryResourceNotification(LowMemoryResourceNotification);
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
    // 表示する前にタイトルバーの色を決めておく(白いタイトルバーが一瞬見えないように)。
    applyModernTitleBar(hwnd_);
    SetTimer(hwnd_, kResourceTimerId, kResourceTimerMs, nullptr);
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
    const bool comparing = compareClip_ != nullptr;
    const bool loaded = clip->open(
        path, kCacheMaxWidth, cacheLimitFor(false, comparing), cacheLimitFor(true, comparing), gpu_,
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
    // 描画スレッドへ渡す前に、上限・動作状態・縮小画像を決めておく(preview()は描画スレッドから呼ばれる)。
    appliedLimit_[0] = 0;
    appliedFrames_[0] = 0;
    applyCacheLimits();
    clip_->setActivity(activity_);
    clip_->startThumbnails(kThumbnailWidth, kThumbnailBytes);
    view_.setClip(clip_, audio_);
    clip_->setPlayhead(0, Clip::Direction::Forward, false);
    if (compareClip_) {
        // 比較中に1本目を差し替えた場合は、比較を続ける(キャッシュは半分ずつ)。
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
        if ((wParam == SIZE_MINIMIZED) != minimized_) {
            minimized_ = wParam == SIZE_MINIMIZED;
            minimizedSinceMs_ = GetTickCount64();
            updateActivity();
        }
        return 0;
    case WM_ACTIVATEAPP:
        // 他のアプリが前面になったら先読みを控え、戻ってきたら再開する。
        appActive_ = wParam != FALSE;
        if (!appActive_) {
            inactiveSinceMs_ = GetTickCount64();
        }
        updateActivity();
        return 0;
    case WM_TIMER:
        if (wParam == kResourceTimerId) {
            onResourceTimer();
        }
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
        KillTimer(hwnd_, kResourceTimerId);
        compareClip_.reset();
        clip_.reset();
        audio_.reset();
        releaseFonts();
        if (lowMemory_) {
            CloseHandle(lowMemory_);
            lowMemory_ = nullptr;
        }
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
    // Keyframe Proと同じく、下から「操作パネル」「タイムライン」の2段。映像はその上に余白なしで置く。
    const int panelHeight = scaled(36, dpi);
    const int timelineHeight = scaled(34, dpi);
    const int panelTop = std::max(static_cast<int>(client.top), static_cast<int>(client.bottom) - panelHeight);
    const int timelineTop = std::max(static_cast<int>(client.top), panelTop - timelineHeight);
    const int margin = scaled(8, dpi);

    Layout layout;
    layout.video = {client.left, client.top, client.right, timelineTop};
    layout.bar = {client.left, timelineTop, client.right, client.bottom};
    layout.timeline = {client.left, timelineTop, client.right, panelTop};
    layout.panel = {client.left, panelTop, client.right, client.bottom};

    // タイムライン: 左に全体のコマ数、右にフレームレートなど、間に細いバー。バーの上に今のコマ番号を出す。
    layout.totalLabel = {client.left + margin, timelineTop, client.left + margin + scaled(80, dpi), panelTop};
    layout.rateLabel = {std::max(static_cast<int>(layout.totalLabel.right), static_cast<int>(client.right) -
                                                                                margin - scaled(64, dpi)),
                        timelineTop, client.right - margin, panelTop};
    const int trackHeight = scaled(6, dpi);
    const int trackTop = panelTop - scaled(8, dpi) - trackHeight;
    layout.track = {layout.totalLabel.right + scaled(8, dpi), trackTop, layout.rateLabel.left - scaled(8, dpi),
                    trackTop + trackHeight};

    // 操作パネル: 左に「ファイル」「比較」、中央に移動・再生のボタン、右に音量。
    const int buttonHeight = scaled(26, dpi);
    const int buttonTop = panelTop + (panelHeight - buttonHeight) / 2;
    layout.fileButton = {client.left + margin, buttonTop, client.left + margin + scaled(72, dpi), buttonTop + buttonHeight};
    layout.compareButton = {layout.fileButton.right + scaled(6, dpi), buttonTop,
                            layout.fileButton.right + scaled(6, dpi) + scaled(56, dpi), buttonTop + buttonHeight};

    const int transportSize = scaled(28, dpi);
    const int playSize = scaled(32, dpi);
    const int gap = scaled(4, dpi);
    const int transportWidth = transportSize * 4 + playSize + gap * 4;
    int x = (client.left + client.right) / 2 - transportWidth / 2;
    auto place = [&](int size) {
        const int top = panelTop + (panelHeight - size) / 2;
        const RECT r{x, top, x + size, top + size};
        x += size + gap;
        return r;
    };
    layout.startButton = place(transportSize);
    layout.prevButton = place(transportSize);
    layout.button = place(playSize);
    layout.nextButton = place(transportSize);
    layout.endButton = place(transportSize);

    const int volumeRight = client.right - margin;
    const int volumeWidth = scaled(80, dpi);
    const int volumeHeight = scaled(16, dpi);
    const int volumeTop = panelTop + (panelHeight - volumeHeight) / 2;
    layout.volumeSlider = {volumeRight - volumeWidth, volumeTop, volumeRight, volumeTop + volumeHeight};
    const int speakerSize = scaled(22, dpi);
    const int speakerTop = panelTop + (panelHeight - speakerSize) / 2;
    layout.volumeButton = {layout.volumeSlider.left - scaled(6, dpi) - speakerSize, speakerTop,
                           layout.volumeSlider.left - scaled(6, dpi), speakerTop + speakerSize};
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
    HGDIOBJ oldFont = SelectObject(dc, uiFont(14, dpi));
    SetBkMode(dc, TRANSPARENT);
    paintControls(dc, computeLayout(), dpi);

    SetViewportOrgEx(dc, 0, 0, nullptr);
    BitBlt(screen, area.left, area.top, width, height, dc, 0, 0, SRCCOPY);

    SelectObject(dc, oldFont);
    SelectObject(dc, oldBitmap);
    DeleteObject(backBuffer);
    DeleteDC(dc);
    EndPaint(hwnd_, &ps);
}

void PlayerWindow::paintControls(HDC dc, const Layout& layout, int dpi) {
    const bool playing = view_.isPlaying();
    // タイムラインと下段は、メディアプレイヤーと同じく1枚の地として塗る。
    fillColor(dc, layout.bar, kSurface);

    // 文字のボタン(「ファイル」「比較」)。比較中の「比較」は色を付けて、押すと比較をやめることを示す。
    HGDIOBJ oldFont = SelectObject(dc, uiFont(9, dpi));
    SetTextColor(dc, kText);
    {
        // 角を丸めた薄い地と枠。比較中は強調色の地に黒い文字(メディア プレーヤーの「ファイルを開く」と同じ)。
        const int radius = scaled(8, dpi);
        auto roundButton = [&](RECT b, COLORREF face, COLORREF border, COLORREF ink, const wchar_t* text) {
            HBRUSH brush = CreateSolidBrush(face);
            HPEN pen = CreatePen(PS_SOLID, 1, border);
            HGDIOBJ oldBrush = SelectObject(dc, brush);
            HGDIOBJ oldPen = SelectObject(dc, pen);
            RoundRect(dc, b.left, b.top, b.right, b.bottom, radius, radius);
            SelectObject(dc, oldBrush);
            SelectObject(dc, oldPen);
            DeleteObject(brush);
            DeleteObject(pen);
            SetTextColor(dc, ink);
            DrawTextW(dc, text, -1, &b, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        };
        roundButton(layout.fileButton, kControlFace, kControlBorder, kText, L"ファイル ▾");
        if (compareClip_) {
            roundButton(layout.compareButton, kAccent, kAccent, kBackground, L"比較 ×");
        } else {
            roundButton(layout.compareButton, kControlFace, kControlBorder, kText, L"比較");
        }
    }
    SelectObject(dc, oldFont);

    // 移動・再生のボタン(Keyframe Proと同じく枠なしの記号)。
    const COLORREF ink = clip_ ? kIcon : kDisabled;
    paintTransportIcon(dc, layout.startButton, TransportIcon::Start, ink);
    paintTransportIcon(dc, layout.prevButton, TransportIcon::Previous, ink);
    paintTransportIcon(dc, layout.button, playing ? TransportIcon::Pause : TransportIcon::Play, clip_ ? kText : kDisabled);
    paintTransportIcon(dc, layout.nextButton, TransportIcon::Next, ink);
    paintTransportIcon(dc, layout.endButton, TransportIcon::End, ink);

    paintVolume(dc, layout, dpi);

    // タイムライン(細いバー)。
    const RECT& t = layout.track;
    if (t.right <= t.left) {
        return;
    }
    fillColor(dc, t, kTrack);
    if (!clip_) {
        return;
    }
    const int count = clip_->frameCount();
    const int trackWidth = t.right - t.left;
    auto xOf = [&](int index) {
        return count > 1 ? t.left + static_cast<int>(static_cast<long long>(index) * trackWidth / (count - 1)) : t.left;
    };

    // キャッシュ済みのコマを、バーの中に青で示す。1画素に複数コマが入る場合は1つでもあれば塗る。
    // 調べるには全コマ(1時間60fpsで21万6千)を見るので、毎回の描画では計算し直さず、
    // 一定間隔(kCacheBarIntervalMs)ごと、またはバーの幅が変わったときだけ計算する。
    static const LONGLONG frequency = ticksPerSecond();
    const LONGLONG now = nowTicks();
    if (cacheRunsTrack_.left != t.left || cacheRunsTrack_.right != t.right ||
        (now - lastCacheBarTicks_) * 1000 / frequency >= kCacheBarIntervalMs) {
        clip_->cachedFlags(cacheFlags_);
        lastCacheBarTicks_ = now;
        cacheRunsTrack_ = t;
        cacheRuns_.clear();
        int runStart = -1;
        for (int px = t.left; px <= t.right; ++px) {
            bool cached = false;
            if (px < t.right && count > 0) {
                const long long span = std::max(1, trackWidth);
                const int first = static_cast<int>(static_cast<long long>(px - t.left) * (count - 1) / span);
                const int last = std::max(
                    first, static_cast<int>(static_cast<long long>(px + 1 - t.left) * (count - 1) / span) - 1);
                for (int i = first; i <= std::min(last, count - 1) && !cached; ++i) {
                    cached = cacheFlags_[static_cast<std::size_t>(i)] != 0;
                }
            }
            if (cached && runStart < 0) {
                runStart = px;
            } else if (!cached && runStart >= 0) {
                cacheRuns_.emplace_back(runStart, px);
                runStart = -1;
            }
        }
    }
    for (const auto& [left, right] : cacheRuns_) {
        fillColor(dc, RECT{left, t.top, right, t.bottom}, kAccent);
    }

    // 今の位置: バーを貫く白い線と、その上の大きめのコマ番号(1始まり)。
    const int playheadX = xOf(current_);
    const int lineHalf = std::max(1, scaled(1, dpi));
    fillColor(dc, RECT{playheadX - lineHalf / 2, t.top - scaled(5, dpi), playheadX - lineHalf / 2 + lineHalf + 1,
                       t.bottom + scaled(3, dpi)},
              kText);
    oldFont = SelectObject(dc, uiFont(11, dpi));
    SetTextColor(dc, kText);
    wchar_t currentText[32];
    std::swprintf(currentText, 32, L"%d", current_ + 1);
    SIZE textSize{};
    GetTextExtentPoint32W(dc, currentText, static_cast<int>(wcslen(currentText)), &textSize);
    // 番号は線の真上に置き、タイムラインの端からはみ出さないように寄せる。
    const int labelLeft = std::clamp(static_cast<int>(playheadX - textSize.cx / 2), static_cast<int>(t.left),
                                     static_cast<int>(t.right - textSize.cx));
    RECT currentRect{labelLeft, layout.timeline.top, labelLeft + textSize.cx, t.top - scaled(5, dpi)};
    DrawTextW(dc, currentText, -1, &currentRect, DT_LEFT | DT_BOTTOM | DT_SINGLELINE);
    SelectObject(dc, oldFont);

    // 左に全体のコマ数、右にフレームレート。
    oldFont = SelectObject(dc, uiFont(8, dpi));
    SetTextColor(dc, kSubText);
    wchar_t totalText[32];
    std::swprintf(totalText, 32, L"%d コマ", count);
    RECT totalRect{layout.totalLabel.left, t.top - scaled(6, dpi), layout.totalLabel.right, t.bottom + scaled(6, dpi)};
    DrawTextW(dc, totalText, -1, &totalRect, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
    wchar_t rateText[32];
    std::swprintf(rateText, 32, L"%.4g fps", playbackRate());
    RECT rateRect{layout.rateLabel.left, t.top - scaled(6, dpi), layout.rateLabel.right, t.bottom + scaled(6, dpi)};
    DrawTextW(dc, rateText, -1, &rateRect, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
    SelectObject(dc, oldFont);
}

void PlayerWindow::paintTransportIcon(HDC dc, const RECT& box, TransportIcon icon, COLORREF ink) {
    // 記号は箱の中央に、箱の大きさに合わせて描く。三角はPolygon、縦棒は四角で描く。
    const int cx = (box.left + box.right) / 2;
    const int cy = (box.top + box.bottom) / 2;
    const int h = std::max(3, static_cast<int>((box.bottom - box.top) / 4));  // 記号の高さの半分。
    const int bar = std::max(2, h / 3);
    HBRUSH brush = CreateSolidBrush(ink);
    HPEN pen = CreatePen(PS_SOLID, 1, ink);
    HGDIOBJ oldBrush = SelectObject(dc, brush);
    HGDIOBJ oldPen = SelectObject(dc, pen);
    auto triangleRight = [&](int left) {  // 右向きの三角(幅h)。
        const POINT p[] = {{left, cy - h}, {left, cy + h}, {left + h, cy}};
        Polygon(dc, p, 3);
    };
    auto triangleLeft = [&](int right) {  // 左向きの三角(幅h)。
        const POINT p[] = {{right, cy - h}, {right, cy + h}, {right - h, cy}};
        Polygon(dc, p, 3);
    };
    auto verticalBar = [&](int left) { fillColorBrush(dc, RECT{left, cy - h, left + bar, cy + h + 1}, brush); };
    switch (icon) {
    case TransportIcon::Play: {
        const int w = h * 3 / 2;
        const POINT p[] = {{cx - w / 2, cy - h - 1}, {cx - w / 2, cy + h + 1}, {cx + w - w / 2, cy}};
        Polygon(dc, p, 3);
        break;
    }
    case TransportIcon::Pause:
        fillColorBrush(dc, RECT{cx - h + 1, cy - h, cx - h + 1 + bar + 1, cy + h + 1}, brush);
        fillColorBrush(dc, RECT{cx + h - bar - 1, cy - h, cx + h, cy + h + 1}, brush);
        break;
    case TransportIcon::Start:  // |◀◀
        verticalBar(cx - h - bar);
        triangleLeft(cx);
        triangleLeft(cx + h);
        break;
    case TransportIcon::Previous:  // |◀
        verticalBar(cx - h / 2 - bar);
        triangleLeft(cx + h / 2);
        break;
    case TransportIcon::Next:  // ▶|
        triangleRight(cx - h / 2);
        verticalBar(cx + h / 2 + 1);
        break;
    case TransportIcon::End:  // ▶▶|
        triangleRight(cx - h);
        triangleRight(cx);
        verticalBar(cx + h + 1);
        break;
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(brush);
    DeleteObject(pen);
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
    // 音量の三角形は小さいので、操作パネルの高さいっぱいまで当たり判定を広げる。
    RECT volumeHit = layout.volumeSlider;
    volumeHit.top = layout.panel.top;
    volumeHit.bottom = layout.panel.bottom;
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
    const int current = view_.currentFrame();
    if (PtInRect(&layout.button, point)) {
        togglePlayback();
    } else if (PtInRect(&layout.startButton, point)) {
        goToFrame(0);
    } else if (PtInRect(&layout.prevButton, point)) {
        goToFrame(current - 1);
    } else if (PtInRect(&layout.nextButton, point)) {
        goToFrame(current + 1);
    } else if (PtInRect(&layout.endButton, point)) {
        goToFrame(clip_->frameCount() - 1);
    } else if (PtInRect(&layout.timeline, point)) {
        // タイムラインの段のどこを押してもよい(バーは細いので)。
        // ドラッグ中にウィンドウ外へ出てもマウスの動きを受け取れるよう、マウスを取り込む。
        // 再生中に触った場合は、ドラッグ中はそのコマを表示し、離したらその位置から再生を続ける(YouTubeと同じ)。
        resumeAfterScrub_ = view_.isPlaying();
        scrubbing_ = true;
        SetCapture(hwnd_);
        goToFrame(frameFromX(x), true);
    }
}

void PlayerWindow::onMouseMove(int x) {
    if (volumeDragging_) {
        setVolume(volumeFromX(x));
    } else if (scrubbing_ && clip_) {
        goToFrame(frameFromX(x), true);
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
    const COLORREF ink = (clip_ && !hasAudio) ? kDisabled : kIcon;

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

    // 音量は右上がりの三角形で示す(Keyframe Proと同じ)。左から音量の分だけ塗り、残りは枠だけ。
    const RECT& s = layout.volumeSlider;
    const int width = std::max(1L, s.right - s.left);
    const int height = s.bottom - s.top;
    const POINT outline[] = {{s.left, s.bottom}, {s.right, s.bottom}, {s.right, s.top}};
    HBRUSH trackBrush = CreateSolidBrush(kVolumeTrack);
    HPEN noPen = static_cast<HPEN>(GetStockObject(NULL_PEN));
    oldBrush = SelectObject(dc, trackBrush);
    oldPen = SelectObject(dc, noPen);
    Polygon(dc, outline, 3);
    const int fx = s.left + static_cast<int>(width * volume_ + 0.5f);
    if (fx > s.left) {
        const POINT filled[] = {{s.left, s.bottom}, {fx, s.bottom}, {fx, s.bottom - height * (fx - s.left) / width}};
        HBRUSH fillBrush = CreateSolidBrush((muted_ || !hasAudio) ? kDisabled : kAccent);
        SelectObject(dc, fillBrush);
        Polygon(dc, filled, 3);
        SelectObject(dc, trackBrush);
        DeleteObject(fillBrush);
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(trackBrush);

    // 音量の数字は三角形の左上の空いている所に小さく出す。
    HGDIOBJ oldFont = SelectObject(dc, uiFont(7, dpi));
    SetTextColor(dc, kSubText);
    wchar_t percent[16];
    std::swprintf(percent, 16, muted_ ? L"消音" : L"%d%%", static_cast<int>(volume_ * 100.0f + 0.5f));
    RECT percentRect{s.left, s.top - scaled(2, dpi), s.left + width * 2 / 3, s.top + height / 2};
    DrawTextW(dc, percent, -1, &percentRect, DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOCLIP);
    SelectObject(dc, oldFont);
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
    std::size_t limit = cacheMegabytes_ << 20;
    if (onGpu && gpu_) {
        // Windowsが示す予算は、ほかのアプリ(MayaやUnreal Engine)がGPUのメモリを使うほど小さくなる。
        // その1/4までにして、ほかのアプリの分を空けておく。
        const std::size_t budget = gpu_->localMemoryBudget();
        if (budget > 0) {
            limit = std::min(limit, budget / 4);
        }
    }
    if (memoryLow_) {
        // GPUのメモリに置いたキャッシュも主メモリの予約(コミット)を使うので、どちらの場合も減らす。
        limit = std::min(limit, kLowMemoryCacheBytes);
    }
    limit = std::max(limit, kMinCacheBytes);
    return comparing ? limit / 2 : limit;
}

int PlayerWindow::frameLimitFor(const Clip& clip) const {
    const double rate = clip.frameRate() > 0.0 ? clip.frameRate() : kDefaultRate;
    return std::max(1, static_cast<int>(std::lround(cacheSeconds_ * rate)));
}

void PlayerWindow::applyCacheLimits() {
    const bool comparing = compareClip_ != nullptr;
    Clip* clips[2] = {clip_.get(), compareClip_.get()};
    for (int i = 0; i < 2; ++i) {
        if (!clips[i]) {
            continue;
        }
        const std::size_t bytes = cacheLimitFor(clips[i]->cachesOnGpu(), comparing);
        const int frames = frameLimitFor(*clips[i]);
        if (bytes != appliedLimit_[i]) {
            clips[i]->setCacheLimit(bytes);
            appliedLimit_[i] = bytes;
        }
        if (frames != appliedFrames_[i]) {
            clips[i]->setFrameLimit(frames);
            appliedFrames_[i] = frames;
        }
    }
}

void PlayerWindow::updateActivity() {
    const ULONGLONG now = GetTickCount64();
    const bool playing = view_.isPlaying();
    const bool away = minimized_ || !appActive_;
    if (playing || !away) {
        dormant_ = false;
    } else if ((minimized_ && now - minimizedSinceMs_ >= kDormantAfterMinimizedMs) ||
               (!appActive_ && now - inactiveSinceMs_ >= kDormantAfterInactiveMs)) {
        dormant_ = true;
    }
    const Clip::Activity activity = playing   ? Clip::Activity::Playing
                                    : dormant_ ? Clip::Activity::Dormant
                                    : away     ? Clip::Activity::Background
                                               : Clip::Activity::Interactive;
    if (activity == activity_) {
        return;
    }
    activity_ = activity;
    if (clip_) {
        clip_->setActivity(activity);
    }
    if (compareClip_) {
        compareClip_->setActivity(activity);
    }
    if (activity == Clip::Activity::Dormant) {
        // 休止に入ったら、しばらく使っていない主メモリをWindowsへ返す(必要になれば自動で戻る)。
        SetProcessWorkingSetSize(GetCurrentProcess(), static_cast<SIZE_T>(-1), static_cast<SIZE_T>(-1));
    }
}

void PlayerWindow::onResourceTimer() {
    BOOL low = FALSE;
    memoryLow_ = lowMemory_ && QueryMemoryResourceNotification(lowMemory_, &low) && low;
    applyCacheLimits();
    updateActivity();
}

void PlayerWindow::loadCacheSettings() {
    DWORD value = 0;
    DWORD size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"CacheMB", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
        ERROR_SUCCESS) {
        cacheMegabytes_ = std::clamp<std::size_t>(value, 64, 64 * 1024);
    }
    size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"CacheSeconds", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
        ERROR_SUCCESS) {
        cacheSeconds_ = std::clamp<int>(static_cast<int>(value), 1, 24 * 60 * 60);
    }
}

HFONT PlayerWindow::uiFont(int points, int dpi) {
    if (dpi != fontsDpi_) {
        releaseFonts();
        fontsDpi_ = dpi;
    }
    for (const auto& [size, font] : fonts_) {
        if (size == points) {
            return font;
        }
    }
    HFONT font = createUiFont(points, dpi);
    fonts_.emplace_back(points, font);
    return font;
}

void PlayerWindow::releaseFonts() {
    for (const auto& entry : fonts_) {
        DeleteObject(entry.second);
    }
    fonts_.clear();
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
    // 2本目は最初から半分の上限で開く(1本目もapplyCacheLimits()で半分にする)。音声は開かない(比較中は鳴らさない)。
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
    // 描画スレッドへ渡す前に、上限・動作状態・縮小画像を決めておく。縮小画像は2本で半分ずつにする。
    compareClip_ = std::move(clip);
    addRecentFile(path);
    appliedLimit_[1] = 0;
    appliedFrames_[1] = 0;
    applyCacheLimits();
    compareClip_->setActivity(activity_);
    compareClip_->startThumbnails(kThumbnailWidth, kThumbnailBytes / 2);
    view_.setCompareOffset(0);
    view_.setCompareClip(compareClip_);
    view_.showFrame(view_.currentFrame(), Clip::Direction::Forward);
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::closeCompare() {
    view_.setCompareClip(nullptr);
    compareClip_.reset();
    appliedLimit_[1] = 0;
    appliedFrames_[1] = 0;
    applyCacheLimits();
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

void PlayerWindow::goToFrame(int index, bool scrubbing) {
    const int clamped = std::clamp(index, 0, clip_->frameCount() - 1);
    const bool wasPlaying = view_.isPlaying();
    const int shown = view_.currentFrame();
    if (clamped == shown && !wasPlaying) {
        return;
    }
    // 移動した向きに先読みさせる(←で戻り続けるときは前のコマを先に読む)。
    // ドラッグ中は向きが細かく入れ替わるので、前後に同じだけ先読みさせる(先読みの範囲が行ったり来たりしないように)。
    const auto direction = scrubbing ? Clip::Direction::Both
                           : clamped < shown ? Clip::Direction::Backward
                                             : Clip::Direction::Forward;
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
    // 再生の開始・停止で、先読みの優先度など(動作状態)も切り替える。
    updateActivity();
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
    // 停止中の表示コマは操作(goToFrame)で決めたものを正とする。描画側の知らせは遅れて届くことがあり、
    // それで書き換えると、ドラッグ中に今の位置の表示が行ったり来たりして見えるため。
    if (!view_.isPlaying()) {
        invalidateBar();
        return;
    }
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
    wchar_t title[1024];
    std::wstring names = fileNameOf(clip_->path());
    if (compareClip_) {
        names += L" | " + fileNameOf(compareClip_->path());
    }
    std::swprintf(title, 1024, L"%ls - %ls [%d / %d]", names.c_str(), kAppName, current_ + 1, clip_->frameCount());
    SetWindowTextW(hwnd_, title);
}

}  // namespace frameplayer
