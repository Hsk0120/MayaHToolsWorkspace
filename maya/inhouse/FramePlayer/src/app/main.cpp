/**
 * @file main.cpp
 * @brief FramePlayerの起動処理。
 */
#include <windows.h>
#include <commctrl.h>
#include <objbase.h>
#include <shellapi.h>

// コモンコントロールの新しい版(6)を使う。ツールチップ・入力欄・メッセージボックスが今のWindowsの見た目になる。
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

#include <cwchar>
#include <string>
#include <vector>

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

    const INITCOMMONCONTROLSEX controls{sizeof(INITCOMMONCONTROLSEX), ICC_WIN95_CLASSES};
    InitCommonControlsEx(&controls);  // ツールチップを使うため。

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
            // 引数: [動画] [比較する動画] [--sync]。--syncがあれば連携モードで始める(Mayaから起動したとき)。
            int argc = 0;
            LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
            if (argv) {
                std::vector<std::wstring> paths;
                bool sync = false;
                for (int i = 1; i < argc; ++i) {
                    if (wcscmp(argv[i], L"--sync") == 0) {
                        sync = true;
                    } else {
                        paths.emplace_back(argv[i]);
                    }
                }
                LocalFree(argv);
                if (sync) {
                    window.setSyncEnabled(true);
                }
                if (paths.size() > 0) {
                    window.openClip(paths[0]);
                }
                if (paths.size() > 1) {
                    window.openCompare(paths[1]);  // 2つ目は比較用として右に並べる。
                }
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
