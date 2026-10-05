/**
 * @file Manifest.cpp
 * @brief インストールするアプリの説明(INI形式)の読み書きの実装。
 */
#include "setup/Manifest.h"

#include "setup/Common.h"
#include "setup/Requirements.h"

#include <shlobj.h>

#include <cwctype>
#include <utility>

namespace wak {

namespace {

/**
 * @brief 文字列を小文字にする(拡張子の比較用)。
 * @param text 文字列。
 * @return 小文字にした文字列。
 */
std::wstring toLowerText(std::wstring text) {
    for (wchar_t& c : text) {
        c = static_cast<wchar_t>(std::towlower(c));
    }
    return text;
}

/**
 * @brief 「yes/no」「1/0」「true/false」を読む。
 * @param text 文字列。
 * @param fallback 読めないときの値。
 * @return 読んだ値。
 */
bool parseBool(const std::wstring& text, bool fallback) {
    if (equalsIgnoreCase(text, L"yes") || equalsIgnoreCase(text, L"true") || text == L"1") {
        return true;
    }
    if (equalsIgnoreCase(text, L"no") || equalsIgnoreCase(text, L"false") || text == L"0") {
        return false;
    }
    return fallback;
}

/**
 * @brief 識別名に使える文字(英数字と . _ -)だけかを返す。
 * @param text 文字列。
 * @return 使える文字だけで、空でなければtrue。
 */
bool isIdentifier(const std::wstring& text) {
    if (text.empty() || text.size() > 64) {
        return false;
    }
    for (wchar_t c : text) {
        if (!(std::iswalnum(c) && c < 128) && c != L'.' && c != L'_' && c != L'-') {
            return false;
        }
    }
    return true;
}

/**
 * @brief インストール先からの相対パスとして安全かを返す(外へ出る「..」・ドライブ指定・先頭の「\」を許さない)。
 * @param path 相対パス。
 * @return 安全ならtrue。
 */
bool isSafeRelativePath(const std::wstring& path) {
    if (path.empty() || path.find(L':') != std::wstring::npos || path[0] == L'\\' || path[0] == L'/') {
        return false;
    }
    for (const std::wstring& part : split(path, L'\\')) {
        for (const std::wstring& piece : split(part, L'/')) {
            if (piece == L".." || piece == L".") {
                return false;
            }
        }
    }
    return true;
}

/**
 * @brief パスの区切りを「\」に揃える。
 * @param path パス。
 * @return 揃えたパス。
 */
std::wstring backslashes(std::wstring path) {
    for (wchar_t& c : path) {
        if (c == L'/') {
            c = L'\\';
        }
    }
    return path;
}

/**
 * @brief 文字列の中の置き換え文字を置き換える(英字の大文字・小文字は区別しない)。
 * @param text 元の文字列。
 * @param token 置き換え文字(例: {LocalAppData})。
 * @param value 置き換える値。
 * @return 置き換えた文字列。
 */
std::wstring replaceToken(std::wstring text, const std::wstring& token, const std::wstring& value) {
    for (std::size_t pos = 0; pos + token.size() <= text.size();) {
        if (equalsIgnoreCase(text.substr(pos, token.size()), token)) {
            text.replace(pos, token.size(), value);
            pos += value.size();
        } else {
            ++pos;
        }
    }
    return text;
}

}  // namespace

bool Manifest::parse(const std::wstring& text, Manifest& manifest, std::wstring& error) {
    manifest = Manifest{};
    std::wstring section;
    int lineNumber = 0;
    std::size_t start = 0;
    while (start < text.size()) {
        std::size_t end = text.find(L'\n', start);
        if (end == std::wstring::npos) {
            end = text.size();
        }
        std::wstring line = trim(text.substr(start, end - start));
        start = end + 1;
        ++lineNumber;
        if (!line.empty() && line[0] == 0xFEFF) {
            line = trim(line.substr(1));  // 先頭のUTF-8の印。
        }
        // 空行と、行頭が「;」「#」の行(注釈)は読み飛ばす。値の途中の「;」は区切りに使うので注釈にしない。
        if (line.empty() || line[0] == L';' || line[0] == L'#') {
            continue;
        }
        if (line.front() == L'[' && line.back() == L']') {
            section = trim(line.substr(1, line.size() - 2));
            continue;
        }
        const std::size_t equal = line.find(L'=');
        if (equal == std::wstring::npos) {
            error = L"Line " + std::to_wstring(lineNumber) + L": not in the \"name=value\" form";
            return false;
        }
        const std::wstring key = trim(line.substr(0, equal));
        const std::wstring value = trim(line.substr(equal + 1));
        if (equalsIgnoreCase(section, L"App")) {
            if (equalsIgnoreCase(key, L"Id")) manifest.id = value;
            else if (equalsIgnoreCase(key, L"Name")) manifest.name = value;
            else if (equalsIgnoreCase(key, L"Version")) manifest.version = value;
            else if (equalsIgnoreCase(key, L"Publisher")) manifest.publisher = value;
            else if (equalsIgnoreCase(key, L"Description")) manifest.description = value;
            else if (equalsIgnoreCase(key, L"Url")) manifest.url = value;
            else if (equalsIgnoreCase(key, L"Executable")) manifest.executable = backslashes(value);
            else if (equalsIgnoreCase(key, L"InstallDir")) manifest.installDir = backslashes(value);
            else if (equalsIgnoreCase(key, L"StartMenuShortcut")) manifest.startMenuShortcut = parseBool(value, true);
            else if (equalsIgnoreCase(key, L"SetupIcon")) manifest.setupIcon = backslashes(value);
        } else if (equalsIgnoreCase(section, L"Files")) {
            // 「元=先」。先を省くと元のファイル名にする。
            const std::wstring source = backslashes(key);
            std::wstring target = backslashes(value);
            if (target.empty()) {
                const std::size_t slash = source.find_last_of(L'\\');
                target = slash == std::wstring::npos ? source : source.substr(slash + 1);
            }
            manifest.files.push_back({source, target});
        } else if (equalsIgnoreCase(section, L"FileTypes")) {
            if (equalsIgnoreCase(key, L"ProgId")) manifest.progId = value;
            else if (equalsIgnoreCase(key, L"Description")) manifest.typeDescription = value;
            else if (equalsIgnoreCase(key, L"Extensions")) manifest.extensions = split(value, L';');
            else if (equalsIgnoreCase(key, L"ContextMenu")) manifest.contextMenu = value;
            else if (equalsIgnoreCase(key, L"Optional")) manifest.fileTypesOptional = parseBool(value, true);
            else if (key.size() > 8 && equalsIgnoreCase(key.substr(0, 8), L"Require.")) {
                manifest.requirements[toLowerText(L"." + key.substr(8))] = value;
            } else if (key.size() > 12 && equalsIgnoreCase(key.substr(0, 12), L"RequireNote.")) {
                manifest.requirementNotes[toLowerText(L"." + key.substr(12))] = value;
            }
        } else if (equalsIgnoreCase(section, L"UserData")) {
            if (equalsIgnoreCase(key, L"Registry")) manifest.userDataRegistry.push_back(value);
            else if (equalsIgnoreCase(key, L"Folder")) manifest.userDataFolders.push_back(backslashes(value));
        }
    }

    // 必要な項目と、形の確認。
    if (!isIdentifier(manifest.id)) {
        error = L"[App] Id must use letters, digits, and . _ - (up to 64 characters)";
        return false;
    }
    if (manifest.name.empty()) {
        manifest.name = manifest.id;
    }
    if (manifest.installDir.empty()) {
        manifest.installDir = L"{LocalPrograms}\\" + manifest.id;
    }
    if (manifest.files.empty()) {
        error = L"[Files] lists no files to install";
        return false;
    }
    bool hasExecutable = false;
    for (const FileEntry& file : manifest.files) {
        if (!isSafeRelativePath(file.target)) {
            error = L"[Files] targets must be relative to the install folder (.. is not allowed): " + file.target;
            return false;
        }
        hasExecutable = hasExecutable || equalsIgnoreCase(file.target, manifest.executable);
    }
    if (!hasExecutable) {
        error = L"[App] Executable is not one of the [Files] targets: " + manifest.executable;
        return false;
    }
    if (!manifest.progId.empty()) {
        if (!isIdentifier(manifest.progId) || manifest.extensions.empty()) {
            error = L"[FileTypes] needs ProgId (letters, digits, and . _ -) and Extensions (like .mp4;.mov)";
            return false;
        }
        for (const std::wstring& extension : manifest.extensions) {
            if (extension.size() < 2 || extension[0] != L'.' || !isIdentifier(extension.substr(1))) {
                error = L"[FileTypes] Extensions must look like \".mp4;.mov\": " + extension;
                return false;
            }
        }
        for (const auto& [extension, expression] : manifest.requirements) {
            bool listed = false;
            for (const std::wstring& candidate : manifest.extensions) {
                listed = listed || equalsIgnoreCase(candidate, extension);
            }
            if (!listed) {
                error = L"[FileTypes] Require names an extension that is not in Extensions: " + extension;
                return false;
            }
            if (!isValidRequirement(expression)) {
                error = L"[FileTypes] Require" + extension + L" is not valid: " + expression;
                return false;
            }
        }
    }
    return true;
}

std::wstring Manifest::serialize() const {
    // インストール時に読む項目だけを書く(元のファイルの場所やセットアップのアイコンは、作るときにしか使わない)。
    std::wstring text = L"[App]\r\n";
    auto put = [&](const wchar_t* key, const std::wstring& value) {
        if (!value.empty()) {
            text += std::wstring(key) + L"=" + value + L"\r\n";
        }
    };
    put(L"Id", id);
    put(L"Name", name);
    put(L"Version", version);
    put(L"Publisher", publisher);
    put(L"Description", description);
    put(L"Url", url);
    put(L"Executable", executable);
    put(L"InstallDir", installDir);
    put(L"StartMenuShortcut", startMenuShortcut ? L"yes" : L"no");
    text += L"[Files]\r\n";
    for (const FileEntry& file : files) {
        text += file.target + L"=" + file.target + L"\r\n";
    }
    if (!progId.empty()) {
        text += L"[FileTypes]\r\n";
        put(L"ProgId", progId);
        put(L"Description", typeDescription);
        std::wstring joined;
        for (const std::wstring& extension : extensions) {
            joined += (joined.empty() ? L"" : L";") + extension;
        }
        put(L"Extensions", joined);
        put(L"ContextMenu", contextMenu);
        put(L"Optional", fileTypesOptional ? L"yes" : L"no");
        for (const auto& [extension, expression] : requirements) {
            put((L"Require" + extension).c_str(), expression);
        }
        for (const auto& [extension, note] : requirementNotes) {
            put((L"RequireNote" + extension).c_str(), note);
        }
    }
    text += L"[UserData]\r\n";
    for (const std::wstring& key : userDataRegistry) {
        put(L"Registry", key);
    }
    for (const std::wstring& folder : userDataFolders) {
        put(L"Folder", folder);
    }
    return text;
}

std::wstring expandPath(const std::wstring& text, const std::wstring& installDir) {
    const std::wstring localAppData = knownFolder(FOLDERID_LocalAppData);
    std::wstring result = replaceToken(text, L"{LocalPrograms}", joinPath(localAppData, L"Programs"));
    result = replaceToken(result, L"{LocalAppData}", localAppData);
    result = replaceToken(result, L"{AppData}", knownFolder(FOLDERID_RoamingAppData));
    result = replaceToken(result, L"{InstallDir}", installDir);
    return result;
}

}  // namespace wak
