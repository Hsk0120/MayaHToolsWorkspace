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

QString formatCommandOutput(const QString& message, OutputKind kind, bool legacy) {
    // Pythonの例外は「例外の型: file 場所 line 行: 内容」の形で通知される(MELのファイルの中で起きたときは
    // その前に「file: a.mel line 32: 」が付く)。Script Editorでは # で始まる。
    static const QRegularExpression pythonException("(?:^|: )[A-Za-z_][\\w.]*: file .+ line \\d+: ");
    // 正規表現は重いので、エラーで「: file 」を含むものだけ調べる(大量のエラーでも速く整えるため)。
    const bool python = kind == OutputKind::Error && message.contains(QLatin1String(": file "))
                        && pythonException.match(message).hasMatch();
    const QString marker = python ? QStringLiteral("# ") : QStringLiteral("// ");
    QString label;
    switch (kind) {
    case OutputKind::Warning: label = QStringLiteral("Warning: "); break;
    case OutputKind::Error: label = QStringLiteral("Error: "); break;
    case OutputKind::Result: label = QStringLiteral("Result: "); break;
    case OutputKind::Info: break;
    default: return message;
    }
    if (legacy) {
        // Maya 2022: 本文はそのままで、最後に「 // 」(Pythonは「 # 」)を付けて改行する。
        const QString closing = python ? QStringLiteral(" # ") : QStringLiteral(" // ");
        if (kind == OutputKind::Result) {
            return QStringLiteral("// Result: ") + message + closing + '\n';
        }
        return marker + label + message + closing + '\n';
    }
    QString body = message;
    if (body.endsWith('\n')) {
        body.chop(1);  // 最後の改行は行の区切りとして数えない。
    }
    if (kind == OutputKind::Result) {
        return QStringLiteral("// Result: ") + body + '\n';
    }
    if (!body.contains('\n')) {
        return marker + label + body + '\n';  // 1行(ほとんどの通知)は分けずに作る。
    }
    // 1行目にだけ種類(Warning: など)を付け、全ての行の頭に記号を付ける(reporterと同じ)。
    const QStringList lines = body.split('\n');
    QString text;
    for (int i = 0; i < lines.size(); ++i) {
        text += marker + (i == 0 ? label : QString()) + lines[i] + '\n';
    }
    return text;
}

}  // namespace hedit
