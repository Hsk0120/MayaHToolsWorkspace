/**
 * @file AudioPlayer.h
 * @brief 動画の音声を再生するクラス(Media Foundationでデコード、WASAPIで出力。どちらもWindows標準)。
 */
#pragma once

#include <windows.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wrl/client.h>

#include <condition_variable>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace frameplayer {

/**
 * @brief 動画ファイルの最初の音声ストリームを、指定した時刻から再生する。
 * @note 出力は専用のスレッドが受け持つ。公開メソッドはどのスレッドから呼んでもよい(指示はmutex_で渡す)。
 *       再生中は「今聞こえている音声の時刻」を返すので、映像側はこれに合わせて表示するコマを決める。
 *       音声が無いファイルや、音声を出せない環境では、hasAudio()がfalseになり何もしない。
 */
class AudioPlayer {
public:
    AudioPlayer() = default;

    /** @brief 出力スレッドを止めてから破棄する。 */
    ~AudioPlayer();

    AudioPlayer(const AudioPlayer&) = delete;
    AudioPlayer& operator=(const AudioPlayer&) = delete;

    /**
     * @brief 動画ファイルの音声を開き、出力スレッドを始める。
     * @param path 動画ファイルのパス。
     * @return 音声を再生できる状態になればtrue。音声が無い、または開けなければfalse(エラーにはしない)。
     * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。1つのAudioPlayerで1回だけ呼ぶ。
     */
    bool open(const std::wstring& path);

    /**
     * @brief 音声があるかを返す。
     * @return 再生できる音声があればtrue。
     */
    bool hasAudio() const { return hasAudio_; }

    /**
     * @brief 指定した時刻から再生を始める。再生中なら、いったん止めてから始め直す。
     * @param mediaTime 再生を始める時刻(100ns単位、映像のコマの表示時刻と同じ時間軸)。
     */
    void start(long long mediaTime);

    /** @brief 再生を止める。 */
    void stop();

    /**
     * @brief 今聞こえている音声の時刻を返す。
     * @param mediaTime 時刻(100ns単位)の格納先。
     * @return 再生中で時刻が分かる場合true。始めた直後でまだ音が出ていない場合などはfalse。
     */
    bool position(long long& mediaTime) const;

    /**
     * @brief 音量を設定する。
     * @param volume 0.0(無音)〜1.0(最大)。
     */
    void setVolume(float volume);

    /**
     * @brief 消音を切り替える。
     * @param muted 消音するならtrue。
     */
    void setMuted(bool muted);

private:
    /** @brief 出力スレッドへの指示。 */
    enum class Command { None, Start, Stop, Quit };

    /** @brief 出力スレッドの本体。WASAPIの準備、指示の処理、バッファへの書き込みを行う。 */
    void outputLoop();

    /**
     * @brief デコード済みの音声が足りなければデコードして、frames分をdestへ書く。出力スレッドで呼ぶ。
     * @param dest 書き込み先(float、channels_個ずつ並ぶ)。
     * @param frames 書くフレーム数(1フレーム=全チャンネル1サンプルずつ)。
     * @note 音声の終わりに達したら無音で埋める。
     */
    void fill(float* dest, UINT32 frames);

    /**
     * @brief 読み込み位置をmediaTimeへ移し、デコード済みの音声を捨てる。出力スレッドで呼ぶ。
     * @param mediaTime 時刻(100ns単位)。
     * @note シークはその時刻より前の区切りに移るので、mediaTimeより前のサンプルはfill()で読み飛ばす。
     */
    void seek(long long mediaTime);

    Microsoft::WRL::ComPtr<IMFSourceReader> reader_;  ///< 音声のデコード用。open()の後は出力スレッドだけが使う。
    bool started_ = false;   ///< MFStartup()に成功したか。
    bool hasAudio_ = false;
    UINT32 sampleRate_ = 0;  ///< デコード結果の1秒あたりのフレーム数。
    UINT32 channels_ = 0;    ///< デコード結果のチャンネル数。

    // 出力スレッドだけが使う、デコード済みでまだ出していない音声。
    std::vector<float> pending_;
    std::size_t pendingOffset_ = 0;  ///< pending_のうち出し終えた位置(float単位)。
    long long skipBefore_ = 0;       ///< この時刻より前のサンプルは捨てる(シーク直後)。
    bool endOfStream_ = false;

    // スレッド間で共有する状態。mutex_で保護する。
    mutable std::mutex mutex_;
    Command command_ = Command::None;
    long long commandTime_ = 0;
    float volume_ = 1.0f;
    bool muted_ = false;
    bool volumeDirty_ = true;
    bool playing_ = false;
    long long startMediaTime_ = 0;  ///< 今の再生を始めた時刻(100ns単位)。
    long long positionMedia_ = 0;   ///< 最後に測った「聞こえている音声の時刻」(100ns単位)。
    long long positionQpc_ = 0;     ///< positionMedia_を測った時刻(QueryPerformanceCounter)。
    bool positionValid_ = false;

    int initState_ = 0;                  ///< 出力の準備の結果。0=準備中、1=成功、-1=失敗。
    std::condition_variable initDone_;   ///< initState_が決まったことをopen()へ知らせる。
    HANDLE commandEvent_ = nullptr;  ///< 指示があることを出力スレッドへ知らせる(自動リセット)。
    std::thread thread_;
};

}  // namespace frameplayer
