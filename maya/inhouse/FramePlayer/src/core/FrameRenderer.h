/**
 * @file FrameRenderer.h
 * @brief コマの縮小・YUVからRGBへの変換・画面に合わせた出力を、自前のシェーダーで行う。
 */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <wrl/client.h>

#include <memory>

#include "core/ColorInfo.h"
#include "core/Frame.h"

namespace frameplayer {

/**
 * @brief コマをGPUで描くための変換をまとめたもの。
 * @note Windowsの映像処理(Video Processor)やGPUのドライバーの映像の補正を通さず、規格どおりの式で変換する。
 *       変換は2段に分ける。
 *       1. prepare(): YUVをRGBへ戻す(色の解釈の行列・範囲・色の位置)。動画の色域・伝達関数のままの値を、
 *          コマと同じ大きさの16bit浮動小数点の画像に置く。表示するコマが変わったときだけ行う。
 *       2. present(): 表示の大きさへ拡大縮小し、色域・明るさを画面に合わせて描画先へ出す。
 *       1つのインスタンスを複数のスレッドから同時に使ってはならない。呼び出し元はGPUの鍵をかけておくこと
 *       (共有のデバイスでは、デバイスの即時コンテキストの状態を他のスレッドと共有するため)。
 */
class FrameRenderer {
public:
    /** @brief 描画先への出し方。 */
    enum class Output {
        Direct8,   ///< 値をそのまま8bitの描画先へ出す(SDR・BT.709の動画をSDRの画面に。ちょうど8bitの値は変わらない)。
        ScRgb,     ///< リニアな値(scRGB。1.0が80cd/m²)を16bit浮動小数点の描画先へ出す。
        Encoded8,  ///< 画面の色域・明るさに合わせたうえでsRGBの値にして8bitの描画先へ出す(scRGBが使えないとき)。
    };

    /** @brief 表示先の画面の状態。 */
    struct DisplayState {
        bool hdr = false;            ///< WindowsのHDRが有効な画面か。
        float sdrWhiteNits = 80.0f;  ///< HDRの画面で、SDRの白を出す明るさ(Windowsの設定)。SDRの画面では使わない。
    };

    /** @brief RGBへ戻した画像(prepare()の結果)。表示枠ごとに持ち、同じコマなら作り直さない。 */
    struct Image {
        Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;        ///< 16bit浮動小数点のRGB(ミップマップ付き)。
        Microsoft::WRL::ComPtr<ID3D11ShaderResourceView> view;  ///< 読むための窓口。
        Microsoft::WRL::ComPtr<ID3D11RenderTargetView> target;  ///< 書くための窓口(最も大きい段)。
        int width = 0;                                          ///< 幅(画素)。
        int height = 0;                                         ///< 高さ(画素)。
        std::shared_ptr<const Frame> source;                    ///< 元のコマ(保持して取り違えを防ぐ)。
        ColorInfo color;                                        ///< 変換に使った色の解釈。

        /**
         * @brief 描ける画像を持っているかを返す。
         * @return 持っていればtrue。
         */
        bool valid() const { return view != nullptr; }
    };

    /**
     * @brief シェーダーなどを作る。
     * @param device 使うデバイス(機能レベル10.0以上)。
     * @return 作れた場合true。
     */
    bool create(ID3D11Device* device);

    /**
     * @brief GPUのNV12・P010のテクスチャを縮小し、明るさと色の面を別々のテクスチャにしてoutへ入れる。
     * @param context 即時コンテキスト。
     * @param source 元のテクスチャ(シェーダーから読める指定で作ったもの)。
     * @param layout 元の並び(Nv12かP010)。
     * @param width 元の幅(偶数)。
     * @param height 元の高さ(偶数)。
     * @param siting 色の画素の位置。縮小後も同じ位置の決まりになるように読む。
     * @param targetWidth 縮小後の幅(偶数)。
     * @param targetHeight 縮小後の高さ(偶数)。
     * @param out 格納先(texture・chroma・layout・大きさを設定する)。
     * @return 成功ならtrue。
     */
    bool downscale(ID3D11DeviceContext* context, ID3D11Texture2D* source, PixelLayout layout, int width, int height,
                   ChromaSiting siting, int targetWidth, int targetHeight, Frame& out);

    /**
     * @brief コマをRGBへ戻してimageへ置く。同じコマと色の解釈なら何もしない。
     * @param context 即時コンテキスト。
     * @param frame 表示するコマ(主メモリでもGPUでもよい)。
     * @param color 当てはめる色の解釈(手動の指定を含む)。
     * @param image 格納先。前回の画像を使い回す。
     * @return 成功ならtrue。
     */
    bool prepare(ID3D11DeviceContext* context, const std::shared_ptr<const Frame>& frame, const ColorInfo& color,
                 Image& image);

    /**
     * @brief imageを表示の大きさへ拡大縮小し、画面に合わせて描画先へ描く。
     * @param context 即時コンテキスト。
     * @param target 描画先。
     * @param dest 描画先の中の表示する範囲(画素)。
     * @param image prepare()の結果。
     * @param output 出し方。
     * @param display 画面の状態。
     */
    void present(ID3D11DeviceContext* context, ID3D11RenderTargetView* target, const RECT& dest, const Image& image,
                 Output output, const DisplayState& display);

    /**
     * @brief 動画を描画先へどう出すかを決める。
     * @param color 動画の色の解釈。
     * @param display 画面の状態。
     * @param scRgbTarget 描画先が16bit浮動小数点(scRGB)ならtrue。
     * @return 出し方。
     */
    static Output chooseOutput(const ColorInfo& color, const DisplayState& display, bool scRgbTarget);

    /**
     * @brief 動画を正しく出すのに16bit浮動小数点(scRGB)の描画先が要るかを返す。
     * @param color 動画の色の解釈。
     * @param display 画面の状態。
     * @return HDRの動画・BT.709以外の色域・10bitの動画ならtrue。SDR・BT.709の8bitならfalse
     *         (HDRの画面でも、SDRの値は8bitの描画先に出せばWindowsが他のSDRのアプリと同じく画面に合わせる)。
     */
    static bool needsScRgb(const ColorInfo& color, const DisplayState& display);

private:
    /**
     * @brief 全画面の三角形を描く準備(頂点・シェーダー以外の状態)をして描く。
     * @param context 即時コンテキスト。
     * @param pixelShader 使うピクセルシェーダー。
     * @param target 描画先。
     * @param viewport 描画先の中の範囲。
     */
    void drawFullscreen(ID3D11DeviceContext* context, ID3D11PixelShader* pixelShader, ID3D11RenderTargetView* target,
                        const D3D11_VIEWPORT& viewport);

    /**
     * @brief 定数バッファーへ値を書く。
     * @param context 即時コンテキスト。
     * @param data 書く値。
     * @param bytes バイト数(16の倍数、kConstantBytes以下)。
     */
    void writeConstants(ID3D11DeviceContext* context, const void* data, UINT bytes);

    static constexpr UINT kConstantBytes = 256;  ///< 定数バッファーの大きさ(どのシェーダーの定数より大きい)。

    Microsoft::WRL::ComPtr<ID3D11Device> device_;
    Microsoft::WRL::ComPtr<ID3D11VertexShader> vertexShader_;
    Microsoft::WRL::ComPtr<ID3D11PixelShader> downscaleShader_;
    Microsoft::WRL::ComPtr<ID3D11PixelShader> convertShader_;
    Microsoft::WRL::ComPtr<ID3D11PixelShader> presentShader_;
    Microsoft::WRL::ComPtr<ID3D11SamplerState> linearSampler_;
    Microsoft::WRL::ComPtr<ID3D11Buffer> constants_;
};

}  // namespace frameplayer
