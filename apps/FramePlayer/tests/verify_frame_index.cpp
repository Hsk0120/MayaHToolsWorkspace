/**
 * @file verify_frame_index.cpp
 * @brief コマ番号が正確に読めているかを確かめる確認用ツール。
 *
 * README記載の手順で作る確認用動画は、各コマの中央の帯に「コマ番号の2進数」を
 * 縦縞(左が最下位ビット、白=1・黒=0)で描いてある。上端は白、下端は黒の帯。
 * プレイヤーと同じClip::load()で読み込み、n番目に保持したコマの縞がnを表しているかを全コマ確認する。
 * 上下の帯で上下反転していないことも確かめる。
 *
 * 使い方: FramePlayerVerify.exe <動画> [期待するコマ数] [保持する最大幅(0なら縮小しない)]
 * 終了コード: 0=全コマ一致、1=不一致あり、2=読み込み失敗や引数の誤り。
 */
#include <windows.h>
#include <objbase.h>

#include <cstdio>
#include <cstdlib>
#include <string>

#include "core/Clip.h"

namespace {

constexpr int kBits = 12;          ///< 縦縞の本数(表せるコマ番号は0〜4095)。
constexpr int kDefaultMaxWidth = 1280;  ///< 既定ではプレイヤーと同じ縮小幅で確かめる。

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
 * @brief コマに描かれたコマ番号を読み取る。
 * @param frame 対象のコマ。
 * @return 読み取った番号。上下の帯が想定と違う(反転など)場合は-1。
 */
int readIndex(const frameplayer::Frame& frame) {
    if (brightnessAt(frame, frame.width / 2, frame.height / 16) < 128 ||
        brightnessAt(frame, frame.width / 2, frame.height * 15 / 16) >= 128) {
        return -1;
    }
    int value = 0;
    for (int bit = 0; bit < kBits; ++bit) {
        const int x = (2 * bit + 1) * frame.width / (2 * kBits);
        if (brightnessAt(frame, x, frame.height / 2) >= 128) {
            value |= 1 << bit;
        }
    }
    return value;
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
        std::fwprintf(stderr, L"usage: FramePlayerVerify.exe <video> [expectedFrames] [maxWidth]\n");
        return 2;
    }
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) {
        std::fwprintf(stderr, L"COM initialization failed\n");
        return 2;
    }

    int result = 0;
    {
        frameplayer::Clip clip;
        std::wstring error;
        const int maxWidth = argc >= 4 ? _wtoi(argv[3]) : kDefaultMaxWidth;
        if (!clip.load(argv[1], maxWidth, {}, error)) {
            std::fwprintf(stderr, L"load failed: %ls\n", error.c_str());
            result = 2;
        } else {
            int mismatches = 0;
            for (int i = 0; i < clip.frameCount(); ++i) {
                const int found = readIndex(clip.frame(i));
                if (found != (i % (1 << kBits))) {
                    if (mismatches < 20) {
                        std::wprintf(L"mismatch: frame %d reads as %d\n", i, found);
                    }
                    ++mismatches;
                }
            }
            std::wprintf(L"frames=%d fps=%.3f size=%dx%d mismatches=%d\n", clip.frameCount(), clip.frameRate(),
                         clip.frame(0).width, clip.frame(0).height, mismatches);
            if (argc >= 3 && clip.frameCount() != _wtoi(argv[2])) {
                std::wprintf(L"frame count differs: expected %d\n", _wtoi(argv[2]));
                result = 1;
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
