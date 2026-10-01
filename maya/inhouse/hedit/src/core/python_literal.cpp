/** @file python_literal.cpp
 * @brief Pythonの文字列リテラルを作る処理の実装。
 */
#include "core/python_literal.h"

namespace hedit {

QString pythonStringLiteral(const QString& text) {
    QString literal;
    literal.reserve(text.size() + 2);
    literal += '\'';
    for (const QChar c : text) {
        switch (c.unicode()) {
        case '\\': literal += QLatin1String("\\\\"); break;
        case '\'': literal += QLatin1String("\\'"); break;
        case '\n': literal += QLatin1String("\\n"); break;
        case '\r': literal += QLatin1String("\\r"); break;
        case '\t': literal += QLatin1String("\\t"); break;
        default:
            if (c.unicode() < 0x20 || c.unicode() == 0x7F) {
                literal += QString("\\x%1").arg(c.unicode(), 2, 16, QLatin1Char('0'));
            } else {
                literal += c;
            }
        }
    }
    literal += '\'';
    return literal;
}

QString pythonStringListLiteral(const QStringList& items) {
    QStringList literals;
    for (const QString& item : items) {
        literals.append(pythonStringLiteral(item));
    }
    return "[" + literals.join(", ") + "]";
}

}  // namespace hedit
