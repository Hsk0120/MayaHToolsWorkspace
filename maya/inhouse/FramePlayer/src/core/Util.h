/**
 * @file Util.h
 * @brief 複数のファイルで使う小さな関数(高精度タイマー、パスの扱い)。
 */
#pragma once

#include <windows.h>

#include <string>

namespace frameplayer {

/**
 * @brief QueryPerformanceCounterの現在値を返す。
 * @return 高精度タイマーの値。PC全体で共通の時刻なので、別のスレッドやプロセスの値と比べられる。
 */
inline LONGLONG nowTicks() {
    LARGE_INTEGER value;
    QueryPerformanceCounter(&value);
    return value.QuadPart;
}

/**
 * @brief QueryPerformanceCounterの1秒あたりの値を返す。
 * @return 1秒あたりの値。起動中は変わらないので、最初の1回だけ調べて覚えておく。
 */
inline LONGLONG ticksPerSecond() {
    static const LONGLONG frequency = [] {
        LARGE_INTEGER value;
        QueryPerformanceFrequency(&value);
        return value.QuadPart;
    }();
    return frequency;
}

/**
 * @brief パスからファイル名部分を取り出す。
 * @param path ファイルのパス。
 * @return 最後の区切り文字(\ または /)より後ろ。
 */
inline std::wstring fileNameOf(const std::wstring& path) {
    const std::size_t pos = path.find_last_of(L"\\/");
    return pos == std::wstring::npos ? path : path.substr(pos + 1);
}

}  // namespace frameplayer
