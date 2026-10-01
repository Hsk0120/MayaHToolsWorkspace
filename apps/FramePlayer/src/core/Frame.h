/**
 * @file Frame.h
 * @brief 1コマ分の画像データを表す構造体。
 */
#pragma once

#include <cstdint>
#include <vector>

namespace frameplayer {

/**
 * @brief 1コマ分のBGRA画像。
 * @note 画素は上の行から順に並び、行の間に余白はない。各画素はメモリ上でB,G,R,Aの順。
 */
struct Frame {
    int width = 0;                      ///< 幅(ピクセル)。
    int height = 0;                     ///< 高さ(ピクセル)。
    std::vector<std::uint32_t> pixels;  ///< width*height個の画素。
};

}  // namespace frameplayer
