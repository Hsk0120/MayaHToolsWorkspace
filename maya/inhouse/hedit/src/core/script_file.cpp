/** @file script_file.cpp
 * @brief スクリプトファイルの読み書き。
 */
#include "core/script_file.h"
#include <QFile>
#include <QRegularExpression>
#include <QSaveFile>

namespace hedit {
namespace {

/** @brief 正しいUTF-8か(RFC 3629)。
 * @param bytes 調べるバイト列。
 * @return 正しければtrue。途中で切れた文字・余分に長い符号化・サロゲート(U+D800〜U+DFFF)・
 * U+10FFFFを超える値はfalse。
 * @details 以前は、QString::fromUtf8で読んだ文字列をUTF-8に書き戻して元と比べていた(書き戻しの分だけ
 * 確保と変換が余分にかかる)。この判定は、書き戻して一致するかと同じ結果になる。
 */
bool isValidUtf8(const QByteArray& bytes) {
    const auto* data = reinterpret_cast<const unsigned char*>(bytes.constData());
    const qsizetype size = bytes.size();
    qsizetype i = 0;
    while (i < size) {
        const unsigned char first = data[i];
        if (first < 0x80) {
            ++i;
            continue;
        }
        int length = 0;
        unsigned int minimum = 0;  // この長さで表すべき最小の値(これより小さければ余分に長い符号化)。
        unsigned int value = 0;
        if ((first & 0xe0) == 0xc0) {
            length = 2;
            minimum = 0x80;
            value = first & 0x1f;
        } else if ((first & 0xf0) == 0xe0) {
            length = 3;
            minimum = 0x800;
            value = first & 0x0f;
        } else if ((first & 0xf8) == 0xf0) {
            length = 4;
            minimum = 0x10000;
            value = first & 0x07;
        } else {
            return false;  // 続きのバイト(10xxxxxx)が先頭にある、または5バイト以上の形。
        }
        if (i + length > size) {
            return false;  // 途中で切れている。
        }
        for (int k = 1; k < length; ++k) {
            const unsigned char next = data[i + k];
            if ((next & 0xc0) != 0x80) {
                return false;
            }
            value = (value << 6) | (next & 0x3f);
        }
        if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) {
            return false;
        }
        i += length;
    }
    return true;
}

}  // namespace

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
    // UTF-8として正しくなければ、UTF-8以外の文字コード。
    const QString decoded = QString::fromUtf8(bytes);
    // 2つ目のBOM(EF BB BF)で始まるとき、QString::fromUtf8がそれも除くなら、書き戻すと元と一致しない。
    // 以前の判定(書き戻して比べる)と同じく、その場合もUTF-8以外として扱う。
    const bool bomDropped = bytes.startsWith("\xef\xbb\xbf") && !decoded.startsWith(QChar(0xfeff));
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    // Qt5のQString::fromUtf8(QByteArray)は最初のNUL文字で読むのをやめる。以前の判定では書き戻しが一致しないため
    // UTF-8以外として扱っていた(途中で切れた本文を開かない)。同じにする。
    const bool truncated = bytes.contains('\0');
#else
    const bool truncated = false;
#endif
    if (!isValidUtf8(bytes) || bomDropped || truncated) {
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
