/**
 * @file Package.cpp
 * @brief インストールする中身をまとめる形式の読み書きの実装。
 */
#include "setup/Package.h"

#include "setup/Common.h"

#include <windows.h>
#include <compressapi.h>

#include <cstring>

namespace wak {

namespace {

constexpr char kMagic[8] = {'W', 'A', 'K', 'P', 'K', 'G', '0', '1'};
constexpr std::uint8_t kStored = 0;  ///< そのまま格納。
constexpr std::uint8_t kLzms = 1;    ///< LZMSで圧縮して格納。

/**
 * @brief 数をリトルエンディアンで書き足す。
 * @param out 書き足す先。
 * @param value 数。
 * @param bytes バイト数(1・4・8)。
 */
void putNumber(std::vector<std::uint8_t>& out, std::uint64_t value, int bytes) {
    for (int i = 0; i < bytes; ++i) {
        out.push_back(static_cast<std::uint8_t>((value >> (8 * i)) & 0xFF));
    }
}

/** @brief バイト列を先頭から順に読む。範囲を越えて読もうとしたら失敗にする(壊れたデータ対策)。 */
class Reader {
public:
    /**
     * @brief 読むバイト列を決める。
     * @param data 先頭。
     * @param size バイト数。
     */
    Reader(const std::uint8_t* data, std::size_t size) : data_(data), size_(size) {}

    /**
     * @brief 数を読む。
     * @param bytes バイト数(1・4・8)。
     * @param value 読んだ数の格納先。
     * @return 読めたらtrue。
     */
    bool number(int bytes, std::uint64_t& value) {
        if (size_ - position_ < static_cast<std::size_t>(bytes)) {
            return false;
        }
        value = 0;
        for (int i = 0; i < bytes; ++i) {
            value |= static_cast<std::uint64_t>(data_[position_ + i]) << (8 * i);
        }
        position_ += static_cast<std::size_t>(bytes);
        return true;
    }

    /**
     * @brief 決まった長さのバイト列を取り出す(写さずに場所だけ返す)。
     * @param length 長さ。
     * @param bytes 先頭の格納先。
     * @return 読めたらtrue。
     */
    bool bytes(std::uint64_t length, const std::uint8_t*& bytes) {
        if (length > size_ - position_) {
            return false;
        }
        bytes = data_ + position_;
        position_ += static_cast<std::size_t>(length);
        return true;
    }

private:
    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t position_ = 0;
};

/**
 * @brief LZMSで圧縮する。
 * @param input 元のバイト列。
 * @param output 圧縮したバイト列の格納先。
 * @return 圧縮できたらtrue。
 */
bool compress(const std::vector<std::uint8_t>& input, std::vector<std::uint8_t>& output) {
    COMPRESSOR_HANDLE compressor = nullptr;
    if (!CreateCompressor(COMPRESS_ALGORITHM_LZMS, nullptr, &compressor)) {
        return false;
    }
    // まず必要な大きさを尋ね(足りないと答える)、その大きさで圧縮する。
    SIZE_T needed = 0;
    Compress(compressor, input.data(), input.size(), nullptr, 0, &needed);
    output.resize(needed);
    SIZE_T written = 0;
    const bool ok = needed > 0 && Compress(compressor, input.data(), input.size(), output.data(), output.size(), &written);
    CloseCompressor(compressor);
    output.resize(ok ? written : 0);
    return ok;
}

/**
 * @brief LZMSで圧縮したバイト列を戻す。
 * @param input 圧縮したバイト列。
 * @param inputSize バイト数。
 * @param output 戻したバイト列の格納先(元の大きさにしておく)。
 * @return 戻せて、大きさが元と同じならtrue。
 */
bool decompress(const std::uint8_t* input, std::size_t inputSize, std::vector<std::uint8_t>& output) {
    DECOMPRESSOR_HANDLE decompressor = nullptr;
    if (!CreateDecompressor(COMPRESS_ALGORITHM_LZMS, nullptr, &decompressor)) {
        return false;
    }
    SIZE_T written = 0;
    const bool ok = Decompress(decompressor, input, inputSize, output.data(), output.size(), &written) &&
                    written == output.size();
    CloseDecompressor(decompressor);
    return ok;
}

}  // namespace

bool writePackage(const Manifest& manifest, const std::vector<PackageFile>& files, std::vector<std::uint8_t>& out,
                  std::wstring& error) {
    out.assign(kMagic, kMagic + sizeof(kMagic));
    const std::string text = toUtf8(manifest.serialize());
    putNumber(out, text.size(), 4);
    out.insert(out.end(), text.begin(), text.end());
    putNumber(out, files.size(), 4);
    for (const PackageFile& file : files) {
        const std::string name = toUtf8(file.target);
        putNumber(out, name.size(), 4);
        out.insert(out.end(), name.begin(), name.end());
        // 圧縮して小さくなるときだけ圧縮して入れる(小さいファイルや圧縮済みの画像はそのまま)。
        std::vector<std::uint8_t> packed;
        const bool useLzms = !file.data.empty() && compress(file.data, packed) && packed.size() < file.data.size();
        const std::vector<std::uint8_t>& stored = useLzms ? packed : file.data;
        putNumber(out, file.data.size(), 8);
        putNumber(out, stored.size(), 8);
        putNumber(out, useLzms ? kLzms : kStored, 1);
        out.insert(out.end(), stored.begin(), stored.end());
    }
    error.clear();
    return true;
}

bool readPackage(const std::uint8_t* data, std::size_t size, Manifest& manifest, std::vector<PackageFile>& files,
                 std::wstring& error) {
    error = L"The setup contents are corrupt (download the setup file again).";
    if (size < sizeof(kMagic) || std::memcmp(data, kMagic, sizeof(kMagic)) != 0) {
        return false;
    }
    Reader reader(data + sizeof(kMagic), size - sizeof(kMagic));
    std::uint64_t length = 0;
    const std::uint8_t* bytes = nullptr;
    if (!reader.number(4, length) || !reader.bytes(length, bytes)) {
        return false;
    }
    std::wstring parseError;
    if (!Manifest::parse(fromUtf8(std::string(reinterpret_cast<const char*>(bytes), static_cast<std::size_t>(length))),
                         manifest, parseError)) {
        error = L"Cannot read the application description: " + parseError;
        return false;
    }
    std::uint64_t count = 0;
    if (!reader.number(4, count) || count != manifest.files.size()) {
        return false;
    }
    files.clear();
    for (std::uint64_t i = 0; i < count; ++i) {
        std::uint64_t original = 0;
        std::uint64_t stored = 0;
        std::uint64_t method = 0;
        const std::uint8_t* name = nullptr;
        if (!reader.number(4, length) || !reader.bytes(length, name) || !reader.number(8, original) ||
            !reader.number(8, stored) || !reader.number(1, method) || !reader.bytes(stored, bytes) ||
            original > (1ULL << 31)) {
            return false;
        }
        PackageFile file;
        file.target = fromUtf8(std::string(reinterpret_cast<const char*>(name), static_cast<std::size_t>(length)));
        if (!equalsIgnoreCase(file.target, manifest.files[static_cast<std::size_t>(i)].target)) {
            return false;
        }
        file.data.resize(static_cast<std::size_t>(original));
        if (method == kStored) {
            if (stored != original) {
                return false;
            }
            std::memcpy(file.data.data(), bytes, static_cast<std::size_t>(stored));
        } else if (method != kLzms || !decompress(bytes, static_cast<std::size_t>(stored), file.data)) {
            return false;
        }
        files.push_back(std::move(file));
    }
    error.clear();
    return true;
}

}  // namespace wak
