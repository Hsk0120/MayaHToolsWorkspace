/** @file signature_help.cpp
 * @brief 引数のヒントの解析の実装。
 */
#include "core/signature_help.h"
#include "core/script_lexer.h"
#include <QVector>

namespace hedit {
namespace {

/// 呼出しを探すときに読む、カーソルより前の文字数。
constexpr int kLookBehind = 4000;

/** @brief 開いている括弧。 */
struct OpenBracket {
    QChar bracket;        ///< ``(``・``[``・``{``。
    int position = 0;     ///< 括弧の位置。
    int arguments = 0;    ///< 括弧の外の``,``の数。
    QString keyword;      ///< 今の引数の``name=``の名前。
    bool afterComma = true;  ///< 今の引数の始まり(``name=``の判定用)。
    QString lastName;     ///< 今の引数の最初の名前。
};

/** @brief 名前を引数の名前にする(``radius=1.0``・``radius: float``→``radius``、``*args``→``args``)。
 * @param parameter 引数の文字列。
 * @return 名前。
 */
QString parameterName(const QString& parameter) {
    QString name = parameter.trimmed();
    while (name.startsWith('*')) {
        name.remove(0, 1);
    }
    int end = 0;
    while (end < name.size() && isNamePart(name[end])) {
        ++end;
    }
    return name.left(end);
}

}  // namespace

CallContext findCallContext(const QString& before) {
    CallContext context;
    const int base = qMax(0, int(before.size()) - kLookBehind);
    // 行の途中から読み始めないよう、範囲の最初の改行の次から読む。
    int start = base == 0 ? 0 : before.indexOf('\n', base) + 1;
    if (start <= 0 && base > 0) {
        start = base;
    }
    QVector<OpenBracket> stack;
    int state = kLexerNormal;
    int lineStart = start;
    while (lineStart <= before.size()) {
        int lineEnd = before.indexOf('\n', lineStart);
        if (lineEnd < 0) {
            lineEnd = before.size();
        }
        const QString line = before.mid(lineStart, lineEnd - lineStart);
        int endState = kLexerNormal;
        const QList<Token> tokens = tokenizeLine(line, ScriptLanguage::Python, state, &endState);
        for (int t = 0; t < tokens.size(); ++t) {
            const Token& token = tokens[t];
            const QString text = line.mid(token.start, token.length);
            const int position = lineStart + token.start;
            if (token.type == TokenType::Comment) {
                continue;
            }
            if (token.type == TokenType::Operator && (text == "(" || text == "[" || text == "{")) {
                stack.append({text[0], position});
                continue;
            }
            if (token.type == TokenType::Operator && (text == ")" || text == "]" || text == "}")) {
                if (!stack.isEmpty()) {
                    stack.removeLast();
                }
                continue;
            }
            if (stack.isEmpty()) {
                continue;
            }
            OpenBracket& top = stack.last();
            if (token.type == TokenType::Operator && text == ",") {
                ++top.arguments;
                top.keyword.clear();
                top.lastName.clear();
                top.afterComma = true;
                continue;
            }
            if (token.type == TokenType::Operator && text == "=" && !top.lastName.isEmpty()) {
                top.keyword = top.lastName;
            }
            if (top.afterComma && token.type == TokenType::Name) {
                top.lastName = text;
            } else {
                top.lastName.clear();
            }
            top.afterComma = false;
        }
        state = endState;
        if (lineEnd >= before.size()) {
            break;
        }
        lineStart = lineEnd + 1;
    }
    // いちばん内側の ( を探す([ { の中なら、その外側の呼出し)。
    for (int i = stack.size() - 1; i >= 0; --i) {
        if (stack[i].bracket != '(') {
            continue;
        }
        int end = stack[i].position;
        while (end > 0 && (before[end - 1] == ' ' || before[end - 1] == '\t')) {
            --end;
        }
        int nameStart = end;
        while (nameStart > 0 && isNamePart(before[nameStart - 1])) {
            --nameStart;
        }
        const QString name = before.mid(nameStart, end - nameStart);
        if (name.isEmpty() || !isNameStart(name[0]) || isKeyword(name, ScriptLanguage::Python)) {
            return context;  // if ( や (1 + 2) は呼出しではない。
        }
        context.nameEnd = end;
        context.openParen = stack[i].position;
        context.argumentIndex = stack[i].arguments;
        context.keyword = i == stack.size() - 1 ? stack[i].keyword : QString();
        context.attribute = nameStart > 0 && before[nameStart - 1] == '.';
        return context;
    }
    return context;
}

SignatureParts splitSignature(const QString& signature) {
    SignatureParts parts;
    const int open = signature.indexOf('(');
    if (open < 0) {
        return parts;
    }
    int depth = 0;
    QChar quote;
    int close = -1;
    int argumentStart = open + 1;
    for (int i = open; i < signature.size(); ++i) {
        const QChar c = signature[i];
        if (!quote.isNull()) {
            if (c == '\\') {
                ++i;
            } else if (c == quote) {
                quote = QChar();
            }
            continue;
        }
        if (c == '\'' || c == '"') {
            quote = c;
        } else if (c == '(' || c == '[' || c == '{') {
            ++depth;
        } else if (c == ')' || c == ']' || c == '}') {
            if (--depth == 0) {
                close = i;
                break;
            }
        } else if (c == ',' && depth == 1) {
            parts.parameters.append(signature.mid(argumentStart, i - argumentStart).trimmed());
            argumentStart = i + 1;
        }
    }
    if (close < 0) {
        return parts;
    }
    const QString last = signature.mid(argumentStart, close - argumentStart).trimmed();
    if (!last.isEmpty() || !parts.parameters.isEmpty()) {
        parts.parameters.append(last);
    }
    parts.head = signature.left(open + 1);
    parts.tail = signature.mid(close);
    parts.valid = true;
    return parts;
}

void dropBoundParameter(SignatureParts* parts) {
    if (!parts->parameters.isEmpty()) {
        const QString first = parameterName(parts->parameters.first());
        if (first == "self" || first == "cls") {
            parts->parameters.removeFirst();
        }
    }
}

int activeParameterIndex(const QStringList& parameters, int argumentIndex, const QString& keyword) {
    int varArgs = -1;
    int varKeywords = -1;
    int positionalEnd = parameters.size();  // 単独の * または *args の位置(それより後ろは名前でしか渡せない)。
    for (int i = 0; i < parameters.size(); ++i) {
        const QString text = parameters[i].trimmed();
        if (text.startsWith("**")) {
            varKeywords = i;
        } else if (text.startsWith('*')) {
            if (text.size() > 1) {
                varArgs = i;
            }
            positionalEnd = qMin(positionalEnd, i);
        }
    }
    if (!keyword.isEmpty()) {
        for (int i = 0; i < parameters.size(); ++i) {
            if (parameterName(parameters[i]) == keyword && !parameters[i].trimmed().startsWith('*')) {
                return i;
            }
        }
        return varKeywords;
    }
    // 位置引数。単独の / は数えない。
    int index = 0;
    for (int i = 0; i < positionalEnd; ++i) {
        if (parameters[i].trimmed() == "/") {
            continue;
        }
        if (index == argumentIndex) {
            return i;
        }
        ++index;
    }
    return varArgs;
}

}  // namespace hedit
