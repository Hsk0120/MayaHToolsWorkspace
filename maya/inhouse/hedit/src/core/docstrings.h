/** @file docstrings.h
 * @brief Pythonの文字列リテラルの値と、docstringの整形(``inspect.cleandoc``とほぼ同じ)。
 * @details マウスを重ねたときの説明(ホバー)に使う。まだ読み込んでいない``.py``のdocstringは、
 * 実行せずに字句解析で取り出すため、リテラルの引用符・接頭辞・エスケープをここで外す。
 * Mayaにも画面にも依存しない。
 */
#pragma once
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 1つの文字列リテラル(``r"""..."""``など)の値を返す。
 * @param literal 字句解析で得た文字列の字句(接頭辞と引用符を含む)。書きかけで閉じていなくてもよい。
 * @return 値。``\n``などのエスケープは、raw文字列(接頭辞``r``)でなければ元の文字に戻す。
 */
QString stringLiteralValue(const QString& literal);

/** @brief 隣り合う文字列リテラル(``"a" "b"``)をつなげた値を返す。
 * @param literals 字句の一覧。
 * @return 値をつなげたもの。
 */
QString stringLiteralsValue(const QStringList& literals);

/** @brief docstringの字下げを整える(Pythonの``inspect.cleandoc``とほぼ同じ)。
 * @param text docstringの値。
 * @return 1行目の前の空白と、2行目以降に共通の字下げ、前後の空行を除いたもの。タブは8桁で空白にする。
 * cleandocと違い、各行の行末の空白も除く。
 */
QString cleanDocstring(const QString& text);

}  // namespace hedit
