/**
 * @file TraceLog.h
 * @brief 処理時間や連携の遅れを測るための時刻の記録(環境変数 FRAMEPLAYER_TRACE_LOG にファイルのパスを入れたときだけ)。
 */
#pragma once

#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <mutex>

#include "core/Util.h"

namespace frameplayer {

/**
 * @brief 測りたい出来事(連携の命令の送受信、コマの表示、動画を開く各段階など)の時刻を1行ずつファイルへ書く。
 * @param format printfと同じ書式(行の内容)。
 * @param ... 書式に渡す値。
 * @note 各行の先頭に、QueryPerformanceCounterの値を秒にした時刻を付ける。この時刻はPC全体で共通なので、
 *       Maya側のPythonの time.perf_counter() と比べて遅れを測れる。環境変数が無ければ何もしない
 *       (最初の1回だけ環境変数を調べる)。複数のスレッドから呼んでよい。
 */
inline void traceLog(const char* format, ...) {
    static std::FILE* file = [] {
        char path[MAX_PATH] = {};
        std::FILE* opened = nullptr;
        // FRAMEPLAYER_SYNC_LOGは以前の名前(連携の測定だけに使っていたころ)。
        if (GetEnvironmentVariableA("FRAMEPLAYER_TRACE_LOG", path, MAX_PATH) > 0 ||
            GetEnvironmentVariableA("FRAMEPLAYER_SYNC_LOG", path, MAX_PATH) > 0) {
            fopen_s(&opened, path, "w");
        }
        return opened;
    }();
    if (!file) {
        return;
    }
    static std::mutex mutex;
    const double seconds = static_cast<double>(nowTicks()) / static_cast<double>(ticksPerSecond());
    std::lock_guard<std::mutex> lock(mutex);
    std::fprintf(file, "%.6f ", seconds);
    va_list args;
    va_start(args, format);
    std::vfprintf(file, format, args);
    va_end(args);
    std::fputc('\n', file);
    std::fflush(file);
}

}  // namespace frameplayer
