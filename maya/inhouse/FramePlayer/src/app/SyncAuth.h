/**
 * @file SyncAuth.h
 * @brief 連携の相手を確かめるための秘密鍵とHMAC-SHA256(Windows標準の暗号API、BCryptを使う)。
 */
#pragma once

#include <string>

namespace frameplayer::syncauth {

/**
 * @brief ユーザーごとの秘密鍵を読む。無ければ作って保存する。
 * @param key 鍵(16進数64文字)の格納先。
 * @return 用意できた場合true。
 * @note 保存先は %LOCALAPPDATA%\FramePlayer\sync.key。このフォルダはWindowsが本人(と管理者)だけに
 *       読めるようにしているので、同じPCの他のユーザーやブラウザのページからは読めない。
 *       Maya側(python/frameplayer)も同じファイルを読み、同じ鍵を持つ相手かを互いに確かめる。
 */
bool loadOrCreateKey(std::string& key);

/**
 * @brief 推測できない乱数を16進数の文字列で返す(チャレンジに使う)。
 * @param bytes 乱数のバイト数。
 * @return 16進数の文字列(bytesの2倍の長さ)。失敗時は空。
 */
std::string randomHex(std::size_t bytes);

/**
 * @brief HMAC-SHA256を計算し、16進数の文字列で返す。
 * @param key 鍵。
 * @param message 対象の文字列。
 * @return 16進数64文字。失敗時は空。
 */
std::string hmacHex(const std::string& key, const std::string& message);

/**
 * @brief 2つの文字列が等しいかを、内容によらず同じ時間で比べる(比べる時間から答えを推測されないように)。
 * @param a 1つ目。
 * @param b 2つ目。
 * @return 等しければtrue。
 */
bool constantTimeEquals(const std::string& a, const std::string& b);

}  // namespace frameplayer::syncauth
