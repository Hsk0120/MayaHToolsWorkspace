/**
 * @file verify_frame_index.cpp
 * @brief コマ番号が正確に読めているかを確かめる確認用ツール。
 *
 * README記載の手順で作る確認用動画は、各コマの中央の帯に「コマ番号の2進数」を
 * 縦縞(左が最下位ビット、白=1・黒=0)で描いてある。上端は白、下端は黒の帯。
 * プレイヤーと同じClip(目次・キャッシュ・裏での先読み)で、次の3通りの順番に全コマを取り出し、
 * 取り出したコマの縞がコマ番号を表しているかを確かめる。上下の帯で上下反転していないことも確かめる。
 *   - 先頭から順に(順再生・→キー)
 *   - 末尾から逆順に(逆再生・←キー)
 *   - ランダムな位置へ飛びながら(スライダー操作)
 * キャッシュの上限を小さくすると、捨てたコマの読み直しやシークも確かめられる。
 *
 * 使い方: FramePlayerVerify.exe <動画> [期待するコマ数] [--bits 縦縞の本数] [--cache-mb 上限MB] [--max-width 幅]
 *         [--limit N](先頭からN・末尾からN・ランダムNだけ確かめる) [--cpu](GPUを使わない) [--no-check](番号を確かめず速さだけ測る)
 * YUVのコマ(GPUのメモリ・主メモリ)は、主メモリへ読み出し、色の解釈に従ってBGRAにしてから縞を読む。
 * 終了コード: 0=全コマ一致、1=不一致あり、2=読み込み失敗や引数の誤り。
 */
#include <windows.h>
#include <d3d11.h>
#include <objbase.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <random>
#include <string>
#include <thread>
#include <vector>

#include "core/Clip.h"
#include "core/ColorInfo.h"
#include "core/GpuDevice.h"

namespace {

/**
 * @brief 指定位置周辺の明るさの平均を返す。
 * @param frame 対象のコマ。
 * @param cx 中心のx座標。
 * @param cy 中心のy座標。
 * @return 0〜255の明るさ。
 */
int brightnessAt(const frameplayer::Frame& frame, int cx, int cy) {
    int sum = 0;
    int count = 0;
    for (int y = cy - 2; y <= cy + 2; ++y) {
        for (int x = cx - 2; x <= cx + 2; ++x) {
            if (x < 0 || y < 0 || x >= frame.width || y >= frame.height) {
                continue;
            }
            const std::uint32_t p = frame.pixels[static_cast<size_t>(y) * frame.width + x];
            sum += static_cast<int>(((p >> 16) & 0xFF) + ((p >> 8) & 0xFF) + (p & 0xFF)) / 3;
            ++count;
        }
    }
    return count ? sum / count : 0;
}

/**
 * @brief GPUのテクスチャの1つの面を主メモリへ読み出し、余白なしで並べてoutの後ろに足す。
 * @param gpu デバイス。
 * @param texture 読み出すテクスチャ。
 * @param rowBytes 1行のバイト数。
 * @param rows 読む行数。
 * @param firstRow NV12・P010の1枚のテクスチャで色の面を読むときは、明るさの面の行数(読み出した先で飛ばす行数)。
 * @param out 格納先。
 * @return 成功ならtrue。
 */
bool readPlane(const frameplayer::GpuDevice& gpu, ID3D11Texture2D* texture, std::size_t rowBytes, int rows,
               int firstRow, std::vector<std::uint8_t>& out) {
    D3D11_TEXTURE2D_DESC desc{};
    texture->GetDesc(&desc);
    desc.Usage = D3D11_USAGE_STAGING;
    desc.BindFlags = 0;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    desc.MiscFlags = 0;
    Microsoft::WRL::ComPtr<ID3D11Texture2D> staging;
    if (FAILED(gpu.device()->CreateTexture2D(&desc, nullptr, &staging))) {
        return false;
    }
    Microsoft::WRL::ComPtr<ID3D11DeviceContext> context;
    gpu.device()->GetImmediateContext(&context);
    auto guard = gpu.lock();
    context->CopyResource(staging.Get(), texture);
    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (FAILED(context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) {
        return false;
    }
    const auto* base = static_cast<const std::uint8_t*>(mapped.pData) + static_cast<std::size_t>(mapped.RowPitch) * firstRow;
    for (int y = 0; y < rows; ++y) {
        const std::uint8_t* row = base + static_cast<std::size_t>(mapped.RowPitch) * y;
        out.insert(out.end(), row, row + rowBytes);
    }
    context->Unmap(staging.Get(), 0);
    return true;
}

/**
 * @brief コマを主メモリのBGRAの画像にする(縞を読むため)。
 * @param gpu GPUのコマを読み出すデバイス。GPUを使わないならnullptr。
 * @param frame コマ。
 * @param out 格納先。
 * @return 成功ならtrue。
 */
bool toBgra(const frameplayer::GpuDevice* gpu, const frameplayer::Frame& frame, frameplayer::Frame& out) {
    if (!frame.isYuv()) {
        out = frame;
        return true;
    }
    const bool p010 = frame.layout == frameplayer::PixelLayout::P010;
    std::vector<std::uint8_t> planes;
    if (frame.onGpu()) {
        if (!gpu) {
            return false;
        }
        // 1枚のNV12・P010なら、色の面は明るさの面の直後の行にある。縮小したコマは2枚に分かれている。
        const std::size_t rowBytes = static_cast<std::size_t>(frame.width) * (p010 ? 2 : 1);
        ID3D11Texture2D* chroma = frame.chroma ? frame.chroma.Get() : frame.texture.Get();
        if (!readPlane(*gpu, frame.texture.Get(), rowBytes, frame.height, 0, planes) ||
            !readPlane(*gpu, chroma, rowBytes, frame.height / 2, frame.chroma ? 0 : frame.height, planes)) {
            return false;
        }
    }
    const std::vector<std::uint8_t>& source = frame.onGpu() ? planes : frame.planes;
    out = frameplayer::Frame{};
    out.width = frame.width;
    out.height = frame.height;
    out.color = frame.color;
    out.pixels.resize(static_cast<std::size_t>(frame.width) * frame.height);
    frameplayer::convertPlanesToBgra(source.data(), frame.width, frame.height, frame.layout, frame.color, frame.width,
                                     frame.height, out.pixels.data());
    return true;
}

/**
 * @brief コマに描かれたコマ番号を読み取る。
 * @param frame 対象のコマ。
 * @param bits 縦縞の本数。
 * @return 読み取った番号。上下の帯が想定と違う(反転など)場合は-1。
 */
int readIndex(const frameplayer::Frame& frame, int bits) {
    if (brightnessAt(frame, frame.width / 2, frame.height / 16) < 128 ||
        brightnessAt(frame, frame.width / 2, frame.height * 15 / 16) >= 128) {
        return -1;
    }
    int value = 0;
    for (int bit = 0; bit < bits; ++bit) {
        const int x = (2 * bit + 1) * frame.width / (2 * bits);
        if (brightnessAt(frame, x, frame.height / 2) >= 128) {
            value |= 1 << bit;
        }
    }
    return value;
}

/**
 * @brief 指定した順番で全コマを取り出し、番号の不一致を数える。
 * @param clip 対象の動画。
 * @param gpu GPUのコマを読み出すためのデバイス。GPUを使わないならnullptr。
 * @param order 取り出すコマ番号の順番。
 * @param direction 先読みの向き。
 * @param bits 縦縞の本数。
 * @param check 縞を読んで番号を確かめるか。falseなら取り出せたかだけを見る(速さの測定用)。
 * @param name 表示用の名前。
 * @return 不一致(取り出せなかったコマを含む)の数。
 */
int runOrder(frameplayer::Clip& clip, const frameplayer::GpuDevice* gpu, const std::vector<int>& order,
             frameplayer::Clip::Direction direction, int bits, bool check, const wchar_t* name) {
    const auto start = std::chrono::steady_clock::now();
    int mismatches = 0;
    for (int index : order) {
        const auto frame = clip.waitForFrame(index, direction, 20000);
        int found = -2;
        if (frame && !check) {
            found = index % (1 << bits);  // 速さだけを測るときは縞を読まない(取り出せたかだけを見る)。
        } else if (frame) {
            frameplayer::Frame rgb;
            found = toBgra(gpu, *frame, rgb) ? readIndex(rgb, bits) : -3;
        }
        if (found != (index % (1 << bits))) {
            if (mismatches < 10) {
                std::wprintf(L"  %ls mismatch: frame %d reads as %d%ls\n", name, index, found,
                             frame ? L"" : L" (not available)");
            }
            ++mismatches;
        }
    }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::wprintf(L"%-8ls frames=%zu mismatches=%d time=%.2fs (%.0f frames/s)\n", name, order.size(), mismatches,
                 seconds, order.size() / seconds);
    return mismatches;
}

}  // namespace

/**
 * @brief 確認用ツールの入口。
 * @param argc 引数の数。
 * @param argv 引数。
 * @return 終了コード(ファイル冒頭を参照)。
 */
int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        std::fwprintf(stderr,
                      L"usage: FramePlayerVerify.exe <video> [expectedFrames] [--bits N] [--cache-mb MB] "
                      L"[--max-width W] [--limit N] [--cpu] [--no-check] [--thumbnails]\n");
        return 2;
    }
    int expected = -1;
    int bits = 12;
    long long cacheMb = 4096;
    int maxWidth = 1280;
    int limit = -1;
    bool useGpu = true;
    bool check = true;
    bool thumbnails = false;
    for (int i = 2; i < argc; ++i) {
        if (std::wcscmp(argv[i], L"--bits") == 0 && i + 1 < argc) {
            bits = _wtoi(argv[++i]);
        } else if (std::wcscmp(argv[i], L"--cache-mb") == 0 && i + 1 < argc) {
            cacheMb = _wtoi64(argv[++i]);
        } else if (std::wcscmp(argv[i], L"--max-width") == 0 && i + 1 < argc) {
            maxWidth = _wtoi(argv[++i]);
        } else if (std::wcscmp(argv[i], L"--limit") == 0 && i + 1 < argc) {
            limit = _wtoi(argv[++i]);
        } else if (std::wcscmp(argv[i], L"--cpu") == 0) {
            useGpu = false;
        } else if (std::wcscmp(argv[i], L"--no-check") == 0) {
            check = false;
        } else if (std::wcscmp(argv[i], L"--thumbnails") == 0) {
            thumbnails = true;
        } else {
            expected = _wtoi(argv[i]);
        }
    }
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) {
        std::fwprintf(stderr, L"COM initialization failed\n");
        return 2;
    }

    int result = 0;
    {
        const std::shared_ptr<frameplayer::GpuDevice> gpu = useGpu ? frameplayer::GpuDevice::create() : nullptr;
        frameplayer::Clip clip;
        std::wstring error;
        const auto openStart = std::chrono::steady_clock::now();
        const std::size_t cacheBytes = static_cast<std::size_t>(cacheMb) << 20;
        if (!clip.open(argv[1], maxWidth, cacheBytes, cacheBytes, gpu, {}, error)) {
            std::fwprintf(stderr, L"load failed: %ls\n", error.c_str());
            result = 2;
        } else {
            const double openSeconds =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - openStart).count();
            const int count = clip.frameCount();
            const auto first = clip.frame(0);
            std::wprintf(L"frames=%d fps=%.3f size=%dx%d open=%.2fs cache=%lldMB [%ls]\n", count, clip.frameRate(),
                         first ? first->width : 0, first ? first->height : 0, openSeconds, cacheMb,
                         clip.description().c_str());
            if (expected >= 0 && count != expected) {
                std::wprintf(L"frame count differs: expected %d\n", expected);
                result = 1;
            }

            // --limitを付けると、先頭からN・末尾からN・ランダムNだけを確かめる(長い動画用)。
            const int span = limit > 0 ? std::min(limit, count) : count;
            std::vector<int> forward(static_cast<size_t>(span));
            std::vector<int> backward(static_cast<size_t>(span));
            for (int i = 0; i < span; ++i) {
                forward[static_cast<size_t>(i)] = i;
                backward[static_cast<size_t>(i)] = count - 1 - i;
            }
            std::vector<int> random;
            std::mt19937 generator(12345);
            std::uniform_int_distribution<int> pick(0, count - 1);
            for (int i = 0; i < std::min(count, limit > 0 ? limit : 300); ++i) {
                random.push_back(pick(generator));
            }

            int mismatches = 0;
            if (thumbnails) {
                // キーフレームの縮小画像を作らせ、各画像に描かれた番号がそのキーフレームの番号と一致するかを見る。
                const auto thumbStart = std::chrono::steady_clock::now();
                clip.startThumbnails(320, std::size_t{160} << 20);
                int done = 0;
                int total = 0;
                std::size_t bytes = 0;
                while (!clip.thumbnailProgress(done, total, bytes)) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
                }
                const double thumbSeconds =
                    std::chrono::duration<double>(std::chrono::steady_clock::now() - thumbStart).count();
                int checked = 0;
                int wrong = 0;
                int lastIndex = -1;
                for (int i = 0; i < count; ++i) {
                    int imageIndex = -1;
                    const auto preview = clip.preview(i, &imageIndex);
                    if (!preview || imageIndex == lastIndex) {
                        continue;
                    }
                    lastIndex = imageIndex;
                    ++checked;
                    const int read = check ? readIndex(*preview, bits) : imageIndex;
                    if (read != imageIndex) {
                        if (++wrong <= 10) {
                            std::wprintf(L"  thumbnail mismatch: keyframe %d reads as %d\n", imageIndex, read);
                        }
                    }
                }
                std::wprintf(L"thumbnails done=%d/%d checked=%d mismatches=%d bytes=%.1fMB time=%.2fs\n", done, total,
                             checked, wrong, bytes / 1048576.0, thumbSeconds);
                mismatches += wrong;
            }
            mismatches += runOrder(clip, gpu.get(), forward, frameplayer::Clip::Direction::Forward, bits, check, L"forward");
            mismatches += runOrder(clip, gpu.get(), backward, frameplayer::Clip::Direction::Backward, bits, check, L"backward");
            mismatches += runOrder(clip, gpu.get(), random, frameplayer::Clip::Direction::Forward, bits, check, L"random");
            if (!clip.error().empty()) {
                std::wprintf(L"error: %ls\n", clip.error().c_str());
            }
            if (mismatches > 0) {
                result = 1;
            }
            std::wprintf(result == 0 ? L"OK\n" : L"FAILED\n");
        }
    }
    CoUninitialize();
    return result;
}
