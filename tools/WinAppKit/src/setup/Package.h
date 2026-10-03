/**
 * @file Package.h
 * @brief インストールする中身(アプリの説明とファイル)を1つのバイト列にまとめる形式の読み書き。
 *
 * セットアップのexeは、このバイト列をリソース(RCDATAの「WAKPACKAGE」)として持つ。形式:
 * @code
 * "WAKPKG01"(8バイト)
 * 説明の長さ(4バイト) + 説明(UTF-8のINI。Manifest::serialize)
 * ファイルの数(4バイト)
 * ファイルごとに: 名前の長さ(4) + 名前(UTF-8) + 元の大きさ(8) + 格納した大きさ(8) + 方式(1: 0=そのまま 1=LZMS) + 中身
 * @endcode
 * 数はすべてリトルエンディアン。圧縮はWindows標準の圧縮API(LZMS)を使う。
 */
#pragma once

#include "setup/Manifest.h"

#include <cstdint>
#include <string>
#include <vector>

namespace wak {

/** @brief パッケージに入れる1つのファイル。 */
struct PackageFile {
    std::wstring target;              ///< インストール先からの相対パス。
    std::vector<std::uint8_t> data;   ///< 中身(圧縮前)。
};

/**
 * @brief 説明とファイルを1つのバイト列にまとめる。
 * @param manifest アプリの説明。
 * @param files ファイル(manifest.filesと同じ順)。
 * @param out まとめたバイト列の格納先。
 * @param error 失敗した理由の格納先。
 * @return 成功ならtrue。
 */
bool writePackage(const Manifest& manifest, const std::vector<PackageFile>& files, std::vector<std::uint8_t>& out,
                  std::wstring& error);

/**
 * @brief まとめたバイト列から、説明とファイルを取り出す。
 * @param data バイト列の先頭。
 * @param size バイト数。
 * @param manifest 説明の格納先。
 * @param files ファイルの格納先。
 * @param error 失敗した理由の格納先(壊れている・形式が違うなど)。
 * @return 成功ならtrue。
 */
bool readPackage(const std::uint8_t* data, std::size_t size, Manifest& manifest, std::vector<PackageFile>& files,
                 std::wstring& error);

}  // namespace wak
