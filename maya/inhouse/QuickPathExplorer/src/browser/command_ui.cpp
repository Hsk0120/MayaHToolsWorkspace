/** @file command_ui.cpp @brief 旧版のコマンドIDと設定形式を保つ検索・キー割当画面。 */
#include "ui_language.h"
#include "browser_window.h"
#include "../core/settings_store.h"
#include <QApplication>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QScrollArea>
#include <QTabWidget>
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
#include <QStyledItemDelegate>
#include <QStyleOptionViewItem>
#include <QTextEdit>
#include <QTimer>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <stdexcept>
namespace qpe {
namespace {
/** @brief 設定ファイルの安定したID、表示名、実装操作を対応付ける。 */
struct Command { QString id, title, action; };
/** @brief キー編集欄の上下が切れない行高を、現在のフォントから算出する。 */
class ShortcutRow final : public QStyledItemDelegate {
public:
    /** @brief 一覧へ所有権を渡す。 @param parent 設定のキー一覧。 */
    explicit ShortcutRow(QObject* parent) : QStyledItemDelegate(parent) {}
    /** @brief 表示プレビューで文字が拡大しても編集欄を収める。 @param option 現在の字形。 @param index 行。 @return 編集可能な寸法。 */
    QSize sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        auto size = QStyledItemDelegate::sizeHint(option, index); size.setHeight(qMax(size.height(), option.fontMetrics.height() + 24)); return size;
    }
};
/** @brief Maya有無に応じた操作一覧を返す。 @param maya Mayaホストか。 @return コマンド一覧。 */
QList<Command> commands(bool maya) {
    QList<Command> result{
        {"palette", "Find command…", "palette"}, {"settings", "Options…", "settings"}, {"appearance", "Display Settings…", "appearance"},
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
    QDialog dialog(this); dialog.setObjectName("qpeCommandPalette"); dialog.setWindowTitle(uiText("Find command")); dialog.resize(540, 480);
    auto* layout = new QVBoxLayout(&dialog); auto* query = new QLineEdit; query->setPlaceholderText(uiText("Search commands…")); auto* list = new QListWidget;
    layout->addWidget(query); layout->addWidget(list); QString selected;
    const auto fill = [this, query, list] { list->clear(); for (const auto& command : commands(host_.maya)) if (command.id != "palette" && command.id != "recoverTransfers" && uiText(command.title).contains(query->text(), Qt::CaseInsensitive)) { auto* item = new QListWidgetItem(uiText(command.title), list); item->setData(Qt::UserRole, command.action); } if (list->count()) list->setCurrentRow(0); };
    const auto accept = [&dialog, list, &selected] { if (list->currentItem()) { selected = list->currentItem()->data(Qt::UserRole).toString(); dialog.accept(); } };
    connect(query, &QLineEdit::textChanged, &dialog, fill); connect(query, &QLineEdit::returnPressed, &dialog, accept); connect(list, &QListWidget::itemActivated, &dialog, accept);
    fill(); query->setFocus(); if (dialog.exec() == QDialog::Accepted && !selected.isEmpty()) perform(selected, selectedPaths(), currentPath());
}
void BrowserWindow::preferencesDialog(const QString& initialPage) {
    const auto state = readSettings(); auto preferences = state["preferences"].toObject();
    const int originalText = textSize_, originalScale = uiPercent_;
    const auto originalTheme = theme_, originalDensity = density_;
    const auto originalWidth = state["columnWidthMode"].toString("fit");
    QDialog dialog(this); dialog.setWindowTitle(uiText("Folder options")); dialog.setObjectName("qpePreferences"); dialog.resize(720, 560);
    // 自分の設定だけに枠と選択表示を付ける。Mayaの標準部品や他ツールへ適用しない。
    dialog.setProperty("qpePreferencesStyle", QString(
        "QTabWidget#settingsTabs::pane { border:1px solid %3; }"
        "QTabWidget#settingsTabs QTabBar::tab { background:%5; color:%2; padding:8px 12px; border-bottom:2px solid transparent; }"
        "QTabWidget#settingsTabs QTabBar::tab:selected { background:%1; border-bottom:2px solid #0078d4; font-weight:600; }"
        "QTabWidget#settingsTabs QTabBar::tab:hover { background:%4; }"
        "QDialog#qpePreferences QComboBox, QDialog#qpePreferences QSpinBox { background:%1; color:%2; border:1px solid %3; border-radius:4px; padding:5px; }"
        "QDialog#qpePreferences QComboBox QAbstractItemView { background:%1; color:%2; }"
        "QDialog#qpePreferences QPushButton { border:1px solid %3; border-radius:4px; padding:6px 12px; }"
        "QDialog#qpePreferences QPushButton:hover { background:%4; }"
        "QDialog#qpePreferences QPushButton:default { border-color:#0078d4; }"));
    auto* layout = new QVBoxLayout(&dialog);
    auto* tabs = new QTabWidget; tabs->setObjectName("settingsTabs"); layout->addWidget(tabs, 1);
    const auto addPage = [tabs](QWidget* content, const QString& title) {
        auto* scroll = new QScrollArea(tabs); scroll->setWidgetResizable(true); scroll->setFrameShape(QFrame::NoFrame); scroll->setWidget(content);
        tabs->addTab(scroll, uiText(title));
    };
    auto* general = new QWidget; general->setObjectName("settingsGeneral"); auto* form = new QFormLayout(general);
    auto* language = new QComboBox; language->setObjectName("uiLanguage"); language->addItem("日本語 (JP)", "ja"); language->addItem("English (EN)", "en");
    language->setCurrentIndex(savedUiLanguage() == "en" ? 1 : 0); form->addRow(uiText("Language / 言語"), language);
    auto* languageHint = new QLabel(uiText("Reopen QPE to apply the language change. In Maya, close QPE and open it from the Window menu.")); languageHint->setWordWrap(true); form->addRow(languageHint);
    auto* scope = new QLabel(uiText("Settings apply to QuickPathExplorer only. Maya and Windows settings are not changed.")); scope->setWordWrap(true); form->addRow(scope);
    addPage(general, "General");
    addPage(appearancePanel(&dialog), "View");
    auto* operations = new QWidget; operations->setObjectName("settingsFileOperations"); auto* operationForm = new QFormLayout(operations);
    auto* days = new QSpinBox; days->setObjectName("undoDays"); days->setRange(1, 3650); days->setValue(preferences["undoDays"].toInt(30)); operationForm->addRow(uiText("Undo retention (days)"), days);
    auto* budget = new QSpinBox; budget->setObjectName("undoMiB"); budget->setRange(1, 1048576); budget->setValue(preferences["undoMiB"].toInt(1024)); operationForm->addRow(uiText("Undo backup budget (MiB)"), budget);
    auto* cleanupNote = new QLabel(uiText("These limits are used for manual cleanup in File operation history. Files are not removed automatically.")); cleanupNote->setWordWrap(true); operationForm->addRow(cleanupNote);
    addPage(operations, "File operations");
    auto* shortcuts = new QWidget; shortcuts->setObjectName("settingsShortcuts"); auto* shortcutLayout = new QVBoxLayout(shortcuts);
    auto* filter = new QLineEdit; filter->setObjectName("shortcutFilter"); filter->setClearButtonEnabled(true); filter->setPlaceholderText(uiText("Search commands or shortcuts…")); shortcutLayout->addWidget(filter);
    auto* info = new QLabel(uiText("Custom shortcuts apply only inside QPE. Editing fields and other Maya views are protected. Standard file-operation keys are reserved.")); info->setWordWrap(true); shortcutLayout->addWidget(info);
    auto* tree = new QTreeWidget; tree->setObjectName("shortcutCommands"); tree->setItemDelegate(new ShortcutRow(tree)); tree->setRootIsDecorated(false); tree->setAlternatingRowColors(true); tree->setHeaderLabels({uiText("Command"), uiText("Shortcut")}); tree->header()->setSectionResizeMode(0, QHeaderView::Stretch); tree->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents); shortcutLayout->addWidget(tree, 1);
    tabs->addTab(shortcuts, uiText("Keyboard shortcuts"));
    auto keys = QJsonObject{{"palette", "Ctrl+Shift+P"}, {"jobs", "Ctrl+Shift+J"}, {"history", "Ctrl+Shift+H"}}; const auto custom = state["commandKeys"].toObject(); for (auto it = custom.begin(); it != custom.end(); ++it) keys[it.key()] = it.value();
    QMap<QString, QKeySequenceEdit*> edits;
    // 同じジョブ画面の旧キーIDは配送だけ維持し、設定と検索の重複入口は表示しない。
    for (const auto& command : commands(host_.maya)) { if (command.id == "recoverTransfers") continue; auto* row = new QTreeWidgetItem(tree, {uiText(command.title)}); row->setData(0, Qt::UserRole, command.title + ' ' + command.id); auto* edit = new QKeySequenceEdit(QKeySequence(keys[command.id].toString()), tree); tree->setItemWidget(row, 1, edit); edits.insert(command.id, edit); }
    connect(filter, &QLineEdit::textChanged, &dialog, [tree](const QString& text) {
        for (int i = 0; i < tree->topLevelItemCount(); ++i) { auto* row = tree->topLevelItem(i); auto* edit = qobject_cast<QKeySequenceEdit*>(tree->itemWidget(row, 1));
            row->setHidden(!(row->text(0) + ' ' + row->data(0, Qt::UserRole).toString() + ' ' + edit->keySequence().toString()).contains(text.trimmed(), Qt::CaseInsensitive)); }
    });
    auto* external = new QWidget; external->setObjectName("settingsExternal"); auto* externalForm = new QFormLayout(external);
    auto* externalNote = new QLabel(uiText("Optional overrides. Leave a field empty to use built-in support or automatic detection.")); externalNote->setWordWrap(true); externalForm->addRow(externalNote);
    QMap<QString, QLineEdit*> executables;
    for (const auto& pair : QList<QPair<QString, QString>>{{"FFmpeg", "ffmpegExecutable"}, {"Everything CLI", "everythingExecutable"}, {"File Locksmith CLI", "fileLocksmithExecutable"}}) {
        auto* row = new QWidget; auto* rowLayout = new QHBoxLayout(row); rowLayout->setContentsMargins(0, 0, 0, 0);
        auto* edit = new QLineEdit(state[pair.second].toString()); edit->setObjectName(pair.second); edit->setClearButtonEnabled(true); rowLayout->addWidget(edit, 1); executables.insert(pair.second, edit);
        auto* browse = new QPushButton(uiText("Browse…")); rowLayout->addWidget(browse); externalForm->addRow(pair.first, row);
        connect(browse, &QPushButton::clicked, &dialog, [&dialog, edit] { const auto path = QFileDialog::getOpenFileName(&dialog, uiText("Choose executable"), edit->text(), "Application (*.exe)"); if (!path.isEmpty()) edit->setText(path); });
    }
    addPage(external, "External applications");
    tabs->setCurrentIndex(qMax(0, QStringList{"general", "display", "files", "shortcuts", "external"}.indexOf(initialPage)));
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel); layout->addWidget(buttons); uiButtons(buttons);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
        try { QJsonObject next = custom; for (auto it = edits.begin(); it != edits.end(); ++it) next[it.key()] = it.value()->keySequence().toString(QKeySequence::PortableText); validateCommandKeys(next);
            if (busy() && language->currentData().toString() != savedUiLanguage()) throw std::runtime_error(uiText("Wait for file operations to finish before changing the language.").toStdString());
            preferences["undoDays"] = days->value(); preferences["undoMiB"] = budget->value();
            QJsonObject changed{{"preferences", preferences}, {"commandKeys", next}, {"uiLanguage", language->currentData().toString()}};
            const auto width = dialog.findChild<QComboBox*>("columnWidthMode")->currentData().toString();
            if (width != originalWidth) changed["columnWidthMode"] = width;
            for (auto it = executables.begin(); it != executables.end(); ++it)
                if (it.value()->text() != state[it.key()].toString()) changed[it.key()] = it.value()->text();
            writeSettings(changed); dialog.accept();
        } catch (const std::exception& e) { UiMessageBox::warning(&dialog, uiText("Settings"), uiText(QString::fromUtf8(e.what()))); }
    });
    // 表示ページはプレビュー。Cancelやタイトルバーで閉じた場合は自分の表示値だけを戻す。
    if (dialog.exec() == QDialog::Accepted) installCommandKeys();
    else {
        textSize_ = originalText; uiPercent_ = originalScale; theme_ = originalTheme; density_ = originalDensity;
        // カラム幅のプレビューは保存していない。他プロセスが更新した設定も巻き戻さない。
        perform("columnWidthPreview:" + originalWidth);
        applyAppearance();
    }
    saveSession();
}
}
