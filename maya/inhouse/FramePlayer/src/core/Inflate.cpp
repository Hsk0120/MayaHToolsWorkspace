/**
 * @file Inflate.cpp
 * @brief zlib・deflateの圧縮を戻す処理の実装(RFC 1950/1951)。
 */
#include "core/Inflate.h"

#include <array>
#include <cstring>

namespace frameplayer {

namespace {

/** @brief 下位のビットから順に読む読み手(deflateはビットを下位から詰める)。 */
class BitReader {
public:
    /**
     * @brief 読み手を作る。
     * @param data 読むデータ。
     * @param size バイト数。
     */
    BitReader(const std::uint8_t* data, std::size_t size) : data_(data), size_(size) {}

    /**
     * @brief 次のnビットを、消費せずに返す。
     * @param count ビット数(0〜32)。
     * @return 値。データの終わりより先は0で埋める。
     */
    std::uint32_t peek(int count) {
        refill();
        return static_cast<std::uint32_t>(buffer_ & ((std::uint64_t{1} << count) - 1u));
    }

    /**
     * @brief nビットを消費する。
     * @param count ビット数。
     * @note データの終わりを越えたらfailed()がtrueになる。
     */
    void consume(int count) {
        if (count > available_) {
            failed_ = true;
            buffer_ = 0;
            available_ = 0;
            return;
        }
        buffer_ >>= count;
        available_ -= count;
    }

    /**
     * @brief nビットを読む。
     * @param count 読むビット数(0〜24)。
     * @return 読んだ値。データの終わりを越えたらfailed()がtrueになる(値は0で埋める)。
     */
    std::uint32_t bits(int count) {
        const std::uint32_t value = peek(count);
        consume(count);
        return value;
    }

    /** @brief 次のバイトの区切りまで読み飛ばす(圧縮していないブロックの前)。 */
    void alignToByte() {
        // 先に読み込んだバイトのうち、使い残した端数のビットだけを捨てる。
        const int drop = available_ % 8;
        buffer_ >>= drop;
        available_ -= drop;
    }

    /**
     * @brief バイト単位で読む(区切りに揃えてから使う)。
     * @return 読んだバイト。終わりを越えたら0でfailed()がtrue。
     */
    std::uint8_t byte() {
        if (available_ >= 8) {
            return static_cast<std::uint8_t>(bits(8));
        }
        if (position_ >= size_) {
            failed_ = true;
            return 0;
        }
        return data_[position_++];
    }

    /**
     * @brief データの終わりを越えて読もうとしたかを返す。
     * @return 越えたらtrue。
     */
    bool failed() const { return failed_; }

private:
    /** @brief 溜めに、入るだけのバイトを読み込む(1バイト単位)。 */
    void refill() {
        while (available_ <= 56 && position_ < size_) {
            buffer_ |= static_cast<std::uint64_t>(data_[position_++]) << available_;
            available_ += 8;
        }
    }

    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t position_ = 0;
    std::uint64_t buffer_ = 0;
    int available_ = 0;
    bool failed_ = false;
};

constexpr int kFastBits = 9;  ///< 一度に表で引くビット数(これより長い符号は1ビットずつ読む)。

/** @brief ハフマン符号の表(符号の長さごとの数と、長さ順に並べた記号)。 */
struct Huffman {
    std::array<std::uint16_t, 16> counts{};   ///< 長さごとの符号の数。
    std::array<std::uint16_t, 320> symbols{}; ///< 符号の小さい順の記号。
    /// 次のkFastBitsビット(読む順)で引く表。値は「記号×16+符号の長さ」、0ならこの表に無い長い符号。
    std::array<std::uint16_t, 1 << kFastBits> fast{};
};

/**
 * @brief 符号の長さの並びから、ハフマン符号の表を作る(RFC 1951 3.2.2の決まり)。
 * @param lengths 記号ごとの符号の長さ(0なら使わない記号)。
 * @param count 記号の数。
 * @param table 格納先。
 * @return 正しく作れたらtrue。
 */
bool build(const std::uint8_t* lengths, int count, Huffman& table) {
    table.counts.fill(0);
    for (int i = 0; i < count; ++i) {
        ++table.counts[lengths[i]];
    }
    table.counts[0] = 0;
    // 長さごとの始まりの位置。
    std::array<std::uint16_t, 16> offsets{};
    for (int length = 1; length < 16; ++length) {
        offsets[length] = static_cast<std::uint16_t>(offsets[length - 1] + table.counts[length - 1]);
    }
    for (int i = 0; i < count; ++i) {
        if (lengths[i] != 0) {
            table.symbols[offsets[lengths[i]]++] = static_cast<std::uint16_t>(i);
        }
    }
    // 短い符号の表引き。符号は上位のビットから読まれるので、ビットの順を逆にした位置に置く。
    table.fast.fill(0);
    std::array<int, 16> next{};  // 長さごとの次の符号。
    int code = 0;
    for (int length = 1; length < 16; ++length) {
        code = (code + table.counts[length - 1]) << 1;
        next[length] = code;
    }
    for (int i = 0; i < count; ++i) {
        const int length = lengths[i];
        if (length == 0 || length > kFastBits) {
            continue;
        }
        const int c = next[length]++;
        int reversed = 0;
        for (int b = 0; b < length; ++b) {
            reversed |= ((c >> b) & 1) << (length - 1 - b);
        }
        for (int fill = reversed; fill < (1 << kFastBits); fill += 1 << length) {
            table.fast[static_cast<std::size_t>(fill)] = static_cast<std::uint16_t>(i * 16 + length);
        }
    }
    return true;
}

/**
 * @brief ハフマン符号を1つ読み、記号を返す。
 * @param reader 読み手。
 * @param table 表。
 * @return 記号。読めなければ負。
 */
int decodeSymbol(BitReader& reader, const Huffman& table) {
    const std::uint16_t entry = table.fast[reader.peek(kFastBits)];
    if (entry != 0) {
        reader.consume(entry & 15);
        return entry >> 4;
    }
    int code = 0;   // 今までに読んだ符号(上位のビットから)。
    int first = 0;  // この長さの最初の符号。
    int index = 0;  // この長さの最初の記号の位置。
    for (int length = 1; length < 16; ++length) {
        code |= static_cast<int>(reader.bits(1));
        const int count = table.counts[length];
        if (code - count < first) {
            return table.symbols[index + (code - first)];
        }
        index += count;
        first += count;
        first <<= 1;
        code <<= 1;
    }
    return -1;
}

// 長さと距離の符号の基本値と、続けて読む追加のビット数(RFC 1951 3.2.5)。
constexpr std::uint16_t kLengthBase[] = {3,  4,  5,  6,  7,  8,  9,  10, 11,  13,  15,  17,  19,  23, 27,
                                         31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
constexpr std::uint8_t kLengthExtra[] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2,
                                         2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
constexpr std::uint16_t kDistanceBase[] = {1,    2,    3,    4,    5,    7,     9,     13,    17,  25,
                                           33,   49,   65,   97,   129,  193,   257,   385,   513, 769,
                                           1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577};
constexpr std::uint8_t kDistanceExtra[] = {0, 0, 0, 0, 1, 1, 2, 2,  3,  3,  4,  4,  5,  5,  6,
                                           6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};

}  // namespace

long long inflateZlib(const std::uint8_t* source, std::size_t sourceSize, std::uint8_t* destination,
                      std::size_t destinationSize) {
    // zlibの見出し: 圧縮方式(8=deflate)と、見出しの検査(31の倍数)。辞書の指定は使われない。
    if (sourceSize < 2 || (source[0] & 0x0F) != 8 || ((source[0] << 8) | source[1]) % 31 != 0 || (source[1] & 0x20)) {
        return -1;
    }
    BitReader reader(source + 2, sourceSize - 2);
    std::size_t out = 0;
    bool last = false;
    while (!last) {
        last = reader.bits(1) != 0;
        const std::uint32_t type = reader.bits(2);
        if (type == 0) {
            // 圧縮していないブロック: 長さ(2)、長さの反転(2)、データ。
            reader.alignToByte();
            const std::uint32_t length = reader.byte() | (reader.byte() << 8);
            const std::uint32_t inverted = reader.byte() | (reader.byte() << 8);
            if ((length ^ 0xFFFFu) != inverted || out + length > destinationSize) {
                return -1;
            }
            for (std::uint32_t i = 0; i < length; ++i) {
                destination[out++] = reader.byte();
            }
            if (reader.failed()) {
                return -1;
            }
            continue;
        }
        Huffman literals;
        Huffman distances;
        if (type == 1) {
            // 決まった符号(RFC 1951 3.2.6)。
            std::uint8_t lengths[288 + 30];
            for (int i = 0; i < 144; ++i) lengths[i] = 8;
            for (int i = 144; i < 256; ++i) lengths[i] = 9;
            for (int i = 256; i < 280; ++i) lengths[i] = 7;
            for (int i = 280; i < 288; ++i) lengths[i] = 8;
            for (int i = 0; i < 30; ++i) lengths[288 + i] = 5;
            build(lengths, 288, literals);
            build(lengths + 288, 30, distances);
        } else if (type == 2) {
            // データの中に符号の表がある(RFC 1951 3.2.7)。
            const int literalCount = static_cast<int>(reader.bits(5)) + 257;
            const int distanceCount = static_cast<int>(reader.bits(5)) + 1;
            const int codeCount = static_cast<int>(reader.bits(4)) + 4;
            static constexpr std::uint8_t kOrder[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
            std::uint8_t codeLengths[19] = {};
            for (int i = 0; i < codeCount; ++i) {
                codeLengths[kOrder[i]] = static_cast<std::uint8_t>(reader.bits(3));
            }
            Huffman codes;
            build(codeLengths, 19, codes);
            std::uint8_t lengths[288 + 32] = {};
            int filled = 0;
            while (filled < literalCount + distanceCount) {
                const int symbol = decodeSymbol(reader, codes);
                if (symbol < 0) {
                    return -1;
                }
                if (symbol < 16) {
                    lengths[filled++] = static_cast<std::uint8_t>(symbol);
                    continue;
                }
                int repeat = 0;
                std::uint8_t value = 0;
                if (symbol == 16) {
                    if (filled == 0) {
                        return -1;
                    }
                    value = lengths[filled - 1];
                    repeat = 3 + static_cast<int>(reader.bits(2));
                } else if (symbol == 17) {
                    repeat = 3 + static_cast<int>(reader.bits(3));
                } else {
                    repeat = 11 + static_cast<int>(reader.bits(7));
                }
                if (filled + repeat > literalCount + distanceCount) {
                    return -1;
                }
                while (repeat-- > 0) {
                    lengths[filled++] = value;
                }
            }
            build(lengths, literalCount, literals);
            build(lengths + literalCount, distanceCount, distances);
        } else {
            return -1;
        }
        // 記号を読み、文字はそのまま、長さと距離の組は前に出たデータを写す。256でブロックが終わる。
        for (;;) {
            const int symbol = decodeSymbol(reader, literals);
            if (symbol < 0 || reader.failed()) {
                return -1;
            }
            if (symbol < 256) {
                if (out >= destinationSize) {
                    return -1;
                }
                destination[out++] = static_cast<std::uint8_t>(symbol);
                continue;
            }
            if (symbol == 256) {
                break;
            }
            const int lengthCode = symbol - 257;
            if (lengthCode >= 29) {
                return -1;
            }
            const std::size_t length = kLengthBase[lengthCode] + reader.bits(kLengthExtra[lengthCode]);
            const int distanceCode = decodeSymbol(reader, distances);
            if (distanceCode < 0 || distanceCode >= 30) {
                return -1;
            }
            const std::size_t distance = kDistanceBase[distanceCode] + reader.bits(kDistanceExtra[distanceCode]);
            if (distance > out || out + length > destinationSize) {
                return -1;
            }
            if (distance >= length) {
                std::memcpy(destination + out, destination + out - distance, length);
                out += length;
            } else {
                for (std::size_t i = 0; i < length; ++i, ++out) {
                    destination[out] = destination[out - distance];
                }
            }
        }
    }
    return reader.failed() ? -1 : static_cast<long long>(out);
}

}  // namespace frameplayer
