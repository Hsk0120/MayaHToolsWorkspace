/** @file diff_dialog.h
 * @brief 保存した内容と今の本文の違いを見る画面(File > Compare with saved)。
 * @details 変更のまとまりごとに、削除した行を赤、追加した行を緑の背景で並べる(前後3行を含む)。
 * 「Revert file」で保存した内容へ戻せる(Ctrl+Zで取り消せる)。
 */
#pragma once
#include "core/line_diff.h"
#include <QDialog>
#include <QString>

class QPlainTextEdit;

namespace hedit {

/** @brief 差分の画面(objectNameは``compareWithSaved``)。 */
class DiffDialog : public QDialog {
public:
    /** @brief 画面を作る。
     * @param parent 所有者(編集画面)。
     * @param title 見出し(ファイル名)。
     * @param saved 保存した内容。
     * @param current 今の本文。
     */
    DiffDialog(QWidget* parent, const QString& title, const QString& saved, const QString& current);

    /** @brief 差分の本文(テスト用)。 @return 表示している文字。 */
    QString diffText() const;

    /** @brief 差分を、表示する行の一覧にする(テストにも使う)。
     * @param saved 保存した内容。
     * @param current 今の本文。
     * @param context 変更の前後に出す行数。
     * @return 各行。先頭が``-``(削除)・``+``(追加)・``␣``(変わらない)・``@``(まとまりの見出し)。
     */
    static QStringList diffLinesText(const QString& saved, const QString& current, int context = 3);

private:
    QPlainTextEdit* view_;  ///< 差分の表示。所有者はこの画面。
};

}  // namespace hedit
