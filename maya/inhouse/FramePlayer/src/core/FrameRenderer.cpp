/**
 * @file FrameRenderer.cpp
 * @brief コマの縮小・変換・出力の実装。
 */
#include "core/FrameRenderer.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <iterator>

// fxcがビルド時に作るシェーダーのバイトコード(src/core/shaders/FrameShaders.hlsl)。
#include "PSConvert.h"
#include "PSDownscale.h"
#include "PSPresent.h"
#include "VSFullscreen.h"

using Microsoft::WRL::ComPtr;

namespace frameplayer {

namespace {

/// HDRの基準の白の明るさ(cd/m²、ITU-R BT.2408)。SDRの画面ではこれをSDRの白(1.0)にする。
constexpr float kReferenceWhiteNits = 203.0f;
/// 最大の明るさの指定が無いHDRの動画で仮定する明るさ(cd/m²)。
constexpr float kDefaultHdrPeakNits = 1000.0f;

/** @brief PSDownscaleの定数(HLSLのDownscaleParamsと同じ並び)。 */
struct DownscaleConstants {
    float scale[2];
    float bias[2];
    float sourceSize[2];
    int taps[2];
};

/** @brief PSConvertの定数(HLSLのConvertParamsと同じ並び)。 */
struct ConvertConstants {
    float rows[12];
    float chromaOffset[2];
    float chromaSize[2];
    int isRgb;
    int pad[3];
};

/** @brief PSPresentの定数(HLSLのPresentParamsと同じ並び)。 */
struct PresentConstants {
    float gamut[12];
    float imageSize[2];
    float destOrigin[2];
    float step[2];
    float lod;
    int upscale;
    int transfer;
    int output;
    float sdrScale;
    float hdrScale;
    float sourcePeakPq;
    float maxLum;
    float kneeStart;
    float referenceWhite;
};

static_assert(sizeof(DownscaleConstants) % 16 == 0, "定数は16バイト単位");
static_assert(sizeof(ConvertConstants) % 16 == 0, "定数は16バイト単位");
static_assert(sizeof(PresentConstants) % 16 == 0, "定数は16バイト単位");

/**
 * @brief 明るさ(cd/m²)をPQの信号にする(SMPTE ST 2084)。
 * @param nits 明るさ。
 * @return 信号(0〜1)。
 */
double nitsToPq(double nits) {
    const double m1 = 2610.0 / 16384.0;
    const double m2 = 2523.0 / 4096.0 * 128.0;
    const double c1 = 3424.0 / 4096.0;
    const double c2 = 2413.0 / 4096.0 * 32.0;
    const double c3 = 2392.0 / 4096.0 * 32.0;
    const double y = std::pow(std::max(nits, 0.0) / 10000.0, m1);
    return std::pow((c1 + c2 * y) / (1.0 + c3 * y), m2);
}

/**
 * @brief 色の画素の位置を、明るさの画素の単位の(横, 縦)で返す。
 * @param siting 色の画素の位置。
 * @param x 横の格納先。
 * @param y 縦の格納先。
 */
void chromaOffset(ChromaSiting siting, float& x, float& y) {
    x = siting == ChromaSiting::Center ? 0.5f : 0.0f;
    y = siting == ChromaSiting::TopLeft ? 0.0f : 0.5f;
}

/**
 * @brief テクスチャの読む窓口を作る。
 * @param device デバイス。
 * @param texture 対象のテクスチャ。
 * @param format 窓口の形式(NV12・P010なら、形式で明るさの面か色の面かが決まる)。
 * @param view 格納先。
 * @return 成功ならtrue。
 */
bool createView(ID3D11Device* device, ID3D11Texture2D* texture, DXGI_FORMAT format, ComPtr<ID3D11ShaderResourceView>& view) {
    D3D11_SHADER_RESOURCE_VIEW_DESC desc{};
    desc.Format = format;
    desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
    desc.Texture2D.MipLevels = 1;
    return SUCCEEDED(device->CreateShaderResourceView(texture, &desc, view.ReleaseAndGetAddressOf()));
}

/**
 * @brief 1つの面のテクスチャを作る(描画先にも、読む元にもできる)。
 * @param device デバイス。
 * @param width 幅。
 * @param height 高さ。
 * @param format 形式。
 * @param data 初めの値(主メモリの面)。nullptrなら描画先として作る。
 * @param pitch dataの1行のバイト数。
 * @param texture 格納先。
 * @return 成功ならtrue。
 */
bool createPlane(ID3D11Device* device, int width, int height, DXGI_FORMAT format, const void* data, UINT pitch,
                 ComPtr<ID3D11Texture2D>& texture) {
    D3D11_TEXTURE2D_DESC desc{};
    desc.Width = static_cast<UINT>(width);
    desc.Height = static_cast<UINT>(height);
    desc.MipLevels = 1;
    desc.ArraySize = 1;
    desc.Format = format;
    desc.SampleDesc.Count = 1;
    desc.Usage = data ? D3D11_USAGE_IMMUTABLE : D3D11_USAGE_DEFAULT;
    desc.BindFlags = D3D11_BIND_SHADER_RESOURCE | (data ? 0u : static_cast<UINT>(D3D11_BIND_RENDER_TARGET));
    D3D11_SUBRESOURCE_DATA initial{data, pitch, 0};
    return SUCCEEDED(device->CreateTexture2D(&desc, data ? &initial : nullptr, texture.ReleaseAndGetAddressOf()));
}

}  // namespace

bool FrameRenderer::create(ID3D11Device* device) {
    device_ = device;
    HRESULT hr = device->CreateVertexShader(g_VSFullscreen, sizeof(g_VSFullscreen), nullptr, &vertexShader_);
    if (SUCCEEDED(hr)) {
        hr = device->CreatePixelShader(g_PSDownscale, sizeof(g_PSDownscale), nullptr, &downscaleShader_);
    }
    if (SUCCEEDED(hr)) {
        hr = device->CreatePixelShader(g_PSConvert, sizeof(g_PSConvert), nullptr, &convertShader_);
    }
    if (SUCCEEDED(hr)) {
        hr = device->CreatePixelShader(g_PSPresent, sizeof(g_PSPresent), nullptr, &presentShader_);
    }
    if (SUCCEEDED(hr)) {
        D3D11_SAMPLER_DESC sampler{};
        sampler.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sampler.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.MaxLOD = D3D11_FLOAT32_MAX;
        hr = device->CreateSamplerState(&sampler, &linearSampler_);
    }
    if (SUCCEEDED(hr)) {
        D3D11_BUFFER_DESC buffer{};
        buffer.ByteWidth = kConstantBytes;
        buffer.Usage = D3D11_USAGE_DYNAMIC;
        buffer.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        buffer.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        hr = device->CreateBuffer(&buffer, nullptr, &constants_);
    }
    return SUCCEEDED(hr);
}

void FrameRenderer::writeConstants(ID3D11DeviceContext* context, const void* data, UINT bytes) {
    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (SUCCEEDED(context->Map(constants_.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped))) {
        std::memcpy(mapped.pData, data, std::min(bytes, kConstantBytes));
        context->Unmap(constants_.Get(), 0);
    }
}

void FrameRenderer::drawFullscreen(ID3D11DeviceContext* context, ID3D11PixelShader* pixelShader,
                                   ID3D11RenderTargetView* target, const D3D11_VIEWPORT& viewport) {
    // 他の描画(Direct2Dや他のスレッド)が変えた状態に左右されないよう、使う状態はすべて設定する。
    context->IASetInputLayout(nullptr);
    context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    context->VSSetShader(vertexShader_.Get(), nullptr, 0);
    context->PSSetShader(pixelShader, nullptr, 0);
    ID3D11Buffer* buffers[] = {constants_.Get()};
    context->PSSetConstantBuffers(0, 1, buffers);
    ID3D11SamplerState* samplers[] = {linearSampler_.Get()};
    context->PSSetSamplers(0, 1, samplers);
    context->RSSetState(nullptr);
    context->OMSetBlendState(nullptr, nullptr, 0xFFFFFFFF);
    context->OMSetDepthStencilState(nullptr, 0);
    context->OMSetRenderTargets(1, &target, nullptr);
    context->RSSetViewports(1, &viewport);
    context->Draw(3, 0);
    // 描画先と読む元を外しておく(次に同じテクスチャを逆の役で使うときの食い違いを防ぐ)。
    ID3D11ShaderResourceView* noViews[2] = {};
    context->PSSetShaderResources(0, 2, noViews);
    context->OMSetRenderTargets(0, nullptr, nullptr);
}

bool FrameRenderer::downscale(ID3D11DeviceContext* context, ID3D11Texture2D* source, PixelLayout layout, int width,
                              int height, ChromaSiting siting, int targetWidth, int targetHeight, Frame& out) {
    const bool p010 = layout == PixelLayout::P010;
    const DXGI_FORMAT lumaFormat = p010 ? DXGI_FORMAT_R16_UNORM : DXGI_FORMAT_R8_UNORM;
    const DXGI_FORMAT chromaFormat = p010 ? DXGI_FORMAT_R16G16_UNORM : DXGI_FORMAT_R8G8_UNORM;
    ComPtr<ID3D11ShaderResourceView> lumaSource;
    ComPtr<ID3D11ShaderResourceView> chromaSource;
    ComPtr<ID3D11Texture2D> luma;
    ComPtr<ID3D11Texture2D> chroma;
    ComPtr<ID3D11RenderTargetView> lumaTarget;
    ComPtr<ID3D11RenderTargetView> chromaTarget;
    if (!createView(device_.Get(), source, lumaFormat, lumaSource) ||
        !createView(device_.Get(), source, chromaFormat, chromaSource) ||
        !createPlane(device_.Get(), targetWidth, targetHeight, lumaFormat, nullptr, 0, luma) ||
        !createPlane(device_.Get(), targetWidth / 2, targetHeight / 2, chromaFormat, nullptr, 0, chroma) ||
        FAILED(device_->CreateRenderTargetView(luma.Get(), nullptr, &lumaTarget)) ||
        FAILED(device_->CreateRenderTargetView(chroma.Get(), nullptr, &chromaTarget))) {
        return false;
    }

    // 明るさの面: 先の画素の中心(n+0.5)を、元の画素の座標へ比例で移す。
    // 色の面: 色の画素は明るさの単位で2i+offsetの位置にあるので、縮小後も同じ決まりになる位置を読む。
    //   元の色の面の座標 = 先の座標×倍率 + (offset - 0.5)(倍率 - 1)/2(左寄せ以外の向きも同じ式)。
    float offsetX, offsetY;
    chromaOffset(siting, offsetX, offsetY);
    struct Pass {
        ID3D11ShaderResourceView* source;
        ID3D11RenderTargetView* target;
        int sourceWidth, sourceHeight, targetWidth, targetHeight;
        bool chroma;
    } passes[] = {
        {lumaSource.Get(), lumaTarget.Get(), width, height, targetWidth, targetHeight, false},
        {chromaSource.Get(), chromaTarget.Get(), width / 2, height / 2, targetWidth / 2, targetHeight / 2, true},
    };
    for (const Pass& pass : passes) {
        DownscaleConstants constants{};
        constants.scale[0] = static_cast<float>(pass.sourceWidth) / pass.targetWidth;
        constants.scale[1] = static_cast<float>(pass.sourceHeight) / pass.targetHeight;
        constants.bias[0] = pass.chroma ? (offsetX - 0.5f) * (constants.scale[0] - 1.0f) / 2.0f : 0.0f;
        constants.bias[1] = pass.chroma ? (offsetY - 0.5f) * (constants.scale[1] - 1.0f) / 2.0f : 0.0f;
        constants.sourceSize[0] = static_cast<float>(pass.sourceWidth);
        constants.sourceSize[1] = static_cast<float>(pass.sourceHeight);
        constants.taps[0] = std::clamp(static_cast<int>(std::ceil(constants.scale[0])), 1, 8);
        constants.taps[1] = std::clamp(static_cast<int>(std::ceil(constants.scale[1])), 1, 8);
        writeConstants(context, &constants, sizeof(constants));
        ID3D11ShaderResourceView* views[] = {pass.source};
        context->PSSetShaderResources(0, 1, views);
        const D3D11_VIEWPORT viewport{0.0f, 0.0f, static_cast<float>(pass.targetWidth),
                                      static_cast<float>(pass.targetHeight), 0.0f, 1.0f};
        drawFullscreen(context, downscaleShader_.Get(), pass.target, viewport);
    }
    out.width = targetWidth;
    out.height = targetHeight;
    out.layout = layout;
    out.pixels.clear();
    out.planes.clear();
    out.texture = std::move(luma);
    out.chroma = std::move(chroma);
    return true;
}

bool FrameRenderer::prepare(ID3D11DeviceContext* context, const std::shared_ptr<const Frame>& frame,
                            const ColorInfo& color, Image& image) {
    if (!frame || frame->width <= 0 || frame->height <= 0) {
        return false;
    }
    if (image.valid() && image.source == frame && image.color.sameRendering(color)) {
        return true;
    }

    // 読む元の窓口を用意する。主メモリのコマは、その場でGPUへ写す。
    const bool p010 = frame->layout == PixelLayout::P010;
    const DXGI_FORMAT lumaFormat = p010 ? DXGI_FORMAT_R16_UNORM : DXGI_FORMAT_R8_UNORM;
    const DXGI_FORMAT chromaFormat = p010 ? DXGI_FORMAT_R16G16_UNORM : DXGI_FORMAT_R8G8_UNORM;
    ComPtr<ID3D11ShaderResourceView> plane0;
    ComPtr<ID3D11ShaderResourceView> plane1;
    if (frame->layout == PixelLayout::Yuy2) {
        // YUY2は「Y0 U Y1 V」の4バイトを1テクセル(RGBA)として、幅/2のテクスチャに置く。
        ComPtr<ID3D11Texture2D> texture;
        if (frame->onGpu() || frame->planes.size() < static_cast<std::size_t>(frame->width) * frame->height * 2 ||
            !createPlane(device_.Get(), frame->width / 2, frame->height, DXGI_FORMAT_R8G8B8A8_UNORM,
                         frame->planes.data(), static_cast<UINT>(frame->width) * 2, texture) ||
            !createView(device_.Get(), texture.Get(), DXGI_FORMAT_R8G8B8A8_UNORM, plane0)) {
            return false;
        }
    } else if (!frame->isYuv()) {
        ComPtr<ID3D11Texture2D> texture;
        if (frame->pixels.size() < static_cast<std::size_t>(frame->width) * frame->height ||
            !createPlane(device_.Get(), frame->width, frame->height, DXGI_FORMAT_B8G8R8A8_UNORM, frame->pixels.data(),
                         static_cast<UINT>(frame->width) * 4, texture) ||
            !createView(device_.Get(), texture.Get(), DXGI_FORMAT_B8G8R8A8_UNORM, plane0)) {
            return false;
        }
    } else if (frame->onGpu()) {
        // 1枚のNV12・P010なら形式で面を選び、縮小した2枚のテクスチャならそれぞれを読む。
        ID3D11Texture2D* chroma = frame->chroma ? frame->chroma.Get() : frame->texture.Get();
        if (!createView(device_.Get(), frame->texture.Get(), lumaFormat, plane0) ||
            !createView(device_.Get(), chroma, chromaFormat, plane1)) {
            return false;
        }
    } else {
        const std::size_t valueBytes = p010 ? 2 : 1;
        const std::size_t lumaBytes = static_cast<std::size_t>(frame->width) * frame->height * valueBytes;
        if (frame->planes.size() < lumaBytes * 3 / 2) {
            return false;
        }
        const UINT pitch = static_cast<UINT>(frame->width * valueBytes);
        ComPtr<ID3D11Texture2D> luma;
        ComPtr<ID3D11Texture2D> chroma;
        if (!createPlane(device_.Get(), frame->width, frame->height, lumaFormat, frame->planes.data(), pitch, luma) ||
            !createPlane(device_.Get(), frame->width / 2, frame->height / 2, chromaFormat,
                         frame->planes.data() + lumaBytes, pitch, chroma) ||
            !createView(device_.Get(), luma.Get(), lumaFormat, plane0) ||
            !createView(device_.Get(), chroma.Get(), chromaFormat, plane1)) {
            return false;
        }
    }

    // 結果の画像(大きさが変わったときだけ作り直す)。縮小して表示するときのためにミップマップを持つ。
    if (!image.texture || image.width != frame->width || image.height != frame->height) {
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = static_cast<UINT>(frame->width);
        desc.Height = static_cast<UINT>(frame->height);
        desc.MipLevels = 0;  // 1×1まで全部。
        desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_R16G16B16A16_FLOAT;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DEFAULT;
        desc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
        desc.MiscFlags = D3D11_RESOURCE_MISC_GENERATE_MIPS;
        image = Image{};
        if (FAILED(device_->CreateTexture2D(&desc, nullptr, &image.texture)) ||
            FAILED(device_->CreateShaderResourceView(image.texture.Get(), nullptr, &image.view))) {
            image = Image{};
            return false;
        }
        D3D11_RENDER_TARGET_VIEW_DESC targetDesc{};
        targetDesc.Format = desc.Format;
        targetDesc.ViewDimension = D3D11_RTV_DIMENSION_TEXTURE2D;
        if (FAILED(device_->CreateRenderTargetView(image.texture.Get(), &targetDesc, &image.target))) {
            image = Image{};
            return false;
        }
        image.width = frame->width;
        image.height = frame->height;
    }

    ConvertConstants constants{};
    if (frame->isYuv()) {
        yuvToRgbMatrix(color, p010, constants.rows);
    }
    chromaOffset(color.siting, constants.chromaOffset[0], constants.chromaOffset[1]);
    constants.chromaSize[0] = static_cast<float>(frame->width / 2);
    constants.chromaSize[1] = static_cast<float>(frame->layout == PixelLayout::Yuy2 ? frame->height : frame->height / 2);
    constants.isRgb = frame->layout == PixelLayout::Yuy2 ? 2 : frame->isYuv() ? 0 : 1;
    writeConstants(context, &constants, sizeof(constants));
    ID3D11ShaderResourceView* views[] = {plane0.Get(), plane1.Get()};
    context->PSSetShaderResources(0, 2, views);
    const D3D11_VIEWPORT viewport{0.0f, 0.0f, static_cast<float>(frame->width), static_cast<float>(frame->height),
                                  0.0f, 1.0f};
    drawFullscreen(context, convertShader_.Get(), image.target.Get(), viewport);
    context->GenerateMips(image.view.Get());
    image.source = frame;
    image.color = color;
    return true;
}

void FrameRenderer::present(ID3D11DeviceContext* context, ID3D11RenderTargetView* target, const RECT& dest,
                            const Image& image, Output output, const DisplayState& display) {
    const int destWidth = dest.right - dest.left;
    const int destHeight = dest.bottom - dest.top;
    if (!image.valid() || destWidth <= 0 || destHeight <= 0) {
        return;
    }
    PresentConstants constants{};
    float gamut[9];
    gamutToBt709(image.color.primaries, gamut);
    for (int i = 0; i < 3; ++i) {
        std::copy(gamut + i * 3, gamut + i * 3 + 3, constants.gamut + i * 4);
    }
    constants.imageSize[0] = static_cast<float>(image.width);
    constants.imageSize[1] = static_cast<float>(image.height);
    constants.destOrigin[0] = static_cast<float>(dest.left);
    constants.destOrigin[1] = static_cast<float>(dest.top);
    constants.step[0] = static_cast<float>(image.width) / destWidth;
    constants.step[1] = static_cast<float>(image.height) / destHeight;
    const float step = std::max(constants.step[0], constants.step[1]);
    constants.upscale = step <= 1.0f ? 1 : 0;
    constants.lod = step > 1.0f ? std::log2(step) : 0.0f;
    switch (image.color.transfer) {
    case TransferFunction::Linear:
        constants.transfer = 1;
        break;
    case TransferFunction::Pq:
        constants.transfer = 2;
        break;
    case TransferFunction::Hlg:
        constants.transfer = 3;
        break;
    case TransferFunction::Sdr:
    default:
        constants.transfer = 0;
        break;
    }
    constants.output = output == Output::Direct8 ? 0 : output == Output::ScRgb ? 1 : 2;
    constants.sdrScale = (output == Output::ScRgb && display.hdr) ? display.sdrWhiteNits / 80.0f : 1.0f;
    constants.hdrScale = (output == Output::ScRgb && display.hdr) ? 1.0f / 80.0f : 0.0f;
    // HDRをSDRの画面に出すときの曲線(BT.2390のEETF)。基準の白(203cd/m²)を収める先の最大にする。
    const float peak = image.color.maxContentNits > 0.0f ? image.color.maxContentNits : kDefaultHdrPeakNits;
    constants.sourcePeakPq = static_cast<float>(nitsToPq(peak));
    constants.maxLum = static_cast<float>(nitsToPq(kReferenceWhiteNits) / nitsToPq(peak));
    constants.kneeStart = 1.5f * constants.maxLum - 0.5f;
    constants.referenceWhite = kReferenceWhiteNits;
    writeConstants(context, &constants, sizeof(constants));
    ID3D11ShaderResourceView* views[] = {image.view.Get()};
    context->PSSetShaderResources(0, 1, views);
    const D3D11_VIEWPORT viewport{static_cast<float>(dest.left), static_cast<float>(dest.top),
                                  static_cast<float>(destWidth), static_cast<float>(destHeight), 0.0f, 1.0f};
    drawFullscreen(context, presentShader_.Get(), target, viewport);
}

bool FrameRenderer::needsScRgb(const ColorInfo& color, const DisplayState&) {
    // SDR・BT.709の8bitは、HDRの画面でも8bitの描画先でよい(他のSDRのアプリと同じく、Windowsが画面に合わせる)。
    return !color.isPassThrough() || color.bitDepth > 8;
}

FrameRenderer::Output FrameRenderer::chooseOutput(const ColorInfo& color, const DisplayState& display,
                                                  bool scRgbTarget) {
    if (scRgbTarget) {
        return Output::ScRgb;
    }
    (void)display;
    return color.isPassThrough() ? Output::Direct8 : Output::Encoded8;
}

}  // namespace frameplayer
