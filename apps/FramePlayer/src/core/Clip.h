/**
 * @file Clip.h
 * @brief 1本の動画を、上限付きのキャッシュと裏での先読みで扱うクラス。
 */
#pragma once

#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "core/Frame.h"
#include "core/FrameSource.h"

namespace frameplayer {

/**
 * @brief 動画の目次を持ち、表示位置(再生ヘッド)の周辺を裏のスレッドで先読みしてキャッシュする。
 * @note コマ番号(0始まり)は読み込み元の目次で決まる。キャッシュに無いコマは無いと答え、
 *       別のコマで代用しない。キャッシュの合計が上限を超えたら、再生ヘッドから遠いコマから捨てる。
 *       公開メソッドはUIスレッドから呼ぶ想定で、内部の状態はmutex_で保護する。
 */
class Clip {
public:
    /// コマがキャッシュに入ったときなどに裏のスレッドから呼ばれる関数。UIへの通知に使う。
    using NotifyCallback = std::function<void()>;

    /// 再生ヘッドの移動方向。先読みする向きを決める。
    enum class Direction { Forward, Backward };

    Clip() = default;

    /** @brief 裏のスレッドを止めてから破棄する。 */
    ~Clip();

    Clip(const Clip&) = delete;
    Clip& operator=(const Clip&) = delete;

    /**
     * @brief 動画を開き、目次を作って先読みを始める。
     * @param path 動画ファイルのパス。
     * @param maxWidth キャッシュする画像の最大幅(ピクセル)。これより大きい動画は縦横比を保って縮小する。
     * @param cacheBytes キャッシュの上限(バイト)。
     * @param notify コマがキャッシュに入ったときに裏のスレッドから呼ばれる。重い処理をしないこと。
     * @param error 失敗時に理由を格納する。
     * @return 開けた場合true。
     * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。1つのClipで1回だけ呼ぶ。
     *       先頭のコマを読み込んでから戻る(大きさを確定するため)。
     */
    bool open(const std::wstring& path, int maxWidth, std::size_t cacheBytes, NotifyCallback notify,
              std::wstring& error);

    /**
     * @brief コマ数を返す。
     * @return コマ数。
     */
    int frameCount() const { return frameCount_; }

    /**
     * @brief ファイルに記録されたフレームレートを返す。
     * @return 1秒あたりのコマ数。不明なら0。
     */
    double frameRate() const { return frameRate_; }

    /**
     * @brief 開いたファイルのパスを返す。
     * @return パス。
     */
    const std::wstring& path() const { return path_; }

    /**
     * @brief キャッシュにあるコマを返す。待たない。
     * @param index 0始まりのコマ番号。
     * @return コマ。キャッシュに無ければnullptr。
     */
    std::shared_ptr<const Frame> frame(int index) const;

    /**
     * @brief コマがキャッシュに入るまで待って返す。再生ヘッドもそのコマへ移す。
     * @param index 0始まりのコマ番号。
     * @param direction 先読みする向き。
     * @param timeoutMs 待つ上限(ミリ秒)。
     * @return コマ。時間切れ、またはデコードできないコマならnullptr。
     */
    std::shared_ptr<const Frame> waitForFrame(int index, Direction direction, int timeoutMs);

    /**
     * @brief 再生ヘッドの位置と向きを伝える。裏のスレッドはこの周辺を先読みする。
     * @param index 0始まりのコマ番号。
     * @param direction 先読みする向き。
     * @param wrap 端を越えて反対側の端を続きとして先読みするか(ループ再生用)。
     */
    void setPlayhead(int index, Direction direction, bool wrap);

    /**
     * @brief どのコマがキャッシュにあるかを返す(タイムラインの表示用)。
     * @param flags コマごとに、キャッシュにあれば1、無ければ0を格納する。
     */
    void cachedFlags(std::vector<std::uint8_t>& flags) const;

    /**
     * @brief デコードできなかったコマかを返す。
     * @param index 0始まりのコマ番号。
     * @return デコードを試みたが得られなかったコマならtrue。
     */
    bool isBroken(int index) const;

    /**
     * @brief 読み込み方式の説明を返す(確認用の表示に使う)。
     * @return 例: 「デコード: GPU / 目次: mp4/movの目次」。
     */
    std::wstring description() const;

    /**
     * @brief 裏での読み込みで起きた失敗の説明を返す。
     * @return 失敗していなければ空文字列。
     */
    std::wstring error() const;

private:
    /** @brief 裏のスレッドの本体。先読みすべきコマを探してはデコードし、キャッシュに入れる。 */
    void workerLoop();

    /**
     * @brief 次にデコードすべきコマを探す。mutex_を持った状態で呼ぶ。
     * @return コマ番号。先読みの範囲がすべてキャッシュ済みなら-1。
     * @note 再生ヘッド、向きの先(上限の約3/4)、反対側(約1/4)の順に、未キャッシュのコマを探す。
     */
    int findTargetLocked() const;

    /**
     * @brief 再生ヘッドから見たコマの「遠さ」を返す。mutex_を持った状態で呼ぶ。
     * @param index 0始まりのコマ番号。
     * @return 遠いほど大きい値。進む向きの先にあるコマは近く、後ろにあるコマは遠く扱う。
     */
    long long distanceCostLocked(int index) const;

    /**
     * @brief コマをキャッシュに入れ、上限を超えたら遠いコマから捨てる。mutex_を持った状態で呼ぶ。
     * @param index 0始まりのコマ番号。
     * @param frame 入れるコマ。
     * @param released 捨てたコマ(と、既にあったため入れなかったコマ)の格納先。
     *                 呼び出し元がロックを外してから解放する(解放中に描画側を待たせないため)。
     */
    void storeLocked(int index, std::shared_ptr<const Frame> frame,
                     std::vector<std::shared_ptr<const Frame>>& released);

    /**
     * @brief 再生ヘッドからoffset離れたコマ番号を返す。mutex_を持った状態で呼ぶ。
     * @param offset 向きに沿った距離。負なら反対向き。
     * @return コマ番号。範囲外(ループしない場合)なら-1。
     */
    int offsetIndexLocked(int offset) const;

    std::unique_ptr<FrameSource> source_;  ///< open()の後は裏のスレッドだけが使う。
    std::wstring path_;
    std::wstring description_;
    int frameCount_ = 0;
    double frameRate_ = 0.0;
    int maxWidth_ = 0;
    std::size_t cacheBytes_ = 0;
    NotifyCallback notify_;

    mutable std::mutex mutex_;
    std::condition_variable wake_;          ///< 裏のスレッドを起こす(再生ヘッドの移動・終了)。
    std::condition_variable frameStored_;   ///< コマがキャッシュに入ったことをwaitForFrame()へ知らせる。
    std::vector<std::shared_ptr<const Frame>> frames_;  ///< コマ番号ごとのキャッシュ。無ければnullptr。
    std::vector<std::uint8_t> broken_;      ///< デコードを試みたが得られなかったコマ。
    std::vector<int> cachedIndices_;        ///< キャッシュにあるコマ番号の一覧(順不同。捨てるコマを選ぶときに使う)。
    std::size_t cachedBytes_ = 0;           ///< キャッシュにあるコマの合計バイト数。
    std::size_t frameBytes_ = 1;            ///< 1コマあたりのバイト数(先頭のコマで決まる)。
    int firstDecodedNext_ = -1;             ///< open()で先頭のコマを読んだ後、デコーダーが次に返すコマ番号。
    int playhead_ = 0;
    Direction direction_ = Direction::Forward;
    bool wrap_ = false;
    bool stop_ = false;
    std::wstring error_;

    std::thread worker_;
};

/**
 * @brief 画像を縦横比を保って縮小する。
 * @param source 元の画像。
 * @param maxWidth 縮小後の最大幅。元の幅がこれ以下ならそのまま返す。
 * @return 縮小した画像。
 * @note 縮小先の1画素に対応する元の範囲を平均する(面積平均)。
 */
Frame shrinkToWidth(const Frame& source, int maxWidth);

}  // namespace frameplayer
