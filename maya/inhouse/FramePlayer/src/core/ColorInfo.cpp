/**
 * @file ColorInfo.cpp
 * @brief 色の解釈と変換式の実装。
 */
#include "core/ColorInfo.h"

#include <algorithm>
#include <cmath>

namespace frameplayer {

namespace {

/** @brief 3行3列の行列(行優先)。 */
struct Mat3 {
    double m[3][3]{};
};

/**
 * @brief 行列の積を求める。
 * @param a 左の行列。
 * @param b 右の行列。
 * @return a×b。
 */
Mat3 multiply(const Mat3& a, const Mat3& b) {
    Mat3 r;
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            for (int k = 0; k < 3; ++k) {
                r.m[i][j] += a.m[i][k] * b.m[k][j];
            }
        }
    }
    return r;
}

/**
 * @brief 逆行列を求める。
 * @param a 対象の行列(正則であること)。
 * @return aの逆行列。
 */
Mat3 inverse(const Mat3& a) {
    const auto& m = a.m;
    const double det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
                       m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
                       m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
    Mat3 r;
    r.m[0][0] = (m[1][1] * m[2][2] - m[1][2] * m[2][1]) / det;
    r.m[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) / det;
    r.m[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) / det;
    r.m[1][0] = (m[1][2] * m[2][0] - m[1][0] * m[2][2]) / det;
    r.m[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) / det;
    r.m[1][2] = (m[0][2] * m[1][0] - m[0][0] * m[1][2]) / det;
    r.m[2][0] = (m[1][0] * m[2][1] - m[1][1] * m[2][0]) / det;
    r.m[2][1] = (m[0][1] * m[2][0] - m[0][0] * m[2][1]) / det;
    r.m[2][2] = (m[0][0] * m[1][1] - m[0][1] * m[1][0]) / det;
    return r;
}

/** @brief 色域の三原色と白のxy色度。 */
struct Chromaticities {
    double rx, ry, gx, gy, bx, by, wx, wy;
};

constexpr double kD65x = 0.3127;
constexpr double kD65y = 0.3290;

/**
 * @brief 色域の三原色と白の色度を返す。
 * @param primaries 色域。
 * @return 色度。
 */
Chromaticities chromaticitiesOf(ColorPrimaries primaries) {
    switch (primaries) {
    case ColorPrimaries::Bt601_525:
        return {0.630, 0.340, 0.310, 0.595, 0.155, 0.070, kD65x, kD65y};
    case ColorPrimaries::Bt601_625:
        return {0.640, 0.330, 0.290, 0.600, 0.150, 0.060, kD65x, kD65y};
    case ColorPrimaries::Bt2020:
        return {0.708, 0.292, 0.170, 0.797, 0.131, 0.046, kD65x, kD65y};
    case ColorPrimaries::DisplayP3:
        return {0.680, 0.320, 0.265, 0.690, 0.150, 0.060, kD65x, kD65y};
    case ColorPrimaries::DciP3:
        return {0.680, 0.320, 0.265, 0.690, 0.150, 0.060, 0.314, 0.351};
    case ColorPrimaries::AcesAp0:
        return {0.7347, 0.2653, 0.0, 1.0, 0.0001, -0.077, 0.32168, 0.33767};
    case ColorPrimaries::AcesAp1:
        return {0.713, 0.293, 0.165, 0.830, 0.128, 0.044, 0.32168, 0.33767};
    case ColorPrimaries::Bt709:
    default:
        return {0.640, 0.330, 0.300, 0.600, 0.150, 0.060, kD65x, kD65y};
    }
}

/**
 * @brief xy色度から、明るさ1のXYZを求める。
 * @param x 色度x。
 * @param y 色度y。
 * @param out X, Y, Zの格納先。
 */
void xyToXyz(double x, double y, double out[3]) {
    out[0] = x / y;
    out[1] = 1.0;
    out[2] = (1.0 - x - y) / y;
}

/**
 * @brief 色域のリニアなRGBをXYZにする行列を求める(SMPTE RP 177の求め方)。
 * @param c 色域の色度。
 * @return 行列。白(1,1,1)が白の色度で明るさ1のXYZになる。
 */
Mat3 rgbToXyz(const Chromaticities& c) {
    double r[3], g[3], b[3], w[3];
    xyToXyz(c.rx, c.ry, r);
    xyToXyz(c.gx, c.gy, g);
    xyToXyz(c.bx, c.by, b);
    xyToXyz(c.wx, c.wy, w);
    Mat3 m;
    for (int i = 0; i < 3; ++i) {
        m.m[i][0] = r[i];
        m.m[i][1] = g[i];
        m.m[i][2] = b[i];
    }
    // 各原色の強さを、白(1,1,1)が白のXYZになるように決める。
    const Mat3 inv = inverse(m);
    double s[3];
    for (int i = 0; i < 3; ++i) {
        s[i] = inv.m[i][0] * w[0] + inv.m[i][1] * w[1] + inv.m[i][2] * w[2];
    }
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            m.m[i][j] *= s[j];
        }
    }
    return m;
}

/**
 * @brief 白の色度を変えるBradford法の行列(XYZに掛ける)を求める。
 * @param fromX 元の白のx。
 * @param fromY 元の白のy。
 * @param toX 先の白のx。
 * @param toY 先の白のy。
 * @return 行列。
 */
Mat3 bradford(double fromX, double fromY, double toX, double toY) {
    const Mat3 cone{{{0.8951, 0.2664, -0.1614}, {-0.7502, 1.7135, 0.0367}, {0.0389, -0.0685, 1.0296}}};
    double from[3], to[3];
    xyToXyz(fromX, fromY, from);
    xyToXyz(toX, toY, to);
    double fromCone[3]{}, toCone[3]{};
    for (int i = 0; i < 3; ++i) {
        for (int k = 0; k < 3; ++k) {
            fromCone[i] += cone.m[i][k] * from[k];
            toCone[i] += cone.m[i][k] * to[k];
        }
    }
    Mat3 scale;
    for (int i = 0; i < 3; ++i) {
        scale.m[i][i] = toCone[i] / fromCone[i];
    }
    return multiply(inverse(cone), multiply(scale, cone));
}

/**
 * @brief 行列の種類から、明るさを作る赤と青の重み(Kr, Kb)を返す。
 * @param matrix 行列の種類。
 * @param kr 赤の重みの格納先。
 * @param kb 青の重みの格納先。
 */
void lumaWeights(ColorMatrix matrix, double& kr, double& kb) {
    switch (matrix) {
    case ColorMatrix::Bt601:
        kr = 0.299;
        kb = 0.114;
        break;
    case ColorMatrix::Bt2020:
        kr = 0.2627;
        kb = 0.0593;
        break;
    case ColorMatrix::Smpte240m:
        kr = 0.212;
        kb = 0.087;
        break;
    case ColorMatrix::Fcc:
        kr = 0.30;
        kb = 0.11;
        break;
    case ColorMatrix::Bt709:
    default:
        kr = 0.2126;
        kb = 0.0722;
        break;
    }
}

/**
 * @brief 推定・手動の印を付けた項目の文字を作る。
 * @param name 項目の名前。
 * @param source 出所。
 * @return 「BT.709(推定)」のような文字。
 */
std::wstring marked(const wchar_t* name, ColorSource source) {
    std::wstring text = name;
    if (source == ColorSource::Guess) {
        text += L" (guessed)";
    } else if (source == ColorSource::Manual) {
        text += L" (manual)";
    }
    return text;
}

}  // namespace

ColorInfo applyOverride(ColorInfo info, const ColorOverride& override) {
    if (override.matrix >= 0) {
        info.matrix = static_cast<ColorMatrix>(override.matrix);
        info.matrixSource = ColorSource::Manual;
    }
    if (override.range >= 0) {
        info.range = static_cast<ColorRange>(override.range);
        info.rangeSource = ColorSource::Manual;
    }
    if (override.primaries >= 0) {
        info.primaries = static_cast<ColorPrimaries>(override.primaries);
        info.primariesSource = ColorSource::Manual;
    }
    if (override.transfer >= 0) {
        info.transfer = static_cast<TransferFunction>(override.transfer);
        info.transferSource = ColorSource::Manual;
    }
    return info;
}

ColorInfo guessColorInfo(int width, int height) {
    ColorInfo info;
    const bool hd = width > 1024 || height > 576;
    info.matrix = hd ? ColorMatrix::Bt709 : ColorMatrix::Bt601;
    info.primaries = hd                                   ? ColorPrimaries::Bt709
                     : (height == 576 || height == 288) ? ColorPrimaries::Bt601_625
                                                        : ColorPrimaries::Bt601_525;
    return info;
}

void applyH273(ColorInfo& info, int primaries, int transfer, int matrix, int fullRange) {
    switch (primaries) {
    case 1:
        info.primaries = ColorPrimaries::Bt709;
        break;
    case 5:
    case 22:  // EBU Tech 3213は625本と同じ三原色。
        info.primaries = ColorPrimaries::Bt601_625;
        break;
    case 6:
    case 7:  // SMPTE 240Mは525本と同じ三原色。
        info.primaries = ColorPrimaries::Bt601_525;
        break;
    case 9:
        info.primaries = ColorPrimaries::Bt2020;
        break;
    case 11:
        info.primaries = ColorPrimaries::DciP3;
        break;
    case 12:
        info.primaries = ColorPrimaries::DisplayP3;
        break;
    default:
        primaries = -1;  // 不明・未対応は推定のまま。
        break;
    }
    if (primaries >= 0) {
        info.primariesSource = ColorSource::File;
    }
    switch (transfer) {
    case 8:
        info.transfer = TransferFunction::Linear;
        break;
    case 16:
        info.transfer = TransferFunction::Pq;
        break;
    case 18:
        info.transfer = TransferFunction::Hlg;
        break;
    case 1:   // BT.709
    case 4:   // ガンマ2.2
    case 5:   // ガンマ2.8
    case 6:   // BT.601
    case 7:   // SMPTE 240M
    case 13:  // sRGB
    case 14:  // BT.2020(10bit)
    case 15:  // BT.2020(12bit)
        info.transfer = TransferFunction::Sdr;
        break;
    default:
        transfer = -1;
        break;
    }
    if (transfer >= 0) {
        info.transferSource = ColorSource::File;
    }
    switch (matrix) {
    case 1:
        info.matrix = ColorMatrix::Bt709;
        break;
    case 4:
        info.matrix = ColorMatrix::Fcc;
        break;
    case 5:
    case 6:
        info.matrix = ColorMatrix::Bt601;
        break;
    case 7:
        info.matrix = ColorMatrix::Smpte240m;
        break;
    case 9:
    case 10:  // 定輝度のBT.2020は非定輝度として扱う(実際の動画はほぼ無い)。
        info.matrix = ColorMatrix::Bt2020;
        break;
    default:
        matrix = -1;
        break;
    }
    if (matrix >= 0) {
        info.matrixSource = ColorSource::File;
    }
    if (fullRange >= 0) {
        info.range = fullRange ? ColorRange::Full : ColorRange::Limited;
        info.rangeSource = ColorSource::File;
    }
}

const wchar_t* colorName(ColorMatrix value) {
    switch (value) {
    case ColorMatrix::Bt601:
        return L"BT.601";
    case ColorMatrix::Bt2020:
        return L"BT.2020";
    case ColorMatrix::Smpte240m:
        return L"SMPTE 240M";
    case ColorMatrix::Fcc:
        return L"FCC";
    case ColorMatrix::Bt709:
    default:
        return L"BT.709";
    }
}

const wchar_t* colorName(ColorRange value) {
    return value == ColorRange::Full ? L"Full (0-255)" : L"Limited (16-235)";
}

const wchar_t* colorName(ColorPrimaries value) {
    switch (value) {
    case ColorPrimaries::Bt601_525:
        return L"BT.601 (525-line)";
    case ColorPrimaries::Bt601_625:
        return L"BT.601 (625-line)";
    case ColorPrimaries::Bt2020:
        return L"BT.2020";
    case ColorPrimaries::DisplayP3:
        return L"Display P3";
    case ColorPrimaries::DciP3:
        return L"DCI-P3";
    case ColorPrimaries::AcesAp0:
        return L"ACES(AP0)";
    case ColorPrimaries::AcesAp1:
        return L"ACEScg(AP1)";
    case ColorPrimaries::Bt709:
    default:
        return L"BT.709";
    }
}

const wchar_t* colorName(TransferFunction value) {
    switch (value) {
    case TransferFunction::Linear:
        return L"Linear";
    case TransferFunction::Pq:
        return L"HDR(PQ)";
    case TransferFunction::Hlg:
        return L"HDR(HLG)";
    case TransferFunction::Sdr:
    default:
        return L"SDR";
    }
}

std::wstring describeColor(const ColorInfo& info) {
    std::wstring text;
    if (info.rgb) {
        text = L"RGB";  // 画像はRGBのままなので、YUVの行列・範囲は無い。
    } else {
        text = L"Matrix " + marked(colorName(info.matrix), info.matrixSource);
        text += L" / " + marked(colorName(info.range), info.rangeSource);
    }
    text += L" / Primaries " + marked(colorName(info.primaries), info.primariesSource);
    text += L" / " + marked(colorName(info.transfer), info.transferSource);
    text += L" / " + std::to_wstring(info.bitDepth) + L"bit";
    if (info.isHdr() && info.maxContentNits > 0.0f) {
        text += L" / Peak " + std::to_wstring(static_cast<int>(info.maxContentNits + 0.5f)) + L"cd/m²";
    }
    return text;
}

void yuvToRgbMatrix(const ColorInfo& info, bool p010, float out[12]) {
    // テクスチャの値(0〜1)を、元の整数の値(コード値)に戻す倍率。P010は10bitの値を左に6bitずらして持つ。
    const int bits = p010 ? 10 : 8;
    const double toCode = p010 ? 65535.0 / 64.0 : 255.0;
    const double unit = std::ldexp(1.0, bits - 8);  // 8bitの1段が何段に当たるか。
    double yOffset, yRange, cOffset, cRange;
    if (info.range == ColorRange::Full) {
        // H.273: 全範囲は Y = (2^n - 1)×E'Y、C = (2^n - 1)×E'C + 2^(n-1)。
        yOffset = 0.0;
        yRange = std::ldexp(1.0, bits) - 1.0;
        cOffset = std::ldexp(1.0, bits - 1);
        cRange = yRange;
    } else {
        // BT.601/709/2020: 映像用は Y = 219×E'Y + 16、C = 224×E'C + 128(8bitの場合。nbitは2^(n-8)倍)。
        yOffset = 16.0 * unit;
        yRange = 219.0 * unit;
        cOffset = 128.0 * unit;
        cRange = 224.0 * unit;
    }
    double kr, kb;
    lumaWeights(info.matrix, kr, kb);
    const double kg = 1.0 - kr - kb;
    // E'R = E'Y + 2(1-Kr)E'Cr、E'B = E'Y + 2(1-Kb)E'Cb、E'G = (E'Y - Kr E'R - Kb E'B) / Kg。
    const double rCr = 2.0 * (1.0 - kr);
    const double bCb = 2.0 * (1.0 - kb);
    const double gCb = -bCb * kb / kg;
    const double gCr = -rCr * kr / kg;
    const double ys = toCode / yRange;
    const double yc = -yOffset / yRange;
    const double cs = toCode / cRange;
    const double cc = -cOffset / cRange;
    const double rows[3][3] = {{1.0, 0.0, rCr}, {1.0, gCb, gCr}, {1.0, bCb, 0.0}};
    for (int i = 0; i < 3; ++i) {
        out[i * 4 + 0] = static_cast<float>(rows[i][0] * ys);
        out[i * 4 + 1] = static_cast<float>(rows[i][1] * cs);
        out[i * 4 + 2] = static_cast<float>(rows[i][2] * cs);
        out[i * 4 + 3] = static_cast<float>(rows[i][0] * yc + (rows[i][1] + rows[i][2]) * cc);
    }
}

void gamutToBt709(ColorPrimaries primaries, float out[9]) {
    const Chromaticities source = chromaticitiesOf(primaries);
    const Chromaticities target = chromaticitiesOf(ColorPrimaries::Bt709);
    Mat3 toXyz = rgbToXyz(source);
    if (source.wx != target.wx || source.wy != target.wy) {
        toXyz = multiply(bradford(source.wx, source.wy, target.wx, target.wy), toXyz);
    }
    const Mat3 m = multiply(inverse(rgbToXyz(target)), toXyz);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            out[i * 3 + j] = static_cast<float>(primaries == ColorPrimaries::Bt709 ? (i == j ? 1.0 : 0.0) : m.m[i][j]);
        }
    }
}

void convertPlanesToBgra(const std::uint8_t* planes, int width, int height, PixelLayout layout, const ColorInfo& info,
                         int outWidth, int outHeight, std::uint32_t* out) {
    const bool p010 = layout == PixelLayout::P010;
    const bool packed = layout == PixelLayout::Yuy2;
    float m[12];
    yuvToRgbMatrix(info, p010, m);
    const int bytesPerValue = p010 ? 2 : 1;
    // YUY2は1行が幅×2バイトで、明るさは偶数バイト目、色は4バイトごとの1・3バイト目(U・V)にある。
    const std::size_t lumaRow = static_cast<std::size_t>(width) * (packed ? 2 : bytesPerValue);
    const std::uint8_t* chroma = packed ? planes : planes + lumaRow * height;
    const int chromaWidth = width / 2;
    const int chromaHeight = packed ? height : height / 2;
    // テクスチャと同じ0〜1の値として読む。
    auto value = [&](const std::uint8_t* p) {
        return p010 ? (p[0] | (p[1] << 8)) / 65535.0f : p[0] / 255.0f;
    };
    auto chromaAt = [&](int cx, int cy, int component) {
        cx = std::clamp(cx, 0, chromaWidth - 1);
        cy = std::clamp(cy, 0, chromaHeight - 1);
        if (packed) {
            return value(chroma + lumaRow * cy + static_cast<std::size_t>(cx) * 4 + 1 + component * 2);
        }
        return value(chroma + lumaRow * cy + (static_cast<std::size_t>(cx) * 2 + component) * bytesPerValue);
    };
    // 色の画素の位置(明るさの画素の単位)。描画のシェーダーと同じ決まり。
    const float offsetX = info.siting == ChromaSiting::Center ? 0.5f : 0.0f;
    const float offsetY = info.siting == ChromaSiting::TopLeft ? 0.0f : 0.5f;
    for (int outY = 0; outY < outHeight; ++outY) {
        // 縮めるときは、作る画素の中心に最も近い元の画素を使う。
        const int y = std::min(height - 1, static_cast<int>((outY + 0.5) * height / outHeight));
        // YUY2(4:2:2)は色の画素が縦には間引かれていない。
        const float cyf = packed ? static_cast<float>(y) : (y - offsetY) / 2.0f;
        const int cy0 = static_cast<int>(std::floor(cyf));
        const float fy = cyf - cy0;
        for (int outX = 0; outX < outWidth; ++outX) {
            const int x = std::min(width - 1, static_cast<int>((outX + 0.5) * width / outWidth));
            const float cxf = (x - offsetX) / 2.0f;
            const int cx0 = static_cast<int>(std::floor(cxf));
            const float fx = cxf - cx0;
            float uv[2];
            for (int c = 0; c < 2; ++c) {
                const float top = chromaAt(cx0, cy0, c) * (1 - fx) + chromaAt(cx0 + 1, cy0, c) * fx;
                const float bottom = chromaAt(cx0, cy0 + 1, c) * (1 - fx) + chromaAt(cx0 + 1, cy0 + 1, c) * fx;
                uv[c] = top * (1 - fy) + bottom * fy;
            }
            const float luma = value(planes + lumaRow * y + static_cast<std::size_t>(x) * (packed ? 2 : bytesPerValue));
            std::uint32_t pixel = 0xFF000000u;
            for (int i = 0; i < 3; ++i) {
                const float v = m[i * 4] * luma + m[i * 4 + 1] * uv[0] + m[i * 4 + 2] * uv[1] + m[i * 4 + 3];
                const auto byte = static_cast<std::uint32_t>(std::clamp(v, 0.0f, 1.0f) * 255.0f + 0.5f);
                pixel |= byte << (16 - 8 * i);  // メモリ上はB,G,R,Aの順(R=16bit目、G=8bit目、B=0bit目)。
            }
            out[static_cast<std::size_t>(outY) * outWidth + outX] = pixel;
        }
    }
}

}  // namespace frameplayer
