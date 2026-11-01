/** @file text_decode.h @brief テキストの安全な復号。 */
#pragma once
#include <QString>
#include <QByteArray>
namespace qpe {
/** @brief BOM付きUTF-16/UTF-8とCP932を復号する。 @param bytes 内容。 @return 復号文字列。 */
QString decodeText(QByteArray bytes);
}
