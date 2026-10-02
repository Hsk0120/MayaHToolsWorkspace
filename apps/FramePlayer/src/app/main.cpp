/**
 * @file main.cpp
 * @brief FramePlayerの起動処理。
 */
#include <windows.h>
#include <objbase.h>
#include <shellapi.h>

#include "app/PlayerWindow.h"

/**
 * @brief アプリの入口。ウィンドウを作り、メッセージループを回す。
 * @param instance アプリのインスタンスハンドル。
 * @param showCommand 初期表示方法。
 * @return 終了コード。
 * @note コマンドライン引数に動画のパスがあれば起動時に開く(2つあれば2つ目を比較用として右に並べる)。
 */
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int showCommand) {
    // 高DPIのモニターでぼやけないよう、モニターごとの拡大率に対応する。
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);

    // Media FoundationはCOMを使うため、このスレッドでCOMを初期化しておく。
    const HRESULT comResult = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    if (FAILED(comResult)) {
        MessageBoxW(nullptr, L"COMを初期化できません", L"FramePlayer", MB_OK | MB_ICONERROR);
        return 1;
    }

    int exitCode = 0;
    {
        frameplayer::PlayerWindow window;
        if (!window.create(instance, showCommand)) {
            MessageBoxW(nullptr, L"ウィンドウを作成できません", L"FramePlayer", MB_OK | MB_ICONERROR);
            exitCode = 1;
        } else {
            int argc = 0;
            LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
            if (argv) {
                if (argc > 1) {
                    window.openClip(argv[1]);
                }
                if (argc > 2) {
                    window.openCompare(argv[2]);  // 2つ目は比較用として右に並べる。
                }
                LocalFree(argv);
            }

            MSG message;
            while (GetMessageW(&message, nullptr, 0, 0) > 0) {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
            exitCode = static_cast<int>(message.wParam);
        }
    }
    CoUninitialize();
    return exitCode;
}
