/**
 * @file ExrReader.cpp
 * @brief OpenEXRの画像を読む処理の実装。
 *
 * ファイルの並び(すべてリトルエンディアン):
 *   魔法の数(4)・版と印(4) → 見出し(属性の並び。複数の部分なら部分ごと) → コマ(チャンク)の位置の表 → チャンク。
 * 走査線のチャンク: [部分の番号] 先頭の行・バイト数・データ。タイルのチャンク: [部分の番号] タイルの位置x・y・段x・y・バイト数・データ。
 * 圧縮を戻したデータは、行ごとに、チャンネル(名前の順)ごとの画素が並ぶ。
 * 圧縮しても小さくならないチャンクは、圧縮せずに入っている(バイト数が戻した大きさと同じ)。
 */
#include "core/ExrReader.h"

#include <windows.h>
#include <ppl.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "core/Inflate.h"

namespace frameplayer {

namespace {

enum Compression { kNone = 0, kRle = 1, kZips = 2, kZip = 3, kPiz = 4, kPxr24 = 5, kB44 = 6, kB44a = 7, kDwaa = 8, kDwab = 9 };
enum PixelType { kUint = 0, kHalf = 1, kFloat = 2 };

/** @brief チャンネル(chlistの1項目)。 */
struct Channel {
    std::string name;
    int type = kHalf;
    int xSampling = 1;
    int ySampling = 1;
    bool pLinear = false;  ///< 知覚的にリニアな値か(DWAで非線形の変換をしない)。

    /** @brief 1画素のバイト数を返す。 @return halfは2、float・uintは4。 */
    int bytes() const { return type == kHalf ? 2 : 4; }
};

/** @brief 見出し(1つの部分)の必要な属性。 */
struct Header {
    std::vector<Channel> channels;
    int compression = kNone;
    int dataMinX = 0, dataMinY = 0, dataMaxX = -1, dataMaxY = -1;
    int displayMinX = 0, displayMinY = 0, displayMaxX = -1, displayMaxY = -1;
    bool tiled = false;
    int tileWidth = 0, tileHeight = 0;
    bool hasChromaticities = false;
    float chromaticities[8] = {};
    float pixelAspect = 1.0f;
    int chunkCount = -1;
    std::string type;  ///< multipartの部分の種類("scanlineimage"・"tiledimage"など)。
};

/** @brief バイト列を先頭から順に読む読み手。 */
class Reader {
public:
    Reader(const std::uint8_t* data, std::size_t size, std::size_t position = 0)
        : data_(data), size_(size), position_(position) {}
    bool ok() const { return ok_; }
    std::size_t position() const { return position_; }
    void seek(std::size_t position) { position_ = position; ok_ = ok_ && position <= size_; }
    bool has(std::size_t bytes) const { return ok_ && position_ + bytes <= size_; }
    const std::uint8_t* pointer() const { return data_ + position_; }
    void skip(std::size_t bytes) {
        if (!has(bytes)) {
            ok_ = false;
            return;
        }
        position_ += bytes;
    }
    std::uint32_t u32() {
        if (!has(4)) {
            ok_ = false;
            return 0;
        }
        std::uint32_t v;
        std::memcpy(&v, data_ + position_, 4);
        position_ += 4;
        return v;
    }
    std::int32_t i32() { return static_cast<std::int32_t>(u32()); }
    std::uint64_t u64() {
        const std::uint64_t low = u32();
        return low | (static_cast<std::uint64_t>(u32()) << 32);
    }
    float f32() {
        const std::uint32_t bits = u32();
        float v;
        std::memcpy(&v, &bits, 4);
        return v;
    }
    std::uint8_t u8() {
        if (!has(1)) {
            ok_ = false;
            return 0;
        }
        return data_[position_++];
    }
    std::string string() {
        std::string s;
        while (has(1) && data_[position_] != 0) {
            s.push_back(static_cast<char>(data_[position_++]));
        }
        u8();  // 終端の0。
        return s;
    }

private:
    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t position_;
    bool ok_ = true;
};

/**
 * @brief 見出しを1つ読む(属性の並び。名前が空なら終わり)。
 * @param reader 読み手。
 * @param header 格納先。
 * @return 読めたらtrue。
 */
bool parseHeader(Reader& reader, Header& header) {
    for (;;) {
        const std::string name = reader.string();
        if (!reader.ok()) {
            return false;
        }
        if (name.empty()) {
            return true;
        }
        const std::string type = reader.string();
        const std::uint32_t size = reader.u32();
        if (!reader.has(size)) {
            return false;
        }
        Reader value(reader.pointer(), size);
        if (name == "channels" && type == "chlist") {
            for (;;) {
                Channel channel;
                channel.name = value.string();
                if (channel.name.empty() || !value.ok()) {
                    break;
                }
                channel.type = value.i32();
                channel.pLinear = value.u8() != 0;
                value.skip(3);  // 予約。
                channel.xSampling = value.i32();
                channel.ySampling = value.i32();
                header.channels.push_back(channel);
            }
        } else if (name == "compression") {
            header.compression = value.u8();
        } else if (name == "dataWindow" && type == "box2i") {
            header.dataMinX = value.i32();
            header.dataMinY = value.i32();
            header.dataMaxX = value.i32();
            header.dataMaxY = value.i32();
        } else if (name == "displayWindow" && type == "box2i") {
            header.displayMinX = value.i32();
            header.displayMinY = value.i32();
            header.displayMaxX = value.i32();
            header.displayMaxY = value.i32();
        } else if (name == "tiles" && type == "tiledesc") {
            header.tiled = true;
            header.tileWidth = static_cast<int>(value.u32());
            header.tileHeight = static_cast<int>(value.u32());
        } else if (name == "chromaticities" && size == 32) {
            header.hasChromaticities = true;
            for (float& c : header.chromaticities) {
                c = value.f32();
            }
        } else if (name == "pixelAspectRatio" && size == 4) {
            header.pixelAspect = value.f32();
        } else if (name == "chunkCount" && size == 4) {
            header.chunkCount = value.i32();
        } else if (name == "type") {
            header.type.assign(reinterpret_cast<const char*>(reader.pointer()), size);
        }
        reader.skip(size);
    }
}

/**
 * @brief 圧縮の方式ごとの、1つのチャンクに入る行数を返す。
 * @param compression 圧縮の方式。
 * @return 行数。
 */
int linesPerChunk(int compression) {
    switch (compression) {
    case kZip:
    case kPxr24:
        return 16;
    case kPiz:
    case kB44:
    case kB44a:
    case kDwaa:
        return 32;
    case kDwab:
        return 256;
    default:
        return 1;
    }
}

// ---------------------------------------------------------------- ZIP・RLE の後処理

/**
 * @brief ZIP・RLEで圧縮を戻した後の並べ直しをする(差分を足し戻し、前半・後半に分けたバイトを交互に戻す)。
 * @param data 戻したバイト列(差分のまま)。
 * @param out 格納先(dataと同じ大きさ)。
 */
void unpredictAndInterleave(std::vector<std::uint8_t>& data, std::uint8_t* out) {
    const std::size_t n = data.size();
    for (std::size_t i = 1; i < n; ++i) {
        data[i] = static_cast<std::uint8_t>(data[i - 1] + data[i] - 128);
    }
    const std::uint8_t* first = data.data();
    const std::uint8_t* second = data.data() + (n + 1) / 2;
    for (std::size_t i = 0; i < n; ++i) {
        out[i] = (i % 2 == 0) ? first[i / 2] : second[i / 2];
    }
}

/**
 * @brief RLEの圧縮を戻す(負の数ならその数だけそのまま、0以上なら次の1バイトを数+1回繰り返す)。
 * @param in 圧縮されたデータ。
 * @param size バイト数。
 * @param out 格納先。
 * @return 戻せたらtrue。
 */
bool unRle(const std::uint8_t* in, std::size_t size, std::vector<std::uint8_t>& out) {
    std::size_t i = 0;
    std::size_t o = 0;
    while (i < size && o < out.size()) {
        const int count = static_cast<std::int8_t>(in[i++]);
        if (count < 0) {
            const std::size_t n = static_cast<std::size_t>(-count);
            if (i + n > size || o + n > out.size()) {
                return false;
            }
            std::memcpy(out.data() + o, in + i, n);
            i += n;
            o += n;
        } else {
            const std::size_t n = static_cast<std::size_t>(count) + 1;
            if (i >= size || o + n > out.size()) {
                return false;
            }
            std::memset(out.data() + o, in[i++], n);
            o += n;
        }
    }
    return o == out.size();
}

// ---------------------------------------------------------------- PIZ(ハフマン符号 + ウェーブレット)

constexpr int kHufEncBits = 16;
constexpr int kHufDecBits = 14;
constexpr int kHufEncSize = (1 << kHufEncBits) + 1;
constexpr int kHufDecSize = 1 << kHufDecBits;
constexpr int kHufDecMask = kHufDecSize - 1;
constexpr int kShortZeroRun = 59;
constexpr int kLongZeroRun = 63;
constexpr int kShortestLongRun = 2 + kLongZeroRun - kShortZeroRun;

/** @brief ハフマン符号を引く表の1項目。短い符号は直接、長い符号は候補の一覧を持つ。 */
struct HufDec {
    int length = 0;              ///< 短い符号の長さ(0なら長い符号の候補を見る)。
    int literal = 0;             ///< 短い符号の記号、または長い符号の候補の数。
    std::vector<int> candidates; ///< 長い符号の記号の候補。
};

/**
 * @brief 上位のビットから順に読む(PIZのハフマン符号はビットを上位から詰める)。
 */
struct BitStream {
    const std::uint8_t* in;
    const std::uint8_t* end;
    std::uint64_t buffer = 0;
    int count = 0;
    bool get() {
        if (in >= end) {
            return false;
        }
        buffer = (buffer << 8) | *in++;
        count += 8;
        return true;
    }
};

/**
 * @brief 符号の長さの表を読む(6bitの長さと、0の続きを短く書く印)。
 * @param in 読む位置(進める)。
 * @param size 読めるバイト数。
 * @param minCode 最初の記号。
 * @param maxCode 最後の記号。
 * @param codes 記号ごとの長さの格納先(後で符号も入れる)。
 * @return 読めたらtrue。
 */
bool unpackCodeLengths(const std::uint8_t*& in, std::size_t size, int minCode, int maxCode, std::vector<std::uint64_t>& codes) {
    const std::uint8_t* end = in + size;
    std::uint64_t buffer = 0;
    int count = 0;
    auto bits = [&](int n, std::uint64_t& value) {
        while (count < n) {
            if (in >= end) {
                return false;
            }
            buffer = (buffer << 8) | *in++;
            count += 8;
        }
        count -= n;
        value = (buffer >> count) & ((1ull << n) - 1);
        return true;
    };
    for (int code = minCode; code <= maxCode; ++code) {
        std::uint64_t length = 0;
        if (!bits(6, length)) {
            return false;
        }
        codes[static_cast<std::size_t>(code)] = length;
        if (length == kLongZeroRun) {
            std::uint64_t run = 0;
            if (!bits(8, run)) {
                return false;
            }
            const int zeros = static_cast<int>(run) + kShortestLongRun;
            if (code + zeros > maxCode + 1) {
                return false;
            }
            for (int i = 0; i < zeros; ++i) {
                codes[static_cast<std::size_t>(code + i)] = 0;
            }
            code += zeros - 1;
        } else if (length >= kShortZeroRun) {
            const int zeros = static_cast<int>(length) - kShortZeroRun + 2;
            if (code + zeros > maxCode + 1) {
                return false;
            }
            for (int i = 0; i < zeros; ++i) {
                codes[static_cast<std::size_t>(code + i)] = 0;
            }
            code += zeros - 1;
        }
    }
    return true;
}

/**
 * @brief 長さの表から、正規のハフマン符号を決める(長い符号ほど小さい値から振る)。
 * @param codes 記号ごとの長さ。符号を上位に入れて「符号 << 6 | 長さ」にする。
 */
void canonicalCodes(std::vector<std::uint64_t>& codes) {
    std::uint64_t n[59] = {};
    for (std::uint64_t c : codes) {
        n[c] += 1;
    }
    std::uint64_t c = 0;
    for (int i = 58; i > 0; --i) {
        const std::uint64_t next = (c + n[i]) >> 1;
        n[i] = c;
        c = next;
    }
    for (std::uint64_t& code : codes) {
        const std::uint64_t length = code;
        if (length > 0) {
            code = length | (n[length]++ << 6);
        }
    }
}

/**
 * @brief 符号を引く表を作る。
 * @param codes 記号ごとの「符号 << 6 | 長さ」。
 * @param minCode 最初の記号。
 * @param maxCode 最後の記号。
 * @param table 格納先(kHufDecSize項目)。
 * @return 作れたらtrue。
 */
bool buildDecodeTable(const std::vector<std::uint64_t>& codes, int minCode, int maxCode, std::vector<HufDec>& table) {
    for (int symbol = minCode; symbol <= maxCode; ++symbol) {
        const std::uint64_t code = codes[static_cast<std::size_t>(symbol)] >> 6;
        const int length = static_cast<int>(codes[static_cast<std::size_t>(symbol)] & 63);
        if (code >> length) {
            return false;
        }
        if (length > kHufDecBits) {
            HufDec& entry = table[static_cast<std::size_t>(code >> (length - kHufDecBits))];
            if (entry.length) {
                return false;
            }
            ++entry.literal;
            entry.candidates.push_back(symbol);
        } else if (length) {
            const std::size_t start = static_cast<std::size_t>(code << (kHufDecBits - length));
            for (std::size_t i = 0; i < (1ull << (kHufDecBits - length)); ++i) {
                HufDec& entry = table[start + i];
                if (entry.length || !entry.candidates.empty()) {
                    return false;
                }
                entry.length = length;
                entry.literal = symbol;
            }
        }
    }
    return true;
}

/**
 * @brief ハフマン符号を戻す(最後の記号は「直前の値を繰り返す」印)。
 * @param data 圧縮されたデータ(見出しの20バイトから)。
 * @param size バイト数。
 * @param out 格納先。
 * @return 戻せたらtrue(格納先がちょうど埋まったとき)。
 */
bool hufUncompress(const std::uint8_t* data, std::size_t size, std::vector<std::uint16_t>& out) {
    if (size < 20) {
        return false;
    }
    Reader header(data, size);
    const int minCode = static_cast<int>(header.u32());
    const int maxCode = static_cast<int>(header.u32());
    header.u32();  // 表の長さ(使わない)。
    const std::uint32_t bitCount = header.u32();
    if (minCode < 0 || minCode >= kHufEncSize || maxCode < 0 || maxCode >= kHufEncSize) {
        return false;
    }
    const std::uint8_t* in = data + 20;
    std::vector<std::uint64_t> codes(kHufEncSize, 0);
    if (!unpackCodeLengths(in, size - 20, minCode, maxCode, codes)) {
        return false;
    }
    if (static_cast<std::size_t>(in - data) + (bitCount + 7) / 8 > size) {
        return false;
    }
    canonicalCodes(codes);
    std::vector<HufDec> table(kHufDecSize);
    if (!buildDecodeTable(codes, minCode, maxCode, table)) {
        return false;
    }

    const int repeatCode = maxCode;
    BitStream bits{in, in + (bitCount + 7) / 8};
    std::size_t o = 0;
    auto emit = [&](int symbol) {
        if (symbol == repeatCode) {
            if (bits.count < 8 && !bits.get()) {
                return false;
            }
            bits.count -= 8;
            int repeat = static_cast<int>((bits.buffer >> bits.count) & 0xFF);
            if (o == 0 || o + static_cast<std::size_t>(repeat) > out.size()) {
                return false;
            }
            const std::uint16_t previous = out[o - 1];
            while (repeat-- > 0) {
                out[o++] = previous;
            }
            return true;
        }
        if (o >= out.size()) {
            return false;
        }
        out[o++] = static_cast<std::uint16_t>(symbol);
        return true;
    };
    while (bits.get()) {
        while (bits.count >= kHufDecBits) {
            const HufDec& entry = table[static_cast<std::size_t>((bits.buffer >> (bits.count - kHufDecBits)) & kHufDecMask)];
            if (entry.length) {
                bits.count -= entry.length;
                if (!emit(entry.literal)) {
                    return false;
                }
                continue;
            }
            if (entry.candidates.empty()) {
                return false;
            }
            bool found = false;
            for (int symbol : entry.candidates) {
                const int length = static_cast<int>(codes[static_cast<std::size_t>(symbol)] & 63);
                while (bits.count < length && bits.get()) {
                }
                if (bits.count >= length &&
                    (codes[static_cast<std::size_t>(symbol)] >> 6) ==
                        ((bits.buffer >> (bits.count - length)) & ((1ull << length) - 1))) {
                    bits.count -= length;
                    if (!emit(symbol)) {
                        return false;
                    }
                    found = true;
                    break;
                }
            }
            if (!found) {
                return false;
            }
        }
    }
    // 残りのビット(最後のバイトの使わない分を除く)。
    const int unused = static_cast<int>((8 - bitCount) & 7);
    bits.buffer >>= unused;
    bits.count -= unused;
    while (bits.count > 0) {
        const HufDec& entry = table[static_cast<std::size_t>((bits.buffer << (kHufDecBits - bits.count)) & kHufDecMask)];
        if (!entry.length) {
            return false;
        }
        bits.count -= entry.length;
        if (!emit(entry.literal)) {
            return false;
        }
    }
    return o == out.size();
}

/** @brief 14bitの値のウェーブレットを戻す(和と差から2つの値へ)。 */
void waveletDecode14(std::uint16_t l, std::uint16_t h, std::uint16_t& a, std::uint16_t& b) {
    const short ls = static_cast<short>(l);
    const short hs = static_cast<short>(h);
    const int hi = hs;
    const int ai = ls + (hi & 1) + (hi >> 1);
    a = static_cast<std::uint16_t>(static_cast<short>(ai));
    b = static_cast<std::uint16_t>(static_cast<short>(ai - hi));
}

/** @brief 16bitの値のウェーブレットを戻す(桁あふれを法として扱う)。 */
void waveletDecode16(std::uint16_t l, std::uint16_t h, std::uint16_t& a, std::uint16_t& b) {
    constexpr int kOffset = 1 << 15;
    constexpr int kMask = (1 << 16) - 1;
    const int m = l;
    const int d = h;
    const int bb = (m - (d >> 1)) & kMask;
    const int aa = (d + bb - kOffset) & kMask;
    b = static_cast<std::uint16_t>(bb);
    a = static_cast<std::uint16_t>(aa);
}

/**
 * @brief 2次元のウェーブレット変換を戻す(粗い段から細かい段へ)。
 * @param in 値(その場で書き換える)。
 * @param nx 横の数。
 * @param ox 横の間隔(値の数)。
 * @param ny 縦の数。
 * @param oy 縦の間隔(値の数)。
 * @param maxValue 値の最大(14bitに収まれば14bitの変換を使う)。
 */
void waveletDecode(std::uint16_t* in, int nx, int ox, int ny, int oy, std::uint16_t maxValue) {
    const bool w14 = maxValue < (1 << 14);
    const int n = std::min(nx, ny);
    int p = 1;
    while (p <= n) {
        p <<= 1;
    }
    p >>= 1;
    int p2 = p;
    p >>= 1;
    auto decode = [w14](std::uint16_t l, std::uint16_t h, std::uint16_t& a, std::uint16_t& b) {
        if (w14) {
            waveletDecode14(l, h, a, b);
        } else {
            waveletDecode16(l, h, a, b);
        }
    };
    while (p >= 1) {
        std::uint16_t* py = in;
        std::uint16_t* ey = in + static_cast<std::ptrdiff_t>(oy) * (ny - p2);
        const int oy1 = oy * p;
        const int oy2 = oy * p2;
        const int ox1 = ox * p;
        const int ox2 = ox * p2;
        std::uint16_t i00, i01, i10, i11;
        for (; py <= ey; py += oy2) {
            std::uint16_t* px = py;
            std::uint16_t* ex = py + static_cast<std::ptrdiff_t>(ox) * (nx - p2);
            for (; px <= ex; px += ox2) {
                std::uint16_t* p01 = px + ox1;
                std::uint16_t* p10 = px + oy1;
                std::uint16_t* p11 = p10 + ox1;
                decode(*px, *p10, i00, i10);
                decode(*p01, *p11, i01, i11);
                decode(i00, i01, *px, *p01);
                decode(i10, i11, *p10, *p11);
            }
            if (nx & p) {
                std::uint16_t* p10 = px + oy1;
                decode(*px, *p10, i00, *p10);
                *px = i00;
            }
        }
        if (ny & p) {
            std::uint16_t* px = py;
            std::uint16_t* ex = py + static_cast<std::ptrdiff_t>(ox) * (nx - p2);
            for (; px <= ex; px += ox2) {
                std::uint16_t* p01 = px + ox1;
                decode(*px, *p01, i00, *p01);
                *px = i00;
            }
        }
        p2 = p;
        p >>= 1;
    }
}

/**
 * @brief PIZの圧縮を戻す。
 * @param in 圧縮されたデータ。
 * @param size バイト数。
 * @param channels チャンネル。
 * @param width チャンクの幅。
 * @param lines チャンクの行数。
 * @param out 格納先(戻した大きさ)。
 * @return 戻せたらtrue。
 */
bool unPiz(const std::uint8_t* in, std::size_t size, const std::vector<Channel>& channels, int width, int lines,
           std::uint8_t* out, std::size_t outSize) {
    Reader reader(in, size);
    // 使われている値の一覧(ビットの表)。表に無い値は使われていないので、値を詰めて符号を短くしてある。
    std::vector<std::uint8_t> bitmap(8192, 0);
    const std::uint16_t minNonZero = static_cast<std::uint16_t>(reader.u8() | (reader.u8() << 8));
    const std::uint16_t maxNonZero = static_cast<std::uint16_t>(reader.u8() | (reader.u8() << 8));
    if (maxNonZero >= 8192) {
        return false;
    }
    if (minNonZero <= maxNonZero) {
        const std::size_t count = static_cast<std::size_t>(maxNonZero) - minNonZero + 1;
        if (!reader.has(count)) {
            return false;
        }
        std::memcpy(bitmap.data() + minNonZero, reader.pointer(), count);
        reader.skip(count);
    }
    std::vector<std::uint16_t> lut(65536, 0);
    int k = 0;
    for (int i = 0; i < 65536; ++i) {
        if (i == 0 || (bitmap[static_cast<std::size_t>(i >> 3)] & (1 << (i & 7)))) {
            lut[static_cast<std::size_t>(k++)] = static_cast<std::uint16_t>(i);
        }
    }
    const std::uint16_t maxValue = static_cast<std::uint16_t>(k - 1);

    const std::uint32_t length = reader.u32();
    if (!reader.ok() || !reader.has(length)) {
        return false;
    }
    std::vector<std::uint16_t> values(outSize / 2);
    if (!hufUncompress(reader.pointer(), length, values)) {
        return false;
    }
    // チャンネルごとに(16bitの値の単位で)ウェーブレットを戻す。値はチャンネルごとにまとまって並ぶ。
    std::size_t start = 0;
    std::vector<std::size_t> starts;
    for (const Channel& channel : channels) {
        starts.push_back(start);
        const int components = channel.bytes() / 2;
        for (int j = 0; j < components; ++j) {
            waveletDecode(values.data() + start + j, width, components, lines, width * components, maxValue);
        }
        start += static_cast<std::size_t>(width) * lines * components;
    }
    for (std::uint16_t& v : values) {
        v = lut[v];
    }
    // 行ごと・チャンネルごとの並びに直す。
    std::uint8_t* o = out;
    for (int y = 0; y < lines; ++y) {
        for (std::size_t c = 0; c < channels.size(); ++c) {
            const std::size_t count = static_cast<std::size_t>(width) * (channels[c].bytes() / 2);
            std::memcpy(o, values.data() + starts[c] + count * y, count * 2);
            o += count * 2;
        }
    }
    return true;
}

// ---------------------------------------------------------------- PXR24

/**
 * @brief PXR24の圧縮を戻す(zlibの後、値の差をバイトの面ごとに並べたものから戻す。floatは下位8bitが0)。
 */
bool unPxr24(const std::uint8_t* in, std::size_t size, const std::vector<Channel>& channels, int width, int lines,
             std::uint8_t* out, std::size_t outSize) {
    std::size_t packedSize = 0;
    for (const Channel& channel : channels) {
        packedSize += static_cast<std::size_t>(width) * (channel.type == kHalf ? 2 : channel.type == kFloat ? 3 : 4);
    }
    packedSize *= static_cast<std::size_t>(lines);
    std::vector<std::uint8_t> packed(packedSize);
    if (inflateZlib(in, size, packed.data(), packed.size()) != static_cast<long long>(packed.size())) {
        return false;
    }
    const std::uint8_t* p = packed.data();
    std::uint8_t* o = out;
    for (int y = 0; y < lines; ++y) {
        for (const Channel& channel : channels) {
            const std::size_t n = static_cast<std::size_t>(width);
            std::uint32_t pixel = 0;
            if (channel.type == kHalf) {
                const std::uint8_t* p0 = p;
                const std::uint8_t* p1 = p + n;
                for (std::size_t j = 0; j < n; ++j) {
                    pixel += (static_cast<std::uint32_t>(p0[j]) << 8) | p1[j];
                    const std::uint16_t v = static_cast<std::uint16_t>(pixel);
                    std::memcpy(o, &v, 2);
                    o += 2;
                }
                p += n * 2;
            } else if (channel.type == kFloat) {
                const std::uint8_t* p0 = p;
                const std::uint8_t* p1 = p + n;
                const std::uint8_t* p2 = p + n * 2;
                for (std::size_t j = 0; j < n; ++j) {
                    pixel += (static_cast<std::uint32_t>(p0[j]) << 24) | (static_cast<std::uint32_t>(p1[j]) << 16) |
                             (static_cast<std::uint32_t>(p2[j]) << 8);
                    std::memcpy(o, &pixel, 4);
                    o += 4;
                }
                p += n * 3;
            } else {
                const std::uint8_t* p0 = p;
                const std::uint8_t* p1 = p + n;
                const std::uint8_t* p2 = p + n * 2;
                const std::uint8_t* p3 = p + n * 3;
                for (std::size_t j = 0; j < n; ++j) {
                    pixel += (static_cast<std::uint32_t>(p0[j]) << 24) | (static_cast<std::uint32_t>(p1[j]) << 16) |
                             (static_cast<std::uint32_t>(p2[j]) << 8) | p3[j];
                    std::memcpy(o, &pixel, 4);
                    o += 4;
                }
                p += n * 4;
            }
        }
    }
    return static_cast<std::size_t>(o - out) == outSize;
}

// ---------------------------------------------------------------- B44・B44A

/** @brief 14バイトの4×4のブロックを戻す(最初の値と、6bitの差を倍率で広げたもの)。 */
void unpack14(const std::uint8_t b[14], std::uint16_t s[16]) {
    s[0] = static_cast<std::uint16_t>((b[0] << 8) | b[1]);
    const std::uint16_t shift = b[2] >> 2;
    const std::uint16_t bias = static_cast<std::uint16_t>(0x20u << shift);
    auto d = [shift, bias](unsigned v) { return static_cast<std::uint16_t>((v << shift) - bias); };
    s[4] = static_cast<std::uint16_t>(s[0] + d(((b[2] << 4) | (b[3] >> 4)) & 0x3f));
    s[8] = static_cast<std::uint16_t>(s[4] + d(((b[3] << 2) | (b[4] >> 6)) & 0x3f));
    s[12] = static_cast<std::uint16_t>(s[8] + d(b[4] & 0x3f));
    s[1] = static_cast<std::uint16_t>(s[0] + d(b[5] >> 2));
    s[5] = static_cast<std::uint16_t>(s[4] + d(((b[5] << 4) | (b[6] >> 4)) & 0x3f));
    s[9] = static_cast<std::uint16_t>(s[8] + d(((b[6] << 2) | (b[7] >> 6)) & 0x3f));
    s[13] = static_cast<std::uint16_t>(s[12] + d(b[7] & 0x3f));
    s[2] = static_cast<std::uint16_t>(s[1] + d(b[8] >> 2));
    s[6] = static_cast<std::uint16_t>(s[5] + d(((b[8] << 4) | (b[9] >> 4)) & 0x3f));
    s[10] = static_cast<std::uint16_t>(s[9] + d(((b[9] << 2) | (b[10] >> 6)) & 0x3f));
    s[14] = static_cast<std::uint16_t>(s[13] + d(b[10] & 0x3f));
    s[3] = static_cast<std::uint16_t>(s[2] + d(b[11] >> 2));
    s[7] = static_cast<std::uint16_t>(s[6] + d(((b[11] << 4) | (b[12] >> 4)) & 0x3f));
    s[11] = static_cast<std::uint16_t>(s[10] + d(((b[12] << 2) | (b[13] >> 6)) & 0x3f));
    s[15] = static_cast<std::uint16_t>(s[14] + d(b[13] & 0x3f));
    // 並べやすいよう符号のビットを入れ替えてあるので戻す。
    for (int i = 0; i < 16; ++i) {
        s[i] = (s[i] & 0x8000) ? static_cast<std::uint16_t>(s[i] & 0x7fff) : static_cast<std::uint16_t>(~s[i]);
    }
}

/** @brief 3バイトの4×4のブロック(全部同じ値、B44Aだけ)を戻す。 */
void unpack3(const std::uint8_t b[3], std::uint16_t s[16]) {
    std::uint16_t v = static_cast<std::uint16_t>((b[0] << 8) | b[1]);
    v = (v & 0x8000) ? static_cast<std::uint16_t>(v & 0x7fff) : static_cast<std::uint16_t>(~v);
    for (int i = 0; i < 16; ++i) {
        s[i] = v;
    }
}

/**
 * @brief B44・B44Aの圧縮を戻す(halfのチャンネルは4×4ごとに圧縮、それ以外はそのまま)。
 */
bool unB44(const std::uint8_t* in, std::size_t size, const std::vector<Channel>& channels, int width, int lines,
           std::uint8_t* out) {
    const std::uint8_t* end = in + size;
    std::vector<std::vector<std::uint8_t>> planes(channels.size());
    for (std::size_t c = 0; c < channels.size(); ++c) {
        const Channel& channel = channels[c];
        std::vector<std::uint8_t>& plane = planes[c];
        plane.resize(static_cast<std::size_t>(width) * lines * channel.bytes());
        if (channel.type != kHalf) {
            if (static_cast<std::size_t>(end - in) < plane.size()) {
                return false;
            }
            std::memcpy(plane.data(), in, plane.size());
            in += plane.size();
            continue;
        }
        auto* values = reinterpret_cast<std::uint16_t*>(plane.data());
        for (int y = 0; y < lines; y += 4) {
            for (int x = 0; x < width; x += 4) {
                std::uint16_t s[16];
                if (end - in < 3) {
                    return false;
                }
                if (in[2] >= (13 << 2)) {
                    unpack3(in, s);
                    in += 3;
                } else {
                    if (end - in < 14) {
                        return false;
                    }
                    unpack14(in, s);
                    in += 14;
                }
                for (int by = 0; by < 4 && y + by < lines; ++by) {
                    for (int bx = 0; bx < 4 && x + bx < width; ++bx) {
                        values[static_cast<std::size_t>(y + by) * width + x + bx] = s[by * 4 + bx];
                    }
                }
            }
        }
    }
    std::uint8_t* o = out;
    for (int y = 0; y < lines; ++y) {
        for (std::size_t c = 0; c < channels.size(); ++c) {
            const std::size_t row = static_cast<std::size_t>(width) * channels[c].bytes();
            std::memcpy(o, planes[c].data() + row * y, row);
            o += row;
        }
    }
    return true;
}

// ---------------------------------------------------------------- DWAA・DWAB(8×8のDCTによる非可逆の圧縮)

/** @brief DWAでのチャンネルの扱い。 */
enum DwaScheme { kDwaUnknown = 0, kDwaLossyDct = 1, kDwaRle = 2 };

/** @brief DWAの、チャンネルの名前の末尾から扱いを決める規則。 */
struct DwaRule {
    std::string suffix;           ///< 名前の末尾(最後の「.」より後)。
    int scheme = kDwaUnknown;     ///< 扱い。
    int type = kHalf;             ///< 対象の画素の型。
    int cscIndex = -1;            ///< 色の変換での役割(0=赤、1=緑、2=青。-1は対象外)。
    bool caseInsensitive = false; ///< 大文字・小文字を区別しないか。
};

/**
 * @brief 規則の書かれていない古い版(版1)の、既定の規則を返す。
 * @return 規則の一覧。
 */
std::vector<DwaRule> legacyDwaRules() {
    std::vector<DwaRule> rules;
    struct Entry {
        const char* suffix;
        int scheme;
        int cscIndex;
    };
    static const Entry kEntries[] = {
        {"r", kDwaLossyDct, 0}, {"red", kDwaLossyDct, 0}, {"g", kDwaLossyDct, 1}, {"grn", kDwaLossyDct, 1},
        {"green", kDwaLossyDct, 1}, {"b", kDwaLossyDct, 2}, {"bl", kDwaLossyDct, 2}, {"blu", kDwaLossyDct, 2},
        {"blue", kDwaLossyDct, 2}, {"y", kDwaLossyDct, -1}, {"by", kDwaLossyDct, -1}, {"ry", kDwaLossyDct, -1},
        {"a", kDwaRle, -1},
    };
    for (const Entry& entry : kEntries) {
        for (int type : {kUint, kHalf, kFloat}) {
            if (entry.scheme == kDwaLossyDct && type != kHalf) {
                continue;  // 古い版は、halfのチャンネルだけを非可逆にしていた。
            }
            rules.push_back({entry.suffix, entry.scheme, type, entry.cscIndex, true});
        }
    }
    return rules;
}

/** @brief 文字列を小文字にする。 @param s 文字列。 @return 小文字にした文字列。 */
std::string toLower(std::string s) {
    for (char& c : s) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

/** @brief 8×8の並びの、ジグザグの順(低い周波数から)の位置を返す表。 */
constexpr int kZigZag[64] = {0,  1,  8,  16, 9,  2,  3,  10, 17, 24, 32, 25, 18, 11, 4,  5,
                             12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,  7,  14, 21, 28,
                             35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
                             58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63};

/**
 * @brief 8つの値の逆DCTをする(行・列のどちらにも使う)。
 * @param v 8つの値(stride おきに並ぶ)。結果で書き換える。
 * @param stride 値の間隔。
 * @note 係数は「0.5×cos(kπ/16)」。偶数番目と奇数番目に分けて計算する、よく知られた分解の形。
 */
void inverseDct8(float* v, int stride) {
    static const float a = 0.5f * std::cos(3.14159f / 4.0f);
    static const float b = 0.5f * std::cos(3.14159f / 16.0f);
    static const float c = 0.5f * std::cos(3.14159f / 8.0f);
    static const float d = 0.5f * std::cos(3.0f * 3.14159f / 16.0f);
    static const float e = 0.5f * std::cos(5.0f * 3.14159f / 16.0f);
    static const float f = 0.5f * std::cos(3.0f * 3.14159f / 8.0f);
    static const float g = 0.5f * std::cos(7.0f * 3.14159f / 16.0f);
    const float x0 = v[0], x1 = v[stride], x2 = v[2 * stride], x3 = v[3 * stride];
    const float x4 = v[4 * stride], x5 = v[5 * stride], x6 = v[6 * stride], x7 = v[7 * stride];
    const float alpha0 = c * x2, alpha1 = f * x2, alpha2 = c * x6, alpha3 = f * x6;
    const float beta0 = b * x1 + d * x3 + e * x5 + g * x7;
    const float beta1 = d * x1 - g * x3 - b * x5 - e * x7;
    const float beta2 = e * x1 - b * x3 + g * x5 + d * x7;
    const float beta3 = g * x1 - e * x3 + d * x5 - b * x7;
    const float theta0 = a * (x0 + x4);
    const float theta3 = a * (x0 - x4);
    const float theta1 = alpha0 + alpha3;
    const float theta2 = alpha1 - alpha2;
    const float gamma0 = theta0 + theta1;
    const float gamma1 = theta3 + theta2;
    const float gamma2 = theta3 - theta2;
    const float gamma3 = theta0 - theta1;
    v[0] = gamma0 + beta0;
    v[stride] = gamma1 + beta1;
    v[2 * stride] = gamma2 + beta2;
    v[3 * stride] = gamma3 + beta3;
    v[4 * stride] = gamma3 - beta3;
    v[5 * stride] = gamma2 - beta2;
    v[6 * stride] = gamma1 - beta1;
    v[7 * stride] = gamma0 - beta0;
}

/**
 * @brief DWAの非線形の値(半精度)を、リニアな値(半精度)にする表を返す。
 * @return 65536項目の表。
 * @note 圧縮の前に「|x|≦1 なら x^(1/2.2)、それより大きければ ln(x)÷2.2+1」で非線形にしてあるので、その逆。
 *       無限大・非数は0にする。
 *       表は片付けない(プログラムの終了の途中でも、裏のデコードが安全に使えるように)。
 */
const std::uint16_t* dwaToLinear() {
    static const std::uint16_t* const table = [] {
        auto* t = new std::uint16_t[65536];
        for (int bits = 0; bits < 65536; ++bits) {
            if (((bits >> 10) & 0x1F) == 31) {
                t[bits] = 0;
                continue;
            }
            const float h = halfToFloat(static_cast<std::uint16_t>(bits));
            const double sign = h < 0.0f ? -1.0 : 1.0;
            const double magnitude = std::fabs(static_cast<double>(h));
            const double linear = magnitude <= 1.0 ? std::pow(magnitude, 2.2) : std::exp(2.2 * (magnitude - 1.0));
            t[bits] = floatToHalf(static_cast<float>(sign * linear));
        }
        return t;
    }();
    return table;
}

/**
 * @brief DWAA・DWABの圧縮を戻す。
 * @param in 圧縮されたデータ。
 * @param size バイト数。
 * @param channels チャンネルの一覧。
 * @param width 幅。
 * @param lines 行数。
 * @param out 格納先(圧縮なしの並び。各行に、チャンネルの順に幅分の値)。
 * @return 戻せたらtrue。
 * @note データの並び: 11個の数(64bit)、規則(版2以降)、扱いの分からないチャンネルの生のデータ(zlib)、
 *       DCTの交流成分(ハフマン符号かzlib)、直流成分(ZIPと同じ並べ替え)、RLEのチャンネル(zlib+RLE)。
 *       非可逆のチャンネルは8×8ごとに逆DCTをし、赤・緑・青の組はYCbCrからRGBへ戻し、非線形からリニアへ戻す。
 */
bool unDwa(const std::uint8_t* in, std::size_t size, const std::vector<Channel>& channels, int width, int lines,
           std::uint8_t* out) {
    Reader reader(in, size);
    std::uint64_t counts[11];
    for (std::uint64_t& count : counts) {
        count = reader.u64();
    }
    const std::uint64_t version = counts[0];
    const std::uint64_t unknownRawSize = counts[1];
    const std::uint64_t unknownSize = counts[2];
    const std::uint64_t acSize = counts[3];
    const std::uint64_t dcSize = counts[4];
    const std::uint64_t rleSize = counts[5];
    const std::uint64_t rleUnpackedSize = counts[6];
    const std::uint64_t rleRawSize = counts[7];
    const std::uint64_t acCount = counts[8];
    const std::uint64_t dcCount = counts[9];
    const std::uint64_t acCompression = counts[10];
    if (!reader.ok() || version > 2) {
        return false;
    }
    // 規則。版2以降はデータに書いてある(先頭の16bitは、その16bit自身を含む規則全体のバイト数)。
    std::vector<DwaRule> rules;
    if (version >= 2) {
        if (!reader.has(2)) {
            return false;
        }
        std::uint16_t ruleBytes;
        std::memcpy(&ruleBytes, reader.pointer(), 2);
        if (ruleBytes < 2 || !reader.has(ruleBytes)) {
            return false;
        }
        Reader ruleReader(reader.pointer() + 2, ruleBytes - 2u);
        while (ruleReader.has(1)) {
            DwaRule rule;
            rule.suffix = ruleReader.string();
            const std::uint8_t value = ruleReader.u8();
            rule.type = ruleReader.u8();
            if (!ruleReader.ok()) {
                return false;
            }
            rule.cscIndex = (value >> 4) - 1;
            rule.scheme = (value >> 2) & 3;
            rule.caseInsensitive = (value & 2) != 0;
            rules.push_back(rule);
        }
        reader.skip(ruleBytes);
    } else {
        rules = legacyDwaRules();
    }

    // チャンネルごとの扱いを決める(名前の末尾と画素の型が合う最初の規則)。
    const std::size_t channelCount = channels.size();
    std::vector<int> scheme(channelCount, kDwaUnknown);
    std::vector<int> cscIndex(channelCount, -1);
    for (std::size_t c = 0; c < channelCount; ++c) {
        const std::size_t dot = channels[c].name.rfind('.');
        const std::string suffix = dot == std::string::npos ? channels[c].name : channels[c].name.substr(dot + 1);
        for (const DwaRule& rule : rules) {
            const bool same = rule.caseInsensitive ? toLower(rule.suffix) == toLower(suffix) : rule.suffix == suffix;
            if (same && rule.type == channels[c].type) {
                scheme[c] = rule.scheme;
                cscIndex[c] = rule.cscIndex;
                break;
            }
        }
        if (scheme[c] == kDwaLossyDct && channels[c].type == kUint) {
            return false;  // 整数のチャンネルは非可逆にできない(壊れたデータ)。
        }
    }
    // 色の変換の組: 同じ層(最後の「.」まで)の、赤・緑・青がそろったもの。層の名前の順に並べる。
    std::map<std::string, std::array<int, 3>> layers;
    for (std::size_t c = 0; c < channelCount; ++c) {
        if (scheme[c] != kDwaLossyDct || cscIndex[c] < 0 || cscIndex[c] > 2) {
            continue;
        }
        const std::size_t dot = channels[c].name.rfind('.');
        const std::string prefix = dot == std::string::npos ? std::string() : channels[c].name.substr(0, dot + 1);
        auto [it, inserted] = layers.try_emplace(prefix, std::array<int, 3>{-1, -1, -1});
        it->second[static_cast<std::size_t>(cscIndex[c])] = static_cast<int>(c);
    }
    std::vector<std::vector<int>> groups;  // 逆DCTをする組(色の変換の組、残りは1チャンネルずつ)。
    std::vector<bool> grouped(channelCount, false);
    for (const auto& [prefix, members] : layers) {
        if (members[0] >= 0 && members[1] >= 0 && members[2] >= 0) {
            groups.push_back({members[0], members[1], members[2]});
            for (int member : members) {
                grouped[static_cast<std::size_t>(member)] = true;
            }
        }
    }
    for (std::size_t c = 0; c < channelCount; ++c) {
        if (scheme[c] == kDwaLossyDct && !grouped[c]) {
            groups.push_back({static_cast<int>(c)});
        }
    }

    // 各部分のデータの位置。
    const std::uint8_t* p = reader.pointer();
    const std::size_t rest = size - reader.position();
    if (unknownSize + acSize + dcSize + rleSize > rest) {
        return false;
    }
    const std::uint8_t* unknownData = p;
    const std::uint8_t* acData = unknownData + unknownSize;
    const std::uint8_t* dcData = acData + acSize;
    const std::uint8_t* rleData = dcData + dcSize;

    // チャンネルごとの画素(行の順に幅×行数)。
    const std::size_t pixelCount = static_cast<std::size_t>(width) * lines;
    std::vector<std::vector<std::uint8_t>> planes(channelCount);
    for (std::size_t c = 0; c < channelCount; ++c) {
        planes[c].assign(pixelCount * channels[c].bytes(), 0);
    }

    // 扱いの分からないチャンネル: zlibで戻すと、行ごとにそのチャンネルの生の値が並ぶ。
    if (unknownRawSize > 0) {
        std::vector<std::uint8_t> raw(static_cast<std::size_t>(unknownRawSize));
        if (inflateZlib(unknownData, static_cast<std::size_t>(unknownSize), raw.data(), raw.size()) !=
            static_cast<long long>(raw.size())) {
            return false;
        }
        std::size_t offset = 0;
        for (int y = 0; y < lines; ++y) {
            for (std::size_t c = 0; c < channelCount; ++c) {
                if (scheme[c] != kDwaUnknown) {
                    continue;
                }
                const std::size_t row = static_cast<std::size_t>(width) * channels[c].bytes();
                if (offset + row > raw.size()) {
                    return false;
                }
                std::memcpy(planes[c].data() + row * y, raw.data() + offset, row);
                offset += row;
            }
        }
    }

    // RLEのチャンネル(アルファなど): zlibとRLEで戻すと、チャンネルごとに「各画素のnバイト目」の面が並ぶ。
    if (rleRawSize > 0) {
        std::vector<std::uint8_t> unpacked(static_cast<std::size_t>(rleUnpackedSize));
        if (inflateZlib(rleData, static_cast<std::size_t>(rleSize), unpacked.data(), unpacked.size()) !=
            static_cast<long long>(unpacked.size())) {
            return false;
        }
        std::vector<std::uint8_t> raw(static_cast<std::size_t>(rleRawSize));
        if (!unRle(unpacked.data(), unpacked.size(), raw)) {
            return false;
        }
        std::size_t offset = 0;
        for (std::size_t c = 0; c < channelCount; ++c) {
            if (scheme[c] != kDwaRle) {
                continue;
            }
            const int bytes = channels[c].bytes();
            if (offset + pixelCount * bytes > raw.size()) {
                return false;
            }
            for (int byte = 0; byte < bytes; ++byte) {
                const std::uint8_t* plane = raw.data() + offset + pixelCount * byte;
                for (std::size_t i = 0; i < pixelCount; ++i) {
                    planes[c][i * bytes + byte] = plane[i];
                }
            }
            offset += pixelCount * bytes;
        }
    }

    if (!groups.empty()) {
        // 交流成分(ハフマン符号かzlib)と直流成分(zlib + ZIPと同じ並べ替え)。どちらも半精度の値の並び。
        std::vector<std::uint16_t> ac(static_cast<std::size_t>(acCount));
        if (acCount > 0) {
            if (acCompression == 0) {
                if (!hufUncompress(acData, static_cast<std::size_t>(acSize), ac)) {
                    return false;
                }
            } else if (acCompression == 1) {
                if (inflateZlib(acData, static_cast<std::size_t>(acSize), reinterpret_cast<std::uint8_t*>(ac.data()),
                                ac.size() * 2) != static_cast<long long>(ac.size() * 2)) {
                    return false;
                }
            } else {
                return false;
            }
        }
        std::vector<std::uint16_t> dc(static_cast<std::size_t>(dcCount));
        if (dcCount > 0) {
            std::vector<std::uint8_t> unpacked(dc.size() * 2);
            if (inflateZlib(dcData, static_cast<std::size_t>(dcSize), unpacked.data(), unpacked.size()) !=
                static_cast<long long>(unpacked.size())) {
                return false;
            }
            unpredictAndInterleave(unpacked, reinterpret_cast<std::uint8_t*>(dc.data()));
        }
        const int blocksX = (width + 7) / 8;
        const int blocksY = (lines + 7) / 8;
        const std::size_t blockCount = static_cast<std::size_t>(blocksX) * blocksY;
        const std::uint16_t* toLinear = dwaToLinear();
        std::size_t acPosition = 0;
        std::size_t dcPosition = 0;
        for (const std::vector<int>& group : groups) {
            const std::size_t components = group.size();
            if (dcPosition + components * blockCount > dc.size()) {
                return false;
            }
            // 色の変換の組は、赤のチャンネルが「知覚的にリニア(pLinear)」なら非線形の変換をしていない。
            const bool nonlinear = !channels[static_cast<std::size_t>(group[0])].pLinear;
            float block[3][64];
            for (int by = 0; by < blocksY; ++by) {
                for (int bx = 0; bx < blocksX; ++bx) {
                    const std::size_t blockIndex = static_cast<std::size_t>(by) * blocksX + bx;
                    for (std::size_t k = 0; k < components; ++k) {
                        // ジグザグの順の係数: 先頭は直流成分、残りは交流成分のRLE
                        // (0xff00は「残りは全て0」、0xffnnは「0がnn個」)。
                        std::uint16_t zig[64] = {};
                        zig[0] = dc[dcPosition + k * blockCount + blockIndex];
                        int index = 1;
                        int last = 0;
                        while (index < 64) {
                            if (acPosition >= ac.size()) {
                                return false;
                            }
                            const std::uint16_t value = ac[acPosition++];
                            if (value == 0xff00) {
                                index = 64;
                            } else if ((value >> 8) == 0xff) {
                                index += value & 0xff;
                            } else {
                                zig[index] = value;
                                last = index;
                                ++index;
                            }
                        }
                        float* f = block[k];
                        if (last == 0) {
                            // 直流成分だけなら、全ての画素が同じ値。
                            const float value = halfToFloat(zig[0]) * 3.535536e-01f * 3.535536e-01f;
                            for (int i = 0; i < 64; ++i) {
                                f[i] = value;
                            }
                            continue;
                        }
                        for (int i = 0; i < 64; ++i) {
                            f[kZigZag[i]] = halfToFloat(zig[i]);
                        }
                        for (int row = 0; row < 8; ++row) {
                            inverseDct8(f + row * 8, 1);
                        }
                        for (int column = 0; column < 8; ++column) {
                            inverseDct8(f + column, 8);
                        }
                    }
                    if (components == 3) {
                        // YCbCr(BT.709の係数)からRGBへ戻す。
                        for (int i = 0; i < 64; ++i) {
                            const float y = block[0][i];
                            const float cb = block[1][i];
                            const float cr = block[2][i];
                            block[0][i] = y + 1.5747f * cr;
                            block[1][i] = y - 0.1873f * cb - 0.4682f * cr;
                            block[2][i] = y + 1.8556f * cb;
                        }
                    }
                    for (std::size_t k = 0; k < components; ++k) {
                        const std::size_t c = static_cast<std::size_t>(group[k]);
                        for (int yy = 0; yy < 8; ++yy) {
                            const int y = by * 8 + yy;
                            if (y >= lines) {
                                break;
                            }
                            for (int xx = 0; xx < 8; ++xx) {
                                const int x = bx * 8 + xx;
                                if (x >= width) {
                                    break;
                                }
                                std::uint16_t half = floatToHalf(block[k][yy * 8 + xx]);
                                if (nonlinear) {
                                    half = toLinear[half];
                                }
                                const std::size_t i = static_cast<std::size_t>(y) * width + x;
                                if (channels[c].type == kHalf) {
                                    std::memcpy(planes[c].data() + i * 2, &half, 2);
                                } else {
                                    const float value = halfToFloat(half);
                                    std::memcpy(planes[c].data() + i * 4, &value, 4);
                                }
                            }
                        }
                    }
                }
            }
            dcPosition += components * blockCount;
        }
    }

    std::uint8_t* o = out;
    for (int y = 0; y < lines; ++y) {
        for (std::size_t c = 0; c < channelCount; ++c) {
            const std::size_t row = static_cast<std::size_t>(width) * channels[c].bytes();
            std::memcpy(o, planes[c].data() + row * y, row);
            o += row;
        }
    }
    return true;
}

/**
 * @brief ファイルを全部読む。
 * @param path パス。
 * @param data 格納先。
 * @return 読めたらtrue。
 */
bool readFile(const std::wstring& path, std::vector<std::uint8_t>& data) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                              OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    LARGE_INTEGER size{};
    bool ok = GetFileSizeEx(file, &size) && size.QuadPart > 0 && size.QuadPart < (1ll << 32);
    if (ok) {
        data.resize(static_cast<std::size_t>(size.QuadPart));
        DWORD read = 0;
        ok = ReadFile(file, data.data(), static_cast<DWORD>(data.size()), &read, nullptr) && read == data.size();
    }
    CloseHandle(file);
    return ok;
}

/**
 * @brief 色度から、知っている色域を選ぶ。
 * @param c 赤・緑・青・白のxy。
 * @param primaries 格納先。
 * @return 知っている色域ならtrue。
 */
bool matchPrimaries(const float c[8], ColorPrimaries& primaries) {
    struct Known {
        ColorPrimaries primaries;
        float xy[8];
    };
    static const Known kKnown[] = {
        {ColorPrimaries::Bt709, {0.64f, 0.33f, 0.30f, 0.60f, 0.15f, 0.06f, 0.3127f, 0.3290f}},
        {ColorPrimaries::Bt2020, {0.708f, 0.292f, 0.170f, 0.797f, 0.131f, 0.046f, 0.3127f, 0.3290f}},
        {ColorPrimaries::DisplayP3, {0.680f, 0.320f, 0.265f, 0.690f, 0.150f, 0.060f, 0.3127f, 0.3290f}},
        {ColorPrimaries::DciP3, {0.680f, 0.320f, 0.265f, 0.690f, 0.150f, 0.060f, 0.314f, 0.351f}},
        {ColorPrimaries::AcesAp0, {0.7347f, 0.2653f, 0.0f, 1.0f, 0.0001f, -0.077f, 0.32168f, 0.33767f}},
        {ColorPrimaries::AcesAp1, {0.713f, 0.293f, 0.165f, 0.830f, 0.128f, 0.044f, 0.32168f, 0.33767f}},
    };
    for (const Known& known : kKnown) {
        bool same = true;
        for (int i = 0; i < 8; ++i) {
            same = same && std::abs(known.xy[i] - c[i]) < 0.002f;
        }
        if (same) {
            primaries = known.primaries;
            return true;
        }
    }
    return false;
}

}  // namespace

std::uint16_t floatToHalf(float value) {
    std::uint32_t bits;
    std::memcpy(&bits, &value, 4);
    const std::uint32_t sign = (bits >> 16) & 0x8000u;
    const std::uint32_t exponent = (bits >> 23) & 0xFFu;
    std::uint32_t mantissa = bits & 0x7FFFFFu;
    if (exponent == 0xFF) {
        return static_cast<std::uint16_t>(sign | 0x7C00u | (mantissa ? 0x200u : 0u));  // 無限大・非数。
    }
    const int e = static_cast<int>(exponent) - 127 + 15;
    if (e >= 31) {
        return static_cast<std::uint16_t>(sign | 0x7C00u);  // 大きすぎるので無限大。
    }
    if (e <= 0) {
        if (e < -10) {
            return static_cast<std::uint16_t>(sign);  // 小さすぎるので0。
        }
        // 非正規化数。最も近い値に丸める(ちょうど中間なら偶数へ)。
        mantissa |= 0x800000u;
        const int shift = 14 - e;
        std::uint32_t half = mantissa >> shift;
        const std::uint32_t rest = mantissa & ((1u << shift) - 1u);
        const std::uint32_t halfway = 1u << (shift - 1);
        if (rest > halfway || (rest == halfway && (half & 1u))) {
            ++half;
        }
        return static_cast<std::uint16_t>(sign | half);
    }
    std::uint32_t half = (static_cast<std::uint32_t>(e) << 10) | (mantissa >> 13);
    const std::uint32_t rest = mantissa & 0x1FFFu;
    if (rest > 0x1000u || (rest == 0x1000u && (half & 1u))) {
        ++half;  // 繰り上がりで指数が増えても正しい値になる(最大を超えれば無限大)。
    }
    return static_cast<std::uint16_t>(sign | half);
}

float halfToFloat(std::uint16_t half) {
    const std::uint32_t sign = static_cast<std::uint32_t>(half & 0x8000u) << 16;
    const std::uint32_t exponent = (half >> 10) & 0x1Fu;
    std::uint32_t mantissa = half & 0x3FFu;
    std::uint32_t bits;
    if (exponent == 0) {
        if (mantissa == 0) {
            bits = sign;
        } else {
            int e = -1;
            do {
                ++e;
                mantissa <<= 1;
            } while (!(mantissa & 0x400u));
            bits = sign | (static_cast<std::uint32_t>(127 - 15 - e) << 23) | ((mantissa & 0x3FFu) << 13);
        }
    } else if (exponent == 31) {
        bits = sign | 0x7F800000u | (mantissa << 13);
    } else {
        bits = sign | ((exponent - 15 + 127) << 23) | (mantissa << 13);
    }
    float value;
    std::memcpy(&value, &bits, 4);
    return value;
}

bool readExr(const std::wstring& path, ExrImage& image, std::wstring& error, const std::atomic<bool>* cancel) {
    std::vector<std::uint8_t> file;
    if (!readFile(path, file)) {
        error = L"Cannot read the EXR file";
        return false;
    }
    Reader reader(file.data(), file.size());
    if (reader.u32() != 20000630u) {
        error = L"Not an EXR file";
        return false;
    }
    const std::uint32_t version = reader.u32();
    const bool singleTiled = (version & 0x200u) != 0;
    const bool deep = (version & 0x800u) != 0;
    const bool multipart = (version & 0x1000u) != 0;
    if (deep) {
        error = L"Deep EXR files are not supported";
        return false;
    }
    // 見出し。複数の部分なら、空の見出しまで続く(使うのは最初の部分)。
    std::vector<Header> headers;
    for (;;) {
        if (multipart && reader.has(1) && *reader.pointer() == 0) {
            reader.u8();
            break;
        }
        Header header;
        if (!parseHeader(reader, header)) {
            error = L"Cannot read the EXR header";
            return false;
        }
        header.tiled = header.tiled && (singleTiled || multipart);
        if (multipart && header.type.find("deep") != std::string::npos) {
            header.channels.clear();
        }
        headers.push_back(header);
        if (!multipart) {
            break;
        }
    }
    if (headers.empty() || headers[0].channels.empty()) {
        error = L"The EXR file has no readable image";
        return false;
    }
    const Header& header = headers[0];
    if (header.compression > kDwab) {
        error = L"Unsupported EXR compression";
        return false;
    }
    for (const Channel& channel : header.channels) {
        if (channel.xSampling != 1 || channel.ySampling != 1) {
            error = L"EXR files with subsampled channels are not supported";
            return false;
        }
        if (channel.type < kUint || channel.type > kFloat) {
            error = L"Unsupported EXR pixel type";
            return false;
        }
    }
    const int dataWidth = header.dataMaxX - header.dataMinX + 1;
    const int dataHeight = header.dataMaxY - header.dataMinY + 1;
    const int width = header.displayMaxX - header.displayMinX + 1;
    const int height = header.displayMaxY - header.displayMinY + 1;
    if (dataWidth <= 0 || dataHeight <= 0 || width <= 0 || height <= 0 || width > 32768 || height > 32768) {
        error = L"Invalid EXR image size";
        return false;
    }

    // 使うチャンネル: R・G・B・A。無ければ「名前.R」などの最初の層、さらに無ければY(明るさだけ)。
    int rgba[4] = {-1, -1, -1, -1};
    const char* letters[4] = {"R", "G", "B", "A"};
    auto find = [&](const std::string& name) {
        for (std::size_t i = 0; i < header.channels.size(); ++i) {
            if (header.channels[i].name == name) {
                return static_cast<int>(i);
            }
        }
        return -1;
    };
    for (int i = 0; i < 4; ++i) {
        rgba[i] = find(letters[i]);
    }
    if (rgba[0] < 0 && rgba[1] < 0 && rgba[2] < 0) {
        for (const Channel& channel : header.channels) {
            const std::size_t dot = channel.name.rfind('.');
            if (dot != std::string::npos && channel.name.substr(dot + 1) == "R") {
                const std::string layer = channel.name.substr(0, dot + 1);
                for (int i = 0; i < 4; ++i) {
                    rgba[i] = find(layer + letters[i]);
                }
                break;
            }
        }
    }
    if (rgba[0] < 0 && rgba[1] < 0 && rgba[2] < 0) {
        int gray = find("Y");
        if (gray < 0) {
            gray = 0;  // 名前が分からなければ最初のチャンネルを灰色として出す。
        }
        rgba[0] = rgba[1] = rgba[2] = gray;
    }

    // チャンクの位置の表。最初の部分の表は見出しのすぐ後にある。
    int chunkCount = header.chunkCount;
    if (chunkCount < 0) {
        if (header.tiled) {
            if (header.tileWidth <= 0 || header.tileHeight <= 0) {
                error = L"Invalid EXR tile size";
                return false;
            }
            chunkCount = ((dataWidth + header.tileWidth - 1) / header.tileWidth) *
                         ((dataHeight + header.tileHeight - 1) / header.tileHeight);
        } else {
            const int lines = linesPerChunk(header.compression);
            chunkCount = (dataHeight + lines - 1) / lines;
        }
    }
    std::vector<std::uint64_t> offsets(static_cast<std::size_t>(chunkCount));
    for (std::uint64_t& offset : offsets) {
        offset = reader.u64();
    }
    if (!reader.ok()) {
        error = L"Cannot read the EXR chunk offset table";
        return false;
    }

    image = ExrImage{};
    image.width = width;
    image.height = height;
    image.pixels.assign(static_cast<std::size_t>(width) * height * 4, 0);
    if (rgba[3] < 0) {
        for (std::size_t i = 3; i < image.pixels.size(); i += 4) {
            image.pixels[i] = 0x3C00;  // アルファが無ければ1.0。
        }
    }
    image.pixelAspect = header.pixelAspect > 0.0f ? header.pixelAspect : 1.0f;
    if (header.hasChromaticities) {
        image.primariesFromFile = matchPrimaries(header.chromaticities, image.primaries);
    }

    // 1つのチャンクを戻して、表示範囲の中の位置へ置く。
    auto place = [&](int x0, int y0, int blockWidth, int lines, const std::uint8_t* data) {
        const std::uint8_t* p = data;
        for (int y = 0; y < lines; ++y) {
            const int outY = y0 + y - header.displayMinY;
            for (std::size_t c = 0; c < header.channels.size(); ++c) {
                const Channel& channel = header.channels[c];
                for (int slot = 0; slot < 4; ++slot) {
                    if (rgba[slot] != static_cast<int>(c) || outY < 0 || outY >= height) {
                        continue;
                    }
                    for (int x = 0; x < blockWidth; ++x) {
                        const int outX = x0 + x - header.displayMinX;
                        if (outX < 0 || outX >= width) {
                            continue;
                        }
                        std::uint16_t value;
                        if (channel.type == kHalf) {
                            std::memcpy(&value, p + static_cast<std::size_t>(x) * 2, 2);
                        } else if (channel.type == kFloat) {
                            float f;
                            std::memcpy(&f, p + static_cast<std::size_t>(x) * 4, 4);
                            value = floatToHalf(f);
                        } else {
                            std::uint32_t u;
                            std::memcpy(&u, p + static_cast<std::size_t>(x) * 4, 4);
                            value = floatToHalf(static_cast<float>(u));
                        }
                        image.pixels[(static_cast<std::size_t>(outY) * width + outX) * 4 + slot] = value;
                    }
                }
                p += static_cast<std::size_t>(blockWidth) * channel.bytes();
            }
        }
    };

    // チャンクは互いに重ならない場所へ置くので、並行して戻せる(1枚の画像でもCPUの複数のコアを使う)。
    // 戻り値は失敗の説明(成功・読み飛ばしならnullptr)。
    auto decodeChunk = [&](std::uint64_t offset) -> const wchar_t* {
        if (cancel && cancel->load(std::memory_order_relaxed)) {
            return L"Reading was canceled";
        }
        std::vector<std::uint8_t> block;
        if (offset == 0 || offset >= file.size()) {
            return nullptr;  // 書かれていないチャンク(途中までのファイルなど)。
        }
        Reader chunk(file.data(), file.size(), static_cast<std::size_t>(offset));
        if (multipart && chunk.i32() != 0) {
            return nullptr;  // 最初の部分以外のチャンク。
        }
        int x0 = header.dataMinX;
        int y0 = 0;
        int blockWidth = dataWidth;
        int lines = 0;
        if (header.tiled) {
            const int tileX = chunk.i32();
            const int tileY = chunk.i32();
            const int levelX = chunk.i32();
            const int levelY = chunk.i32();
            if (levelX != 0 || levelY != 0) {
                return nullptr;  // 最も細かい段だけを使う。
            }
            x0 = header.dataMinX + tileX * header.tileWidth;
            y0 = header.dataMinY + tileY * header.tileHeight;
            blockWidth = std::min(header.tileWidth, header.dataMaxX - x0 + 1);
            lines = std::min(header.tileHeight, header.dataMaxY - y0 + 1);
        } else {
            y0 = chunk.i32();
            lines = std::min(linesPerChunk(header.compression), header.dataMaxY - y0 + 1);
        }
        const std::uint32_t size = chunk.u32();
        if (!chunk.ok() || blockWidth <= 0 || lines <= 0 || !chunk.has(size)) {
            return L"The EXR chunk is corrupt";
        }
        std::size_t rawSize = 0;
        for (const Channel& channel : header.channels) {
            rawSize += static_cast<std::size_t>(blockWidth) * channel.bytes();
        }
        rawSize *= static_cast<std::size_t>(lines);
        const std::uint8_t* data = chunk.pointer();
        if (size == rawSize || header.compression == kNone) {
            if (size < rawSize) {
                return L"The EXR chunk is corrupt";
            }
            place(x0, y0, blockWidth, lines, data);
            return nullptr;
        }
        block.assign(rawSize, 0);
        bool ok = false;
        switch (header.compression) {
        case kRle: {
            std::vector<std::uint8_t> unpacked(rawSize);
            ok = unRle(data, size, unpacked);
            if (ok) {
                unpredictAndInterleave(unpacked, block.data());
            }
            break;
        }
        case kZips:
        case kZip: {
            std::vector<std::uint8_t> unpacked(rawSize);
            ok = inflateZlib(data, size, unpacked.data(), unpacked.size()) == static_cast<long long>(rawSize);
            if (ok) {
                unpredictAndInterleave(unpacked, block.data());
            }
            break;
        }
        case kPiz:
            ok = unPiz(data, size, header.channels, blockWidth, lines, block.data(), rawSize);
            break;
        case kPxr24:
            ok = unPxr24(data, size, header.channels, blockWidth, lines, block.data(), rawSize);
            break;
        case kB44:
        case kB44a:
            ok = unB44(data, size, header.channels, blockWidth, lines, block.data());
            break;
        case kDwaa:
        case kDwab:
            ok = unDwa(data, size, header.channels, blockWidth, lines, block.data());
            break;
        default:
            break;
        }
        if (!ok) {
            return L"Cannot decompress the EXR data (the file may be corrupt)";
        }
        place(x0, y0, blockWidth, lines, block.data());
        return nullptr;
    };

    std::atomic<const wchar_t*> failure{nullptr};
    if (header.compression == kNone || offsets.size() < 4) {
        for (std::uint64_t offset : offsets) {
            if (const wchar_t* message = decodeChunk(offset)) {
                failure = message;
                break;
            }
        }
    } else {
        concurrency::parallel_for(std::size_t{0}, offsets.size(), [&](std::size_t i) {
            if (failure.load() == nullptr) {
                if (const wchar_t* message = decodeChunk(offsets[i])) {
                    failure = message;
                }
            }
        });
    }
    if (const wchar_t* message = failure.load()) {
        error = message;
        return false;
    }
    return true;
}

}  // namespace frameplayer
