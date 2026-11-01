/** @file organizer_ui.cpp @brief ZIP・ジョブ・履歴・OS操作を必要時のダイアログへ分離する。 */
#include "browser_window.h"
#include "../core/file_operations.h"
#include "../core/settings_store.h"
#include "../core/legacy_history.h"
#include <QAction>
#include <QUuid>
#include <QCryptographicHash>
#include <QDateTime>
#include <QApplication>
#include <QDialog>
#include <QDir>
#include <QFileInfo>
#include <QFileDialog>
#include <QFormLayout>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLocale>
#include <QGridLayout>
#include <QMenu>
#include <QMessageBox>
#include <QProcess>
#include <QPushButton>
#include <QTextEdit>
#include <QTimer>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <QDesktopServices>
#include <QUrl>
#include <QSet>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
namespace qpe {
WId shellDialogOwner(QWidget* widget) {
    if (!widget) throw std::invalid_argument("A dialog owner is required");
    // 子のwinId()はMayaのドック親も連鎖的にネイティブ化する。所有する最上位だけを参照する。
    return widget->window()->winId();
}
void BrowserWindow::organizerMenu(QMenu* menu) {
    auto* searchMenu = menu->findChild<QMenu*>("toolsSearch");
    auto* view = menu->findChild<QMenu*>("toolsView");
    auto* sets = menu->findChild<QMenu*>("toolsTabs");
    auto* transfer = menu->findChild<QMenu*>("toolsTransfers");
    auto* settings = menu->findChild<QMenu*>("toolsSettings");
    auto* saved = searchMenu->addMenu("Saved searches");
    const auto searches = readSettings()["savedSearches"].toObject();
    for (const auto& name : searches.keys()) saved->addAction(name, this, [this, name] { perform("savedSearch:" + name); });
    saved->setEnabled(!searches.isEmpty());
    auto* area = view->addMenu("Browser layout");
    for (const auto& pair : QList<QPair<QString, QString>>{{"Columns first", "columns"}, {"Balanced", "balanced"}, {"Files first", "files"}, {"Custom", "custom"}})
        area->addAction(pair.first, this, [this, mode = pair.second] { perform("area:" + mode); });
    view->addAction("Second file pane", this, [this] { perform("secondPane"); });
    sets->addAction("Restore previous tab set", this, [this] { perform("restoreTabSet"); });
    auto* archives = searchMenu->addMenu("ZIP archives");
    for (const auto& pair : QList<QPair<QString, QString>>{{"Create ZIP…", "createZip"}, {"Browse ZIP…", "browseZip"}, {"Extract ZIP…", "extractZip"}})
        archives->addAction(pair.first, this, [this, action = pair.second] { perform(action, selectedPaths(), currentPath()); });
    transfer->addAction("File jobs / retry…", this, [this] { perform("jobs"); });
    transfer->addAction("Resume unfinished transfers…", this, [this] { perform("jobs"); });
    transfer->addAction("File operation history…", this, [this] { perform("history"); });
    searchMenu->addAction("Browse tags / collections…", this, [this] { perform("browseLabels"); });
    auto* configuration = settings->addMenu("External applications");
    for (const auto& pair : QList<QPair<QString, QString>>{{"FFmpeg…", "ffmpegExecutable"}, {"Everything CLI…", "everythingExecutable"}, {"File Locksmith CLI…", "fileLocksmithExecutable"}})
        configuration->addAction(pair.first, this, [this, key = pair.second] { const auto path = QFileDialog::getOpenFileName(this, "Choose executable", {}, "Application (*.exe)"); if (!path.isEmpty()) { try { writeSettings({{key, path}}); } catch (const std::exception& e) { QMessageBox::warning(this, "Settings", QString::fromUtf8(e.what())); } } });
    if (host_.maya) {
        auto* maya = menu->addMenu("Maya");
        for (const auto& pair : QList<QPair<QString, QString>>{{"New Scene", "new"}, {"Save Scene", "save"}, {"Save Scene As…", "saveAs"}, {"Export Selection…", "export"}, {"Current scene folder", "sceneFolder"}, {"Current project", "project"}, {"Save scene information and thumbnail", "sidecar"}, {"Maya standard options…", "options"}})
            maya->addAction(pair.first, this, [this, action = pair.second] { perform(action, selectedPaths(), currentPath()); });
    }
}
bool BrowserWindow::extendedAction(const QString& action, const QStringList& paths, const QString& directory) {
    if (action == "manageLabels") {
        auto values = readSettings()["fileLabels"].toObject(); QSet<QString> unique;
        for (auto it = values.begin(); it != values.end(); ++it) for (const auto& value : it.value().toObject()["tags"].toArray()) unique.insert(value.toString());
        auto names = unique.values(); names.sort(Qt::CaseInsensitive); if (names.isEmpty()) { QMessageBox::information(this, "Manage tags", "No saved tags yet."); return true; }
        bool ok = false; const auto old = QInputDialog::getItem(this, "Manage tag names", "Tag", names, 0, false, &ok); if (!ok) return true;
        const auto replacement = QInputDialog::getText(this, "Rename tag", "New name (empty removes this tag from all QPE labels)", QLineEdit::Normal, old, &ok).trimmed();
        if (!ok || replacement == old) return true;
        if (QMessageBox::question(this, "Update tag", "Update this tag in all saved QPE labels?\n" + old + " → " + (replacement.isEmpty() ? "(remove)" : replacement), QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return true;
        // ダイアログ表示中の他プロセス更新も保持するため、確定時点で再取得する。
        values = readSettings()["fileLabels"].toObject();
        for (auto it = values.begin(); it != values.end(); ++it) {
            auto label = it.value().toObject(); QJsonArray tags;
            for (const auto& value : label["tags"].toArray()) { const auto name = value.toString() == old ? replacement : value.toString(); if (!name.isEmpty() && !tags.contains(name)) tags.append(name); }
            label["tags"] = tags; it.value() = label;
        }
        writeSettings({{"fileLabels", values}}); return true;
    }
    if (action == "createZip" || action == "extractZip" || action == "browseZip") {
        if (paths.isEmpty() || (action != "createZip" && paths.size() != 1)) throw std::invalid_argument("Select files (one ZIP for extraction)");
        FileRequest request{action, paths};
        if (action == "createZip") request.destination = QFileDialog::getSaveFileName(this, "Create ZIP (new file)", QDir(currentPath()).filePath("Archive.zip"), "ZIP (*.zip)");
        else if (action == "extractZip") {
            const auto parent = QFileDialog::getExistingDirectory(this, "Choose parent for a new extraction folder"); if (parent.isEmpty()) return true;
            bool ok = false; const auto name = QInputDialog::getText(this, "Extract ZIP", "New folder name", QLineEdit::Normal, QFileInfo(paths[0]).completeBaseName(), &ok);
            if (!ok) return true; validateFileName(name); request.destination = QDir(parent).filePath(name);
        }
        if (action == "browseZip" || !request.destination.isEmpty()) jobs_->enqueue(request); return true;
    }
    if (action == "properties" || action == "openWith" || action == "explorer" || action == "terminal") {
        const auto path = paths.value(0, directory.isEmpty() ? currentPath() : directory); if (path.isEmpty()) return true;
        const auto native = QDir::toNativeSeparators(path);
        if (action == "properties") {
            SHELLEXECUTEINFOW info{sizeof(info)}; info.fMask = SEE_MASK_INVOKEIDLIST; info.hwnd = reinterpret_cast<HWND>(shellDialogOwner(this)); info.lpVerb = L"properties"; info.lpFile = reinterpret_cast<LPCWSTR>(native.utf16()); info.nShow = SW_SHOWNORMAL;
            if (!ShellExecuteExW(&info)) throw std::runtime_error("Could not open Windows Properties");
        } else if (action == "openWith") {
            OPENASINFO info{}; info.pcszFile = reinterpret_cast<LPCWSTR>(native.utf16()); info.oaifInFlags = OAIF_EXEC;
            const auto code = SHOpenWithDialog(reinterpret_cast<HWND>(shellDialogOwner(this)), &info); if (FAILED(code) && code != HRESULT_FROM_WIN32(ERROR_CANCELLED)) throw std::runtime_error("Could not open app chooser");
        } else if (action == "explorer") QProcess::startDetached("explorer.exe", QFileInfo(path).isDir() ? QStringList{native} : QStringList{"/select,", native});
        else QProcess::startDetached("powershell.exe", {"-NoExit"}, QFileInfo(path).isDir() ? path : QFileInfo(path).absolutePath());
        return true;
    }
    if (action == "browseLabels") {
        bool ok = false; const auto query = QInputDialog::getText(this, "Browse labels", "Tag, collection or rating:3", QLineEdit::Normal, {}, &ok); if (!ok) return true;
        const auto labels = readSettings()["fileLabels"].toObject(); QJsonArray rows;
        for (auto it = labels.begin(); it != labels.end(); ++it) {
            const auto value = it.value().toObject(); QStringList tags; for (const auto& v : value["tags"].toArray()) tags.append(v.toString());
            if ((query.startsWith("rating:") && value["rating"].toInt() >= query.mid(7).toInt()) || (!query.startsWith("rating:") && (tags.contains(query) || value["collection"].toString() == query)))
                rows.append(QJsonObject{{"path", it.key()}, {"size", double(QFileInfo(it.key()).size())}, {"state", tags.join(", ")}});
        }
        showQuery({{"query", "Labels"}, {"rows", rows}}); return true;
    }
    if (action == "jobs") {
        auto* dialog = new QDialog(this); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setWindowTitle("File jobs / retry"); dialog->resize(850, 500);
        auto* layout = new QVBoxLayout(dialog); auto* list = new QTreeWidget; list->setHeaderLabels({"Action", "State", "Destination / errors"}); layout->addWidget(list);
        auto* progress = new QLabel; progress->setWordWrap(true); layout->addWidget(progress);
        auto* actions = new QGridLayout; layout->addLayout(actions);
        const auto refresh = [this, list, progress] {
            progress->setText("No active transfer"); for (const auto& value : jobs_->records()) { const auto row = value.toObject(); if (row["state"] == "running" || row["state"] == "paused") progress->setText(QString("%1 copied · %2/s average · %3").arg(QLocale().formattedDataSize(qint64(row["bytes"].toDouble())), QLocale().formattedDataSize(qint64(row["bytesPerSecond"].toDouble())), row["path"].toString())); }
            const auto selected = list->currentItem() ? list->currentItem()->data(0, Qt::UserRole).toString() : QString(); list->clear(); QSet<QString> live;
            for (const auto& value : jobs_->records()) { const auto row = value.toObject(); auto* item = new QTreeWidgetItem(list, {row["action"].toString(), row["state"].toString(), row["destination"].toString()}); item->setData(0, Qt::UserRole, row["id"].toString()); item->setData(0, Qt::UserRole + 1, row["index"].toInt(-1)); live.insert(row["id"].toString()); }
            for (const auto& file : QDir(operationsDirectory() + "/jobs").entryInfoList({"*.json"}, QDir::Files, QDir::Time)) {
                try { const auto row = loadJson(file.absoluteFilePath()); if (live.contains(row["id"].toString()) || row["state"] == "discarded") continue;
                    auto* item = new QTreeWidgetItem(list, {row["action"].toString(), row["state"].toString(), row["destination"].toString() + " " + QString::fromUtf8(QJsonDocument(row["errors"].toArray()).toJson(QJsonDocument::Compact))}); item->setData(0, Qt::UserRole, row["id"].toString()); item->setData(0, Qt::UserRole + 1, -1);
                } catch (...) {}
            }
            for (const auto& file : QDir(QFileInfo(operationsDirectory()).absolutePath() + "/jobs").entryInfoList({"*.json"}, QDir::Files, QDir::Time)) {
                try { const auto row = loadJson(file.absoluteFilePath());
                    if (row["version"].toInt() != 1 || QStringList{"Completed", "Discarded"}.contains(row["state"].toString())) continue;
                    const auto nativeId = legacyTransferId(row["id"].toString());
                    if (QFileInfo::exists(operationsDirectory() + "/jobs/" + nativeId + ".json")) continue;
                    auto* item = new QTreeWidgetItem(list, {row["action"].toString(), "Legacy: " + row["state"].toString(), row["destination"].toString()});
                    item->setData(0, Qt::UserRole, "legacy:" + row["id"].toString()); item->setData(0, Qt::UserRole + 1, -1);
                } catch (...) {}
            }
            for (int i = 0; i < list->topLevelItemCount(); ++i) if (list->topLevelItem(i)->data(0, Qt::UserRole).toString() == selected) list->setCurrentItem(list->topLevelItem(i));
            list->resizeColumnToContents(0); list->resizeColumnToContents(1);
        };
        int buttonIndex = 0;
        for (const auto& label : QStringList{"Pause active", "Pause queue", "Cancel active", "Cancel queued", "Resume / retry", "Move up", "Move down", "Discard record"}) {
            auto* button = new QPushButton(label); actions->addWidget(button, buttonIndex / 4, buttonIndex % 4); ++buttonIndex; button->setCheckable(label.startsWith("Pause"));
            if (label == "Pause active") button->setChecked(jobs_->activePaused()); else if (label == "Pause queue") button->setChecked(jobs_->queuePaused());
            connect(button, &QPushButton::clicked, dialog, [this, list, label, button, refresh] {
                try {
                    if (label == "Pause active") jobs_->pauseActive(button->isChecked());
                    else if (label == "Pause queue") jobs_->pauseQueue(button->isChecked());
                    else if (label == "Cancel active") jobs_->cancelActive(); else if (label == "Cancel queued") jobs_->cancelQueued();
                    else if (list->currentItem()) { if (label == "Resume / retry") jobs_->resume(list->currentItem()->data(0, Qt::UserRole).toString()); else if (label == "Discard record") jobs_->discard(list->currentItem()->data(0, Qt::UserRole).toString()); else jobs_->moveQueued(list->currentItem()->data(0, Qt::UserRole + 1).toInt(), label == "Move up" ? -1 : 1); }
                    refresh();
                } catch (const std::exception& e) { QMessageBox::warning(this, "File jobs", QString::fromUtf8(e.what())); }
            });
        }
        auto* timer = new QTimer(dialog); connect(timer, &QTimer::timeout, dialog, refresh); timer->start(1000); refresh(); dialog->show(); return true;
    }
    if (action == "history") {
        auto* dialog = new QDialog(this); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setWindowTitle("File operation history — latest operation is undone first"); dialog->resize(900, 560);
        auto* layout = new QVBoxLayout(dialog); auto* rows = new QTreeWidget; rows->setHeaderLabels({"State", "Time", "Operation", "Source", "Target"}); layout->addWidget(rows);
        const auto journal = loadJson(operationsDirectory() + "/journal.json");
        for (const auto& key : {"undo", "redo", "retained", "reviewed"}) { const auto values = journal[key].toArray(); for (int i = values.size() - 1; i >= 0; --i) { const auto item = values[i].toObject(); auto* row = new QTreeWidgetItem(rows, {key, item["time"].toString(), item["action"].toString(), item["source"].toString(), item["target"].toString()}); row->setToolTip(3, item["source"].toString()); row->setToolTip(4, item["target"].toString()); } }
        auto* text = new QTextEdit; text->setReadOnly(true); text->setMaximumHeight(130); text->setPlainText(QString::fromUtf8(QJsonDocument(journal["pending"].toObject()).toJson())); text->setVisible(!journal["pending"].toObject().isEmpty()); layout->addWidget(text);
        auto* note = new QLabel("Undo/Redo refuses external changes. Recycle Bin data is managed by Windows. Cleanup removes only verified QPE backups; reviewed recovery data and Redo are retained."); note->setWordWrap(true); layout->addWidget(note);
        auto* buttons = new QHBoxLayout; layout->addLayout(buttons);
        for (const auto& operation : QStringList{"undo", "redo"}) { auto* button = new QPushButton(operation == "undo" ? "Undo latest" : "Redo latest"); buttons->addWidget(button); connect(button, &QPushButton::clicked, dialog, [this, dialog, operation] { perform(operation); dialog->close(); }); }
        auto* cleanup = new QPushButton("Clean up expired history…"); buttons->addWidget(cleanup);
        connect(cleanup, &QPushButton::clicked, dialog, [this, dialog] {
            try { const auto values = readSettings()["preferences"].toObject(); const int days = values["undoDays"].toInt(30), budget = values["undoMiB"].toInt(1024);
                if (QMessageBox::question(dialog, "Clean up Undo history", QString("Remove oldest Undo backups older than %1 days or exceeding %2 MiB?\nRemoved operations cannot be undone. Recycle Bin is not emptied.").arg(days).arg(budget), QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                jobs_->enqueue({"historyCleanup", {}, {}, "rename", {{"days", days}, {"budget", double(budget) * 1024 * 1024}}}); dialog->close();
            } catch (const std::exception& e) { QMessageBox::warning(dialog, "Cleanup", QString::fromUtf8(e.what())); }
        });
        if (!journal["pending"].toObject().isEmpty()) {
            auto* review = new QPushButton("Acknowledge reviewed interruption…"); buttons->addWidget(review);
            connect(review, &QPushButton::clicked, dialog, [this, dialog, journal] {
                if (QMessageBox::question(dialog, "Retain current files", "Inspect the source, target and retained backup paths above before continuing.\nKeep every file exactly as it is and archive the interrupted record?\nQPE will not guess which copy to keep. This record will no longer be an Undo/Redo target.", QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                const auto digest = QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(journal).toJson(QJsonDocument::Compact), QCryptographicHash::Sha256).toHex());
                jobs_->enqueue({"historyReview", {}, {}, "rename", {{"acknowledge", true}, {"journalDigest", digest}}}); dialog->close();
            });
        }
        dialog->show(); return true;
    }
    return false;
}
}
