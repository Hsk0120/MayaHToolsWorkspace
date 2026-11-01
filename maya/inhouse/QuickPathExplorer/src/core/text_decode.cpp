/** @file text_decode.cpp @brief 検索とプレビューで共通の文字コード判定。 */
#include "text_decode.h"
#include <string>
#define NOMINMAX
#include <windows.h>
namespace qpe {
/** @brief UTF BOM/UTF-8/CP932をシェルなしで復号する。 @param bytes 内容。 @return テキスト。 */
QString decodeText(QByteArray bytes) {
    if (bytes.startsWith("\xff\xfe") || bytes.startsWith("\xfe\xff")) {
        const bool little = bytes.startsWith("\xff\xfe"); QString result;
        for (int i = 2; i + 1 < bytes.size(); i += 2) result.append(QChar(little ? uchar(bytes[i]) | (ushort(uchar(bytes[i + 1])) << 8) : (ushort(uchar(bytes[i])) << 8) | uchar(bytes[i + 1])));
        return result;
    }
    if (bytes.startsWith("\xef\xbb\xbf")) bytes.remove(0, 3);
    int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.constData(), bytes.size(), nullptr, 0); UINT page = CP_UTF8;
    if (!length) { page = 932; length = MultiByteToWideChar(page, 0, bytes.constData(), bytes.size(), nullptr, 0); }
    std::wstring text(size_t(length), L'\0'); if (length) MultiByteToWideChar(page, page == CP_UTF8 ? MB_ERR_INVALID_CHARS : 0, bytes.constData(), bytes.size(), &text[0], length);
    return QString::fromStdWString(text);
}
}
