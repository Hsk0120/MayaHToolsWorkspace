/**
 * @file Installer.cpp
 * @brief インストール・更新・アンインストールの本体の実装。
 */
#include "setup/Installer.h"

#include "setup/Common.h"

#include <windows.h>
#include <restartmanager.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <wrl/client.h>

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <utility>

namespace wak {

namespace {

constexpr wchar_t kRecordName[] = L"uninstall.wak";    ///< インストール先に置く記録のファイル名。
constexpr wchar_t kBackupName[] = L".wak-backup";      ///< 更新中に、置き換える前のファイルを控えるフォルダ。
constexpr wchar_t kUninstallerName[] = L"Uninstall.exe";  ///< インストール先に写す自分自身の名前。
constexpr wchar_t kUninstallRoot[] = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\";
constexpr wchar_t kAppPathsRoot[] = L"Software\\Microsoft\\Windows\\CurrentVersion\\App Paths";

/** @brief インストールで作ったものの1つ(記録の1行)。 */
struct Action {
    /** @brief 作ったものの種類。 */
    enum class Type {
        Dir,       ///< 新しく作ったフォルダ。消すときは空なら消す。
        File,      ///< 置いたファイル。消すときは消す。
        Key,       ///< 自分のレジストリのキー(中身ごと自分のもの)。消すときは中身ごと消す。
        EmptyKey,  ///< 途中に新しく作ったキー(ほかのアプリも使うかもしれない)。消すときは空なら消す。
        Value,     ///< ほかのアプリと共有するキーに足した値。消すときはその値だけ消す。
    };
    Type type = Type::File;
    std::wstring path;   ///< ファイル・フォルダのパス、またはHKEY_CURRENT_USERからのキーのパス。
    std::wstring name;   ///< 値の名前(Valueのときだけ)。
    bool existedBefore = false;  ///< 作る前からあったか(失敗したときの巻き戻しで、元からあったものは消さない)。

    /**
     * @brief 同じものを指すかを返す(更新のときに、前の版の記録と比べるため)。
     * @param other 比べるもの。
     * @return 同じならtrue。
     */
    bool same(const Action& other) const {
        return type == other.type && equalsIgnoreCase(path, other.path) && equalsIgnoreCase(name, other.name);
    }
};

/** @brief 記録のファイルの中身。 */
struct Record {
    std::wstring id;
    std::wstring name;
    std::wstring version;
    std::wstring executable;
    std::vector<std::wstring> userDataRegistry;  ///< 「データも削除」で消すキー(HKCU\...の形)。
    std::vector<std::wstring> userDataFolders;   ///< 同じく消すフォルダ(置き換え済みの実際のパス)。
    std::vector<Action> actions;                 ///< 作った順。
};

/**
 * @brief 記録の種類を文字にする。
 * @param type 種類。
 * @return 記録のファイルに書く名前。
 */
const wchar_t* typeName(Action::Type type) {
    switch (type) {
    case Action::Type::Dir:
        return L"dir";
    case Action::Type::File:
        return L"file";
    case Action::Type::Key:
        return L"key";
    case Action::Type::EmptyKey:
        return L"emptykey";
    case Action::Type::Value:
        return L"value";
    }
    return L"";
}

/**
 * @brief 記録をファイルに書く。
 * @param path 記録のファイル。
 * @param record 中身。
 * @return 書けたらtrue。
 */
bool saveRecord(const std::wstring& path, const Record& record) {
    std::wstring text = L"WAKRECORD 1\r\n";
    text += L"id=" + record.id + L"\r\nname=" + record.name + L"\r\nversion=" + record.version +
            L"\r\nexecutable=" + record.executable + L"\r\n";
    for (const std::wstring& key : record.userDataRegistry) {
        text += L"userdata.registry=" + key + L"\r\n";
    }
    for (const std::wstring& folder : record.userDataFolders) {
        text += L"userdata.folder=" + folder + L"\r\n";
    }
    for (const Action& action : record.actions) {
        text += std::wstring(typeName(action.type)) + L"|" + action.path;
        if (action.type == Action::Type::Value) {
            text += L"|" + action.name;
        }
        text += L"\r\n";
    }
    const std::string utf8 = toUtf8(text);
    return writeFile(path, utf8.data(), utf8.size());
}

/**
 * @brief 記録をファイルから読む。
 * @param path 記録のファイル。
 * @param record 中身の格納先。
 * @return 読めたらtrue。
 */
bool loadRecord(const std::wstring& path, Record& record) {
    std::vector<std::uint8_t> raw;
    if (!readFile(path, raw)) {
        return false;
    }
    const std::wstring text = fromUtf8(std::string(raw.begin(), raw.end()));
    record = Record{};
    bool header = false;
    for (const std::wstring& line : split(text, L'\n')) {
        if (!header) {
            header = line == L"WAKRECORD 1";
            if (!header) {
                return false;
            }
            continue;
        }
        const std::size_t bar = line.find(L'|');
        const std::size_t equal = line.find(L'=');
        if (bar != std::wstring::npos && (equal == std::wstring::npos || bar < equal)) {
            Action action;
            const std::wstring type = line.substr(0, bar);
            std::wstring rest = line.substr(bar + 1);
            if (type == L"dir") action.type = Action::Type::Dir;
            else if (type == L"file") action.type = Action::Type::File;
            else if (type == L"key") action.type = Action::Type::Key;
            else if (type == L"emptykey") action.type = Action::Type::EmptyKey;
            else if (type == L"value") action.type = Action::Type::Value;
            else continue;
            if (action.type == Action::Type::Value) {
                const std::size_t second = rest.find(L'|');
                if (second == std::wstring::npos) {
                    continue;
                }
                action.name = rest.substr(second + 1);
                rest = rest.substr(0, second);
            }
            action.path = rest;
            record.actions.push_back(action);
        } else if (equal != std::wstring::npos) {
            const std::wstring key = line.substr(0, equal);
            const std::wstring value = line.substr(equal + 1);
            if (key == L"id") record.id = value;
            else if (key == L"name") record.name = value;
            else if (key == L"version") record.version = value;
            else if (key == L"executable") record.executable = value;
            else if (key == L"userdata.registry") record.userDataRegistry.push_back(value);
            else if (key == L"userdata.folder") record.userDataFolders.push_back(value);
        }
    }
    return header;
}

/**
 * @brief キーがあるかを返す(HKEY_CURRENT_USERの中)。
 * @param path キーのパス。
 * @return あればtrue。
 */
bool keyExists(const std::wstring& path) {
    HKEY key = nullptr;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, path.c_str(), 0, KEY_READ, &key) != ERROR_SUCCESS) {
        return false;
    }
    RegCloseKey(key);
    return true;
}

/**
 * @brief 文字列の値を書く(キーが無ければ作る)。
 * @param path キーのパス(HKEY_CURRENT_USERの中)。
 * @param name 値の名前。空なら既定の値。
 * @param value 値。
 * @return 書けたらtrue。
 */
bool setString(const std::wstring& path, const std::wstring& name, const std::wstring& value) {
    return RegSetKeyValueW(HKEY_CURRENT_USER, path.c_str(), name.empty() ? nullptr : name.c_str(), REG_SZ,
                           value.c_str(), static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t))) == ERROR_SUCCESS;
}

/**
 * @brief 数の値を書く(キーが無ければ作る)。
 * @param path キーのパス(HKEY_CURRENT_USERの中)。
 * @param name 値の名前。
 * @param value 値。
 * @return 書けたらtrue。
 */
bool setNumber(const std::wstring& path, const std::wstring& name, DWORD value) {
    return RegSetKeyValueW(HKEY_CURRENT_USER, path.c_str(), name.c_str(), REG_DWORD, &value, sizeof(value)) ==
           ERROR_SUCCESS;
}

/**
 * @brief 文字列の値を読む。
 * @param root 読むところ(HKEY_CURRENT_USERなど)。
 * @param path キーのパス。
 * @param name 値の名前。
 * @return 値。無ければ空。
 */
std::wstring getString(HKEY root, const std::wstring& path, const std::wstring& name) {
    wchar_t buffer[2048] = {};
    DWORD size = sizeof(buffer) - sizeof(wchar_t);
    if (RegGetValueW(root, path.c_str(), name.c_str(), RRF_RT_REG_SZ, nullptr, buffer, &size) != ERROR_SUCCESS) {
        return std::wstring();
    }
    return buffer;
}

/**
 * @brief キーとその中身をすべて消す。
 * @param path キーのパス(HKEY_CURRENT_USERの中)。
 */
void deleteKeyTree(const std::wstring& path) {
    RegDeleteTreeW(HKEY_CURRENT_USER, path.c_str());
    RegDeleteKeyW(HKEY_CURRENT_USER, path.c_str());
}

/**
 * @brief キーが空(下のキーも値も無い)なら消す。
 * @param path キーのパス(HKEY_CURRENT_USERの中)。
 */
void deleteKeyIfEmpty(const std::wstring& path) {
    HKEY key = nullptr;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, path.c_str(), 0, KEY_READ, &key) != ERROR_SUCCESS) {
        return;
    }
    DWORD subKeys = 0;
    DWORD values = 0;
    const bool empty = RegQueryInfoKeyW(key, nullptr, nullptr, nullptr, &subKeys, nullptr, nullptr, &values, nullptr,
                                        nullptr, nullptr, nullptr) == ERROR_SUCCESS &&
                       subKeys == 0 && values == 0;
    RegCloseKey(key);
    if (empty) {
        RegDeleteKeyW(HKEY_CURRENT_USER, path.c_str());
    }
}

/**
 * @brief フォルダとその中身を消す。ジャンクションなど(リパースポイント)の先へは入らない。
 * @param path フォルダ。
 */
void deleteFolderTree(const std::wstring& path) {
    WIN32_FIND_DATAW found{};
    HANDLE find = FindFirstFileW(joinPath(path, L"*").c_str(), &found);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            const std::wstring name = found.cFileName;
            if (name == L"." || name == L"..") {
                continue;
            }
            const std::wstring child = joinPath(path, name);
            if ((found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) &&
                !(found.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
                deleteFolderTree(child);
            } else if (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                RemoveDirectoryW(child.c_str());  // リパースポイントは、つながりだけを外す(先の中身は消さない)。
            } else {
                SetFileAttributesW(child.c_str(), FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(child.c_str());
            }
        } while (FindNextFileW(find, &found));
        FindClose(find);
    }
    RemoveDirectoryW(path.c_str());
}

/**
 * @brief 作ったもの1つを元に戻す(消す)。
 * @param action 作ったもの。
 */
void undo(const Action& action) {
    switch (action.type) {
    case Action::Type::File:
        SetFileAttributesW(action.path.c_str(), FILE_ATTRIBUTE_NORMAL);
        if (!DeleteFileW(action.path.c_str()) && GetLastError() != ERROR_FILE_NOT_FOUND) {
            logLine(L"Cannot delete the file: %ls  %ls", action.path.c_str(), errorText(GetLastError()).c_str());
        }
        break;
    case Action::Type::Dir:
        RemoveDirectoryW(action.path.c_str());  // 空でなければ消えない(ほかの人が置いたファイルを消さない)。
        break;
    case Action::Type::Key:
        deleteKeyTree(action.path);
        break;
    case Action::Type::EmptyKey:
        deleteKeyIfEmpty(action.path);
        break;
    case Action::Type::Value:
        RegDeleteKeyValueW(HKEY_CURRENT_USER, action.path.c_str(), action.name.c_str());
        break;
    }
}

/** @brief 1回のインストールの作業。作ったものを順に覚え、失敗したら巻き戻す。 */
class Session {
public:
    std::vector<Action> actions;                                 ///< 作ったもの(作った順)。
    std::vector<std::pair<std::wstring, std::wstring>> backups;  ///< 置き換えたファイルと、その控えの場所。

    /**
     * @brief キーを、途中のキーも含めて作る。新しく作ったキーは「空なら消す」として覚える。
     * @param path キーのパス(HKEY_CURRENT_USERの中)。
     * @return 作れた(既にあった)ならtrue。
     */
    bool ensureKey(const std::wstring& path) {
        if (path.empty() || keyExists(path)) {
            return true;
        }
        const std::size_t slash = path.find_last_of(L'\\');
        if (slash != std::wstring::npos && !ensureKey(path.substr(0, slash))) {
            return false;
        }
        HKEY key = nullptr;
        if (RegCreateKeyExW(HKEY_CURRENT_USER, path.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr) !=
            ERROR_SUCCESS) {
            return false;
        }
        RegCloseKey(key);
        actions.push_back({Action::Type::EmptyKey, path, L"", false});
        return true;
    }

    /**
     * @brief 自分のキーを作り直す(前の版の中身が残らないよう、あれば消してから作る)。中身ごと自分のものとして覚える。
     * @param path キーのパス(HKEY_CURRENT_USERの中)。
     * @return 作れたらtrue。
     */
    bool ownKey(const std::wstring& path) {
        const std::size_t slash = path.find_last_of(L'\\');
        if (slash != std::wstring::npos && !ensureKey(path.substr(0, slash))) {
            return false;
        }
        const bool existed = keyExists(path);
        if (existed) {
            RegDeleteTreeW(HKEY_CURRENT_USER, path.c_str());
        }
        HKEY key = nullptr;
        if (RegCreateKeyExW(HKEY_CURRENT_USER, path.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr) !=
            ERROR_SUCCESS) {
            return false;
        }
        RegCloseKey(key);
        actions.push_back({Action::Type::Key, path, L"", existed});
        return true;
    }

    /**
     * @brief ほかのアプリと共有するキーに、値を1つ足す。
     * @param path キーのパス(HKEY_CURRENT_USERの中)。
     * @param name 値の名前。
     * @param value 値。
     * @return 書けたらtrue。
     */
    bool addValue(const std::wstring& path, const std::wstring& name, const std::wstring& value) {
        if (!ensureKey(path)) {
            return false;
        }
        const bool existed = RegGetValueW(HKEY_CURRENT_USER, path.c_str(), name.c_str(), RRF_RT_ANY, nullptr, nullptr,
                                          nullptr) == ERROR_SUCCESS;
        if (!setString(path, name, value)) {
            return false;
        }
        actions.push_back({Action::Type::Value, path, name, existed});
        return true;
    }

    /**
     * @brief フォルダを、途中のフォルダも含めて作る。新しく作ったフォルダを覚える。
     * @param path フォルダ。
     * @return 作れた(既にあった)ならtrue。
     */
    bool ensureDirectory(const std::wstring& path) {
        std::vector<std::wstring> created;
        const bool ok = createDirectories(path, &created);
        for (const std::wstring& dir : created) {
            actions.push_back({Action::Type::Dir, dir, L"", false});
        }
        return ok;
    }

    /**
     * @brief ファイルを置く。あれば控えのフォルダへ移してから置く(失敗したときに戻すため)。
     * @param path 置く場所。
     * @param data 中身。
     * @param size バイト数。
     * @param backupDir 控えのフォルダ。
     * @param error 失敗した理由の格納先。
     * @return 置けたらtrue。
     */
    bool placeFile(const std::wstring& path, const void* data, std::size_t size, const std::wstring& backupDir,
                   std::wstring& error) {
        if (!ensureDirectory(parentPath(path))) {
            error = L"Cannot create the folder: " + parentPath(path) + L"\n" + errorText(GetLastError());
            return false;
        }
        const bool existed = fileExists(path);
        if (existed) {
            const std::wstring backup = joinPath(backupDir, std::to_wstring(backups.size()));
            SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
            if (!MoveFileExW(path.c_str(), backup.c_str(), MOVEFILE_REPLACE_EXISTING)) {
                error = L"Cannot replace the file (it may be in use): " + path + L"\n" + errorText(GetLastError());
                return false;
            }
            backups.emplace_back(path, backup);
        }
        if (!writeFile(path, data, size)) {
            error = L"Cannot write the file: " + path + L"\n" + errorText(GetLastError());
            if (existed) {
                MoveFileExW(backups.back().second.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING);
                backups.pop_back();
            }
            return false;
        }
        actions.push_back({Action::Type::File, path, L"", existed});
        return true;
    }

    /** @brief 失敗したときに巻き戻す。新しく作ったものを消し、置き換えたファイルを戻す。 */
    void rollback() {
        for (auto it = actions.rbegin(); it != actions.rend(); ++it) {
            if (!it->existedBefore) {
                undo(*it);
            }
        }
        for (auto it = backups.rbegin(); it != backups.rend(); ++it) {
            MoveFileExW(it->second.c_str(), it->first.c_str(), MOVEFILE_REPLACE_EXISTING);
        }
    }
};

/**
 * @brief ショートカット(.lnk)を作る。
 * @param linkPath ショートカットの場所。
 * @param target 開くexe。
 * @param description 説明(マウスを乗せたときに出る)。
 * @return 作れたらtrue。
 */
bool createShortcut(const std::wstring& linkPath, const std::wstring& target, const std::wstring& description) {
    Microsoft::WRL::ComPtr<IShellLinkW> link;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link)))) {
        return false;
    }
    link->SetPath(target.c_str());
    link->SetWorkingDirectory(parentPath(target).c_str());
    link->SetDescription(description.c_str());
    link->SetIconLocation(target.c_str(), 0);
    Microsoft::WRL::ComPtr<IPersistFile> file;
    return SUCCEEDED(link.As(&file)) && SUCCEEDED(file->Save(linkPath.c_str(), TRUE));
}

/**
 * @brief 今日の日付を「20261003」の形で返す(「アプリ」一覧のインストール日)。
 * @return 日付の文字列。
 */
std::wstring today() {
    SYSTEMTIME now{};
    GetLocalTime(&now);
    wchar_t text[16];
    std::swprintf(text, 16, L"%04u%02u%02u", now.wYear, now.wMonth, now.wDay);
    return text;
}

/**
 * @brief パスの区切りごとの部分に、アプリの識別名と同じ名前があるかを返す。
 * @param parts パスを区切った部分。
 * @param id アプリの識別名。
 * @return あればtrue。
 */
bool containsId(const std::vector<std::wstring>& parts, const std::wstring& id) {
    return std::any_of(parts.begin(), parts.end(), [&](const std::wstring& part) { return equalsIgnoreCase(part, id); });
}

/**
 * @brief 「データも削除」で消すキーとして安全かを返す。
 * @param key 「HKCU\Software\...」の形のキー。
 * @param id アプリの識別名。
 * @param subKey HKEY_CURRENT_USERからのパスの格納先。
 * @return 安全ならtrue。HKCU\Software\ の下で、途中にアプリの識別名の階層があるキーだけ
 *         (例: HKCU\Software\FramePlayer、HKCU\Software\会社名\FramePlayer)。Windowsや共有の場所は消さない。
 */
bool safeUserDataKey(const std::wstring& key, const std::wstring& id, std::wstring& subKey) {
    const std::wstring prefix = L"HKCU\\Software\\";
    if (key.size() <= prefix.size() || !equalsIgnoreCase(key.substr(0, prefix.size()), prefix)) {
        return false;
    }
    subKey = key.substr(5);  // 「HKCU\」を外す。
    const std::vector<std::wstring> parts = split(key.substr(prefix.size()), L'\\');
    if (parts.empty() || !containsId(parts, id)) {
        return false;
    }
    for (const wchar_t* shared : {L"Microsoft", L"Classes", L"Policies", L"Wow6432Node", L"RegisteredApplications"}) {
        if (equalsIgnoreCase(parts.front(), shared)) {
            return false;
        }
    }
    return true;
}

/**
 * @brief 「データも削除」で消すフォルダとして安全かを返す。
 * @param folder フォルダ(正規の形)。
 * @param id アプリの識別名。
 * @return 安全ならtrue。LocalAppData・AppData(Roaming)の中で、その下の途中にアプリの識別名の階層があるフォルダだけ
 *         (例: %LOCALAPPDATA%\FramePlayer)。Temp・Programs・Microsoft など共有の場所を消さないため。
 */
bool safeUserDataFolder(const std::wstring& folder, const std::wstring& id) {
    for (const GUID* known : {&FOLDERID_LocalAppData, &FOLDERID_RoamingAppData}) {
        const std::wstring base = fullPath(knownFolder(*known));
        if (base.empty() || !isInside(folder, base) || equalsIgnoreCase(folder, base)) {
            continue;
        }
        const std::vector<std::wstring> parts = split(folder.substr(base.size()), L'\\');
        if (!parts.empty() && containsId(parts, id) && !equalsIgnoreCase(parts.front(), L"Microsoft") &&
            !equalsIgnoreCase(parts.front(), L"Programs") && !equalsIgnoreCase(parts.front(), L"Temp") &&
            !equalsIgnoreCase(parts.front(), L"Packages")) {
            return true;
        }
    }
    return false;
}

}  // namespace

std::wstring defaultInstallDir(const Manifest& manifest) {
    return fullPath(expandPath(manifest.installDir, std::wstring()));
}

ExistingInstall findExistingInstall(const std::wstring& id) {
    ExistingInstall existing;
    const std::wstring key = std::wstring(kUninstallRoot) + id;
    existing.dir = getString(HKEY_CURRENT_USER, key, L"InstallLocation");
    existing.version = getString(HKEY_CURRENT_USER, key, L"DisplayVersion");
    existing.found = !existing.dir.empty() && fileExists(joinPath(existing.dir, kRecordName));
    return existing;
}

bool checkInstallDir(const std::wstring& dir, std::wstring& error) {
    if (dir.size() < 4 || dir[1] != L':' || dir[2] != L'\\') {
        error = L"Specify an install folder that starts with a drive, such as \"C:\\...\": " + dir;
        return false;
    }
    // Windowsやユーザーの大事なフォルダそのもの・その親には入れない(中のファイルを上書きしないように)。
    const GUID* folders[] = {&FOLDERID_Windows,        &FOLDERID_System,       &FOLDERID_ProgramFiles,
                             &FOLDERID_ProgramFilesX86, &FOLDERID_Profile,      &FOLDERID_LocalAppData,
                             &FOLDERID_RoamingAppData,  &FOLDERID_Desktop,      &FOLDERID_Documents,
                             &FOLDERID_Downloads,       &FOLDERID_UserProgramFiles, &FOLDERID_Programs};
    for (const GUID* id : folders) {
        const std::wstring special = fullPath(knownFolder(*id));
        if (!special.empty() && isInside(special, dir)) {
            error = L"Cannot install into this folder (it is an important Windows or user folder): " + dir;
            return false;
        }
    }
    if (isInside(dir, fullPath(knownFolder(FOLDERID_Windows)))) {
        error = L"Cannot install inside the Windows folder: " + dir;
        return false;
    }
    // 既にあるフォルダは、空か、このインストーラーで入れたもの(記録がある)だけ。
    if (directoryExists(dir) && !fileExists(joinPath(dir, kRecordName))) {
        WIN32_FIND_DATAW found{};
        HANDLE find = FindFirstFileW(joinPath(dir, L"*").c_str(), &found);
        bool empty = true;
        if (find != INVALID_HANDLE_VALUE) {
            do {
                const std::wstring name = found.cFileName;
                empty = empty && (name == L"." || name == L"..");
            } while (empty && FindNextFileW(find, &found));
            FindClose(find);
        }
        if (!empty) {
            error = L"Cannot install into a folder that contains other files (specify an empty folder or "
                    L"a new folder): " + dir;
            return false;
        }
    }
    return true;
}

std::vector<std::wstring> findRunningApps(const std::vector<std::wstring>& files) {
    std::vector<std::wstring> names;
    if (files.empty()) {
        return names;
    }
    DWORD session = 0;
    wchar_t sessionKey[CCH_RM_SESSION_KEY + 1] = {};
    if (RmStartSession(&session, 0, sessionKey) != ERROR_SUCCESS) {
        return names;
    }
    std::vector<LPCWSTR> paths;
    for (const std::wstring& file : files) {
        paths.push_back(file.c_str());
    }
    if (RmRegisterResources(session, static_cast<UINT>(paths.size()), paths.data(), 0, nullptr, 0, nullptr) ==
        ERROR_SUCCESS) {
        UINT needed = 0;
        UINT count = 0;
        DWORD reasons = 0;
        DWORD result = RmGetList(session, &needed, &count, nullptr, &reasons);
        if (result == ERROR_MORE_DATA && needed > 0) {
            std::vector<RM_PROCESS_INFO> infos(needed);
            count = needed;
            result = RmGetList(session, &needed, &count, infos.data(), &reasons);
            if (result == ERROR_SUCCESS) {
                for (UINT i = 0; i < count; ++i) {
                    names.emplace_back(infos[i].strAppName);
                }
            }
        }
    }
    RmEndSession(session);
    return names;
}

bool closeRunningApps(const std::vector<std::wstring>& files) {
    DWORD session = 0;
    wchar_t sessionKey[CCH_RM_SESSION_KEY + 1] = {};
    if (RmStartSession(&session, 0, sessionKey) != ERROR_SUCCESS) {
        return false;
    }
    std::vector<LPCWSTR> paths;
    for (const std::wstring& file : files) {
        paths.push_back(file.c_str());
    }
    // まず閉じるよう頼み、応じなければ終了させる(RmForceShutdown)。
    bool ok = RmRegisterResources(session, static_cast<UINT>(paths.size()), paths.data(), 0, nullptr, 0, nullptr) ==
                  ERROR_SUCCESS &&
              RmShutdown(session, RmForceShutdown, nullptr) == ERROR_SUCCESS;
    RmEndSession(session);
    return ok && findRunningApps(files).empty();
}

std::vector<std::wstring> installedFiles(const Manifest& manifest, const std::wstring& installDir) {
    std::vector<std::wstring> paths;
    for (const FileEntry& file : manifest.files) {
        const std::wstring path = joinPath(installDir, file.target);
        if (fileExists(path)) {
            paths.push_back(path);
        }
    }
    const std::wstring uninstaller = joinPath(installDir, kUninstallerName);
    if (fileExists(uninstaller)) {
        paths.push_back(uninstaller);
    }
    return paths;
}

bool install(const Manifest& manifest, const std::vector<PackageFile>& files, const InstallOptions& options,
             const ProgressCallback& progress, std::wstring& error) {
    const std::wstring dir = options.installDir;
    auto report = [&](int percent, const std::wstring& step) {
        logLine(L"[%3d%%] %ls", percent, step.c_str());
        if (progress) {
            progress(percent, step);
        }
    };
    if (!checkInstallDir(dir, error)) {
        return false;
    }
    // 前の版の記録(更新のとき)。
    const std::wstring recordPath = joinPath(dir, kRecordName);
    Record previous;
    const bool upgrading = loadRecord(recordPath, previous);
    if (upgrading && !equalsIgnoreCase(previous.id, manifest.id)) {
        error = L"This folder already contains another application (" + previous.name + L"): " + dir;
        return false;
    }

    Session session;
    report(0, L"Copying files");
    if (!session.ensureDirectory(dir)) {
        error = L"Cannot create the install folder: " + dir + L"\n" + errorText(GetLastError());
        return false;
    }
    const std::wstring backupDir = joinPath(dir, kBackupName);
    createDirectories(backupDir, nullptr);
    SetFileAttributesW(backupDir.c_str(), FILE_ATTRIBUTE_HIDDEN);

    bool ok = true;
    std::size_t totalBytes = 0;
    for (const PackageFile& file : files) {
        totalBytes += file.data.size();
    }
    std::size_t doneBytes = 0;
    for (const PackageFile& file : files) {
        if (!session.placeFile(joinPath(dir, file.target), file.data.data(), file.data.size(), backupDir, error)) {
            ok = false;
            break;
        }
        doneBytes += file.data.size();
        report(static_cast<int>(70 * doneBytes / std::max<std::size_t>(1, totalBytes)), file.target);
    }

    // 自分自身(セットアップのexe)を、アンインストール用に写す。
    const std::wstring exePath = joinPath(dir, manifest.executable);
    const std::wstring uninstaller = joinPath(dir, kUninstallerName);
    if (ok) {
        wchar_t self[MAX_PATH * 2];
        GetModuleFileNameW(nullptr, self, static_cast<DWORD>(std::size(self)));
        std::vector<std::uint8_t> selfData;
        if (equalsIgnoreCase(fullPath(self), fullPath(uninstaller))) {
            // インストール先のUninstall.exeから直接(修復として)動かしたときは、写す必要が無い。
            session.actions.push_back({Action::Type::File, uninstaller, L"", true});
        } else if (!readFile(self, selfData) ||
                   !session.placeFile(uninstaller, selfData.data(), selfData.size(), backupDir, error)) {
            if (error.empty()) {
                error = L"Cannot copy the uninstaller";
            }
            ok = false;
        }
    }

    // レジストリ: 「アプリ」一覧への登録。
    if (ok) {
        report(75, L"Registering with Windows");
        const std::wstring key = std::wstring(kUninstallRoot) + manifest.id;
        std::size_t bytes = totalBytes;
        ok = session.ownKey(key) && setString(key, L"DisplayName", manifest.name) &&
             setString(key, L"DisplayVersion", manifest.version) && setString(key, L"Publisher", manifest.publisher) &&
             setString(key, L"DisplayIcon", exePath + L",0") && setString(key, L"InstallLocation", dir) &&
             setString(key, L"UninstallString", L"\"" + uninstaller + L"\" --uninstall") &&
             setString(key, L"QuietUninstallString", L"\"" + uninstaller + L"\" --uninstall /S") &&
             setString(key, L"InstallDate", today()) && setNumber(key, L"NoModify", 1) &&
             setNumber(key, L"NoRepair", 1) &&
             setNumber(key, L"EstimatedSize", static_cast<DWORD>((bytes + 1023) / 1024));
        if (ok && !manifest.url.empty()) {
            ok = setString(key, L"URLInfoAbout", manifest.url);
        }
        if (ok && !manifest.description.empty()) {
            ok = setString(key, L"Comments", manifest.description);
        }
        // 「ファイル名を指定して実行」や、ほかのプログラムからexeの場所を見つけられるようにする(App Paths)。
        const std::wstring exeName = exePath.substr(exePath.find_last_of(L'\\') + 1);
        const std::wstring appPath = std::wstring(kAppPathsRoot) + L"\\" + exeName;
        ok = ok && session.ownKey(appPath) && setString(appPath, L"", exePath) &&
             setString(appPath, L"Path", parentPath(exePath));
        if (!ok && error.empty()) {
            error = L"Cannot write to the registry";
        }
    }

    // レジストリ: 関連付け(右クリック・「プログラムから開く」・既定のアプリの候補)。
    if (ok && !options.extensions.empty() && !manifest.progId.empty()) {
        report(85, L"Registering file types");
        const std::wstring classes = L"Software\\Classes\\";
        const std::wstring command = L"\"" + exePath + L"\" \"%1\"";
        const std::wstring icon = exePath + L",0";
        const std::wstring exeName = exePath.substr(exePath.find_last_of(L'\\') + 1);
        const std::wstring typeName = manifest.typeDescription.empty() ? manifest.name : manifest.typeDescription;
        // FramePlayer.Video のような、開き方の定義。
        const std::wstring progKey = classes + manifest.progId;
        ok = session.ownKey(progKey) && setString(progKey, L"", typeName) &&
             setString(progKey + L"\\DefaultIcon", L"", icon) && setString(progKey + L"\\shell\\open\\command", L"", command);
        // 「別のアプリを選択」の画面での表示名と、開ける拡張子。
        const std::wstring appKey = classes + L"Applications\\" + exeName;
        ok = ok && session.ownKey(appKey) && setString(appKey, L"FriendlyAppName", manifest.name) &&
             setString(appKey + L"\\DefaultIcon", L"", icon) && setString(appKey + L"\\shell\\open\\command", L"", command);
        // 設定の「既定のアプリ」に出すための、アプリの能力の宣言。
        const std::wstring capabilities = L"Software\\" + manifest.id + L"\\Capabilities";
        ok = ok && session.ownKey(capabilities) && setString(capabilities, L"ApplicationName", manifest.name) &&
             setString(capabilities, L"ApplicationDescription",
                       manifest.description.empty() ? manifest.name : manifest.description) &&
             setString(capabilities, L"ApplicationIcon", icon);
        for (const std::wstring& extension : options.extensions) {
            if (!ok) {
                break;
            }
            ok = setString(appKey + L"\\SupportedTypes", extension, L"") &&
                 setString(capabilities + L"\\FileAssociations", extension, manifest.progId) &&
                 session.addValue(classes + extension + L"\\OpenWithProgids", manifest.progId, L"");
            if (ok && options.contextMenu && !manifest.contextMenu.empty()) {
                // 右クリックの項目。拡張子ごとの共有の場所に、自分の項目のキーだけを足す。
                const std::wstring verb = classes + L"SystemFileAssociations\\" + extension + L"\\shell\\" + manifest.progId;
                ok = session.ownKey(verb) && setString(verb, L"", manifest.contextMenu) &&
                     setString(verb, L"Icon", icon) && setString(verb + L"\\command", L"", command);
            }
        }
        ok = ok && session.addValue(L"Software\\RegisteredApplications", manifest.id, capabilities);
        if (!ok && error.empty()) {
            error = L"Cannot register file types";
        }
    }

    // スタートメニュー。
    if (ok && manifest.startMenuShortcut) {
        report(92, L"Adding to the Start menu");
        const std::wstring link = joinPath(knownFolder(FOLDERID_Programs), manifest.name + L".lnk");
        const bool existed = fileExists(link);
        if (createShortcut(link, exePath, manifest.description.empty() ? manifest.name : manifest.description)) {
            session.actions.push_back({Action::Type::File, link, L"", existed});
        } else {
            logLine(L"Cannot create the Start menu shortcut (continuing): %ls", link.c_str());
        }
    }

    if (!ok) {
        logLine(L"Failed; rolling back: %ls", error.c_str());
        session.rollback();
        deleteFolderTree(backupDir);
        RemoveDirectoryW(dir.c_str());
        return false;
    }

    // 記録を作る。前の版から引き継ぐのは、途中に作ったフォルダ・キー(空になったら消すもの)。
    Record record;
    record.id = manifest.id;
    record.name = manifest.name;
    record.version = manifest.version;
    record.executable = manifest.executable;
    for (const std::wstring& key : manifest.userDataRegistry) {
        record.userDataRegistry.push_back(key);
    }
    for (const std::wstring& folder : manifest.userDataFolders) {
        record.userDataFolders.push_back(fullPath(expandPath(folder, dir)));
    }
    auto inNew = [&](const Action& action) {
        return std::any_of(session.actions.begin(), session.actions.end(),
                           [&](const Action& a) { return a.same(action); });
    };
    for (const Action& old : previous.actions) {
        if ((old.type == Action::Type::Dir || old.type == Action::Type::EmptyKey) && !inNew(old)) {
            record.actions.push_back(old);
        }
    }
    record.actions.insert(record.actions.end(), session.actions.begin(), session.actions.end());
    if (!saveRecord(recordPath, record)) {
        error = L"Cannot write the install record: " + recordPath;
        session.rollback();
        return false;
    }
    // 前の版にあって今の版に無いもの(使わなくなったファイル・登録)を消す。
    for (auto it = previous.actions.rbegin(); it != previous.actions.rend(); ++it) {
        if (it->type != Action::Type::Dir && it->type != Action::Type::EmptyKey && !inNew(*it)) {
            undo(*it);
        }
    }
    deleteFolderTree(backupDir);
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, nullptr, nullptr);  // エクスプローラーに関連付けの変更を知らせる。
    report(100, upgrading ? L"Updated" : L"Installed");
    return true;
}

bool readRecordInfo(const std::wstring& installDir, RecordInfo& info) {
    Record record;
    if (!loadRecord(joinPath(installDir, kRecordName), record)) {
        return false;
    }
    info.id = record.id;
    info.name = record.name;
    info.version = record.version;
    info.executable = record.executable;
    info.hasUserData = !record.userDataRegistry.empty() || !record.userDataFolders.empty();
    // 関連付けた拡張子は「Software\Classes\.mp4\OpenWithProgids」に足した値から、右クリックは
    // 「...\SystemFileAssociations\...」のキーから分かる。
    const std::wstring classes = L"Software\\Classes\\";
    const std::wstring openWith = L"\\OpenWithProgids";
    for (const Action& action : record.actions) {
        if (action.type == Action::Type::Value && action.path.size() > classes.size() + openWith.size() &&
            equalsIgnoreCase(action.path.substr(0, classes.size()), classes) &&
            equalsIgnoreCase(action.path.substr(action.path.size() - openWith.size()), openWith)) {
            info.extensions.push_back(
                action.path.substr(classes.size(), action.path.size() - classes.size() - openWith.size()));
        }
        if (action.type == Action::Type::Key && action.path.find(L"\\SystemFileAssociations\\") != std::wstring::npos) {
            info.contextMenu = true;
        }
    }
    return true;
}

bool uninstall(const std::wstring& installDir, bool removeUserData, std::wstring& error) {
    const std::wstring recordPath = joinPath(installDir, kRecordName);
    Record record;
    if (!loadRecord(recordPath, record)) {
        error = L"The install record was not found: " + recordPath;
        return false;
    }
    logLine(L"Uninstall: %ls %ls (%ls)", record.name.c_str(), record.version.c_str(), installDir.c_str());
    for (auto it = record.actions.rbegin(); it != record.actions.rend(); ++it) {
        // インストール先の外のファイル(スタートメニューのショートカットなど)も、記録にあるものだけを消す。
        undo(*it);
    }
    if (removeUserData) {
        for (const std::wstring& key : record.userDataRegistry) {
            std::wstring subKey;
            if (safeUserDataKey(key, record.id, subKey)) {
                logLine(L"Deleting data: %ls", key.c_str());
                deleteKeyTree(subKey);
            } else {
                logLine(L"Not deleted because it is not safe: %ls", key.c_str());
            }
        }
        for (const std::wstring& folder : record.userDataFolders) {
            const std::wstring full = fullPath(folder);
            if (safeUserDataFolder(full, record.id)) {
                logLine(L"Deleting data: %ls", full.c_str());
                deleteFolderTree(full);
            } else {
                logLine(L"Not deleted because it is not safe: %ls", full.c_str());
            }
        }
    }
    DeleteFileW(recordPath.c_str());
    deleteFolderTree(joinPath(installDir, kBackupName));
    RemoveDirectoryW(installDir.c_str());  // 空になっていれば消える。
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, nullptr, nullptr);
    error.clear();
    return true;
}

}  // namespace wak
