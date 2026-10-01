/** @file python_literal.h
 * @brief 文字列を、Pythonの文字列リテラル(``'...'``)にする。
 * @details C++からPythonのコードを組み立てるとき(同梱のPythonの登録・hedit.bridgeの関数の呼出し)に、
 * 本文などの文字列を安全に埋め込むために使う。エスケープの書き方はこの1か所だけにまとめる。
 * MELの文字列はplugin/mel.hのmelQuote()を使う(言語が違うので別)。Mayaにも画面にも依存しない。
 */
#pragma once
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 文字列を、Pythonの文字列リテラルにする。
 * @param text 埋め込む文字列(引用符・改行・バックスラッシュを含み得る)。
 * @return ``'...'``の形。``\``・``'``・改行・タブ・その他の制御文字だけをエスケープし、日本語などはそのまま入れる。
 */
QString pythonStringLiteral(const QString& text);

/** @brief 文字列の一覧を、Pythonのリストのリテラル(``['a', 'b']``)にする。
 * @param items 文字列の一覧。
 * @return リストのリテラル。
 */
QString pythonStringListLiteral(const QStringList& items);

}  // namespace hedit
