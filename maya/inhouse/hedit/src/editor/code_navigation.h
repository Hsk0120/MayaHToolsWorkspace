/** @file code_navigation.h
 * @brief コード欄の文書(QTextDocument)の上で、対応する括弧・同じ名前の位置・選択範囲の拡大を求める。
 * @details どれも字句解析(core/script_lexer.cpp)で文字列とコメントを区別する。行をまたぐ文字列の状態は、
 * 構文強調が行ごとに保存している状態(QTextBlock::userState)を使う。画面の部品には依存しないので、
 * QTextDocumentだけでテストできる。
 */
#pragma once
#include "core/script_lexer.h"
#include <QChar>
#include <QHash>
#include <QList>
#include <QString>
#include <QVector>

class QTextBlock;
class QTextDocument;

namespace hedit {

/** @brief 1行の字句を返す(前の行の状態を引き継ぐ)。
 * @param block 行。
 * @param language 言語。
 * @return 字句の一覧。
 */
QVector<Token> blockTokens(const QTextBlock& block, ScriptLanguage language);

/** @brief 位置が文字列かコメントの中か。
 * @param document 文書。
 * @param language 言語。
 * @param position 位置(この位置の直前の文字で判断する)。
 * @return 文字列・コメントの途中ならtrue。字句の終わり(閉じ引用符の直後)はfalse。
 */
bool isInsideStringOrComment(const QTextDocument* document, ScriptLanguage language, int position);

/** @brief 括弧の対応を探すときの、行ごとの括弧の位置の控え。
 * @details 対応する括弧は、カーソルが動くたびに最大で数千行をさかのぼって探す。本文が変わっていなければ(同じ文書の版の
 * 間は)、一度字句解析した行の括弧をここから使う。本文か言語が変われば、次に使うときに捨てて作り直す。
 * 控えはコード欄が値として持つ(Qtの文書の行に付ける情報は使わない)。
 */
struct BracketCache {
    /** @brief 括弧1つ。 */
    struct Bracket {
        int position = 0;  ///< 文書の中の位置。
        QChar bracket;     ///< 括弧の文字(``()[]{}``のどれか)。
    };
    int revision = -1;                                 ///< 控えを作ったときの文書の版(QTextDocument::revision)。
    ScriptLanguage language = ScriptLanguage::Python;  ///< 控えを作ったときの言語。
    QHash<int, QVector<Bracket>> blocks;               ///< 行番号(0始まり) → その行の括弧(行の中の順)。
};

/** @brief カーソルの隣の括弧と、対応する括弧の位置を求める。
 * @param document 文書。
 * @param language 言語。
 * @param position カーソルの位置。直後の文字、無ければ直前の文字の括弧を使う。
 * @param first 隣の括弧の位置を入れる。
 * @param second 対応する括弧の位置を入れる。
 * @param cache 行ごとの括弧の控え。nullptrなら控えを使わない(毎回字句解析する)。
 * @return 対応する括弧が見つかればtrue。文字列・コメントの中の括弧は対象外。
 */
bool findMatchingBracket(const QTextDocument* document, ScriptLanguage language, int position, int* first,
                         int* second, BracketCache* cache = nullptr);

/** @brief 名前と同じ名前の字句の位置を返す(文字列・コメントの中は除く)。
 * @param document 文書。
 * @param language 言語。
 * @param name 名前(MELの``$var``も可)。
 * @param limit 返す最大の件数。
 * @return 各位置(先頭の位置)。文書が大きすぎる(50万文字超)ときは空。
 */
QList<int> nameOccurrences(const QTextDocument* document, ScriptLanguage language, const QString& name, int limit);

/** @brief 選択範囲を、次に大きい意味のまとまりへ広げる(VS CodeのShift+Alt+→)。
 * @param document 文書。
 * @param language 言語。
 * @param start 今の選択の先頭。
 * @param end 今の選択の終わり。
 * @param newStart 広げた先頭を入れる。
 * @param newEnd 広げた終わりを入れる。
 * @return 広げられたらtrue。順番は 名前(``a.b.c``)→ 文字列の中身 → 文字列 → 括弧の中身 → 括弧を含む →
 * 行の中身 → 行 → インデントのブロック → 見出しを含むブロック → 文書全体。
 */
bool expandedSelection(const QTextDocument* document, ScriptLanguage language, int start, int end, int* newStart,
                       int* newEnd);

}  // namespace hedit
