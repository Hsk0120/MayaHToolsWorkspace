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
#include "core/KeyframeThumbnails.h"

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
    /// Bothは前後に同じだけ先読みする(スライダーのドラッグなど、向きが定まらない操作で使う)。
    enum class Direction { Forward, Backward, Both };

    /// ウィンドウと再生の状態。先読みの範囲と、裏のスレッドの優先度を決める。
    enum class Activity {
        Playing,      ///< 再生中。通常の優先度で、再生の先を読む。
        Interactive,  ///< 停止中で、このアプリが前面にある。通常の優先度で上限まで先読みし、縮小画像も作る。
        Background,   ///< 停止中で、最小化中または他のアプリが前面にある。低い優先度で、再生ヘッドの近くだけ読む。
        Dormant,      ///< 長く使われていない。キャッシュを表示中の1コマまで減らし、デコーダーも閉じる。
    };

    Clip() = default;

    /** @brief 裏のスレッドを止めてから破棄する。 */
    ~Clip();

    Clip(const Clip&) = delete;
    Clip& operator=(const Clip&) = delete;

    /**
     * @brief 動画を開き、目次を作って先読みを始める。
     * @param path 動画ファイルのパス。
     * @param maxWidth キャッシュする画像の最大幅(ピクセル)。これより大きい動画は縦横比を保って縮小する。
     * @param cpuCacheBytes 主メモリにキャッシュするときの上限(バイト)。
     * @param gpuCacheBytes GPUのメモリにキャッシュするときの上限(バイト)。
     * @param gpu 共有のGPUデバイス。nullptrならGPUを使わない。
     * @param notify コマがキャッシュに入ったときに裏のスレッドから呼ばれる。重い処理をしないこと。
     * @param error 失敗時に理由を格納する。
     * @return 開けた場合true。
     * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。1つのClipで1回だけ呼ぶ。
     *       先頭のコマを読み込んでから戻る(大きさと、主メモリ・GPUのどちらに置くかを確定するため)。
     */
    bool open(const std::wstring& path, int maxWidth, std::size_t cpuCacheBytes, std::size_t gpuCacheBytes,
              std::shared_ptr<GpuDevice> gpu, NotifyCallback notify, std::wstring& error);

    /**
     * @brief キャッシュをGPUのメモリに置いているかを返す。
     * @return GPUのメモリならtrue。
     */
    bool cachesOnGpu() const { return cachesOnGpu_; }

    /**
     * @brief キャッシュの上限を返す。
     * @return バイト数。
     */
    std::size_t cacheLimit() const;

    /**
     * @brief キャッシュの上限を変える(2本目の動画を開いたときに分け合うためなど)。
     * @param bytes 新しい上限(バイト)。
     * @note 上限を下げた場合は、再生ヘッドから遠いコマから捨てて上限に収める。
     */
    void setCacheLimit(std::size_t bytes);

    /**
     * @brief キャッシュに持つコマ数の上限を変える(時間で上限を決めるため)。
     * @param frames 上限のコマ数(1以上)。バイト数の上限と小さい方が効く。
     */
    void setFrameLimit(int frames);

    /**
     * @brief ウィンドウと再生の状態を伝える。先読みの範囲・優先度・縮小画像の作成を切り替える。
     * @param activity 新しい状態。
     */
    void setActivity(Activity activity);

    /**
     * @brief キーフレームの縮小画像(キャッシュに無い位置の仮表示用)の作成を始める。
     * @param width 縮小画像の幅。
     * @param budgetBytes 縮小画像の合計の上限(バイト)。
     * @note 全コマがキャッシュに入る短い動画では、仮表示が要らないので作らない。
     */
    void startThumbnails(int width, std::size_t budgetBytes);

    /**
     * @brief 指定したコマに近いキーフレームの縮小画像を返す(キャッシュに無いコマの仮表示用)。
     * @param index コマ番号。
     * @param imageIndex 返した画像のコマ番号(近くのキーフレーム)の格納先。nullptrなら格納しない。
     * @return 主メモリのBGRA画像。縮小画像が無ければnullptr。
     * @note 描画スレッドから呼んでよい(縮小画像はstartThumbnails()の後は差し替えない)。
     */
    std::shared_ptr<const Frame> preview(int index, int* imageIndex = nullptr) const;

    /**
     * @brief 縮小画像の作成の進み具合を返す(確認用ツールの表示に使う)。
     * @param done 作った枚数。
     * @param total 作る予定の枚数。
     * @param bytes 縮小画像の合計バイト数。
     * @return 作成を終えたならtrue。縮小画像を作らない場合もtrue(done=total=0)。
     */
    bool thumbnailProgress(int& done, int& total, std::size_t& bytes) const;

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
     * @brief コマの表示時刻を返す。
     * @param index 0始まりのコマ番号。範囲外は端に丸める。
     * @return 表示時刻(100ns単位)。音声と同じ時間軸。
     * @note 開いた後は変わらないので、どのスレッドから呼んでもよい。
     */
    long long frameTime(int index) const;

    /**
     * @brief 指定した時刻に表示すべきコマ(表示時刻がその時刻以前で最も新しいコマ)を返す。
     * @param time 時刻(100ns単位)。
     * @return 0始まりのコマ番号。最初のコマより前なら0。
     */
    int frameAtTime(long long time) const;

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
     * @brief ループ再生する範囲(再生範囲)を伝える。ループ中(wrap)の先読みは、この範囲の中で回り込む。
     * @param first 範囲の最初のコマ番号。
     * @param last 範囲の最後のコマ番号(first以上)。
     * @note 範囲の外のコマは、ループ中は最も遠いものとして先に捨てる。
     */
    void setLoopRange(int first, int last);

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
     * @brief ループする範囲を、動画の範囲に収めて返す。
     * @param first 範囲の最初のコマ番号の格納先。
     * @param last 範囲の最後のコマ番号の格納先。
     */
    void loopBoundsLocked(int& first, int& last) const;

    /**
     * @brief 今の上限(バイト数・コマ数・状態)で、キャッシュに持てるコマ数を返す。
     * @return コマ数(1以上)。
     */
    long long capacityLocked() const;

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
     * @brief キャッシュの合計が上限を超えていれば、再生ヘッドから遠いコマから捨てる。mutex_を持った状態で呼ぶ。
     * @param released 捨てたコマの格納先。呼び出し元がロックを外してから解放する。
     */
    void evictLocked(std::vector<std::shared_ptr<const Frame>>& released);

    /**
     * @brief 再生ヘッドからoffset離れたコマ番号を返す。mutex_を持った状態で呼ぶ。
     * @param offset 向きに沿った距離。負なら反対向き。
     * @return コマ番号。範囲外(ループしない場合)なら-1。
     */
    int offsetIndexLocked(int offset) const;

    std::unique_ptr<FrameSource> source_;  ///< open()の後は裏のスレッドだけが使う。
    std::wstring path_;
    std::wstring description_;
    std::vector<long long> frameTimes_;  ///< コマ番号ごとの表示時刻(open()で目次から写す。以後変えない)。
    int frameCount_ = 0;
    double frameRate_ = 0.0;
    int maxWidth_ = 0;
    std::size_t cacheBytes_ = 0;
    bool cachesOnGpu_ = false;
    int frameLimit_ = 0x7FFFFFFF;           ///< キャッシュに持つコマ数の上限。
    int loopFirst_ = 0;                     ///< ループする範囲の最初のコマ番号。
    int loopLast_ = 0x7FFFFFFF;             ///< ループする範囲の最後のコマ番号(動画の範囲に丸めて使う)。
    Activity activity_ = Activity::Interactive;
    std::shared_ptr<GpuDevice> gpu_;        ///< 縮小画像のデコードに渡す共有のGPUデバイス。
    std::unique_ptr<KeyframeThumbnails> thumbnails_;  ///< キーフレームの縮小画像。作らない場合はnullptr。
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
