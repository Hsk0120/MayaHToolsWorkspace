/** @file code_outline.cpp
 * @brief 本文の構成と折りたたみの範囲の実装。
 * @details Pythonは1行ずつ字句に分け、「文の始まりの行」(前の行から文字列・括弧が続いていない行)だけを見る。
 * クラス・関数の範囲は、同じかより浅いインデントの文が現れた所で閉じる(スタックで1回の走査で求める)。
 * 見出しの固定表示が入力のたびに呼ぶため、行・字句ごとの文字列(QString)を作らず、QStringViewで比べる。
 */
#include "core/code_outline.h"
#include <QPair>
#include <QRegularExpression>
#include <QSet>
#include <QVector>
#include <algorithm>

namespace hedit {
namespace {

/** @brief 開き括弧なら+1、閉じ括弧なら-1。 @param c 1文字の記号。 @return 括弧の深さの変化。 */
int bracketDelta(QChar c) {
    if (c == '(' || c == '[' || c == '{') {
        return 1;
    }
    if (c == ')' || c == ']' || c == '}') {
        return -1;
    }
    return 0;
}

/** @brief 記号の字句の括弧の深さの変化。 @param line 行。 @param token 記号の字句。 @return +1・-1・0。 */
int bracketDelta(QStringView line, const Token& token) {
    return token.length == 1 ? bracketDelta(line[token.start]) : 0;
}

/** @brief 空白(QChar::isSpace)だけの行か。 @param line 行。 @return 空行ならtrue。 */
bool isBlank(QStringView line) {
    for (const QChar c : line) {
        if (!c.isSpace()) {
            return false;
        }
    }
    return true;
}

/// 項目の種類の文字列。項目ごとに文字列を確保しないよう、共有の定数を代入する(QStringは暗黙の共有)。
const QString& kindClass() {
    static const QString value = QStringLiteral("class");
    return value;
}

/** @brief 種類``function``。 @return 共有の定数。 */
const QString& kindFunction() {
    static const QString value = QStringLiteral("function");
    return value;
}

/** @brief 種類``method``。 @return 共有の定数。 */
const QString& kindMethod() {
    static const QString value = QStringLiteral("method");
    return value;
}

/** @brief 種類``variable``。 @return 共有の定数。 */
const QString& kindVariable() {
    static const QString value = QStringLiteral("variable");
    return value;
}

/** @brief 種類``proc``(MEL)。 @return 共有の定数。 */
const QString& kindProc() {
    static const QString value = QStringLiteral("proc");
    return value;
}

/** @brief 開いているクラス・関数(範囲の終わりがまだ決まっていない項目)。 */
struct OpenEntry {
    int indent = 0;  ///< 見出しの行のインデント。
    int index = 0;   ///< 項目の位置(折りたたみでは、結果の配列の中の位置)。
};

/** @brief Pythonの本文の構成を読む。 @param text 本文。 @return 項目の一覧。 */
QList<OutlineEntry> pythonOutline(QStringView text) {
    QList<OutlineEntry> outline;
    QVector<OpenEntry> open;            // 外側から順。
    QSet<QPair<int, QString>> variables;  // 追加済みの変数(親の項目の位置・名前)。同じ場所の同じ名前は最初だけ出す。
    QVector<Token> tokens;              // 行ごとに使い回す字句の配列。
    int state = kLexerNormal;
    int depth = 0;
    int lastNonBlank = -1;
    // 今のインデントで閉じるクラス・関数の範囲を、直前の空でない行までに決める。
    auto closeTo = [&outline, &open, &lastNonBlank](int indent) {
        while (!open.isEmpty() && open.last().indent >= indent) {
            OutlineEntry& entry = outline[open.last().index];
            entry.endLine = qMax(entry.line, lastNonBlank);
            open.removeLast();
        }
    };
    forEachLine(text, [&](int i, QStringView line) {
        int endState = kLexerNormal;
        tokenizeLineInto(line, ScriptLanguage::Python, state, &endState, &tokens);
        const bool statementStart = state == kLexerNormal && depth == 0;
        // コメントを除いた字句の数。コメントは常に行の最後の字句なので、数を1つ減らすだけでよい。
        int count = int(tokens.size());
        if (count > 0 && tokens[count - 1].type == TokenType::Comment) {
            --count;
        }
        auto word = [&line, &tokens, count](int index) {
            return index < count ? line.mid(tokens[index].start, tokens[index].length) : QStringView();
        };
        if (statementStart && count > 0) {
            const int indent = lineIndentWidth(line);
            closeTo(indent);
            int nameIndex = -1;
            const QString* kind = nullptr;
            const QStringView first = word(0);
            if (first == QLatin1String("class")) {
                nameIndex = 1;
                kind = &kindClass();
            } else if (first == QLatin1String("def")) {
                nameIndex = 1;
                kind = &kindFunction();
            } else if (first == QLatin1String("async") && word(1) == QLatin1String("def")) {
                nameIndex = 2;
                kind = &kindFunction();
            }
            const int parent = open.isEmpty() ? -1 : open.last().index;
            if (nameIndex > 0 && nameIndex < count && tokens[nameIndex].type == TokenType::Name) {
                OutlineEntry entry;
                entry.name = word(nameIndex).toString();
                const bool method = kind == &kindFunction() && parent >= 0 && outline[parent].kind == kindClass();
                entry.kind = method ? kindMethod() : *kind;
                entry.line = i;
                entry.endLine = i;
                entry.column = tokens[nameIndex].start;
                entry.parent = parent;
                entry.depth = int(open.size());
                QStringView header = line.trimmed();
                if (header.endsWith(QLatin1Char(':'))) {
                    header.chop(1);
                }
                entry.detail = header.toString();
                outline.append(entry);
                open.append({indent, int(outline.size()) - 1});
            } else if (tokens[0].type == TokenType::Name && !isKeyword(first, ScriptLanguage::Python) && count >= 2
                       && tokens[1].type == TokenType::Operator
                       && (word(1) == QLatin1String("=") || word(1) == QLatin1String(":"))
                       && (parent < 0 || outline[parent].kind == kindClass())) {
                // トップレベルとクラス直下の代入(x = 1・x: int = 1)。同じ場所の同じ名前は最初だけ。
                const QString name = first.toString();
                if (!variables.contains(qMakePair(parent, name))) {
                    variables.insert(qMakePair(parent, name));
                    OutlineEntry entry;
                    entry.name = name;
                    entry.kind = kindVariable();
                    entry.line = i;
                    entry.endLine = i;
                    entry.column = tokens[0].start;
                    entry.parent = parent;
                    entry.depth = int(open.size());
                    outline.append(entry);
                }
            }
        }
        for (int t = 0; t < count; ++t) {
            if (tokens[t].type == TokenType::Operator) {
                depth = qMax(0, depth + bracketDelta(line, tokens[t]));
            }
        }
        if (!isBlank(line)) {
            lastNonBlank = i;
        }
        state = endState;
    });
    closeTo(-1);
    return outline;
}

/** @brief MELの本文の構成(procの一覧)を読む。 @param lines 本文の行。 @return 項目の一覧。 */
QList<OutlineEntry> melOutline(const QStringList& lines) {
    static const QRegularExpression procPattern(
        "^\\s*(?:global\\s+)?proc\\s+(?:[A-Za-z_]\\w*(?:\\[\\])?\\s+)?([A-Za-z_]\\w*)\\s*\\(");
    QList<OutlineEntry> outline;
    QVector<Token> tokens;
    int state = kLexerNormal;
    int braceDepth = 0;
    int openIndex = -1;  // 中身の終わりを探しているproc。
    bool opened = false;
    for (int i = 0; i < lines.size(); ++i) {
        const QString& line = lines[i];
        int endState = kLexerNormal;
        tokenizeLineInto(line, ScriptLanguage::Mel, state, &endState, &tokens);
        if (state == kLexerNormal && braceDepth == 0) {
            const QRegularExpressionMatch match = procPattern.match(line);
            if (match.hasMatch()) {
                OutlineEntry entry;
                entry.name = match.captured(1);
                entry.kind = kindProc();
                entry.line = i;
                entry.endLine = i;
                entry.column = int(match.capturedStart(1));
                entry.detail = line.trimmed();
                outline.append(entry);
                openIndex = int(outline.size()) - 1;
                opened = false;
            }
        }
        for (const Token& token : tokens) {
            if (token.type != TokenType::Operator || token.length != 1) {
                continue;
            }
            const QChar c = line[token.start];
            if (c == '{') {
                ++braceDepth;
                opened = true;
            } else if (c == '}') {
                braceDepth = qMax(0, braceDepth - 1);
            }
        }
        if (openIndex >= 0 && opened && braceDepth == 0) {
            outline[openIndex].endLine = i;
            openIndex = -1;
        }
        state = endState;
    }
    if (openIndex >= 0) {
        outline[openIndex].endLine = int(lines.size()) - 1;
    }
    return outline;
}

/** @brief 行のインデントの幅と、空行かを1回の走査で求める(lineIndentWidthと同じ幅)。
 * @param line 行。
 * @param width 幅を入れる。
 * @return 空白(QChar::isSpace)だけの行ならfalse。
 */
bool indentation(QStringView line, int* width) {
    int value = 0;
    bool counting = true;  // 行頭の空白・タブを数えている間はtrue。それ以外の空白で幅の計算をやめる。
    for (const QChar c : line) {
        if (!c.isSpace()) {
            *width = value;
            return true;
        }
        if (!counting) {
            continue;
        }
        if (c == ' ') {
            ++value;
        } else if (c == '\t') {
            value = (value / 4 + 1) * 4;
        } else {
            counting = false;
        }
    }
    return false;
}

}  // namespace

int lineIndentWidth(QStringView line) {
    int width = 0;
    for (const QChar c : line) {
        if (c == ' ') {
            ++width;
        } else if (c == '\t') {
            width = (width / 4 + 1) * 4;
        } else {
            break;
        }
    }
    return width;
}

int lineIndentWidth(const QString& line) {
    return lineIndentWidth(QStringView(line));
}

QList<OutlineEntry> buildOutline(const QString& text, ScriptLanguage language) {
    return language == ScriptLanguage::Mel ? melOutline(text.split('\n')) : pythonOutline(text);
}

int findOutlinePath(const QList<OutlineEntry>& outline, const QStringList& path) {
    int parent = -1;
    int found = -1;
    for (const QString& name : path) {
        found = -1;
        for (int i = 0; i < outline.size(); ++i) {
            if (outline[i].parent == parent && outline[i].name == name) {
                found = i;  // 同じ場所に同じ名前が複数あれば、後の定義(Pythonで有効な方)を使う。
            }
        }
        if (found < 0) {
            return -1;
        }
        parent = found;
    }
    return found;
}

int enclosingOutlineEntry(const QList<OutlineEntry>& outline, int line) {
    int best = -1;
    for (int i = 0; i < outline.size(); ++i) {
        const OutlineEntry& entry = outline[i];
        if (entry.kind == kindVariable() || line < entry.line || line > entry.endLine) {
            continue;
        }
        if (best < 0 || entry.depth >= outline[best].depth) {
            best = i;
        }
    }
    return best;
}

QList<FoldRange> indentationFoldRanges(const QStringList& lines) {
    // 空でない行を開くたびに結果の配列へ仮の範囲(終わりが-1)を入れておき、閉じたときに終わりを書き込む。
    // こうすると結果は見出しの行の順に並ぶので、最後に並べ替える必要がない。中身の無かった仮の範囲は最後に除く。
    QList<FoldRange> ranges;
    ranges.reserve(lines.size());
    QVector<OpenEntry> open;  // まだ終わっていない、空でない行(インデント・結果の中の位置)。
    int lastNonBlank = -1;
    auto closeTo = [&ranges, &open, &lastNonBlank](int indent) {
        while (!open.isEmpty() && open.last().indent >= indent) {
            FoldRange& range = ranges[open.last().index];
            if (lastNonBlank > range.start) {
                range.end = lastNonBlank;
            }
            open.removeLast();
        }
    };
    for (int i = 0; i < lines.size(); ++i) {
        int indent = 0;
        if (!indentation(lines[i], &indent)) {
            continue;
        }
        closeTo(indent);
        ranges.append({i, -1});
        open.append({indent, int(ranges.size()) - 1});
        lastNonBlank = i;
    }
    closeTo(-1);
    ranges.erase(std::remove_if(ranges.begin(), ranges.end(), [](const FoldRange& range) { return range.end < 0; }),
                 ranges.end());
    return ranges;
}

int localDefinitionLine(const QString& text, const QString& name, int beforeLine, int* column) {
    if (name.isEmpty()) {
        return -1;
    }
    // 行の始まりの位置(beforeLineの行まで)。行ごとのQStringは、名前を含む行だけ作る。
    QVector<int> lineStarts;
    lineStarts.append(0);
    for (int position = int(text.indexOf('\n')); position >= 0 && lineStarts.size() < beforeLine;
         position = int(text.indexOf('\n', position + 1))) {
        lineStarts.append(position + 1);
    }
    const int lineCount = qMin(beforeLine, int(lineStarts.size()));
    if (lineCount <= 0) {
        return -1;
    }
    const QString n = QRegularExpression::escape(name);
    // 正規表現は最初に照合するときに作られる(名前を含む行が無ければ作らない)。
    const QRegularExpression patterns[] = {
        // 代入・型ヒント(a, name = ... も含む)。
        QRegularExpression("^\\s*(?:[A-Za-z_][\\w.]*\\s*,\\s*)*(" + n + ")\\s*(?:,\\s*[A-Za-z_][\\w.]*\\s*)*(?:=(?!=)|:(?!=)|\\+=|-=)"),
        // for name in / for a, name in
        QRegularExpression("^\\s*(?:async\\s+)?for\\s+[\\w\\s,()]*?\\b(" + n + ")\\b[\\w\\s,()]*\\bin\\b"),
        // with ... as name / except ... as name / import ... as name
        QRegularExpression("\\bas\\s+(" + n + ")\\b"),
        // import name / from x import a, name
        QRegularExpression("^\\s*(?:from\\s+[\\w.]+\\s+)?import\\s+(?:[\\w.]+\\s*,\\s*)*(" + n + ")\\b"),
        // 関数の引数(def f(a, name=1) / 複数行の引数)。
        QRegularExpression("^\\s*(?:async\\s+)?def\\s+\\w+\\s*(?:\\(|\\(.*?,)\\s*\\**(" + n + ")\\s*(?:[:=,)]|$)"),
        QRegularExpression("^\\s*(?:async\\s+)?def\\s+(" + n + ")\\s*\\("),
        QRegularExpression("^\\s*class\\s+(" + n + ")\\b"),
    };
    const QStringView whole(text);
    for (int i = lineCount - 1; i >= 0; --i) {
        const int start = lineStarts[i];
        int end = i + 1 < lineStarts.size() ? lineStarts[i + 1] - 1 : int(text.indexOf('\n', start));
        if (end < 0) {
            end = int(text.size());
        }
        const QStringView view = whole.mid(start, end - start);
        // どのパターンも名前をそのまま含む行にしか一致しないので、含まない行は正規表現を使わずに飛ばす。
        if (!view.contains(name)) {
            continue;
        }
        const QString line = view.toString();
        for (const QRegularExpression& pattern : patterns) {
            const QRegularExpressionMatch match = pattern.match(line);
            if (match.hasMatch()) {
                if (column) {
                    *column = int(match.capturedStart(1));
                }
                return i;
            }
        }
    }
    return -1;
}

}  // namespace hedit
