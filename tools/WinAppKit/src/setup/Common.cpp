/**
 * @file Common.cpp
 * @brief WinAppSetupで共通に使う小さな関数の実装。
 */
#include "setup/Common.h"

#include <shlobj.h>

#include <cstdarg>
#include <cstdio>
#include <cwctype>

namespace wak {

namespace {

std::wstring g_logPath;  ///< 記録の書き出し先。

}  // namespace

std::wstring fromUtf8(const std::string& text) {
    if (text.empty()) {
        return std::wstring();
    }
    const int length = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0);
    std::wstring result(static_cast<std::size_t>(length), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), length);
    return result;
}

std::string toUtf8(const std::wstring& text) {
    if (text.empty()) {
        return std::string();
    }
    const int length =
        WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string result(static_cast<std::size_t>(length), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), length, nullptr,
                        nullptr);
    return result;
}

std::wstring trim(const std::wstring& text) {
    std::size_t first = 0;
    std::size_t last = text.size();
    while (first < last && std::iswspace(text[first])) {
        ++first;
    }
    while (last > first && std::iswspace(text[last - 1])) {
        --last;
    }
    return text.substr(first, last - first);
}

std::vector<std::wstring> split(const std::wstring& text, wchar_t separator) {
    std::vector<std::wstring> parts;
    std::size_t start = 0;
    while (start <= text.size()) {
        const std::size_t end = text.find(separator, start);
        const std::wstring part = trim(text.substr(start, end == std::wstring::npos ? std::wstring::npos : end - start));
        if (!part.empty()) {
            parts.push_back(part);
        }
        if (end == std::wstring::npos) {
            break;
        }
        start = end + 1;
    }
    return parts;
}

bool equalsIgnoreCase(const std::wstring& a, const std::wstring& b) {
    return CompareStringOrdinal(a.c_str(), static_cast<int>(a.size()), b.c_str(), static_cast<int>(b.size()), TRUE) ==
           CSTR_EQUAL;
}

std::wstring knownFolder(const GUID& id) {
    PWSTR path = nullptr;
    std::wstring result;
    if (SUCCEEDED(SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, nullptr, &path))) {
        result = path;
    }
    CoTaskMemFree(path);
    return result;
}

std::wstring joinPath(const std::wstring& base, const std::wstring& name) {
    if (base.empty()) {
        return name;
    }
    if (base.back() == L'\\' || base.back() == L'/') {
        return base + name;
    }
    return base + L"\\" + name;
}

std::wstring parentPath(const std::wstring& path) {
    const std::size_t slash = path.find_last_of(L"\\/");
    if (slash == std::wstring::npos || slash == 0) {
        return std::wstring();
    }
    // 「C:\」のようなドライブの直下なら、ドライブ(「C:\」)を返す。
    if (slash == 2 && path[1] == L':') {
        return path.substr(0, 3);
    }
    return path.substr(0, slash);
}

std::wstring fullPath(const std::wstring& path) {
    if (path.empty()) {
        return path;
    }
    const DWORD length = GetFullPathNameW(path.c_str(), 0, nullptr, nullptr);
    if (length == 0) {
        return path;
    }
    std::wstring result(length, L'\0');
    const DWORD written = GetFullPathNameW(path.c_str(), length, result.data(), nullptr);
    result.resize(written);
    // ドライブの直下(「C:\」)以外は、末尾の「\」を外す。
    while (result.size() > 3 && (result.back() == L'\\' || result.back() == L'/')) {
        result.pop_back();
    }
    return result;
}

bool isInside(const std::wstring& path, const std::wstring& folder) {
    if (folder.empty() || path.size() < folder.size()) {
        return false;
    }
    if (!equalsIgnoreCase(path.substr(0, folder.size()), folder)) {
        return false;
    }
    // 「C:\Foo」と「C:\FooBar」を取り違えないよう、続きが区切りか終わりかを確かめる。
    return path.size() == folder.size() || path[folder.size()] == L'\\' || folder.back() == L'\\';
}

bool fileExists(const std::wstring& path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}

bool directoryExists(const std::wstring& path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY);
}

bool createDirectories(const std::wstring& path, std::vector<std::wstring>* created) {
    if (path.empty() || directoryExists(path)) {
        return !path.empty();
    }
    const std::wstring parent = parentPath(path);
    if (!parent.empty() && parent != path && !createDirectories(parent, created)) {
        return false;
    }
    if (CreateDirectoryW(path.c_str(), nullptr)) {
        if (created) {
            created->push_back(path);
        }
        return true;
    }
    return GetLastError() == ERROR_ALREADY_EXISTS && directoryExists(path);
}

bool readFile(const std::wstring& path, std::vector<std::uint8_t>& data) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    LARGE_INTEGER size{};
    bool ok = GetFileSizeEx(file, &size) && size.QuadPart < (1LL << 31);  // 2GBまで(インストールする中身として十分)。
    if (ok) {
        data.resize(static_cast<std::size_t>(size.QuadPart));
        DWORD read = 0;
        ok = data.empty() || (ReadFile(file, data.data(), static_cast<DWORD>(data.size()), &read, nullptr) &&
                              read == data.size());
    }
    CloseHandle(file);
    return ok;
}

bool writeFile(const std::wstring& path, const void* data, std::size_t size) {
    HANDLE file =
        CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD written = 0;
    const bool ok =
        size == 0 || (WriteFile(file, data, static_cast<DWORD>(size), &written, nullptr) && written == size);
    CloseHandle(file);
    return ok;
}

std::wstring errorText(DWORD code) {
    wchar_t* buffer = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr,
                   code, 0, reinterpret_cast<wchar_t*>(&buffer), 0, nullptr);
    std::wstring text = buffer ? trim(buffer) : std::wstring();
    LocalFree(buffer);
    wchar_t number[32];
    std::swprintf(number, 32, L" (%lu)", static_cast<unsigned long>(code));
    return text + number;
}

void openLog(const std::wstring& path) {
    g_logPath = path;
    writeFile(path, "\xEF\xBB\xBF", 3);  // UTF-8の印(メモ帳などで文字化けしないように)。
}

const std::wstring& logPath() {
    return g_logPath;
}

void logLine(const wchar_t* format, ...) {
    wchar_t buffer[2048];
    va_list args;
    va_start(args, format);
    std::vswprintf(buffer, 2048, format, args);
    va_end(args);
    const std::string line = toUtf8(buffer) + "\r\n";
    if (!g_logPath.empty()) {
        HANDLE file = CreateFileW(g_logPath.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, OPEN_ALWAYS,
                                  FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file != INVALID_HANDLE_VALUE) {
            DWORD written = 0;
            WriteFile(file, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
            CloseHandle(file);
        }
    }
    // 画面を持つ形のexeでも、コマンドラインからパイプにつないで実行されたときは標準出力が使える。
    HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
    if (out && out != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(out, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
    }
}

}  // namespace wak
