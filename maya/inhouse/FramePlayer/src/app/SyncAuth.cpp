/**
 * @file SyncAuth.cpp
 * @brief 連携の相手を確かめるための秘密鍵とHMAC-SHA256の実装。
 */
#include "app/SyncAuth.h"

#include <windows.h>
#include <aclapi.h>
#include <bcrypt.h>
#include <sddl.h>
#include <shlobj.h>

#include <cstdio>
#include <vector>

namespace frameplayer::syncauth {

namespace {

constexpr std::size_t kKeyBytes = 32;  ///< 鍵の長さ(バイト)。16進数で64文字。

/**
 * @brief バイト列を16進数の文字列にする。
 * @param data バイト列。
 * @param size バイト数。
 * @return 小文字の16進数。
 */
std::string toHex(const unsigned char* data, std::size_t size) {
    static const char digits[] = "0123456789abcdef";
    std::string text(size * 2, '0');
    for (std::size_t i = 0; i < size; ++i) {
        text[i * 2] = digits[data[i] >> 4];
        text[i * 2 + 1] = digits[data[i] & 0x0F];
    }
    return text;
}

/**
 * @brief 鍵の文字列として正しいか(16進数64文字か)を返す。
 * @param key 鍵。
 * @return 正しければtrue。
 */
bool isValidKey(const std::string& key) {
    if (key.size() != kKeyBytes * 2) {
        return false;
    }
    for (char c : key) {
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
            return false;
        }
    }
    return true;
}

/**
 * @brief 鍵ファイルのパスを返す(フォルダが無ければ作る)。
 * @return %LOCALAPPDATA%\FramePlayer\sync.key。取得できなければ空。
 */
std::wstring keyPath() {
    PWSTR base = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &base))) {
        return std::wstring();
    }
    std::wstring folder = std::wstring(base) + L"\\FramePlayer";
    CoTaskMemFree(base);
    CreateDirectoryW(folder.c_str(), nullptr);  // 既にあれば何もしない。権限は親フォルダ(本人だけ)を引き継ぐ。
    return folder + L"\\sync.key";
}

/**
 * @brief ファイルを、持ち主(本人)とSYSTEMだけが読み書きできるようにする。親フォルダの権限は引き継がない。
 * @param path 対象のファイル。
 * @return 設定できた場合true。
 * @note %LOCALAPPDATA% は通常は本人だけが読めるが、PCによっては他のツールがグループやアプリコンテナ
 *       (サンドボックス化されたアプリ)の読み取りを足していることがあるため、鍵ファイルには明示的に設定する。
 *       管理者はWindowsの仕組み上いつでも読めるので、守る対象には含めない。
 */
bool restrictToOwner(const std::wstring& path) {
    // P: 親の権限を引き継がない。OW: 持ち主(Owner Rights)、SY: SYSTEM に全ての権限。
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(L"D:P(A;;FA;;;OW)(A;;FA;;;SY)", SDDL_REVISION_1,
                                                              &descriptor, nullptr)) {
        return false;
    }
    BOOL present = FALSE;
    BOOL defaulted = FALSE;
    PACL dacl = nullptr;
    bool ok = GetSecurityDescriptorDacl(descriptor, &present, &dacl, &defaulted) && present;
    if (ok) {
        ok = SetNamedSecurityInfoW(const_cast<LPWSTR>(path.c_str()), SE_FILE_OBJECT,
                                   DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr,
                                   dacl, nullptr) == ERROR_SUCCESS;
    }
    LocalFree(descriptor);
    return ok;
}

}  // namespace

std::string randomHex(std::size_t bytes) {
    std::vector<unsigned char> data(bytes);
    if (!BCRYPT_SUCCESS(BCryptGenRandom(nullptr, data.data(), static_cast<ULONG>(data.size()),
                                        BCRYPT_USE_SYSTEM_PREFERRED_RNG))) {
        return std::string();
    }
    return toHex(data.data(), data.size());
}

bool loadOrCreateKey(std::string& key) {
    const std::wstring path = keyPath();
    if (path.empty()) {
        return false;
    }
    // 既にあれば読む(前後の空白・改行は除く)。
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL,
                              nullptr);
    if (file != INVALID_HANDLE_VALUE) {
        char buffer[256] = {};
        DWORD read = 0;
        const BOOL ok = ReadFile(file, buffer, sizeof(buffer) - 1, &read, nullptr);
        CloseHandle(file);
        std::string text = ok ? std::string(buffer, read) : std::string();
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r' || text.back() == ' ')) {
            text.pop_back();
        }
        if (isValidKey(text)) {
            restrictToOwner(path);  // 以前の版で作った鍵ファイルにも、読める相手の制限をかける。
            key = text;
            return true;
        }
    }
    // 無い・壊れている場合は作り直す。
    const std::string created = randomHex(kKeyBytes);
    if (created.empty()) {
        return false;
    }
    file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD written = 0;
    const BOOL ok = WriteFile(file, created.data(), static_cast<DWORD>(created.size()), &written, nullptr);
    CloseHandle(file);
    if (!ok || written != created.size() || !restrictToOwner(path)) {
        DeleteFileW(path.c_str());  // 読める相手を制限できない鍵は使わない。
        return false;
    }
    key = created;
    return true;
}

std::string hmacHex(const std::string& key, const std::string& message) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    if (!BCRYPT_SUCCESS(
            BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, BCRYPT_ALG_HANDLE_HMAC_FLAG))) {
        return std::string();
    }
    unsigned char digest[32] = {};
    const NTSTATUS status =
        BCryptHash(algorithm, reinterpret_cast<PUCHAR>(const_cast<char*>(key.data())), static_cast<ULONG>(key.size()),
                   reinterpret_cast<PUCHAR>(const_cast<char*>(message.data())), static_cast<ULONG>(message.size()),
                   digest, sizeof(digest));
    BCryptCloseAlgorithmProvider(algorithm, 0);
    return BCRYPT_SUCCESS(status) ? toHex(digest, sizeof(digest)) : std::string();
}

bool constantTimeEquals(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) {
        return false;
    }
    unsigned char difference = 0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        difference |= static_cast<unsigned char>(a[i] ^ b[i]);
    }
    return difference == 0;
}

}  // namespace frameplayer::syncauth
