/** @file syntax_highlighter.h
 * @brief Python/MELの本文の色分け。
 */
#pragma once
#include "core/script_lexer.h"
#include <QSyntaxHighlighter>

namespace hedit {

/** @brief 字句解析(core/script_lexer.cpp)の結果で色を付ける、表示専用の構文強調。
 * @details Qtは、変更された行から順にhighlightBlock()を呼ぶ。行をまたぐ文字列・コメントの状態は
 * setCurrentBlockState()で行ごとに保存し、次の行はpreviousBlockState()で受け取る。状態が変わると、
 * Qtが次の行も自動で塗り直す。本文を実行・importしない。
 * QSyntaxHighlighterは文書(QTextDocument)の子として作り、文書と一緒に破棄される。
 */
class SyntaxHighlighter : public QSyntaxHighlighter {
public:
    /** @brief 文書に構文強調を取り付ける。
     * @param document 色を付ける文書。この文書が強調を所有する。
     */
    explicit SyntaxHighlighter(QTextDocument* document);

    /** @brief MELとして色分けするかを切り替える。呼んだ後にrehighlight()で全体を塗り直す。
     * @param mel trueならMEL、falseならPython。
     */
    void setMel(bool mel);

protected:
    /** @brief 1行を色分けする。Qtが行ごとに呼ぶ。
     * @param text その行の文字列。
     */
    void highlightBlock(const QString& text) override;

private:
    ScriptLanguage language_ = ScriptLanguage::Python;  ///< 色分けする言語。
};

}  // namespace hedit
