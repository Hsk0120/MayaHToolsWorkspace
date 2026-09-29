/** @file script_lexer.cpp
 * @brief 字句解析の実装。
 * @details 1文字ずつ見て、次の字句の種類を先頭の文字で決める(名前・数値・文字列・コメント・記号)。
 * 正規表現を使わないので、長い行でも行の長さに比例した時間で終わる。
 */
#include "core/script_lexer.h"
#include <QSet>
#include <QStringList>

namespace hedit {
namespace {

/// 2・3文字でひとまとまりの記号(長いものから調べる)。
const QStringList& multiCharacterOperators() {
    static const QStringList operators = {
        "**=", "//=", ">>=", "<<=", "...",
        "==", "!=", "<=", ">=", "->", ":=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "@=",
        "**", "//", "<<", ">>", "&&", "||", "++", "--",
    };
    return operators;
}

/** @brief 位置iから始まる記号の長さ。 @param line 行。 @param i 位置。 @return 1〜3。 */
int operatorLength(const QString& line, int i) {
    for (const QString& op : multiCharacterOperators()) {
        if (QStringView(line).mid(i, op.size()) == op) {
            return op.size();
        }
    }
    return 1;
}

/** @brief 数値の終わりを探す。 @param line 行。 @param i 数値の先頭。 @return 数値の直後の位置。 */
int scanNumber(const QString& line, int i) {
    int end = i;
    while (end < line.size()) {
        const QChar c = line[end];
        if (c.isLetterOrNumber() || c == '_' || c == '.') {
            ++end;
        } else if ((c == '+' || c == '-') && end > i && (line[end - 1] == 'e' || line[end - 1] == 'E')
                   && !QStringView(line).mid(i, 2).startsWith(QLatin1String("0x"), Qt::CaseInsensitive)) {
            ++end;  // 1e+5 のような指数の符号。
        } else {
            break;
        }
    }
    return end;
}

/** @brief 1行の引用符の文字列の終わりを探す(行末で閉じていなければ行末まで)。
 * @param line 行。
 * @param quoteStart 開きの引用符の位置。
 * @param raw ``\``を特別扱いしないならtrue。
 * @return 文字列の直後の位置。
 */
int scanSingleLineString(const QString& line, int quoteStart, bool raw) {
    const QChar quote = line[quoteStart];
    int i = quoteStart + 1;
    while (i < line.size()) {
        if (line[i] == '\\' && !raw) {
            i += 2;  // エスケープされた次の文字を飛ばす。
            continue;
        }
        if (line[i] == quote) {
            return i + 1;
        }
        ++i;
    }
    return line.size();
}

/** @brief 三重引用符の文字列の終わりを探す。
 * @param line 行。
 * @param from 探し始める位置(文字列の中身の先頭)。
 * @param quote 引用符(``'``か``"``)。
 * @param raw ``\``を特別扱いしないならtrue。
 * @return 閉じの三重引用符の直後の位置。この行で閉じなければ-1。
 */
int scanTripleStringEnd(const QString& line, int from, QChar quote, bool raw) {
    int i = from;
    while (i < line.size()) {
        if (line[i] == '\\' && !raw) {
            i += 2;
            continue;
        }
        if (line[i] == quote && i + 2 < line.size() && line[i + 1] == quote && line[i + 2] == quote) {
            return i + 3;
        }
        ++i;
    }
    return -1;
}

/** @brief 状態から、三重引用符の引用符と生文字列かを取り出す。
 * @param state 状態。
 * @param quote 引用符を入れる。
 * @param raw 生文字列ならtrueを入れる。
 * @return 三重引用符の状態ならtrue。
 */
bool tripleStringState(int state, QChar* quote, bool* raw) {
    switch (state) {
    case kPythonTripleSingle:
        *quote = '\'';
        *raw = false;
        return true;
    case kPythonTripleDouble:
        *quote = '"';
        *raw = false;
        return true;
    case kPythonRawTripleSingle:
        *quote = '\'';
        *raw = true;
        return true;
    case kPythonRawTripleDouble:
        *quote = '"';
        *raw = true;
        return true;
    default:
        return false;
    }
}

/** @brief 三重引用符と生文字列かから、状態の値を決める。 @param quote 引用符。 @param raw 生文字列か。 @return 状態。 */
int tripleState(QChar quote, bool raw) {
    if (quote == '\'') {
        return raw ? kPythonRawTripleSingle : kPythonTripleSingle;
    }
    return raw ? kPythonRawTripleDouble : kPythonTripleDouble;
}

/** @brief Pythonの文字列の接頭辞(r・b・u・fとその組合せ)か。 @param prefix 名前の部分。 @return 接頭辞ならtrue。 */
bool isStringPrefix(const QString& prefix) {
    static const QSet<QString> prefixes = {"r", "u", "b", "f", "br", "rb", "fr", "rf"};
    return prefixes.contains(prefix.toLower());
}

/** @brief Pythonの1行を字句に分ける。 @param line 行。 @param state 開始の状態。 @param endState 終わりの状態。 @return 字句。 */
QList<Token> tokenizePython(const QString& line, int state, int* endState) {
    QList<Token> tokens;
    int i = 0;
    // 前の行から三重引用符の文字列が続いている場合は、まずその終わりを探す。
    QChar quote;
    bool raw = false;
    if (tripleStringState(state, &quote, &raw)) {
        const int end = scanTripleStringEnd(line, 0, quote, raw);
        if (end < 0) {
            tokens.append({TokenType::String, 0, int(line.size())});
            *endState = state;
            return tokens;
        }
        tokens.append({TokenType::String, 0, end});
        i = end;
    }
    *endState = kLexerNormal;

    while (i < line.size()) {
        const QChar c = line[i];
        if (c.isSpace()) {
            ++i;
            continue;
        }
        if (c == '#') {
            tokens.append({TokenType::Comment, i, int(line.size()) - i});
            break;
        }
        // 名前。直後に引用符が続けば、文字列の接頭辞(r"..."など)。
        if (isNameStart(c)) {
            int end = i + 1;
            while (end < line.size() && isNamePart(line[end])) {
                ++end;
            }
            const QString word = line.mid(i, end - i);
            if (end < line.size() && (line[end] == '\'' || line[end] == '"') && isStringPrefix(word)) {
                const bool rawPrefix = word.contains('r', Qt::CaseInsensitive);
                const QChar q = line[end];
                const bool triple = end + 2 < line.size() && line[end + 1] == q && line[end + 2] == q;
                if (triple) {
                    const int close = scanTripleStringEnd(line, end + 3, q, rawPrefix);
                    if (close < 0) {
                        tokens.append({TokenType::String, i, int(line.size()) - i});
                        *endState = tripleState(q, rawPrefix);
                        return tokens;
                    }
                    tokens.append({TokenType::String, i, close - i});
                    i = close;
                } else {
                    const int close = scanSingleLineString(line, end, rawPrefix);
                    tokens.append({TokenType::String, i, close - i});
                    i = close;
                }
                continue;
            }
            tokens.append({TokenType::Name, i, end - i});
            i = end;
            continue;
        }
        if (c.isDigit() || (c == '.' && i + 1 < line.size() && line[i + 1].isDigit())) {
            const int end = scanNumber(line, i);
            tokens.append({TokenType::Number, i, end - i});
            i = end;
            continue;
        }
        if (c == '\'' || c == '"') {
            const bool triple = i + 2 < line.size() && line[i + 1] == c && line[i + 2] == c;
            if (triple) {
                const int close = scanTripleStringEnd(line, i + 3, c, false);
                if (close < 0) {
                    tokens.append({TokenType::String, i, int(line.size()) - i});
                    *endState = tripleState(c, false);
                    return tokens;
                }
                tokens.append({TokenType::String, i, close - i});
                i = close;
            } else {
                const int close = scanSingleLineString(line, i, false);
                tokens.append({TokenType::String, i, close - i});
                i = close;
            }
            continue;
        }
        const int length = operatorLength(line, i);
        tokens.append({TokenType::Operator, i, length});
        i += length;
    }
    return tokens;
}

/** @brief MELの1行を字句に分ける。 @param line 行。 @param state 開始の状態。 @param endState 終わりの状態。 @return 字句。 */
QList<Token> tokenizeMel(const QString& line, int state, int* endState) {
    QList<Token> tokens;
    int i = 0;
    *endState = kLexerNormal;
    // 前の行から /* */ のコメントが続いている場合。
    if (state == kMelBlockComment) {
        const int close = line.indexOf("*/");
        if (close < 0) {
            tokens.append({TokenType::Comment, 0, int(line.size())});
            *endState = kMelBlockComment;
            return tokens;
        }
        tokens.append({TokenType::Comment, 0, close + 2});
        i = close + 2;
    }
    while (i < line.size()) {
        const QChar c = line[i];
        if (c.isSpace()) {
            ++i;
            continue;
        }
        if (c == '/' && i + 1 < line.size() && line[i + 1] == '/') {
            tokens.append({TokenType::Comment, i, int(line.size()) - i});
            break;
        }
        if (c == '/' && i + 1 < line.size() && line[i + 1] == '*') {
            const int close = line.indexOf("*/", i + 2);
            if (close < 0) {
                tokens.append({TokenType::Comment, i, int(line.size()) - i});
                *endState = kMelBlockComment;
                return tokens;
            }
            tokens.append({TokenType::Comment, i, close + 2 - i});
            i = close + 2;
            continue;
        }
        if (c == '$' && i + 1 < line.size() && isNameStart(line[i + 1])) {
            int end = i + 2;
            while (end < line.size() && isNamePart(line[end])) {
                ++end;
            }
            tokens.append({TokenType::Variable, i, end - i});
            i = end;
            continue;
        }
        if (isNameStart(c)) {
            int end = i + 1;
            while (end < line.size() && isNamePart(line[end])) {
                ++end;
            }
            tokens.append({TokenType::Name, i, end - i});
            i = end;
            continue;
        }
        if (c.isDigit() || (c == '.' && i + 1 < line.size() && line[i + 1].isDigit())) {
            const int end = scanNumber(line, i);
            tokens.append({TokenType::Number, i, end - i});
            i = end;
            continue;
        }
        if (c == '"') {
            const int close = scanSingleLineString(line, i, false);
            tokens.append({TokenType::String, i, close - i});
            i = close;
            continue;
        }
        const int length = operatorLength(line, i);
        tokens.append({TokenType::Operator, i, length});
        i += length;
    }
    return tokens;
}

}  // namespace

bool isNameStart(QChar character) {
    return character.isLetter() || character == '_';
}

bool isNamePart(QChar character) {
    return character.isLetterOrNumber() || character == '_' || character.isMark();
}

QList<Token> tokenizeLine(const QString& line, ScriptLanguage language, int state, int* endState) {
    int ignored = 0;
    if (!endState) {
        endState = &ignored;
    }
    if (state < 0) {
        state = kLexerNormal;  // QSyntaxHighlighterは、まだ状態が無い行に-1を渡す。
    }
    if (language == ScriptLanguage::Mel) {
        return tokenizeMel(line, state == kMelBlockComment ? state : kLexerNormal, endState);
    }
    return tokenizePython(line, state == kMelBlockComment ? kLexerNormal : state, endState);
}

bool isKeyword(const QString& word, ScriptLanguage language) {
    static const QSet<QString> python = {
        "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else",
        "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
        "or", "pass", "raise", "return", "try", "while", "with", "yield",
    };
    static const QSet<QString> mel = {
        "proc", "global", "return", "if", "else", "for", "in", "while", "do", "switch", "case", "default",
        "break", "continue", "string", "int", "float", "vector", "matrix",
    };
    return language == ScriptLanguage::Mel ? mel.contains(word) : python.contains(word);
}

bool isConstant(const QString& word, ScriptLanguage language) {
    static const QSet<QString> python = {"True", "False", "None", "self"};
    static const QSet<QString> mel = {"true", "false", "on", "off", "yes", "no"};
    return language == ScriptLanguage::Mel ? mel.contains(word) : python.contains(word);
}

}  // namespace hedit
