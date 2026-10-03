/**
 * @file Ui.h
 * @brief 操作部の描画に使う色・寸法と、GDIの描画部品。
 */
#pragma once

#include <windows.h>

#include <utility>
#include <vector>

namespace frameplayer::ui {

// 色はWindows 11標準の「メディア プレーヤー」に合わせる(同じ動画を再生した画面から測った値)。
inline constexpr COLORREF kBackground = RGB(0, 0, 0);       ///< 映像の周りの背景。
inline constexpr COLORREF kSurface = RGB(20, 20, 20);       ///< タイトルバー・タイムスライダー・レンジスライダーの地(#141414)。
inline constexpr COLORREF kAccent = RGB(255, 130, 50);      ///< 強調色(キャッシュの帯・音量・比較中のボタン。#FF8232)。
inline constexpr COLORREF kText = RGB(255, 255, 255);       ///< 文字と、移動・再生ボタンの記号。
inline constexpr COLORREF kVolumeTrack = RGB(69, 69, 69);   ///< 音量の三角形の地(#454545。メディア プレーヤーのつまみの色)。
inline constexpr COLORREF kControlFace = RGB(38, 38, 38);    ///< 文字のボタンと数字の欄の地。
inline constexpr COLORREF kControlBorder = RGB(51, 51, 51);  ///< 文字のボタンと数字の欄の枠。
inline constexpr COLORREF kDisabled = RGB(106, 106, 106);    ///< 使えない記号・入力できない数字(#6A6A6A)。
inline constexpr COLORREF kRuler = RGB(32, 32, 32);          ///< タイムスライダーの目盛りとレンジスライダーのバーの地。
inline constexpr COLORREF kTick = RGB(84, 84, 84);           ///< 細かい目盛り。
inline constexpr COLORREF kMajorTick = RGB(110, 110, 110);   ///< 数字の付く目盛り。
inline constexpr COLORREF kRulerText = RGB(197, 197, 197);   ///< 目盛りの数字。
inline constexpr COLORREF kCurrentColumn = RGB(70, 70, 70);  ///< 現在のフレームの区画。
inline constexpr COLORREF kLabelBox = RGB(52, 52, 52);       ///< 現在のフレームの番号の箱。
inline constexpr COLORREF kRangeSelected = RGB(58, 58, 58);  ///< レンジスライダーの再生範囲。
inline constexpr COLORREF kHandle = RGB(148, 148, 148);      ///< レンジスライダーのつまみ。
inline constexpr COLORREF kRulerOutside = RGB(16, 16, 16);   ///< 目盛りとバーのうち、動画の外の部分の地。
inline constexpr COLORREF kRangeSelectedOutside = RGB(44, 44, 44);  ///< 再生範囲のうち、動画の外の部分。
inline constexpr COLORREF kControlHover = RGB(54, 54, 54);   ///< マウスが乗っているボタン・欄の地。
inline constexpr COLORREF kControlBorderHover = RGB(84, 84, 84);  ///< マウスが乗っているボタン・欄の枠。
inline constexpr COLORREF kAccentHover = RGB(255, 157, 94);  ///< マウスが乗っている強調色のボタンの地。
inline constexpr COLORREF kSecondaryText = RGB(176, 176, 176);  ///< 控えめな文字(全体範囲の欄・ラベル)。
inline constexpr int kTextPoints = 9;   ///< 操作部の文字(欄・ボタン・ラベル・fps)の大きさ(ポイント)。
inline constexpr int kSmallPoints = 8;  ///< 小さい文字(目盛りの数字・現在のフレームの箱・音量)の大きさ(ポイント)。

/** @brief 移動・再生ボタンの記号。 */
enum class TransportIcon { Start, Previous, Play, Pause, Next, End };

/**
 * @brief 96DPI基準の長さを、ウィンドウのDPIに合わせた長さへ変換する。
 * @param value 96DPIでの長さ(ピクセル)。
 * @param dpi ウィンドウのDPI。
 * @return 変換後の長さ。
 */
inline int scaled(int value, int dpi) {
    return MulDiv(value, dpi, 96);
}

/**
 * @brief 矩形を単色で塗る。
 * @param dc 描画先。
 * @param rect 塗る範囲。
 * @param color 色。
 * @note ブラシを作らず、描画先に備わっている色を変えられるブラシ(DC_BRUSH)で塗る。
 *       目盛りのように1回の描画で何百回も呼ぶので、ブラシの作成と破棄を省く。
 */
void fill(HDC dc, const RECT& rect, COLORREF color);

/**
 * @brief 矩形の1ピクセルの枠を描く。
 * @param dc 描画先。
 * @param rect 枠の範囲。
 * @param color 色。
 */
void frame(HDC dc, const RECT& rect, COLORREF color);

/**
 * @brief 指定サイズの文字の書体を作る(Windows 11ならSegoe UI Variable、無ければSegoe UI)。
 * @param points 文字の大きさ(ポイント)。
 * @param dpi ウィンドウのDPI。
 * @return 作成した書体。呼び出し元がDeleteObjectで解放する(FontCacheを使えば自動)。
 */
HFONT createFont(int points, int dpi);

/**
 * @brief タイトルバーをダークにし、操作部と同じ色にする(Windows 11のアプリと同じ見た目)。
 * @param hwnd 対象のウィンドウ。
 * @note Windows 10では色の指定が効かず、ダークの指定だけが効く(失敗しても表示に支障はない)。
 */
void applyDarkTitleBar(HWND hwnd);

/**
 * @brief 角を丸めた文字のボタンを描く。
 * @param dc 描画先(文字の書体は選んでおく)。
 * @param rect ボタンの範囲。
 * @param face 地の色。
 * @param border 枠の色。
 * @param ink 文字の色。
 * @param text 文字。
 * @param radius 角の丸みの大きさ(ピクセル)。
 */
void drawRoundButton(HDC dc, const RECT& rect, COLORREF face, COLORREF border, COLORREF ink, const wchar_t* text,
                     int radius);

/**
 * @brief 移動・再生ボタンの記号を描く。
 * @param dc 描画先。
 * @param box ボタンの範囲(記号はその中央に描く)。
 * @param icon 記号の種類。
 * @param ink 記号の色。
 */
void drawTransportIcon(HDC dc, const RECT& box, TransportIcon icon, COLORREF ink);

/**
 * @brief 作った書体を大きさごとに覚えて使い回す。DPIが変わったら作り直す。
 */
class FontCache {
public:
    FontCache() = default;
    /** @brief 覚えている書体をすべて解放する。 */
    ~FontCache() { clear(); }
    FontCache(const FontCache&) = delete;
    FontCache& operator=(const FontCache&) = delete;

    /**
     * @brief 書体を返す。初めての大きさなら作って覚える。
     * @param points 文字の大きさ(ポイント)。
     * @param dpi ウィンドウのDPI。
     * @return 書体。このクラスが持つので、呼び出し元は解放しない。
     */
    HFONT get(int points, int dpi);

    /** @brief 覚えている書体をすべて解放する。 */
    void clear();

private:
    std::vector<std::pair<int, HFONT>> fonts_;  ///< 作った書体(大きさ, 書体)。
    int dpi_ = 0;                               ///< fonts_を作ったときのDPI。
};

/**
 * @brief 作り置きの画像(変わらない部分を一度だけ描いておき、描き直しのたびに写して使う)。
 */
class Layer {
public:
    Layer() = default;
    /** @brief 画像を解放する。 */
    ~Layer();
    Layer(const Layer&) = delete;
    Layer& operator=(const Layer&) = delete;

    /**
     * @brief 指定の大きさの画像を用意し、描くための描画先を返す(大きさが同じなら作り直さない)。
     * @param compatible 互換の描画先(色の形式を合わせる)。
     * @param width 幅。
     * @param height 高さ。
     * @return 画像の描画先。左上が(0, 0)。
     */
    HDC prepare(HDC compatible, int width, int height);

    /**
     * @brief 画像の一部を描画先へ写す。
     * @param target 写す先。
     * @param x 写す先の左端。
     * @param y 写す先の上端。
     * @param width 幅。
     * @param height 高さ。
     * @param sourceX 画像の中の左端。
     * @param sourceY 画像の中の上端。
     */
    void blit(HDC target, int x, int y, int width, int height, int sourceX, int sourceY) const;

private:
    HDC dc_ = nullptr;
    HBITMAP bitmap_ = nullptr;
    HGDIOBJ oldBitmap_ = nullptr;
    int width_ = 0;
    int height_ = 0;
};

/**
 * @brief ちらつかずに描くための裏の画像。描き直しのたびに作らず、必要な大きさが入る間は使い回す。
 */
class BackBuffer {
public:
    BackBuffer() = default;
    /** @brief 裏の画像を解放する。 */
    ~BackBuffer();
    BackBuffer(const BackBuffer&) = delete;
    BackBuffer& operator=(const BackBuffer&) = delete;

    /**
     * @brief 描き直す範囲用の描画先を用意する。座標はクライアント座標のまま使えるよう原点をずらしてある。
     * @param screen 画面の描画先(BeginPaintの結果)。
     * @param area 描き直す範囲(クライアント座標)。
     * @return 裏の画像の描画先。present()まで使う。
     */
    HDC begin(HDC screen, const RECT& area);

    /**
     * @brief 裏の画像を画面へ一度に写す。
     * @param screen 画面の描画先。
     */
    void present(HDC screen);

private:
    HDC dc_ = nullptr;
    HBITMAP bitmap_ = nullptr;
    HGDIOBJ oldBitmap_ = nullptr;
    int width_ = 0;    ///< 今の裏の画像の幅。
    int height_ = 0;   ///< 今の裏の画像の高さ。
    RECT area_{};      ///< begin()で受け取った描き直す範囲。
};

}  // namespace frameplayer::ui
