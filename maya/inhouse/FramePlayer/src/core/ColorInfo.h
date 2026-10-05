/**
 * @file ColorInfo.h
 * @brief 動画の色の解釈(YUVの行列・範囲・色域・伝達関数)と、規格から求める変換式。
 *
 * 式はすべて規格(ITU-R BT.601/709/2020/2100、ITU-T H.273、IEC 61966-2-1、SMPTE RP 177)から求める。
 * 表示の考え方(ニュートラル):
 *   - SDRでBT.709の色域の動画は、YUVからRGBへ戻した値をそのまま画面へ出す(味付けをしない)。
 *   - 色域が違う動画(BT.2020・P3・SDのBT.601など)は、画面の色域(BT.709/sRGB)の同じ色になるよう変換する。
 *   - HDR(PQ・HLG)は、HDRの画面なら明るさをそのまま、SDRの画面ならBT.2390の曲線で明るさの範囲を収める。
 */
#pragma once

#include <cstdint>
#include <string>

namespace frameplayer {

/** @brief 画像の画素の並び。 */
enum class PixelLayout : std::uint8_t {
    Bgra8,  ///< BGRAの各8bit(縮小画像など)。値は動画の色域・伝達関数のままのRGB。
    Nv12,   ///< YUV 4:2:0の8bit(明るさの面と、縦横半分の色の面(UVの交互))。
    P010,   ///< YUV 4:2:0の10bit(NV12と同じ並びで、各値を16bitの上位10bitに持つ)。
    Yuy2,   ///< YUV 4:2:2の8bit(1行に「Y0 U Y1 V」が並ぶ。DVのデコーダーなどが出す)。
};

/** @brief YUVからRGBへ戻す行列の種類。 */
enum class ColorMatrix : std::uint8_t {
    Bt601,      ///< ITU-R BT.601(SDの動画)。
    Bt709,      ///< ITU-R BT.709(HDの動画)。
    Bt2020,     ///< ITU-R BT.2020の非定輝度(UHD・HDRの動画)。
    Smpte240m,  ///< SMPTE 240M(古いHDの動画)。
    Fcc,        ///< FCC(NTSCの古い規定)。
};

/** @brief YUVの値の範囲。 */
enum class ColorRange : std::uint8_t {
    Limited,  ///< 映像用(8bitなら明るさ16〜235、色16〜240)。
    Full,     ///< 全範囲(8bitなら0〜255)。
};

/** @brief 色域(三原色と白の位置)。 */
enum class ColorPrimaries : std::uint8_t {
    Bt709,      ///< BT.709・sRGB。
    Bt601_525,  ///< BT.601の525本(SMPTE 170M・SMPTE C。北米・日本のSD)。
    Bt601_625,  ///< BT.601の625本(BT.470 BG・EBU。欧州のSD)。
    Bt2020,     ///< BT.2020(UHD・HDR)。
    DisplayP3,  ///< P3の色域でD65の白(SMPTE EG 432-1)。
    DciP3,      ///< P3の色域でDCIの白(SMPTE RP 431-2。映画館)。
};

/** @brief 伝達関数(信号と明るさの関係)。SDRの曲線どうしは表示で区別しないので1つにまとめる。 */
enum class TransferFunction : std::uint8_t {
    Sdr,     ///< SDR(BT.709・sRGB・ガンマ2.2など)。値をそのまま画面へ出す。
    Linear,  ///< リニア。sRGBの曲線を掛けて画面へ出す。
    Pq,      ///< HDRのPQ(SMPTE ST 2084、BT.2100)。
    Hlg,     ///< HDRのHLG(ARIB STD-B67、BT.2100)。
};

/** @brief YUV 4:2:0の色の画素の位置(明るさの画素に対して)。 */
enum class ChromaSiting : std::uint8_t {
    Left,     ///< 横は左の明るさの画素と同じ位置、縦は2行の中間(H.264・HEVCの既定)。
    Center,   ///< 縦横とも中間(JPEG・MPEG-1)。
    TopLeft,  ///< 縦横とも左上の明るさの画素と同じ位置。
};

/** @brief 色の解釈の各項目がどこから来たか(情報の表示に使う)。 */
enum class ColorSource : std::uint8_t {
    Guess,   ///< 動画に指定が無いので、大きさなどから推定した。
    File,    ///< 動画に指定されていた。
    Manual,  ///< 利用者が手動で指定した。
};

/** @brief 1本の動画の色の解釈。 */
struct ColorInfo {
    ColorMatrix matrix = ColorMatrix::Bt709;
    ColorRange range = ColorRange::Limited;
    ColorPrimaries primaries = ColorPrimaries::Bt709;
    TransferFunction transfer = TransferFunction::Sdr;
    ChromaSiting siting = ChromaSiting::Left;
    int bitDepth = 8;            ///< デコードした値のビット数(8または10)。
    float maxContentNits = 0.0f; ///< HDRの最大の明るさ(MaxCLL、無ければマスタリングの最大)。0なら不明。
    ColorSource matrixSource = ColorSource::Guess;
    ColorSource rangeSource = ColorSource::Guess;
    ColorSource primariesSource = ColorSource::Guess;
    ColorSource transferSource = ColorSource::Guess;

    /**
     * @brief HDRの動画かを返す。
     * @return 伝達関数がPQかHLGならtrue。
     */
    bool isHdr() const { return transfer == TransferFunction::Pq || transfer == TransferFunction::Hlg; }

    /**
     * @brief 値をそのまま画面へ出せる(色域・明るさの変換が要らない)かを返す。
     * @return SDRでBT.709の色域ならtrue。
     */
    bool isPassThrough() const { return transfer == TransferFunction::Sdr && primaries == ColorPrimaries::Bt709; }

    /**
     * @brief 描画の結果に影響する項目がすべて同じかを返す(出所は比べない)。
     * @param other 比べる相手。
     * @return 同じならtrue。
     */
    bool sameRendering(const ColorInfo& other) const {
        return matrix == other.matrix && range == other.range && primaries == other.primaries &&
               transfer == other.transfer && siting == other.siting && bitDepth == other.bitDepth &&
               maxContentNits == other.maxContentNits;
    }
};

/** @brief 利用者による色の解釈の手動指定。各項目は負なら「自動」(動画の指定・推定のまま)。 */
struct ColorOverride {
    int matrix = -1;     ///< ColorMatrixの値。負なら自動。
    int range = -1;      ///< ColorRangeの値。負なら自動。
    int primaries = -1;  ///< ColorPrimariesの値。負なら自動。
    int transfer = -1;   ///< TransferFunctionの値。負なら自動。

    /**
     * @brief どれか1つでも手動で指定しているかを返す。
     * @return 指定していればtrue。
     */
    bool any() const { return matrix >= 0 || range >= 0 || primaries >= 0 || transfer >= 0; }

    /**
     * @brief 同じ指定かを返す。
     * @param other 比べる相手。
     * @return 同じならtrue。
     */
    bool operator==(const ColorOverride& other) const {
        return matrix == other.matrix && range == other.range && primaries == other.primaries &&
               transfer == other.transfer;
    }
};

/**
 * @brief 手動の指定を当てはめた色の解釈を返す。
 * @param info 動画の指定・推定による解釈。
 * @param override 手動の指定。
 * @return 指定した項目だけを差し替え、出所をManualにしたもの。
 */
ColorInfo applyOverride(ColorInfo info, const ColorOverride& override);

/**
 * @brief 動画に指定が無い項目の推定値を返す(一般的なプレイヤーと同じ決まり)。
 * @param width 映像の幅。
 * @param height 映像の高さ。
 * @return HD以上(幅1024超か高さ576超)はBT.709、それ未満はBT.601(高さ576なら625本、それ以外は525本)。
 *         範囲は映像用、伝達関数はSDR。出所はすべてGuess。
 */
ColorInfo guessColorInfo(int width, int height);

/**
 * @brief ITU-T H.273の番号(mp4/movのcolrボックスや、H.264/HEVCのVUIと同じ)を色の解釈に当てはめる。
 * @param info 当てはめる先。分かった項目だけを差し替え、出所をFileにする。
 * @param primaries 色域の番号(colour_primaries)。
 * @param transfer 伝達関数の番号(transfer_characteristics)。
 * @param matrix 行列の番号(matrix_coefficients)。
 * @param fullRange 全範囲なら1、映像用なら0、不明なら負。
 */
void applyH273(ColorInfo& info, int primaries, int transfer, int matrix, int fullRange);

/**
 * @brief 色の解釈を、情報の表示用の文字にする。
 * @param info 色の解釈。
 * @return 「BT.709 / 映像用(16-235) / 色域 BT.709 / SDR / 8bit」のような1行。推定・手動の項目には印を付ける。
 */
std::wstring describeColor(const ColorInfo& info);

/**
 * @brief 各項目の名前を返す(メニューと情報の表示に使う)。
 * @param value 項目の値。
 * @return 表示用の名前。
 */
const wchar_t* colorName(ColorMatrix value);
/** @copydoc colorName(ColorMatrix) */
const wchar_t* colorName(ColorRange value);
/** @copydoc colorName(ColorMatrix) */
const wchar_t* colorName(ColorPrimaries value);
/** @copydoc colorName(ColorMatrix) */
const wchar_t* colorName(TransferFunction value);

/**
 * @brief テクスチャから読んだYUVの値(0〜1)をRGB(0〜1)へ戻す行列を求める。
 * @param info 色の解釈(行列・範囲・ビット数を使う)。
 * @param p010 値がP010(10bitの値を16bitの上位に詰めたもの)ならtrue、8bitならfalse。
 * @param out 行優先の3行4列。RGB = out × (Y, Cb, Cr, 1)。
 */
void yuvToRgbMatrix(const ColorInfo& info, bool p010, float out[12]);

/**
 * @brief 色域をBT.709の色域へ変換する行列(リニアな値に掛ける)を求める。
 * @param primaries 元の色域。
 * @param out 行優先の3行3列。
 * @note 白がD65でない色域(DCI-P3)は、Bradford法で白をD65に合わせる。
 */
void gamutToBt709(ColorPrimaries primaries, float out[9]);

/**
 * @brief 主メモリのYUVのコマ(NV12・P010・YUY2)を、主メモリのBGRAの画像にする(縮小画像・確認用)。
 * @param planes NV12・P010は明るさの面(幅×高さ)の後に色の面(幅×高さ/2、UVの交互)が続くデータ。
 *               YUY2は1行に「Y0 U Y1 V」が並ぶデータ。
 * @param width 幅(偶数)。
 * @param height 高さ(偶数)。
 * @param layout 並び(Nv12・P010・Yuy2)。
 * @param info 色の解釈(行列・範囲・色の位置を使う)。
 * @param outWidth 作る画像の幅。widthと同じなら全画素を変換し、小さければ近い画素を選んで縮める。
 * @param outHeight 作る画像の高さ。
 * @param out BGRAの画素(outWidth×outHeight個)の格納先。値は動画の色域・伝達関数のままのRGB。
 */
void convertPlanesToBgra(const std::uint8_t* planes, int width, int height, PixelLayout layout, const ColorInfo& info,
                         int outWidth, int outHeight, std::uint32_t* out);

}  // namespace frameplayer
