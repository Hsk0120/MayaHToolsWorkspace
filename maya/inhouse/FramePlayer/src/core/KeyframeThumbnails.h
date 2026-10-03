/**
 * @file KeyframeThumbnails.h
 * @brief キーフレームの縮小画像を裏で作って持ち、キャッシュに無い位置の仮表示に使うクラス。
 */
#pragma once

#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "core/Frame.h"
#include "core/FrameSource.h"
#include "core/GpuDevice.h"

namespace frameplayer {

/**
 * @brief 動画全体のキーフレームを小さな画像(既定で幅320)にして持つ。
 * @note キャッシュに無い位置へスライダーを動かしたとき、デコードを待つ間(約0.3秒)に近いキーフレームの画像を
 *       仮に表示するためのもの。あくまで近くのコマの画像で、そのコマ自体ではない。
 *       画像は1画素2バイト(RGB565)で主メモリに持ち、合計がbudgetBytesを超えないよう間隔を空けて選ぶ。
 *       作成は専用のスレッドが低い優先度で行い、粗い間隔から順に埋める(早いうちから全体に散らばる)。
 *       自分専用の読み込み元(デコーダー)を開くので、再生用のデコードとは独立している。
 */
class KeyframeThumbnails {
public:
    /// 縮小画像が1つできたときに裏のスレッドから呼ばれる関数(表示を更新する合図に使う)。
    using NotifyCallback = std::function<void()>;

    KeyframeThumbnails() = default;

    /** @brief 裏のスレッドを止めてから破棄する。 */
    ~KeyframeThumbnails();

    KeyframeThumbnails(const KeyframeThumbnails&) = delete;
    KeyframeThumbnails& operator=(const KeyframeThumbnails&) = delete;

    /**
     * @brief 裏のスレッドで作成を始める。
     * @param path 動画ファイルのパス。
     * @param frameCount 再生用の目次のコマ数(同じファイルなので一致する)。
     * @param frameRate 1秒あたりのコマ数(画像の間隔の下限を1秒にするために使う)。
     * @param width 縮小画像の幅。
     * @param budgetBytes 縮小画像の合計の上限(バイト)。
     * @param gpu 共有のGPUデバイス。nullptrならCPUでデコードする。
     * @param notify 画像が1つできるたびに呼ぶ関数。
     */
    void start(const std::wstring& path, int frameCount, double frameRate, int width, std::size_t budgetBytes,
               std::shared_ptr<GpuDevice> gpu, NotifyCallback notify);

    /**
     * @brief 作成を一時停止するか再開するかを切り替える。
     * @param paused trueなら止める。止めている間はデコーダーを閉じ、GPUのメモリを返す。
     * @note 再生中や、ほかのアプリが前面にあるときに止める。
     */
    void setPaused(bool paused);

    /**
     * @brief 指定したコマに最も近いキーフレームの縮小画像を返す。
     * @param index コマ番号。
     * @param imageIndex 返した画像のコマ番号(キーフレームの番号)の格納先。nullptrなら格納しない。
     * @return 主メモリのBGRA画像。まだ1つも無ければnullptr。
     * @note 同じ画像を続けて求めた場合は同じオブジェクトを返す(描画側が描き直しの要否をアドレスで判断するため)。
     */
    std::shared_ptr<const Frame> nearest(int index, int* imageIndex = nullptr) const;

    /**
     * @brief 作成の進み具合を返す(確認用ツールの表示に使う)。
     * @param done 作った枚数。
     * @param total 作る予定の枚数(選び終わる前は0)。
     * @return 作成を終えた(または作れないと分かった)ならtrue。
     */
    bool progress(int& done, int& total) const;

    /**
     * @brief 持っている縮小画像の合計バイト数を返す。
     * @return バイト数。
     */
    std::size_t bytes() const;

private:
    /**
     * @brief 裏のスレッドの本体。読み込み元を開き、選んだキーフレームを順に縮小画像にする。
     * @param path 動画ファイルのパス。
     * @param gpu 共有のGPUデバイス。
     */
    void run(std::wstring path, std::shared_ptr<GpuDevice> gpu);

    /**
     * @brief 一時停止が解けるか、終了を求められるまで待つ。止めている間はデコーダーを閉じておく。
     * @param source 使っている読み込み元。
     * @return 終了を求められたらtrue。
     */
    bool waitWhilePaused(FrameSource& source);

    int frameCount_ = 0;
    double frameRate_ = 0.0;
    int width_ = 320;
    std::size_t budgetBytes_ = 0;
    NotifyCallback notify_;

    mutable std::mutex mutex_;
    std::condition_variable wake_;
    std::vector<int> positions_;                       ///< 縮小画像を作るコマ番号(昇順)。
    std::vector<std::vector<std::uint16_t>> images_;   ///< positions_に対応する縮小画像(RGB565)。未作成は空。
    int imageWidth_ = 0;                               ///< 縮小画像の幅(最初の1枚で決まる)。
    int imageHeight_ = 0;                              ///< 縮小画像の高さ(最初の1枚で決まる)。
    ColorInfo imageColor_;                             ///< 縮小画像の色の解釈(最初の1枚で決まる)。
    std::size_t bytes_ = 0;                            ///< 作った縮小画像の合計バイト数。
    mutable int lastPosition_ = -1;                    ///< 最後にnearest()で返した画像の位置(positions_の添字)。
    mutable std::shared_ptr<const Frame> lastFrame_;   ///< 最後にnearest()で返した画像。
    bool paused_ = false;
    bool stop_ = false;
    bool finished_ = false;                            ///< 裏のスレッドが作成を終えたか。
    std::thread thread_;
};

}  // namespace frameplayer
