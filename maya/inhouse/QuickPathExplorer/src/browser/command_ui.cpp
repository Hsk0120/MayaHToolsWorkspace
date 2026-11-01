/** @file command_ui.cpp @brief 旧版のコマンドIDと設定形式を保つ検索・キー割当画面。 */
#include "browser_window.h"
#include "../core/settings_store.h"
#include <QApplication>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QHeaderView>
#include <QKeySequenceEdit>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QShortcut>
#include <QSpinBox>
#include <QTextEdit>
#include <QTimer>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <stdexcept>
namespace qpe {
namespace {
/** @brief 設定ファイルの安定したID、表示名、実装操作を対応付ける。 */
struct Command { QString id, title, action; };
/** @brief Maya有無に応じた操作一覧を返す。 @param maya Mayaホストか。 @return コマンド一覧。 */
QList<Command> commands(bool maya) {
    QList<Command> result{
        {"palette", "Find command…", "palette"}, {"settings", "QPE settings / keyboard shortcuts…", "settings"}, {"appearance", "Display Settings…", "appearance"},
        {"saveWorkspace", "Save tab set…", "saveTabs"}, {"loadWorkspace", "Open tab set…", "loadTabs"},
        {"deleteWorkspace", "Delete tab set…", "deleteTabs"}, {"previousWorkspace", "Restore previous tab set", "restoreTabSet"},
        {"archive", "Browse ZIP…", "browseZip"}, {"createZip", "Create ZIP…", "createZip"}, {"extractZip", "Extract ZIP…", "extractZip"},
        {"diagnose", "Diagnose file usage / availability…", "diagnose"}, {"jobs", "File jobs / retry…", "jobs"},
        {"recoverTransfers", "Resume unfinished transfers…", "jobs"}, {"history", "File operation history…", "history"},
        {"redo", "Redo file operation", "redo"}, {"undo", "Undo file operation", "undo"}, {"summary", "Calculate selected / folder size…", "size"},
        {"openFile", "Open selected file", "open"}, {"labels", "Manage label names…", "manageLabels"},
        {"thumbnails", "View: thumbnails", "view:Thumbnails"}, {"metadata", "View: extended details / tags", "view:Extended details"},
        {"details", "View: details", "view:Details"}, {"flat", "View: toggle subfolders", "recursiveToggle"},
        {"columnsFirst", "Browser layout: columns first", "area:columns"}, {"balanced", "Browser layout: balanced", "area:balanced"}, {"filesFirst", "Browser layout: files first", "area:files"},
        {"search", "Search subfolders…", "search"}, {"duplicates", "Find duplicate files…", "duplicates"},
        {"compare", "Compare folders…", "compare"}, {"hash", "Calculate SHA-256", "hash"}, {"secondPane", "Toggle second file pane", "secondPane"},
        {"tag", "Tags / rating / collection…", "tag"}, {"browseLabels", "Browse tags / collections…", "browseLabels"},
        {"batchRename", "Batch rename…", "batchRename"}, {"copyTo", "Copy to folder…", "copyTo"}, {"moveTo", "Move to folder…", "moveTo"},
        {"newFolder", "New Folder…", "newFolder"}, {"newFile", "New File…", "newFile"},
        {"exportSettings", "Export QPE settings…", "exportSettings"}, {"importSettings", "Import QPE settings…", "importSettings"},
        {"properties", "Windows Properties", "properties"}, {"explorer", "Show in Windows Explorer", "explorer"}, {"openWith", "Open with…", "openWith"}
    };
    if (maya) for (const auto& command : QList<Command>{{"new", "Maya: New Scene", "new"}, {"save", "Maya: Save Scene", "save"}, {"saveAs", "Maya: Save Scene As…", "prepareSave"}, {"import", "Maya: Import", "import"}, {"reference", "Maya: Reference", "reference"}, {"sidecar", "Maya: Save scene information and thumbnail", "sidecar"}, {"project", "Maya: Current project", "project"}, {"sceneFolder", "Maya: Current scene folder", "sceneFolder"}, {"options", "Maya: Standard file dialogs…", "options"}}) result.append(command);
    return result;
}
/** @brief 入力欄と別ダイアログではカスタムキーを処理しない。 @param owner QPE。 @return 操作キーを有効にするか。 */
bool commandFocus(QWidget* owner) {
    auto* focus = QApplication::focusWidget(); if (!focus || focus->window() != owner->window() || (focus != owner && !owner->isAncestorOf(focus))) return false;
    for (auto* widget = focus; widget && widget != owner; widget = widget->parentWidget())
        if (qobject_cast<QLineEdit*>(widget) || qobject_cast<QTextEdit*>(widget) || qobject_cast<QPlainTextEdit*>(widget) || qobject_cast<QAbstractSpinBox*>(widget) || qobject_cast<QKeySequenceEdit*>(widget) || qobject_cast<QComboBox*>(widget)) return false;
    return true;
}
}
void BrowserWindow::installCommandKeys() {
    for (auto* shortcut : findChildren<QShortcut*>("qpeCustomCommand", Qt::FindDirectChildrenOnly)) delete shortcut;
    auto keys = QJsonObject{{"palette", "Ctrl+Shift+P"}, {"jobs", "Ctrl+Shift+J"}, {"history", "Ctrl+Shift+H"}};
    try { const auto configured = readSettings()["commandKeys"].toObject(); for (auto it = configured.begin(); it != configured.end(); ++it) keys[it.key()] = it.value(); validateCommandKeys(keys); }
    catch (const std::exception& e) { qWarning("QPE custom shortcuts disabled: %s", e.what()); return; }
    for (const auto& command : commands(host_.maya)) {
        const auto key = keys[command.id].toString(); if (key.isEmpty()) continue;
        auto* shortcut = new QShortcut(QKeySequence(key), this); shortcut->setObjectName("qpeCustomCommand"); shortcut->setProperty("commandId", command.id); shortcut->setContext(Qt::WidgetWithChildrenShortcut); shortcut->setEnabled(commandFocus(this));
        connect(qApp, &QApplication::focusChanged, shortcut, [this, shortcut] { shortcut->setEnabled(commandFocus(this)); });
        connect(shortcut, &QShortcut::activated, this, [this, action = command.action] { if (commandFocus(this)) perform(action, selectedPaths(), currentPath()); });
    }
}
void BrowserWindow::commandPalette() {
    QDialog dialog(this); dialog.setObjectName("qpeCommandPalette"); dialog.setWindowTitle("Find command"); dialog.resize(540, 480);
    auto* layout = new QVBoxLayout(&dialog); auto* query = new QLineEdit; query->setPlaceholderText("Search commands…"); auto* list = new QListWidget;
    layout->addWidget(query); layout->addWidget(list); QString selected;
    const auto fill = [this, query, list] { list->clear(); for (const auto& command : commands(host_.maya)) if (command.id != "palette" && command.title.contains(query->text(), Qt::CaseInsensitive)) { auto* item = new QListWidgetItem(command.title, list); item->setData(Qt::UserRole, command.action); } if (list->count()) list->setCurrentRow(0); };
    const auto accept = [&dialog, list, &selected] { if (list->currentItem()) { selected = list->currentItem()->data(Qt::UserRole).toString(); dialog.accept(); } };
    connect(query, &QLineEdit::textChanged, &dialog, fill); connect(query, &QLineEdit::returnPressed, &dialog, accept); connect(list, &QListWidget::itemActivated, &dialog, accept);
    fill(); query->setFocus(); if (dialog.exec() == QDialog::Accepted && !selected.isEmpty()) perform(selected, selectedPaths(), currentPath());
}
void BrowserWindow::preferencesDialog() {
    const auto state = readSettings(); auto preferences = state["preferences"].toObject();
    QDialog dialog(this); dialog.setWindowTitle("QPE settings / keyboard shortcuts"); dialog.setObjectName("qpePreferences"); dialog.resize(680, 560);
    auto* layout = new QVBoxLayout(&dialog); auto* form = new QFormLayout; layout->addLayout(form);
    auto* days = new QSpinBox; days->setRange(1, 3650); days->setValue(preferences["undoDays"].toInt(30)); form->addRow("Undo retention (days, manual cleanup)", days);
    auto* budget = new QSpinBox; budget->setRange(1, 1048576); budget->setValue(preferences["undoMiB"].toInt(1024)); form->addRow("Undo backup budget (MiB, manual cleanup)", budget);
    auto* everything = new QLineEdit(state["everythingExecutable"].toString()); form->addRow("Everything CLI executable", everything);
    auto* info = new QLabel("Custom shortcuts apply only inside QPE. Editing fields and other Maya views are protected. Standard file-operation keys are reserved."); info->setWordWrap(true); layout->addWidget(info);
    auto* tree = new QTreeWidget; tree->setHeaderLabels({"Command", "Shortcut"}); tree->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents); layout->addWidget(tree);
    auto keys = QJsonObject{{"palette", "Ctrl+Shift+P"}, {"jobs", "Ctrl+Shift+J"}, {"history", "Ctrl+Shift+H"}}; const auto custom = state["commandKeys"].toObject(); for (auto it = custom.begin(); it != custom.end(); ++it) keys[it.key()] = it.value();
    QMap<QString, QKeySequenceEdit*> edits;
    for (const auto& command : commands(host_.maya)) { auto* row = new QTreeWidgetItem(tree, {command.title}); auto* edit = new QKeySequenceEdit(QKeySequence(keys[command.id].toString()), tree); tree->setItemWidget(row, 1, edit); edits.insert(command.id, edit); }
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel); layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
        try { QJsonObject next = custom; for (auto it = edits.begin(); it != edits.end(); ++it) next[it.key()] = it.value()->keySequence().toString(QKeySequence::PortableText); validateCommandKeys(next);
            preferences["undoDays"] = days->value(); preferences["undoMiB"] = budget->value(); writeSettings({{"preferences", preferences}, {"commandKeys", next}, {"everythingExecutable", everything->text()}}); dialog.accept();
        } catch (const std::exception& e) { QMessageBox::warning(&dialog, "Settings", QString::fromUtf8(e.what())); }
    });
    if (dialog.exec() == QDialog::Accepted) installCommandKeys();
}
}
