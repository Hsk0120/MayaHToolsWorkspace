/**
 * @file VideoView.h
 * @brief 映像を表示する子ウィンドウ。描画専用のスレッドがGPU(Direct3D 11で映像、Direct2Dで文字)で描く。
 */
#pragma once

#include <windows.h>
#include <d2d1_3.h>
#include <d3d11.h>
#include <dwrite.h>
#include <dxgi1_6.h>
#include <wrl/client.h>

#include <atomic>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

#include "core/AudioPlayer.h"
#include "core/GpuDevice.h"
#include "core/Clip.h"
#include "core/FrameRenderer.h"

namespace frameplayer {

/**
 * @brief 映像の表示と再生の時間管理を受け持つ子ウィンドウ。比較用の2本目の動画を右に並べて表示できる。
 * @note 描画は専用のスレッドで行い、画面の書き換え(垂直同期)に合わせて表示する。
 *       再生中に表示するコマも描画スレッドが経過時間から決めるので、UIスレッド(キー操作やスライダーの描画)が
 *       一時的に止まっても再生は止まらない。表示するコマが変わると、親ウィンドウへnotifyMessageを送る。
 *       公開メソッドはUIスレッドから呼ぶ。描画スレッドと共有する状態はmutex_とatomicで保護する。
 *       2本目の動画(比較)は、1本目のコマ番号にオフセットを足したコマを表示する。再生中は両方のコマが
 *       そろってから進めるので、左右がずれて見えることはない。比較中は音声を鳴らさない。
 *       コマ番号は1本目の動画の1コマ目を0とするタイムライン上の番号で、動画の外(負の番号や最後のコマより後)も
 *       表示・再生できる(Mayaのタイムラインと同じく、範囲は動画の長さに縛られない)。動画の外では「範囲外」と出す。
 *       色はFrameRendererで規格どおりに変換する。SDR・BT.709の8bitの動画は値をそのまま8bitの描画先へ出し、
 *       HDR・BT.709以外の色域・10bitの動画を表示するときは、描画先を16bit浮動小数点(scRGB)に切り替える。
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
     * @param gpu デコード・キャッシュと共有するGPUデバイス。GPUのメモリにあるコマをそのまま描くのに必要。
     *            nullptrなら描画用のデバイスを自分で作る(GPUが無ければCPU用の代わり)。
     * @return 作成できた場合true。
     */
    bool create(HINSTANCE instance, HWND parent, UINT notifyMessage, std::shared_ptr<GpuDevice> gpu = nullptr);

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
     * @param audio 動画の音声。nullptrまたは音声なしなら、PCの時計だけで再生する。
     */
    void setClip(std::shared_ptr<Clip> clip, std::shared_ptr<AudioPlayer> audio = nullptr);

    /**
     * @brief 比較用の2本目の動画を設定する。再生中なら止める。
     * @param clip 2本目の動画。nullptrなら比較をやめて1本だけ表示する。
     */
    void setCompareClip(std::shared_ptr<Clip> clip);

    /**
     * @brief 2本目のオフセットを設定する。2本目には「1本目のコマ番号+オフセット」のコマを表示する。
     * @param offset ずらすコマ数(負も可)。
     */
    void setCompareOffset(int offset);

    /**
     * @brief 2本目のオフセットを返す。
     * @return コマ数。
     */
    int compareOffset() const { return compareOffset_; }

    /**
     * @brief 再生範囲を設定する。再生はこの範囲の中でループする。
     * @param first 範囲の最初のコマ番号(動画の外でもよい)。
     * @param last 範囲の最後のコマ番号(first以上)。
     * @note 再生中に変えた場合、今のコマが範囲の外なら範囲の最初から再生し直す。
     */
    void setPlaybackRange(int first, int last);

    /**
     * @brief 比較中の表示枠の下に出すフレーム番号の始まり(動画の1コマ目の番号)を設定する。
     * @param start 1コマ目のフレーム番号。
     */
    void setFrameNumberStart(int start) { frameNumberStart_ = start; }

    /**
     * @brief 再生を止め、指定したコマを表示する。
     * @param index コマ番号(1本目の1コマ目が0)。動画の外なら「範囲外」と表示する。
     * @param direction 先読みする向き(移動してきた向き)。
     * @param compareOffset 指定すると、2本目のオフセットも同時に変える(途中の組み合わせを描かないよう、同じ鍵の中で変える)。
     */
    void showFrame(int index, Clip::Direction direction, std::optional<int> compareOffset = std::nullopt);

    /**
     * @brief 現在表示しているコマから再生を始める。
     * @param rate 1秒あたりのコマ数(表示中のコマ番号の換算と、半コマずらしに使う)。
     * @note 音声があれば音声も鳴らし、映像の進みを音声の再生位置に合わせる。ただし再生範囲が動画の外にかかるときは
     *       音声を鳴らさず、PCの時計で進める(動画の外には音声が無いため)。
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
     * @return コマ番号(1本目の1コマ目が0。動画の外なら負や最後のコマより大きい値)。
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

    /**
     * @brief 色の解釈の情報を映像の上に出すかを設定する。
     * @param show 出すならtrue。
     */
    void setShowColorInfo(bool show) {
        showColorInfo_ = show;
        redraw();
    }

    /** @brief 描き直す(色の解釈の手動の指定を変えたときなど、コマが同じでも見え方が変わるとき)。 */
    void redraw() {
        ++redrawGeneration_;
        wake();
    }

    /** @brief 画面の状態(HDRの有無・SDRの白の明るさ・表示するモニター)を調べ直して描き直す。 */
    void displayChanged() {
        displayDirty_ = true;
        redraw();
    }

    /**
     * @brief 表示中の画面の状態を返す(情報の表示用)。
     * @return HDRが有効ならtrue。
     */
    bool displayHdr() const { return displayHdr_; }

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

    /** @brief 1つの表示枠(1本目または2本目)に描く内容。 */
    struct PaneState {
        const Clip* clip = nullptr;          ///< 表示する動画。無ければnullptr。
        std::shared_ptr<const Frame> frame;  ///< 描く画像。読み込み中なら直前の画像。
        int index = 0;                       ///< 表示すべきコマ番号(1本目の1コマ目が0)。
        int imageIndex = -1;                 ///< frameが実際に表すコマ番号(仮表示の画像なら近くのキーフレーム)。
        bool loading = false;                ///< 「読み込み中」を重ねるか。
        bool broken = false;                 ///< 「デコードできません」を重ねるか。
        bool outOfRange = false;             ///< 表示すべきコマが動画の外か(画像を描かずに知らせる)。

        /**
         * @brief 前回描いた内容と同じかを返す(停止中に描き直しが必要かの判断に使う)。
         * @param other 比べる内容。
         * @return 同じならtrue。
         */
        bool same(const PaneState& other) const {
            return clip == other.clip && frame == other.frame && index == other.index && loading == other.loading &&
                   broken == other.broken && outOfRange == other.outOfRange;
        }
    };

    /** @brief 表示枠ごとに、RGBへ戻した画像を覚えておく(同じコマ・同じ色の解釈なら作り直さない)。描画スレッドだけが使う。 */
    struct PaneCache {
        FrameRenderer::Image image;  ///< RGBへ戻した画像。
    };

    /**
     * @brief 1回分を描いて画面に出す。描画スレッドで呼ぶ。
     * @param panes 表示枠の内容(1本目、比較中なら2本目)。
     * @param paneCount 表示枠の数(1か2)。
     * @param compareOffset 2本目のオフセット(表示用)。
     * @return 描けた場合true。デバイスが失われた場合false。
     */
    bool draw(const PaneState* panes, int paneCount, int compareOffset);

    /**
     * @brief 描画スレッドを指定時間だけ眠らせる。合図(wake())があれば途中で起きる。
     * @param ticks 眠る長さ(QueryPerformanceCounterの単位)。0以下なら眠らない。
     * @param wakeOnSignal trueならwake()の合図でも起きる。
     * @note 高精度の待機タイマーを使い、CPUを使わずに待つ(Sleepより時刻の誤差が小さい)。
     */
    void sleepTicks(LONGLONG ticks, bool wakeOnSignal);

    /**
     * @brief 1つの表示枠の画像をDirect3Dで描く。描画スレッドで、文字を描く前に呼ぶ。
     * @param pane 描く内容。
     * @param color 当てはめる色の解釈(手動の指定を含む)。
     * @param cache この表示枠の画像の覚え。
     * @param area 画像を収める範囲。
     */
    void drawPaneImage(const PaneState& pane, const ColorInfo& color, PaneCache& cache, const D2D1_RECT_F& area);

    /**
     * @brief 1つの表示枠の文字(知らせ・下の行・色の情報)をDirect2Dで描く。描画スレッドでBeginDrawとEndDrawの間に呼ぶ。
     * @param pane 描く内容。
     * @param area 画像を収める範囲。
     * @param labelArea 下の行の範囲。
     * @param label 表示枠の下に出す文字。空なら出さない(比較中だけ出す)。
     * @param detail 「範囲外」の下に添える説明(動画がタイムラインのどこにあるか)。空なら出さない。
     * @param info 左上に出す色の情報。空なら出さない。
     */
    void drawPaneText(const PaneState& pane, const D2D1_RECT_F& area, const D2D1_RECT_F& labelArea,
                      const std::wstring& label, const std::wstring& detail, const std::wstring& info);

    /**
     * @brief 画面の状態(HDRの有無・SDRの白の明るさ)を、必要なら調べ直す。描画スレッドで呼ぶ。
     * @note 表示するモニターが変わったとき、Windowsの画面の構成が変わったとき(DXGIの工場が古くなったとき)、
     *       displayChanged()が呼ばれたときだけ調べる(毎回は調べない)。
     */
    void updateDisplayState();

    /**
     * @brief 描画先の形式を切り替える。描画スレッドで呼ぶ。
     * @param scRgb trueなら16bit浮動小数点(scRGB)、falseなら8bit(BGRA)。
     * @return 切り替えられたらtrue。scRGBにできなければ8bitに戻してfalse。
     */
    bool setOutputFormat(bool scRgb);

    /**
     * @brief 文字や枠の色(sRGBの値)を、今の描画先で同じ見た目になる値にする。
     * @param color sRGBの色。
     * @return 8bitの描画先ならそのまま、scRGBならリニアにしてSDRの白の明るさを掛けた色。
     */
    D2D1_COLOR_F uiColor(const D2D1_COLOR_F& color) const;

    /**
     * @brief 色の情報の文字を作る(情報の表示用)。
     * @param color 当てはめた色の解釈。
     * @param output 描画先への出し方。
     * @return 2行の文字。
     */
    std::wstring colorInfoText(const ColorInfo& color, FrameRenderer::Output output) const;

    /**
     * @brief 「範囲外」の下に添える説明を作る。
     * @param pane 表示枠の内容。
     * @param shift その動画の1コマ目が、タイムライン上で1本目の1コマ目から何コマ後にあるか(2本目は-オフセット)。
     * @return 「動画は 1001〜8200」のような説明。範囲外でなければ空。
     */
    std::wstring outOfRangeDetail(const PaneState& pane, int shift) const;

    /** @brief 親ウィンドウへ「表示するコマが変わった」と知らせる(未処理の知らせがあれば送らない)。 */
    void notifyParent();

    HWND hwnd_ = nullptr;
    HWND parent_ = nullptr;
    UINT notifyMessage_ = 0;
    std::atomic<bool> notifyPending_{false};

    // UIスレッドから描画スレッドへの指示。mutex_で保護する。
    mutable std::mutex mutex_;
    std::shared_ptr<Clip> clip_;
    std::shared_ptr<Clip> compare_;       ///< 比較用の2本目の動画。比較していなければnullptr。
    std::atomic<int> compareOffset_{0};   ///< 2本目のオフセット(コマ数)。
    std::shared_ptr<AudioPlayer> audio_;  ///< 再生中に鳴らす音声。無ければnullptr。
    int requested_ = 0;              ///< 停止中に表示するコマ。
    bool playRequested_ = false;     ///< 再生中か(UIスレッドの指示)。
    double rate_ = 24.0;             ///< 再生速度(1秒あたりのコマ数)。
    int playStartFrame_ = 0;         ///< 再生を始めたコマ。
    int playFirst_ = 0;              ///< 再生範囲の最初のコマ。
    int playLast_ = 0;               ///< 再生範囲の最後のコマ。
    std::atomic<int> frameNumberStart_{1};  ///< 表示するフレーム番号の始まり(1コマ目の番号)。
    int playSession_ = 0;            ///< play()のたびに増やす番号。描画スレッドが新しい再生の始まりを知るのに使う。
    bool stopThread_ = false;

    // 描画スレッドからUIスレッドへの状態。
    std::atomic<bool> playing_{false};
    std::atomic<int> current_{0};
    std::atomic<int> dropped_{0};

    HANDLE wakeEvent_ = nullptr;     ///< 描画スレッドを起こす合図(自動リセット)。
    std::thread thread_;

    std::shared_ptr<GpuDevice> gpu_;  ///< 共有のGPUデバイス。無ければnullptr。
    std::atomic<bool> showColorInfo_{false};  ///< 色の情報を映像の上に出すか。
    std::atomic<int> redrawGeneration_{0};    ///< 描き直しの要求の番号(redraw()のたびに増やす)。
    std::atomic<bool> displayDirty_{true};    ///< 画面の状態を調べ直すか。
    std::atomic<bool> displayHdr_{false};     ///< 表示中の画面のHDRが有効か(UIスレッドから読む写し)。

    // 以下は描画スレッドだけが使う。
    Microsoft::WRL::ComPtr<ID3D11Device> device_;
    Microsoft::WRL::ComPtr<ID3D11DeviceContext> d3dContext_;   ///< 映像を描く即時コンテキスト。
    Microsoft::WRL::ComPtr<ID3D11RenderTargetView> backBuffer_;  ///< 裏画面に映像を描く窓口。
    Microsoft::WRL::ComPtr<IDXGISwapChain3> swapChain_;
    FrameRenderer renderer_;          ///< 映像の変換と描画。
    bool scRgb_ = false;              ///< 描画先が16bit浮動小数点(scRGB)か。
    bool scRgbUnavailable_ = false;   ///< scRGBの描画先を作れなかった(以後は8bitで画面に合わせて出す)。
    FrameRenderer::DisplayState display_;      ///< 表示中の画面の状態。
    HMONITOR displayMonitor_ = nullptr;        ///< display_を調べたモニター。
    Microsoft::WRL::ComPtr<IDXGIFactory1> displayFactory_;  ///< display_を調べたときの工場(古くなったら調べ直す)。
    HANDLE frameWaitable_ = nullptr;  ///< 次の画面更新に描けるようになると合図される。
    HANDLE timer_ = nullptr;          ///< 次のコマの時刻まで眠るための高精度の待機タイマー。
    Microsoft::WRL::ComPtr<ID2D1Factory3> d2dFactory_;
    Microsoft::WRL::ComPtr<ID2D1DeviceContext2> context_;  ///< 文字と枠を描く。
    Microsoft::WRL::ComPtr<ID2D1Bitmap1> target_;
    PaneCache paneCaches_[2];  ///< 表示枠ごとの画像の覚え(0=1本目、1=2本目)。
    Microsoft::WRL::ComPtr<IDWriteFactory> writeFactory_;
    Microsoft::WRL::ComPtr<IDWriteTextFormat> textFormat_;
    Microsoft::WRL::ComPtr<IDWriteTextFormat> labelFormat_;  ///< 比較中に各表示枠の下に出す文字(左寄せ・小さめ)。
    Microsoft::WRL::ComPtr<IDWriteTextFormat> detailFormat_;  ///< 「範囲外」の下に添える説明(中央寄せ・小さめ)。
    Microsoft::WRL::ComPtr<IDWriteTextFormat> infoFormat_;    ///< 色の情報(左上寄せ・小さめ)。
    UINT swapWidth_ = 0;
    UINT swapHeight_ = 0;
};

}  // namespace frameplayer
