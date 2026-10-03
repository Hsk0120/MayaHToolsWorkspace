/**
 * @file Settings.cpp
 * @brief 設定の読み書きの実装。
 */
#include "app/Settings.h"

#include <windows.h>

#include <algorithm>
#include <cwchar>

namespace frameplayer {

namespace {

constexpr wchar_t kSettingsKey[] = L"Software\\FramePlayer";  ///< 設定の保存先(HKEY_CURRENT_USERの下)。

/**
 * @brief DWORDの値を読む。
 * @param name 値の名前。
 * @param value 読めた値の格納先。
 * @return 読めた場合true。
 */
bool readDword(const wchar_t* name, DWORD& value) {
    DWORD size = sizeof(value);
    return RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, name, RRF_RT_REG_DWORD, nullptr, &value, &size) ==
           ERROR_SUCCESS;
}

/**
 * @brief DWORDの値を書く(キーが無ければ作る)。
 * @param name 値の名前。
 * @param value 値。
 */
void writeDword(const wchar_t* name, DWORD value) {
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, name, REG_DWORD, &value, sizeof(value));
}

}  // namespace

void Settings::load() {
    DWORD value = 0;
    if (readDword(L"Volume", value)) {
        volume = std::clamp(static_cast<float>(value) / 100.0f, 0.0f, 1.0f);
    }
    if (readDword(L"Muted", value)) {
        muted = value != 0;
    }
    if (readDword(L"CacheMB", value)) {
        cacheMegabytes = std::clamp<std::size_t>(value, 64, 64 * 1024);
    }
    if (readDword(L"CacheSeconds", value)) {
        cacheSeconds = std::clamp<int>(static_cast<int>(value), 1, 24 * 60 * 60);
    }
    if (readDword(L"StartFrame", value)) {
        startFrame = static_cast<int>(value);  // 負の番号もそのまま(DWORDの値を符号付きとして読む)。
    }
    if (readDword(L"SyncPort", value) && value > 0 && value < 65536) {
        syncPort = static_cast<unsigned short>(value);
    }
    if (readDword(L"AutoPlay", value)) {
        autoPlay = value != 0;
    }

    // 最近使ったファイルはREG_MULTI_SZ(文字列を\0で区切って並べ、最後に\0をもう1つ置いたもの)で保存してある。
    DWORD size = 0;
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", RRF_RT_REG_MULTI_SZ, nullptr, nullptr, &size) !=
            ERROR_SUCCESS ||
        size == 0) {
        return;
    }
    std::vector<wchar_t> buffer(size / sizeof(wchar_t) + 1, L'\0');
    if (RegGetValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", RRF_RT_REG_MULTI_SZ, nullptr, buffer.data(),
                     &size) != ERROR_SUCCESS) {
        return;
    }
    recentFiles.clear();
    for (const wchar_t* p = buffer.data(); *p && recentFiles.size() < kMaxRecentFiles; p += wcslen(p) + 1) {
        recentFiles.emplace_back(p);
    }
}

void Settings::saveAudio() const {
    writeDword(L"Volume", static_cast<DWORD>(volume * 100.0f + 0.5f));
    writeDword(L"Muted", muted ? 1 : 0);
}

void Settings::saveStartFrame() const {
    writeDword(L"StartFrame", static_cast<DWORD>(startFrame));
}

void Settings::saveAutoPlay() const {
    writeDword(L"AutoPlay", autoPlay ? 1 : 0);
}

void Settings::saveRecentFiles() const {
    std::wstring data;
    for (const std::wstring& path : recentFiles) {
        data += path;
        data += L'\0';
    }
    data += L'\0';
    RegSetKeyValueW(HKEY_CURRENT_USER, kSettingsKey, L"RecentFiles", REG_MULTI_SZ, data.data(),
                    static_cast<DWORD>(data.size() * sizeof(wchar_t)));
}

void Settings::addRecentFile(const std::wstring& path) {
    // 同じファイルは先頭へ移す(大文字小文字を区別しない)。
    recentFiles.erase(std::remove_if(recentFiles.begin(), recentFiles.end(),
                                     [&](const std::wstring& item) { return _wcsicmp(item.c_str(), path.c_str()) == 0; }),
                      recentFiles.end());
    recentFiles.insert(recentFiles.begin(), path);
    if (recentFiles.size() > kMaxRecentFiles) {
        recentFiles.resize(kMaxRecentFiles);
    }
    saveRecentFiles();
}

}  // namespace frameplayer
