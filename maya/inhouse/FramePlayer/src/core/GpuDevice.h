/**
 * @file GpuDevice.h
 * @brief デコード・キャッシュ・描画で共有するGPU(Direct3D 11)のデバイス。
 */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <mfapi.h>
#include <mfidl.h>
#include <wrl/client.h>

#include <cstddef>
#include <memory>

#include "core/Frame.h"

namespace frameplayer {

/**
 * @brief デコード(Media Foundation)・キャッシュ・描画(Direct2D)が同じGPUのテクスチャを使えるよう、1つのデバイスを共有する。
 * @note 複数のスレッド(裏の読み込み・描画)から使うので、Direct3Dの複数スレッド保護を有効にしてある。
 *       さらに、一連のGPU処理(デコード1回、描画1回など)が他のスレッドの処理と混ざらないよう、
 *       使う側はlock()で囲む。
 */
class GpuDevice {
public:
    /**
     * @brief GPUのデバイスを作る。
     * @return 作れた場合はデバイス。GPUが無い(リモート接続の一部やVM等)などで作れなければnullptr。
     */
    static std::shared_ptr<GpuDevice> create();

    /** @brief Media Foundationの利用を終了する(create()で開始した分と対になる)。 */
    ~GpuDevice();

    GpuDevice(const GpuDevice&) = delete;
    GpuDevice& operator=(const GpuDevice&) = delete;

    /**
     * @brief Direct3D 11のデバイスを返す。
     * @return デバイス。
     */
    ID3D11Device* device() const { return device_.Get(); }

    /**
     * @brief Media Foundationへ渡すためのデバイス管理役を返す。
     * @return 管理役。
     */
    IMFDXGIDeviceManager* manager() const { return manager_.Get(); }

    /**
     * @brief NV12(動画本来の形式。1画素1.5バイト)のテクスチャをキャッシュと描画に使えるかを返す。
     * @return 使えればtrue。
     */
    bool supportsNv12() const { return supportsNv12_; }

    /**
     * @brief P010(10bitの動画の形式)のテクスチャをキャッシュと描画に使えるかを返す。
     * @return 使えればtrue。
     */
    bool supportsP010() const { return supportsP010_; }

    /**
     * @brief GPUのメモリのうち、このアプリが使ってよい量の目安を返す(Windowsが示す予算)。
     * @return バイト数。分からなければ0。
     */
    std::size_t localMemoryBudget() const;

    /**
     * @brief 一連のGPU処理を他のスレッドと混ざらないように囲む鍵。lock()の戻り値が生きている間は他のスレッドを待たせる。
     * @return 鍵を外すまでの間有効なオブジェクト。
     * @note 鍵の本体はDirect3Dの複数スレッド保護(ID3D10Multithread)で、同じスレッドからは重ねてかけられる。
     *       裏の読み込み(デコード1回分)と描画(1回分)の両方をこの鍵で囲み、互いに待ち合わせる。
     */
    class Lock {
    public:
        /**
         * @brief 鍵をかける。
         * @param multithread 鍵の本体。
         */
        explicit Lock(ID3D10Multithread* multithread) : multithread_(multithread) { multithread_->Enter(); }
        /** @brief 鍵を外す。 */
        ~Lock() { multithread_->Leave(); }
        Lock(const Lock&) = delete;
        Lock& operator=(const Lock&) = delete;

    private:
        ID3D10Multithread* multithread_;
    };

    /**
     * @brief 鍵をかける。
     * @return 鍵。破棄すると外れる。
     */
    Lock lock() const { return Lock(multithread_.Get()); }

    /**
     * @brief 鍵をかけ、ポインターで返す(かけるかどうかを条件で選ぶときに使う)。
     * @return 鍵。破棄すると外れる。
     */
    std::unique_ptr<Lock> lockPtr() const { return std::make_unique<Lock>(multithread_.Get()); }

private:
    GpuDevice() = default;

    Microsoft::WRL::ComPtr<ID3D11Device> device_;
    Microsoft::WRL::ComPtr<ID3D10Multithread> multithread_;
    Microsoft::WRL::ComPtr<IMFDXGIDeviceManager> manager_;
    bool supportsNv12_ = false;
    bool supportsP010_ = false;
    bool started_ = false;  ///< MFStartup()に成功したか。
};

}  // namespace frameplayer
