/**
 * @file Mp4SampleTable.cpp
 * @brief mp4/movのサンプルテーブルを読む処理の実装。
 *
 * 読むボックス(ISO/IEC 14496-12、QuickTimeも同じ構造):
 *   moov > trak > mdia > hdlr   トラックの種類('vide'なら映像)
 *                      > mdhd   時刻の単位(timescale)
 *                      > minf > stbl > stts  デコード時刻の間隔
 *                                    > ctts  デコード時刻から表示時刻へのずれ(Bフレームがあるとき)
 *                                    > stss  キーフレームの番号(無ければ全コマがキーフレーム)
 *                                    > stsz  コマ数の確認用
 *                                    > stsd > (avc1など) > colr  色の情報(H.273の番号)
 * 数値はすべてビッグエンディアン。
 */
#include "core/Mp4SampleTable.h"

#include <windows.h>

#include <algorithm>
#include <cstring>

namespace frameplayer {

namespace {

/// moovボックスとして受け付ける最大サイズ。これより大きいものは壊れているとみなす。
constexpr std::uint64_t kMaxMoovSize = 512ull << 20;

/**
 * @brief ビッグエンディアンの32ビット値を読む。
 * @param p 読む位置。
 * @return 値。
 */
std::uint32_t readU32(const std::uint8_t* p) {
    return (std::uint32_t{p[0]} << 24) | (std::uint32_t{p[1]} << 16) | (std::uint32_t{p[2]} << 8) | p[3];
}

/**
 * @brief ビッグエンディアンの64ビット値を読む。
 * @param p 読む位置。
 * @return 値。
 */
std::uint64_t readU64(const std::uint8_t* p) {
    return (std::uint64_t{readU32(p)} << 32) | readU32(p + 4);
}

/**
 * @brief 4文字のボックス名を比べる。
 * @param p ボックス名の位置。
 * @param name 比べる名前(4文字)。
 * @return 一致すればtrue。
 */
bool isType(const std::uint8_t* p, const char* name) {
    return std::memcmp(p, name, 4) == 0;
}

/** @brief メモリ上のボックスの範囲。 */
struct Range {
    const std::uint8_t* begin = nullptr;  ///< 中身の先頭(ヘッダーの直後)。
    const std::uint8_t* end = nullptr;    ///< 中身の終わり。
    bool valid() const { return begin != nullptr; }  ///< 見つかったか。
};

/**
 * @brief 範囲内の子ボックスを順に調べ、指定した名前のものを返す。
 * @param parent 探す範囲。
 * @param name ボックス名(4文字)。
 * @param skip 同じ名前のボックスのうち何番目を返すか(0なら最初)。
 * @return 見つかったボックスの中身の範囲。無ければ無効な範囲。
 */
Range findChild(Range parent, const char* name, int skip = 0) {
    const std::uint8_t* p = parent.begin;
    while (p && parent.end - p >= 8) {
        std::uint64_t size = readU32(p);
        std::size_t header = 8;
        if (size == 1) {
            if (parent.end - p < 16) {
                break;
            }
            size = readU64(p + 8);
            header = 16;
        } else if (size == 0) {
            size = static_cast<std::uint64_t>(parent.end - p);
        }
        if (size < header || size > static_cast<std::uint64_t>(parent.end - p)) {
            break;  // 壊れている。
        }
        if (isType(p + 4, name) && skip-- == 0) {
            return Range{p + header, p + size};
        }
        p += size;
    }
    return Range{};
}

/**
 * @brief ファイルの先頭から最上位のボックスをたどり、moovボックスの中身を読み込む。
 * @param path ファイルのパス。
 * @param moov 読み込んだ中身の格納先。
 * @return 読めた場合true。
 * @note 映像データ(mdat)は読み飛ばすので、ファイルが大きくても速い。
 */
bool readMoov(const std::wstring& path, std::vector<std::uint8_t>& moov) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                              nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    LARGE_INTEGER fileSize{};
    GetFileSizeEx(file, &fileSize);
    auto readAt = [&](std::uint64_t offset, void* buffer, DWORD bytes) {
        LARGE_INTEGER position;
        position.QuadPart = static_cast<LONGLONG>(offset);
        DWORD read = 0;
        return SetFilePointerEx(file, position, nullptr, FILE_BEGIN) && ReadFile(file, buffer, bytes, &read, nullptr) &&
               read == bytes;
    };

    bool found = false;
    std::uint64_t offset = 0;
    const std::uint64_t total = static_cast<std::uint64_t>(fileSize.QuadPart);
    while (offset + 8 <= total) {
        std::uint8_t header[16];
        if (!readAt(offset, header, 8)) {
            break;
        }
        std::uint64_t size = readU32(header);
        std::uint64_t headerSize = 8;
        if (size == 1) {
            if (!readAt(offset + 8, header + 8, 8)) {
                break;
            }
            size = readU64(header + 8);
            headerSize = 16;
        } else if (size == 0) {
            size = total - offset;
        }
        if (size < headerSize || offset + size > total) {
            break;
        }
        if (isType(header + 4, "moov")) {
            const std::uint64_t bodySize = size - headerSize;
            if (bodySize > kMaxMoovSize) {
                break;
            }
            moov.resize(static_cast<std::size_t>(bodySize));
            found = readAt(offset + headerSize, moov.data(), static_cast<DWORD>(bodySize));
            break;
        }
        offset += size;
    }
    CloseHandle(file);
    return found;
}

/**
 * @brief 映像の形式の説明(stsd)の最初の項目にあるcolrボックスから、色の情報を読む。
 * @param stbl stblボックスの中身。
 * @param table 格納先。読めなければ変えない。
 * @note 'nclx'(ISO/IEC 14496-12)は範囲の印まで、'nclc'(QuickTime)は3つの番号だけを持つ。
 *       'prof'(ICCプロファイル)は扱わない。
 */
void readColor(Range stbl, Mp4SampleTable& table) {
    const Range stsd = findChild(stbl, "stsd");
    // stsdの中身: 版とフラグ(4)、項目数(4)、その後に項目(ボックス)が並ぶ。
    if (!stsd.valid() || stsd.end - stsd.begin < 16) {
        return;
    }
    const std::uint8_t* entry = stsd.begin + 8;
    const std::uint32_t entrySize = readU32(entry);
    // 映像の項目は、ボックスの見出し(8)の後に決まった78バイトの説明があり、その後に子ボックスが並ぶ。
    constexpr std::ptrdiff_t kVisualHeader = 8 + 78;
    if (entrySize < kVisualHeader || entrySize > static_cast<std::uint64_t>(stsd.end - entry)) {
        return;
    }
    const Range colr = findChild(Range{entry + kVisualHeader, entry + entrySize}, "colr");
    if (!colr.valid() || colr.end - colr.begin < 10) {
        return;
    }
    const bool nclx = isType(colr.begin, "nclx");
    if (!nclx && !isType(colr.begin, "nclc")) {
        return;
    }
    auto readU16 = [](const std::uint8_t* p) { return (p[0] << 8) | p[1]; };
    table.colorPrimaries = readU16(colr.begin + 4);
    table.transferCharacteristics = readU16(colr.begin + 6);
    table.matrixCoefficients = readU16(colr.begin + 8);
    if (nclx && colr.end - colr.begin >= 11) {
        table.fullRange = (colr.begin[10] & 0x80) ? 1 : 0;
    }
}

}  // namespace

bool readMp4SampleTable(const std::wstring& path, Mp4SampleTable& table) {
    table = {};
    std::vector<std::uint8_t> moovData;
    if (!readMoov(path, moovData)) {
        return false;
    }
    const Range moov{moovData.data(), moovData.data() + moovData.size()};
    // mvexがあるのは断片化mp4。コマの情報がmoovの外(moof)にあるので対象外。
    if (findChild(moov, "mvex").valid()) {
        return false;
    }

    // 最初の映像トラックを探す(Media Foundationの「最初の映像ストリーム」と合わせる)。
    Range stbl;
    std::uint32_t timescale = 0;
    for (int i = 0;; ++i) {
        const Range trak = findChild(moov, "trak", i);
        if (!trak.valid()) {
            return false;
        }
        const Range mdia = findChild(trak, "mdia");
        const Range hdlr = findChild(mdia, "hdlr");
        if (!mdia.valid() || !hdlr.valid() || hdlr.end - hdlr.begin < 12 || !isType(hdlr.begin + 8, "vide")) {
            continue;
        }
        const Range mdhd = findChild(mdia, "mdhd");
        if (!mdhd.valid() || mdhd.end - mdhd.begin < 4) {
            return false;
        }
        const std::uint8_t version = mdhd.begin[0];
        const std::ptrdiff_t timescaleOffset = version == 1 ? 20 : 12;
        if (mdhd.end - mdhd.begin < timescaleOffset + 4) {
            return false;
        }
        timescale = readU32(mdhd.begin + timescaleOffset);
        stbl = findChild(findChild(mdia, "minf"), "stbl");  // 見つからなければ無効な範囲のまま。
        break;
    }
    if (!stbl.valid() || timescale == 0) {
        return false;
    }
    readColor(stbl, table);

    // stts: デコード時刻の間隔を「コマ数×間隔」の並びで持つ。
    const Range stts = findChild(stbl, "stts");
    if (!stts.valid() || stts.end - stts.begin < 8) {
        return false;
    }
    const std::uint32_t sttsCount = readU32(stts.begin + 4);
    if (static_cast<std::uint64_t>(stts.end - stts.begin) < 8 + std::uint64_t{sttsCount} * 8) {
        return false;
    }
    std::vector<std::int64_t> decodeTimes;
    std::int64_t time = 0;
    for (std::uint32_t e = 0; e < sttsCount; ++e) {
        const std::uint32_t count = readU32(stts.begin + 8 + e * 8);
        const std::uint32_t delta = readU32(stts.begin + 12 + e * 8);
        if (decodeTimes.size() + count > 100000000) {
            return false;  // 現実的でないコマ数は壊れているとみなす。
        }
        for (std::uint32_t k = 0; k < count; ++k) {
            decodeTimes.push_back(time);
            time += delta;
        }
    }
    const std::size_t sampleCount = decodeTimes.size();
    if (sampleCount == 0) {
        return false;
    }

    // stsz: コマ数がsttsと一致するか確かめる。
    const Range stsz = findChild(stbl, "stsz");
    if (!stsz.valid() || stsz.end - stsz.begin < 12 || readU32(stsz.begin + 8) != sampleCount) {
        return false;
    }

    // ctts: 表示時刻 = デコード時刻 + ずれ。version 1は負のずれを持てる。どちらも符号付きとして読む。
    std::vector<std::int64_t> presentation(decodeTimes);
    const Range ctts = findChild(stbl, "ctts");
    if (ctts.valid()) {
        if (ctts.end - ctts.begin < 8) {
            return false;
        }
        const std::uint32_t cttsCount = readU32(ctts.begin + 4);
        if (static_cast<std::uint64_t>(ctts.end - ctts.begin) < 8 + std::uint64_t{cttsCount} * 8) {
            return false;
        }
        std::size_t sample = 0;
        for (std::uint32_t e = 0; e < cttsCount && sample < sampleCount; ++e) {
            const std::uint32_t count = readU32(ctts.begin + 8 + e * 8);
            const std::int32_t offset = static_cast<std::int32_t>(readU32(ctts.begin + 12 + e * 8));
            for (std::uint32_t k = 0; k < count && sample < sampleCount; ++k, ++sample) {
                presentation[sample] += offset;
            }
        }
        if (sample != sampleCount) {
            return false;
        }
    }

    // stss: キーフレームのコマ番号(1始まり、デコード順)。無ければ全コマがキーフレーム。
    std::vector<std::uint8_t> isKey(sampleCount, 0);
    const Range stss = findChild(stbl, "stss");
    if (stss.valid()) {
        if (stss.end - stss.begin < 8) {
            return false;
        }
        const std::uint32_t stssCount = readU32(stss.begin + 4);
        if (static_cast<std::uint64_t>(stss.end - stss.begin) < 8 + std::uint64_t{stssCount} * 4) {
            return false;
        }
        for (std::uint32_t e = 0; e < stssCount; ++e) {
            const std::uint32_t number = readU32(stss.begin + 8 + e * 4);
            if (number >= 1 && number <= sampleCount) {
                isKey[number - 1] = 1;
            }
        }
    } else {
        std::fill(isKey.begin(), isKey.end(), std::uint8_t{1});
    }

    // 時刻の単位を100nsへ換算する(四捨五入)。
    table.presentationTimes.resize(sampleCount);
    for (std::size_t i = 0; i < sampleCount; ++i) {
        // 大きな値でも桁あふれしないよう、整数部と余りに分けて換算する。
        const std::int64_t t = presentation[i];
        const std::int64_t scale = timescale;
        const std::int64_t whole = t / scale;
        const std::int64_t rest = t % scale;
        const std::int64_t half = rest >= 0 ? scale / 2 : -(scale / 2);
        table.presentationTimes[i] = whole * 10000000 + (rest * 10000000 + half) / scale;
    }
    table.isKeyFrame = std::move(isKey);
    return true;
}

}  // namespace frameplayer
