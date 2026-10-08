/** @file syntax_highlighter.cpp
 * @brief SyntaxHighlighterの実装。
 */
#include "editor/syntax_highlighter.h"
#include "editor/theme.h"
#include <QColor>

namespace hedit {
namespace {

/** @brief 字句の種類ごとの色(1回だけ作り、行ごと・字句ごとに色の文字列を読み直さない)。
 * @note 共有するのは値の型の色(QColor)だけにし、書式(QTextCharFormat)はsetFormatの中でQtに作らせる
 * (中身を共有するQtの型を、hedit.mllの中のstaticな値として全ての文書から参照させない)。
 */
struct Colors {
    QColor string{theme::kSyntaxString};          ///< 文字列。
    QColor comment{theme::kSyntaxComment};        ///< コメント。
    QColor number{theme::kSyntaxNumber};          ///< 数値。
    QColor identifier{theme::kSyntaxIdentifier};  ///< 名前・MELの変数。
    QColor keyword{theme::kSyntaxKeyword};        ///< 予約語。
    QColor constant{theme::kSyntaxConstant};      ///< True・None・self。
    QColor className{theme::kSyntaxClassName};    ///< classの後のクラス名。
    QColor function{theme::kSyntaxFunction};      ///< 関数の名前。
};

/** @brief 共有の色を返す。 @return 色の一式。 */
const Colors& colors() {
    static const Colors instance;
    return instance;
}

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
    const auto tokens = tokenizeLine(text, language_, previousBlockState(), &endState);
    setCurrentBlockState(endState);

    const Colors& format = colors();
    QStringView previousWord;  // 直前の名前(classの後のクラス名を見分けるため)。textの一部を指す。
    for (const Token& token : tokens) {
        const QColor* color = nullptr;
        switch (token.type) {
        case TokenType::String:
            color = &format.string;
            break;
        case TokenType::Comment:
            color = &format.comment;
            break;
        case TokenType::Number:
            color = &format.number;
            break;
        case TokenType::Variable:
            color = &format.identifier;
            break;
        case TokenType::Name: {
            const QStringView word = QStringView(text).mid(token.start, token.length);
            if (isKeyword(word, language_)) {
                color = &format.keyword;
            } else if (isConstant(word, language_)) {
                color = &format.constant;
            } else if (previousWord == QLatin1String("class") && language_ == ScriptLanguage::Python) {
                color = &format.className;
            } else if (followedByParenthesis(text, token.start + token.length)) {
                color = &format.function;
            } else {
                color = &format.identifier;
            }
            previousWord = word;
            break;
        }
        case TokenType::Operator:
            break;  // 記号は色を付けない(既定の文字色)。
        }
        if (color) {
            setFormat(token.start, token.length, *color);
        }
        if (token.type != TokenType::Name) {
            previousWord = QStringView();
        }
    }
}

}  // namespace hedit
