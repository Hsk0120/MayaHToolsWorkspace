/** @file syntax_highlighter.cpp
 * @brief SyntaxHighlighterの実装。
 */
#include "editor/syntax_highlighter.h"
#include <QJsonObject>
#include "editor/code_navigation.h"
#include <QTextBlock>
#include "editor/theme.h"
#include <QColor>

namespace mce {
namespace {

/** @brief 字句の種類ごとの色(1回だけ作り、行ごと・字句ごとに色の文字列を読み直さない)。
 * @note 共有するのは値の型の色(QColor)だけにし、書式(QTextCharFormat)はsetFormatの中でQtに作らせる
 * (中身を共有するQtの型を、mayaCodeEditor.mllの中のstaticな値として全ての文書から参照させない)。
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
    QVector<Token> tokens;
    if (language_ == ScriptLanguage::Python) {
        PythonLexState state;
        const auto* previous = dynamic_cast<const PythonBlockData*>(currentBlock().previous().userData());
        if (previous) state = previous->state;
        tokens = tokenizePythonEditing(QStringView(text), &state);
        const auto* old = dynamic_cast<const PythonBlockData*>(currentBlockUserData());
        if (!state.frames.isEmpty()) {
            endState = old && old->state == state ? currentBlockState() : nextPythonState_++;
        }
        auto* data = new PythonBlockData;
        data->state = state;
        setCurrentBlockUserData(data);
    } else {
        tokens = tokenizeLine(text, language_, previousBlockState(), &endState);
        setCurrentBlockUserData(nullptr);
    }
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
    if (language_ == ScriptLanguage::Python) {
        for (const auto& entry : semantic_.value(currentBlock().blockNumber())) {
            const auto token = entry.toObject();
            const QString type = token.value("type").toString();
            QColor color;
            if (type == "class" || type == "type" || type == "typeParameter") color = QColor("#4ec9b0");
            else if (type == "function" || type == "method") color = QColor("#dcdcaa");
            else if (type == "parameter" || type == "variable" || type == "property") color = QColor("#9cdcfe");
            else if (type == "namespace") color = QColor("#4ec9b0");
            if (color.isValid()) setFormat(token.value("column").toInt(), token.value("length").toInt(), color);
        }
    }
}

void SyntaxHighlighter::setSemanticTokens(const QJsonArray& tokens) {
    semantic_.clear();
    for (const auto& token : tokens) semantic_[token.toObject().value("line").toInt()].append(token);
    rehighlight();
}

}  // namespace mce
