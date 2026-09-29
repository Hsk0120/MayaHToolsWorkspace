/** @file syntax_highlighter.h
 * @brief Python/MELの本文の簡易な色分け。
 */
#pragma once
#include <QSyntaxHighlighter>

namespace hedit {

/** @brief 行ごとに正規表現で色を付ける、表示専用の構文強調。
 * @details 構文解析器ではないため、複数行の文字列などは正確には色分けしない。本文を実行・importしない。
 * QSyntaxHighlighterは文書(QTextDocument)の子として作り、文書と一緒に破棄される。
 */
class SyntaxHighlighter : public QSyntaxHighlighter {
public:
    /** @brief 文書に構文強調を取り付ける。
     * @param document 色を付ける文書。この文書が強調を所有する。
     */
    explicit SyntaxHighlighter(QTextDocument* document);

    /** @brief MELとして色分けするかを切り替える。呼んだ後にrehighlight()で全体を塗り直す。
     * @param mel trueならコメントを``//``、falseなら``#``として扱う。
     */
    void setMel(bool mel);

protected:
    /** @brief 1行を色分けする。Qtが行ごとに呼ぶ。
     * @param text その行の文字列。
     */
    void highlightBlock(const QString& text) override;

private:
    /** @brief 引用符の外にある最初のコメント記号の位置を探す。
     * @param text 行の文字列。
     * @return コメントの開始位置。コメントが無ければ-1。
     */
    int commentStart(const QString& text) const;

    bool mel_ = false;  ///< MELとして色分けするか。
};

}  // namespace hedit
