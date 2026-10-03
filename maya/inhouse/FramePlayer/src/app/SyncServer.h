/**
 * @file SyncServer.h
 * @brief Mayaなどの外部アプリとタイムスライダーを連携させる待ち受け口(TCP、このPCの中だけ)。
 */
#pragma once

#include <winsock2.h>
#include <windows.h>

#include <atomic>
#include <mutex>
#include <string>
#include <thread>

#include "app/TimeSync.h"

namespace frameplayer {

/**
 * @brief 127.0.0.1の決まった番号の口で接続を待ち、1行1命令の文字で双方向にやり取りする。
 * @note やり取りする命令(UTF-8、改行区切り):
 *         - 両方向: `frame <番号>`、`range <最初> <最後>`
 *         - 相手→FramePlayer: `play`、`stop`、`hello <名前>`
 *         - FramePlayer→相手: `state playing` / `state stopped`、`hello FramePlayer 1`
 *       つながった直後は、FramePlayerは挨拶と再生状態だけを送り、フレームと再生範囲は相手から受け取る(相手側を正とする)。
 *       受け取った命令は、裏のスレッドからPostMessageでUIスレッドへ渡す(lParamに新しく作った
 *       std::stringのポインターを渡し、UIスレッドが解放する)。接続は同時に1つで、新しい接続が来たら古い方を切る。
 *       送るのはUIスレッドから。相手の読み取りが追いつかず送れないときは、その命令を捨てる
 *       (フレームの通知は次の通知で上書きされるので、捨てても最終的な位置は合う)。
 */
class SyncServer : public TimeSync {
public:
    /// UIスレッドへ渡す知らせの種類(PostMessageのwParam)。
    enum Event : WPARAM {
        kLine = 0,          ///< 1行の命令を受け取った(lParamはstd::string*)。
        kConnected = 1,     ///< 接続された。
        kDisconnected = 2,  ///< 接続が切れた。
    };

    SyncServer() = default;

    /** @brief 待ち受けを止めてから破棄する。 */
    ~SyncServer() override;

    SyncServer(const SyncServer&) = delete;
    SyncServer& operator=(const SyncServer&) = delete;

    /**
     * @brief 待ち受けを始める。
     * @param window 知らせを受け取るウィンドウ。
     * @param message 知らせに使うメッセージの番号。
     * @param port 待ち受ける口の番号。
     * @return 待ち受けを始められた場合true(同じ番号を他のアプリが使っているなどで失敗するとfalse)。
     */
    bool start(HWND window, UINT message, unsigned short port);

    /** @brief 待ち受けを止め、接続も切る。 */
    void stop();

    /**
     * @brief 相手とつながっているかを返す。
     * @return つながっていればtrue。
     */
    bool connected() const { return connected_; }

    /**
     * @brief 待ち受けている口の番号を返す。
     * @return 番号。待ち受けていなければ0。
     */
    unsigned short port() const { return port_; }

    /**
     * @brief 1行の命令を送る(末尾の改行はこの関数が付ける)。
     * @param line 命令。
     */
    void sendLine(const std::string& line);

    /** @copydoc TimeSync::currentFrameChanged */
    void currentFrameChanged(int frame) override;
    /** @copydoc TimeSync::playbackRangeChanged */
    void playbackRangeChanged(int first, int last) override;
    /** @copydoc TimeSync::playStateChanged */
    void playStateChanged(bool playing) override;

private:
    /** @brief 裏のスレッドの本体。接続を受け付け、届いた文字を行に分けてUIスレッドへ渡す。 */
    void run();

    /**
     * @brief 今の接続を切る(呼び出し元がmutex_をかけておくこと)。
     */
    void closeClientLocked();

    HWND window_ = nullptr;
    UINT message_ = 0;
    unsigned short port_ = 0;
    bool started_ = false;            ///< WSAStartup()に成功したか。
    SOCKET listener_ = INVALID_SOCKET;
    std::mutex mutex_;                ///< client_を守る(送るUIスレッドと、受け取る裏のスレッドが使う)。
    SOCKET client_ = INVALID_SOCKET;  ///< つながっている相手。いなければINVALID_SOCKET。
    std::atomic<bool> connected_{false};
    std::atomic<bool> stop_{false};
    std::thread thread_;
};

}  // namespace frameplayer
