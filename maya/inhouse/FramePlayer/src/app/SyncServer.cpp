/**
 * @file SyncServer.cpp
 * @brief 外部アプリとの連携の待ち受け口(相互認証あり)の実装。
 */
#include "app/SyncServer.h"

#include <ws2tcpip.h>

#include <cstdio>

#include "app/SyncAuth.h"
#include "core/TraceLog.h"

namespace frameplayer {

namespace {

/// 認証済みの相手からの1行の長さの上限。これを超えたら壊れた相手として切る。
constexpr std::size_t kMaxLineLength = 4096;

/// 認証中の相手から受け取る文字の上限。認証の応答(約150文字)より十分大きく、それ以上は受け付けない。
constexpr std::size_t kMaxPendingBytes = 512;

/// 認証が済むまで待つ時間(ミリ秒)。
constexpr ULONGLONG kAuthTimeoutMs = 5000;

/// チャレンジの乱数の長さ(バイト)。
constexpr std::size_t kChallengeBytes = 16;

/// 接続を待つ・届くのを待つときに、止める指示を確かめる間隔(ミリ秒)。
constexpr long kPollMs = 200;

/**
 * @brief 文字列が、指定範囲の長さの小文字の16進数かを返す。
 * @param text 調べる文字列。
 * @param minLength 最短の長さ。
 * @param maxLength 最長の長さ。
 * @return 条件に合えばtrue。
 */
bool isHex(const std::string& text, std::size_t minLength, std::size_t maxLength) {
    if (text.size() < minLength || text.size() > maxLength) {
        return false;
    }
    for (char c : text) {
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
            return false;
        }
    }
    return true;
}

/**
 * @brief 接続を、送受信で待たない設定にする。
 * @param socket 対象の接続。
 */
void configureSocket(SOCKET socket) {
    u_long nonBlocking = 1;
    ioctlsocket(socket, FIONBIO, &nonBlocking);
    BOOL noDelay = TRUE;
    setsockopt(socket, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&noDelay), sizeof(noDelay));
}

}  // namespace

SyncServer::~SyncServer() {
    stop();
}

bool SyncServer::start(HWND window, UINT message, unsigned short port) {
    if (thread_.joinable()) {
        return true;
    }
    // 鍵を用意できなければ、相手を確かめられないので待ち受けない。
    if (port == 0 || !syncauth::loadOrCreateKey(key_)) {
        return false;
    }
    window_ = window;
    message_ = message;
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        return false;
    }
    started_ = true;

    // このPCの中(127.0.0.1)からだけ受け付ける。他のPCからは接続できない。
    listener_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listener_ == INVALID_SOCKET) {
        return false;
    }
    // 同じ番号を別のアプリが使っていたら失敗させる(他のアプリに同じ番号で割り込まれないようにする)。
    BOOL exclusive = TRUE;
    setsockopt(listener_, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char*>(&exclusive), sizeof(exclusive));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    InetPtonW(AF_INET, L"127.0.0.1", &address.sin_addr);
    if (bind(listener_, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) == SOCKET_ERROR ||
        listen(listener_, 2) == SOCKET_ERROR) {
        closesocket(listener_);
        listener_ = INVALID_SOCKET;
        return false;
    }
    port_ = port;
    stop_ = false;
    thread_ = std::thread(&SyncServer::run, this);
    return true;
}

void SyncServer::stop() {
    stop_ = true;
    if (thread_.joinable()) {
        thread_.join();
    }
    closePending();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        closeActiveLocked();
    }
    if (listener_ != INVALID_SOCKET) {
        closesocket(listener_);
        listener_ = INVALID_SOCKET;
    }
    port_ = 0;
    if (started_) {
        WSACleanup();
        started_ = false;
    }
}

void SyncServer::closePending() {
    if (pending_.socket != INVALID_SOCKET) {
        closesocket(pending_.socket);
    }
    pending_ = Pending{};
}

void SyncServer::closeActiveLocked() {
    if (active_ != INVALID_SOCKET) {
        closesocket(active_);
        active_ = INVALID_SOCKET;
    }
    connected_ = false;
}

bool SyncServer::sendAll(SOCKET socket, const std::string& data) {
    const int sent = send(socket, data.data(), static_cast<int>(data.size()), 0);
    return sent == static_cast<int>(data.size());
}

void SyncServer::sendLine(const std::string& line) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (active_ == INVALID_SOCKET) {
        return;
    }
    // 接続は待たない設定にしてあるので、相手の受け取りが詰まっていれば送らずに戻る(UIを止めない)。
    const std::string data = line + "\n";
    const int sent = send(active_, data.data(), static_cast<int>(data.size()), 0);
    traceLog("send %s result=%d", line.c_str(), sent == SOCKET_ERROR ? -WSAGetLastError() : sent);
}

void SyncServer::currentFrameChanged(int frame) {
    char line[64];
    std::snprintf(line, sizeof(line), "frame %d", frame);
    sendLine(line);
}

void SyncServer::playbackRangeChanged(int first, int last) {
    char line[64];
    std::snprintf(line, sizeof(line), "range %d %d", first, last);
    sendLine(line);
}

void SyncServer::playStateChanged(bool playing) {
    sendLine(playing ? "state playing" : "state stopped");
}

void SyncServer::acceptPending() {
    SOCKET accepted = accept(listener_, nullptr, nullptr);
    if (accepted == INVALID_SOCKET) {
        return;
    }
    // 認証中の接続は同時に1つまで。新しい接続が来たら、認証中の古い方を切る(認証済みの接続はそのまま)。
    closePending();
    configureSocket(accepted);
    pending_.socket = accepted;
    pending_.challenge = syncauth::randomHex(kChallengeBytes);
    pending_.deadline = GetTickCount64() + kAuthTimeoutMs;
    if (pending_.challenge.empty() || !sendAll(accepted, "challenge " + pending_.challenge + "\n")) {
        closePending();
    }
}

void SyncServer::readPending() {
    char chunk[256];
    const int received = recv(pending_.socket, chunk, sizeof(chunk), 0);
    if (received <= 0) {
        if (received == SOCKET_ERROR && WSAGetLastError() == WSAEWOULDBLOCK) {
            return;
        }
        closePending();
        return;
    }
    pending_.buffer.append(chunk, static_cast<std::size_t>(received));
    const std::size_t end = pending_.buffer.find('\n');
    if (end == std::string::npos) {
        if (pending_.buffer.size() > kMaxPendingBytes) {
            closePending();  // 応答より長い文字を送ってくる相手は、応答する気がない(HTTPのリクエストなど)。
        }
        return;
    }

    // 最初の1行は `auth <応答> <相手の乱数>` でなければならない。それ以外は何であっても切る。
    std::string line = pending_.buffer.substr(0, end);
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
    const std::size_t first = line.find(' ');
    const std::size_t second = first == std::string::npos ? std::string::npos : line.find(' ', first + 1);
    const std::string command = line.substr(0, first);
    const std::string response = first == std::string::npos ? std::string() : line.substr(first + 1, second - first - 1);
    const std::string clientNonce = second == std::string::npos ? std::string() : line.substr(second + 1);
    const std::string expected = syncauth::hmacHex(key_, "maya-to-player:" + pending_.challenge);
    if (command != "auth" || !isHex(response, 64, 64) || !isHex(clientNonce, 32, 64) || expected.empty() ||
        !syncauth::constantTimeEquals(response, expected)) {
        traceLog("auth rejected");
        closePending();
        return;
    }

    // 正しい相手だった。こちらも鍵を持っていることを示し、認証済みの接続にする(前の相手は切る)。
    const std::string proof = syncauth::hmacHex(key_, "player-to-maya:" + clientNonce);
    if (proof.empty() || !sendAll(pending_.socket, "auth " + proof + "\n")) {
        closePending();
        return;
    }
    const bool replaced = connected_;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        closeActiveLocked();
        active_ = pending_.socket;
        connected_ = true;
    }
    activeBuffer_ = pending_.buffer.substr(end + 1);  // 応答の後ろに続けて届いた命令。
    pending_ = Pending{};
    traceLog("auth accepted");
    if (replaced) {
        PostMessageW(window_, message_, kDisconnected, 0);
    }
    PostMessageW(window_, message_, kConnected, 0);
    readActive();
}

void SyncServer::readActive() {
    SOCKET active = INVALID_SOCKET;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        active = active_;
    }
    if (active == INVALID_SOCKET) {
        return;
    }
    char chunk[1024];
    const int received = recv(active, chunk, sizeof(chunk), 0);
    if (received > 0) {
        activeBuffer_.append(chunk, static_cast<std::size_t>(received));
    } else if (!(received == SOCKET_ERROR && WSAGetLastError() == WSAEWOULDBLOCK)) {
        // 相手が切った、または通信が壊れた。
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (active_ == active) {
                closeActiveLocked();
            }
        }
        activeBuffer_.clear();
        PostMessageW(window_, message_, kDisconnected, 0);
        return;
    }
    // 改行ごとに1つの命令としてUIスレッドへ渡す。
    for (std::size_t end; (end = activeBuffer_.find('\n')) != std::string::npos;) {
        std::string line = activeBuffer_.substr(0, end);
        activeBuffer_.erase(0, end + 1);
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.empty() || line.size() > kMaxLineLength) {
            continue;
        }
        traceLog("recv %s", line.c_str());
        auto* message = new std::string(std::move(line));
        if (!PostMessageW(window_, message_, kLine, reinterpret_cast<LPARAM>(message))) {
            delete message;  // ウィンドウが無くなっていた。
        }
    }
    if (activeBuffer_.size() > kMaxLineLength) {
        // 改行の来ない長すぎる文字は、壊れた相手として切る。
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (active_ == active) {
                closeActiveLocked();
            }
        }
        activeBuffer_.clear();
        PostMessageW(window_, message_, kDisconnected, 0);
    }
}

void SyncServer::run() {
    while (!stop_) {
        // 接続の受け付けと、認証中・認証済みの相手からの受け取りを、まとめて待つ(止める指示も一定間隔で確かめる)。
        fd_set readable;
        FD_ZERO(&readable);
        FD_SET(listener_, &readable);
        SOCKET active = INVALID_SOCKET;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            active = active_;
        }
        if (active != INVALID_SOCKET) {
            FD_SET(active, &readable);
        }
        if (pending_.socket != INVALID_SOCKET) {
            FD_SET(pending_.socket, &readable);
        }
        timeval timeout{0, kPollMs * 1000};
        const int ready = select(0, &readable, nullptr, nullptr, &timeout);
        if (pending_.socket != INVALID_SOCKET && GetTickCount64() > pending_.deadline) {
            traceLog("auth timeout");
            closePending();  // 時間内に認証しなかった。
        }
        if (ready <= 0) {
            continue;
        }
        if (FD_ISSET(listener_, &readable)) {
            acceptPending();
        }
        if (pending_.socket != INVALID_SOCKET && FD_ISSET(pending_.socket, &readable)) {
            readPending();
        }
        if (active != INVALID_SOCKET && FD_ISSET(active, &readable)) {
            readActive();
        }
    }
}

}  // namespace frameplayer
