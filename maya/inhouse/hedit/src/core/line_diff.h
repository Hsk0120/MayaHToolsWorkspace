/** @file line_diff.h
 * @brief 保存した内容と今の本文の、行単位の差分。
 * @details 行番号の横の変更の印(追加・変更・削除)と、「保存前との差分」の表示が使う。
 * 共通の先頭と末尾を除いた残りを、最長共通部分列(LCS)で比べる。残りが大きすぎるときは、まとめて
 * 1つの変更として扱う(画面を止めないため)。Mayaにも画面にも依存しない。
 */
#pragma once
#include <QList>
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 変更のまとまり(hunk)。行番号は0始まり。 */
struct LineChange {
    int beforeStart = 0;  ///< 保存した内容での開始行。
    int beforeCount = 0;  ///< 保存した内容で置き換わった行数(0なら追加)。
    int afterStart = 0;   ///< 今の本文での開始行。
    int afterCount = 0;   ///< 今の本文での行数(0なら削除。afterStartの行の上で削除された)。

    /** @brief 種類。 @return ``added``・``deleted``・``modified``。 */
    QString kind() const { return beforeCount == 0 ? "added" : afterCount == 0 ? "deleted" : "modified"; }
};

/** @brief 2つの行の並びの差分を求める。
 * @param before 保存した内容の行。
 * @param after 今の本文の行。
 * @return 変更のまとまり(行の順)。同じなら空。
 */
QList<LineChange> diffLines(const QStringList& before, const QStringList& after);

}  // namespace hedit
