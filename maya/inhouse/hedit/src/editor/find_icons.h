/** @file find_icons.h
 * @brief 検索バーのアイコン。VS Codeのアイコン(codicon)に似せた細い線の絵を、QPainterで描く。
 * @details 画像ファイルを同梱せず、hedit.mll単体で使えるようにするため、その場で描く。
 * 色はheditの配色(editor/theme.h)を使い、大きさは拡大率(scaled)に合わせる。
 */
#pragma once
#include <QColor>
#include <QIcon>

namespace hedit {

/** @brief 検索バーで使うアイコンの種類。 */
enum class FindIcon {
    ChevronRight,  ///< 置換欄を開く(閉じているとき)。
    ChevronDown,   ///< 置換欄を閉じる(開いているとき)。
    ArrowUp,       ///< 前の一致へ。
    ArrowDown,     ///< 次の一致へ。
    Selection,     ///< 選択範囲内で検索(三本線)。
    Close,         ///< 閉じる(×)。
    MatchCase,     ///< 大文字小文字を区別(Aa)。
    WholeWord,     ///< 単語単位(下に括弧の付いたab)。
    Regex,         ///< 正規表現(.*)。
    PreserveCase,  ///< 大文字小文字を保つ置換(AB)。
    Replace,       ///< 1件置換。
    ReplaceAll,    ///< すべて置換。
};

/** @brief アイコンを描いて返す。
 * @param icon 種類。
 * @param color 線と文字の色。
 * @param size 1辺のピクセル数(拡大率を掛けた後の値)。
 * @return 描いたアイコン。
 */
QIcon findIcon(FindIcon icon, const QColor& color, int size);

}  // namespace hedit
