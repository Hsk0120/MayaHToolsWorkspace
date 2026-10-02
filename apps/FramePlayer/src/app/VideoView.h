/**
 * @file VideoView.h
 * @brief 映像を表示する子ウィンドウ。描画専用のスレッドがGPU(Direct3D 11 + Direct2D)で描く。
 */
#pragma once

#include <windows.h>
#include <d2d1_1.h>
#include <d3d11.h>
#include <dwrite.h>
#include <dxgi1_3.h>
#include <wrl/client.h>

#include <atomic>
#include <memory>
#include <mutex>
#include <thread>

#include "core/Clip.h"

namespace frameplayer {

/**
 * @brief 映像の表示と再生の時間管理を受け持つ子ウィンドウ。
 * @note 描画は専用のスレッドで行い、画面の書き換え(垂直同期)に合わせて表示する。
 *       再生中に表示するコマも描画スレッドが経過時間から決めるので、UIスレッド(キー操作やスライダーの描画)が
 *       一時的に止まっても再生は止まらない。表示するコマが変わると、親ウィンドウへnotifyMessageを送る。
 *       公開メソッドはUIスレッドから呼ぶ。描画スレッドと共有する状態はmutex_とatomicで保護する。
 */
class VideoView {
public:
    VideoView() = default;

    /** @brief 描画スレッドを止めてから破棄する。 */
    ~VideoView();

    VideoView(const VideoView&) = delete;
    VideoView& operator=(const VideoView&) = delete;

    /**
     * @brief 子ウィンドウを作り、描画スレッドを始める。
     * @param instance アプリのインスタンスハンドル。
     * @param parent 親ウィンドウ。
     * @param notifyMessage 表示するコマが変わったときに親へ送るメッセージ。
     * @return 作成できた場合true。
     */
    bool create(HINSTANCE instance, HWND parent, UINT notifyMessage);

    /** @brief 描画スレッドを止める。親ウィンドウが破棄される前に呼ぶ。2回目以降は何もしない。 */
    void shutdown();

    /**
     * @brief 子ウィンドウの位置と大きさを変える。
     * @param bounds 親ウィンドウのクライアント座標での範囲。
     */
    void setBounds(const RECT& bounds);

    /**
     * @brief 表示する動画を差し替える。再生は止め、先頭のコマを表示する。
     * @param clip 表示する動画。nullptrなら何も表示しない。
     */
    void setClip(std::shared_ptr<Clip> clip);

    /**
     * @brief 再生を止め、指定したコマを表示する。
     * @param index 0始まりのコマ番号。範囲外は端に丸める。
     * @param direction 先読みする向き(移動してきた向き)。
     */
    void showFrame(int index, Clip::Direction direction);

    /**
     * @brief 現在表示しているコマから再生を始める。
     * @param rate 1秒あたりのコマ数。
     */
    void play(double rate);

    /** @brief 再生を止める。表示中のコマはそのまま。 */
    void stop();

    /**
     * @brief 再生中かを返す。
     * @return 再生中ならtrue。
     */
    bool isPlaying() const { return playing_; }

    /**
     * @brief 表示しているコマ番号を返す。
     * @return 0始まりのコマ番号。
     */
    int currentFrame() const { return current_; }

    /**
     * @brief 再生を始めてから表示できずに飛ばしたコマ数を返す。
     * @return コマ数。
     */
    int droppedFrames() const { return dropped_; }

    /** @brief 描画スレッドを起こす(キャッシュにコマが入ったときなど、描き直しが必要かもしれないとき)。 */
    void wake();

    /** @brief 親ウィンドウがnotifyMessageを処理したことを伝える。次の変化を再び知らせられるようにする。 */
    void acknowledgeNotify() { notifyPending_ = false; }

private:
    /**
     * @brief 子ウィンドウのメッセージ処理。描画はすべて描画スレッドが行うので、ここでは背景を消さないだけ。
     * @param hwnd 対象ウィンドウ。
     * @param message メッセージの種類。
     * @param wParam メッセージごとの値。
     * @param lParam メッセージごとの値。
     * @return メッセージごとの処理結果。
     */
    static LRESULT CALLBACK windowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam);

    /** @brief 描画スレッドの本体。 */
    void renderLoop();

    /**
     * @brief Direct3D 11・Direct2D・スワップチェーンを作る。描画スレッドで呼ぶ。
     * @return 作れた場合true。GPUが使えなければCPU用の代わり(WARP)で作る。
     */
    bool createDevice();

    /**
     * @brief スワップチェーンの裏画面をDirect2Dの描画先にする。描画スレッドで呼ぶ。
     * @return 成功ならtrue。
     */
    bool createTarget();

    /**
     * @brief 子ウィンドウの大きさが変わっていれば、スワップチェーンの大きさを合わせる。描画スレッドで呼ぶ。
     * @return 成功ならtrue。
     */
    bool resizeIfNeeded();

    /**
     * @brief 1回分を描いて画面に出す。描画スレッドで呼ぶ。
     * @param clip 表示中の動画。
     * @param frame 描く画像。nullptrなら画像を描かない。
     * @param loading 「読み込み中」を重ねるか。
     * @param broken 「デコードできません」を重ねるか。
     * @return 描けた場合true。デバイスが失われた場合false。
     */
    bool draw(const Clip* clip, const std::shared_ptr<const Frame>& frame, bool loading, bool broken);

    /** @brief 親ウィンドウへ「表示するコマが変わった」と知らせる(未処理の知らせがあれば送らない)。 */
    void notifyParent();

    HWND hwnd_ = nullptr;
    HWND parent_ = nullptr;
    UINT notifyMessage_ = 0;
    std::atomic<bool> notifyPending_{false};

    // UIスレッドから描画スレッドへの指示。mutex_で保護する。
    mutable std::mutex mutex_;
    std::shared_ptr<Clip> clip_;
    int requested_ = 0;              ///< 停止中に表示するコマ。
    bool playRequested_ = false;     ///< 再生中か(UIスレッドの指示)。
    double rate_ = 24.0;             ///< 再生速度(1秒あたりのコマ数)。
    int playStartFrame_ = 0;         ///< 再生を始めたコマ。
    LONGLONG playStartTicks_ = 0;    ///< 再生を始めた時刻(QueryPerformanceCounter)。0なら次の画面更新で決める。
    bool stopThread_ = false;

    // 描画スレッドからUIスレッドへの状態。
    std::atomic<bool> playing_{false};
    std::atomic<int> current_{0};
    std::atomic<int> dropped_{0};

    HANDLE wakeEvent_ = nullptr;     ///< 描画スレッドを起こす合図(自動リセット)。
    std::thread thread_;

    // 以下は描画スレッドだけが使う。
    Microsoft::WRL::ComPtr<ID3D11Device> device_;
    Microsoft::WRL::ComPtr<IDXGISwapChain2> swapChain_;
    HANDLE frameWaitable_ = nullptr;  ///< 次の画面更新に描けるようになると合図される。
    Microsoft::WRL::ComPtr<ID2D1Factory1> d2dFactory_;
    Microsoft::WRL::ComPtr<ID2D1DeviceContext> context_;
    Microsoft::WRL::ComPtr<ID2D1Bitmap1> target_;
    Microsoft::WRL::ComPtr<ID2D1Bitmap1> frameBitmap_;  ///< 表示中の画像をGPUへ写したもの。
    std::shared_ptr<const Frame> frameBitmapSource_;     ///< frameBitmap_に写した画像(同じなら写し直さない)。
    Microsoft::WRL::ComPtr<IDWriteFactory> writeFactory_;
    Microsoft::WRL::ComPtr<IDWriteTextFormat> textFormat_;
    UINT swapWidth_ = 0;
    UINT swapHeight_ = 0;
};

}  // namespace frameplayer
