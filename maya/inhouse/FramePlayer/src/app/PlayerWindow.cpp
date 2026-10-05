/**
 * @file PlayerWindow.cpp
 * @brief プレイヤーのメインウィンドウの実装。
 */
#include "app/PlayerWindow.h"

#include "core/Util.h"

#include "app/Resource.h"
#include "app/Settings.h"
#include "core/TraceLog.h"
#include "app/Ui.h"

#include <commctrl.h>
#include <shobjidl.h>
#include <windowsx.h>
#include <wrl/client.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <initializer_list>
#include <iterator>
#include <string>

namespace frameplayer {

namespace {

constexpr wchar_t kClassName[] = L"FramePlayerWindow";
constexpr wchar_t kAppName[] = L"FramePlayer";
constexpr int kCacheMaxWidth = 1280;                       ///< キャッシュする画像の最大幅。
constexpr std::size_t kMinCacheBytes = std::size_t{64} << 20;     ///< 上限を下げるときの下限(64MB)。
constexpr std::size_t kLowMemoryCacheBytes = std::size_t{256} << 20;  ///< 主メモリが足りないときの上限(256MB)。
constexpr int kThumbnailWidth = 320;                                ///< キーフレームの縮小画像の幅。
constexpr std::size_t kThumbnailBytes = std::size_t{160} << 20;    ///< 縮小画像の合計の上限(1本あたり160MB)。
constexpr UINT_PTR kResourceTimerId = 1;          ///< キャッシュの上限の見直しと休止の判定に使うタイマー。
constexpr UINT kResourceTimerMs = 2000;           ///< そのタイマーの間隔(ミリ秒)。
constexpr ULONGLONG kDormantAfterMinimizedMs = 30 * 1000;    ///< 最小化してから休止に入るまで(30秒)。
constexpr ULONGLONG kDormantAfterInactiveMs = 5 * 60 * 1000;  ///< 背面になってから休止に入るまで(5分)。

/// ファイルのメニューの項目の番号。
enum MenuCommand : UINT {
    kMenuOpen = 1,
    kMenuOpenCompare,
    kMenuCloseCompare,
    kMenuClearRecent,
    kMenuAutoPlay,
    kMenuExit,
    kMenuTogglePlayback,  ///< 右クリックのメニュー: 再生/停止。
    kMenuFullscreen,      ///< 右クリックのメニュー: フルスクリーンの切り替え。
    kMenuColorInfo,       ///< 右クリックのメニュー: 色の情報の表示の切り替え。
    /// 右クリックのメニュー: 色の解釈の手動の指定。番号 = kMenuColorFirst + 動画(0/1)×100 + 項目×10 + (値+1)。
    /// 項目は0=行列、1=範囲、2=色域、3=伝達関数、4=手動の指定をすべて解除。値が-1(0番)なら自動。
    kMenuColorFirst = 1000,
    kMenuColorLast = 1199,
    kMenuRecentFirst = 100,  ///< 最近使ったファイルの1つ目(以降、順に番号を振る)。
};

}  // namespace

bool PlayerWindow::create(HINSTANCE instance, int showCommand) {
    instance_ = instance;
    settings_.load();
    videoStartFrame_ = settings_.startFrame;
    setImageSequenceFrameRate(settings_.sequenceFrameRate);
    editBrush_ = CreateSolidBrush(ui::kControlFace);
    // 主メモリが足りなくなるとWindowsが合図するので、タイマーで確かめてキャッシュを減らす。
    lowMemory_ = CreateMemoryResourceNotification(LowMemoryResourceNotification);
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = &PlayerWindow::windowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    // アプリのアイコン(resources/icon のSVGから作った .ico をexeに埋め込んである)。大きい方はタスクバーと
    // Alt+Tab、小さい方はタイトルバーに使われる。画面の拡大率に合う大きさを選んで読む。
    LoadIconMetric(instance, MAKEINTRESOURCEW(IDI_APP_ICON), LIM_LARGE, &wc.hIcon);
    LoadIconMetric(instance, MAKEINTRESOURCEW(IDI_APP_ICON), LIM_SMALL, &wc.hIconSm);
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
    ui::applyDarkTitleBar(hwnd_);
    SetTimer(hwnd_, kResourceTimerId, kResourceTimerMs, nullptr);
    // Mayaとの連携の待ち受け口は、通常は開かない(「Maya連携」ボタンか、起動時の --sync で開く)。
    // GPUが使えれば、デコード・キャッシュ・描画で同じデバイスを使う(GPUのメモリにあるコマをそのまま描くため)。
    gpu_ = GpuDevice::create();
    if (!view_.create(instance, hwnd_, kViewFrameMessage, gpu_)) {
        DestroyWindow(hwnd_);
        return false;
    }
    view_.setBounds(computeLayout().video);
    view_.setFrameNumberStart(settings_.startFrame);
    view_.setShowColorInfo(settings_.showColorInfo);
    createTooltips();
    DragAcceptFiles(hwnd_, TRUE);
    ShowWindow(hwnd_, showCommand);
    UpdateWindow(hwnd_);
    return true;
}

void PlayerWindow::openClip(const std::wstring& path) {
    const LONGLONG openStart = nowTicks();
    view_.stop();
    syncPowerRequest();
    cancelEdit();
    resumeAfterScrub_ = false;  // 別の動画を開くときは、ドラッグ前の再生を引き継がない。
    endScrub();
    std::shared_ptr<Clip> clip = loadClip(path, compareClip_ != nullptr);
    if (!clip) {
        updateTitle();
        return;
    }
    const LONGLONG clipLoaded = nowTicks();
    // 音声は無くても動画は再生できる(音声なしとして扱う)。画像には音声が無いので開かない。
    auto audio = std::make_shared<AudioPlayer>();
    if (!isImageFile(path)) {
        audio->open(path);
    }
    traceLog("open clip %.1f ms audio %.1f ms", (clipLoaded - openStart) * 1000.0 / ticksPerSecond(),
            (nowTicks() - clipLoaded) * 1000.0 / ticksPerSecond());
    audio->setVolume(settings_.volume);
    audio->setMuted(settings_.muted);

    clip_ = std::move(clip);
    audio_ = std::move(audio);
    settings_.addRecentFile(path);
    // 連番画像は、最初のファイルの番号をタイムラインの開始にする(保存はしない)。動画は設定の値に戻す。
    const std::optional<int> firstNumber = clip_->firstFrameNumber();
    settings_.startFrame = firstNumber ? *firstNumber : videoStartFrame_;
    view_.setFrameNumberStart(settings_.startFrame);
    current_ = 0;
    cacheRuns_.clear();
    cacheRunsTrack_ = RECT{};
    prepareClip(*clip_, 0, kThumbnailBytes);
    view_.setClip(clip_, audio_);
    clip_->setPlayhead(0, Clip::Direction::Forward, false);
    // 全体範囲・再生範囲は、動画のある所(動画の開始から最後のコマまで)から始める。
    animFirst_ = 0;
    animLast_ = clip_->frameCount() - 1;
    playFirst_ = animFirst_;
    playLast_ = animLast_;
    hasSavedRange_ = false;
    view_.setPlaybackRange(playFirst_, playLast_);
    clip_->setLoopRange(playFirst_, playLast_);
    if (sync_) {
        sync_->playbackRangeChanged(settings_.startFrame + playFirst_, settings_.startFrame + playLast_);
    }
    notifyCurrentFrame();
    if (compareClip_) {
        // 比較中に1本目を差し替えた場合は、比較を続ける(キャッシュは半分ずつ)。
        view_.setCompareClip(compareClip_);
    }
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
    autoPlay();
}

void PlayerWindow::autoPlay() {
    // Mayaとの連携モードでは自動再生しない(タイムラインはMaya側が動かす。勝手に再生するとMayaも再生させてしまう)。
    if (settings_.autoPlay && !syncServer_) {
        resumePlayback();
    }
}

std::shared_ptr<Clip> PlayerWindow::loadClip(const std::wstring& path, bool comparing) {
    auto clip = std::make_shared<Clip>();
    std::wstring error;
    HCURSOR previousCursor = SetCursor(LoadCursorW(nullptr, IDC_WAIT));
    // 開くときは目次を作って先頭のコマを読むだけで、残りは裏のスレッドが先読みする。
    // 裏のスレッドからの知らせは、描画スレッドを起こす合図と、UIスレッドへのPostMessageにする。
    // UIへの知らせは、処理前のものが残っていれば送らない。
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
        MessageBoxW(hwnd_, (path + L"\n\n" + error).c_str(), kAppName, MB_OK | MB_ICONWARNING);
        return nullptr;
    }
    return clip;
}

void PlayerWindow::prepareClip(Clip& clip, int slot, std::size_t thumbnailBytes) {
    // 描画スレッドへ渡す前に、上限・動作状態・縮小画像を決めておく(preview()は描画スレッドから呼ばれる)。
    appliedLimit_[slot] = 0;
    appliedFrames_[slot] = 0;
    applyCacheLimits();
    clip.setActivity(activity_);
    clip.startThumbnails(kThumbnailWidth, thumbnailBytes);
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
    case WM_DISPLAYCHANGE:
    case WM_SETTINGCHANGE:
    case WM_EXITSIZEMOVE:
        // 画面の構成・HDRの有無・SDRの白の明るさの変更、別のモニターへの移動。映像の出し方を調べ直す。
        view_.displayChanged();
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case WM_SIZE:
        view_.setBounds(computeLayout().video);
        updateTooltipRects();
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
        // Mayaと同じAltの組み合わせ。それ以外はWindowsに任せる。
        //   Alt+, / Alt+. : 1コマ戻る/進む
        //   Alt+V         : 再生/停止(押しっぱなしで切り替わり続けないよう、キーリピートは無視する)
        //   Alt+Shift+V   : 再生範囲の最初へ
        if (clip_ && (wParam == VK_OEM_COMMA || wParam == VK_OEM_PERIOD)) {
            stepFrame(wParam == VK_OEM_COMMA ? -1 : 1);
            return 0;
        }
        if (clip_ && wParam == 'V') {
            if (GetKeyState(VK_SHIFT) < 0) {
                goToFrame(playFirst_);
            } else if (!(lParam & (1 << 30))) {
                togglePlayback();
            }
            return 0;
        }
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case WM_SYSCHAR:
        // 上で処理したAltの組み合わせは、Windowsに渡すとメニューのアクセスキーを探して見つからず、警告音が鳴る。
        if (clip_ && (wParam == L',' || wParam == L'.' || wParam == L'v' || wParam == L'V')) {
            return 0;
        }
        return DefWindowProcW(hwnd_, message, wParam, lParam);
    case WM_LBUTTONDOWN:
        if (!paneDragging()) {  // 中ボタンでドラッグ中の左クリックは無視する。
            onLeftButtonDown(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        }
        return 0;
    case WM_LBUTTONDBLCLK:
        // Kを押しながら素早く押し直したときの2回目も、普通に押したのと同じにドラッグを始める。
        if (!paneDragging() && !beginKeyScrub(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam))) {
            onDoubleClick(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        }
        return 0;
    case WM_MBUTTONDOWN:
    case WM_MBUTTONDBLCLK:  // 素早く2回押したときの2回目も、普通に押したのと同じに扱う。
        onMiddleButtonDown(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        return 0;
    case WM_MBUTTONUP:
        if (paneDragging()) {
            endScrub();
        }
        return 0;
    case WM_CONTEXTMENU:
        // 右クリック(またはアプリケーションキー・Shift+F10)でメニューを出す。
        if (drag_ == Drag::None) {
            showContextMenu(POINT{GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam)});
        }
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
            SetTextColor(editDc, ui::kText);
            SetBkColor(editDc, ui::kControlFace);
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
        onMouseMove(GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam));
        return 0;
    case WM_MOUSELEAVE:
        trackingLeave_ = false;
        setHover(Part::None);
        return 0;
    case WM_NOTIFY: {
        // ツールチップが出す文字を尋ねてきたら、部品の説明を返す(状態で変わる説明があるため、その都度返す)。
        auto* header = reinterpret_cast<NMHDR*>(lParam);
        if (tooltip_ && header->hwndFrom == tooltip_ && header->code == TTN_GETDISPINFOW) {
            auto* info = reinterpret_cast<NMTTDISPINFOW*>(lParam);
            info->lpszText = const_cast<wchar_t*>(tooltipText(static_cast<Part>(info->hdr.idFrom)));
        }
        return 0;
    }
    case WM_LBUTTONUP:
        if (!paneDragging()) {
            endScrub();
        }
        return 0;
    case WM_CAPTURECHANGED:
        // 他のウィンドウにマウスを取られたときもドラッグを終える(endScrub()の中で外したときは何もしない)。
        if (drag_ != Drag::None) {
            const bool resume = resumeAfterScrub_;
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
        fonts_.clear();
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

void PlayerWindow::resumePlayback() {
    if (clip_ && !view_.isPlaying()) {
        view_.play(playbackRate());
        syncPowerRequest();
        invalidateBar();
    }
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
    AppendMenuW(menu, MF_STRING, kMenuOpen, L"Open...\tCtrl+O");
    AppendMenuW(menu, MF_STRING | (clip_ ? 0 : MF_GRAYED), kMenuOpenCompare, L"Open for Comparison...\tCtrl+Shift+O");
    AppendMenuW(menu, MF_STRING | (compareClip_ ? 0 : MF_GRAYED), kMenuCloseCompare, L"Close Comparison");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    // 最近使ったファイル。左にファイル名、右(タブの後ろ)にフォルダーを出す。
    for (std::size_t i = 0; i < settings_.recentFiles.size(); ++i) {
        const std::wstring& path = settings_.recentFiles[i];
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
    if (!settings_.recentFiles.empty()) {
        AppendMenuW(recent, MF_SEPARATOR, 0, nullptr);
    }
    AppendMenuW(recent, MF_STRING | (settings_.recentFiles.empty() ? MF_GRAYED : 0), kMenuClearRecent, L"Clear List");
    AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(recent), L"Recent Files");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (settings_.autoPlay ? MF_CHECKED : 0), kMenuAutoPlay, L"Play Automatically on Open");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, kMenuExit, L"Exit");

    // 操作部は画面の下にあるので、ボタンの上端から上向きに開く。選ぶか閉じるまで戻らない。
    const RECT b = computeLayout().fileButton;
    POINT corner{b.left, b.top};
    ClientToScreen(hwnd_, &corner);
    const UINT command = static_cast<UINT>(TrackPopupMenu(
        menu, TPM_RETURNCMD | TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_NONOTIFY, corner.x, corner.y, 0, hwnd_, nullptr));
    DestroyMenu(menu);  // 中の「最近使ったファイル」も一緒に破棄される。

    switch (command) {
    case kMenuOpen: {
        const std::wstring path = chooseVideoFile(L"Select a Video or Image Sequence");
        if (!path.empty()) {
            openClip(path);
        }
        break;
    }
    case kMenuOpenCompare: {
        const std::wstring path = chooseVideoFile(L"Select a Video to Compare");
        if (!path.empty()) {
            openCompare(path);
        }
        break;
    }
    case kMenuCloseCompare:
        closeCompare();
        break;
    case kMenuClearRecent:
        settings_.recentFiles.clear();
        settings_.saveRecentFiles();
        break;
    case kMenuAutoPlay:
        settings_.autoPlay = !settings_.autoPlay;
        settings_.saveAutoPlay();
        break;
    case kMenuExit:
        PostMessageW(hwnd_, WM_CLOSE, 0, 0);
        break;
    default:
        if (command >= kMenuRecentFirst && command < kMenuRecentFirst + settings_.recentFiles.size()) {
            const std::wstring path = settings_.recentFiles[command - kMenuRecentFirst];  // openClipで一覧が変わるので写す。
            openClip(path);
        }
        break;
    }
}

HMENU PlayerWindow::createColorMenu(const Clip& clip, int clipIndex) const {
    const ColorInfo detected = clip.color();
    const ColorOverride current = clip.colorOverride();
    HMENU menu = CreatePopupMenu();
    // 1つの項目の選択肢を並べる。先頭は「自動」(動画の指定・推定のまま。今の値を添える)。
    auto addField = [&](int field, const wchar_t* title, int selected, const wchar_t* automatic,
                        std::initializer_list<std::pair<int, const wchar_t*>> choices) {
        HMENU sub = CreatePopupMenu();
        const UINT base = kMenuColorFirst + static_cast<UINT>(clipIndex * 100 + field * 10);
        const std::wstring autoLabel = std::wstring(L"Auto (") + automatic + L")";
        AppendMenuW(sub, MF_STRING | (selected < 0 ? MF_CHECKED : 0), base, autoLabel.c_str());
        AppendMenuW(sub, MF_SEPARATOR, 0, nullptr);
        for (const auto& [value, label] : choices) {
            AppendMenuW(sub, MF_STRING | (selected == value ? MF_CHECKED : 0), base + static_cast<UINT>(value + 1), label);
        }
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(sub), title);
    };
    auto value = [](auto v) { return static_cast<int>(v); };
    addField(0, L"YUV Matrix", current.matrix, colorName(detected.matrix),
             {{value(ColorMatrix::Bt601), colorName(ColorMatrix::Bt601)},
              {value(ColorMatrix::Bt709), colorName(ColorMatrix::Bt709)},
              {value(ColorMatrix::Bt2020), colorName(ColorMatrix::Bt2020)}});
    addField(1, L"Range", current.range, colorName(detected.range),
             {{value(ColorRange::Limited), colorName(ColorRange::Limited)},
              {value(ColorRange::Full), colorName(ColorRange::Full)}});
    addField(2, L"Primaries", current.primaries, colorName(detected.primaries),
             {{value(ColorPrimaries::Bt709), colorName(ColorPrimaries::Bt709)},
              {value(ColorPrimaries::Bt601_525), colorName(ColorPrimaries::Bt601_525)},
              {value(ColorPrimaries::Bt601_625), colorName(ColorPrimaries::Bt601_625)},
              {value(ColorPrimaries::Bt2020), colorName(ColorPrimaries::Bt2020)},
              {value(ColorPrimaries::DisplayP3), colorName(ColorPrimaries::DisplayP3)},
              {value(ColorPrimaries::DciP3), colorName(ColorPrimaries::DciP3)}});
    addField(3, L"Transfer Function", current.transfer, colorName(detected.transfer),
             {{value(TransferFunction::Sdr), colorName(TransferFunction::Sdr)},
              {value(TransferFunction::Pq), colorName(TransferFunction::Pq)},
              {value(TransferFunction::Hlg), colorName(TransferFunction::Hlg)},
              {value(TransferFunction::Linear), colorName(TransferFunction::Linear)}});
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (current.any() ? 0 : MF_GRAYED),
                kMenuColorFirst + static_cast<UINT>(clipIndex * 100 + 40), L"Reset All Overrides");
    return menu;
}

void PlayerWindow::applyColorCommand(UINT command) {
    const UINT offset = command - kMenuColorFirst;
    const int clipIndex = static_cast<int>(offset / 100);
    const int field = static_cast<int>(offset % 100 / 10);
    const int value = static_cast<int>(offset % 10) - 1;
    Clip* clip = clipIndex == 0 ? clip_.get() : compareClip_.get();
    if (!clip) {
        return;
    }
    ColorOverride override = clip->colorOverride();
    switch (field) {
    case 0:
        override.matrix = value;
        break;
    case 1:
        override.range = value;
        break;
    case 2:
        override.primaries = value;
        break;
    case 3:
        override.transfer = value;
        break;
    default:
        override = ColorOverride{};
        break;
    }
    clip->setColorOverride(override);
    view_.redraw();
}

void PlayerWindow::showContextMenu(POINT screenPoint) {
    if (screenPoint.x == -1 && screenPoint.y == -1) {
        GetCursorPos(&screenPoint);
    }
    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING | (clip_ ? 0 : MF_GRAYED), kMenuTogglePlayback,
                view_.isPlaying() ? L"Stop\tSpace" : L"Play\tSpace");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (fullscreen_ ? MF_CHECKED : 0), kMenuFullscreen, L"Full Screen\tCtrl+F");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (settings_.showColorInfo ? MF_CHECKED : 0), kMenuColorInfo, L"Show Color Info");
    // 色の解釈の手動の指定(動画の指定が誤っているときに直す)。比較中は動画ごとに分ける。
    if (clip_ && compareClip_) {
        const std::wstring first = L"Color Interpretation: 1st (" + fileNameOf(clip_->path()) + L")";
        const std::wstring second = L"Color Interpretation: 2nd (" + fileNameOf(compareClip_->path()) + L")";
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(createColorMenu(*clip_, 0)), first.c_str());
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(createColorMenu(*compareClip_, 1)), second.c_str());
    } else if (clip_) {
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(createColorMenu(*clip_, 0)), L"Color Interpretation");
    }
    const UINT command = static_cast<UINT>(TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                                          screenPoint.x, screenPoint.y, 0, hwnd_, nullptr));
    DestroyMenu(menu);  // 中の項目のメニューも一緒に破棄される。
    if (command >= kMenuColorFirst && command <= kMenuColorLast) {
        applyColorCommand(command);
        return;
    }
    switch (command) {
    case kMenuTogglePlayback:
        if (clip_) {
            togglePlayback();
        }
        break;
    case kMenuFullscreen:
        toggleFullscreen();
        break;
    case kMenuColorInfo:
        settings_.showColorInfo = !settings_.showColorInfo;
        settings_.saveShowColorInfo();
        view_.setShowColorInfo(settings_.showColorInfo);
        break;
    default:
        break;
    }
}

void PlayerWindow::toggleFullscreen() {
    const LONG_PTR style = GetWindowLongPtrW(hwnd_, GWL_STYLE);
    if (!fullscreen_) {
        // 今のウィンドウがあるモニター全体(タスクバーも覆う)に広げる。戻せるよう、今の位置と最大化の状態を覚えておく。
        MONITORINFO monitor{sizeof(MONITORINFO)};
        if (!GetWindowPlacement(hwnd_, &windowedPlacement_) ||
            !GetMonitorInfoW(MonitorFromWindow(hwnd_, MONITOR_DEFAULTTOPRIMARY), &monitor)) {
            return;
        }
        fullscreen_ = true;
        SetWindowLongPtrW(hwnd_, GWL_STYLE, style & ~static_cast<LONG_PTR>(WS_OVERLAPPEDWINDOW));
        const RECT& r = monitor.rcMonitor;
        SetWindowPos(hwnd_, HWND_TOP, r.left, r.top, r.right - r.left, r.bottom - r.top,
                     SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
    } else {
        // 枠を戻してから、覚えておいた位置・大きさ(最大化していたなら最大化)に戻す。
        fullscreen_ = false;
        SetWindowLongPtrW(hwnd_, GWL_STYLE, style | WS_OVERLAPPEDWINDOW);
        SetWindowPlacement(hwnd_, &windowedPlacement_);
        SetWindowPos(hwnd_, nullptr, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
    }
}

std::wstring PlayerWindow::chooseVideoFile(const wchar_t* title) {
    // Windows標準のファイル選択画面(COMの部品)。UIスレッドはCOM初期化済み(main.cpp)。
    Microsoft::WRL::ComPtr<IFileOpenDialog> dialog;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog)))) {
        return std::wstring();
    }
    const COMDLG_FILTERSPEC types[] = {
        {L"Videos and Image Sequences", L"*.mp4;*.mov;*.m4v;*.avi;*.wmv;*.mkv;*.webm;*.mts;*.m2ts;*.ts;*.mpg;*.mpeg;*.vob;*.3gp;"
                         L"*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.gif;*.webp;*.heic;*.heif;*.avif;*.jxl;*.jxr;*.exr"},
        {L"Video Files", L"*.mp4;*.mov;*.m4v;*.avi;*.wmv;*.mkv;*.webm;*.mts;*.m2ts;*.ts;*.mpg;*.mpeg;*.vob;*.3gp"},
        {L"Image Sequences", L"*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.gif;*.webp;*.heic;*.heif;*.avif;*.jxl;*.jxr;*.exr"},
        {L"All Files", L"*.*"},
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
    // MayaやUnreal Engineと同時に使っても邪魔にならないよう、設定(CacheMB)・GPUのメモリの予算の1/4・
    // 主メモリの残りのうち最も小さいものにする。
    std::size_t limit = settings_.cacheMegabytes << 20;
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
    return std::max(1, static_cast<int>(std::lround(settings_.cacheSeconds * rate)));
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

void PlayerWindow::openCompare(const std::wstring& path) {
    if (!clip_) {
        openClip(path);
        return;
    }
    view_.stop();
    syncPowerRequest();
    // 2本目は最初から半分の上限で開く(1本目もapplyCacheLimits()で半分にする)。音声は開かない(比較中は鳴らさない)。
    std::shared_ptr<Clip> clip = loadClip(path, true);
    if (!clip) {
        return;
    }
    compareClip_ = std::move(clip);
    settings_.addRecentFile(path);
    prepareClip(*compareClip_, 1, kThumbnailBytes / 2);  // 縮小画像は2本で半分ずつにする。
    view_.setCompareOffset(0);
    view_.setCompareClip(compareClip_);
    view_.showFrame(view_.currentFrame(), Clip::Direction::Forward);
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
    autoPlay();
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

int PlayerWindow::clampIndex(long long index) const {
    const long long start = settings_.startFrame;
    return static_cast<int>(std::clamp(index, -kMaxSyncFrame - start, kMaxSyncFrame - start));
}

void PlayerWindow::setPlaybackRange(int first, int last) {
    // Mayaと同じく、全体範囲の外を再生範囲にしたら全体範囲を広げる。
    first = clampIndex(first);
    last = clampIndex(std::max(first, last));
    setTimeRange(std::min(animFirst_, first), std::max(animLast_, last), first, last);
}

void PlayerWindow::setTimeRange(int animFirst, int animLast, int playFirst, int playLast) {
    if (!clip_) {
        return;
    }
    animFirst = clampIndex(animFirst);
    animLast = clampIndex(std::max(animFirst, animLast));
    playFirst = std::clamp(playFirst, animFirst, animLast);
    playLast = std::clamp(playLast, playFirst, animLast);
    const bool playChanged = playFirst != playFirst_ || playLast != playLast_;
    if (!playChanged && animFirst == animFirst_ && animLast == animLast_) {
        return;
    }
    animFirst_ = animFirst;
    animLast_ = animLast;
    playFirst_ = playFirst;
    playLast_ = playLast;
    if (playChanged) {
        view_.setPlaybackRange(playFirst, playLast);
        // 先読みのループは、再生範囲のうち動画のある部分だけ(動画の外にはコマが無い)。
        const int maxIndex = clip_->frameCount() - 1;
        clip_->setLoopRange(std::clamp(playFirst, 0, maxIndex), std::clamp(playLast, 0, maxIndex));
    }
    updateTitle();
    invalidateBar();
    if (playChanged && sync_ && !applyingRemote_) {
        sync_->playbackRangeChanged(settings_.startFrame + playFirst, settings_.startFrame + playLast);
    }
}

void PlayerWindow::setClipStart(int frame) {
    frame = std::clamp(frame, -1000000, 100000000);
    const int delta = frame - settings_.startFrame;
    if (delta == 0) {
        return;
    }
    settings_.startFrame = frame;
    if (!clip_ || !clip_->firstFrameNumber()) {
        // 動画の開始は保存する。連番画像の開始(最初のファイルの番号)は、開いている間だけ変える。
        videoStartFrame_ = frame;
        settings_.saveStartFrame();
    }
    view_.setFrameNumberStart(frame);
    if (clip_) {
        // コマ番号は動画の1コマ目からの数なので、動画を後ろへ動かした分だけ引くと、フレーム番号は変わらない。
        // 連携先へ知らせる必要もない(フレーム番号の再生範囲・現在のフレームは同じまま)。
        animFirst_ = clampIndex(static_cast<long long>(animFirst_) - delta);
        animLast_ = clampIndex(static_cast<long long>(animLast_) - delta);
        playFirst_ = clampIndex(static_cast<long long>(playFirst_) - delta);
        playLast_ = clampIndex(static_cast<long long>(playLast_) - delta);
        hasSavedRange_ = false;
        view_.setPlaybackRange(playFirst_, playLast_);
        const int maxIndex = clip_->frameCount() - 1;
        clip_->setLoopRange(std::clamp(playFirst_, 0, maxIndex), std::clamp(playLast_, 0, maxIndex));
        goToFrame(static_cast<int>(static_cast<long long>(current_) - delta));
    }
    updateTitle();
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::goToSceneFrame(int frame) {
    if (clip_) {
        goToFrame(clampIndex(static_cast<long long>(frame) - settings_.startFrame));
    }
}

void PlayerWindow::setPlaybackRangeScene(int first, int last) {
    setPlaybackRange(clampIndex(static_cast<long long>(first) - settings_.startFrame),
                     clampIndex(static_cast<long long>(last) - settings_.startFrame));
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
        invalidateBar();  // 「Maya連携」ボタンの表示(連携待ち→連携中)を変える。
        break;
    case SyncServer::kDisconnected:
        updateTitle();
        invalidateBar();
        break;
    default:
        break;
    }
}

void PlayerWindow::setSyncEnabled(bool enabled) {
    if (enabled == (syncServer_ != nullptr)) {
        return;
    }
    if (enabled) {
        // 連携モードにしたときだけ、このPCの中からだけ接続できる待ち受け口を開く(相手は鍵で確かめる)。
        auto server = std::make_unique<SyncServer>();
        if (!server->start(hwnd_, kSyncMessage, settings_.syncPort)) {
            wchar_t message[512];
            std::swprintf(message, 512,
                          L"Cannot start Maya sync.\n\n"
                          L"Port %u is in use by another application (such as another FramePlayer), or the sync key could not be prepared.",
                          static_cast<unsigned>(settings_.syncPort));
            MessageBoxW(hwnd_, message, kAppName, MB_OK | MB_ICONWARNING);
            return;
        }
        syncServer_ = server.get();
        sync_ = std::move(server);
    } else {
        // 通常モードに戻したら、接続を切って待ち受け口も閉じる。
        syncServer_ = nullptr;
        sync_.reset();
    }
    notifiedFrame_ = 0x7FFFFFFF;
    notifiedPlaying_ = false;
    updateTitle();
    invalidateBar();
}

void PlayerWindow::applySyncCommand(const std::string& line) {
    // 1行の命令: frame <番号> / range <最初> <最後> / play / stop / hello <名前>
    // 決まった命令と、決まった数の整数だけを受け付ける。それ以外(余分な語・範囲外の数・数でない文字)は無視する。
    std::vector<std::string> words;
    for (std::size_t start = 0; start < line.size() && words.size() <= 3;) {
        const std::size_t end = line.find(' ', start);
        if (end != start) {
            words.push_back(line.substr(start, end == std::string::npos ? std::string::npos : end - start));
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    auto toFrame = [](const std::string& text, int& value) {
        // フレーム番号は±1億まで(int・コマ番号の計算であふれないように)。
        if (text.empty() || text.size() > 12) {
            return false;
        }
        char* end = nullptr;
        const long long parsed = std::strtoll(text.c_str(), &end, 10);
        if (!end || *end != '\0' || parsed < -kMaxSyncFrame || parsed > kMaxSyncFrame) {
            return false;
        }
        value = static_cast<int>(parsed);
        return true;
    };
    if (words.empty()) {
        return;
    }
    const std::string& name = words[0];
    int first = 0;
    int second = 0;
    const bool isFrame = name == "frame" && words.size() == 2 && toFrame(words[1], first);
    const bool isRange = name == "range" && words.size() == 3 && toFrame(words[1], first) && toFrame(words[2], second);
    const bool isPlay = (name == "play" || name == "stop") && words.size() == 1;
    if (!isFrame && !isRange && !isPlay) {
        return;  // helloや知らない命令は何もしない。
    }
    traceLog("apply %s", line.c_str());
    applyingRemote_ = true;
    if (isFrame) {
        if (clip_ && first != currentSceneFrame()) {
            goToSceneFrame(first);
        }
    } else if (isRange) {
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
    syncServer_->sendLine("hello FramePlayer 2");
    syncServer_->playStateChanged(view_.isPlaying());
    notifiedPlaying_ = view_.isPlaying();
    notifiedFrame_ = 0x7FFFFFFF;  // 次にフレームが変わったら必ず知らせる。
}

void PlayerWindow::goToFrame(int index, bool scrubbing, std::optional<int> compareOffset) {
    const int clamped = clampIndex(index);  // 動画の外も表示できる(「範囲外」と出す)。
    const bool wasPlaying = view_.isPlaying();
    const int shown = view_.currentFrame();
    if (clamped == shown && !wasPlaying) {
        if (compareOffset && *compareOffset != view_.compareOffset()) {
            view_.setCompareOffset(*compareOffset);
        }
        return;
    }
    // 移動した向きに先読みさせる(←で戻り続けるときは前のコマを先に読む)。
    // ドラッグ中は向きが細かく入れ替わるので、前後に同じだけ先読みさせる(先読みの範囲が行ったり来たりしないように)。
    const auto direction = scrubbing ? Clip::Direction::Both
                           : clamped < shown ? Clip::Direction::Backward
                                             : Clip::Direction::Forward;
    view_.showFrame(clamped, direction, compareOffset);
    syncPowerRequest();
    current_ = clamped;
    // ドラッグ中のタイトルバーの書き換えは間引く(離したときにendScrub()で最新にする)。
    if (!scrubbing || (nowTicks() - lastTitleTicks_) * 1000 / ticksPerSecond() >= kPlayingTitleIntervalMs) {
        updateTitle();
    }
    invalidateTimeRow();  // コマの移動で変わるのは上段だけ(下段のレンジスライダーは現在のフレームを表示しない)。
    notifyCurrentFrame();
}

void PlayerWindow::togglePlayback() {
    if (view_.isPlaying()) {
        view_.stop();
        current_ = view_.currentFrame();
        updateTitle();  // 再生中は間引いていたので、止めた位置にする。
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
    // 操作部はgoToFrame()で既に描き直しているので、ここでは何もしない。
    if (!view_.isPlaying()) {
        return;
    }
    const int shown = view_.currentFrame();
    if (shown == current_) {
        return;
    }
    current_ = shown;
    // タイトルバーの書き換えは1回約0.2msかかるので、再生中は1秒に4回までにする(止めたときに最新にする)。
    if ((nowTicks() - lastTitleTicks_) * 1000 / ticksPerSecond() >= kPlayingTitleIntervalMs) {
        updateTitle();
    }
    notifyCurrentFrame();
    invalidateTimeRow();  // 再生中にコマが進んで変わるのは上段だけ(キャッシュ表示はonFrameReady()が描き直す)。
}

void PlayerWindow::onFrameReady() {
    frameReadyPending_ = false;
    if (!clip_) {
        return;
    }
    // キャッシュ表示の描き直しは間引く(映像の描き直しは描画スレッドが自分で判断する)。
    if ((nowTicks() - lastCacheBarTicks_) * 1000 / ticksPerSecond() >= kCacheBarIntervalMs) {
        invalidateBar();
    }
}

void PlayerWindow::setSequenceFrameRate(double rate) {
    settings_.sequenceFrameRate = rate;
    settings_.saveSequenceFrameRate();
    setImageSequenceFrameRate(rate);
    if (!clip_ || !clip_->firstFrameNumber()) {
        return;
    }
    // コマの時刻はフレームレートから決まるので、開き直して目次を作り直す。表示中のフレームは保つ。
    const int frame = currentSceneFrame();
    const std::wstring path = clip_->path();
    const bool playing = view_.isPlaying();
    openClip(path);
    goToSceneFrame(frame);
    if (playing) {
        resumePlayback();
    }
}

void PlayerWindow::updateTitle() {
    const LONGLONG titleStart = nowTicks();
    lastTitleTicks_ = titleStart;
    struct TitleLog {
        LONGLONG start;
        ~TitleLog() { traceLog("title %lld us", (nowTicks() - start) * 1000000 / ticksPerSecond()); }
    } titleLog{titleStart};
    if (!clip_) {
        SetWindowTextW(hwnd_, kAppName);
        return;
    }
    wchar_t title[1024];
    std::wstring names = fileNameOf(clip_->path());
    if (compareClip_) {
        names += L" | " + fileNameOf(compareClip_->path());
    }
    // [現在のフレーム / 再生範囲]
    std::swprintf(title, 1024, L"%ls - %ls [%d / %d-%d]%ls", names.c_str(), kAppName, currentSceneFrame(),
                  settings_.startFrame + playFirst_, settings_.startFrame + playLast_,
                  (syncServer_ && syncServer_->connected()) ? L" - Synced" : L"");
    SetWindowTextW(hwnd_, title);
}

}  // namespace frameplayer
