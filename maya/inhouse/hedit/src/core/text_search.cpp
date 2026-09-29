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
        result.error = "Invalid expression: " + regex.errorString();
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
        result.matches.append({int(match.capturedStart()), int(match.capturedLength())});
        if (replacementTemplate) {
            // 通常の検索では置換の文字列をそのまま使う。$記法は正規表現モードだけ。
            if (options.regex) {
                result.replacements.append(expandReplacement(*replacementTemplate, match, regex.captureCount()));
            } else {
                result.replacements.append(*replacementTemplate);
            }
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

}  // namespace hedit
