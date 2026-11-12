/** @file merge_ui.cpp @brief コピー・移動先の同名項目を確認する。 */
#include "ui_language.h"
#include "browser_window.h"
#include "../core/file_operations.h"
#include <QComboBox>
#include <QCommandLinkButton>
#include <QDialog>
#include <QDialogButtonBox>
#include <QEventLoop>
#include <QHeaderView>
#include <QLabel>
#include <QLocale>
#include <QPointer>
#include <QProgressDialog>
#include <QPushButton>
#include <QScopeGuard>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <algorithm>

namespace qpe {
namespace {
/** @brief ファイルとフォルダーの異種競合を識別する。 @param row 競合情報。 @return 種類が異なるか。 */
bool differentKinds(const QJsonObject& row) {
    return row["sourceFolder"].toBool() != row["targetFolder"].toBool();
}

/** @brief 転送先と元の情報を比較し、各項目の処理を指定する。
 * @param owner 親ウィンドウ。 @param reviewed 確認済みの競合。 @param choices 確定する処理。
 * @return 個別の選択を確定したか。
 */
bool reviewItems(QWidget* owner, const QJsonArray& reviewed, QJsonObject& choices) {
    QPointer<QDialog> dialog(new QDialog(owner));
    const auto cleanup = qScopeGuard([&] { delete dialog.data(); });
    dialog->setWindowTitle(uiText("Choose which files to keep"));
    dialog->setObjectName("mergeConflicts");
    dialog->resize(760, 400);
    auto* layout = new QVBoxLayout(dialog);
    auto* rows = new QTreeWidget(dialog);
    rows->setRootIsDecorated(false);
    rows->setHeaderLabels({uiText("Relative path"), uiText("Source size / modified"), uiText("Destination size / modified"), uiText("Action")});
    rows->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    for (int col = 1; col < 4; ++col) rows->header()->setSectionResizeMode(col, QHeaderView::ResizeToContents);
    layout->addWidget(rows);
    for (const auto& raw : reviewed) {
        const auto row = raw.toObject();
        const auto description = [&](const QString& prefix) {
            const auto size = row[prefix + "Folder"].toBool() ? uiText("Folder")
                : uiLocale().formattedDataSize(qint64(row[prefix + "Size"].toDouble()));
            return size + " / " + row[prefix + "Modified"].toString();
        };
        auto* item = new QTreeWidgetItem(rows, {row["relative"].toString(), description("source"), description("target")});
        item->setData(0, Qt::UserRole, row["source"]);
        item->setToolTip(0, row["source"].toString() + '\n' + row["target"].toString());
        auto* choice = new QComboBox;
        if (!differentKinds(row)) choice->addItem(uiText("Replace"), "replace");
        choice->addItem(uiText("Skip"), "skip");
        choice->addItem(uiText("Keep both"), "rename");
        rows->setItemWidget(item, 3, choice);
    }
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, dialog);
    uiButtons(buttons);
    layout->addWidget(buttons);
    QObject::connect(buttons, &QDialogButtonBox::accepted, dialog.data(), &QDialog::accept);
    QObject::connect(buttons, &QDialogButtonBox::rejected, dialog.data(), &QDialog::reject);
    if (dialog->exec() != QDialog::Accepted || !dialog) return false;
    for (int i = 0; i < rows->topLevelItemCount(); ++i) {
        auto* row = rows->topLevelItem(i);
        choices[row->data(0, Qt::UserRole).toString()] = qobject_cast<QComboBox*>(rows->itemWidget(row, 3))->currentData().toString();
    }
    return true;
}
}

bool BrowserWindow::confirmTransfer(FileRequest& request) {
    if (request.paths.isEmpty()) return false;
    // Mayaの終了時に所有ウィジェットが先に消えても、ローカルの待機を抜ける。
    const bool wasVisible = isVisible();
    QPointer<BrowserWindow> owner(this);
    QPointer<QProgressDialog> checking(new QProgressDialog(uiText("Checking existing items…"), uiText("Cancel"), 0, 0, this));
    const auto cleanup = qScopeGuard([&] { delete checking.data(); });
    checking->setWindowTitle(uiText("File transfer"));
    checking->setWindowModality(Qt::WindowModal);
    checking->setMinimumDuration(350);
    checking->setAutoReset(false);
    checking->setAutoClose(false);
    FileJobs jobs;
    QEventLoop wait;
    FileResult preview;
    connect(checking.data(), &QProgressDialog::canceled, &wait, &QEventLoop::quit);
    connect(checking.data(), &QObject::destroyed, &wait, &QEventLoop::quit);
    connect(&jobs, &FileJobs::finished, &wait, [&](const QJsonObject& value) {
        preview = fileResultFromJson(value);
        wait.quit();
    });
    jobs.enqueue({"mergeConflicts", request.paths, request.destination});
    checking->setValue(0);
    wait.exec();
    if (!checking || !owner || (wasVisible && !owner->isVisible()) || checking->wasCanceled() || preview.cancelled) return false;
    checking->hide();
    if (!preview.errors.isEmpty()) {
        UiMessageBox::warning(this, uiText("File transfer"), preview.errors.join('\n'));
        return false;
    }
    const auto reviewed = preview.extra["rows"].toArray();
    QJsonObject choices{{"_requireReviewed", true}};
    if (!reviewed.isEmpty()) {
        const bool different = std::any_of(reviewed.constBegin(), reviewed.constEnd(), [](const QJsonValue& row) {
            return differentKinds(row.toObject());
        });
        QPointer<QDialog> dialog(new QDialog(this));
        const auto cleanupDialog = qScopeGuard([&] { delete dialog.data(); });
        dialog->setWindowTitle(uiText("Replace or skip files"));
        dialog->setObjectName("pasteConflict");
        dialog->setMinimumWidth(440);
        auto* layout = new QVBoxLayout(dialog);
        const auto first = reviewed.first().toObject();
        auto* description = new QLabel(different ? uiText("Some items have the same name but different types.")
            : reviewed.size() == 1 ? uiText("The destination already has a file named %1.").arg(first["relative"].toString())
            : uiText("The destination already has %1 files with the same names.").arg(reviewed.size()), dialog);
        description->setWordWrap(true);
        description->setTextFormat(Qt::PlainText);
        layout->addWidget(description);

        auto* replace = new QCommandLinkButton(uiText("Replace the files in the destination"), dialog);
        auto* skip = new QCommandLinkButton(uiText("Skip these files"), dialog);
        auto* compare = new QCommandLinkButton(uiText("Choose which files to keep"), dialog);
        replace->setObjectName("replaceTransfer");
        skip->setObjectName("skipTransfer");
        compare->setObjectName("compareTransfer");
        replace->setEnabled(!different);
        layout->addWidget(replace);
        layout->addWidget(skip);
        layout->addWidget(compare);
        (different ? compare : replace)->setDefault(true);
        (different ? compare : replace)->setFocus(Qt::OtherFocusReason);
        connect(replace, &QPushButton::clicked, dialog.data(), [&] { dialog->done(1); });
        connect(skip, &QPushButton::clicked, dialog.data(), [&] { dialog->done(2); });
        connect(compare, &QPushButton::clicked, dialog.data(), [&] { dialog->done(3); });
        const int decision = dialog->exec();
        if (!owner || !dialog || decision == QDialog::Rejected) return false;
        if (decision == 3) {
            if (!reviewItems(this, reviewed, choices)) return false;
        } else {
            const auto policy = decision == 1 ? "replace" : "skip";
            for (const auto& raw : reviewed) choices[raw.toObject()["source"].toString()] = policy;
        }
    }
    request.conflict = "merge";
    request.options["choices"] = choices;
    request.options["mergeReviewed"] = reviewed;
    return true;
}
}
