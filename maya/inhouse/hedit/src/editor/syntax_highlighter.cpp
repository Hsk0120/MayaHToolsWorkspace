/** @file syntax_highlighter.cpp
 * @brief SyntaxHighlighterの実装。
 */
#include "editor/syntax_highlighter.h"
#include "editor/theme.h"
#include <QColor>
#include <QList>
#include <QRegularExpression>

namespace hedit {
namespace {

/** @brief 色分けの規則。一致した範囲をcolorで塗る。 */
struct HighlightRule {
    QRegularExpression pattern;  ///< 一致させる正規表現。
    QColor color;                ///< 塗る色。
};

/** @brief 色分けの規則を返す。後の規則ほど優先される(同じ範囲を上から塗り直す)。
 * @return 規則の一覧。初回だけ作り、以後は同じものを使う(正規表現の作成は重いため)。
 */
const QList<HighlightRule>& highlightRules() {
    static const QList<HighlightRule> rules = {
        {QRegularExpression("\\b[A-Za-z_][A-Za-z_0-9]*\\b"), QColor(theme::kSyntaxIdentifier)},
        {QRegularExpression("\\b[0-9]+(?:\\.[0-9]+)?\\b"), QColor(theme::kSyntaxNumber)},
        {QRegularExpression("\\b[A-Za-z_][A-Za-z_0-9]*(?=\\s*\\()"), QColor(theme::kSyntaxFunction)},
        {QRegularExpression("\\b(?:def|class|import|from|as|return|if|else|elif|for|while|in|try|except|finally|"
                            "with|yield|raise|pass|and|or|not|lambda|async|await)\\b"),
         QColor(theme::kSyntaxKeyword)},
        {QRegularExpression("\\b(?:True|False|None|self)\\b"), QColor(theme::kSyntaxConstant)},
    };
    return rules;
}

/// classの後のクラス名(1番目のキャプチャー)。
const QRegularExpression& classNamePattern() {
    static const QRegularExpression pattern("\\bclass\\s+([A-Za-z_][A-Za-z_0-9]*)");
    return pattern;
}

/// 1行の中の文字列("..."または'...')。
const QRegularExpression& stringPattern() {
    static const QRegularExpression pattern("(?:\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*')");
    return pattern;
}

}  // namespace

SyntaxHighlighter::SyntaxHighlighter(QTextDocument* document) : QSyntaxHighlighter(document) {}

void SyntaxHighlighter::setMel(bool mel) {
    mel_ = mel;
}

void SyntaxHighlighter::highlightBlock(const QString& text) {
    // 1. 名前・数値・関数・予約語などを順に塗る。
    for (const HighlightRule& rule : highlightRules()) {
        auto matches = rule.pattern.globalMatch(text);
        while (matches.hasNext()) {
            const auto match = matches.next();
            setFormat(match.capturedStart(), match.capturedLength(), rule.color);
        }
    }
    // 2. classの後のクラス名を塗る。
    auto classes = classNamePattern().globalMatch(text);
    while (classes.hasNext()) {
        const auto match = classes.next();
        setFormat(match.capturedStart(1), match.capturedLength(1), QColor(theme::kSyntaxClassName));
    }
    // 3. 文字列は中の単語より優先するため、最後の方で塗り直す。
    auto strings = stringPattern().globalMatch(text);
    while (strings.hasNext()) {
        const auto match = strings.next();
        setFormat(match.capturedStart(), match.capturedLength(), QColor(theme::kSyntaxString));
    }
    // 4. コメントは行末まで全てを上書きする。
    const int comment = commentStart(text);
    if (comment >= 0) {
        setFormat(comment, text.size() - comment, QColor(theme::kSyntaxComment));
    }
}

int SyntaxHighlighter::commentStart(const QString& text) const {
    QChar openQuote;  // 文字列の中なら、その開始の引用符。外ならnull。
    bool escaped = false;
    for (int i = 0; i < text.size(); ++i) {
        const QChar character = text[i];
        if (escaped) {
            escaped = false;
            continue;
        }
        if (character == '\\') {
            escaped = true;
            continue;
        }
        if (!openQuote.isNull()) {
            if (character == openQuote) {
                openQuote = QChar();
            }
            continue;
        }
        if (character == '\'' || character == '"') {
            openQuote = character;
            continue;
        }
        const bool pythonComment = !mel_ && character == '#';
        const bool melComment = mel_ && character == '/' && i + 1 < text.size() && text[i + 1] == '/';
        if (pythonComment || melComment) {
            return i;
        }
    }
    return -1;
}

}  // namespace hedit
