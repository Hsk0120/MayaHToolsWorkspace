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

    // NV12・P010のテクスチャを作れて、描画で読める(シェーダーで標本化できる)か。
    auto supports = [&gpu](DXGI_FORMAT format) {
        UINT support = 0;
        return SUCCEEDED(gpu->device_->CheckFormatSupport(format, &support)) &&
               (support & D3D11_FORMAT_SUPPORT_TEXTURE2D) && (support & D3D11_FORMAT_SUPPORT_SHADER_SAMPLE);
    };
    gpu->supportsNv12_ = supports(DXGI_FORMAT_NV12);
    gpu->supportsP010_ = supports(DXGI_FORMAT_P010);
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
