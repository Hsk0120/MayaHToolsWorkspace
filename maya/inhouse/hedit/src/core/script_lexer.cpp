/** @file script_lexer.cpp
 * @brief 字句解析の実装。
 * @details 1文字ずつ見て、次の字句の種類を先頭の文字で決める(名前・数値・文字列・コメント・記号)。
 * 正規表現を使わないので、長い行でも行の長さに比例した時間で終わる。
 * 構文強調は表示する行ごとに呼ぶため、字句ごとの文字列の確保(QString)をしない。行はQStringViewで受け取り、
 * 文字列の接頭辞・記号・予約語も、文字を直接比べて調べる。
 */
#include "core/script_lexer.h"
#include <cstddef>

namespace hedit {

QString languageName(ScriptLanguage language) {
    return language == ScriptLanguage::Mel ? QStringLiteral("mel") : QStringLiteral("python");
}

ScriptLanguage languageFromName(const QString& name) {
    return name == QLatin1String("mel") ? ScriptLanguage::Mel : ScriptLanguage::Python;
}

ScriptLanguage languageForPath(const QString& path) {
    return path.endsWith(QLatin1String(".mel"), Qt::CaseInsensitive) ? ScriptLanguage::Mel : ScriptLanguage::Python;
}
namespace {

/** @brief 位置iの文字を返す。行の外なら空の文字(どの記号とも一致しない)。 @param line 行。 @param i 位置。 @return 文字。 */
QChar charAt(QStringView line, qsizetype i) {
    return i < line.size() ? line[i] : QChar();
}

/** @brief 位置iから始まる記号の長さ。
 * @param line 行。
 * @param i 位置。
 * @return 1〜3。2・3文字でひとまとまりの記号(``**=``・``//=``・``>>=``・``<<=``・``...``・``==``・``!=``・``<=``・``>=``・
 * ``->``・``:=``・``+=``・``-=``・``*=``・``/=``・``%=``・``&=``・``|=``・``^=``・``@=``・``**``・``//``・``<<``・``>>``・
 * ``&&``・``||``・``++``・``--``)は、長いものを優先してその長さを返す。
 * @details 以前は28個の記号の文字列と順に比べていた。先頭の文字で分岐し、続く1・2文字だけを見る。
 */
int operatorLength(QStringView line, qsizetype i) {
    const QChar next = charAt(line, i + 1);
    const QChar after = charAt(line, i + 2);
    switch (line[i].unicode()) {
    case '*':
    case '/':
    case '>':
    case '<':
        // ** // >> << と、その後ろの = (**= など)、または1文字 + = (*= など)。
        if (next == line[i]) {
            return after == '=' ? 3 : 2;
        }
        return next == '=' ? 2 : 1;
    case '.':
        return next == '.' && after == '.' ? 3 : 1;
    case '=':
    case '!':
    case ':':
    case '%':
    case '^':
    case '@':
        return next == '=' ? 2 : 1;
    case '-':
        return next == '=' || next == '>' || next == '-' ? 2 : 1;
    case '+':
    case '&':
    case '|':
        // += &= |= と、MELの ++ && ||。
        return next == '=' || next == line[i] ? 2 : 1;
    default:
        return 1;
    }
}

/** @brief 数値の終わりを探す。 @param line 行。 @param i 数値の先頭。 @return 数値の直後の位置。 */
qsizetype scanNumber(QStringView line, qsizetype i) {
    qsizetype end = i;
    while (end < line.size()) {
        const QChar c = line[end];
        if (c.isLetterOrNumber() || c == '_' || c == '.') {
            ++end;
        } else if ((c == '+' || c == '-') && end > i && (line[end - 1] == 'e' || line[end - 1] == 'E')
                   && !line.mid(i, 2).startsWith(QLatin1String("0x"), Qt::CaseInsensitive)) {
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
 * @return 文字列の直後の位置。
 * @note ``\``の次の文字は、生文字列(``r"..."``)でも閉じの引用符として扱わない(Pythonと同じ)。
 */
qsizetype scanSingleLineString(QStringView line, qsizetype quoteStart) {
    const QChar quote = line[quoteStart];
    qsizetype i = quoteStart + 1;
    while (i < line.size()) {
        if (line[i] == '\\') {
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
 * @return 閉じの三重引用符の直後の位置。この行で閉じなければ-1。
 * @note scanSingleLineStringと同じく、生文字列でも``\``の次の文字では閉じない。
 */
qsizetype scanTripleStringEnd(QStringView line, qsizetype from, QChar quote) {
    qsizetype i = from;
    while (i < line.size()) {
        if (line[i] == '\\') {
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

/** @brief 状態から、三重引用符の引用符を取り出す。
 * @param state 状態。
 * @param quote 引用符を入れる。
 * @return 三重引用符の状態ならtrue。
 */
bool tripleStringState(int state, QChar* quote) {
    switch (state) {
    case kPythonTripleSingle:
    case kPythonRawTripleSingle:
        *quote = '\'';
        return true;
    case kPythonTripleDouble:
    case kPythonRawTripleDouble:
        *quote = '"';
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

/** @brief ASCIIの英大文字を小文字にする(それ以外はそのまま)。 @param c 文字。 @return 文字コード。 */
char16_t asciiLower(QChar c) {
    const char16_t u = c.unicode();
    return u >= 'A' && u <= 'Z' ? char16_t(u + ('a' - 'A')) : u;
}

/** @brief Pythonの文字列の接頭辞(r・u・b・fとその組合せ。大文字も可)か。
 * @param prefix 名前の部分。
 * @return ``r``・``u``・``b``・``f``・``br``・``rb``・``fr``・``rf``(大文字小文字を問わない)ならtrue。
 */
bool isStringPrefix(QStringView prefix) {
    if (prefix.size() == 1) {
        const char16_t c = asciiLower(prefix[0]);
        return c == 'r' || c == 'u' || c == 'b' || c == 'f';
    }
    if (prefix.size() == 2) {
        const char16_t a = asciiLower(prefix[0]);
        const char16_t b = asciiLower(prefix[1]);
        return (a == 'r' && (b == 'b' || b == 'f')) || ((a == 'b' || a == 'f') && b == 'r');
    }
    return false;
}

/** @brief 接頭辞に``r``(生文字列)を含むか。 @param prefix isStringPrefixで確かめた接頭辞。 @return 含めばtrue。 */
bool hasRawPrefix(QStringView prefix) {
    for (const QChar c : prefix) {
        if (asciiLower(c) == 'r') {
            return true;
        }
    }
    return false;
}

/** @brief Pythonの1行を字句に分ける。
 * @param line 行。
 * @param state 開始の状態。
 * @param endState 終わりの状態を入れる。
 * @param tokens 字句を追加する配列(空で渡す)。
 */
void tokenizePython(QStringView line, int state, int* endState, QVector<Token>& tokens) {
    const int size = int(line.size());
    int i = 0;
    // 前の行から三重引用符の文字列が続いている場合は、まずその終わりを探す。
    QChar quote;
    if (tripleStringState(state, &quote)) {
        const int end = int(scanTripleStringEnd(line, 0, quote));
        if (end < 0) {
            tokens.append({TokenType::String, 0, size});
            *endState = state;
            return;
        }
        tokens.append({TokenType::String, 0, end});
        i = end;
    }
    *endState = kLexerNormal;

    while (i < size) {
        const QChar c = line[i];
        if (c.isSpace()) {
            ++i;
            continue;
        }
        if (c == '#') {
            tokens.append({TokenType::Comment, i, size - i});
            break;
        }
        // 名前。直後に引用符が続けば、文字列の接頭辞(r"..."など)。接頭辞は2文字までなので、長い名前は調べない。
        if (isNameStart(c)) {
            int end = i + 1;
            while (end < size && isNamePart(line[end])) {
                ++end;
            }
            const QStringView word = line.mid(i, end - i);
            if (end < size && end - i <= 2 && (line[end] == '\'' || line[end] == '"') && isStringPrefix(word)) {
                const bool rawPrefix = hasRawPrefix(word);
                const QChar q = line[end];
                const bool triple = end + 2 < size && line[end + 1] == q && line[end + 2] == q;
                if (triple) {
                    const int close = int(scanTripleStringEnd(line, end + 3, q));
                    if (close < 0) {
                        tokens.append({TokenType::String, i, size - i});
                        *endState = tripleState(q, rawPrefix);
                        return;
                    }
                    tokens.append({TokenType::String, i, close - i});
                    i = close;
                } else {
                    const int close = int(scanSingleLineString(line, end));
                    tokens.append({TokenType::String, i, close - i});
                    i = close;
                }
                continue;
            }
            tokens.append({TokenType::Name, i, end - i});
            i = end;
            continue;
        }
        if (c.isDigit() || (c == '.' && i + 1 < size && line[i + 1].isDigit())) {
            const int end = int(scanNumber(line, i));
            tokens.append({TokenType::Number, i, end - i});
            i = end;
            continue;
        }
        if (c == '\'' || c == '"') {
            const bool triple = i + 2 < size && line[i + 1] == c && line[i + 2] == c;
            if (triple) {
                const int close = int(scanTripleStringEnd(line, i + 3, c));
                if (close < 0) {
                    tokens.append({TokenType::String, i, size - i});
                    *endState = tripleState(c, false);
                    return;
                }
                tokens.append({TokenType::String, i, close - i});
                i = close;
            } else {
                const int close = int(scanSingleLineString(line, i));
                tokens.append({TokenType::String, i, close - i});
                i = close;
            }
            continue;
        }
        const int length = operatorLength(line, i);
        tokens.append({TokenType::Operator, i, length});
        i += length;
    }
}

/** @brief MELの1行を字句に分ける。
 * @param line 行。
 * @param state 開始の状態。
 * @param endState 終わりの状態を入れる。
 * @param tokens 字句を追加する配列(空で渡す)。
 */
void tokenizeMel(QStringView line, int state, int* endState, QVector<Token>& tokens) {
    const int size = int(line.size());
    int i = 0;
    *endState = kLexerNormal;
    // 前の行から /* */ のコメントが続いている場合。
    if (state == kMelBlockComment) {
        const int close = int(line.indexOf(QLatin1String("*/")));
        if (close < 0) {
            tokens.append({TokenType::Comment, 0, size});
            *endState = kMelBlockComment;
            return;
        }
        tokens.append({TokenType::Comment, 0, close + 2});
        i = close + 2;
    }
    while (i < size) {
        const QChar c = line[i];
        if (c.isSpace()) {
            ++i;
            continue;
        }
        if (c == '/' && i + 1 < size && line[i + 1] == '/') {
            tokens.append({TokenType::Comment, i, size - i});
            break;
        }
        if (c == '/' && i + 1 < size && line[i + 1] == '*') {
            const int close = int(line.indexOf(QLatin1String("*/"), i + 2));
            if (close < 0) {
                tokens.append({TokenType::Comment, i, size - i});
                *endState = kMelBlockComment;
                return;
            }
            tokens.append({TokenType::Comment, i, close + 2 - i});
            i = close + 2;
            continue;
        }
        if (c == '$' && i + 1 < size && isNameStart(line[i + 1])) {
            int end = i + 2;
            while (end < size && isNamePart(line[end])) {
                ++end;
            }
            tokens.append({TokenType::Variable, i, end - i});
            i = end;
            continue;
        }
        if (isNameStart(c)) {
            int end = i + 1;
            while (end < size && isNamePart(line[end])) {
                ++end;
            }
            tokens.append({TokenType::Name, i, end - i});
            i = end;
            continue;
        }
        if (c.isDigit() || (c == '.' && i + 1 < size && line[i + 1].isDigit())) {
            const int end = int(scanNumber(line, i));
            tokens.append({TokenType::Number, i, end - i});
            i = end;
            continue;
        }
        if (c == '"') {
            const int close = int(scanSingleLineString(line, i));
            tokens.append({TokenType::String, i, close - i});
            i = close;
            continue;
        }
        const int length = operatorLength(line, i);
        tokens.append({TokenType::Operator, i, length});
        i += length;
    }
}

/** @brief 名前が一覧のどれかと一致するか。 @param word 名前。 @param words 一覧。 @param count 一覧の数。 @return 一致すればtrue。 */
bool matchesAny(QStringView word, const QLatin1String* words, int count) {
    for (int i = 0; i < count; ++i) {
        if (word == words[i]) {
            return true;
        }
    }
    return false;
}

/// Pythonの予約語(True・False・NoneはisConstantで扱う)。
const QLatin1String kPythonKeywords[] = {
    QLatin1String("and"),     QLatin1String("as"),       QLatin1String("assert"), QLatin1String("async"),
    QLatin1String("await"),   QLatin1String("break"),    QLatin1String("class"),  QLatin1String("continue"),
    QLatin1String("def"),     QLatin1String("del"),      QLatin1String("elif"),   QLatin1String("else"),
    QLatin1String("except"),  QLatin1String("finally"),  QLatin1String("for"),    QLatin1String("from"),
    QLatin1String("global"),  QLatin1String("if"),       QLatin1String("import"), QLatin1String("in"),
    QLatin1String("is"),      QLatin1String("lambda"),   QLatin1String("nonlocal"), QLatin1String("not"),
    QLatin1String("or"),      QLatin1String("pass"),     QLatin1String("raise"),  QLatin1String("return"),
    QLatin1String("try"),     QLatin1String("while"),    QLatin1String("with"),   QLatin1String("yield"),
};

/// MELの予約語。
const QLatin1String kMelKeywords[] = {
    QLatin1String("proc"),  QLatin1String("global"),   QLatin1String("return"),  QLatin1String("if"),
    QLatin1String("else"),  QLatin1String("for"),      QLatin1String("in"),      QLatin1String("while"),
    QLatin1String("do"),    QLatin1String("switch"),   QLatin1String("case"),    QLatin1String("default"),
    QLatin1String("break"), QLatin1String("continue"), QLatin1String("string"),  QLatin1String("int"),
    QLatin1String("float"), QLatin1String("vector"),   QLatin1String("matrix"),
};

/// Pythonの定数の名前。
const QLatin1String kPythonConstants[] = {
    QLatin1String("True"), QLatin1String("False"), QLatin1String("None"), QLatin1String("self"),
};

/// MELの定数の名前。
const QLatin1String kMelConstants[] = {
    QLatin1String("true"), QLatin1String("false"), QLatin1String("on"),
    QLatin1String("off"),  QLatin1String("yes"),   QLatin1String("no"),
};

/** @brief 配列の要素数。 @return 要素数。 */
template <typename T, std::size_t N>
constexpr int countOf(const T (&)[N]) {
    return int(N);
}

}  // namespace

bool isNameStart(QChar character) {
    return character.isLetter() || character == '_';
}

bool isNamePart(QChar character) {
    return character.isLetterOrNumber() || character == '_' || character.isMark();
}

void tokenizeLineInto(QStringView line, ScriptLanguage language, int state, int* endState, QVector<Token>* tokens) {
    tokens->clear();
    int ignored = 0;
    if (!endState) {
        endState = &ignored;
    }
    if (state < 0) {
        state = kLexerNormal;  // QSyntaxHighlighterは、まだ状態が無い行に-1を渡す。
    }
    if (language == ScriptLanguage::Mel) {
        tokenizeMel(line, state == kMelBlockComment ? state : kLexerNormal, endState, *tokens);
    } else {
        tokenizePython(line, state == kMelBlockComment ? kLexerNormal : state, endState, *tokens);
    }
}

QVector<Token> tokenizeLine(QStringView line, ScriptLanguage language, int state, int* endState) {
    QVector<Token> tokens;
    if (!line.isEmpty()) {
        tokens.reserve(16);  // 1行の字句はたいてい16個以下。確保を1回で済ませる。
    }
    tokenizeLineInto(line, language, state, endState, &tokens);
    return tokens;
}

QVector<Token> tokenizeLine(const QString& line, ScriptLanguage language, int state, int* endState) {
    return tokenizeLine(QStringView(line), language, state, endState);
}

bool isKeyword(QStringView word, ScriptLanguage language) {
    if (word.isEmpty() || word[0] < 'a' || word[0] > 'z') {
        return false;  // 予約語はどれも英小文字で始まる。
    }
    return language == ScriptLanguage::Mel ? matchesAny(word, kMelKeywords, countOf(kMelKeywords))
                                           : matchesAny(word, kPythonKeywords, countOf(kPythonKeywords));
}

bool isKeyword(const QString& word, ScriptLanguage language) {
    return isKeyword(QStringView(word), language);
}

bool isConstant(QStringView word, ScriptLanguage language) {
    return language == ScriptLanguage::Mel ? matchesAny(word, kMelConstants, countOf(kMelConstants))
                                           : matchesAny(word, kPythonConstants, countOf(kPythonConstants));
}

bool isConstant(const QString& word, ScriptLanguage language) {
    return isConstant(QStringView(word), language);
}

}  // namespace hedit
