/**
 * @file Common.h
 * @brief WinAppSetup(汎用インストーラー)で共通に使う、文字列・パス・ファイル・記録(ログ)の小さな関数。
 */
#pragma once

#include <windows.h>

#include <cstdint>
#include <string>
#include <vector>

namespace wak {

/**
 * @brief UTF-8の文字列を、Windowsの文字列(UTF-16)にする。
 * @param text UTF-8の文字列。
 * @return UTF-16の文字列。
 */
std::wstring fromUtf8(const std::string& text);

/**
 * @brief Windowsの文字列(UTF-16)を、UTF-8の文字列にする。
 * @param text UTF-16の文字列。
 * @return UTF-8の文字列。
 */
std::string toUtf8(const std::wstring& text);

/**
 * @brief 前後の空白を取り除く。
 * @param text 元の文字列。
 * @return 取り除いた文字列。
 */
std::wstring trim(const std::wstring& text);

/**
 * @brief 区切り文字で分け、それぞれの前後の空白を取り除く。空の部分は捨てる。
 * @param text 元の文字列。
 * @param separator 区切り文字。
 * @return 分けた文字列。
 */
std::vector<std::wstring> split(const std::wstring& text, wchar_t separator);

/**
 * @brief 英字の大文字・小文字を区別せずに等しいかを返す。
 * @param a 比べる文字列。
 * @param b 比べる文字列。
 * @return 等しければtrue。
 */
bool equalsIgnoreCase(const std::wstring& a, const std::wstring& b);

/**
 * @brief Windowsの決まったフォルダ(LocalAppDataなど)のパスを返す。
 * @param id フォルダの種類(FOLDERID_LocalAppDataなど)。
 * @return パス。得られなければ空。
 */
std::wstring knownFolder(const GUID& id);

/**
 * @brief パスをつなぐ。
 * @param base 前のパス。
 * @param name 後ろに足す名前(相対パス)。
 * @return つないだパス。
 */
std::wstring joinPath(const std::wstring& base, const std::wstring& name);

/**
 * @brief 親フォルダのパスを返す。
 * @param path パス。
 * @return 親フォルダ。無ければ空。
 */
std::wstring parentPath(const std::wstring& path);

/**
 * @brief パスを、ドライブから始まる正規の形(「..」や「/」を含まない形)にする。
 * @param path パス。
 * @return 正規の形のパス。末尾の「\」は付けない。
 */
std::wstring fullPath(const std::wstring& path);

/**
 * @brief パスがフォルダの中(または同じ)にあるかを返す。
 * @param path 調べるパス(正規の形)。
 * @param folder フォルダ(正規の形)。
 * @return 中にある、または同じならtrue。
 */
bool isInside(const std::wstring& path, const std::wstring& folder);

/**
 * @brief ファイルがあるかを返す。
 * @param path パス。
 * @return ファイルがあればtrue(フォルダならfalse)。
 */
bool fileExists(const std::wstring& path);

/**
 * @brief フォルダがあるかを返す。
 * @param path パス。
 * @return フォルダがあればtrue。
 */
bool directoryExists(const std::wstring& path);

/**
 * @brief フォルダを、途中のフォルダも含めて作る。
 * @param path 作るフォルダ。
 * @param created 新しく作ったフォルダの格納先(浅い順)。nullptrなら格納しない。
 * @return 作れた(既にあった)ならtrue。
 */
bool createDirectories(const std::wstring& path, std::vector<std::wstring>* created);

/**
 * @brief ファイルを全部読む。
 * @param path パス。
 * @param data 中身の格納先。
 * @return 読めたらtrue。
 */
bool readFile(const std::wstring& path, std::vector<std::uint8_t>& data);

/**
 * @brief ファイルに書く(あれば上書き)。
 * @param path パス。
 * @param data 中身。
 * @param size 中身のバイト数。
 * @return 書けたらtrue。
 */
bool writeFile(const std::wstring& path, const void* data, std::size_t size);

/**
 * @brief 直前に失敗したWindowsの呼び出しの理由を文字にする。
 * @param code エラー番号(GetLastErrorの値)。
 * @return 理由の文字列。
 */
std::wstring errorText(DWORD code);

/**
 * @brief 記録(ログ)の書き出し先を決める。以後のlogLineはこのファイルにも書く。
 * @param path 書き出すファイル(上書き)。
 */
void openLog(const std::wstring& path);

/**
 * @brief 記録の書き出し先を返す。
 * @return パス。決めていなければ空。
 */
const std::wstring& logPath();

/**
 * @brief 記録に1行書く。標準出力がつながっていれば(コマンドラインから実行したときなど)、そこにも出す。
 * @param format printfと同じ書式。
 */
void logLine(const wchar_t* format, ...);

}  // namespace wak
