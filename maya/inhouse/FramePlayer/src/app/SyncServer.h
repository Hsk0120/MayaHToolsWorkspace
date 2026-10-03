/**
 * @file SyncServer.h
 * @brief Mayaなどの外部アプリとタイムスライダーを連携させる待ち受け口(TCP、このPCの中だけ、相互認証あり)。
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
 * @brief 127.0.0.1の決まった番号の口で接続を待ち、相手を確かめてから、1行1命令の文字で双方向にやり取りする。
 * @note 相手の確かめ方(相互認証。鍵そのものは通信に流さない):
 *         1. FramePlayer→相手: `challenge <乱数>`
 *         2. 相手→FramePlayer: `auth <HMAC(鍵, "maya-to-player:" + 1の乱数)> <相手の乱数>`
 *         3. FramePlayer→相手: `auth <HMAC(鍵, "player-to-maya:" + 相手の乱数)>`(相手はこれでFramePlayerを確かめる)
 *       鍵はユーザーごとの %LOCALAPPDATA%\FramePlayer\sync.key(syncauth::loadOrCreateKey())。
 *       2が正しくなければ、命令を1つも受け付けずに切る。5秒以内に2が来なければ切る。
 *       認証が済んでいない接続は、認証済みの接続を切らない(接続するだけで連携を乗っ取れないように)。
 *       認証後にやり取りする命令(UTF-8、改行区切り):
 *         - 両方向: `frame <番号>`、`range <最初> <最後>`
 *         - 相手→FramePlayer: `play`、`stop`、`hello <名前>`
 *         - FramePlayer→相手: `state playing` / `state stopped`、`hello FramePlayer 2`
 *       つながった直後は、FramePlayerは挨拶と再生状態だけを送り、フレームと再生範囲は相手から受け取る(相手側を正とする)。
 *       受け取った命令は、裏のスレッドからPostMessageでUIスレッドへ渡す(lParamに新しく作った
 *       std::stringのポインターを渡し、UIスレッドが解放する)。命令の中身の検査はUIスレッド側で行う。
 *       送るのはUIスレッドから。相手の読み取りが追いつかず送れないときは、その命令を捨てる
 *       (フレームの通知は次の通知で上書きされるので、捨てても最終的な位置は合う)。
 */
class SyncServer : public TimeSync {
public:
    /// UIスレッドへ渡す知らせの種類(PostMessageのwParam)。
    enum Event : WPARAM {
        kLine = 0,          ///< 認証済みの相手から1行の命令を受け取った(lParamはstd::string*)。
        kConnected = 1,     ///< 相手を確かめて、つながった。
        kDisconnected = 2,  ///< 接続が切れた。
    };

    SyncServer() = default;

    /** @brief 待ち受けを止めてから破棄する。 */
    ~SyncServer() override;

    SyncServer(const SyncServer&) = delete;
    SyncServer& operator=(const SyncServer&) = delete;

    /**
     * @brief 鍵を用意して待ち受けを始める。
     * @param window 知らせを受け取るウィンドウ。
     * @param message 知らせに使うメッセージの番号。
     * @param port 待ち受ける口の番号。
     * @return 待ち受けを始められた場合true(鍵を用意できない、同じ番号を他のアプリが使っているなどで失敗するとfalse)。
     */
    bool start(HWND window, UINT message, unsigned short port);

    /** @brief 待ち受けを止め、接続も切る。 */
    void stop();

    /**
     * @brief 認証済みの相手とつながっているかを返す。
     * @return つながっていればtrue。
     */
    bool connected() const { return connected_; }

    /**
     * @brief 待ち受けている口の番号を返す。
     * @return 番号。待ち受けていなければ0。
     */
    unsigned short port() const { return port_; }

    /**
     * @brief 認証済みの相手へ1行の命令を送る(末尾の改行はこの関数が付ける)。
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
    /** @brief 認証中の接続(裏のスレッドだけが使う)。 */
    struct Pending {
        SOCKET socket = INVALID_SOCKET;
        std::string challenge;   ///< 送ったチャレンジ(乱数)。
        std::string buffer;      ///< 受け取った途中の文字。
        ULONGLONG deadline = 0;  ///< この時刻(GetTickCount64)までに認証が済まなければ切る。
    };

    /** @brief 裏のスレッドの本体。接続を受け付けて相手を確かめ、届いた文字を行に分けてUIスレッドへ渡す。 */
    void run();

    /** @brief 新しい接続を受け付け、チャレンジを送る(認証中の接続があれば切る)。 */
    void acceptPending();

    /**
     * @brief 認証中の接続から届いた文字を読み、応答が正しければ認証済みの接続にする。
     * @note 応答が正しくない・長すぎる・切れた場合は、その接続を切る。
     */
    void readPending();

    /** @brief 認証済みの接続から届いた文字を行に分けて、UIスレッドへ渡す。 */
    void readActive();

    /** @brief 認証中の接続を切る。 */
    void closePending();

    /** @brief 認証済みの接続を切る(呼び出し元がmutex_をかけておくこと)。 */
    void closeActiveLocked();

    /**
     * @brief まとまった文字を、待たない設定の接続へ送り切る(相手が詰まっていたら諦める)。
     * @param socket 送り先。
     * @param data 送る文字。
     * @return 送り切れた場合true。
     */
    static bool sendAll(SOCKET socket, const std::string& data);

    HWND window_ = nullptr;
    UINT message_ = 0;
    unsigned short port_ = 0;
    bool started_ = false;            ///< WSAStartup()に成功したか。
    std::string key_;                 ///< 相手を確かめるための鍵。
    SOCKET listener_ = INVALID_SOCKET;
    Pending pending_;                 ///< 認証中の接続(同時に1つまで)。
    std::mutex mutex_;                ///< active_を守る(送るUIスレッドと、受け取る裏のスレッドが使う)。
    SOCKET active_ = INVALID_SOCKET;  ///< 認証済みの相手。いなければINVALID_SOCKET。
    std::string activeBuffer_;        ///< 認証済みの相手から受け取った途中の文字(裏のスレッドだけが使う)。
    std::atomic<bool> connected_{false};
    std::atomic<bool> stop_{false};
    std::thread thread_;
};

}  // namespace frameplayer
