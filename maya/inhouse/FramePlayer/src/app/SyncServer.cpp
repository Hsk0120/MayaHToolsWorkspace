/**
 * @file SyncServer.cpp
 * @brief 外部アプリとの連携の待ち受け口の実装。
 */
#include "app/SyncServer.h"

#include <ws2tcpip.h>

#include "app/SyncLog.h"

#include <cstdio>

namespace frameplayer {

namespace {

/// 1行の長さの上限。これを超える行は壊れた入力として捨てる。
constexpr std::size_t kMaxLineLength = 4096;

/// 接続を待つ・届くのを待つときに、止める指示を確かめる間隔(ミリ秒)。
constexpr long kPollMs = 200;

}  // namespace

SyncServer::~SyncServer() {
    stop();
}

bool SyncServer::start(HWND window, UINT message, unsigned short port) {
    if (thread_.joinable()) {
        return true;
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
    // 同じ番号を別のアプリが使っていたら失敗させる(取り合いを避ける)。
    BOOL exclusive = TRUE;
    setsockopt(listener_, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char*>(&exclusive), sizeof(exclusive));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    InetPtonW(AF_INET, L"127.0.0.1", &address.sin_addr);
    if (bind(listener_, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) == SOCKET_ERROR ||
        listen(listener_, 1) == SOCKET_ERROR) {
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
    {
        std::lock_guard<std::mutex> lock(mutex_);
        closeClientLocked();
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

void SyncServer::closeClientLocked() {
    if (client_ != INVALID_SOCKET) {
        closesocket(client_);
        client_ = INVALID_SOCKET;
    }
    connected_ = false;
}

void SyncServer::sendLine(const std::string& line) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (client_ == INVALID_SOCKET) {
        return;
    }
    const std::string data = line + "\n";
    // 接続は待たない設定にしてあるので、相手の受け取りが詰まっていれば送らずに戻る(UIを止めない)。
    const int sent = send(client_, data.data(), static_cast<int>(data.size()), 0);
    syncLog("send %s result=%d", line.c_str(), sent == SOCKET_ERROR ? -WSAGetLastError() : sent);
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

void SyncServer::run() {
    std::string buffer;
    while (!stop_) {
        // 接続の受け付けと、届いた文字の受け取りを、両方まとめて待つ(止める指示も一定間隔で確かめる)。
        fd_set readable;
        FD_ZERO(&readable);
        FD_SET(listener_, &readable);
        SOCKET client = INVALID_SOCKET;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            client = client_;
        }
        if (client != INVALID_SOCKET) {
            FD_SET(client, &readable);
        }
        timeval timeout{0, kPollMs * 1000};
        if (select(0, &readable, nullptr, nullptr, &timeout) <= 0) {
            continue;
        }

        if (FD_ISSET(listener_, &readable)) {
            SOCKET accepted = accept(listener_, nullptr, nullptr);
            if (accepted != INVALID_SOCKET) {
                // 送るときに待たない設定にする。新しい接続が来たら古い方は切る。
                u_long nonBlocking = 1;
                ioctlsocket(accepted, FIONBIO, &nonBlocking);
                BOOL noDelay = TRUE;
                setsockopt(accepted, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&noDelay), sizeof(noDelay));
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    closeClientLocked();
                    client_ = accepted;
                    connected_ = true;
                }
                buffer.clear();
                PostMessageW(window_, message_, kConnected, 0);
            }
            continue;
        }

        if (client != INVALID_SOCKET && FD_ISSET(client, &readable)) {
            char chunk[1024];
            const int received = recv(client, chunk, sizeof(chunk), 0);
            if (received <= 0) {
                if (received == SOCKET_ERROR && WSAGetLastError() == WSAEWOULDBLOCK) {
                    continue;
                }
                // 相手が切った、または通信が壊れた。
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    if (client_ == client) {
                        closeClientLocked();
                    }
                }
                PostMessageW(window_, message_, kDisconnected, 0);
                continue;
            }
            buffer.append(chunk, static_cast<std::size_t>(received));
            // 改行ごとに1つの命令としてUIスレッドへ渡す。
            for (std::size_t end; (end = buffer.find('\n')) != std::string::npos;) {
                std::string line = buffer.substr(0, end);
                buffer.erase(0, end + 1);
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                if (!line.empty()) {
                    syncLog("recv %s", line.c_str());
                    auto* message = new std::string(std::move(line));
                    if (!PostMessageW(window_, message_, kLine, reinterpret_cast<LPARAM>(message))) {
                        delete message;  // ウィンドウが無くなっていた。
                    }
                }
            }
            if (buffer.size() > kMaxLineLength) {
                buffer.clear();
            }
        }
    }
}

}  // namespace frameplayer
