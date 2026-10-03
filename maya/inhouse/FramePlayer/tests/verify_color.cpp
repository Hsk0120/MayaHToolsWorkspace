/**
 * @file verify_color.cpp
 * @brief 色の正確さを確かめる確認用ツール(FramePlayerColorCheck、配布対象外)。
 *
 * tests/make_color_testdata.py で作った動画と期待値(expected.txt)を読み、プレイヤーと同じ読み込み・変換
 * (MediaFoundationSource・FrameRenderer)で各動画の最初のコマを等倍で描いて、パッチの中央の値を期待値と比べる。
 * 表示の状態は「SDRの画面」と「HDRの画面(SDRの白200cd/m²)」の2通りを、画面を使わずに描いて確かめる。
 *
 * 使い方: FramePlayerColorCheck <確認用動画のフォルダ> [--cpu] [--max-width N] [--only ファイル名]
 *   --cpu        GPUを使わずにデコードする(描画はGPU)。
 *   --max-width  キャッシュする画像の最大幅(既定は0=縮小しない)。縮小の処理も確かめられる。
 * 終了コード: 0=すべて一致、1=不一致あり、2=読み込み失敗。
 */
#include <windows.h>
#include <d3d11.h>
#include <fcntl.h>
#include <io.h>
#include <objbase.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cwchar>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "core/ColorInfo.h"
#include "core/FrameRenderer.h"
#include "core/FrameSource.h"
#include "core/GpuDevice.h"

using Microsoft::WRL::ComPtr;
using namespace frameplayer;

namespace {

/** @brief 1本の動画の期待値。 */
struct Expected {
    std::string file;       ///< ファイル名。
    std::string matrix;     ///< 期待する行列の名前。
    std::string range;      ///< 期待する範囲の名前。
    std::string primaries;  ///< 期待する色域の名前。
    std::string transfer;   ///< 期待する伝達関数の名前。
    int bits = 8;           ///< 期待するビット数。
    std::vector<std::array<float, 3>> sdr;  ///< SDRの画面での各パッチの値(sRGBの値)。
    std::vector<std::array<float, 3>> hdr;  ///< HDRの画面での各パッチの値(scRGB)。
};

/**
 * @brief 期待値のファイルを読む。
 * @param path expected.txtのパス。
 * @param columns パッチの列数の格納先。
 * @param rows パッチの行数の格納先。
 * @return 動画ごとの期待値。
 */
std::vector<Expected> readExpected(const std::wstring& path, int& columns, int& rows) {
    std::vector<Expected> videos;
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        std::istringstream fields(line);
        std::string kind;
        fields >> kind;
        if (kind == "grid") {
            fields >> columns >> rows;
        } else if (kind == "video") {
            Expected video;
            fields >> video.file >> video.matrix >> video.range >> video.primaries >> video.transfer >> video.bits;
            videos.push_back(video);
        } else if ((kind == "sdr" || kind == "hdr") && !videos.empty()) {
            int index = 0;
            std::array<float, 3> rgb{};
            fields >> index >> rgb[0] >> rgb[1] >> rgb[2];
            (kind == "sdr" ? videos.back().sdr : videos.back().hdr).push_back(rgb);
        }
    }
    return videos;
}

const char* nameOf(ColorMatrix value) {
    switch (value) {
    case ColorMatrix::Bt601:
        return "bt601";
    case ColorMatrix::Bt2020:
        return "bt2020";
    case ColorMatrix::Smpte240m:
        return "smpte240m";
    case ColorMatrix::Fcc:
        return "fcc";
    default:
        return "bt709";
    }
}

const char* nameOf(ColorRange value) { return value == ColorRange::Full ? "full" : "limited"; }

const char* nameOf(ColorPrimaries value) {
    switch (value) {
    case ColorPrimaries::Bt601_525:
        return "smpte170m";
    case ColorPrimaries::Bt601_625:
        return "bt470bg";
    case ColorPrimaries::Bt2020:
        return "bt2020";
    case ColorPrimaries::DisplayP3:
        return "displayp3";
    case ColorPrimaries::DciP3:
        return "dcip3";
    default:
        return "bt709";
    }
}

const char* nameOf(TransferFunction value) {
    switch (value) {
    case TransferFunction::Linear:
        return "linear";
    case TransferFunction::Pq:
        return "pq";
    case TransferFunction::Hlg:
        return "hlg";
    default:
        return "sdr";
    }
}

/**
 * @brief 16bit浮動小数点の値を32bitの浮動小数点にする。
 * @param half 16bitの値。
 * @return 値。
 */
float halfToFloat(std::uint16_t half) {
    const int sign = (half >> 15) & 1;
    const int exponent = (half >> 10) & 0x1F;
    const int mantissa = half & 0x3FF;
    float value;
    if (exponent == 0) {
        value = std::ldexp(static_cast<float>(mantissa), -24);
    } else if (exponent == 31) {
        value = mantissa ? NAN : INFINITY;
    } else {
        value = std::ldexp(static_cast<float>(mantissa + 1024), exponent - 25);
    }
    return sign ? -value : value;
}


float linearToSrgb(float v) {
    v = std::clamp(v, 0.0f, 1.0f);
    return v <= 0.0031308f ? v * 12.92f : 1.055f * std::pow(v, 1.0f / 2.4f) - 0.055f;
}

/**
 * @brief scRGBの値をPQの信号にする(明るさの差を見た目に近い尺度で比べるため)。
 * @param scRgb scRGBの値(1.0が80cd/m²)。
 * @return PQの信号。0.5cd/m²以下(負も含む)は0.5cd/m²とみなす(黒に近い成分のわずかな差は見えないため)。
 */
float scRgbToPq(float scRgb) {
    const double m1 = 2610.0 / 16384.0;
    const double m2 = 2523.0 / 4096.0 * 128.0;
    const double c1 = 3424.0 / 4096.0;
    const double c2 = 2413.0 / 4096.0 * 32.0;
    const double c3 = 2392.0 / 4096.0 * 32.0;
    const double y = std::pow(std::max(scRgb * 80.0, 0.5) / 10000.0, m1);
    return static_cast<float>(std::pow((c1 + c2 * y) / (1.0 + c3 * y), m2));
}

/**
 * @brief コマを等倍で描き、描画先の画素を主メモリへ読み出す。
 * @param device デバイス。
 * @param renderer 変換と描画。
 * @param frame コマ。
 * @param color 色の解釈。
 * @param display 画面の状態。
 * @param pixels 各画素のRGB(描画先の値のまま。8bitなら0〜1、scRGBならそのまま)の格納先。
 * @param scRgb 描画先がscRGBだったかの格納先。
 * @return 成功ならtrue。
 */
bool render(ID3D11Device* device, FrameRenderer& renderer, const std::shared_ptr<const Frame>& frame,
            const ColorInfo& color, const FrameRenderer::DisplayState& display, std::vector<std::array<float, 3>>& pixels,
            bool& scRgb) {
    ComPtr<ID3D11DeviceContext> context;
    device->GetImmediateContext(&context);
    scRgb = FrameRenderer::needsScRgb(color, display);
    D3D11_TEXTURE2D_DESC desc{};
    desc.Width = static_cast<UINT>(frame->width);
    desc.Height = static_cast<UINT>(frame->height);
    desc.MipLevels = 1;
    desc.ArraySize = 1;
    desc.Format = scRgb ? DXGI_FORMAT_R16G16B16A16_FLOAT : DXGI_FORMAT_B8G8R8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.Usage = D3D11_USAGE_DEFAULT;
    desc.BindFlags = D3D11_BIND_RENDER_TARGET;
    ComPtr<ID3D11Texture2D> target;
    ComPtr<ID3D11RenderTargetView> view;
    if (FAILED(device->CreateTexture2D(&desc, nullptr, &target)) ||
        FAILED(device->CreateRenderTargetView(target.Get(), nullptr, &view))) {
        return false;
    }
    FrameRenderer::Image image;
    if (!renderer.prepare(context.Get(), frame, color, image)) {
        return false;
    }
    renderer.present(context.Get(), view.Get(), RECT{0, 0, frame->width, frame->height}, image,
                     FrameRenderer::chooseOutput(color, display, scRgb), display);
    desc.Usage = D3D11_USAGE_STAGING;
    desc.BindFlags = 0;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    ComPtr<ID3D11Texture2D> staging;
    if (FAILED(device->CreateTexture2D(&desc, nullptr, &staging))) {
        return false;
    }
    context->CopyResource(staging.Get(), target.Get());
    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (FAILED(context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) {
        return false;
    }
    pixels.resize(static_cast<std::size_t>(frame->width) * frame->height);
    for (int y = 0; y < frame->height; ++y) {
        const auto* row = static_cast<const std::uint8_t*>(mapped.pData) + static_cast<std::size_t>(mapped.RowPitch) * y;
        for (int x = 0; x < frame->width; ++x) {
            std::array<float, 3>& out = pixels[static_cast<std::size_t>(y) * frame->width + x];
            if (scRgb) {
                const auto* half = reinterpret_cast<const std::uint16_t*>(row) + x * 4;
                out = {halfToFloat(half[0]), halfToFloat(half[1]), halfToFloat(half[2])};
            } else {
                const std::uint8_t* p = row + x * 4;  // B, G, R, A
                out = {p[2] / 255.0f, p[1] / 255.0f, p[0] / 255.0f};
            }
        }
    }
    context->Unmap(staging.Get(), 0);
    return true;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        std::fwprintf(stderr, L"使い方: FramePlayerColorCheck <確認用動画のフォルダ> [--cpu] [--max-width N] [--only ファイル名]\n");
        return 2;
    }
    // 日本語をそのまま出せるよう、標準出力をUTF-8にする。
    _setmode(_fileno(stdout), _O_U8TEXT);
    const HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const std::wstring folder = argv[1];
    bool cpu = false;
    int maxWidth = 0;
    std::wstring only;
    for (int i = 2; i < argc; ++i) {
        if (std::wcscmp(argv[i], L"--cpu") == 0) {
            cpu = true;
        } else if (std::wcscmp(argv[i], L"--max-width") == 0 && i + 1 < argc) {
            maxWidth = _wtoi(argv[++i]);
        } else if (std::wcscmp(argv[i], L"--only") == 0 && i + 1 < argc) {
            only = argv[++i];
        }
    }
    int columns = 8;
    int rows = 4;
    const std::vector<Expected> videos = readExpected(folder + L"\\expected.txt", columns, rows);
    if (videos.empty()) {
        std::fwprintf(stderr, L"期待値を読めません: %ls\\expected.txt\n", folder.c_str());
        return 2;
    }

    // デコードと描画で同じGPUデバイスを使う(プレイヤーと同じ)。--cpuのときは描画用のデバイスだけを作る。
    std::shared_ptr<GpuDevice> gpu = GpuDevice::create();
    ComPtr<ID3D11Device> device;
    if (gpu) {
        device = gpu->device();
    } else if (FAILED(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
                                        &device, nullptr, nullptr))) {
        std::fwprintf(stderr, L"GPUを使えません\n");
        return 2;
    }
    FrameRenderer renderer;
    if (!renderer.create(device.Get())) {
        std::fwprintf(stderr, L"シェーダーを作れません\n");
        return 2;
    }

    bool allPassed = true;
    bool loadFailed = false;
    for (const Expected& video : videos) {
        const std::wstring name(video.file.begin(), video.file.end());
        if (!only.empty() && name != only) {
            continue;
        }
        std::wstring error;
        auto source = openFrameSource(folder + L"\\" + name, maxWidth, cpu ? nullptr : gpu, error);
        Frame decoded;
        int index = -1;
        if (!source || !source->readNext(decoded, index)) {
            std::wprintf(L"%ls: 読み込み失敗 %ls\n", name.c_str(), error.c_str());
            loadFailed = true;
            continue;
        }
        auto frame = std::make_shared<const Frame>(std::move(decoded));
        const ColorInfo& color = frame->color;
        const bool infoOk = video.matrix == nameOf(color.matrix) && video.range == nameOf(color.range) &&
                            video.primaries == nameOf(color.primaries) && video.transfer == nameOf(color.transfer) &&
                            video.bits == color.bitDepth;
        std::wprintf(L"%ls  %ls  %dx%d %ls\n  色の解釈: %ls  [%ls]\n", name.c_str(), source->description().c_str(),
                     frame->width, frame->height, frame->onGpu() ? L"GPU" : L"主メモリ", describeColor(color).c_str(),
                     infoOk ? L"期待どおり" : L"期待と違う");
        allPassed = allPassed && infoOk;

        for (int mode = 0; mode < 2; ++mode) {
            FrameRenderer::DisplayState display;
            display.hdr = mode == 1;
            display.sdrWhiteNits = 200.0f;
            std::vector<std::array<float, 3>> pixels;
            bool scRgb = false;
            bool rendered;
            {
                std::unique_ptr<GpuDevice::Lock> lock;
                if (gpu) {
                    lock = gpu->lockPtr();
                }
                rendered = render(device.Get(), renderer, frame, color, display, pixels, scRgb);
            }
            if (!rendered) {
                std::wprintf(L"  描画失敗\n");
                loadFailed = true;
                continue;
            }
            const auto& expected = mode == 0 ? video.sdr : video.hdr;
            float worst = 0.0f;
            int worstPatch = -1;
            std::array<float, 3> worstGot{}, worstWant{};
            for (int patch = 0; patch < static_cast<int>(expected.size()); ++patch) {
                // パッチの中央の6×6画素の平均(縮小したコマでも、割合で位置を決める)。
                const int cx = static_cast<int>((patch % columns + 0.5) * frame->width / columns);
                const int cy = static_cast<int>((patch / columns + 0.5) * frame->height / rows);
                std::array<float, 3> got{};
                for (int dy = -3; dy < 3; ++dy) {
                    for (int dx = -3; dx < 3; ++dx) {
                        const auto& p = pixels[static_cast<std::size_t>(cy + dy) * frame->width + cx + dx];
                        for (int c = 0; c < 3; ++c) {
                            got[c] += p[c] / 36.0f;
                        }
                    }
                }
                for (int c = 0; c < 3; ++c) {
                    float difference;
                    if (mode == 0) {
                        // SDRの画面: sRGBの値で比べる(scRGBなら画面と同じく範囲外を切ってsRGBにする)。
                        const float value = scRgb ? linearToSrgb(got[c]) : got[c];
                        difference = std::abs(value - expected[static_cast<std::size_t>(patch)][c]) * 255.0f;
                    } else if (!color.isHdr()) {
                        // HDRの画面のSDRの動画: SDRの白の明るさで割ってsRGBの値(8bitの段)で比べる。
                        // 8bitの描画先は、WindowsがsRGBの曲線とSDRの白の明るさで画面に合わせるので値のまま比べる。
                        const float white = display.sdrWhiteNits / 80.0f;
                        const float value = scRgb ? linearToSrgb(got[c] / white) : got[c];
                        const float want = linearToSrgb(expected[static_cast<std::size_t>(patch)][c] / white);
                        difference = std::abs(value - want) * 255.0f;
                    } else {
                        // HDRの画面のHDRの動画: 明るさの差を、見た目に近いPQの尺度で比べる(10bitの1段 = 1/1023)。
                        difference =
                            std::abs(scRgbToPq(got[c]) - scRgbToPq(expected[static_cast<std::size_t>(patch)][c])) *
                            1023.0f;
                    }
                    if (difference > worst) {
                        worst = difference;
                        worstPatch = patch;
                        worstGot = got;
                        worstWant = expected[static_cast<std::size_t>(patch)];
                    }
                }
            }
            // 許す差: SDRの値は8bitで2.5段、HDRの明るさはPQの10bitで4段(圧縮・4:2:0・丸めの分)。
            const bool sdrScale = mode == 0 || !color.isHdr();
            const float limit = sdrScale ? 2.5f : 4.0f;
            const bool passed = worst <= limit;
            allPassed = allPassed && passed;
            std::wprintf(L"  %ls(%ls): 最大の差 %ls%.2f段 %ls", mode == 0 ? L"SDRの画面" : L"HDRの画面",
                         scRgb ? L"scRGB" : L"8bit", sdrScale ? L"8bitで" : L"PQで", worst, passed ? L"OK" : L"NG");
            if (worstPatch >= 0) {
                std::wprintf(L"  (パッチ%d: 結果 %.4f %.4f %.4f / 期待 %.4f %.4f %.4f)", worstPatch, worstGot[0],
                             worstGot[1], worstGot[2], worstWant[0], worstWant[1], worstWant[2]);
            }
            std::wprintf(L"\n");
        }
    }
    std::wprintf(L"%ls\n", loadFailed ? L"FAILED(読み込み失敗あり)" : allPassed ? L"OK" : L"FAILED");
    if (SUCCEEDED(com)) {
        CoUninitialize();
    }
    return loadFailed ? 2 : allPassed ? 0 : 1;
}
