/**
 * @file Frame.h
 * @brief 1コマ分の画像データを表す構造体。
 */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <dxgicommon.h>
#include <wrl/client.h>

#include <cstddef>
#include <cstdint>
#include <vector>

namespace frameplayer {

/**
 * @brief 1コマ分の画像。主メモリのBGRA画像か、GPUのメモリ上のNV12テクスチャのどちらかを持つ。
 * @note 主メモリの画像(pixels)は、上の行から順に並び行の間に余白はない。各画素はメモリ上でB,G,R,Aの順。
 *       GPUのテクスチャ(texture)は、動画本来の形式(NV12: 明るさの面と、縦横半分の色の面)のまま持ち、
 *       描画のときにcolorSpaceに従ってRGBへ変換する。主メモリの画像より約2.7倍小さい。
 */
struct Frame {
    int width = 0;                      ///< 幅(ピクセル)。
    int height = 0;                     ///< 高さ(ピクセル)。
    std::vector<std::uint32_t> pixels;  ///< 主メモリの画像(width*height個)。GPUのコマでは空。
    Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;  ///< GPUのNV12テクスチャ。主メモリのコマではnullptr。
    DXGI_COLOR_SPACE_TYPE colorSpace = DXGI_COLOR_SPACE_YCBCR_STUDIO_G22_LEFT_P709;  ///< textureの色の解釈。

    /**
     * @brief GPUのメモリ上のコマかを返す。
     * @return GPUのテクスチャを持っていればtrue。
     */
    bool onGpu() const { return texture != nullptr; }

    /**
     * @brief このコマが使うメモリのバイト数を返す(キャッシュの上限の計算に使う)。
     * @return バイト数。
     */
    std::size_t bytes() const {
        return onGpu() ? static_cast<std::size_t>(width) * height * 3 / 2 : pixels.size() * sizeof(std::uint32_t);
    }
};

}  // namespace frameplayer
