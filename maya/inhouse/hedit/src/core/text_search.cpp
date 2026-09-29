/** @file text_search.cpp
 * @brief 検索・置換の一致箇所の計算と、置換文字列の展開。
 */
#include "core/text_search.h"
#include <QRegularExpression>

namespace hedit {
namespace {

/// 一致の件数の上限。これを超える検索は止める(画面が長時間固まるのを防ぐ)。
constexpr int kMaximumMatches = 100000;

/** @brief 検索条件から、QRegularExpressionのパターン文字列を作る。
 * @param options 検索条件。
 * @return 正規表現モードでなければ、入力をそのまま一致させるようエスケープしたパターン。
 */
QString buildPattern(const SearchOptions& options) {
    QString pattern = options.regex ? options.text : QRegularExpression::escape(options.text);
    if (options.wholeWord) {
        // 前後が単語の文字(英数字と_)でないときだけ一致させる。
        pattern = "(?<!\\w)(?:" + pattern + ")(?!\\w)";
    }
    return pattern;
}

}  // namespace

SearchResult findMatches(const QString& document, const SearchOptions& options, const QString* replacementTemplate) {
    SearchResult result;
    auto flags = QRegularExpression::UseUnicodePropertiesOption | QRegularExpression::MultilineOption;
    if (!options.matchCase) {
        flags |= QRegularExpression::CaseInsensitiveOption;
    }
    const QRegularExpression regex(buildPattern(options), flags);
    if (!regex.isValid()) {
        result.error = "Invalid regular expression: " + regex.errorString();
        return result;
    }

    auto iterator = regex.globalMatch(document);
    while (iterator.hasNext()) {
        const QRegularExpressionMatch match = iterator.next();
        if (match.capturedLength() == 0) {
            result.error = "Zero-length matches are not supported";
            return result;
        }
        if (result.matches.size() >= kMaximumMatches) {
            result.error = "Too many matches (limit 100,000)";
            return result;
        }
        // 選択範囲内で検索するときは、範囲に収まる一致だけを数える。
        const bool limited = options.rangeStart >= 0 && options.rangeEnd >= options.rangeStart;
        if (limited && (match.capturedStart() < options.rangeStart || match.capturedEnd() > options.rangeEnd)) {
            continue;
        }
        result.matches.append({int(match.capturedStart()), int(match.capturedLength())});
        if (replacementTemplate) {
            // 通常の検索では置換の文字列をそのまま使う。$記法は正規表現モードだけ。
            QString value = options.regex ? expandReplacement(*replacementTemplate, match, regex.captureCount())
                                          : *replacementTemplate;
            if (options.preserveCase) {
                value = preserveCase(value, match.captured());
            }
            result.replacements.append(value);
        }
    }
    return result;
}

QString expandReplacement(const QString& replacementTemplate, const QRegularExpressionMatch& match, int captureCount) {
    const QString& value = replacementTemplate;
    QString expanded;
    for (int i = 0; i < value.size(); ++i) {
        const bool isLastCharacter = i + 1 == value.size();
        if (value[i] != '$' || isLastCharacter) {
            expanded += value[i];
            continue;
        }
        const QChar next = value[i + 1];
        if (next == '$') {
            // $$ はドル記号そのもの。
            expanded += '$';
            ++i;
        } else if (next == '&') {
            // $& は一致した文字列全体。
            expanded += match.captured();
            ++i;
        } else if (next >= '1' && next <= '9') {
            // $1〜$99 はキャプチャー。2桁目は、その番号のキャプチャーがある場合だけ読む。
            int number = next.digitValue();
            ++i;
            const bool hasSecondDigit = i + 1 < value.size() && value[i + 1].isDigit();
            if (hasSecondDigit && number * 10 + value[i + 1].digitValue() <= captureCount) {
                ++i;
                number = number * 10 + value[i].digitValue();
            }
            if (number <= captureCount) {
                expanded += match.captured(number);
            } else {
                expanded += '$' + QString::number(number);
            }
        } else {
            expanded += '$';
        }
    }
    return expanded;
}

QString preserveCase(const QString& replacement, const QString& matched) {
    bool hasLetter = false;
    bool allUpper = true;
    bool allLower = true;
    for (const QChar c : matched) {
        if (!c.isLetter()) {
            continue;
        }
        hasLetter = true;
        allUpper = allUpper && c.isUpper();
        allLower = allLower && c.isLower();
    }
    if (!hasLetter || replacement.isEmpty()) {
        return replacement;
    }
    if (allUpper) {
        return replacement.toUpper();  // CMDS → HLIB
    }
    if (allLower) {
        return replacement.toLower();  // cmds → hlib
    }
    if (matched.at(0).isUpper()) {
        return replacement.at(0).toUpper() + replacement.mid(1);  // Cmds → Hlib
    }
    return replacement.at(0).toLower() + replacement.mid(1);  // 先頭が小文字なら、先頭だけ小文字にする
}

}  // namespace hedit
