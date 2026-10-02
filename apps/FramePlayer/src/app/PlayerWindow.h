/**
 * @file PlayerWindow.h
 * @brief プレイヤーのメインウィンドウ(Win32)。
 */
#pragma once

#include <windows.h>
#include <shellapi.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "app/VideoView.h"
#include "core/AudioPlayer.h"
#include "core/Clip.h"
#include "core/GpuDevice.h"

namespace frameplayer {

/**
 * @brief 動画の表示領域(VideoView)と、再生ボタン・タイムスライダー・コマ番号を持つウィンドウ。
 * @note 映像の描画と再生の時間管理はVideoViewの描画スレッドが行う。このウィンドウ(UIスレッド)は
 *       キーとマウスの操作をVideoViewへの指示に変え、下部の操作部をGDIで描く。
 *       操作部の描画が遅れても映像の再生には影響しない。
 */
class PlayerWindow {
public:
    PlayerWindow() = default;

    PlayerWindow(const PlayerWindow&) = delete;
    PlayerWindow& operator=(const PlayerWindow&) = delete;

    /**
     * @brief ウィンドウを作成して表示する。
     * @param instance アプリのインスタンスハンドル。
     * @param showCommand ShowWindowに渡す表示方法。
     * @return 作成できた場合true。
     */
    bool create(HINSTANCE instance, int showCommand);

    /**
     * @brief 比較用の2本目の動画を開き、右に並べて表示する。失敗時はメッセージボックスで知らせる。
     * @param path 動画ファイルのパス。
     * @note 1本目を開いていなければ、1本目として開く。キャッシュの上限は2本で半分ずつにする。
     */
    void openCompare(const std::wstring& path);

    /** @brief 比較をやめ、1本目だけを表示する。1本目のキャッシュの上限を元に戻す。 */
    void closeCompare();

    /**
     * @brief 動画を開いて表示する。失敗時はメッセージボックスで知らせる。
     * @param path 動画ファイルのパス。
     * @note 目次を作って先頭のコマを読むまで戻らない。残りは裏で先読みする。
     */
    void openClip(const std::wstring& path);

private:
    /** @brief 移動・再生ボタンの記号。 */
    enum class TransportIcon { Start, Previous, Play, Pause, Next, End };

    /**
     * @brief ウィンドウ内の各部品の位置(クライアント座標)。
     * @note Keyframe Proと同じく、映像の下にタイムラインの段、その下に操作パネルの段を置く。
     */
    struct Layout {
        RECT video{};          ///< 映像の表示領域(VideoViewの子ウィンドウを置く)。
        RECT bar{};            ///< 下部(タイムラインと操作パネル)全体。
        RECT timeline{};       ///< タイムラインの段(押すとその位置へ移動。ドラッグも可)。
        RECT track{};          ///< タイムラインの細いバー(コマを割り当てる横幅)。
        RECT totalLabel{};     ///< 全体のコマ数の文字。
        RECT rateLabel{};      ///< フレームレートなどの文字。
        RECT panel{};          ///< 操作パネルの段。
        RECT fileButton{};     ///< 「ファイル」ボタン(押すとファイルのメニューを出す)。
        RECT compareButton{};  ///< 「比較」ボタン(2本目の動画を選ぶ。比較中に押すと比較をやめる)。
        RECT startButton{};    ///< 先頭へ移動するボタン。
        RECT prevButton{};     ///< 1コマ戻るボタン。
        RECT button{};         ///< 再生/停止ボタン。
        RECT nextButton{};     ///< 1コマ進むボタン。
        RECT endButton{};      ///< 末尾へ移動するボタン。
        RECT volumeButton{};   ///< スピーカーのボタン(押すと消音を切り替える)。
        RECT volumeSlider{};   ///< 音量の三角形(クリック判定には上下に広げた範囲を使う)。
    };

    /**
     * @brief Windowsから届くメッセージを、対応するPlayerWindowへ振り分ける。
     * @param hwnd 対象ウィンドウ。
     * @param message メッセージの種類。
     * @param wParam メッセージごとの値。
     * @param lParam メッセージごとの値。
     * @return メッセージごとの処理結果。
     * @note WM_NCCREATEで受け取ったthisをウィンドウに保存し、以降はそれを使う。
     */
    static LRESULT CALLBACK windowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam);

    /**
     * @brief メッセージを処理する。
     * @param message メッセージの種類。
     * @param wParam メッセージごとの値。
     * @param lParam メッセージごとの値。
     * @return メッセージごとの処理結果。
     */
    LRESULT handleMessage(UINT message, WPARAM wParam, LPARAM lParam);

    /**
     * @brief 現在のウィンドウの大きさとDPIから各部品の位置を求める。
     * @return 各部品の位置。
     */
    Layout computeLayout() const;

    /** @brief 操作部と余白を描く。映像の領域は子ウィンドウ(VideoView)が描く。 */
    void paint();

    /**
     * @brief 移動・再生ボタンの記号を描く。
     * @param dc 描画先。
     * @param box ボタンの範囲(記号はその中央に描く)。
     * @param icon 記号の種類。
     * @param ink 記号の色。
     */
    void paintTransportIcon(HDC dc, const RECT& box, TransportIcon icon, COLORREF ink);

    /**
     * @brief 操作パネル・タイムライン・コマ番号を描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     */
    void paintControls(HDC dc, const Layout& layout, int dpi);

    /** @brief 操作部だけを描き直すよう要求する(映像の領域は描き直さない)。 */
    void invalidateBar();

    /**
     * @brief キー入力でコマを移動する。再生中なら停止してから移動する(Spaceは再生/停止の切り替え)。
     * @param key 押された仮想キーコード。
     */
    void onKeyDown(WPARAM key);

    /**
     * @brief マウスの左ボタンが押されたときの処理。再生ボタンかスライダー上なら対応する操作を行う。
     * @param x クライアント座標のx。
     * @param y クライアント座標のy。
     */
    void onLeftButtonDown(int x, int y);

    /**
     * @brief スライダーをドラッグ中なら、マウス位置のコマへ移動する。
     * @param x クライアント座標のx。
     */
    void onMouseMove(int x);

    /**
     * @brief スライダー(タイム・音量)のドラッグを終える。マウスの取り込み(SetCapture)も解除する。
     * @note 再生中にタイムスライダーを触った場合は、離した位置から再生を続ける。
     */
    void endScrub();

    /** @brief 停止中なら、表示中のコマから再生を始める(スライダーのドラッグ後に再生を続けるため)。 */
    void resumePlayback();

    /**
     * @brief スピーカーのボタンと音量スライダーを描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     */
    void paintVolume(HDC dc, const Layout& layout, int dpi);

    /**
     * @brief 音量を変える。消音中なら消音も解除する。設定は保存して次回の起動でも使う。
     * @param volume 0.0〜1.0。範囲外は端に丸める。
     */
    void setVolume(float volume);

    /** @brief 消音を切り替える。設定は保存して次回の起動でも使う。 */
    void toggleMute();

    /**
     * @brief 音量スライダー上のx座標に対応する音量を返す。
     * @param x クライアント座標のx。
     * @return 0.0〜1.0。
     */
    float volumeFromX(int x) const;

    /** @brief 音量と消音の設定をレジストリ(HKCU\Software\FramePlayer)から読む。無ければ既定値のまま。 */
    void loadAudioSettings();

    /** @brief 音量と消音の設定をレジストリへ保存する。 */
    void saveAudioSettings() const;

    /**
     * @brief ドロップされたファイルを開く。
     * @param drop ドロップ情報。処理後に解放する。
     * @note 2つ以上なら1つ目を1本目、2つ目を2本目(比較)として開く。1つの場合、1本目を開いている状態で
     *       映像の右半分へ落とすと2本目、それ以外は1本目として開く。
     */
    void onDropFiles(HDROP drop);

    /**
     * @brief 「ファイル」ボタンの上にファイルのメニューを出し、選ばれた項目を実行する。
     * @note メニューは選ぶか閉じるまで戻らない(Windows標準のメニュー)。
     */
    void showFileMenu();

    /**
     * @brief 開いた動画を「最近使ったファイル」の先頭に加え、保存する。
     * @param path 動画ファイルのパス。
     */
    void addRecentFile(const std::wstring& path);

    /** @brief 「最近使ったファイル」をレジストリから読む。 */
    void loadRecentFiles();

    /** @brief 「最近使ったファイル」をレジストリへ保存する。 */
    void saveRecentFiles() const;

    /**
     * @brief Windowsのファイル選択画面で動画を選ばせる。
     * @param title 画面の題名。
     * @return 選ばれたファイルのパス。取り消されたら空。
     */
    std::wstring chooseVideoFile(const wchar_t* title);

    /**
     * @brief 比較中の2本目のずらしを変える。
     * @param delta 変える量(コマ数)。
     */
    void shiftCompare(int delta);

    /**
     * @brief 動画のキャッシュの上限を返す。比較中は2本で半分ずつにする。
     * @param onGpu GPUのメモリにキャッシュする動画か。
     * @param comparing 比較中か。
     * @return バイト数。
     */
    std::size_t cacheLimitFor(bool onGpu, bool comparing) const;

    /**
     * @brief スライダー上のx座標に対応するコマ番号を返す。
     * @param x クライアント座標のx。
     * @return 0始まりのコマ番号。範囲外は端に丸める。
     */
    int frameFromX(int x) const;

    /**
     * @brief 再生を止め、指定したコマを表示する。範囲外は端に丸める。
     * @param index 0始まりのコマ番号。
     * @param scrubbing タイムラインのドラッグ中か。trueなら前後に同じだけ先読みさせる。
     */
    void goToFrame(int index, bool scrubbing = false);

    /** @brief 再生中なら停止し、そうでなければ現在のコマから再生する。 */
    void togglePlayback();

    /** @brief 再生中だけ、画面の省電力(表示の消灯)とスリープを止めるようWindowsへ伝える。 */
    void syncPowerRequest();

    /**
     * @brief 再生に使うフレームレートを返す。
     * @return ファイルに記録されたフレームレート。不明なら24。
     */
    double playbackRate() const;

    /** @brief VideoViewが表示するコマを変えたときの処理。コマ番号の表示を更新する。 */
    void onViewFrameChanged();

    /**
     * @brief 裏の読み込みでコマがキャッシュに入ったときの処理。キャッシュ表示を間引いて描き直す。
     * @note 先読み中は1秒に数百回届くため、描き直しは一定間隔に抑える。
     */
    void onFrameReady();

    /** @brief タイトルバーにファイル名と現在のコマを表示する。 */
    void updateTitle();

    /**
     * @brief キャッシュに持つコマ数の上限(設定の秒数分)を返す。
     * @param clip 対象の動画。
     * @return コマ数。
     */
    int frameLimitFor(const Clip& clip) const;

    /**
     * @brief 今の設定・GPUのメモリの予算・主メモリの残りから、両方の動画のキャッシュの上限を決め直す。
     * @note 変わったときだけ動画へ伝える。2秒ごとのタイマーと、動画を開いた・閉じたときに呼ぶ。
     */
    void applyCacheLimits();

    /**
     * @brief 再生・前面かどうか・最小化・放置時間から動作状態(Clip::Activity)を決め、動画へ伝える。
     * @note 休止(Dormant)に入るときは、使っていない主メモリもWindowsへ返す。
     */
    void updateActivity();

    /** @brief 2秒ごとのタイマー。キャッシュの上限の見直しと、休止に入るかの判定を行う。 */
    void onResourceTimer();

    /** @brief キャッシュの上限の設定(CacheMB・CacheSeconds)をレジストリから読む。無ければ既定値のまま。 */
    void loadCacheSettings();

    /**
     * @brief 操作部の描画に使う書体を返す。作った書体は覚えておき、次の描画でも使う。
     * @param points 文字の大きさ(ポイント)。
     * @param dpi ウィンドウのDPI。変わったら作り直す。
     * @return 書体。このクラスが持つので、呼び出し元は解放しない。
     */
    HFONT uiFont(int points, int dpi);

    /** @brief 覚えている書体をすべて解放する。 */
    void releaseFonts();

    HWND hwnd_ = nullptr;
    HINSTANCE instance_ = nullptr;
    // 破棄の順序: clip_(裏の読み込みスレッド)を先に止めてからview_を破棄し、最後にgpu_を破棄する
    // (宣言の逆順に破棄される)。
    std::shared_ptr<GpuDevice> gpu_;  ///< デコード・キャッシュ・描画で共有するGPUデバイス。無ければnullptr。
    VideoView view_;              ///< 映像の表示と再生の時間管理。
    std::shared_ptr<Clip> clip_;  ///< 表示中の動画。描画スレッドとも共有する。未読み込みならnullptr。
    std::shared_ptr<Clip> compareClip_;  ///< 比較用の2本目の動画。比較していなければnullptr。
    std::vector<std::wstring> recentFiles_;  ///< 最近使ったファイル(新しい順)。
    std::shared_ptr<AudioPlayer> audio_;  ///< 表示中の動画の音声。描画スレッドとも共有する。
    float volume_ = 0.8f;   ///< 音量(0.0〜1.0)。
    bool muted_ = false;    ///< 消音中か。
    std::size_t cacheMegabytes_ = 1024;  ///< キャッシュの上限(MB)。設定CacheMB。
    int cacheSeconds_ = 30;              ///< キャッシュに持つ長さの上限(秒)。設定CacheSeconds。
    std::size_t appliedLimit_[2] = {};   ///< 動画へ最後に伝えたバイト数の上限(0=1本目、1=2本目)。
    int appliedFrames_[2] = {};          ///< 動画へ最後に伝えたコマ数の上限。
    bool memoryLow_ = false;             ///< Windowsが主メモリの不足を知らせているか。
    HANDLE lowMemory_ = nullptr;         ///< 主メモリの不足を知る仕組み(CreateMemoryResourceNotification)。
    bool appActive_ = true;              ///< このアプリが前面にあるか。
    bool minimized_ = false;             ///< 最小化されているか。
    bool dormant_ = false;               ///< 休止中か。
    ULONGLONG inactiveSinceMs_ = 0;      ///< 前面でなくなった時刻(GetTickCount64)。
    ULONGLONG minimizedSinceMs_ = 0;     ///< 最小化された時刻(GetTickCount64)。
    Clip::Activity activity_ = Clip::Activity::Interactive;  ///< 動画へ最後に伝えた動作状態。
    std::vector<std::pair<int, HFONT>> fonts_;  ///< 作った書体(大きさ, 書体)。
    int fontsDpi_ = 0;                          ///< fonts_を作ったときのDPI。
    int current_ = 0;             ///< 操作部に表示しているコマ番号(VideoViewの表示に追従する)。

    std::atomic<bool> frameReadyPending_{false};  ///< 裏の読み込みからの知らせが未処理か(送りすぎ防止)。
    std::vector<std::uint8_t> cacheFlags_;        ///< キャッシュ表示用の作業領域(描画のたびに確保しないため)。
    LONGLONG lastCacheBarTicks_ = 0;              ///< キャッシュ表示を最後に計算した時刻。
    std::vector<std::pair<int, int>> cacheRuns_;  ///< キャッシュ表示で塗る横の範囲[左, 右)の一覧。
    RECT cacheRunsTrack_{};                       ///< cacheRuns_を計算したときのスライダーの範囲。

    bool scrubbing_ = false;      ///< タイムスライダーをドラッグ中か。
    bool volumeDragging_ = false; ///< 音量スライダーをドラッグ中か。
    bool resumeAfterScrub_ = false;  ///< タイムスライダーを離したら再生を続けるか(触ったときに再生中だった)。
    bool keepDisplayOn_ = false;  ///< 画面の消灯を止めるようWindowsへ伝えているか。
};

}  // namespace frameplayer
