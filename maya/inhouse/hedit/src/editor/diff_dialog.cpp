/** @file diff_dialog.cpp
 * @brief DiffDialogの実装。
 */
#include "editor/diff_dialog.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QDialogButtonBox>
#include <QLabel>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QRegularExpression>
#include <QTextBlock>
#include <QVBoxLayout>

namespace hedit {

QStringList DiffDialog::diffLinesText(const QString& saved, const QString& current, int context) {
    QString before = saved;
    before.replace("\r\n", "\n");
    const QStringList beforeLines = before.split('\n');
    const QStringList afterLines = current.split('\n');
    const QList<LineChange> changes = diffLines(beforeLines, afterLines);
    QStringList lines;
    for (int i = 0; i < changes.size(); ++i) {
        // 近いまとまりは1つの見出しにまとめる。
        const LineChange& first = changes[i];
        int last = i;
        while (last + 1 < changes.size()
               && changes[last + 1].afterStart - (changes[last].afterStart + changes[last].afterCount) <= context * 2) {
            ++last;
        }
        const int startAfter = qMax(0, first.afterStart - context);
        const int startBefore = qMax(0, first.beforeStart - (first.afterStart - startAfter));
        lines.append(QString("@@ -%1 +%2 @@").arg(startBefore + 1).arg(startAfter + 1));
        int after = startAfter;
        for (int c = i; c <= last; ++c) {
            const LineChange& change = changes[c];
            for (; after < change.afterStart; ++after) {
                lines.append(" " + afterLines.value(after));
            }
            for (int b = 0; b < change.beforeCount; ++b) {
                lines.append("-" + beforeLines.value(change.beforeStart + b));
            }
            for (int a = 0; a < change.afterCount; ++a) {
                lines.append("+" + afterLines.value(change.afterStart + a));
            }
            after = change.afterStart + change.afterCount;
        }
        const int end = qMin(int(afterLines.size()), after + context);
        for (; after < end; ++after) {
            lines.append(" " + afterLines.value(after));
        }
        i = last;
    }
    return lines;
}

DiffDialog::DiffDialog(QWidget* parent, const QString& title, const QString& saved, const QString& current)
    : QDialog(parent) {
    setObjectName("compareWithSaved");
    setWindowTitle(title + " (saved) ↔ current");
    resize(scaled(900), scaled(600));
    view_ = new QPlainTextEdit(this);
    view_->setObjectName("diffView");
    view_->setReadOnly(true);
    view_->setLineWrapMode(QPlainTextEdit::NoWrap);
    QFont font("Consolas");
    font.setPixelSize(scaled(13));
    view_->setFont(font);
    view_->setStyleSheet(QString("QPlainTextEdit{background:%1;color:%2;}").arg(theme::kBackground, theme::kText));
    const QStringList lines = diffLinesText(saved, current);
    view_->setPlainText(lines.isEmpty() ? QString("No changes since the last save.") : lines.join('\n'));
    // 行の先頭の記号で背景を塗る(本文は変えない)。
    QList<QTextEdit::ExtraSelection> marks;
    for (QTextBlock block = view_->document()->begin(); block.isValid() && !lines.isEmpty(); block = block.next()) {
        const QString text = block.text();
        QColor color;
        if (text.startsWith('+')) {
            color = QColor(theme::kChangeAdded);
            color.setAlpha(90);
        } else if (text.startsWith('-')) {
            color = QColor(theme::kChangeDeleted);
            color.setAlpha(80);
        } else if (text.startsWith("@@")) {
            color = QColor(theme::kPopupBackground);
        } else {
            continue;
        }
        QTextEdit::ExtraSelection mark;
        mark.cursor = QTextCursor(block);
        mark.format.setBackground(color);
        mark.format.setProperty(QTextFormat::FullWidthSelection, true);
        marks.append(mark);
    }
    view_->setExtraSelections(marks);

    auto summary = new QLabel(this);
    const int added = lines.filter(QRegularExpression("^\\+")).size();
    const int removed = lines.filter(QRegularExpression("^-")).size();
    summary->setText(QString("%1 added, %2 removed").arg(added).arg(removed));
    auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, this);
    QPushButton* revert = buttons->addButton("Revert file", QDialogButtonBox::DestructiveRole);
    revert->setObjectName("revertFile");
    revert->setEnabled(!lines.isEmpty());
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(revert, &QPushButton::clicked, this, [this] { done(2); });  // 2 = 保存した内容へ戻す。
    auto layout = new QVBoxLayout(this);
    layout->addWidget(summary);
    layout->addWidget(view_);
    layout->addWidget(buttons);
}

QString DiffDialog::diffText() const {
    return view_->toPlainText();
}

}  // namespace hedit
