/**
 * @file ExrReader.h
 * @brief OpenEXRの画像を読む処理(外部のライブラリを使わず、OpenEXRのファイル形式の仕様から書いた)。
 */
#pragma once

#include <atomic>
#include <cstdint>
#include <string>
#include <vector>

#include "core/ColorInfo.h"

namespace frameplayer {

/** @brief 読んだEXRの画像。 */
struct ExrImage {
    int width = 0;   ///< 幅(表示範囲の大きさ)。
    int height = 0;  ///< 高さ(表示範囲の大きさ)。
    /// RGBAの各16bit浮動小数点(半精度)の画素。上の行から順に並ぶ(幅×高さ×4個)。データの範囲の外は0。
    std::vector<std::uint16_t> pixels;
    ColorPrimaries primaries = ColorPrimaries::Bt709;  ///< 色域(chromaticitiesの属性。無ければBT.709)。
    bool primariesFromFile = false;                     ///< 色域がファイルに書かれていたか。
    float pixelAspect = 1.0f;                           ///< 1画素の横÷縦(pixelAspectRatioの属性)。
};

/**
 * @brief EXRファイルを読み、RGBAの半精度の画像にする。
 * @param path ファイルのパス。
 * @param image 格納先。
 * @param error 失敗時に理由を格納する。
 * @param cancel trueになったらチャンクの区切りで打ち切る印(先読みを捨てたとき)。nullptrなら打ち切らない。
 * @return 読めた場合true。打ち切ったときはfalse。
 * @note 対応: 走査線(scanline)とタイル(最も細かい段だけ)、複数の部分(最初の部分だけ)、
 *       画素の型(half・float・uint)、圧縮(NONE・RLE・ZIPS・ZIP・PIZ・PXR24・B44・B44A・DWAA・DWAB)。
 *       チャンネルはR・G・B・A(無ければ「名前.R」の形やY)を使う。
 *       未対応: 深いデータ(deep)、縦横に間引いたチャンネル。
 */
bool readExr(const std::wstring& path, ExrImage& image, std::wstring& error,
             const std::atomic<bool>* cancel = nullptr);

/**
 * @brief 32bit浮動小数点を16bit浮動小数点(半精度、IEEE 754)にする(最も近い値に丸める)。
 * @param value 値。
 * @return 半精度のビット列。
 */
std::uint16_t floatToHalf(float value);

/**
 * @brief 16bit浮動小数点(半精度)を32bit浮動小数点にする。
 * @param half 半精度のビット列。
 * @return 値。
 */
float halfToFloat(std::uint16_t half);

}  // namespace frameplayer
