/** @file code_outline.h
 * @brief 本文の構成(クラス・関数・変数の一覧と行の範囲)と、インデントによる折りたたみの範囲を求める。
 * @details 記号へ移動(Ctrl+Shift+O)・アウトライン・見出しの固定表示(スクロールしても関数の見出しが上に残る)・
 * 定義へ移動(F12)・折りたたみが共通で使う。字句解析(core/script_lexer.cpp)で文字列とコメントを除いて読み、
 * 実行・importはしない。Mayaにも画面にも依存しない。
 */
#pragma once
#include "core/script_lexer.h"
#include <QList>
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 構成の1項目。 */
struct OutlineEntry {
    QString name;       ///< 名前。
    QString kind;       ///< ``class``・``function``・``method``・``variable``・``proc``(MEL)。
    int line = 0;       ///< 宣言の行(0始まり)。
    int endLine = 0;    ///< 中身の最後の行(0始まり。変数は宣言の行と同じ)。
    int column = 0;     ///< 名前の行の中の位置(0始まり)。
    int parent = -1;    ///< 親(クラス・関数)の項目の位置。トップレベルなら-1。
    int depth = 0;      ///< 入れ子の深さ(トップレベルは0)。
    QString detail;     ///< 一覧に出す補足(関数の見出し``def build(self, radius=1.0)``など)。
};

/** @brief 本文の構成を、上から順の一覧で返す。
 * @param text 本文。
 * @param language 言語。Pythonは``class``・``def``・``async def``とクラス直下・トップレベルの代入、
 * MELは``proc``・``global proc``を読む。
 * @return 項目の一覧(行の順)。親子関係はOutlineEntry::parentで表す。
 */
QList<OutlineEntry> buildOutline(const QString& text, ScriptLanguage language);

/** @brief ``Class.method``のような位置をたどって項目を探す。
 * @param outline buildOutlineの結果。
 * @param path 名前の並び(``[ChainBuilder, build]``)。
 * @return 項目の位置。見つからなければ-1。
 */
int findOutlinePath(const QList<OutlineEntry>& outline, const QStringList& path);

/** @brief 行を含む、いちばん内側のクラス・関数の項目を返す。
 * @param outline buildOutlineの結果。
 * @param line 行(0始まり)。
 * @return 項目の位置。どこにも含まれなければ-1。
 */
int enclosingOutlineEntry(const QList<OutlineEntry>& outline, int line);

/** @brief 折りたたみの範囲(VS Codeと同じく、インデントで決める)。 */
struct FoldRange {
    int start = 0;  ///< 見出しの行(0始まり)。この行は表示したまま残る。
    int end = 0;    ///< 畳む最後の行(0始まり)。
};

/** @brief インデントから折りたたみの範囲を求める。
 * @param lines 本文の行。
 * @return 見出しの行の後に、より深い行が続く範囲の一覧(見出しの行の順)。空行は範囲に含めるが、
 * 範囲の最後の空行は含めない。
 */
QList<FoldRange> indentationFoldRanges(const QStringList& lines);

/** @brief 行頭のインデントの幅(タブは次の4の倍数まで進める)。 @param line 行。 @return 幅。 */
int lineIndentWidth(const QString& line);

/** @brief 関数の中の変数・引数・for・with・exceptの名前が定義された行を、カーソルより前から探す。
 * @param text 本文。
 * @param name 名前。
 * @param beforeLine この行(0始まり)より前を、近い順に探す。
 * @param column 見つかった行の中での名前の位置を入れる(0始まり)。nullptrなら入れない。
 * @return 行(0始まり)。見つからなければ-1。
 */
int localDefinitionLine(const QString& text, const QString& name, int beforeLine, int* column = nullptr);

}  // namespace hedit
