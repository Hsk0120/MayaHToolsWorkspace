/** @file script_file.cpp
 * @brief スクリプトファイルの読み書き。
 */
#include "core/script_file.h"
#include <QFile>
#include <QRegularExpression>
#include <QSaveFile>

namespace hedit {

bool readScriptFile(const QString& path, QString* text, QString* error) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        *error = file.errorString();
        return false;
    }
    QByteArray bytes = file.readAll();
    if (bytes.startsWith("\xef\xbb\xbf")) {
        bytes.remove(0, 3);
    }
    const QString decoded = QString::fromUtf8(bytes);
    // UTF-8として読み、書き戻して元と一致しなければ、UTF-8以外の文字コード。
    if (decoded.toUtf8() != bytes) {
        *error = "Only UTF-8 files are supported";
        return false;
    }
    *text = decoded;
    return true;
}

QString formatForSave(QString text, bool trimTrailingSpaces, bool ensureFinalNewline) {
    if (trimTrailingSpaces) {
        static const QRegularExpression trailingSpaces("[ \\t]+(?=\\n|$)");
        text.replace(trailingSpaces, QString());
    }
    if (ensureFinalNewline && !text.endsWith('\n')) {
        text += '\n';
    }
    return text;
}

bool writeScriptFile(const QString& path, const QString& text, QString* error) {
    QSaveFile file(path);
    const QByteArray bytes = text.toUtf8();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
        *error = file.errorString();
        return false;
    }
    return true;
}

}  // namespace hedit
