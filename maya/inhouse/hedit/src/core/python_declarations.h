/** @file python_declarations.h
 * @brief Pythonの本文から、補完に使う宣言(def・class・import・代入)を取り出す。実行はしない。
 * @details 以前はPythonのast.parseで行っていた処理(補完1回あたり、5,000行で約100ms)をC++にしたもの。
 * 字句解析(core/script_lexer.cpp)で行をまとめ、インデントでブロックを判断する。
 * astと違い、構文エラーがあっても読める部分の宣言は取り出す。
 *
 * 取り出す宣言(Pythonの``ast``で読んでいたときと同じ):
 * - モジュール直下とクラスの中の ``def``/``async def``(引数の名前)・``class``(中身)
 * - ``import a.b``・``import a.b as c``・``from X import Y``(相対importを含む)
 * - ``名前 = ...``・``名前: 型 = ...``
 * - ``if TYPE_CHECKING:``(``typing.TYPE_CHECKING``を含む)の中
 * 関数の中・for/with/tryなどの中の宣言は取り出さない。
 */
#pragma once
#include "core/symbols.h"
#include <QString>

namespace hedit {

/** @brief 宣言を取り出した結果。 */
struct DeclarationResult {
    SymbolTable symbols;   ///< 取り出した宣言。
    bool complete = true;  ///< 本文の最後で括弧や三重引用符が閉じていればtrue(書きかけでない)。
};

/** @brief Pythonの本文から宣言を取り出す。
 * @param source 本文。
 * @param moduleName 相対import(``from . import x``)を解決するためのモジュール名。
 * パッケージの``__init__.py``は``pkg.__init__``のように渡す。本文がファイルでなければ空。
 * @return 宣言と、本文が書きかけでないか。
 */
DeclarationResult extractPythonDeclarations(const QString& source, const QString& moduleName = QString());

}  // namespace hedit
