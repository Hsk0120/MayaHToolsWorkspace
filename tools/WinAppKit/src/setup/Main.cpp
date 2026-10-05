/**
 * @file Main.cpp
 * @brief WinAppSetup(汎用インストーラー)の入口。
 *
 * 同じexeが3つの役を持つ:
 * - セットアップを作る: `WinAppSetup.exe --build <アプリ.ini> --out <Setup.exe>`
 *   (このexeを写し、写した方にアプリの中身を埋め込む)
 * - インストール: 中身を埋め込んだSetup.exeを起動する。`/S` で画面を出さずに入れる。
 *   `--dir <フォルダ>` でインストール先、`--extensions .mp4;.mov` で関連付ける拡張子、`--no-file-types` で関連付けをしない、
 *   `--no-context-menu` で右クリックに出さない。
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
#include "setup/Requirements.h"
#include "setup/SetupUi.h"

// コモンコントロールの新しい版(6)を使う。タスクダイアログはこの版にしか無い。
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

namespace {

constexpr int kInstallButton = 100;      ///< 「インストール」ボタン。
constexpr int kChangeDirButton = 101;    ///< 「インストール先を変更」ボタン。
constexpr int kCloseAppsButton = 102;    ///< 「閉じて続ける」ボタン。
constexpr int kUninstallButton = 103;    ///< 「アンインストール」ボタン。
constexpr int kAssociationsButton = 104;  ///< 「ファイルの関連付けを変更」ボタン。

/** @brief コマンドラインの指定。 */
struct Arguments {
    std::wstring buildManifest;  ///< --build: アプリの設定ファイル。
    std::wstring buildOutput;    ///< --out: 書き出すSetup.exe。
    bool uninstall = false;      ///< --uninstall。
    bool silent = false;         ///< /S: 画面を出さない。
    std::wstring dir;            ///< --dir: インストール先。
    bool noFileTypes = false;    ///< --no-file-types: 関連付けをしない。
    std::wstring extensions;     ///< --extensions: 関連付ける拡張子(「.mp4;.mov」の形)。省くと前回の選択かすべて。
    bool noContextMenu = false;  ///< --no-context-menu: 右クリックに項目を出さない。
    bool checkFileTypes = false; ///< --check-file-types: 関連付けの前提条件を調べて標準出力へ書くだけ(確認用)。
    bool removeData = false;     ///< --remove-data: アンインストールでデータも消す。
    bool tempCopy = false;       ///< --temp-copy: 一時フォルダへ写した自分として動いている(アンインストール)。
    DWORD waitPid = 0;           ///< --wait-pid: このプロセスが終わるのを待ってから始める。
};

/** @brief 同じアプリのセットアップ・アンインストールが同時に動かないようにする鍵(名前付きのミューテックス)。 */
class AppLock {
public:
    AppLock() = default;
    AppLock(const AppLock&) = delete;
    AppLock& operator=(const AppLock&) = delete;

    /** @brief 鍵を持っていれば手放す。 */
    ~AppLock() {
        if (mutex_) {
            if (owned_) {
                ReleaseMutex(mutex_);
            }
            CloseHandle(mutex_);
        }
    }

    /**
     * @brief 鍵を取る。ほかが持っていれば、手放すまで少し待つ。
     * @param id アプリの識別名(鍵の名前に使う)。
     * @return 取れたらtrue。60秒待っても取れなければfalse。
     */
    bool acquire(const std::wstring& id) {
        mutex_ = CreateMutexW(nullptr, FALSE, (L"Local\\WinAppSetup-" + id).c_str());
        if (!mutex_) {
            return false;
        }
        const DWORD result = WaitForSingleObject(mutex_, 60000);
        owned_ = result == WAIT_OBJECT_0 || result == WAIT_ABANDONED;  // 前の持ち主が落ちていても取れる。
        return owned_;
    }

private:
    HANDLE mutex_ = nullptr;
    bool owned_ = false;
};

/**
 * @brief 拡張子を小文字にする(前提条件の表を引くため)。
 * @param extension 拡張子。
 * @return 小文字にした拡張子。
 */
std::wstring toLowerExtension(std::wstring extension) {
    for (wchar_t& c : extension) {
        c = static_cast<wchar_t>(towlower(c));
    }
    return extension;
}

/**
 * @brief 関連付けの前提条件を調べ、拡張子ごとの結果を標準出力へUTF-8で書く(確認用の --check-file-types)。
 * @param manifest アプリの説明。
 * @return 終了コード(常に0)。
 */
int checkFileTypes(const wak::Manifest& manifest) {
    std::string text;
    for (const std::wstring& extension : manifest.extensions) {
        const auto rule = manifest.requirements.find(toLowerExtension(extension));
        std::wstring missing;
        const bool ok = rule == manifest.requirements.end() || wak::meetsRequirement(extension, rule->second, missing);
        std::wstring line = extension + (ok ? L"\tOK" : L"\tNG\t" + missing) + L"\n";
        const int size = WideCharToMultiByte(CP_UTF8, 0, line.c_str(), static_cast<int>(line.size()), nullptr, 0, nullptr, nullptr);
        std::string utf8(static_cast<std::size_t>(size), '\0');
        WideCharToMultiByte(CP_UTF8, 0, line.c_str(), static_cast<int>(line.size()), utf8.data(), size, nullptr, nullptr);
        text += utf8;
    }
    DWORD written = 0;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
    return 0;
}

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
        else if (arg == L"--extensions") next(args.extensions);
        else if (arg == L"--no-context-menu") args.noContextMenu = true;
        else if (arg == L"--check-file-types") args.checkFileTypes = true;
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
    wak::logLine(L"Error: %ls", message.c_str());
    if (silent) {
        return;
    }
    wak::DialogSpec spec;
    spec.title = title;
    spec.instruction = L"Something went wrong";
    spec.content = message + L"\n\nLog: " + wak::logPath();
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
        names += L"- " + name + L"\n";
    }
    wak::logLine(L"Running applications: %ls", names.c_str());
    if (!silent) {
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = L"Close the running application to continue";
        spec.content = names + L"\nClick \"Close and continue\" to close it.";
        spec.buttons = {{kCloseAppsButton, L"Close and continue"}};
        spec.cancelButton = true;
        spec.icon = wak::DialogIcon::Warning;
        if (wak::showDialog(spec).button != kCloseAppsButton) {
            return false;
        }
    }
    if (!wak::closeRunningApps(files)) {
        showError(title, L"The application could not be closed. Close it manually and run setup again.", silent);
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
    const std::wstring title = manifest.name + L" Setup";
    const wak::ExistingInstall existing = wak::findExistingInstall(manifest.id);
    std::wstring dir = !args.dir.empty() ? wak::fullPath(args.dir)
                       : existing.found  ? wak::fullPath(existing.dir)
                                         : wak::defaultInstallDir(manifest);
    wak::logLine(L"%ls %ls  install folder: %ls%ls", manifest.name.c_str(), manifest.version.c_str(), dir.c_str(),
                 existing.found ? (L"  (update; installed version " + existing.version + L")").c_str() : L"");

    // 関連付けの初期値: 新しく入れるときはすべて。更新のときは前回の選択(記録から読む)。コマンドラインの指定が優先。
    const bool hasFileTypes = !manifest.progId.empty();
    wak::AssociationChoice choice;
    choice.extensions = manifest.extensions;
    choice.selected.assign(manifest.extensions.size(), hasFileTypes);
    choice.hasContextMenu = !manifest.contextMenu.empty();
    choice.contextMenu = choice.hasContextMenu;
    wak::RecordInfo previous;
    if (existing.found && wak::readRecordInfo(existing.dir, previous)) {
        for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
            choice.selected[i] = false;
            for (const std::wstring& extension : previous.extensions) {
                choice.selected[i] = choice.selected[i] || wak::equalsIgnoreCase(extension, choice.extensions[i]);
            }
        }
        choice.contextMenu = choice.hasContextMenu && previous.contextMenu;
    }
    if (!args.extensions.empty()) {
        const std::vector<std::wstring> wanted = wak::split(args.extensions, L';');
        for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
            choice.selected[i] = false;
            for (const std::wstring& extension : wanted) {
                choice.selected[i] = choice.selected[i] || wak::equalsIgnoreCase(extension, choice.extensions[i]);
            }
        }
    }
    if (args.noFileTypes || !hasFileTypes) {
        choice.selected.assign(choice.extensions.size(), false);
    }
    // 前提の拡張機能が入っていない拡張子は関連付けない(開けないファイルが FramePlayer で開くようにならないように)。
    std::wstring unavailable;
    for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
        bool available = true;
        std::wstring missing;
        const auto rule = manifest.requirements.find(toLowerExtension(choice.extensions[i]));
        if (hasFileTypes && rule != manifest.requirements.end()) {
            available = wak::meetsRequirement(choice.extensions[i], rule->second, missing);
        }
        choice.available.push_back(available);
        if (!available) {
            choice.selected[i] = false;
            const auto note = manifest.requirementNotes.find(toLowerExtension(choice.extensions[i]));
            const std::wstring need = note != manifest.requirementNotes.end() ? note->second : missing;
            unavailable += L"\n" + choice.extensions[i] + L": " + need;
            wak::logLine(L"Not associating %ls (requirement not met: %ls)", choice.extensions[i].c_str(), missing.c_str());
        }
    }
    if (!unavailable.empty()) {
        choice.unavailableNote = L"Grayed-out types need a Windows extension (available from the Microsoft Store) that is not installed. "
                                 L"Install it and run setup again to select them." + unavailable;
    }
    if (args.noContextMenu) {
        choice.contextMenu = false;
    }
    // 選んだ拡張子の説明(確認の画面に出す)。多いときは最初の4つと数だけ。
    auto summary = [&]() {
        std::wstring text;
        int count = 0;
        for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
            if (choice.selected[i]) {
                if (count < 4) {
                    text += (text.empty() ? L"" : L" ") + choice.extensions[i];
                }
                ++count;
            }
        }
        if (count == 0) {
            return std::wstring(L"No file associations");
        }
        if (count > 4) {
            text += L" and " + std::to_wstring(count - 4) + L" more";
        }
        if (choice.hasContextMenu) {
            text += choice.contextMenu ? L" (with right-click menu)" : L" (without right-click menu)";
        }
        return text;
    };

    if (!args.silent) {
        // 確認の画面。選択肢を縦に並べ、それぞれの下に今の設定を出す。
        for (;;) {
            wak::DialogSpec spec;
            spec.title = title;
            if (!existing.found) {
                spec.instruction = manifest.name + L" " + manifest.version + L" will be installed";
            } else if (existing.version == manifest.version) {
                spec.instruction = manifest.name + L" " + manifest.version + L" will be reinstalled";  // 同じ版の上書き(修復)。
            } else {
                spec.instruction =
                    manifest.name + L" will be updated from " + existing.version + L" to " + manifest.version;
            }
            spec.content = L"Installs for the current user only (no administrator rights needed). "
                           L"You can uninstall it at any time from Settings > Apps.";
            spec.commandLinks = true;
            const wchar_t* action = !existing.found                         ? L"Install\n"
                                    : existing.version == manifest.version ? L"Reinstall\n"
                                                                            : L"Update\n";
            spec.buttons = {{kInstallButton, action + dir}};
            if (!existing.found) {
                spec.buttons.push_back({kChangeDirButton, L"Change the install folder\nChoose a folder to install into"});
            }
            if (hasFileTypes && manifest.fileTypesOptional) {
                spec.buttons.push_back({kAssociationsButton, L"Change file associations\n" + summary()});
            }
            spec.cancelButton = true;
            const wak::DialogResult result = wak::showDialog(spec);
            if (result.button == kChangeDirButton) {
                const std::wstring chosen = wak::chooseFolder(L"Select the Install Folder", wak::parentPath(dir));
                if (!chosen.empty()) {
                    // 選んだフォルダの中に、アプリの名前のフォルダを作って入れる(選んだフォルダの中身を散らかさない)。
                    const std::wstring full = wak::fullPath(chosen);
                    const std::wstring last = full.substr(full.find_last_of(L'\\') + 1);
                    dir = wak::equalsIgnoreCase(last, manifest.id) ? full : wak::joinPath(full, manifest.id);
                }
                continue;
            }
            if (result.button == kAssociationsButton) {
                wak::chooseAssociations(title, manifest.name, choice);
                continue;
            }
            if (result.button != kInstallButton) {
                wak::logLine(L"Canceled");
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
    for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
        if (choice.selected[i]) {
            options.extensions.push_back(choice.extensions[i]);
        }
    }
    options.contextMenu = choice.contextMenu;
    wak::logLine(L"File associations: %ls", summary().c_str());
    bool ok = false;
    auto work = [&](const std::function<void(int, const std::wstring&)>& progress) {
        ok = wak::install(manifest, files, options, progress, error);
    };
    if (args.silent) {
        work(nullptr);
    } else {
        wak::runWithProgress(title, L"Installing " + manifest.name, work);
    }
    if (!ok) {
        showError(title, error, args.silent);
        return 2;
    }

    const bool associated = !options.extensions.empty();
    if (!args.silent) {
        const std::wstring exePath = wak::joinPath(dir, manifest.executable);
        wak::DialogSpec spec;
        spec.title = title;
        spec.instruction = existing.found ? L"Updated" : L"Installed";
        spec.content = L"Start it from \"" + manifest.name + L"\" in the Start menu.";
        if (associated) {
            // 既定のアプリはWindowsの決まりで本人が選ぶ(アプリからは設定できない)ので、選び方を案内する。
            spec.content += L"\n\nTo always open files with " + manifest.name +
                            L", right-click a file, choose \"Open with\" > \"Choose another app\", select " +
                            manifest.name + L", and click \"Always\".";
        }
        spec.closeButton = true;
        spec.verification = L"Launch " + manifest.name;
        spec.verificationChecked = false;  // 起動は本人が選んだときだけ(既定はオフ)。
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
        showError(fallbackId + L" Uninstall", L"The install record was not found: " + installDir, args.silent);
        return 2;
    }
    const std::wstring title = info.name + L" Uninstall";

    // インストール先の中から動いているときは、一時フォルダへ写した自分に任せて終わる。
    if (!args.tempCopy) {
        if (!relaunchFromTemp(args, installDir, info.id)) {
            showError(title, L"Cannot start uninstalling: " + wak::errorText(GetLastError()), args.silent);
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
        spec.instruction = L"Uninstall " + info.name + L" " + info.version + L"?";
        spec.content = L"Install folder:\n" + installDir;
        spec.buttons = {{kUninstallButton, L"Uninstall"}};
        spec.cancelButton = true;
        if (info.hasUserData) {
            spec.verification = L"Also delete settings and other data";
            spec.verificationChecked = removeData;
        }
        const wak::DialogResult result = wak::showDialog(spec);
        if (result.button != kUninstallButton) {
            wak::logLine(L"Canceled");
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
        spec.instruction = L"Uninstalled";
        spec.content = removeData ? L"Settings and other data were also deleted." : L"Settings and other data were kept.";
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
    // 画面の文字は英語なので、Windowsが出す標準のボタン(Cancel・Close)とフォルダ選択の画面も英語にする
    // (英語の表示用データが無いWindowsでは、Windowsの言語のまま出る)。
    const wchar_t languages[] = L"en-US\0";
    SetProcessPreferredUILanguages(MUI_LANGUAGE_NAME, languages, nullptr);
    SetThreadPreferredUILanguages(MUI_LANGUAGE_NAME, languages, nullptr);
    const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    const INITCOMMONCONTROLSEX controls{sizeof(INITCOMMONCONTROLSEX), ICC_WIN95_CLASSES};
    InitCommonControlsEx(&controls);

    int result = 2;
    Arguments args;
    if (!parseArguments(args)) {
        wak::logLine(L"Usage: WinAppSetup --build <app.ini> --out <Setup.exe> / Setup.exe [/S] [--dir <folder>] "
                     L"[--extensions .mp4;.mov] [--no-file-types] [--no-context-menu] / Uninstall.exe --uninstall [/S] [--remove-data]");
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
        // 同じアプリのインストールとアンインストールが同時に動かないようにする(互いのファイルや登録を消し合わないため)。
        // アンインストールは、インストール先から一時フォルダへ写した方だけが作業するので、そちらで取る。
        AppLock lock;
        const bool needsLock = (!args.uninstall || args.tempCopy) && !args.checkFileTypes;
        if (embedded && args.checkFileTypes) {
            result = checkFileTypes(manifest);
        } else if (needsLock && !lock.acquire(id)) {
            showError(id, L"Setup or uninstall of the same application is already running. Try again after it finishes.",
                      args.silent);
            result = 2;
        } else if (args.uninstall) {
            result = runUninstall(args, id);
        } else if (!embedded) {
            showError(L"WinAppSetup",
                      error.empty() ? L"This is the tool for building setup programs.\n"
                                      L"Use WinAppSetup.exe --build <app.ini> --out <Setup.exe> to build a setup for your application."
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
