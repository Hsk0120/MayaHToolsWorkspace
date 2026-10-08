/** @file docstrings.cpp
 * @brief 文字列リテラルの値とdocstringの整形の実装。
 * @details 宣言の抽出(core/python_declarations.cpp)が、def・classごとに呼ぶ。行や部分ごとのQStringを作らないよう、
 * 途中はQStringView(元の文字列の一部を指す)で扱い、最後に1つの文字列へまとめる。
 */
#include "core/docstrings.h"
#include <QVector>
#include <climits>

namespace hedit {
namespace {

/** @brief タブを8桁ごとの空白にする(Pythonの``str.expandtabs()``と同じ)。 @param line 1行。 @return 置き換えた行。 */
QString expandTabs(QStringView line) {
    QString result;
    result.reserve(int(line.size()) + 8);
    for (const QChar c : line) {
        if (c == '\t') {
            result += QString(8 - result.size() % 8, ' ');
        } else {
            result += c;
        }
    }
    return result;
}

/** @brief 行頭の空白の数。 @param line 1行。 @return 数。 */
int leadingSpaces(QStringView line) {
    int count = 0;
    while (count < line.size() && line[count] == ' ') {
        ++count;
    }
    return count;
}

/** @brief 空白(QChar::isSpace)だけの行か(``line.trimmed().isEmpty()``と同じ)。 @param line 1行。 @return 空行ならtrue。 */
bool isBlank(QStringView line) {
    for (const QChar c : line) {
        if (!c.isSpace()) {
            return false;
        }
    }
    return true;
}

/** @brief raw文字列でないリテラルの``\``のエスケープを元の文字に戻す。 @param body 引用符の内側。 @return 値。 */
QString unescape(QStringView body) {
    QString result;
    result.reserve(int(body.size()));
    for (qsizetype i = 0; i < body.size(); ++i) {
        if (body[i] != '\\' || i + 1 >= body.size()) {
            result += body[i];
            continue;
        }
        const QChar next = body[++i];
        switch (next.unicode()) {
        case 'n': result += '\n'; break;
        case 't': result += '\t'; break;
        case 'r': break;  // 改行はLFだけにそろえる。
        case '\\': result += '\\'; break;
        case '\'': result += '\''; break;
        case '"': result += '"'; break;
        case '\n': break;  // 行末の \ は、次の行へ続く印(文字にはならない)。
        default:
            // \d のような未知のエスケープは、Pythonと同じくそのまま残す。
            result += '\\';
            result += next;
        }
    }
    return result;
}

}  // namespace

QString stringLiteralValue(const QString& literal) {
    int start = 0;
    bool raw = false;
    while (start < literal.size() && literal[start].isLetter()) {
        raw = raw || literal[start].toLower() == 'r';
        ++start;
    }
    const QStringView rest = QStringView(literal).mid(start);
    if (rest.isEmpty()) {
        return QString();
    }
    // 引用符は1文字か、同じ文字の3つ(三重引用符)。
    const QChar quote = rest[0];
    const int quoteSize = rest.size() >= 3 && rest[1] == quote && rest[2] == quote ? 3 : 1;
    QStringView body = rest.mid(quoteSize);
    bool closed = body.size() >= quoteSize;
    for (int i = 1; closed && i <= quoteSize; ++i) {
        closed = body[body.size() - i] == quote;
    }
    if (closed && rest.size() >= quoteSize * 2) {
        body.chop(quoteSize);
    }
    return raw ? body.toString() : unescape(body);
}

QString stringLiteralsValue(const QStringList& literals) {
    QString value;
    for (const QString& literal : literals) {
        value += stringLiteralValue(literal);
    }
    return value;
}

QString cleanDocstring(const QString& text) {
    // 行は元の文字列の一部を指す。タブがあるときだけ、タブを空白にした行を作る(expanded)。
    // 行のQStringViewは文字の並びを指すので、expandedの配列が伸びて要素が移っても無効にならない(QStringの中身は動かない)。
    QVector<QStringView> lines;
    QStringList expanded;
    const QStringView whole(text);
    const bool hasTabs = text.contains(QLatin1Char('\t'));
    for (qsizetype start = 0;;) {
        const qsizetype newline = whole.indexOf(QLatin1Char('\n'), start);
        const QStringView line = whole.mid(start, (newline < 0 ? whole.size() : newline) - start);
        if (hasTabs && line.contains(QLatin1Char('\t'))) {
            expanded.append(expandTabs(line));
            lines.append(expanded.last());
        } else {
            lines.append(line);
        }
        if (newline < 0) {
            break;
        }
        start = newline + 1;
    }
    // 2行目以降の、空白だけでない行に共通する字下げを求める。
    int margin = INT_MAX;
    for (int i = 1; i < lines.size(); ++i) {
        if (!isBlank(lines[i])) {
            margin = qMin(margin, leadingSpaces(lines[i]));
        }
    }
    lines[0] = lines[0].mid(leadingSpaces(lines[0]));
    if (margin != INT_MAX) {
        for (int i = 1; i < lines.size(); ++i) {
            lines[i] = lines[i].mid(margin);
        }
    }
    // 行末の空白と、前後の空行を除く。
    qsizetype total = 0;
    for (QStringView& line : lines) {
        while (!line.isEmpty() && line.back().isSpace()) {
            line.chop(1);
        }
        total += line.size() + 1;
    }
    int first = 0;
    int last = int(lines.size()) - 1;
    while (first <= last && lines[first].isEmpty()) {
        ++first;
    }
    while (last >= first && lines[last].isEmpty()) {
        --last;
    }
    QString result;
    result.reserve(int(total));
    for (int i = first; i <= last; ++i) {
        if (i > first) {
            result += '\n';
        }
        result.append(lines[i].data(), int(lines[i].size()));
    }
    return result;
}

}  // namespace hedit
