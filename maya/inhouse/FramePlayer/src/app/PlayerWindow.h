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
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "app/Settings.h"
#include "app/SyncServer.h"
#include "app/TimeSync.h"
#include "app/Ui.h"
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

    // ---- タイムスライダーの外部からの操作(Mayaとの連携などの窓口) ----
    // フレーム番号はタイムスライダーに表示している番号(Mayaと同じく、動画の長さに縛られない)。
    // 動画はタイムラインの「動画の開始」の番号に置かれ、動画の外のフレームでは「範囲外」と表示する。UIスレッドから呼ぶ。

    /**
     * @brief 現在のフレーム番号を返す。
     * @return フレーム番号。
     */
    int currentSceneFrame() const { return current_ + settings_.startFrame; }

    /**
     * @brief 再生を止め、指定したフレームを表示する。動画の外なら「範囲外」と表示する。
     * @param frame フレーム番号。
     */
    void goToSceneFrame(int frame);

    /**
     * @brief 再生範囲を設定する。全体範囲の外にかかるときは、Mayaと同じく全体範囲を広げる。
     * @param first 範囲の最初のフレーム番号。
     * @param last 範囲の最後のフレーム番号。
     */
    void setPlaybackRangeScene(int first, int last);

    /**
     * @brief 再生を始める、または止める。
     * @param playing trueなら再生、falseなら停止。
     */
    void setPlaying(bool playing);

    /**
     * @brief Mayaとの連携モード(待ち受け口を開いて接続を待つ)を切り替える。
     * @param enabled trueなら連携モードにする。falseなら接続を切り、待ち受け口も閉じる(通常モード)。
     * @note 通常モードではポートを開かない。開けなかった場合はメッセージボックスで知らせ、通常モードのまま。
     */
    void setSyncEnabled(bool enabled);

    /**
     * @brief 連携モードかを返す。
     * @return 連携モード(待ち受け口を開いている)ならtrue。
     */
    bool syncEnabled() const { return syncServer_ != nullptr; }

    /**
     * @brief タイムスライダーの変化を知らせる先を設定する。
     * @param sync 知らせる先。nullptrなら知らせない。
     */
    void setTimeSync(std::unique_ptr<TimeSync> sync) { sync_ = std::move(sync); }

private:
    // ---- 定数(PlayerWindow.cppとPlayerWindowControls.cppで共有する) ----
    static constexpr int kLargeStep = 10;  ///< Shift併用時に移動するコマ数。
    static constexpr double kDefaultRate = 24.0;  ///< フレームレートが不明な動画の再生速度。
    static constexpr UINT kViewFrameMessage = WM_APP + 1;  ///< VideoViewが表示するコマを変えたときの知らせ。
    static constexpr UINT kFrameReadyMessage = WM_APP + 2;  ///< 裏の読み込みでコマがキャッシュに入ったときの知らせ。
    static constexpr UINT kEditCommitMessage = WM_APP + 3;  ///< 数字の欄でEnterが押されたときの知らせ。
    static constexpr UINT kEditCancelMessage = WM_APP + 4;  ///< 数字の欄でEscが押されたときの知らせ。
    static constexpr UINT kSyncMessage = WM_APP + 5;  ///< 連携の待ち受け口(SyncServer)からの知らせ。
    static constexpr LONGLONG kCacheBarIntervalMs = 200;  ///< キャッシュ表示を計算し直す最短間隔(ミリ秒)。
    static constexpr float kVolumeStep = 0.05f;  ///< ↑↓キーで変える音量の幅。
    static constexpr int kCompareLargeShift = 10;  ///< Shift+[ ]で変える2本目のオフセットの幅。
    static constexpr int kPaneDragPixelsPerFrame = 8;  ///< 映像の上の中ボタンドラッグで1コマ動かす距離(96DPIでのピクセル)。
    static constexpr LONGLONG kPlayingTitleIntervalMs = 250;  ///< 再生中にタイトルバーを書き換える最短間隔(ミリ秒)。
    static constexpr int kCacheStripHeight = 3;  ///< 目盛りの下端のキャッシュの帯の高さ(96DPIでのピクセル)。
    static constexpr long long kMaxSyncFrame = 100000000;  ///< 連携で受け付けるフレーム番号の絶対値の上限。

    /** @brief 目盛りの作り置きを作ったときの条件。どれかが変わったら作り直す。 */
    struct RulerKey {
        int width = 0;
        int height = 0;
        int first = -1;
        int last = -1;
        int startFrame = 0;
        int dpi = 0;
        int clipFrames = 0;  ///< 動画のコマ数(動画の外を暗く塗る範囲が変わるため)。
        /**
         * @brief 全ての条件が同じかを返す。
         * @param other 比べる条件。
         * @return 同じならtrue。
         */
        bool operator==(const RulerKey& other) const {
            return width == other.width && height == other.height && first == other.first && last == other.last &&
                   startFrame == other.startFrame && dpi == other.dpi && clipFrames == other.clipFrames;
        }
    };

    /** @brief マウスでドラッグしている部品。 */
    enum class Drag {
        None,
        Scrub,       ///< タイムスライダー(現在のフレーム)。
        Volume,      ///< 音量スライダー。
        RangeStart,  ///< レンジスライダーの左のつまみ(再生範囲の最初)。
        RangeEnd,    ///< レンジスライダーの右のつまみ(再生範囲の最後)。
        RangeMove,   ///< レンジスライダーの範囲(長さを保って移動)。
        PaneMain,    ///< 1本目(左)の映像の上の中ボタン。1本目だけを動かす(2本目の表示は動かさない)。
        PaneCompare, ///< 2本目(右)の映像の上の中ボタン。2本目のオフセットを変える。
        KeyScrub,    ///< Kを押しながら映像の上を左ドラッグ(Mayaの仮想タイムスライダー)。現在のフレームを動かす。
    };

    /**
     * @brief 操作部の部品(マウスが乗っている部品の判定・ホバーの表示・ツールチップに使う)。
     * @note ツールチップの識別番号にも使うので、Noneは0にしておく。
     */
    enum class Part : UINT_PTR {
        None = 0,
        Ruler,
        CurrentField,
        StartButton,
        PrevButton,
        PlayButton,
        NextButton,
        EndButton,
        AnimStartField,
        PlayStartField,
        RangeBar,
        PlayEndField,
        AnimEndField,
        ClipStartField,
        SyncButton,
        FileButton,
        CompareButton,
        VolumeButton,
        VolumeSlider,
        Count,  ///< 部品の数(繰り返し用)。
    };

    /** @brief 数字を入力できる欄。 */
    enum class EditField {
        None,
        Current,    ///< 現在のフレーム。
        AnimStart,  ///< 全体範囲の最初。
        PlayStart,  ///< 再生範囲の最初。
        PlayEnd,    ///< 再生範囲の最後。
        AnimEnd,    ///< 全体範囲の最後。
        ClipStart,  ///< 動画の開始(動画の1コマ目を置くフレーム番号)。
    };

    /**
     * @brief ウィンドウ内の各部品の位置(クライアント座標)。
     * @note Mayaと同じく、映像の下にタイムスライダーの段、その下にレンジスライダーの段を置く。
     *       タイムスライダーは再生範囲だけを目盛りで表示し、レンジスライダーは全体範囲の中の再生範囲を表す。
     */
    struct Layout {
        RECT video{};          ///< 映像の表示領域(VideoViewの子ウィンドウを置く)。
        RECT bar{};            ///< 下部(2段)全体。
        RECT timeRow{};        ///< タイムスライダーの段。
        RECT ruler{};          ///< 目盛り(再生範囲のフレームを割り当てる横幅。押すとそのフレームへ移動)。
        RECT currentField{};   ///< 現在のフレームの欄(押すと入力できる)。
        RECT startButton{};    ///< 再生範囲の最初へ移動するボタン。
        RECT prevButton{};     ///< 1コマ戻るボタン。
        RECT button{};         ///< 再生/停止ボタン。
        RECT nextButton{};     ///< 1コマ進むボタン。
        RECT endButton{};      ///< 再生範囲の最後へ移動するボタン。
        RECT rangeRow{};       ///< レンジスライダーの段。
        RECT animStartField{};  ///< 全体範囲の最初の欄(押すと入力できる。以下の欄も同じ)。
        RECT playStartField{};  ///< 再生範囲の最初の欄。
        RECT rangeBar{};        ///< レンジスライダーのバー(全体範囲を割り当てる横幅)。
        RECT playEndField{};    ///< 再生範囲の最後の欄。
        RECT animEndField{};    ///< 全体範囲の最後の欄。
        RECT clipStartLabel{};  ///< 「動画の開始」の文字。
        RECT clipStartField{};  ///< 動画の開始(動画の1コマ目を置くフレーム番号)の欄。
        RECT rateLabel{};      ///< フレームレートの文字。
        RECT syncButton{};     ///< 「Maya連携」ボタン(押すと連携モードと通常モードを切り替える)。
        RECT fileButton{};     ///< 「ファイル」ボタン(押すとファイルのメニューを出す)。
        RECT compareButton{};  ///< 「比較」ボタン(2本目の動画を選ぶ。比較中に押すと比較をやめる)。
        RECT volumeButton{};   ///< スピーカーのボタン(押すと消音を切り替える)。
        RECT volumeSlider{};   ///< 音量の三角形(クリック判定には上下に広げた範囲を使う)。
    };

    /**
     * @brief 動画ファイルを開く(目次を作り、先頭のコマを読む)。失敗時はメッセージボックスで知らせる。
     * @param path 動画ファイルのパス。
     * @param comparing 比較中として開くか(キャッシュの上限が半分になる)。
     * @return 開けた動画。失敗時はnullptr。
     */
    std::shared_ptr<Clip> loadClip(const std::wstring& path, bool comparing);

    /**
     * @brief 開いた動画を描画スレッドへ渡す前の準備(キャッシュの上限・動作状態・縮小画像の作成開始)をする。
     * @param clip 対象の動画。clip_かcompareClip_に入れた後に呼ぶ。
     * @param slot 0なら1本目、1なら2本目(キャッシュの上限を覚えておく場所)。
     * @param thumbnailBytes 縮小画像の合計の上限(バイト)。
     */
    void prepareClip(Clip& clip, int slot, std::size_t thumbnailBytes);

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
     * @brief 操作部(タイムスライダーとレンジスライダーの2段)を描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     * @param area 描き直す範囲。かからない段は描かない。
     */
    void paintControls(HDC dc, const Layout& layout, int dpi, const RECT& area);

    /**
     * @brief キャッシュの有無を表す帯(塗る範囲)を、必要なときだけ計算し直す。
     * @param layout 各部品の位置。
     * @note 一定間隔(kCacheBarIntervalMs)ごと、または横幅や再生範囲が変わったときだけ計算する。
     */
    void updateCacheRuns(const Layout& layout);

    /**
     * @brief タイムスライダー(目盛り・現在のフレーム・キャッシュの帯)を描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     */
    void paintTimeSlider(HDC dc, const Layout& layout, int dpi);

    /**
     * @brief 目盛り(地・細かい目盛り・数字の付く目盛りと数字)を、左上を(0, 0)として描く(作り置き用)。
     * @param dc 描画先(作り置きの画像)。
     * @param width 幅。
     * @param height 高さ。
     * @param slab 地の色。
     * @param outside 動画の外の部分の地の色。
     * @param dpi ウィンドウのDPI。
     */
    void paintRulerMarks(HDC dc, int width, int height, COLORREF slab, COLORREF outside, int dpi);

    /**
     * @brief レンジスライダー(動画全体の中の再生範囲と、両端のつまみ)を描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     */
    void paintRangeSlider(HDC dc, const Layout& layout, int dpi);

    /**
     * @brief 数字の欄を描く。
     * @param dc 描画先(裏の画像)。
     * @param rect 欄の範囲。
     * @param value 表示する数。
     * @param part 欄の部品(マウスが乗っていれば明るくする)。
     * @param primary 主な欄か。falseなら控えめな見た目にする(全体範囲の欄。再生範囲の欄と見分けるため)。
     * @param dpi ウィンドウのDPI。
     */
    void paintField(HDC dc, const RECT& rect, int value, Part part, bool primary, int dpi);

    /**
     * @brief 部品の範囲を返す(クリック・ホバー・ツールチップの判定に使う)。
     * @param layout 各部品の位置。
     * @param part 部品。
     * @return 範囲。目盛り・バー・音量は、押しやすいよう段の高さいっぱいに広げた範囲。
     */
    RECT partRect(const Layout& layout, Part part) const;

    /**
     * @brief 位置にある部品を返す。
     * @param layout 各部品の位置。
     * @param point クライアント座標。
     * @return 部品。どれにも当たらなければPart::None。
     */
    Part hitTestPart(const Layout& layout, POINT point) const;

    /**
     * @brief 部品の説明(ツールチップの文字)を返す。
     * @param part 部品。
     * @return 説明。静的な文字列なので、呼び出し元で保持してよい。
     */
    const wchar_t* tooltipText(Part part) const;

    /** @brief ツールチップを作り、各部品を登録する。 */
    void createTooltips();

    /** @brief ウィンドウの大きさが変わったときに、ツールチップの各部品の範囲を合わせる。 */
    void updateTooltipRects();

    /**
     * @brief マウスが乗っている部品を変える。変わったら操作部を描き直す。
     * @param part 新しい部品。
     */
    void setHover(Part part);

    /**
     * @brief コマのキャッシュの有無を、横幅の画素ごとの塗る範囲にまとめる。
     * @param flags コマごとのキャッシュの有無(Clip::cachedFlags()の結果)。
     * @param first 横幅に割り当てる最初のコマ番号。
     * @param last 横幅に割り当てる最後のコマ番号。
     * @param left 横幅の左端のx。
     * @param width 横幅(ピクセル)。
     * @param runs 塗る範囲[左, 右)の格納先。
     */
    static void buildCacheRuns(const std::vector<std::uint8_t>& flags, int first, int last, int left, int width,
                               std::vector<std::pair<int, int>>& runs);

    /** @brief 操作部だけを描き直すよう要求する(映像の領域は描き直さない)。 */
    void invalidateBar();

    /** @brief タイムスライダーの段(上段)だけを描き直すよう要求する(再生中にコマが進んだとき)。 */
    void invalidateTimeRow();

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
     * @brief マウスの中ボタンが押されたときの処理。映像の上なら、その映像のコマを動かすドラッグを始める。
     * @param x クライアント座標のx。
     * @param y クライアント座標のy。
     * @note 比較中は、左の映像の上なら1本目だけを動かし(2本目の表示はそのまま、オフセットが逆に変わる)、
     *       右の映像の上なら2本目のオフセットを変える。1本だけのときは、その動画のコマを動かす。
     *       再生中なら押した時点で止め、離したら再生を続ける。
     */
    void onMiddleButtonDown(int x, int y);

    /**
     * @brief Kを押しながら映像の上で左ボタンが押されたら、現在のフレームを動かすドラッグを始める(Mayaの仮想タイムスライダー)。
     * @param x クライアント座標のx。
     * @param y クライアント座標のy。
     * @return ドラッグを始めたらtrue(押した位置が映像の外・Kを押していない・動画が無いときはfalse)。
     * @note 押した位置からの左右の距離でコマを動かす(中ボタンのドラッグと同じ距離で1コマ)。比較中は2本とも
     *       オフセットを保って動く。再生中なら押した時点で止め、離したら再生を続ける。
     */
    bool beginKeyScrub(int x, int y);

    /**
     * @brief 映像の上の中ボタンドラッグ中か。
     * @return Drag::PaneMainかDrag::PaneCompareならtrue。
     */
    bool paneDragging() const { return drag_ == Drag::PaneMain || drag_ == Drag::PaneCompare; }

    /**
     * @brief スライダーをドラッグ中なら、マウス位置のコマへ移動する。映像の上の中ボタンドラッグ中なら、動いた距離に合わせてコマ・オフセットを変える。
     *        ドラッグ中でなければ、マウスが乗っている部品を明るく表示する。
     * @param x クライアント座標のx。
     * @param y クライアント座標のy。
     */
    void onMouseMove(int x, int y);

    /**
     * @brief マウスの左ボタンのダブルクリック。レンジスライダー上なら、動画全体と直前の再生範囲を切り替える(Mayaと同じ)。
     *        映像の上なら、フルスクリーンを切り替える。
     * @param x クライアント座標のx。
     * @param y クライアント座標のy。
     */
    void onDoubleClick(int x, int y);

    /**
     * @brief マウスが乗っている部品に合わせてカーソルの形を決める(レンジスライダーのつまみでは左右の矢印)。
     * @return カーソルを設定した場合true。
     */
    bool updateCursor();

    /**
     * @brief スライダー(タイム・音量)や映像の上の中ボタンのドラッグを終える。マウスの取り込み(SetCapture)も解除する。
     * @note 再生中にタイムスライダーを触った(または映像の上で中ボタンドラッグを始めた)場合は、離した位置から再生を続ける。
     */
    void endScrub();

    /**
     * @brief 動画を開いた後に、設定(「開いたら自動で再生」)に従って再生を始める。
     * @note Mayaとの連携モードのときは再生しない(タイムラインはMaya側が動かすため)。
     */
    void autoPlay();

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
     * @brief 右クリックのメニュー(再生/停止・フルスクリーン)を出し、選ばれた項目を実行する。
     * @param screenPoint メニューを出す位置(画面座標)。キーボードから開いたとき(x・yとも-1)はマウスの位置に出す。
     */
    void showContextMenu(POINT screenPoint);

    /**
     * @brief フルスクリーン表示と通常のウィンドウを切り替える。
     * @note フルスクリーンは、枠とタイトルバーを外して、ウィンドウがあるモニター全体を覆う(操作部はそのまま表示する)。
     *       戻すときは、フルスクリーンにする前の位置・大きさ・最大化の状態に戻す。
     */
    void toggleFullscreen();

    /**
     * @brief Windowsのファイル選択画面で動画を選ばせる。
     * @param title 画面の題名。
     * @return 選ばれたファイルのパス。取り消されたら空。
     */
    std::wstring chooseVideoFile(const wchar_t* title);

    /**
     * @brief 比較中の2本目のオフセットを変える。
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
     * @brief 1コマ戻る・進む。Mayaと同じく、再生範囲の端では反対の端へ回り込む。
     * @param delta -1なら戻る、1なら進む。
     */
    void stepFrame(int delta);

    /**
     * @brief レンジスライダーのバー上のx座標が、どの部品(左右のつまみ・範囲の中)に当たるかを返す。
     * @param layout 各部品の位置。
     * @param x クライアント座標のx。
     * @return RangeStart・RangeEnd・RangeMoveのどれか。どれにも当たらなければNone。
     * @note クリックしたときと、カーソルの形を決めるときの両方で使う(判定を揃えるため)。
     */
    Drag hitTestRange(const Layout& layout, int x) const;

    /**
     * @brief タイムスライダーの目盛り上のx座標に対応するコマ番号を返す。
     * @param x クライアント座標のx。
     * @return コマ番号(動画の1コマ目が0)。再生範囲の外は範囲の端に丸める。
     */
    int frameFromX(int x) const;

    /**
     * @brief レンジスライダーのバー上のx座標に対応するコマ番号を返す。
     * @param x クライアント座標のx。
     * @return コマ番号(動画の1コマ目が0)。全体範囲の外は端に丸める。
     */
    int rangeFrameFromX(int x) const;

    /**
     * @brief レンジスライダーのバー上で、コマの区画の左端のx座標を返す。
     * @param layout 各部品の位置。
     * @param index コマ番号(全体範囲の最後+1を渡すとバーの右端)。
     * @return x座標。
     */
    int rangeXOf(const Layout& layout, int index) const;

    /**
     * @brief 再生範囲を設定する。全体範囲の外にかかるときは、Mayaと同じく全体範囲を広げる。
     * @param first 範囲の最初のコマ番号(動画の1コマ目が0。動画の外でもよい)。
     * @param last 範囲の最後のコマ番号。
     */
    void setPlaybackRange(int first, int last);

    /**
     * @brief 全体範囲と再生範囲をまとめて設定し、表示・再生・先読み・連携先へ伝える。
     * @param animFirst 全体範囲の最初のコマ番号。
     * @param animLast 全体範囲の最後のコマ番号(animFirstより前なら同じにする)。
     * @param playFirst 再生範囲の最初のコマ番号(全体範囲に収める)。
     * @param playLast 再生範囲の最後のコマ番号(全体範囲に収める)。
     * @note 連携先へは再生範囲が変わったときだけ知らせる(Mayaとは再生範囲を合わせる)。
     */
    void setTimeRange(int animFirst, int animLast, int playFirst, int playLast);

    /**
     * @brief 動画をタイムライン上で置く位置(動画の1コマ目のフレーム番号)を変える。
     * @param frame 新しい開始のフレーム番号。
     * @note タイムライン(全体範囲・再生範囲・現在のフレームの番号)はそのままにして、動画だけを動かす。設定にも保存する。
     */
    void setClipStart(int frame);

    /**
     * @brief コマ番号を、扱えるフレーム番号の範囲(±1億。連携で受け付ける範囲と同じ)に収める。
     * @param index コマ番号(動画の1コマ目が0)。
     * @return 収めたコマ番号。
     */
    int clampIndex(long long index) const;

    /**
     * @brief 数字の欄の入力を始める。欄の上に入力用の子ウィンドウ(EDIT)を重ねる。
     * @param field 入力する欄。
     */
    void beginEdit(EditField field);

    /** @brief 入力中の数字を反映して入力を終える。数字として読めなければ何もせずに終える。 */
    void commitEdit();

    /** @brief 入力を取り消して終える。 */
    void cancelEdit();

    /**
     * @brief 入力用の子ウィンドウのキー入力を横取りする(EnterとEscを親へ知らせる)。
     * @param hwnd 入力用の子ウィンドウ。
     * @param message メッセージの種類。
     * @param wParam メッセージごとの値。
     * @param lParam メッセージごとの値。
     * @param id 横取りの登録番号。
     * @param data 登録時に渡したPlayerWindowのポインター。
     * @return メッセージごとの処理結果。
     */
    static LRESULT CALLBACK editProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam, UINT_PTR id,
                                     DWORD_PTR data);

    /**
     * @brief 連携の待ち受け口(SyncServer)からの知らせを処理する。
     * @param event 知らせの種類(SyncServer::Event)。
     * @param lParam 命令の行(kLineのときだけ。std::string*で、この関数が解放する)。
     * @note 受け取った命令でタイムスライダーを動かしている間は、連携先へ送り返さない(行ったり来たりを防ぐ)。
     */
    void onSyncMessage(WPARAM event, LPARAM lParam);

    /**
     * @brief 1行の命令を実行する(frame・range・play・stop)。
     * @param line 命令。
     */
    void applySyncCommand(const std::string& line);

    /** @brief つながった相手へ、挨拶と再生中かを送る(フレームと再生範囲は相手側を正とするので送らない)。 */
    void sendSyncState();

    /** @brief 現在のフレームが変わったことを連携先へ知らせる(変わっていなければ知らせない)。 */
    void notifyCurrentFrame();

    /** @brief 再生・停止が変わったことを連携先へ知らせる(変わっていなければ知らせない)。 */
    void notifyPlayState();

    /**
     * @brief 再生を止め、指定したコマを表示する。範囲外は端に丸める。
     * @param index 0始まりのコマ番号。
     * @param scrubbing タイムラインのドラッグ中か。trueなら前後に同じだけ先読みさせる。
     * @param compareOffset 指定すると、2本目のオフセットも同時に変える(2本目の表示を途中の位置へ動かさないため)。
     */
    void goToFrame(int index, bool scrubbing = false, std::optional<int> compareOffset = std::nullopt);

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

    HWND hwnd_ = nullptr;
    HINSTANCE instance_ = nullptr;
    // 破棄の順序: clip_(裏の読み込みスレッド)を先に止めてからview_を破棄し、最後にgpu_を破棄する
    // (宣言の逆順に破棄される)。
    std::shared_ptr<GpuDevice> gpu_;  ///< デコード・キャッシュ・描画で共有するGPUデバイス。無ければnullptr。
    VideoView view_;              ///< 映像の表示と再生の時間管理。
    std::shared_ptr<Clip> clip_;  ///< 表示中の動画。描画スレッドとも共有する。未読み込みならnullptr。
    std::shared_ptr<Clip> compareClip_;  ///< 比較用の2本目の動画。比較していなければnullptr。
    Settings settings_;                   ///< 次回の起動でも使う設定(音量・キャッシュ上限・開始フレームなど)。
    std::shared_ptr<AudioPlayer> audio_;  ///< 表示中の動画の音声。描画スレッドとも共有する。
    std::size_t appliedLimit_[2] = {};   ///< 動画へ最後に伝えたバイト数の上限(0=1本目、1=2本目)。
    int appliedFrames_[2] = {};          ///< 動画へ最後に伝えたコマ数の上限。
    bool memoryLow_ = false;             ///< Windowsが主メモリの不足を知らせているか。
    HANDLE lowMemory_ = nullptr;         ///< 主メモリの不足を知る仕組み(CreateMemoryResourceNotification)。
    bool appActive_ = true;              ///< このアプリが前面にあるか。
    bool minimized_ = false;             ///< 最小化されているか。
    bool fullscreen_ = false;            ///< フルスクリーン表示中か。
    WINDOWPLACEMENT windowedPlacement_{sizeof(WINDOWPLACEMENT)};  ///< フルスクリーンにする前の位置・大きさ(戻すときに使う)。
    bool dormant_ = false;               ///< 休止中か。
    ULONGLONG inactiveSinceMs_ = 0;      ///< 前面でなくなった時刻(GetTickCount64)。
    ULONGLONG minimizedSinceMs_ = 0;     ///< 最小化された時刻(GetTickCount64)。
    Clip::Activity activity_ = Clip::Activity::Interactive;  ///< 動画へ最後に伝えた動作状態。
    ui::FontCache fonts_;     ///< 操作部の描画に使う書体(大きさごとに使い回す)。
    ui::BackBuffer backBuffer_;      ///< 操作部の描画に使う裏の画像(使い回す)。
    ui::Layer rulerLayer_;           ///< 目盛りの作り置き(通常の地)。
    ui::Layer rulerHighlightLayer_;  ///< 目盛りの作り置き(現在のフレームの区画の色の地)。
    RulerKey rulerKey_;              ///< 目盛りの作り置きを作ったときの条件。
    LONGLONG lastTitleTicks_ = 0;    ///< 最後にタイトルバーを書き換えた時刻。
    int current_ = 0;             ///< 操作部に表示しているコマ番号(VideoViewの表示に追従する)。
    int animFirst_ = 0;           ///< 全体範囲の最初のコマ番号(動画の1コマ目が0。動画の外でもよい)。
    int animLast_ = 0;            ///< 全体範囲の最後のコマ番号。
    int playFirst_ = 0;           ///< 再生範囲の最初のコマ番号(全体範囲の中)。
    int playLast_ = 0;            ///< 再生範囲の最後のコマ番号。
    int savedFirst_ = 0;          ///< レンジスライダーのダブルクリックで戻す再生範囲の最初。
    bool hasSavedRange_ = false;  ///< savedFirst_・savedLast_が有効か(コマ番号は負もあり得るので、別に持つ)。
    int savedLast_ = -1;          ///< 同じく最後。
    Drag drag_ = Drag::None;      ///< ドラッグしている部品。
    int dragAnchor_ = 0;          ///< 範囲の移動を始めたときのマウス位置のコマ番号。
    int dragFirst_ = 0;           ///< 範囲の移動を始めたときの再生範囲の最初。
    int dragLast_ = 0;            ///< 同じく最後。
    int paneDragX_ = 0;           ///< 映像の上の中ボタンドラッグを始めたときのマウスのx。
    int paneDragFrame_ = 0;       ///< 同じく、そのときの1本目のコマ番号。
    int paneDragOffset_ = 0;      ///< 同じく、そのときの2本目のオフセット。
    EditField editField_ = EditField::None;  ///< 入力中の欄。
    HWND editControl_ = nullptr;  ///< 入力用の子ウィンドウ(入力中だけある)。
    HWND tooltip_ = nullptr;      ///< 部品の説明を出すツールチップ(このウィンドウが持ち、一緒に破棄される)。
    Part hover_ = Part::None;     ///< マウスが乗っている部品。
    bool trackingLeave_ = false;  ///< マウスがウィンドウから出たことの知らせ(WM_MOUSELEAVE)を頼んでいるか。
    HBRUSH editBrush_ = nullptr;  ///< 入力用の子ウィンドウの背景のブラシ。
    std::unique_ptr<TimeSync> sync_;  ///< タイムスライダーの変化を知らせる先(Mayaとの連携など)。無ければnullptr。
    SyncServer* syncServer_ = nullptr;  ///< sync_が連携の待ち受け口のときの、その口(sync_が持つ)。
    bool applyingRemote_ = false;       ///< 連携先から受け取った命令を実行中か(実行中の変化は送り返さない)。
    int notifiedFrame_ = 0x7FFFFFFF;  ///< 連携先へ最後に知らせたフレーム番号。
    bool notifiedPlaying_ = false;    ///< 連携先へ最後に知らせた再生状態。
    std::vector<std::pair<int, int>> rangeCacheRuns_;  ///< レンジスライダーのキャッシュ表示で塗る範囲。
    RECT rangeCacheRunsBar_{};                         ///< rangeCacheRuns_を計算したときのバーの範囲。
    int cacheRunsFirst_ = -1;                          ///< cacheRuns_を計算したときの再生範囲の最初。
    int cacheRunsLast_ = -1;                           ///< 同じく最後。
    int cacheRunsAnimFirst_ = 0;                       ///< rangeCacheRuns_を計算したときの全体範囲の最初。
    int cacheRunsAnimLast_ = -1;                       ///< 同じく最後。

    std::atomic<bool> frameReadyPending_{false};  ///< 裏の読み込みからの知らせが未処理か(送りすぎ防止)。
    std::vector<std::uint8_t> cacheFlags_;        ///< キャッシュ表示用の作業領域(描画のたびに確保しないため)。
    LONGLONG lastCacheBarTicks_ = 0;              ///< キャッシュ表示を最後に計算した時刻。
    std::vector<std::pair<int, int>> cacheRuns_;  ///< キャッシュ表示で塗る横の範囲[左, 右)の一覧。
    RECT cacheRunsTrack_{};                       ///< cacheRuns_を計算したときのスライダーの範囲。

    bool resumeAfterScrub_ = false;  ///< ドラッグを終えたら再生を続けるか(再生中にドラッグを始めた)。
    bool keepDisplayOn_ = false;  ///< 画面の消灯を止めるようWindowsへ伝えているか。
};

}  // namespace frameplayer
