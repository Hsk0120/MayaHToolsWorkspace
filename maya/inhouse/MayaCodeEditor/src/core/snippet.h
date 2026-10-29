/** @file snippet.h
 * @brief LSPの番号付きスニペットを実行せず展開する。未対応の変換は本文を変更せず拒否する。
 */
#pragma once
#include <QMap>
#include <QSet>
#include <QString>
#include <QVector>
#include <algorithm>

namespace mce {
/** @brief 展開後のUTF-16選択範囲。0は終了位置。 */
struct SnippetStop { int number; int start; int length; };
/** @brief スニペットの本文と入力箇所。 */
struct SnippetExpansion { QString text; QVector<SnippetStop> stops; };
/** @brief スニペットをプレーンテキストと入力範囲へ変換する。
 * @param source サーバーのスニペット。@param result 成功時の展開。
 * @return 構文・変換・重複参照が未対応ならfalse。任意コードは実行しない。
 */
inline bool expandSnippet(const QString& source, SnippetExpansion* result) {
    SnippetExpansion out;
    QSet<int> numbers;
    for (int i = 0; i < source.size();) {
        QChar ch = source[i++];
        if (ch == '\\') {
            if (i < source.size() && (source[i] == '\\' || source[i] == '$' || source[i] == '}')) out.text += source[i++];
            else out.text += ch;
            continue;
        }
        if (ch != '$') { out.text += ch; continue; }
        bool braced = i < source.size() && source[i] == '{';
        if (braced) ++i;
        int begin = i;
        while (i < source.size() && source[i].isDigit()) ++i;
        if (begin == i) return false;
        bool ok = false;
        int number = source.mid(begin, i - begin).toInt(&ok);
        if (!ok || numbers.contains(number)) return false;
        numbers.insert(number);
        QString value;
        if (braced) {
            if (i >= source.size()) return false;
            if (source[i] == ':' || source[i] == '|') {
                const bool choice = source[i++] == '|';
                bool first = true;
                bool closedChoice = !choice;
                while (i < source.size() && source[i] != '}') {
                    ch = source[i++];
                    if (ch == '\\') {
                        if (i < source.size() && (source[i] == '\\' || source[i] == '$' || source[i] == '}'
                            || (choice && (source[i] == ',' || source[i] == '|')))) ch = source[i++];
                    } else {
                        if (ch == '$' || ch == '{') return false;
                        if (choice && ch == ',') { first = false; continue; }
                        if (choice && ch == '|') {
                            if (i >= source.size() || source[i] != '}') return false;
                            closedChoice = true;
                            break;
                        }
                    }
                    if (first) value += ch;
                }
                if (!closedChoice) return false;
            }
            if (i >= source.size() || source[i++] != '}') return false;
        }
        out.stops.append({number, int(out.text.size()), int(value.size())});
        out.text += value;
    }
    std::sort(out.stops.begin(), out.stops.end(), [](const SnippetStop& a, const SnippetStop& b) {
        if (a.number == 0) return false;
        if (b.number == 0) return true;
        return a.number < b.number;
    });
    if (!numbers.contains(0)) out.stops.append({0, int(out.text.size()), 0});
    *result = out;
    return true;
}
}  // namespace mce
