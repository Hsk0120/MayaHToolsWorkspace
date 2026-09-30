/** @file docstrings.cpp
 * @brief 文字列リテラルの値とdocstringの整形の実装。
 */
#include "core/docstrings.h"
#include <climits>

namespace hedit {
namespace {

/** @brief タブを8桁ごとの空白にする(Pythonの``str.expandtabs()``と同じ)。 @param line 1行。 @return 置き換えた行。 */
QString expandTabs(const QString& line) {
    QString result;
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
int leadingSpaces(const QString& line) {
    int count = 0;
    while (count < line.size() && line[count] == ' ') {
        ++count;
    }
    return count;
}

/** @brief raw文字列でないリテラルの``\``のエスケープを元の文字に戻す。 @param body 引用符の内側。 @return 値。 */
QString unescape(const QString& body) {
    QString result;
    for (int i = 0; i < body.size(); ++i) {
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
    const QString rest = literal.mid(start);
    if (rest.isEmpty()) {
        return QString();
    }
    QString quote = rest.left(1);
    if (rest.startsWith(QString(3, quote[0]))) {
        quote = QString(3, quote[0]);
    }
    QString body = rest.mid(quote.size());
    if (body.endsWith(quote) && rest.size() >= quote.size() * 2) {
        body.chop(quote.size());
    }
    return raw ? body : unescape(body);
}

QString stringLiteralsValue(const QStringList& literals) {
    QString value;
    for (const QString& literal : literals) {
        value += stringLiteralValue(literal);
    }
    return value;
}

QString cleanDocstring(const QString& text) {
    QStringList lines = text.split('\n');
    for (QString& line : lines) {
        line = expandTabs(line);
    }
    // 2行目以降の、空白だけでない行に共通する字下げを求める。
    int margin = INT_MAX;
    for (int i = 1; i < lines.size(); ++i) {
        if (!lines[i].trimmed().isEmpty()) {
            margin = qMin(margin, leadingSpaces(lines[i]));
        }
    }
    if (!lines.isEmpty()) {
        lines[0] = lines[0].mid(leadingSpaces(lines[0]));
    }
    if (margin != INT_MAX) {
        for (int i = 1; i < lines.size(); ++i) {
            lines[i] = lines[i].mid(margin);
        }
    }
    // 行末の空白と、前後の空行を除く。
    for (QString& line : lines) {
        while (!line.isEmpty() && line.back().isSpace()) {
            line.chop(1);
        }
    }
    while (!lines.isEmpty() && lines.first().isEmpty()) {
        lines.removeFirst();
    }
    while (!lines.isEmpty() && lines.last().isEmpty()) {
        lines.removeLast();
    }
    return lines.join('\n');
}

}  // namespace hedit
