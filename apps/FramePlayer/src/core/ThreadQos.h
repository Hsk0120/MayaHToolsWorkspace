/**
 * @file ThreadQos.h
 * @brief 裏で動くスレッドの優先度と省電力の扱いを切り替える小さな関数。
 */
#pragma once

#include <windows.h>

namespace frameplayer {

/**
 * @brief 呼び出したスレッドを、ほかのアプリの邪魔をしない「裏の作業」として扱うかを切り替える。
 * @param background trueなら低い優先度(CPU・ファイル読み込み・メモリの優先度)と省電力(EcoQoS)にする。
 *                   falseなら通常に戻す。
 * @note Windowsの決まりで、優先度の切り替えは対象のスレッド自身が行う必要がある。
 *       省電力の扱いにすると、Intelの第12世代以降では主に効率コア(Eコア)で動き、MayaやUnreal Engineが
 *       使う性能コアを空けやすい。対応していないWindowsでは何もしない(失敗しても動作に支障はない)。
 */
inline void setBackgroundWork(bool background) {
    SetThreadPriority(GetCurrentThread(), background ? THREAD_MODE_BACKGROUND_BEGIN : THREAD_MODE_BACKGROUND_END);
    THREAD_POWER_THROTTLING_STATE state{};
    state.Version = THREAD_POWER_THROTTLING_CURRENT_VERSION;
    state.ControlMask = THREAD_POWER_THROTTLING_EXECUTION_SPEED;
    state.StateMask = background ? THREAD_POWER_THROTTLING_EXECUTION_SPEED : 0;
    SetThreadInformation(GetCurrentThread(), ThreadPowerThrottling, &state, sizeof(state));
}

}  // namespace frameplayer
