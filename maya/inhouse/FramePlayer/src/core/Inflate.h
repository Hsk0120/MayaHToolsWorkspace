/**
 * @file Inflate.h
 * @brief zlib形式(RFC 1950)・deflate形式(RFC 1951)の圧縮を戻す処理(EXRのZIP・PXR24・DWAの圧縮に使う)。
 */
#pragma once

#include <cstddef>
#include <cstdint>

namespace frameplayer {

/**
 * @brief zlib形式で圧縮されたデータを戻す。
 * @param source 圧縮されたデータ(2バイトの見出しの後にdeflateのデータが続く)。
 * @param sourceSize sourceのバイト数。
 * @param destination 戻したデータの格納先。
 * @param destinationSize destinationの大きさ(戻した後の大きさが分かっていること)。
 * @return 戻したバイト数。壊れている・格納先に入りきらない場合は負。
 * @note 外部のライブラリを使わないよう、RFC 1950/1951に従って書いた。末尾の検査値(Adler-32)は確かめない。
 */
long long inflateZlib(const std::uint8_t* source, std::size_t sourceSize, std::uint8_t* destination,
                      std::size_t destinationSize);

}  // namespace frameplayer
