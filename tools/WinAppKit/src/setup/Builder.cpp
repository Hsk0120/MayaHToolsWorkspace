/**
 * @file Builder.cpp
 * @brief セットアップのexeを作る処理の実装。
 */
#include "setup/Builder.h"

#include "setup/Common.h"
#include "setup/Manifest.h"
#include "setup/Package.h"

#include <windows.h>

#include <cstdio>
#include <cstring>

namespace wak {

namespace {

/**
 * @brief exeのバージョン情報から「1.2.3」のようなバージョンを読む。
 * @param path exeのパス。
 * @return バージョン。読めなければ空。4つ目の数(ビルド番号)は0なら省く。
 */
std::wstring readFileVersion(const std::wstring& path) {
    DWORD handle = 0;
    const DWORD size = GetFileVersionInfoSizeW(path.c_str(), &handle);
    if (size == 0) {
        return std::wstring();
    }
    std::vector<std::uint8_t> info(size);
    VS_FIXEDFILEINFO* fixed = nullptr;
    UINT length = 0;
    if (!GetFileVersionInfoW(path.c_str(), 0, size, info.data()) ||
        !VerQueryValueW(info.data(), L"\\", reinterpret_cast<void**>(&fixed), &length) || !fixed) {
        return std::wstring();
    }
    wchar_t text[64];
    const unsigned build = LOWORD(fixed->dwProductVersionLS);
    if (build != 0) {
        std::swprintf(text, 64, L"%u.%u.%u.%u", HIWORD(fixed->dwProductVersionMS), LOWORD(fixed->dwProductVersionMS),
                      HIWORD(fixed->dwProductVersionLS), build);
    } else {
        std::swprintf(text, 64, L"%u.%u.%u", HIWORD(fixed->dwProductVersionMS), LOWORD(fixed->dwProductVersionMS),
                      HIWORD(fixed->dwProductVersionLS));
    }
    return text;
}

/**
 * @brief 設定ファイルに書かれたパスを、実際のパスにする。
 * @param baseDir 設定ファイルのフォルダ。
 * @param path 書かれたパス。相対パスなら設定ファイルのフォルダから、絶対パス(C:\… や \\server\…)ならそのまま。
 * @return 正規の形のパス。
 */
std::wstring resolvePath(const std::wstring& baseDir, const std::wstring& path) {
    const bool absolute = path.size() > 1 && (path[1] == L':' || (path[0] == L'\\' && path[1] == L'\\'));
    return fullPath(absolute ? path : joinPath(baseDir, path));
}

#pragma pack(push, 2)
/** @brief .icoファイルの目次の1項目(ファイル上の形)。 */
struct IcoEntry {
    BYTE width;
    BYTE height;
    BYTE colors;
    BYTE reserved;
    WORD planes;
    WORD bitCount;
    DWORD bytes;
    DWORD offset;
};
/** @brief exeのアイコンのまとめ(RT_GROUP_ICON)の1項目。.icoの目次と違い、位置の代わりにリソース番号を持つ。 */
struct GroupEntry {
    BYTE width;
    BYTE height;
    BYTE colors;
    BYTE reserved;
    WORD planes;
    WORD bitCount;
    DWORD bytes;
    WORD id;
};
#pragma pack(pop)

/**
 * @brief .icoファイルを、exeのアイコンのリソースとして足す(画像ごとにRT_ICON、まとめをRT_GROUP_ICONの1番)。
 * @param update リソースの書き換えの手続き(BeginUpdateResourceの結果)。
 * @param ico .icoファイルの中身。
 * @return 足せたらtrue。
 * @note 番号が一番小さいアイコンのまとめが、エクスプローラーでのexeのアイコンになる。
 */
bool addIcon(HANDLE update, const std::vector<std::uint8_t>& ico) {
    if (ico.size() < 6) {
        return false;
    }
    const WORD count = static_cast<WORD>(ico[4] | (ico[5] << 8));
    if (ico.size() < 6 + static_cast<std::size_t>(count) * sizeof(IcoEntry)) {
        return false;
    }
    std::vector<std::uint8_t> group(6 + static_cast<std::size_t>(count) * sizeof(GroupEntry));
    std::memcpy(group.data(), ico.data(), 6);  // 見出し(予約・種類・数)は同じ形。
    for (WORD i = 0; i < count; ++i) {
        IcoEntry entry{};
        std::memcpy(&entry, ico.data() + 6 + i * sizeof(IcoEntry), sizeof(entry));
        if (static_cast<std::size_t>(entry.offset) + entry.bytes > ico.size()) {
            return false;
        }
        const WORD id = static_cast<WORD>(i + 1);
        if (!UpdateResourceW(update, RT_ICON, MAKEINTRESOURCEW(id), MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
                             const_cast<std::uint8_t*>(ico.data() + entry.offset), entry.bytes)) {
            return false;
        }
        GroupEntry groupEntry{entry.width, entry.height, entry.colors, 0, entry.planes, entry.bitCount, entry.bytes, id};
        std::memcpy(group.data() + 6 + i * sizeof(GroupEntry), &groupEntry, sizeof(groupEntry));
    }
    return UpdateResourceW(update, RT_GROUP_ICON, MAKEINTRESOURCEW(1), MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
                           group.data(), static_cast<DWORD>(group.size())) != FALSE;
}

}  // namespace

int buildSetup(const std::wstring& manifestPath, const std::wstring& outputPath) {
    const std::wstring manifestFull = fullPath(manifestPath);
    const std::wstring baseDir = parentPath(manifestFull);
    std::vector<std::uint8_t> raw;
    if (!readFile(manifestFull, raw)) {
        logLine(L"Cannot read the settings file: %ls", manifestFull.c_str());
        return 2;
    }
    Manifest manifest;
    std::wstring error;
    if (!Manifest::parse(fromUtf8(std::string(raw.begin(), raw.end())), manifest, error)) {
        logLine(L"Error in the settings file: %ls", error.c_str());
        return 2;
    }

    // 入れるファイルを読む。
    std::vector<PackageFile> files;
    for (const FileEntry& entry : manifest.files) {
        PackageFile file;
        file.target = entry.target;
        const std::wstring source = resolvePath(baseDir, entry.source);
        if (!readFile(source, file.data)) {
            logLine(L"Cannot read the file: %ls", source.c_str());
            return 2;
        }
        logLine(L"  %ls  (%zu bytes)", entry.target.c_str(), file.data.size());
        if (manifest.version.empty() && equalsIgnoreCase(entry.target, manifest.executable)) {
            manifest.version = readFileVersion(source);
        }
        files.push_back(std::move(file));
    }
    if (manifest.version.empty()) {
        logLine(L"Unknown version. Write [App] Version, or add version information to the main exe.");
        return 2;
    }

    std::vector<std::uint8_t> package;
    if (!writePackage(manifest, files, package, error)) {
        logLine(L"Cannot pack the contents: %ls", error.c_str());
        return 2;
    }

    // このexe(セットアップの本体)を写し、写した方にリソースを足す。
    wchar_t self[MAX_PATH * 2];
    GetModuleFileNameW(nullptr, self, static_cast<DWORD>(std::size(self)));
    const std::wstring output = fullPath(outputPath);
    createDirectories(parentPath(output), nullptr);
    if (!CopyFileW(self, output.c_str(), FALSE)) {
        logLine(L"Cannot write: %ls  %ls", output.c_str(), errorText(GetLastError()).c_str());
        return 2;
    }
    HANDLE update = BeginUpdateResourceW(output.c_str(), FALSE);
    bool ok = update != nullptr;
    if (ok) {
        ok = UpdateResourceW(update, RT_RCDATA, kPackageResource, MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
                             package.data(), static_cast<DWORD>(package.size())) != FALSE;
    }
    if (ok && !manifest.setupIcon.empty()) {
        std::vector<std::uint8_t> ico;
        const std::wstring iconPath = resolvePath(baseDir, manifest.setupIcon);
        if (!readFile(iconPath, ico) || !addIcon(update, ico)) {
            logLine(L"Cannot embed the icon: %ls", iconPath.c_str());
            ok = false;
        }
    }
    if (update && !EndUpdateResourceW(update, ok ? FALSE : TRUE)) {
        ok = false;
    }
    if (!ok) {
        logLine(L"Cannot create the setup exe: %ls", errorText(GetLastError()).c_str());
        DeleteFileW(output.c_str());
        return 2;
    }
    logLine(L"Created: %ls  (%ls %ls, contents %zu bytes)", output.c_str(), manifest.name.c_str(),
            manifest.version.c_str(), package.size());
    return 0;
}

}  // namespace wak
