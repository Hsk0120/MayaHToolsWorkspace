/** @file fuzzy_match.h
 * @brief 補完の候補の絞り込みと並べ替え(VS Codeと同じく、大文字小文字を区別しない・単語の頭からの飛び飛びの一致)。
 * @details ``pcube`` で ``polyCube``、``gat`` で ``getAttr`` が見つかる。1文字目は名前の先頭か単語の頭
 * (``_`` の後・小文字の後の大文字)で一致する必要がある(``ube`` では ``polyCube`` を出さない)。
 * Mayaにも画面にも依存しない。
 */
#pragma once
#include "core/completion_types.h"
#include <QList>
#include <QString>
#include <QStringView>

namespace hedit {

/** @brief 入力した文字列が名前にどれだけよく一致するか。
 * @param pattern 入力途中の名前(空なら全ての名前に一致する)。
 * @param word 候補の名前。
 * @return 一致しなければ-1。一致すれば0以上(大きいほどよい)。前方一致・単語の頭・連続した一致・大文字小文字が
 *         同じ文字ほど高い。空のpatternは0。
 */
int fuzzyScore(QStringView pattern, QStringView word);

/** @brief 候補を、patternとの一致の度合いの順に並べ、一致しないものを除く。
 * @param items 候補。
 * @param pattern 入力途中の名前。
 * @return 一致した候補(よい順。同じ度合いなら名前の順)。
 */
QList<CompletionItem> rankCompletions(const QList<CompletionItem>& items, const QString& pattern);

/** @brief 2つの候補の並び順(rankCompletionsと補完エンジンで同じ順にする)。
 * @param leftScore 左の度合い。
 * @param left 左の名前。
 * @param rightScore 右の度合い。
 * @param right 右の名前。
 * @return 左を先に並べるならtrue。度合いの高い順、同じなら大文字小文字を区別しない名前の順。
 */
bool rankedBefore(int leftScore, const QString& left, int rightScore, const QString& right);

}  // namespace hedit
