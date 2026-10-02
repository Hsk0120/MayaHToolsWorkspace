/**
 * @file GpuDevice.cpp
 * @brief 共有するGPUデバイスの実装。
 */
#include "core/GpuDevice.h"

#include <dxgi1_4.h>

#include <algorithm>
#include <iterator>

using Microsoft::WRL::ComPtr;

namespace frameplayer {

std::shared_ptr<GpuDevice> GpuDevice::create() {
    std::shared_ptr<GpuDevice> gpu(new GpuDevice());
    if (FAILED(MFStartup(MF_VERSION, MFSTARTUP_LITE))) {
        return nullptr;
    }
    gpu->started_ = true;

    // 動画のデコード(VIDEO_SUPPORT)とDirect2Dでの描画(BGRA_SUPPORT)の両方に使えるデバイスを作る。
    static const D3D_FEATURE_LEVEL levels[] = {D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_1,
                                               D3D_FEATURE_LEVEL_10_0};
    HRESULT hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
                                   D3D11_CREATE_DEVICE_VIDEO_SUPPORT | D3D11_CREATE_DEVICE_BGRA_SUPPORT, levels,
                                   static_cast<UINT>(std::size(levels)), D3D11_SDK_VERSION, &gpu->device_, nullptr,
                                   nullptr);
    if (SUCCEEDED(hr)) {
        hr = gpu->device_.As(&gpu->multithread_);
    }
    if (FAILED(hr)) {
        return nullptr;
    }
    // 裏の読み込みスレッドと描画スレッドから使うので、Direct3Dの呼び出しを1つずつ排他にする。
    gpu->multithread_->SetMultithreadProtected(TRUE);

    UINT resetToken = 0;
    hr = MFCreateDXGIDeviceManager(&resetToken, &gpu->manager_);
    if (SUCCEEDED(hr)) {
        hr = gpu->manager_->ResetDevice(gpu->device_.Get(), resetToken);
    }
    if (FAILED(hr)) {
        return nullptr;
    }

    // NV12のテクスチャを作れて、描画で読める(シェーダーで標本化できる)か。
    UINT support = 0;
    gpu->supportsNv12_ = SUCCEEDED(gpu->device_->CheckFormatSupport(DXGI_FORMAT_NV12, &support)) &&
                         (support & D3D11_FORMAT_SUPPORT_TEXTURE2D) && (support & D3D11_FORMAT_SUPPORT_SHADER_SAMPLE);
    return gpu;
}

GpuDevice::~GpuDevice() {
    manager_.Reset();  // MFShutdownより先に解放する。
    multithread_.Reset();
    device_.Reset();
    if (started_) {
        MFShutdown();
    }
}

bool GpuDevice::readBack(const Frame& frame, Frame& out) const {
    if (!frame.onGpu()) {
        return false;
    }
    D3D11_TEXTURE2D_DESC desc{};
    frame.texture->GetDesc(&desc);
    desc.Usage = D3D11_USAGE_STAGING;
    desc.BindFlags = 0;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    desc.MiscFlags = 0;
    ComPtr<ID3D11Texture2D> staging;
    if (FAILED(device_->CreateTexture2D(&desc, nullptr, &staging))) {
        return false;
    }
    ComPtr<ID3D11DeviceContext> context;
    device_->GetImmediateContext(&context);
    auto guard = lock();
    context->CopyResource(staging.Get(), frame.texture.Get());
    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (FAILED(context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) {
        return false;
    }
    // NV12: 明るさ(Y)の面が高さ分並び、その後に縦横半分の色(U,Vの交互)の面が続く。
    // BT.709・映像用の範囲(16〜235)としてRGBへ変換する(確認用なので色の厳密さは求めない)。
    const auto* base = static_cast<const std::uint8_t*>(mapped.pData);
    const std::uint8_t* uvPlane = base + static_cast<std::size_t>(mapped.RowPitch) * desc.Height;
    out = Frame{};
    out.width = frame.width;
    out.height = frame.height;
    out.pixels.resize(static_cast<std::size_t>(out.width) * out.height);
    for (int y = 0; y < out.height; ++y) {
        const std::uint8_t* yRow = base + static_cast<std::size_t>(mapped.RowPitch) * y;
        const std::uint8_t* uvRow = uvPlane + static_cast<std::size_t>(mapped.RowPitch) * (y / 2);
        for (int x = 0; x < out.width; ++x) {
            const float c = (yRow[x] - 16) * 1.164f;
            const float u = uvRow[(x & ~1)] - 128.0f;
            const float v = uvRow[(x & ~1) + 1] - 128.0f;
            const auto clampByte = [](float value) {
                return static_cast<std::uint32_t>(std::clamp(value, 0.0f, 255.0f));
            };
            const std::uint32_t r = clampByte(c + 1.793f * v);
            const std::uint32_t g = clampByte(c - 0.213f * u - 0.533f * v);
            const std::uint32_t b = clampByte(c + 2.112f * u);
            out.pixels[static_cast<std::size_t>(y) * out.width + x] = 0xFF000000u | (r << 16) | (g << 8) | b;
        }
    }
    context->Unmap(staging.Get(), 0);
    return true;
}

std::size_t GpuDevice::localMemoryBudget() const {
    ComPtr<IDXGIDevice> dxgiDevice;
    ComPtr<IDXGIAdapter> adapter;
    ComPtr<IDXGIAdapter3> adapter3;
    if (FAILED(device_.As(&dxgiDevice)) || FAILED(dxgiDevice->GetAdapter(&adapter)) || FAILED(adapter.As(&adapter3))) {
        return 0;
    }
    DXGI_QUERY_VIDEO_MEMORY_INFO info{};
    if (FAILED(adapter3->QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL, &info))) {
        return 0;
    }
    return static_cast<std::size_t>(info.Budget);
}

}  // namespace frameplayer
