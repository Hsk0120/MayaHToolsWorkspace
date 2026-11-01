/** @file bridge.cpp
 * @brief Mayaのコマンドを使わない、PySide統合テスト専用入口。製品配布には含めない。
 */
#include "native_browser.h"
#include <QApplication>
#include <QWidget>
#include <csignal>
#include <cstdlib>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <DbgHelp.h>

namespace {
HANDLE crashFile = INVALID_HANDLE_VALUE;
/** @brief 隔離テストのabortでスタックを保存する。 @param signalNumber シグナル。 */
void logAbort(int signalNumber) {
    CONTEXT context{};
    RtlCaptureContext(&context);
    EXCEPTION_RECORD record{};
    record.ExceptionCode = 0xC0000409;
    EXCEPTION_POINTERS pointers{&record, &context};
    MINIDUMP_EXCEPTION_INFORMATION info{GetCurrentThreadId(), &pointers, FALSE};
    MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), crashFile, MiniDumpNormal, &info, nullptr, nullptr);
    CloseHandle(crashFile);
    std::_Exit(signalNumber + 128);
}
}

/** @brief 製品では使わないテスト用クラッシュ記録。 @param path 出力先。 */
extern "C" __declspec(dllexport) void qpeTestAbortLog(const wchar_t* path) {
    crashFile = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    std::signal(SIGABRT, logAbort);
}

/** @brief 同じQtランタイムの生存ウィジェットだけを親にする。
 * @param kind 部品種別。 @param address 親ポインター。 @return 部品ポインター、失敗は0。
 */
extern "C" __declspec(dllexport) quintptr qpeTestCreate(const char* kind, quintptr address) {
    for (auto widget : QApplication::allWidgets())
        if (reinterpret_cast<quintptr>(widget) == address)
            return reinterpret_cast<quintptr>(qpe::createNative(QString::fromUtf8(kind), widget));
    return 0;
}

/** @brief 生存部品とワーカーを確認して安全に終了する。 @return 解除できるか。 */
extern "C" __declspec(dllexport) bool qpeTestReleased() {
    return qpe::nativeObjectsReleased();
}
