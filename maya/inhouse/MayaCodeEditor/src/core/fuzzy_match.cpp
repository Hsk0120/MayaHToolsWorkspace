/** @file fuzzy_match.cpp
 * @brief 補完の候補の絞り込みと並べ替えの実装。
 */
#include "core/fuzzy_match.h"
#include <QVector>
#include <algorithm>

namespace mce {
namespace {

/// 名前の先頭から続けて一致したとき(前方一致)の加点。前方一致の候補を必ず上に並べるため大きくする。
constexpr int kPrefixBonus = 100;
/// 大文字小文字まで同じ前方一致の加点。
constexpr int kExactCaseBonus = 10;
/// 単語の頭(先頭・``_``の後・小文字の後の大文字)での一致の加点。
constexpr int kWordStartBonus = 8;
/// 1文字目が名前の先頭で一致したときの加点(``ls`` で ``listSets`` を ``dR_lockSelTGL`` より上にする)。
constexpr int kNameStartBonus = 6;
/// 前の文字に続く一致の加点。
constexpr int kConsecutiveBonus = 6;
/// 大文字小文字まで同じ文字の加点。
constexpr int kSameCaseBonus = 1;

/** @brief 名前のi文字目が単語の頭か。 @param word 名前。 @param i 位置。 @return 先頭・``_``や``.``の後・小文字の後の大文字ならtrue。 */
bool isWordStart(QStringView word, int i) {
    if (i == 0) {
        return true;
    }
    const QChar previous = word[i - 1];
    const QChar current = word[i];
    if (current == '_') {
        return false;
    }
    if (previous == '_' || previous == '.') {
        return true;
    }
    return current.isUpper() && previous.isLower();
}

/** @brief start文字目から1文字目を合わせたときの度合い(残りは左から順に探す)。
 * @param pattern 入力。
 * @param word 名前。
 * @param start patternの1文字目に合わせる位置。
 * @return 一致しなければ-1。
 */
int scoreFrom(QStringView pattern, QStringView word, int start) {
    int score = 0;
    int previous = -2;
    int position = start;
    for (int i = 0; i < pattern.size(); ++i) {
        const QChar wanted = pattern[i].toLower();
        // 2文字目以降は、続きの文字か、次の単語の頭を優先して探す(``gat`` → ``g``et``At``tr)。
        int found = -1;
        if (i == 0) {
            found = start;
        } else if (position < word.size() && word[position].toLower() == wanted) {
            found = position;
        } else {
            int fallback = -1;
            for (int j = position; j < word.size(); ++j) {
                if (word[j].toLower() != wanted) {
                    continue;
                }
                if (isWordStart(word, j)) {
                    found = j;
                    break;
                }
                if (fallback < 0) {
                    fallback = j;
                }
            }
            if (found < 0) {
                found = fallback;
            }
        }
        if (found < 0) {
            return -1;
        }
        score += 1;
        if (isWordStart(word, found)) {
            score += kWordStartBonus;
        }
        if (i == 0 && found == 0) {
            score += kNameStartBonus;
        }
        if (found == previous + 1) {
            score += kConsecutiveBonus;
        }
        if (word[found] == pattern[i]) {
            score += kSameCaseBonus;
        }
        // 離れた文字の一致より短い語境界の一致を優先する(gJO → getJointOrient)。
        if (previous >= 0) score -= qMin(3, found - previous - 1);
        previous = found;
        position = found + 1;
    }
    return score;
}

}  // namespace

int fuzzyScore(QStringView pattern, QStringView word) {
    if (pattern.isEmpty()) {
        return 0;
    }
    if (pattern.size() > word.size()) {
        return -1;
    }
    if (word.startsWith(pattern, Qt::CaseInsensitive)) {
        // 前方一致: 連続した一致と同じ点に、前方一致の加点を足す。
        int score = kPrefixBonus + scoreFrom(pattern, word, 0);
        if (word.startsWith(pattern, Qt::CaseSensitive)) {
            score += kExactCaseBonus;
        }
        return score;
    }
    // 1文字目は、名前の先頭か単語の頭でだけ合わせる。合わせ方が複数あれば、度合いの高いほう。
    const QChar first = pattern[0].toLower();
    int best = -1;
    for (int start = 0; start < word.size(); ++start) {
        if (word[start].toLower() == first && isWordStart(word, start)) {
            best = std::max(best, scoreFrom(pattern, word, start));
        }
    }
    return best;
}

bool rankedBefore(int leftScore, const QString& left, int rightScore, const QString& right) {
    if (leftScore != rightScore) {
        return leftScore > rightScore;
    }
    const int compared = left.compare(right, Qt::CaseInsensitive);
    if (compared != 0) {
        return compared < 0;
    }
    return left < right;
}

QList<CompletionItem> rankCompletions(const QList<CompletionItem>& items, const QString& pattern) {
    struct Ranked {
        int score;
        int index;
    };
    QVector<Ranked> ranked;
    ranked.reserve(items.size());
    for (int i = 0; i < items.size(); ++i) {
        QString name = items[i].filterText.isEmpty() ? items[i].name : items[i].filterText;
        if (name.size() >= 2 && (name.front() == '\'' || name.front() == '"') && name.back() == name.front())
            name = name.mid(1, name.size() - 2);
        int score = fuzzyScore(pattern, name);
        if (score < 0) continue;
        // 内部名は明示的に_から探す場合だけ通常の順位にする。
        if (score >= 0 && !pattern.startsWith('_') && name.startsWith('_')) score -= 1000;
        ranked.append({score, i});
    }
    // 同点ならサーバーの順位、未提供なら従来の名前順を使う。
    std::stable_sort(ranked.begin(), ranked.end(), [&items](const Ranked& a, const Ranked& b) {
        if (a.score == b.score) {
            const auto& left = items[a.index]; const auto& right = items[b.index];
            const QString leftKey = left.sortText.isEmpty() ? left.name.toCaseFolded() : left.sortText;
            const QString rightKey = right.sortText.isEmpty() ? right.name.toCaseFolded() : right.sortText;
            if (leftKey != rightKey) return leftKey < rightKey;
        }
        return rankedBefore(a.score, items[a.index].name, b.score, items[b.index].name);
    });
    QList<CompletionItem> result;
    result.reserve(ranked.size());
    for (const Ranked& entry : ranked) {
        result.append(items[entry.index]);
    }
    return result;
}

}  // namespace mce
