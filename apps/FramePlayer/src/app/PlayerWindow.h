/**
 * @file PlayerWindow.h
 * @brief プレイヤーのメインウィンドウ(Win32)。
 */
#pragma once

#include <windows.h>
#include <shellapi.h>

#include <atomic>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "core/Clip.h"

namespace frameplayer {

/**
 * @brief 動画を表示し、キー操作・タイムスライダー・再生ボタンでコマを移動するウィンドウ。
 * @note 動画1本を扱う。描画はGDIで行い、ちらつき防止のため裏の画像に描いてから転送する。
 *       タイムスライダーと再生ボタンは標準部品を使わず、paint()で直接描いてマウス操作も自前で判定する。
 */
class PlayerWindow {
public:
    PlayerWindow() = default;

    /** @brief 再生用スレッドが残っていれば止めてから破棄する(通常はWM_DESTROYで止まっている)。 */
    ~PlayerWindow();

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
     * @brief 動画を読み込んで表示する。失敗時はメッセージボックスで知らせる。
     * @param path 動画ファイルのパス。
     * @note 読み込みが終わるまで戻らない(読み込み中の操作はできない)。再生中なら停止する。
     */
    void openClip(const std::wstring& path);

private:
    /** @brief ウィンドウ内の各部品の位置(クライアント座標)。 */
    struct Layout {
        RECT video{};   ///< 動画を表示する範囲。
        RECT button{};  ///< 再生/停止ボタン。
        RECT slider{};  ///< タイムスライダー全体(クリック判定にも使う)。
        RECT track{};   ///< スライダーのうちコマを割り当てる横幅(両端は再生位置の線が収まるよう内側に寄せる)。
        RECT info{};    ///< コマ番号などの文字。
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

    /** @brief ウィンドウ全体を描画する。 */
    void paint();

    /**
     * @brief 再生ボタン・タイムスライダー・コマ番号を描く。
     * @param dc 描画先(裏の画像)。
     * @param layout 各部品の位置。
     * @param dpi ウィンドウのDPI。
     */
    void paintControls(HDC dc, const Layout& layout, int dpi);

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

    /** @brief スライダーのドラッグを終える。マウスの取り込み(SetCapture)も解除する。 */
    void endScrub();

    /**
     * @brief ドロップされたファイルのうち最初の1つを開く。
     * @param drop ドロップ情報。処理後に解放する。
     */
    void onDropFiles(HDROP drop);

    /**
     * @brief スライダー上のx座標に対応するコマ番号を返す。
     * @param x クライアント座標のx。
     * @return 0始まりのコマ番号。範囲外は端に丸める。
     */
    int frameFromX(int x) const;

    /**
     * @brief 表示するコマを変更する。範囲外は端に丸める。
     * @param index 0始まりのコマ番号。
     */
    void setCurrentFrame(int index);

    /** @brief 再生中なら停止し、そうでなければ現在のコマから再生する。 */
    void togglePlayback();

    /** @brief 現在のコマから再生を始める。最後のコマにいる場合は先頭から始める。 */
    void startPlayback();

    /** @brief 再生を止める。表示中のコマはそのまま。 */
    void stopPlayback();

    /** @brief 再生用スレッドに停止を合図し、終了を待って後片付けする。スレッドが無ければ何もしない。 */
    void joinTickThread();

    /**
     * @brief 再生用スレッドからの知らせ(コマの境目ごと)の処理。再生開始からの経過時間で表示すべきコマを求めて表示する。
     * @note 最後まで進んだら先頭に戻って繰り返す。経過時間で決めるため、描画が遅れてもコマが飛ぶだけで速さは保たれる。
     */
    void onPlaybackTick();

    /**
     * @brief 再生に使うフレームレートを返す。
     * @return ファイルに記録されたフレームレート。不明なら24。
     */
    double playbackRate() const;

    /**
     * @brief 裏の読み込みでコマがキャッシュに入ったときの処理。待っていたコマが届いたら描き直す。
     * @note キャッシュ表示の描き直しは間引く(先読み中は1秒に数百回届くため)。
     */
    void onFrameReady();

    /** @brief タイトルバーにファイル名と現在のコマを表示する。 */
    void updateTitle();

    HWND hwnd_ = nullptr;
    std::unique_ptr<Clip> clip_;  ///< 表示中の動画。未読み込みならnullptr。
    int current_ = 0;             ///< 表示中のコマ番号(0始まり)。
    std::shared_ptr<const Frame> shownFrame_;  ///< 最後に描いた画像。表示中のコマが読み込み中のとき代わりに残して「読み込み中」と重ねる。
    std::atomic<bool> frameReadyPending_{false};  ///< 裏の読み込みからの知らせが未処理か(送りすぎ防止)。
    std::vector<std::uint8_t> cacheFlags_;     ///< キャッシュ表示用の作業領域(描画のたびに確保しないため)。
    LONGLONG lastCacheBarTicks_ = 0;           ///< キャッシュ表示を最後に計算した時刻。
    std::vector<std::pair<int, int>> cacheRuns_;  ///< キャッシュ表示で塗る横の範囲[左, 右)の一覧。
    RECT cacheRunsTrack_{};                    ///< cacheRuns_を計算したときのスライダーの範囲。

    bool playing_ = false;          ///< 再生中か。
    int playStartFrame_ = 0;        ///< 再生を始めたコマ番号。
    LONGLONG playStartTicks_ = 0;   ///< 再生を始めた時刻(QueryPerformanceCounterの値)。
    int droppedFrames_ = 0;         ///< 再生開始から表示できずに飛ばしたコマ数(描画が追いついているかの確認用)。

    std::thread tickThread_;                ///< コマの境目ごとに再生の知らせを送るスレッド。再生中だけ動く。
    HANDLE stopEvent_ = nullptr;            ///< tickThread_への停止の合図。再生中だけ存在する。
    std::atomic<bool> tickPending_{false};  ///< 送った知らせがまだ処理されていないか(送りすぎ防止)。

    bool scrubbing_ = false;  ///< タイムスライダーをドラッグ中か。
};

}  // namespace frameplayer
