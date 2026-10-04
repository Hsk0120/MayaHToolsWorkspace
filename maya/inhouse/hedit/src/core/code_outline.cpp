/** @file code_outline.cpp
 * @brief 本文の構成と折りたたみの範囲の実装。
 * @details Pythonは1行ずつ字句に分け、「文の始まりの行」(前の行から文字列・括弧が続いていない行)だけを見る。
 * クラス・関数の範囲は、同じかより浅いインデントの文が現れた所で閉じる(スタックで1回の走査で求める)。
 */
#include "core/code_outline.h"
#include <QRegularExpression>
#include <algorithm>
#include <QVector>

namespace hedit {
namespace {

/** @brief 開き括弧なら+1、閉じ括弧なら-1。 @param text 記号の字句。 @return 括弧の深さの変化。 */
int bracketDelta(const QString& text) {
    if (text.size() != 1) {
        return 0;
    }
    const QChar c = text[0];
    if (c == '(' || c == '[' || c == '{') {
        return 1;
    }
    if (c == ')' || c == ']' || c == '}') {
        return -1;
    }
    return 0;
}

/** @brief 開いているクラス・関数(範囲の終わりがまだ決まっていない項目)。 */
struct OpenEntry {
    int indent = 0;  ///< 見出しの行のインデント。
    int index = 0;   ///< 項目の位置。
};

/** @brief Pythonの本文の構成を読む。 @param lines 本文の行。 @return 項目の一覧。 */
QList<OutlineEntry> pythonOutline(const QStringList& lines) {
    QList<OutlineEntry> outline;
    QVector<OpenEntry> open;  // 外側から順。
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
    for (int i = 0; i < lines.size(); ++i) {
        const QString& line = lines[i];
        int endState = kLexerNormal;
        const QList<Token> tokens = tokenizeLine(line, ScriptLanguage::Python, state, &endState);
        const bool statementStart = state == kLexerNormal && depth == 0;
        // コメントを除いた字句。
        QList<Token> code;
        for (const Token& token : tokens) {
            if (token.type != TokenType::Comment) {
                code.append(token);
            }
        }
        if (statementStart && !code.isEmpty()) {
            const int indent = lineIndentWidth(line);
            closeTo(indent);
            auto text = [&line, &code](int index) {
                return index < code.size() ? line.mid(code[index].start, code[index].length) : QString();
            };
            int nameIndex = -1;
            QString kind;
            if (text(0) == "class") {
                nameIndex = 1;
                kind = "class";
            } else if (text(0) == "def") {
                nameIndex = 1;
                kind = "function";
            } else if (text(0) == "async" && text(1) == "def") {
                nameIndex = 2;
                kind = "function";
            }
            const int parent = open.isEmpty() ? -1 : open.last().index;
            if (nameIndex > 0 && nameIndex < code.size() && code[nameIndex].type == TokenType::Name) {
                OutlineEntry entry;
                entry.name = text(nameIndex);
                entry.kind = kind == "function" && parent >= 0 && outline[parent].kind == "class" ? "method" : kind;
                entry.line = i;
                entry.endLine = i;
                entry.column = code[nameIndex].start;
                entry.parent = parent;
                entry.depth = open.size();
                QString header = line.trimmed();
                if (header.endsWith(':')) {
                    header.chop(1);
                }
                entry.detail = header;
                outline.append(entry);
                open.append({indent, int(outline.size()) - 1});
            } else if (code[0].type == TokenType::Name && !isKeyword(text(0), ScriptLanguage::Python)
                       && code.size() >= 2 && code[1].type == TokenType::Operator
                       && (text(1) == "=" || text(1) == ":")
                       && (parent < 0 || outline[parent].kind == "class")) {
                // トップレベルとクラス直下の代入(x = 1・x: int = 1)。同じ場所の同じ名前は最初だけ。
                bool duplicate = false;
                for (int e = outline.size() - 1; e >= 0 && !duplicate; --e) {
                    duplicate = outline[e].parent == parent && outline[e].name == text(0)
                                && outline[e].kind == "variable";
                }
                if (!duplicate) {
                    OutlineEntry entry;
                    entry.name = text(0);
                    entry.kind = "variable";
                    entry.line = i;
                    entry.endLine = i;
                    entry.column = code[0].start;
                    entry.parent = parent;
                    entry.depth = open.size();
                    outline.append(entry);
                }
            }
        }
        for (const Token& token : code) {
            if (token.type == TokenType::Operator) {
                depth = qMax(0, depth + bracketDelta(line.mid(token.start, token.length)));
            }
        }
        if (!line.trimmed().isEmpty()) {
            lastNonBlank = i;
        }
        state = endState;
    }
    closeTo(-1);
    return outline;
}

/** @brief MELの本文の構成(procの一覧)を読む。 @param lines 本文の行。 @return 項目の一覧。 */
QList<OutlineEntry> melOutline(const QStringList& lines) {
    static const QRegularExpression procPattern(
        "^\\s*(?:global\\s+)?proc\\s+(?:[A-Za-z_]\\w*(?:\\[\\])?\\s+)?([A-Za-z_]\\w*)\\s*\\(");
    QList<OutlineEntry> outline;
    int state = kLexerNormal;
    int braceDepth = 0;
    int openIndex = -1;  // 中身の終わりを探しているproc。
    bool opened = false;
    for (int i = 0; i < lines.size(); ++i) {
        const QString& line = lines[i];
        int endState = kLexerNormal;
        const QList<Token> tokens = tokenizeLine(line, ScriptLanguage::Mel, state, &endState);
        if (state == kLexerNormal && braceDepth == 0) {
            const QRegularExpressionMatch match = procPattern.match(line);
            if (match.hasMatch()) {
                OutlineEntry entry;
                entry.name = match.captured(1);
                entry.kind = "proc";
                entry.line = i;
                entry.endLine = i;
                entry.column = match.capturedStart(1);
                entry.detail = line.trimmed();
                outline.append(entry);
                openIndex = outline.size() - 1;
                opened = false;
            }
        }
        for (const Token& token : tokens) {
            if (token.type != TokenType::Operator) {
                continue;
            }
            const QString text = line.mid(token.start, token.length);
            if (text == "{") {
                ++braceDepth;
                opened = true;
            } else if (text == "}") {
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
        outline[openIndex].endLine = lines.size() - 1;
    }
    return outline;
}

}  // namespace

int lineIndentWidth(const QString& line) {
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

QList<OutlineEntry> buildOutline(const QString& text, ScriptLanguage language) {
    const QStringList lines = text.split('\n');
    return language == ScriptLanguage::Mel ? melOutline(lines) : pythonOutline(lines);
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
        if (entry.kind == "variable" || line < entry.line || line > entry.endLine) {
            continue;
        }
        if (best < 0 || entry.depth >= outline[best].depth) {
            best = i;
        }
    }
    return best;
}

QList<FoldRange> indentationFoldRanges(const QStringList& lines) {
    QList<FoldRange> ranges;
    QVector<OpenEntry> open;  // まだ終わっていない、空でない行(インデント・行)。
    int lastNonBlank = -1;
    auto closeTo = [&ranges, &open, &lastNonBlank](int indent) {
        while (!open.isEmpty() && open.last().indent >= indent) {
            if (lastNonBlank > open.last().index) {
                ranges.append({open.last().index, lastNonBlank});
            }
            open.removeLast();
        }
    };
    for (int i = 0; i < lines.size(); ++i) {
        if (lines[i].trimmed().isEmpty()) {
            continue;
        }
        closeTo(lineIndentWidth(lines[i]));
        open.append({lineIndentWidth(lines[i]), i});
        lastNonBlank = i;
    }
    closeTo(-1);
    std::sort(ranges.begin(), ranges.end(), [](const FoldRange& a, const FoldRange& b) { return a.start < b.start; });
    return ranges;
}

int localDefinitionLine(const QString& text, const QString& name, int beforeLine, int* column) {
    if (name.isEmpty()) {
        return -1;
    }
    const QString n = QRegularExpression::escape(name);
    const QList<QRegularExpression> patterns{
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
    const QStringList lines = text.split('\n');
    for (int i = qMin(beforeLine, int(lines.size())) - 1; i >= 0; --i) {
        for (const QRegularExpression& pattern : patterns) {
            const QRegularExpressionMatch match = pattern.match(lines[i]);
            if (match.hasMatch()) {
                if (column) {
                    *column = match.capturedStart(1);
                }
                return i;
            }
        }
    }
    return -1;
}

}  // namespace hedit
