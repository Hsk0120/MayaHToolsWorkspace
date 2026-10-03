/**
 * @file PlayerWindow.cpp
 * @brief プレイヤーのメインウィンドウの実装。
 */
#include "app/PlayerWindow.h"

#include "app/SyncLog.h"

#include <commctrl.h>
#include <dwmapi.h>
#include <shobjidl.h>
#include <windowsx.h>
#include <wrl/client.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <iterator>
#include <string>

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
constexpr UINT kEditCommitMessage = WM_APP + 3;  ///< 数字の欄でEnterが押されたときの知らせ。
constexpr UINT kEditCancelMessage = WM_APP + 4;  ///< 数字の欄でEscが押されたときの知らせ。
constexpr UINT kSyncMessage = WM_APP + 5;        ///< 連携の待ち受け口(SyncServer)からの知らせ。
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
constexpr COLORREF kRuler = RGB(32, 32, 32);          ///< タイムスライダーの目盛りとレンジスライダーのバーの地。
constexpr COLORREF kTick = RGB(84, 84, 84);           ///< 細かい目盛り。
constexpr COLORREF kMajorTick = RGB(110, 110, 110);   ///< 数字の付く目盛り。
constexpr COLORREF kRulerText = RGB(197, 197, 197);   ///< 目盛りの数字。
constexpr COLORREF kCurrentColumn = RGB(70, 70, 70);  ///< 現在のフレームの区画。
constexpr COLORREF kLabelBox = RGB(52, 52, 52);       ///< 現在のフレームの番号の箱。
constexpr COLORREF kRangeSelected = RGB(58, 58, 58);  ///< レンジスライダーの再生範囲。
constexpr COLORREF kHandle = RGB(148, 148, 148);      ///< レンジスライダーのつまみ。
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
    loadTimelineSettings();
    editBrush_ = CreateSolidBrush(kControlFace);
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
    wc.style = CS_DBLCLKS;  // レンジスライダーのダブルクリック(全体と直前の範囲の切り替え)を受け取る。
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
    // Mayaなどと連携するための待ち受け口を開く(このPCの中からだけ接続できる)。
    // 同じ番号を他のアプリ(2つ目のFramePlayerなど)が使っていれば、連携なしで動く。
    {
        auto server = std::make_unique<SyncServer>();
        if (server->start(hwnd_, kSyncMessage, syncPort_)) {
            syncServer_ = server.get();
            sync_ = std::move(server);
        }
    }
    // GPUが使えれば、デコード・キャッシュ・描画で同じデバイスを使う(GPUのメモリにあるコマをそのまま描くため)。
    gpu_ = GpuDevice::create();
    if (!view_.create(instance, hwnd_, kViewFrameMessage, gpu_)) {
        DestroyWindow(hwnd_);
        return false;
    }
    view_.setBounds(computeLayout().video);
    view_.setFrameNumberStart(startFrame_);
    DragAcceptFiles(hwnd_, TRUE);
    ShowWindow(hwnd_, showCommand);
    UpdateWindow(hwnd_);
    return true;
}

void PlayerWindow::openClip(const std::wstring& path) {
    view_.stop();
    syncPowerRequest();
    cancelEdit();
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
    // 再生範囲は動画全体から始める。
    playFirst_ = 0;
    playLast_ = clip_->frameCount() - 1;
    savedFirst_ = -1;
    savedLast_ = -1;
    view_.setPlaybackRange(playFirst_, playLast_);
    clip_->setLoopRange(playFirst_, playLast_);
    if (sync_) {
        sync_->playbackRangeChanged(startFrame_ + playFirst_, startFrame_ + playLast_);
    }
    notifyCurrentFrame();
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
    case WM_SYSKEYDOWN:
        // Alt+, / Alt+. : 1コマ戻る/進む(Mayaと同じ)。それ以外のAltの組み合わせはWindowsに任せる。
        if (clip_ && (wParam == VK_OEM_COMMA || wParam == VK_OEM_PERIOD)) {
            stepFrame(wParam == VK_OEM_COMMA ? -1 : 1);
            return 0;
        }
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case WM_LBUTTONDOWN:
        onLeftButtonDown(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        return 0;
    case WM_LBUTTONDBLCLK:
        onDoubleClick(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        return 0;
    case WM_SETCURSOR:
        if (LOWORD(lParam) == HTCLIENT && updateCursor()) {
            return TRUE;
        }
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case WM_COMMAND:
        // 数字の欄から離れたら(他の所を押した・他のアプリへ移ったなど)、入力を確定する。
        if (editControl_ && reinterpret_cast<HWND>(lParam) == editControl_ && HIWORD(wParam) == EN_KILLFOCUS) {
            commitEdit();
        }
        return 0;
    case WM_CTLCOLOREDIT:
        if (editControl_ && reinterpret_cast<HWND>(lParam) == editControl_) {
            HDC editDc = reinterpret_cast<HDC>(wParam);
            SetTextColor(editDc, kText);
            SetBkColor(editDc, kControlFace);
            return reinterpret_cast<LRESULT>(editBrush_);
        }
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case kEditCommitMessage:
        commitEdit();
        return 0;
    case kSyncMessage:
        onSyncMessage(wParam, lParam);
        return 0;
    case kEditCancelMessage:
        cancelEdit();
        return 0;
    case WM_MOUSEMOVE:
        onMouseMove(GET_X_LPARAM(lParam));
        return 0;
    case WM_LBUTTONUP:
        endScrub();
        return 0;
    case WM_CAPTURECHANGED:
        // 他のウィンドウにマウスを取られたときもドラッグを終える(endScrub()の中で外したときは何もしない)。
        if (drag_ != Drag::None) {
            const bool resume = drag_ == Drag::Scrub && resumeAfterScrub_;
            drag_ = Drag::None;
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
        // 連携の待ち受けを先に止める(以降の知らせを受け取らない)。
        syncServer_ = nullptr;
        sync_.reset();
        // 描画スレッドを止めてから動画を手放す(手放すと裏の読み込みスレッドも止まる)。
        view_.shutdown();
        view_.setClip(nullptr);
        syncPowerRequest();
        KillTimer(hwnd_, kResourceTimerId);
        compareClip_.reset();
        clip_.reset();
        audio_.reset();
        cancelEdit();
        releaseFonts();
        if (editBrush_) {
            DeleteObject(editBrush_);
            editBrush_ = nullptr;
        }
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
    const int left = static_cast<int>(client.left);
    const int right = static_cast<int>(client.right);
    const int bottom = static_cast<int>(client.bottom);
    // Mayaと同じく、下から「レンジスライダー」「タイムスライダー」の2段。映像はその上に余白なしで置く。
    const int rangeHeight = scaled(32, dpi);
    const int timeHeight = scaled(40, dpi);
    const int rangeTop = std::max(static_cast<int>(client.top), bottom - rangeHeight);
    const int timeTop = std::max(static_cast<int>(client.top), rangeTop - timeHeight);
    const int margin = scaled(8, dpi);
    const int gap = scaled(6, dpi);
    const int fieldWidth = scaled(64, dpi);
    const int fieldHeight = scaled(22, dpi);

    Layout layout;
    layout.video = {left, static_cast<int>(client.top), right, timeTop};
    layout.bar = {left, timeTop, right, bottom};
    layout.timeRow = {left, timeTop, right, rangeTop};
    layout.rangeRow = {left, rangeTop, right, bottom};

    // タイムスライダーの段: 左から目盛り、現在のフレームの欄、移動・再生のボタン(Mayaと同じ並び)。
    const int buttonSize = scaled(26, dpi);
    const int buttonGap = scaled(2, dpi);
    int x = right - margin - (buttonSize * 5 + buttonGap * 4);
    const int buttonsLeft = x;
    auto placeButton = [&] {
        const int top = timeTop + (timeHeight - buttonSize) / 2;
        const RECT r{x, top, x + buttonSize, top + buttonSize};
        x += buttonSize + buttonGap;
        return r;
    };
    layout.startButton = placeButton();
    layout.prevButton = placeButton();
    layout.button = placeButton();
    layout.nextButton = placeButton();
    layout.endButton = placeButton();
    const int timeFieldTop = timeTop + (timeHeight - fieldHeight) / 2;
    layout.currentField = {buttonsLeft - gap - fieldWidth, timeFieldTop, buttonsLeft - gap, timeFieldTop + fieldHeight};
    layout.ruler = {left + margin, timeTop + scaled(4, dpi),
                    std::max(left + margin + 1, static_cast<int>(layout.currentField.left) - gap), rangeTop - scaled(2, dpi)};

    // レンジスライダーの段: 左から開始フレームの欄、バー、終了フレームの欄、fps、「ファイル」「比較」、音量。
    const int rangeFieldTop = rangeTop + (rangeHeight - fieldHeight) / 2;
    layout.startField = {left + margin, rangeFieldTop, left + margin + fieldWidth, rangeFieldTop + fieldHeight};
    const int volumeWidth = scaled(80, dpi);
    const int volumeHeight = scaled(16, dpi);
    const int volumeTop = rangeTop + (rangeHeight - volumeHeight) / 2;
    layout.volumeSlider = {right - margin - volumeWidth, volumeTop, right - margin, volumeTop + volumeHeight};
    const int speakerSize = scaled(22, dpi);
    const int speakerTop = rangeTop + (rangeHeight - speakerSize) / 2;
    const int speakerRight = static_cast<int>(layout.volumeSlider.left) - gap;
    layout.volumeButton = {speakerRight - speakerSize, speakerTop, speakerRight, speakerTop + speakerSize};
    const int textButtonHeight = scaled(24, dpi);
    const int textButtonTop = rangeTop + (rangeHeight - textButtonHeight) / 2;
    const int compareRight = static_cast<int>(layout.volumeButton.left) - scaled(12, dpi);
    layout.compareButton = {compareRight - scaled(56, dpi), textButtonTop, compareRight, textButtonTop + textButtonHeight};
    const int fileRight = static_cast<int>(layout.compareButton.left) - gap;
    layout.fileButton = {fileRight - scaled(72, dpi), textButtonTop, fileRight, textButtonTop + textButtonHeight};
    const int rateRight = static_cast<int>(layout.fileButton.left) - scaled(12, dpi);
    layout.rateLabel = {rateRight - scaled(56, dpi), rangeTop, rateRight, bottom};
    const int endFieldRight = static_cast<int>(layout.rateLabel.left) - gap;
    layout.endField = {endFieldRight - fieldWidth, rangeFieldTop, endFieldRight, rangeFieldTop + fieldHeight};
    layout.rangeBar = {static_cast<int>(layout.startField.right) + gap, rangeFieldTop,
                       std::max(static_cast<int>(layout.startField.right) + gap + 1,
                                static_cast<int>(layout.endField.left) - gap),
                       rangeFieldTop + fieldHeight};
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
    // 2段は、メディア プレーヤーと同じく1枚の地として塗る。
    fillColor(dc, layout.bar, kSurface);

    // 文字のボタン(「ファイル」「比較」)。比較中の「比較」は色を付けて、押すと比較をやめることを示す。
    HGDIOBJ oldFont = SelectObject(dc, uiFont(9, dpi));
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

    // 移動・再生のボタン(枠なしの記号)。
    const COLORREF ink = clip_ ? kIcon : kDisabled;
    paintTransportIcon(dc, layout.startButton, TransportIcon::Start, ink);
    paintTransportIcon(dc, layout.prevButton, TransportIcon::Previous, ink);
    paintTransportIcon(dc, layout.button, playing ? TransportIcon::Pause : TransportIcon::Play, ink);
    paintTransportIcon(dc, layout.nextButton, TransportIcon::Next, ink);
    paintTransportIcon(dc, layout.endButton, TransportIcon::End, ink);
    paintVolume(dc, layout, dpi);

    // キャッシュの有無は全コマ(1時間60fpsで21万6千)を調べるので、毎回の描画では計算し直さず、
    // 一定間隔(kCacheBarIntervalMs)ごと、または横幅や再生範囲が変わったときだけ計算する。
    if (clip_) {
        static const LONGLONG frequency = ticksPerSecond();
        const LONGLONG now = nowTicks();
        const RECT& ruler = layout.ruler;
        const RECT& rangeBar = layout.rangeBar;
        if (cacheRunsTrack_.left != ruler.left || cacheRunsTrack_.right != ruler.right ||
            rangeCacheRunsBar_.left != rangeBar.left || rangeCacheRunsBar_.right != rangeBar.right ||
            cacheRunsFirst_ != playFirst_ || cacheRunsLast_ != playLast_ ||
            (now - lastCacheBarTicks_) * 1000 / frequency >= kCacheBarIntervalMs) {
            clip_->cachedFlags(cacheFlags_);
            lastCacheBarTicks_ = now;
            cacheRunsTrack_ = ruler;
            rangeCacheRunsBar_ = rangeBar;
            cacheRunsFirst_ = playFirst_;
            cacheRunsLast_ = playLast_;
            buildCacheRuns(cacheFlags_, playFirst_, playLast_, ruler.left, ruler.right - ruler.left, cacheRuns_);
            buildCacheRuns(cacheFlags_, 0, clip_->frameCount() - 1, rangeBar.left, rangeBar.right - rangeBar.left,
                           rangeCacheRuns_);
        }
    }
    paintTimeSlider(dc, layout, dpi);
    paintRangeSlider(dc, layout, dpi);

    // 数字の欄。開始フレームは入力できる(動画の1コマ目の番号を変える)。終了フレームは表示だけ。
    const int count = clip_ ? clip_->frameCount() : 0;
    paintField(dc, layout.currentField, currentSceneFrame(), true, dpi);
    paintField(dc, layout.startField, startFrame_, true, dpi);
    paintField(dc, layout.endField, startFrame_ + std::max(0, count - 1), false, dpi);

    // フレームレート。
    oldFont = SelectObject(dc, uiFont(8, dpi));
    SetTextColor(dc, kSubText);
    wchar_t rateText[32];
    std::swprintf(rateText, 32, L"%.4g fps", playbackRate());
    RECT rateRect = layout.rateLabel;
    DrawTextW(dc, rateText, -1, &rateRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    SelectObject(dc, oldFont);
}

void PlayerWindow::buildCacheRuns(const std::vector<std::uint8_t>& flags, int first, int last, int left, int width,
                                  std::vector<std::pair<int, int>>& runs) {
    // 横幅の各画素に割り当たるコマのうち、1つでもキャッシュにあれば塗る。
    runs.clear();
    const int count = last - first + 1;
    if (count <= 0 || width <= 0 || flags.empty()) {
        return;
    }
    int runStart = -1;
    for (int px = 0; px <= width; ++px) {
        bool cached = false;
        if (px < width) {
            const int f0 = first + static_cast<int>(static_cast<long long>(px) * count / width);
            const int f1 = std::max(f0 + 1, first + static_cast<int>(static_cast<long long>(px + 1) * count / width));
            for (int i = f0; i < f1 && i <= last && !cached; ++i) {
                cached = i >= 0 && i < static_cast<int>(flags.size()) && flags[static_cast<std::size_t>(i)] != 0;
            }
        }
        if (cached && runStart < 0) {
            runStart = left + px;
        } else if (!cached && runStart >= 0) {
            runs.emplace_back(runStart, left + px);
            runStart = -1;
        }
    }
}

void PlayerWindow::paintTimeSlider(HDC dc, const Layout& layout, int dpi) {
    const RECT& r = layout.ruler;
    const int width = r.right - r.left;
    if (width < 2) {
        return;
    }
    fillColor(dc, r, kRuler);
    if (!clip_) {
        return;
    }
    // 再生範囲の各コマに同じ幅の区画を割り当てる(Mayaと同じく、目盛りは区画の左端)。
    const int first = playFirst_;
    const int last = playLast_;
    const int count = last - first + 1;
    auto xOf = [&](int index) {
        return static_cast<int>(r.left) + static_cast<int>(static_cast<long long>(index - first) * width / count);
    };
    const double pixelsPerFrame = static_cast<double>(width) / count;
    const int strip = scaled(3, dpi);  // 下端のキャッシュの帯の高さ。
    const int tickBottom = r.bottom - strip;

    // 現在のフレームの区画(目盛りより先に描き、目盛りが上に重なるようにする)。
    const bool currentInRange = current_ >= first && current_ <= last;
    int currentLeft = 0;
    int currentRight = 0;
    if (currentInRange) {
        currentLeft = xOf(current_);
        currentRight = std::max(currentLeft + scaled(2, dpi), xOf(current_ + 1));
        fillColor(dc, RECT{currentLeft, r.top, currentRight, tickBottom}, kCurrentColumn);
    }

    // 数字の間隔は1・2・5・10・20・50…の中で、数字どうしが重ならない最小のもの。
    HGDIOBJ oldFont = SelectObject(dc, uiFont(8, dpi));
    wchar_t widest[32];
    std::swprintf(widest, 32, L"%d", std::max(std::abs(startFrame_ + first), std::abs(startFrame_ + last)) * 10);
    SIZE labelSize{};
    GetTextExtentPoint32W(dc, widest, static_cast<int>(wcslen(widest)), &labelSize);
    const double minSpacing = labelSize.cx + scaled(8, dpi);
    long long major = 1;
    for (long long base = 1; major * pixelsPerFrame < minSpacing && base < 100000000; base *= 10) {
        for (int multiplier : {1, 2, 5}) {
            major = base * multiplier;
            if (major * pixelsPerFrame >= minSpacing) {
                break;
            }
        }
    }
    // 細かい目盛りは、1コマごとに5ピクセル以上空くなら各コマ、そうでなければ数字の間隔の1/5か1/2。
    const double minTick = scaled(5, dpi);
    long long minor = 0;
    if (pixelsPerFrame >= minTick) {
        minor = 1;
    } else if (major % 5 == 0 && (major / 5) * pixelsPerFrame >= minTick) {
        minor = major / 5;
    } else if (major % 2 == 0 && (major / 2) * pixelsPerFrame >= minTick) {
        minor = major / 2;
    }
    // 目盛りの番号はフレーム番号(開始フレームを足した番号)で揃える。
    const long long sceneFirst = static_cast<long long>(startFrame_) + first;
    const long long sceneLast = static_cast<long long>(startFrame_) + last;
    auto firstMultiple = [&](long long step) {
        const long long q = sceneFirst / step;
        const long long candidate = q * step;
        return candidate < sceneFirst ? candidate + step : candidate;
    };
    if (minor > 0) {
        for (long long frame = firstMultiple(minor); frame <= sceneLast; frame += minor) {
            const int x = xOf(static_cast<int>(frame - startFrame_));
            fillColor(dc, RECT{x, tickBottom - scaled(5, dpi), x + 1, tickBottom}, kTick);
        }
    }
    SetTextColor(dc, kRulerText);
    for (long long frame = firstMultiple(major); frame <= sceneLast; frame += major) {
        const int x = xOf(static_cast<int>(frame - startFrame_));
        fillColor(dc, RECT{x, r.top + scaled(2, dpi), x + 1, tickBottom}, kMajorTick);
        wchar_t text[32];
        std::swprintf(text, 32, L"%lld", frame);
        // 右端で切れてしまう数字は描かない(途中で切れた数字は別の数に見えるため)。
        SIZE textSize{};
        GetTextExtentPoint32W(dc, text, static_cast<int>(wcslen(text)), &textSize);
        if (x + scaled(3, dpi) + textSize.cx <= r.right) {
            RECT textRect{x + scaled(3, dpi), r.top + scaled(1, dpi), r.right, tickBottom};
            DrawTextW(dc, text, -1, &textRect, DT_LEFT | DT_TOP | DT_SINGLELINE);
        }
    }

    // 下端の帯: キャッシュに入っているコマ。
    for (const auto& [runLeft, runRight] : cacheRuns_) {
        fillColor(dc, RECT{runLeft, r.bottom - strip, runRight, r.bottom}, kAccent);
    }

    // 現在のフレームの番号は、区画の右下に箱で出す(右端で入らなければ左側)。
    if (currentInRange) {
        wchar_t text[32];
        std::swprintf(text, 32, L"%d", currentSceneFrame());
        SIZE size{};
        GetTextExtentPoint32W(dc, text, static_cast<int>(wcslen(text)), &size);
        const int boxWidth = size.cx + scaled(8, dpi);
        const int boxHeight = size.cy + scaled(2, dpi);
        int boxLeft = currentRight + 1;
        if (boxLeft + boxWidth > r.right) {
            boxLeft = currentLeft - 1 - boxWidth;
        }
        RECT box{boxLeft, tickBottom - boxHeight, boxLeft + boxWidth, tickBottom};
        fillColor(dc, box, kLabelBox);
        SetTextColor(dc, kText);
        DrawTextW(dc, text, -1, &box, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    }
    SelectObject(dc, oldFont);
}

int PlayerWindow::rangeXOf(const Layout& layout, int index) const {
    const RECT& b = layout.rangeBar;
    const int count = clip_ ? std::max(1, clip_->frameCount()) : 1;
    return static_cast<int>(b.left) + static_cast<int>(static_cast<long long>(index) * (b.right - b.left) / count);
}

void PlayerWindow::paintRangeSlider(HDC dc, const Layout& layout, int dpi) {
    const RECT& b = layout.rangeBar;
    if (b.right - b.left < 2) {
        return;
    }
    fillColor(dc, b, kRuler);
    if (!clip_) {
        return;
    }
    // 動画全体の中の再生範囲を明るく塗り、両端につまみを置く。つまみの内側に範囲の最初と最後の番号を出す。
    const int x0 = rangeXOf(layout, playFirst_);
    const int x1 = std::max(x0 + scaled(2, dpi), rangeXOf(layout, playLast_ + 1));
    const int handle = scaled(6, dpi);
    fillColor(dc, RECT{x0, b.top, x1, b.bottom}, kRangeSelected);
    fillColor(dc, RECT{x0, b.top, x0 + handle, b.bottom}, kHandle);
    fillColor(dc, RECT{std::max(x0, x1 - handle), b.top, x1, b.bottom}, kHandle);

    HGDIOBJ oldFont = SelectObject(dc, uiFont(8, dpi));
    SetTextColor(dc, kRulerText);
    wchar_t firstText[32];
    wchar_t lastText[32];
    std::swprintf(firstText, 32, L"%d", startFrame_ + playFirst_);
    std::swprintf(lastText, 32, L"%d", startFrame_ + playLast_);
    SIZE firstSize{};
    SIZE lastSize{};
    GetTextExtentPoint32W(dc, firstText, static_cast<int>(wcslen(firstText)), &firstSize);
    GetTextExtentPoint32W(dc, lastText, static_cast<int>(wcslen(lastText)), &lastSize);
    const int pad = scaled(4, dpi);
    // 範囲が狭くて両方入らないときは、入る方だけを出す。
    if (x1 - x0 >= 2 * handle + firstSize.cx + lastSize.cx + 3 * pad) {
        RECT firstRect{x0 + handle + pad, b.top, x1, b.bottom};
        DrawTextW(dc, firstText, -1, &firstRect, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
        RECT lastRect{x0, b.top, x1 - handle - pad, b.bottom};
        DrawTextW(dc, lastText, -1, &lastRect, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
    } else if (x1 - x0 >= 2 * handle + firstSize.cx + 2 * pad) {
        RECT firstRect{x0 + handle + pad, b.top, x1, b.bottom};
        DrawTextW(dc, firstText, -1, &firstRect, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
    }
    SelectObject(dc, oldFont);

    // 下端の帯: 動画全体のうちキャッシュに入っているコマ。
    const int strip = scaled(2, dpi);
    for (const auto& [runLeft, runRight] : rangeCacheRuns_) {
        fillColor(dc, RECT{runLeft, b.bottom - strip, runRight, b.bottom}, kAccent);
    }
}

void PlayerWindow::paintField(HDC dc, const RECT& rect, int value, bool editable, int dpi) {
    fillColor(dc, rect, kControlFace);
    HBRUSH border = CreateSolidBrush(kControlBorder);
    FrameRect(dc, &rect, border);
    DeleteObject(border);
    if (!clip_) {
        return;
    }
    HGDIOBJ oldFont = SelectObject(dc, uiFont(9, dpi));
    SetTextColor(dc, editable ? kText : kDisabled);
    wchar_t text[32];
    std::swprintf(text, 32, L"%d", value);
    RECT textRect = rect;
    DrawTextW(dc, text, -1, &textRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
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
    switch (key) {
    case VK_RIGHT:
        if (shift) {
            goToFrame(current + kLargeStep);
        } else {
            stepFrame(1);
        }
        break;
    case VK_LEFT:
        if (shift) {
            goToFrame(current - kLargeStep);
        } else {
            stepFrame(-1);
        }
        break;
    case VK_HOME:
        goToFrame(playFirst_);
        break;
    case VK_END:
        goToFrame(playLast_);
        break;
    case 'I':
        // 再生範囲の最初を今のフレームにする(最後より後なら最後も合わせる)。
        setPlaybackRange(current, std::max(playLast_, current));
        break;
    case 'O':
        // 再生範囲の最後を今のフレームにする(最初より前なら最初も合わせる)。
        setPlaybackRange(std::min(playFirst_, current), current);
        break;
    default:
        break;
    }
}

void PlayerWindow::stepFrame(int delta) {
    // Mayaと同じく、再生範囲の端で1コマ送ると反対の端へ回り込む(範囲の外にいるときは回り込まない)。
    const int current = view_.currentFrame();
    int next = current + delta;
    if (current >= playFirst_ && current <= playLast_) {
        if (next > playLast_) {
            next = playFirst_;
        } else if (next < playFirst_) {
            next = playLast_;
        }
    }
    goToFrame(next);
}

void PlayerWindow::onLeftButtonDown(int x, int y) {
    if (editField_ != EditField::None) {
        commitEdit();  // 入力中に他の所を押したら、入力を確定する。
    }
    const Layout layout = computeLayout();
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const POINT point{x, y};
    // 音量の三角形は小さいので、レンジスライダーの段の高さいっぱいまで当たり判定を広げる。
    RECT volumeHit = layout.volumeSlider;
    volumeHit.top = layout.rangeRow.top;
    volumeHit.bottom = layout.rangeRow.bottom;
    InflateRect(&volumeHit, scaled(4, dpi), 0);
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
        drag_ = Drag::Volume;
        SetCapture(hwnd_);
        setVolume(volumeFromX(x));
        return;
    }
    if (!clip_) {
        return;
    }
    if (PtInRect(&layout.currentField, point)) {
        beginEdit(EditField::Current);
        return;
    }
    if (PtInRect(&layout.startField, point)) {
        beginEdit(EditField::StartFrame);
        return;
    }
    if (PtInRect(&layout.button, point)) {
        togglePlayback();
        return;
    }
    if (PtInRect(&layout.startButton, point)) {
        goToFrame(playFirst_);
        return;
    }
    if (PtInRect(&layout.prevButton, point)) {
        stepFrame(-1);
        return;
    }
    if (PtInRect(&layout.nextButton, point)) {
        stepFrame(1);
        return;
    }
    if (PtInRect(&layout.endButton, point)) {
        goToFrame(playLast_);
        return;
    }
    RECT rulerHit = layout.ruler;
    rulerHit.top = layout.timeRow.top;
    rulerHit.bottom = layout.timeRow.bottom;
    if (PtInRect(&rulerHit, point)) {
        // 目盛りの段のどこを押してもよい。ドラッグ中にウィンドウ外へ出てもマウスの動きを受け取れるよう、
        // マウスを取り込む。再生中に触った場合は、ドラッグ中はそのコマを表示し、離したらその位置から再生を続ける。
        resumeAfterScrub_ = view_.isPlaying();
        drag_ = Drag::Scrub;
        SetCapture(hwnd_);
        goToFrame(frameFromX(x), true);
        return;
    }
    RECT rangeHit = layout.rangeBar;
    rangeHit.top = layout.rangeRow.top;
    rangeHit.bottom = layout.rangeRow.bottom;
    if (PtInRect(&rangeHit, point)) {
        // つまみ(少し広めに判定)なら範囲の端を、範囲の中なら長さを保って範囲を動かす。
        const int x0 = rangeXOf(layout, playFirst_);
        const int x1 = std::max(x0 + scaled(2, dpi), rangeXOf(layout, playLast_ + 1));
        const int handle = scaled(6, dpi) + scaled(3, dpi);
        if (x >= x0 - scaled(3, dpi) && x < x0 + handle && (x - x0) <= (x1 - x)) {
            drag_ = Drag::RangeStart;
        } else if (x <= x1 + scaled(3, dpi) && x > x1 - handle) {
            drag_ = Drag::RangeEnd;
        } else if (x >= x0 && x < x1) {
            drag_ = Drag::RangeMove;
            dragAnchor_ = rangeFrameFromX(x);
            dragFirst_ = playFirst_;
            dragLast_ = playLast_;
        } else {
            return;
        }
        SetCapture(hwnd_);
    }
}

void PlayerWindow::onMouseMove(int x) {
    switch (drag_) {
    case Drag::Volume:
        setVolume(volumeFromX(x));
        break;
    case Drag::Scrub:
        if (clip_) {
            goToFrame(frameFromX(x), true);
        }
        break;
    case Drag::RangeStart:
        if (clip_) {
            setPlaybackRange(std::min(rangeFrameFromX(x), playLast_), playLast_);
        }
        break;
    case Drag::RangeEnd:
        if (clip_) {
            setPlaybackRange(playFirst_, std::max(rangeFrameFromX(x), playFirst_));
        }
        break;
    case Drag::RangeMove:
        if (clip_) {
            // 長さを保ったまま、動画の範囲からはみ出さないように動かす。
            const int length = dragLast_ - dragFirst_;
            const int first = std::clamp(dragFirst_ + rangeFrameFromX(x) - dragAnchor_, 0,
                                         std::max(0, clip_->frameCount() - 1 - length));
            setPlaybackRange(first, first + length);
        }
        break;
    case Drag::None:
        break;
    }
}

void PlayerWindow::onDoubleClick(int x, int y) {
    const Layout layout = computeLayout();
    const POINT point{x, y};
    RECT rangeHit = layout.rangeBar;
    rangeHit.top = layout.rangeRow.top;
    rangeHit.bottom = layout.rangeRow.bottom;
    if (clip_ && PtInRect(&rangeHit, point)) {
        // Mayaと同じく、動画全体と、直前の再生範囲を切り替える。
        const int last = clip_->frameCount() - 1;
        if (playFirst_ == 0 && playLast_ == last) {
            if (savedFirst_ >= 0 && savedLast_ >= savedFirst_ && savedLast_ <= last) {
                setPlaybackRange(savedFirst_, savedLast_);
            }
        } else {
            savedFirst_ = playFirst_;
            savedLast_ = playLast_;
            setPlaybackRange(0, last);
        }
        return;
    }
    // ダブルクリックの2回目も、普通のクリックとして扱う(ボタンの連打で取りこぼさないように)。
    onLeftButtonDown(x, y);
}

bool PlayerWindow::updateCursor() {
    if (!clip_) {
        return false;
    }
    bool sizing = drag_ == Drag::RangeStart || drag_ == Drag::RangeEnd;
    if (drag_ == Drag::None) {
        POINT point;
        GetCursorPos(&point);
        ScreenToClient(hwnd_, &point);
        const Layout layout = computeLayout();
        const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
        if (point.y >= layout.rangeBar.top && point.y < layout.rangeBar.bottom) {
            const int x0 = rangeXOf(layout, playFirst_);
            const int x1 = std::max(x0 + scaled(2, dpi), rangeXOf(layout, playLast_ + 1));
            const int handle = scaled(9, dpi);
            sizing = (point.x >= x0 - scaled(3, dpi) && point.x < x0 + handle) ||
                     (point.x <= x1 + scaled(3, dpi) && point.x > x1 - handle);
        }
    }
    if (sizing) {
        SetCursor(LoadCursorW(nullptr, IDC_SIZEWE));
    }
    return sizing;
}

void PlayerWindow::endScrub() {
    const bool resume = drag_ == Drag::Scrub && resumeAfterScrub_;
    if (drag_ != Drag::None) {
        // ReleaseCapture()はWM_CAPTURECHANGEDをすぐ送ってくるので、先に状態を戻しておく。
        drag_ = Drag::None;
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
    const RECT ruler = computeLayout().ruler;
    const int width = ruler.right - ruler.left;
    const int count = playLast_ - playFirst_ + 1;
    if (count <= 1 || width <= 0) {
        return playFirst_;
    }
    // 目盛りの区画(コマごとに同じ幅)のうち、xを含む区画のコマ。
    const long long offset = static_cast<long long>(x - ruler.left) * count / width;
    return std::clamp(playFirst_ + static_cast<int>(offset), playFirst_, playLast_);
}

int PlayerWindow::rangeFrameFromX(int x) const {
    const RECT bar = computeLayout().rangeBar;
    const int width = bar.right - bar.left;
    const int count = clip_ ? clip_->frameCount() : 0;
    if (count <= 1 || width <= 0) {
        return 0;
    }
    const long long offset = static_cast<long long>(x - bar.left) * count / width;
    return std::clamp(static_cast<int>(offset), 0, count - 1);
}

void PlayerWindow::setPlaybackRange(int first, int last) {
    if (!clip_) {
        return;
    }
    const int maxIndex = clip_->frameCount() - 1;
    first = std::clamp(first, 0, maxIndex);
    last = std::clamp(last, first, maxIndex);
    if (first == playFirst_ && last == playLast_) {
        return;
    }
    playFirst_ = first;
    playLast_ = last;
    view_.setPlaybackRange(first, last);
    clip_->setLoopRange(first, last);
    updateTitle();
    invalidateBar();
    if (sync_ && !applyingRemote_) {
        sync_->playbackRangeChanged(startFrame_ + first, startFrame_ + last);
    }
}

void PlayerWindow::goToSceneFrame(int frame) {
    if (clip_) {
        goToFrame(frame - startFrame_);
    }
}

void PlayerWindow::setPlaybackRangeScene(int first, int last) {
    setPlaybackRange(first - startFrame_, last - startFrame_);
}

void PlayerWindow::setPlaying(bool playing) {
    if (clip_ && playing != view_.isPlaying()) {
        togglePlayback();
    }
}

void PlayerWindow::notifyCurrentFrame() {
    const int frame = currentSceneFrame();
    if (applyingRemote_) {
        notifiedFrame_ = frame;  // 相手から受け取った位置なので送り返さない(相手は既にこの位置にいる)。
        return;
    }
    if (sync_ && frame != notifiedFrame_) {
        notifiedFrame_ = frame;
        sync_->currentFrameChanged(frame);
    }
}

void PlayerWindow::notifyPlayState() {
    const bool playing = view_.isPlaying();
    if (applyingRemote_) {
        notifiedPlaying_ = playing;
        return;
    }
    if (sync_ && playing != notifiedPlaying_) {
        notifiedPlaying_ = playing;
        sync_->playStateChanged(playing);
    }
}

void PlayerWindow::beginEdit(EditField field) {
    if (!clip_) {
        return;
    }
    if (editField_ != EditField::None) {
        commitEdit();
    }
    const Layout layout = computeLayout();
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const RECT& r = field == EditField::Current ? layout.currentField : layout.startField;
    const int value = field == EditField::Current ? currentSceneFrame() : startFrame_;
    // 欄の上に、同じ大きさの入力用の子ウィンドウを重ねる。文字の高さに合わせて上下の中央に置く。
    HFONT font = uiFont(9, dpi);
    const int textHeight = scaled(16, dpi);
    const int top = r.top + (r.bottom - r.top - textHeight) / 2;
    editField_ = field;
    editControl_ = CreateWindowExW(0, L"EDIT", std::to_wstring(value).c_str(),
                                   WS_CHILD | WS_VISIBLE | ES_CENTER | ES_AUTOHSCROLL, r.left + 2, top,
                                   r.right - r.left - 4, textHeight, hwnd_, nullptr, instance_, nullptr);
    if (!editControl_) {
        editField_ = EditField::None;
        return;
    }
    SendMessageW(editControl_, WM_SETFONT, reinterpret_cast<WPARAM>(font), FALSE);
    // EnterとEscを受け取るため、入力用の子ウィンドウのメッセージを横取りする(Windows標準のサブクラス化)。
    SetWindowSubclass(editControl_, &PlayerWindow::editProc, 1, reinterpret_cast<DWORD_PTR>(this));
    SendMessageW(editControl_, EM_SETSEL, 0, -1);
    SetFocus(editControl_);
}

void PlayerWindow::commitEdit() {
    if (editField_ == EditField::None || !editControl_) {
        return;
    }
    wchar_t text[64] = {};
    GetWindowTextW(editControl_, text, 64);
    const EditField field = editField_;
    // 先に状態を戻してから子ウィンドウを壊す(壊すときの「入力欄から離れた」知らせで、もう一度確定しないように)。
    editField_ = EditField::None;
    HWND edit = editControl_;
    editControl_ = nullptr;
    SetFocus(hwnd_);
    DestroyWindow(edit);

    wchar_t* end = nullptr;
    const long value = std::wcstol(text, &end, 10);
    while (end && *end == L' ') {
        ++end;
    }
    if (end == text || (end && *end != L'\0')) {
        invalidateBar();
        return;  // 数字として読めない。
    }
    if (field == EditField::Current) {
        goToSceneFrame(static_cast<int>(value));
    } else {
        startFrame_ = static_cast<int>(std::clamp<long>(value, -1000000, 100000000));
        saveTimelineSettings();
        view_.setFrameNumberStart(startFrame_);
        updateTitle();
        if (sync_) {
            sync_->playbackRangeChanged(startFrame_ + playFirst_, startFrame_ + playLast_);
            notifyCurrentFrame();
        }
    }
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::cancelEdit() {
    if (editField_ == EditField::None || !editControl_) {
        return;
    }
    editField_ = EditField::None;
    HWND edit = editControl_;
    editControl_ = nullptr;
    SetFocus(hwnd_);
    DestroyWindow(edit);
    invalidateBar();
}

LRESULT CALLBACK PlayerWindow::editProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam, UINT_PTR id,
                                        DWORD_PTR data) {
    auto* self = reinterpret_cast<PlayerWindow*>(data);
    switch (message) {
    case WM_KEYDOWN:
        // EnterとEscは、子ウィンドウの処理中に自分を壊さないよう、親へPostMessageで知らせて後で処理する。
        if (wParam == VK_RETURN) {
            PostMessageW(self->hwnd_, kEditCommitMessage, 0, 0);
            return 0;
        }
        if (wParam == VK_ESCAPE) {
            PostMessageW(self->hwnd_, kEditCancelMessage, 0, 0);
            return 0;
        }
        break;
    case WM_CHAR:
        if (wParam == L'\r' || wParam == 0x1B) {
            return 0;  // 1行の入力欄にEnter・Escを渡すと警告音が鳴るので渡さない。
        }
        break;
    case WM_NCDESTROY:
        RemoveWindowSubclass(hwnd, &PlayerWindow::editProc, id);
        break;
    default:
        break;
    }
    return DefSubclassProc(hwnd, message, wParam, lParam);
}

void PlayerWindow::onSyncMessage(WPARAM event, LPARAM lParam) {
    switch (event) {
    case SyncServer::kLine: {
        std::unique_ptr<std::string> line(reinterpret_cast<std::string*>(lParam));
        applySyncCommand(*line);
        break;
    }
    case SyncServer::kConnected:
        // つながったら挨拶と再生状態だけを知らせる。フレームと再生範囲は相手(Maya)側を正とし、相手から届く。
        // ここで自分のフレームや範囲も送ると、相手が送ってくる状態と行き違いになり、相手を古い状態で上書きしてしまう。
        sendSyncState();
        updateTitle();
        break;
    case SyncServer::kDisconnected:
        updateTitle();
        break;
    default:
        break;
    }
}

void PlayerWindow::applySyncCommand(const std::string& line) {
    // 1行の命令: frame <番号> / range <最初> <最後> / play / stop / hello <名前>
    char command[16] = {};
    int first = 0;
    int second = 0;
    const int fields =
        sscanf_s(line.c_str(), "%15s %d %d", command, static_cast<unsigned>(sizeof(command)), &first, &second);
    if (fields < 1) {
        return;
    }
    const std::string name = command;
    syncLog("apply %s", line.c_str());
    applyingRemote_ = true;
    if (name == "frame" && fields >= 2) {
        if (clip_ && first != currentSceneFrame()) {
            goToSceneFrame(first);
        }
    } else if (name == "range" && fields >= 3) {
        setPlaybackRangeScene(std::min(first, second), std::max(first, second));
    } else if (name == "play") {
        setPlaying(true);
    } else if (name == "stop") {
        setPlaying(false);
    }
    applyingRemote_ = false;
}

void PlayerWindow::sendSyncState() {
    if (!syncServer_) {
        return;
    }
    syncServer_->sendLine("hello FramePlayer 1");
    syncServer_->playStateChanged(view_.isPlaying());
    notifiedPlaying_ = view_.isPlaying();
    notifiedFrame_ = 0x7FFFFFFF;  // 次にフレームが変わったら必ず知らせる。
}

void PlayerWindow::loadTimelineSettings() {
    DWORD value = 0;
    DWORD size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"StartFrame", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
        ERROR_SUCCESS) {
        startFrame_ = static_cast<int>(value);  // 負の番号もそのまま(DWORDの値を符号付きとして読む)。
    }
    size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"SyncPort", RRF_RT_REG_DWORD, nullptr, &value, &size) ==
            ERROR_SUCCESS &&
        value > 0 && value < 65536) {
        syncPort_ = static_cast<unsigned short>(value);
    }
}

void PlayerWindow::saveTimelineSettings() const {
    const DWORD value = static_cast<DWORD>(startFrame_);
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, L"StartFrame", REG_DWORD, &value, sizeof(value));
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
    notifyCurrentFrame();
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
    notifyPlayState();
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
        notifyCurrentFrame();
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
    std::swprintf(title, 1024, L"%ls - %ls [%d / %d-%d]%ls", names.c_str(), kAppName, currentSceneFrame(), startFrame_,
                  startFrame_ + clip_->frameCount() - 1,
                  (syncServer_ && syncServer_->connected()) ? L" - 連携中" : L"");
    SetWindowTextW(hwnd_, title);
}

}  // namespace frameplayer
