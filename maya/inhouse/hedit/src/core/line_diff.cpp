/** @file line_diff.cpp
 * @brief 行単位の差分の実装。
 * @details 保存後の編集のたびに(300msごとに)呼ばれる。共通の先頭と末尾を除いた残りを、次の順で比べる。
 * 1. 行を整数の番号にする(同じ文字列の行は同じ番号)。以後は文字列ではなく番号を比べる。
 * 2. Myersの差分のアルゴリズム(O((N+M)D)。Dは違う行の数)で、変更の少ない場合を速く求める。
 * 3. 違う行が多くて2.が予算を超えたら、以前と同じ最長共通部分列(LCS)の表で求める(表の大きさに上限がある)。
 * 4. それも上限を超えたら、残り全体を1つの変更として扱う(画面を止めないため)。
 * 2.と3.は同じ結果になる: どちらも「先頭から、同じ行は対応させ、違う行では追加(今の本文の行)を先に、
 * 最短の差分になる範囲で選ぶ」という同じ規則で、1通りの対応を選ぶ。
 */
#include "core/line_diff.h"
#include <QHash>
#include <QVector>
#include <climits>

namespace hedit {
namespace {

/// LCSの表の大きさの上限(行数の積)。これを超える部分は1つの変更として扱う。Myersの計算量の予算にも使う。
constexpr qint64 kMaximumCells = 2500000;

/** @brief 差分を求める範囲。行は番号(同じ文字列なら同じ番号)で表す。 */
struct DiffInput {
    QVector<int> before;  ///< 保存した内容の行(共通の先頭・末尾を除いた部分)。
    QVector<int> after;   ///< 今の本文の行。
    int prefix = 0;       ///< 除いた共通の先頭の行数(結果の行番号に足す)。
};

/** @brief 対応の道筋から、変更のまとまりを作る。
 * @details 道筋は先頭から1歩ずつ進む。同じ行の対応(斜め)で、それまでの変更のまとまりを閉じる。
 */
class ChangeBuilder {
public:
    /** @brief 結果の追加先を受け取る。 @param changes 追加先。 @param prefix 行番号に足す数。 */
    ChangeBuilder(QList<LineChange>* changes, int prefix) : changes_(changes), prefix_(prefix) {}

    /** @brief 同じ行の対応。 */
    void match() { flush(); }

    /** @brief 今の本文の行の追加。 @param i 保存した内容の位置。 @param j 今の本文の位置。 */
    void insert(int i, int j) {
        begin(i, j);
        ++current_.afterCount;
    }

    /** @brief 保存した内容の行の削除。 @param i 保存した内容の位置。 @param j 今の本文の位置。 */
    void remove(int i, int j) {
        begin(i, j);
        ++current_.beforeCount;
    }

    /** @brief 途中のまとまりを結果へ入れる。 */
    void flush() {
        if (current_.beforeCount > 0 || current_.afterCount > 0) {
            changes_->append(current_);
        }
        current_ = {-1, 0, -1, 0};
    }

private:
    /** @brief まとまりの始まりを記録する。 @param i 保存した内容の位置。 @param j 今の本文の位置。 */
    void begin(int i, int j) {
        if (current_.beforeStart < 0) {
            current_.beforeStart = prefix_ + i;
            current_.afterStart = prefix_ + j;
        }
    }

    QList<LineChange>* changes_;      ///< 結果の追加先。
    int prefix_;                      ///< 行番号に足す数。
    LineChange current_{-1, 0, -1, 0};  ///< 作っている途中のまとまり。
};

/** @brief Myersのアルゴリズムで差分を求める。
 * @param input 比べる行(どちらも1行以上)。
 * @param maximumDistance 違う行の数(追加と削除の数の合計)の上限。
 * @param changes 結果の追加先。
 * @return 上限以内で求められればtrue。超えたらfalse(changesは変えない)。
 * @details 後ろから、各「残りの距離d」について、各対角線k(=i-j)で残りの距離がd以下になる最も前の位置
 * V_d[k]を求める(Myersの方法を後ろ向きに行う)。対角線の上では、後ろへ進むほど残りの距離は増えないので、
 * 「位置(i,j)から最後までの距離がd以下」は「V_d[i-j] <= i」と同じになる。これを使い、先頭から
 * LCSの表と同じ規則(同じ行は対応させ、違えば追加を優先し、最短になる方へ進む)で1歩ずつたどる。
 * 記録の大きさは(D+1)(D+2)/2個の整数(Dは違う行の数)。
 */
bool myersDiff(const DiffInput& input, int maximumDistance, QList<LineChange>* changes) {
    const QVector<int>& a = input.before;
    const QVector<int>& b = input.after;
    const int n = int(a.size());
    const int m = int(b.size());
    const int target = n - m;  // 終わりの位置(n, m)の対角線。
    // V_d[k]は history[d][(k - (target - d)) / 2] に入れる。対角線はtarget-dからtarget+dまで2つおき。
    QVector<QVector<int>> history;
    auto at = [&history, target](int d, int k) -> int {
        const QVector<int>& row = history[d];
        const int index = (k - (target - d)) / 2;
        return row[index];
    };
    // 対角線kの、位置xから後ろ向きに同じ行が続く限り戻る。
    auto slide = [&a, &b](int x, int k) {
        int y = x - k;
        while (x > 0 && y > 0 && a[x - 1] == b[y - 1]) {
            --x;
            --y;
        }
        return x;
    };
    int distance = -1;
    for (int d = 0; d <= maximumDistance; ++d) {
        QVector<int> row(d + 1, INT_MAX);  // INT_MAXは「その対角線には無い」。
        for (int index = 0; index <= d; ++index) {
            const int k = target - d + 2 * index;
            if (k < -m || k > n) {
                continue;  // 本文の外の対角線。
            }
            int x = INT_MAX;
            if (d == 0) {
                x = n;
            } else {
                // 対角線k+1の位置x1から、1つ前の行の削除で来る: (x1-1, x1-1-k)。
                if (k + 1 <= target + (d - 1)) {
                    const int x1 = at(d - 1, k + 1);
                    if (x1 != INT_MAX && x1 - 1 >= 0 && x1 - 1 - k >= 0) {
                        x = qMin(x, x1 - 1);
                    }
                }
                // 対角線k-1の位置x2から、1つ前の行の追加で来る: (x2, x2-k)。
                if (k - 1 >= target - (d - 1)) {
                    const int x2 = at(d - 1, k - 1);
                    if (x2 != INT_MAX && x2 - k >= 0) {
                        x = qMin(x, x2);
                    }
                }
            }
            if (x == INT_MAX) {
                continue;
            }
            row[index] = slide(x, k);
        }
        history.append(row);
        const int origin = (0 - (target - d));  // 対角線0の位置(偶奇が合う場合だけ)。
        if (origin >= 0 && origin <= 2 * d && origin % 2 == 0 && history[d][origin / 2] == 0) {
            distance = d;
            break;
        }
    }
    if (distance < 0) {
        return false;
    }
    // 先頭からたどる。rは今の位置から最後までの距離。
    ChangeBuilder builder(changes, input.prefix);
    int i = 0;
    int j = 0;
    int r = distance;
    // 位置(x, y)から最後までの距離がd以下か。
    auto within = [&at, target](int x, int y, int d) {
        const int k = x - y;
        if (d < 0 || k < target - d || k > target + d || (k - (target - d)) % 2 != 0) {
            return false;
        }
        const int v = at(d, k);
        return v != INT_MAX && v <= x;
    };
    while (i < n || j < m) {
        if (i < n && j < m && a[i] == b[j]) {
            builder.match();
            ++i;
            ++j;
        } else if (j < m && (i >= n || within(i, j + 1, r - 1))) {
            builder.insert(i, j);
            ++j;
            --r;
        } else {
            builder.remove(i, j);
            ++i;
            --r;
        }
    }
    builder.flush();
    return true;
}

/** @brief 最長共通部分列の表で差分を求める(以前の方法。表の大きさに上限がある)。
 * @param input 比べる行。
 * @param changes 結果の追加先。
 */
void tableDiff(const DiffInput& input, QList<LineChange>* changes) {
    const QVector<int>& a = input.before;
    const QVector<int>& b = input.after;
    const int n = int(a.size());
    const int m = int(b.size());
    // table[i][j] = a[i..]とb[j..]の最長共通部分列の長さ(後ろから求める)。
    QVector<int> table((n + 1) * (m + 1), 0);
    auto at = [&table, m](int i, int j) -> int& { return table[i * (m + 1) + j]; };
    for (int i = n - 1; i >= 0; --i) {
        for (int j = m - 1; j >= 0; --j) {
            at(i, j) = a[i] == b[j] ? at(i + 1, j + 1) + 1 : qMax(at(i + 1, j), at(i, j + 1));
        }
    }
    // 前からたどり、一致しない行を連続したまとまりにする。
    ChangeBuilder builder(changes, input.prefix);
    int i = 0;
    int j = 0;
    while (i < n || j < m) {
        if (i < n && j < m && a[i] == b[j]) {
            builder.match();
            ++i;
            ++j;
        } else if (j < m && (i >= n || at(i, j + 1) >= at(i + 1, j))) {
            builder.insert(i, j);
            ++j;
        } else {
            builder.remove(i, j);
            ++i;
        }
    }
    builder.flush();
}

}  // namespace

QList<LineChange> diffLines(const QStringList& before, const QStringList& after) {
    QList<LineChange> changes;
    // 共通の先頭と末尾を除く。
    int prefix = 0;
    const int shorter = int(qMin(before.size(), after.size()));
    while (prefix < shorter && before[prefix] == after[prefix]) {
        ++prefix;
    }
    int suffix = 0;
    while (suffix < shorter - prefix && before[before.size() - 1 - suffix] == after[after.size() - 1 - suffix]) {
        ++suffix;
    }
    const int n = int(before.size()) - prefix - suffix;
    const int m = int(after.size()) - prefix - suffix;
    if (n == 0 && m == 0) {
        return changes;
    }
    if (n == 0 || m == 0) {
        changes.append({prefix, n, prefix, m});
        return changes;
    }
    // 行を番号にする(同じ文字列は同じ番号)。以後の比較は整数で行う。
    DiffInput input;
    input.prefix = prefix;
    input.before.reserve(n);
    input.after.reserve(m);
    QHash<QString, int> ids;
    ids.reserve(n + m);
    auto idOf = [&ids](const QString& line) {
        const auto found = ids.constFind(line);
        if (found != ids.constEnd()) {
            return found.value();
        }
        const int id = int(ids.size());
        ids.insert(line, id);
        return id;
    };
    for (int i = 0; i < n; ++i) {
        input.before.append(idOf(before[prefix + i]));
    }
    for (int j = 0; j < m; ++j) {
        input.after.append(idOf(after[prefix + j]));
    }
    // Myersの予算: 計算量(N+M)Dと記録の大きさD^2/2が、LCSの表の上限と同じくらいに収まる違いの数まで。
    const qint64 budget = kMaximumCells / qint64(n + m);
    const int maximumDistance = int(qBound(qint64(16), budget, qint64(2048)));
    if (myersDiff(input, qMin(maximumDistance, n + m), &changes)) {
        return changes;
    }
    if (qint64(n + 1) * (m + 1) > kMaximumCells) {
        changes.append({prefix, n, prefix, m});
        return changes;
    }
    tableDiff(input, &changes);
    return changes;
}

}  // namespace hedit
