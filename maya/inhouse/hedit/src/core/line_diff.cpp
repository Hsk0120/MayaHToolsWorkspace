/** @file line_diff.cpp
 * @brief 行単位の差分の実装。
 */
#include "core/line_diff.h"
#include <QVector>

namespace hedit {
namespace {

/// LCSの表の大きさの上限(行数の積)。これを超える部分は1つの変更として扱う。
constexpr qint64 kMaximumCells = 2500000;

}  // namespace

QList<LineChange> diffLines(const QStringList& before, const QStringList& after) {
    QList<LineChange> changes;
    // 共通の先頭と末尾を除く。
    int prefix = 0;
    const int shorter = qMin(before.size(), after.size());
    while (prefix < shorter && before[prefix] == after[prefix]) {
        ++prefix;
    }
    int suffix = 0;
    while (suffix < shorter - prefix && before[before.size() - 1 - suffix] == after[after.size() - 1 - suffix]) {
        ++suffix;
    }
    const int n = before.size() - prefix - suffix;
    const int m = after.size() - prefix - suffix;
    if (n == 0 && m == 0) {
        return changes;
    }
    if (n == 0 || m == 0 || qint64(n + 1) * (m + 1) > kMaximumCells) {
        changes.append({prefix, n, prefix, m});
        return changes;
    }
    // table[i][j] = before[prefix+i..]とafter[prefix+j..]の最長共通部分列の長さ(後ろから求める)。
    QVector<int> table((n + 1) * (m + 1), 0);
    auto at = [&table, m](int i, int j) -> int& { return table[i * (m + 1) + j]; };
    for (int i = n - 1; i >= 0; --i) {
        for (int j = m - 1; j >= 0; --j) {
            at(i, j) = before[prefix + i] == after[prefix + j] ? at(i + 1, j + 1) + 1 : qMax(at(i + 1, j), at(i, j + 1));
        }
    }
    // 前からたどり、一致しない行を連続したまとまりにする。
    int i = 0;
    int j = 0;
    LineChange current{-1, 0, -1, 0};
    auto flush = [&changes, &current] {
        if (current.beforeCount > 0 || current.afterCount > 0) {
            changes.append(current);
        }
        current = {-1, 0, -1, 0};
    };
    auto begin = [&current, prefix, &i, &j] {
        if (current.beforeStart < 0) {
            current.beforeStart = prefix + i;
            current.afterStart = prefix + j;
        }
    };
    while (i < n || j < m) {
        if (i < n && j < m && before[prefix + i] == after[prefix + j]) {
            flush();
            ++i;
            ++j;
        } else if (j < m && (i >= n || at(i, j + 1) >= at(i + 1, j))) {
            begin();
            ++current.afterCount;
            ++j;
        } else {
            begin();
            ++current.beforeCount;
            ++i;
        }
    }
    flush();
    return changes;
}

}  // namespace hedit
