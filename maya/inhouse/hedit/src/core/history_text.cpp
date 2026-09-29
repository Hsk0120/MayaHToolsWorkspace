/** @file history_text.cpp
 * @brief 起動前の出力履歴の整形と種類の判定。
 */
#include "core/history_text.h"
#include <QRegularExpression>
#include <QStringList>

namespace hedit {

QString compactHistory(QString text) {
    if (text.isEmpty()) {
        return QString();
    }
    // Windowsの改行(CRLF)と古いMacの改行(CR)を、すべてLFにそろえる。
    text.replace("\r\n", "\n");
    text.replace('\r', '\n');

    // print(a, b) は "a" " " "b" のように分かれて通知される。そのため履歴では
    // "optimization\n \non" のように空白だけの行が挟まる。空白を残して前後をつなぐ。
    static const QRegularExpression whitespaceOnlyLine("\n([ \t]+)\n");
    text.replace(whitespaceOnlyLine, "\\1");

    QStringList lines;
    for (const QString& line : text.split('\n')) {
        if (!line.trimmed().isEmpty()) {
            lines.append(line);
        }
    }
    return lines.join('\n') + "\n";
}

OutputKind classifyHistoryLine(const QString& line) {
    // MELの出力は "//"、Pythonの出力は "#" で始まる。
    if (line.startsWith("// Result:") || line.startsWith("# Result:")) {
        return OutputKind::Result;
    }
    if (line.startsWith("// Warning:") || line.startsWith("# Warning:")) {
        return OutputKind::Warning;
    }
    if (line.startsWith("// Error:") || line.startsWith("# Error:")) {
        return OutputKind::Error;
    }
    return OutputKind::Normal;
}

}  // namespace hedit
