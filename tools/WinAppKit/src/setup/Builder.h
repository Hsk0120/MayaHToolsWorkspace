/**
 * @file Builder.h
 * @brief アプリの設定ファイル(INI)から、そのアプリのセットアップのexeを作る。
 */
#pragma once

#include <string>

namespace wak {

/** @brief セットアップのexeに中身を埋め込むリソースの名前(種類はRCDATA)。 */
inline constexpr wchar_t kPackageResource[] = L"WAKPACKAGE";

/**
 * @brief セットアップのexeを作る。
 * @param manifestPath アプリの設定ファイル(INI)。[Files] の元のファイルは、このファイルのフォルダからの相対パス。
 * @param outputPath 書き出すセットアップのexe。
 * @return 成功なら0、失敗なら2(理由は記録に書く)。
 * @note このexe(WinAppSetup.exe)自身を写し、写した方に中身(Package.h の形式)とアイコンをリソースとして足す。
 *       セットアップのexeは、起動すると自分のリソースから中身を取り出してインストールする。
 *       バージョンが設定ファイルに無ければ、本体のexeのバージョン情報から読む。
 */
int buildSetup(const std::wstring& manifestPath, const std::wstring& outputPath);

}  // namespace wak
