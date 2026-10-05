/**
 * @file Frame.h
 * @brief 1コマ分の画像データを表す構造体。
 */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <wrl/client.h>

#include <cstddef>
#include <cstdint>
#include <vector>

#include "core/ColorInfo.h"

namespace frameplayer {

/**
 * @brief 1コマ分の画像。主メモリかGPUのメモリのどちらかに持つ。
 * @note YUVのコマはデコードした値のまま持ち、描画のときに色の解釈(color)に従ってRGBへ戻す
 *       (Windowsの映像処理やGPUのドライバーの補正を通さず、自分のシェーダーで規格どおりに変換するため)。
 *       置き場所は次のどれか1つ:
 *       - pixels: 主メモリのBGRA(Bgra8)。上の行から順に並び、行の間に余白はない。
 *       - planes: 主メモリのYUV(Nv12・P010)。明るさの面(幅×高さ)の後に色の面(幅×高さ/2)が続き、余白はない。
 *         Yuy2は1行に「Y0 U Y1 V」の4バイトが幅/2組並び、余白はない。
 *       - texture: GPUのNV12・P010のテクスチャ(chromaがnullptrのとき)。
 *       - texture + chroma: GPUの明るさの面(R8・R16)と色の面(R8G8・R16G16)の別々のテクスチャ(縮小したコマ)。
 */
struct Frame {
    int width = 0;   ///< 幅(ピクセル)。YUVなら偶数。
    int height = 0;  ///< 高さ(ピクセル)。YUVなら偶数。
    PixelLayout layout = PixelLayout::Bgra8;  ///< 画素の並び。
    std::vector<std::uint32_t> pixels;        ///< 主メモリのBGRA。
    std::vector<std::uint8_t> planes;         ///< 主メモリのYUV。
    Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;  ///< GPUのYUV(1枚)、または明るさの面。
    Microsoft::WRL::ComPtr<ID3D11Texture2D> chroma;   ///< GPUの色の面(明るさと別のテクスチャのとき)。
    ColorInfo color;  ///< 色の解釈(動画の指定・推定。手動の指定は描画のときに当てはめる)。
    float pixelAspect = 1.0f;  ///< 1画素の横÷縦(DVなどの横長・縦長の画素。表示の縦横比に使う)。

    /**
     * @brief GPUのメモリ上のコマかを返す。
     * @return GPUのテクスチャを持っていればtrue。
     */
    bool onGpu() const { return texture != nullptr; }

    /**
     * @brief YUVのコマかを返す。
     * @return NV12・P010・YUY2ならtrue。
     */
    bool isYuv() const { return layout != PixelLayout::Bgra8; }

    /**
     * @brief このコマが使うメモリのバイト数を返す(キャッシュの上限の計算に使う)。
     * @return バイト数。
     */
    std::size_t bytes() const {
        const std::size_t area = static_cast<std::size_t>(width) * height;
        switch (layout) {
        case PixelLayout::Nv12:
            return area * 3 / 2;
        case PixelLayout::P010:
            return area * 3;
        case PixelLayout::Yuy2:
            return area * 2;
        case PixelLayout::Bgra8:
        default:
            return area * 4;
        }
    }
};

}  // namespace frameplayer
