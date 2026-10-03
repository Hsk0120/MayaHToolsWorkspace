/**
 * @file Main.cpp
 * @brief WinAppSetup(汎用インストーラー)の入口。
 *
 * 同じexeが3つの役を持つ:
 * - セットアップを作る: `WinAppSetup.exe --build <アプリ.ini> --out <Setup.exe>`
 *   (このexeを写し、写した方にアプリの中身を埋め込む)
 * - インストール: 中身を埋め込んだSetup.exeを起動する。`/S` で画面を出さずに入れる。
 *   `--dir <フォルダ>` でインストール先、`--no-file-types` で関連付けをしない。
 * - アンインストール: インストール先の `Uninstall.exe --uninstall`(「アプリ」一覧から呼ばれる)。
 *   `/S` で画面を出さず、`--remove-data` で設定などのデータも消す。
 *
 * 終了コード: 0=成功、1=取り消し、2=失敗。記録は %TEMP%\<アプリ>-setup.log に書く。
 */
#include <windows.h>
#include <commctrl.h>
#include <objbase.h>
#include <shellapi.h>

#include <string>
#include <vector>

#include "setup/Builder.h"
#include "setup/Common.h"
#include "setup/Installer.h"
#include "setup/Package.h"
#include "setup/SetupUi.h"

// コモンコントロールの新しい版(6)を使う。タスクダイアログはこの版にしか無い。
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

namespace {

constexpr int kInstallButton = 100;      ///< 「インストール」ボタン。
constexpr int kChangeDirButton = 101;    ///< 「インストール先を変更」ボタン。
constexpr int kCloseAppsButton = 102;    ///< 「閉じて続ける」ボタン。
constexpr int kUninstallButton = 103;    ///< 「アンインストール」ボタン。

/** @brief コマンドラインの指定。 */
struct Arguments {
    std::wstring buildManifest;  ///< --build: アプリの設定ファイル。
    std::wstring buildOutput;    ///< --out: 書き出すSetup.exe。
    bool uninstall = false;      ///< --uninstall。
    bool silent = false;         ///< /S: 画面を出さない。
    std::wstring dir;            ///< --dir: インストール先。
    bool noFileTypes = false;    ///< --no-file-types: 関連付けをしない。
    bool removeData = false;     ///< --remove-data: アンインストールでデータも消す。
    bool tempCopy = false;       ///< --temp-copy: 一時フォルダへ写した自分として動いている(アンインストール)。
    DWORD waitPid = 0;           ///< --wait-pid: このプロセスが終わるのを待ってから始める。
};

/**
 * @brief コマンドラインを読む。
 * @param args 読んだ指定の格納先。
 * @return 正しく読めたらtrue。
 */
bool parseArguments(Arguments& args) {
    int count = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &count);
    bool ok = true;
    for (int i = 1; i < count && ok; ++i) {
        const std::wstring arg = argv[i];
        auto next = [&](std::wstring& value) {
            if (i + 1 >= count) {
                ok = false;
                return;
            }
            value = argv[++i];
        };
        if (arg == L"--build") next(args.buildManifest);
        else if (arg == L"--out") next(args.buildOutput);
        else if (arg == L"--uninstall") args.uninstall = true;
        else if (wak::equalsIgnoreCase(arg, L"/S") || arg == L"--silent") args.silent = true;
        else if (arg == L"--dir") next(args.dir);
        else if (arg.size() > 3 && wak::equalsIgnoreCase(arg.substr(0, 3), L"/D=")) args.dir = arg.substr(3);
        else if (arg == L"--no-file-types") args.noFileTypes = true;
        else if (arg == L"--remove-data") args.removeData = true;
        else if (arg == L"--temp-copy") args.tempCopy = true;
        else if (arg == L"--wait-pid") {
            std::wstring pid;
            next(pid);
            args.waitPid = static_cast<DWORD>(_wtoi(pid.c_str()));
        } else {
            ok = false;
        }
    }
    LocalFree(argv);
    return ok;
}

/**
 * @brief このexeのパスを返す。
 * @return パス。
 */
std::wstring selfPath() {
    wchar_t path[MAX_PATH * 2];
    GetModuleFileNameW(nullptr, path, static_cast<DWORD>(std::size(path)));
    return path;
}

/**
 * @brief このexeに埋め込まれた中身を取り出す。
 * @param manifest アプリの説明の格納先。
 * @param files ファイルの格納先。
 * @param error 失敗した理由の格納先。
 * @return 取り出せたらtrue。中身が無い(Setup.exeを作る前の本体)ならfalseで、errorは空。
 */
bool loadEmbeddedPackage(wak::Manifest& manifest, std::vector<wak::PackageFile>& files, std::wstring& error) {
    HRSRC resource = FindResourceW(nullptr, wak::kPackageResource, RT_RCDATA);
    if (!resource) {
        error.clear();
        return false;
    }
    HGLOBAL loaded = LoadResource(nullptr, resource);
    const void* data = loaded ? LockResource(loaded) : nullptr;
    const DWORD size = SizeofResource(nullptr, resource);
    return data && wak::readPackage(static_cast<const std::uint8_t*>(data), size, manifest, files, error);
}

/**
 * @brief 失敗を知らせる(画面を出さないときは記録だけ)。
 * @param title ダイアログのタイトル。
 * @param message 理由。
 * @param silent 画面を出さないか。
 */
void showError(const std::wstring& title, const std::wstring& message, bool silent) {
    wak::logLine(L"エラー: %ls", message.c_str());
    if (silent) {
        return;
    }
    wak::DialogSpec spec;
    spec.title = title;
    spec.instruction = L"うまくいきませんでした";
    spec.content = message + L"\n\n詳しい記録: " + wak::logPath();
    spec.closeButton = true;
    spec.icon = wak::DialogIcon::Error;
    wak::showDialog(spec);
}

/**
 * @brief 起動中のアプリがあれば閉じてもらう(画面を出さないときは閉じる)。
 * @param files 対象のファイル。
 * @param title ダイアログのタイトル。
 * @param silent 画面を出さないか。
 * @return 続けてよければtrue。取り消された・閉じられなかったらfalse。
 */
bool ensureAppsClosed(const std::vector<std::wstring>& files, const std::wstring& title, bool silent) {
    std::vector<std::wstring> running = wak::findRunningApps(files);
    if (running.empty()) {
        return true;
    }
    std::wstring names;
    for (const std::wstring& name : running) {
        names += L"・" + name + L"\n";
    }
    wak::logLine(L"起動中のアプリ: %ls", names.c_str());
    if (!silent) {
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = L"使用中のアプリを閉じてから続けます";
        spec.content = names + L"\n「閉じて続ける」を押すと、このアプリを閉じます。";
        spec.buttons = {{kCloseAppsButton, L"閉じて続ける"}};
        spec.cancelButton = true;
        spec.icon = wak::DialogIcon::Warning;
        if (wak::showDialog(spec).button != kCloseAppsButton) {
            return false;
        }
    }
    if (!wak::closeRunningApps(files)) {
        showError(title, L"アプリを閉じられませんでした。手動で閉じてから、もう一度実行してください。", silent);
        return false;
    }
    return true;
}

/**
 * @brief インストールする(画面の流れ: 確認 → 起動中のアプリを閉じる → 進み具合 → 完了)。
 * @param args コマンドラインの指定。
 * @param manifest アプリの説明。
 * @param files 中身。
 * @return 終了コード。
 */
int runInstall(const Arguments& args, const wak::Manifest& manifest, const std::vector<wak::PackageFile>& files) {
    const std::wstring title = manifest.name + L" セットアップ";
    const wak::ExistingInstall existing = wak::findExistingInstall(manifest.id);
    std::wstring dir = !args.dir.empty() ? wak::fullPath(args.dir)
                       : existing.found  ? wak::fullPath(existing.dir)
                                         : wak::defaultInstallDir(manifest);
    bool fileTypes = !manifest.progId.empty() && !args.noFileTypes;
    wak::logLine(L"%ls %ls  インストール先: %ls%ls", manifest.name.c_str(), manifest.version.c_str(), dir.c_str(),
                 existing.found ? (L"  (更新。今の版 " + existing.version + L")").c_str() : L"");

    if (!args.silent) {
        // 確認の画面。インストール先は変えられる(更新のときは、今の場所のまま)。
        for (;;) {
            wak::DialogSpec spec;
            spec.title = title;
            spec.instruction = existing.found ? manifest.name + L" を " + existing.version + L" から " + manifest.version +
                                                    L" に更新します"
                                              : manifest.name + L" " + manifest.version + L" をインストールします";
            spec.content = L"インストール先:\n" + dir + L"\n\nこのユーザーだけにインストールします(管理者の権限は要りません)。"
                           L"\n設定の「アプリ」から、いつでもアンインストールできます。";
            spec.buttons = {{kInstallButton, existing.found ? L"更新" : L"インストール"}};
            if (!existing.found) {
                spec.buttons.push_back({kChangeDirButton, L"インストール先を変更..."});
            }
            spec.cancelButton = true;
            if (!manifest.progId.empty() && manifest.fileTypesOptional) {
                // 拡張子が多いときは、最初の1つと数だけを書く(チェックボックスの文が折り返さないように)。
                std::wstring extensions = manifest.extensions.front();
                if (manifest.extensions.size() == 2) {
                    extensions += L" " + manifest.extensions[1];
                } else if (manifest.extensions.size() > 2) {
                    extensions += L" ほか" + std::to_wstring(manifest.extensions.size() - 1) + L"種類";
                }
                spec.verification = L"右クリックと「プログラムから開く」に追加(" + extensions + L")";
                spec.verificationChecked = fileTypes;
            }
            const wak::DialogResult result = wak::showDialog(spec);
            if (!spec.verification.empty()) {
                fileTypes = result.verification;
            }
            if (result.button == kChangeDirButton) {
                const std::wstring chosen = wak::chooseFolder(L"インストール先のフォルダを選択", wak::parentPath(dir));
                if (!chosen.empty()) {
                    // 選んだフォルダの中に、アプリの名前のフォルダを作って入れる(選んだフォルダの中身を散らかさない)。
                    const std::wstring full = wak::fullPath(chosen);
                    const std::wstring last = full.substr(full.find_last_of(L'\\') + 1);
                    dir = wak::equalsIgnoreCase(last, manifest.id) ? full : wak::joinPath(full, manifest.id);
                }
                continue;
            }
            if (result.button != kInstallButton) {
                wak::logLine(L"取り消されました");
                return 1;
            }
            break;
        }
    }

    std::wstring error;
    if (!wak::checkInstallDir(dir, error)) {
        showError(title, error, args.silent);
        return 2;
    }
    if (!ensureAppsClosed(wak::installedFiles(manifest, dir), title, args.silent)) {
        return 1;
    }

    wak::InstallOptions options;
    options.installDir = dir;
    options.fileTypes = fileTypes;
    bool ok = false;
    auto work = [&](const std::function<void(int, const std::wstring&)>& progress) {
        ok = wak::install(manifest, files, options, progress, error);
    };
    if (args.silent) {
        work(nullptr);
    } else {
        wak::runWithProgress(title, manifest.name + L" をインストールしています", work);
    }
    if (!ok) {
        showError(title, error, args.silent);
        return 2;
    }

    if (!args.silent) {
        const std::wstring exePath = wak::joinPath(dir, manifest.executable);
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = existing.found ? L"更新しました" : L"インストールしました";
        spec.content = L"スタートメニューの「" + manifest.name + L"」から起動できます。";
        if (fileTypes) {
            spec.content += L"\n\nファイルをいつも " + manifest.name +
                            L" で開くには、設定の <a href=\"ms-settings:defaultapps\">既定のアプリ</a> で選んでください"
                            L"(Windowsの決まりで、既定のアプリは本人が選びます)。";
            spec.onLink = [](const std::wstring& href) {
                ShellExecuteW(nullptr, L"open", href.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
            };
        }
        spec.closeButton = true;
        spec.verification = manifest.name + L" を起動する";
        spec.verificationChecked = true;
        if (wak::showDialog(spec).verification) {
            ShellExecuteW(nullptr, L"open", exePath.c_str(), nullptr, wak::parentPath(exePath).c_str(), SW_SHOWNORMAL);
        }
    }
    return 0;
}

/**
 * @brief このexe(インストール先のUninstall.exe)を一時フォルダへ写し、そちらでアンインストールを続ける。
 * @param args コマンドラインの指定。
 * @param installDir インストール先。
 * @param id アプリの識別名(一時ファイルの名前に使う)。
 * @return 写した方を起動できたらtrue。
 * @note 動いているexeは自分を消せないので、写した方が元のUninstall.exeを消す。写した方は、最後に自分を消す。
 */
bool relaunchFromTemp(const Arguments& args, const std::wstring& installDir, const std::wstring& id) {
    wchar_t tempDir[MAX_PATH];
    GetTempPathW(MAX_PATH, tempDir);
    const std::wstring copy = wak::joinPath(tempDir, id + L"-uninstall.exe");
    if (!CopyFileW(selfPath().c_str(), copy.c_str(), FALSE)) {
        return false;
    }
    std::wstring command = L"\"" + copy + L"\" --uninstall --temp-copy --dir \"" + installDir + L"\" --wait-pid " +
                           std::to_wstring(GetCurrentProcessId());
    if (args.silent) {
        command += L" /S";
    }
    if (args.removeData) {
        command += L" --remove-data";
    }
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(copy.c_str(), command.data(), nullptr, nullptr, FALSE, 0, nullptr, tempDir, &startup,
                        &process)) {
        return false;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return true;
}

/** @brief 一時フォルダへ写した自分を、終わった後に消すよう頼む(少し待ってから消す小さなコマンドを裏で動かす)。 */
void scheduleSelfDelete() {
    wchar_t system[MAX_PATH];
    GetSystemDirectoryW(system, MAX_PATH);
    const std::wstring cmd = wak::joinPath(system, L"cmd.exe");
    std::wstring command = L"\"" + cmd + L"\" /c ping -n 3 127.0.0.1 >nul & del /f /q \"" + selfPath() + L"\"";
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    if (CreateProcessW(cmd.c_str(), command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr,
                       &startup, &process)) {
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
}

/**
 * @brief アンインストールする(画面の流れ: 確認 → 起動中のアプリを閉じる → 完了)。
 * @param args コマンドラインの指定。
 * @param fallbackId 記録が読めないときに使う識別名(埋め込まれた中身から)。
 * @return 終了コード。
 */
int runUninstall(const Arguments& args, const std::wstring& fallbackId) {
    const std::wstring installDir = wak::fullPath(args.dir.empty() ? wak::parentPath(selfPath()) : args.dir);
    wak::RecordInfo info;
    if (!wak::readRecordInfo(installDir, info)) {
        showError(fallbackId + L" のアンインストール", L"インストールの記録が見つかりません: " + installDir, args.silent);
        return 2;
    }
    const std::wstring title = info.name + L" のアンインストール";

    // インストール先の中から動いているときは、一時フォルダへ写した自分に任せて終わる。
    if (!args.tempCopy) {
        if (!relaunchFromTemp(args, installDir, info.id)) {
            showError(title, L"アンインストールを始められません: " + wak::errorText(GetLastError()), args.silent);
            return 2;
        }
        return 0;
    }
    if (args.waitPid != 0) {
        if (HANDLE parent = OpenProcess(SYNCHRONIZE, FALSE, args.waitPid)) {
            WaitForSingleObject(parent, 10000);  // 元のUninstall.exeが終わってから消す。
            CloseHandle(parent);
        }
    }

    bool removeData = args.removeData;
    if (!args.silent) {
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = info.name + L" " + info.version + L" をアンインストールしますか?";
        spec.content = L"インストール先:\n" + installDir;
        spec.buttons = {{kUninstallButton, L"アンインストール"}};
        spec.cancelButton = true;
        if (info.hasUserData) {
            spec.verification = L"設定などのデータも削除する";
            spec.verificationChecked = removeData;
        }
        const wak::DialogResult result = wak::showDialog(spec);
        if (result.button != kUninstallButton) {
            wak::logLine(L"取り消されました");
            scheduleSelfDelete();
            return 1;
        }
        removeData = info.hasUserData && result.verification;
    }
    std::vector<std::wstring> files;
    const std::wstring exe = wak::joinPath(installDir, info.executable);
    if (wak::fileExists(exe)) {
        files.push_back(exe);
    }
    if (!ensureAppsClosed(files, title, args.silent)) {
        scheduleSelfDelete();
        return 1;
    }
    std::wstring error;
    const bool ok = wak::uninstall(installDir, removeData, error);
    if (!ok) {
        showError(title, error, args.silent);
    } else if (!args.silent) {
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = L"アンインストールしました";
        spec.content = removeData ? L"設定などのデータも削除しました。" : L"設定などのデータは残してあります。";
        spec.closeButton = true;
        spec.icon = wak::DialogIcon::Information;
        wak::showDialog(spec);
    }
    scheduleSelfDelete();
    return ok ? 0 : 2;
}

}  // namespace

/**
 * @brief 入口。コマンドラインに応じて、セットアップを作る・インストール・アンインストールのどれかを行う。
 * @param instance このexeのインスタンス。
 * @return 終了コード(0=成功、1=取り消し、2=失敗)。
 */
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int) {
    (void)instance;
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    const INITCOMMONCONTROLSEX controls{sizeof(INITCOMMONCONTROLSEX), ICC_WIN95_CLASSES};
    InitCommonControlsEx(&controls);

    int result = 2;
    Arguments args;
    if (!parseArguments(args)) {
        wak::logLine(L"使い方: WinAppSetup --build <アプリ.ini> --out <Setup.exe> / Setup.exe [/S] [--dir <フォルダ>] "
                     L"[--no-file-types] / Uninstall.exe --uninstall [/S] [--remove-data]");
        result = 2;
    } else if (!args.buildManifest.empty()) {
        result = args.buildOutput.empty() ? 2 : wak::buildSetup(args.buildManifest, args.buildOutput);
    } else {
        wak::Manifest manifest;
        std::vector<wak::PackageFile> files;
        std::wstring error;
        const bool embedded = loadEmbeddedPackage(manifest, files, error);
        wchar_t tempDir[MAX_PATH];
        GetTempPathW(MAX_PATH, tempDir);
        const std::wstring id = embedded ? manifest.id : L"WinAppSetup";
        wak::openLog(wak::joinPath(tempDir, id + (args.uninstall ? L"-uninstall.log" : L"-setup.log")));
        if (args.uninstall) {
            result = runUninstall(args, id);
        } else if (!embedded) {
            showError(L"WinAppSetup",
                      error.empty() ? L"これはセットアップを作るための本体です。\n"
                                      L"WinAppSetup.exe --build <アプリ.ini> --out <Setup.exe> で、アプリのセットアップを作ってください。"
                                    : error,
                      args.silent);
            result = 2;
        } else {
            result = runInstall(args, manifest, files);
        }
    }
    if (SUCCEEDED(com)) {
        CoUninitialize();
    }
    return result;
}
