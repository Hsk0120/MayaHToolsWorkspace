/**
 * @file Settings.h
 * @brief 次回の起動でも使う設定(レジストリのHKEY_CURRENT_USER\Software\FramePlayerに保存する)。
 */
#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace frameplayer {

/**
 * @brief FramePlayerの設定。読み込みは起動時に1回、保存は変わったときに項目ごとに行う。
 * @note 画面から変えられない項目(CacheMB・CacheSeconds・SyncPort)は、レジストリを直接書いて設定する。
 *       値が無い・範囲外の場合は既定値のまま使う。
 */
struct Settings {
    static constexpr std::size_t kDefaultCacheMegabytes = 1024;  ///< キャッシュの上限の既定値(MB)。
    static constexpr int kDefaultCacheSeconds = 30;              ///< キャッシュに持つ長さの既定値(秒)。
    static constexpr int kDefaultStartFrame = 1;                 ///< 動画の開始(1コマ目を置くフレーム番号)の既定値。
    static constexpr unsigned short kDefaultSyncPort = 7010;     ///< 連携の待ち受け口の番号の既定値。
    static constexpr std::size_t kMaxRecentFiles = 8;            ///< 「最近使ったファイル」に残す数。

    float volume = 0.8f;                                  ///< 音量(0.0〜1.0)。Volume(0〜100)。
    bool muted = false;                                   ///< 消音中か。Muted。
    std::size_t cacheMegabytes = kDefaultCacheMegabytes;  ///< キャッシュの上限(MB)。CacheMB。
    int cacheSeconds = kDefaultCacheSeconds;              ///< キャッシュに持つ長さの上限(秒)。CacheSeconds。
    int startFrame = kDefaultStartFrame;                  ///< 動画の開始(タイムライン上で1コマ目を置くフレーム番号)。StartFrame。
    unsigned short syncPort = kDefaultSyncPort;           ///< 連携の待ち受け口の番号。SyncPort。
    bool autoPlay = true;                                 ///< 動画を開いたら自動で再生するか。AutoPlay。
    std::vector<std::wstring> recentFiles;                ///< 最近使ったファイル(新しい順)。RecentFiles。

    /** @brief 全ての項目をレジストリから読む。 */
    void load();

    /** @brief 音量と消音を保存する。 */
    void saveAudio() const;

    /** @brief 動画の開始を保存する。 */
    void saveStartFrame() const;

    /** @brief 自動再生の設定を保存する。 */
    void saveAutoPlay() const;

    /** @brief 最近使ったファイルを保存する。 */
    void saveRecentFiles() const;

    /**
     * @brief 開いたファイルを「最近使ったファイル」の先頭に加えて保存する。同じファイルは先頭へ移す。
     * @param path ファイルのパス。
     */
    void addRecentFile(const std::wstring& path);
};

}  // namespace frameplayer
