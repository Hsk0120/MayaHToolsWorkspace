/** @file search_ui.cpp @brief 検索を専用キューと世代で分離し、途中結果を表示する。 */
#include "browser_window.h"
#include "../core/file_operations.h"
#include <QDialog>
#include <QCheckBox>
#include <QDir>
#include <QFileInfo>
#include <QHeaderView>
#include <QLabel>
#include <QLocale>
#include <QPushButton>
#include <QSet>
#include <QTimer>
#include <QTreeWidget>
#include <QUuid>
#include <QVBoxLayout>
#include <memory>
namespace qpe {
void BrowserWindow::streamingSearch(const FileRequest& request) {
    auto* dialog = new QDialog(this); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setWindowTitle("Search results"); dialog->setObjectName("qpeSearchResults"); dialog->resize(900, 550);
    auto* layout = new QVBoxLayout(dialog); auto* info = new QLabel; info->setWordWrap(true); layout->addWidget(info);
    auto* list = new QTreeWidget; list->setHeaderLabels({"Name", "Folder", "Size", "Matches"}); list->setSelectionMode(QAbstractItemView::ExtendedSelection); list->setColumnWidth(0, 220); list->header()->setSectionResizeMode(1, QHeaderView::Stretch); layout->addWidget(list);
    auto* controls = new QHBoxLayout; layout->addLayout(controls); auto* start = new QPushButton("Search again"); auto* stop = new QPushButton("Stop"); stop->setObjectName("searchStop"); auto* live = new QCheckBox("Refresh every 10 seconds"); live->setChecked(request.options["live"].toBool()); controls->addWidget(start); controls->addWidget(stop); controls->addWidget(live);
    auto* jobs = new FileJobs(dialog); auto* timer = new QTimer(dialog); timer->setInterval(10000);
    auto token = std::make_shared<QString>(); auto seen = std::make_shared<QSet<QString>>();
    const auto append = [list, info, token, seen](const QJsonObject& value) {
        if (value["token"].toString() != *token) return;
        for (const auto& data : value["rows"].toArray()) { const auto row = data.toObject(); const auto path = row["path"].toString(); if (seen->contains(path.toCaseFolded())) continue; seen->insert(path.toCaseFolded());
            auto* item = new QTreeWidgetItem(list, {QFileInfo(path).fileName(), QFileInfo(path).absolutePath(), QLocale().formattedDataSize(qint64(row["size"].toDouble())), row["state"].toString()}); item->setData(0, Qt::UserRole + 1, path); item->setToolTip(1, path);
            QStringList lines; for (const auto& hit : row["matches"].toArray()) lines.append(hit.toString()); item->setToolTip(0, path + '\n' + lines.join('\n'));
        }
        info->setText(QString("%1 results — searching…").arg(list->topLevelItemCount()));
    };
    const auto run = [=] {
        stop->setEnabled(true); jobs->cancel(); *token = QUuid::createUuid().toString(); seen->clear(); list->clear(); info->setText("Searching…");
        auto next = request; next.options["token"] = *token; jobs->enqueue(next); if (live->isChecked()) timer->start();
    };
    connect(jobs, &FileJobs::partial, dialog, append);
    connect(jobs, &FileJobs::finished, dialog, [=](const QJsonObject& value) {
        const auto result = fileResultFromJson(value); if (result.extra["token"].toString() != *token) return; append(result.extra); stop->setEnabled(false);
        info->setText(QString("%1 results — %2").arg(list->topLevelItemCount()).arg(result.cancelled ? "Stopped" : result.errors.isEmpty() ? "Completed" : "Incomplete") + '\n' + (result.errors + result.warnings).join('\n'));
    });
    connect(start, &QPushButton::clicked, dialog, run);
    connect(stop, &QPushButton::clicked, dialog, [=] { timer->stop(); live->setChecked(false); jobs->cancel(); info->setText("Stopping…"); });
    connect(live, &QCheckBox::toggled, timer, [timer](bool enabled) { if (enabled) timer->start(); else timer->stop(); });
    connect(timer, &QTimer::timeout, dialog, [=] { if (!jobs->busy()) run(); });
    connect(dialog, &QDialog::finished, jobs, &FileJobs::cancel);
    connect(list, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item) { perform("reveal", {item->data(0, Qt::UserRole + 1).toString()}); });
    list->setContextMenuPolicy(Qt::CustomContextMenu); connect(list, &QTreeWidget::customContextMenuRequested, this, [this, list](const QPoint& point) { contextMenu(list, point, currentPath()); });
    dialog->show(); run();
}
}
