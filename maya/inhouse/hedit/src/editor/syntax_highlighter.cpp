/** @file syntax_highlighter.cpp
 * @brief SyntaxHighlighterの実装。
 */
#include "editor/syntax_highlighter.h"
#include "editor/theme.h"
#include <QColor>

namespace hedit {
namespace {

/** @brief 名前の直後(空白を除く)が``(``か(関数呼出し・関数定義の名前か)。
 * @param text 行。
 * @param end 名前の直後の位置。
 * @return ``(``が続けばtrue。
 */
bool followedByParenthesis(const QString& text, int end) {
    while (end < text.size() && text[end].isSpace()) {
        ++end;
    }
    return end < text.size() && text[end] == '(';
}

}  // namespace

SyntaxHighlighter::SyntaxHighlighter(QTextDocument* document) : QSyntaxHighlighter(document) {}

void SyntaxHighlighter::setMel(bool mel) {
    language_ = mel ? ScriptLanguage::Mel : ScriptLanguage::Python;
}

void SyntaxHighlighter::highlightBlock(const QString& text) {
    int endState = kLexerNormal;
    const QList<Token> tokens = tokenizeLine(text, language_, previousBlockState(), &endState);
    setCurrentBlockState(endState);

    QString previousWord;  // 直前の名前(classの後のクラス名を見分けるため)。
    for (const Token& token : tokens) {
        QColor color;
        switch (token.type) {
        case TokenType::String:
            color = QColor(theme::kSyntaxString);
            break;
        case TokenType::Comment:
            color = QColor(theme::kSyntaxComment);
            break;
        case TokenType::Number:
            color = QColor(theme::kSyntaxNumber);
            break;
        case TokenType::Variable:
            color = QColor(theme::kSyntaxIdentifier);
            break;
        case TokenType::Name: {
            const QString word = text.mid(token.start, token.length);
            if (isKeyword(word, language_)) {
                color = QColor(theme::kSyntaxKeyword);
            } else if (isConstant(word, language_)) {
                color = QColor(theme::kSyntaxConstant);
            } else if (previousWord == "class" && language_ == ScriptLanguage::Python) {
                color = QColor(theme::kSyntaxClassName);
            } else if (followedByParenthesis(text, token.start + token.length)) {
                color = QColor(theme::kSyntaxFunction);
            } else {
                color = QColor(theme::kSyntaxIdentifier);
            }
            previousWord = word;
            break;
        }
        case TokenType::Operator:
            break;  // 記号は色を付けない(既定の文字色)。
        }
        if (color.isValid()) {
            setFormat(token.start, token.length, color);
        }
        if (token.type != TokenType::Name) {
            previousWord.clear();
        }
    }
}

}  // namespace hedit
