/** @file merge_ui.cpp @brief 結合前に日時・サイズと個別の上書き方針を確認する。 */
#include "browser_window.h"
#include "../core/file_operations.h"
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QHeaderView>
#include <QLabel>
#include <QLocale>
#include <QPushButton>
#include <QTreeWidget>
#include <QVBoxLayout>
namespace qpe {
bool BrowserWindow::confirmMerge(FileRequest& request) {
    QDialog dialog(this); dialog.setWindowTitle("Merge folders — review conflicts"); dialog.setObjectName("mergeConflicts"); dialog.resize(940, 520);
    QVBoxLayout layout(&dialog); QLabel info("Checking existing items…"); info.setWordWrap(true); layout.addWidget(&info);
    QTreeWidget rows; rows.setHeaderLabels({"Relative path", "Source size / modified", "Destination size / modified", "Action"});
    rows.header()->setSectionResizeMode(0, QHeaderView::Stretch); for (int col = 1; col < 4; ++col) rows.header()->setSectionResizeMode(col, QHeaderView::ResizeToContents); layout.addWidget(&rows);
    QDialogButtonBox buttons(QDialogButtonBox::Ok | QDialogButtonBox::Cancel); buttons.button(QDialogButtonBox::Ok)->setText("Merge"); buttons.button(QDialogButtonBox::Ok)->setEnabled(false); layout.addWidget(&buttons);
    FileJobs jobs; QJsonArray reviewed;
    connect(&jobs, &FileJobs::finished, &dialog, [&](const QJsonObject& value) {
        const auto result = fileResultFromJson(value); if (result.cancelled || !result.errors.isEmpty()) { info.setText(result.errors.join('\n')); return; }
        reviewed = result.extra["rows"].toArray();
        for (const auto& raw : reviewed) {
            const auto row = raw.toObject();
            const auto description = [&](const QString& prefix) { return (row[prefix + "Folder"].toBool() ? QString("Folder") : QLocale().formattedDataSize(qint64(row[prefix + "Size"].toDouble()))) + " / " + row[prefix + "Modified"].toString(); };
            auto* item = new QTreeWidgetItem(&rows, {row["relative"].toString(), description("source"), description("target")});
            item->setData(0, Qt::UserRole, row["source"]); item->setToolTip(0, row["source"].toString() + '\n' + row["target"].toString());
            auto* choice = new QComboBox; choice->addItem("Replace", "replace"); choice->addItem("Skip", "skip"); choice->addItem("Keep both", "rename"); rows.setItemWidget(item, 3, choice);
        }
        info.setText(QString("%1 conflicts. Destination-only files are kept. A whole-folder backup is retained for Undo.").arg(reviewed.size())); buttons.button(QDialogButtonBox::Ok)->setEnabled(true);
    });
    connect(&buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept); connect(&buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    jobs.enqueue({"mergeConflicts", request.paths, request.destination});
    if (dialog.exec() != QDialog::Accepted) { jobs.cancel(); return false; }
    QJsonObject choices{{"_requireReviewed", true}};
    for (int i = 0; i < rows.topLevelItemCount(); ++i) { auto* row = rows.topLevelItem(i); choices[row->data(0, Qt::UserRole).toString()] = qobject_cast<QComboBox*>(rows.itemWidget(row, 3))->currentData().toString(); }
    request.options["choices"] = choices; request.options["mergeReviewed"] = reviewed; return true;
}
}
