/**
 * @file SyncLog.h
 * @brief 連携の遅れを測るための時刻の記録(環境変数 FRAMEPLAYER_SYNC_LOG にファイルのパスを入れたときだけ)。
 */
#pragma once

#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <mutex>

namespace frameplayer {

/**
 * @brief 連携の命令の送受信と、コマの表示の時刻を1行ずつファイルへ書く。
 * @param format printfと同じ書式(行の内容)。
 * @param ... 書式に渡す値。
 * @note 各行の先頭に、QueryPerformanceCounterの値を秒にした時刻を付ける。この時刻はPC全体で共通なので、
 *       Maya側のPythonの time.perf_counter() と比べて遅れを測れる。環境変数が無ければ何もしない
 *       (最初の1回だけ環境変数を調べる)。複数のスレッドから呼んでよい。
 */
inline void syncLog(const char* format, ...) {
    static std::FILE* file = [] {
        char path[MAX_PATH] = {};
        std::FILE* opened = nullptr;
        if (GetEnvironmentVariableA("FRAMEPLAYER_SYNC_LOG", path, MAX_PATH) > 0) {
            fopen_s(&opened, path, "w");
        }
        return opened;
    }();
    if (!file) {
        return;
    }
    static std::mutex mutex;
    static const double frequency = [] {
        LARGE_INTEGER value;
        QueryPerformanceFrequency(&value);
        return static_cast<double>(value.QuadPart);
    }();
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    std::lock_guard<std::mutex> lock(mutex);
    std::fprintf(file, "%.6f ", static_cast<double>(now.QuadPart) / frequency);
    va_list args;
    va_start(args, format);
    std::vfprintf(file, format, args);
    va_end(args);
    std::fputc('\n', file);
    std::fflush(file);
}

}  // namespace frameplayer
