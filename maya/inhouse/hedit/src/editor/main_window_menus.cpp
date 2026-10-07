/** @file main_window_menus.cpp
 * @brief MainWindowのうち、メニュー・ツールバーの組み立てと、Preferencesのリセット。
 * @details メニューの項目(QAction)は、メニューとツールバーで共有する(同じ項目を両方に置く)。
 * ``menu->addAction(文字, this, ラムダ, ショートカット)``は、選んだときにラムダを呼ぶ項目を作る。
 * 第3引数(this)はラムダの持ち主で、このウィンドウが破棄されると接続も外れる。
 * テストが項目を探すときは、表示名(text)かobjectNameを使う(docs/development.rstの一覧)。
 */
#include "editor/code_assist.h"
#include "editor/code_editor.h"
#include "editor/editor_tabs.h"
#include "editor/explorer.h"
#include "editor/find_bar.h"
#include "editor/main_window.h"
#include "editor/output_panel.h"
#include "editor/ui_scale.h"
#include <QAction>
#include <QComboBox>
#include <QDockWidget>
#include <QFileDialog>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QSignalBlocker>
#include <QStyle>
#include <QToolBar>

namespace hedit {
namespace {

/// アウトラインの表示の状態を保存する名前(main_window.cppのkOutlineVisibleFlagと同じ)。
constexpr const char* kOutlineVisibleFlagName = "outlineVisible";

}  // namespace

void MainWindow::buildMenusAndToolbar() {
    // ---- File ----
    QMenu* file = menuBar()->addMenu("File");
    file->addAction("New Python tab", this, [this] { newTab(); }, QKeySequence::New);
    file->addAction("New MEL tab", this, [this] { newTab(ScriptLanguage::Mel); });
    QAction* openAction = file->addAction("Open…", this, [this] {
        openFile(QFileDialog::getOpenFileName(this, "Open script", {}, "Scripts (*.py *.mel);;All files (*)"));
    }, QKeySequence::Open);
    recentMenu_ = file->addMenu("Open recent");
    recentMenu_->setObjectName("recentMenu");
    connect(recentMenu_, &QMenu::aboutToShow, this, [this] { rebuildRecentMenu(); });
    QAction* quickOpen = file->addAction("Quick open…", this, [this] { showFilePicker(); }, QKeySequence("Ctrl+P"));
    quickOpen->setObjectName("quickOpen");
    file->addAction("Open folder…", this, [this] {
        const QString path = QFileDialog::getExistingDirectory(this, "Open folder");
        if (!path.isEmpty()) {
            explorer_->addFolder(path, true);
            explorerDock_->show();
        }
    });
    file->addAction("Add folder…", this, [this] {
        const QString path = QFileDialog::getExistingDirectory(this, "Add folder");
        if (!path.isEmpty()) {
            explorer_->addFolder(path);
            explorerDock_->show();
        }
    });
    QAction* saveAction = file->addAction("Save", this, [this] { saveFile(currentEditor()); }, QKeySequence::Save);
    file->addAction("Save as…", this, [this] { saveFile(currentEditor(), true); }, QKeySequence("Ctrl+Shift+S"));
    QAction* compare = file->addAction("Compare with saved", this, [this] { compareWithSaved(); },
                                       QKeySequence("Ctrl+K, D"));
    compare->setObjectName("compareWithSavedAction");
    QAction* closeAction = file->addAction("Close tab", this, [this] { closeTab(tabs_->currentIndex()); });
    closeAction->setShortcuts({QKeySequence("Ctrl+W"), QKeySequence("Ctrl+F4")});

    // ---- Edit ----
    QMenu* edit = menuBar()->addMenu("Edit");
    buildPreferencesMenu(edit->addMenu("Preferences"));
    edit->addAction("Find…", this, [this] { findBar_->open(false); }, QKeySequence("Ctrl+F"));
    edit->addAction("Replace…", this, [this] { findBar_->open(true); }, QKeySequence("Ctrl+H"));
    edit->addAction("Find next", this, [this] { findBar_->findNext(); }, QKeySequence("F3"));
    edit->addAction("Find previous", this, [this] { findBar_->findNext(true); }, QKeySequence("Shift+F3"));
    edit->addAction("Go to line…", this, [this] { showGoToLine(); }, QKeySequence("Ctrl+G"));
    // VS Codeの「ホバーを表示」と同じキー(Ctrl+Kを押してからCtrl+I)。
    edit->addAction("Show hover", this, [this] {
        if (CodeEditor* editor = currentEditor()) {
            editor->showHoverAtCursor();
        }
    }, QKeySequence("Ctrl+K, Ctrl+I"));
    edit->addSeparator();
    edit->addAction("Expand selection", this, [this] {
        if (CodeEditor* editor = currentEditor()) {
            editor->expandSelection();
        }
    }, QKeySequence("Shift+Alt+Right"));
    edit->addAction("Shrink selection", this, [this] {
        if (CodeEditor* editor = currentEditor()) {
            editor->shrinkSelection();
        }
    }, QKeySequence("Shift+Alt+Left"));
    edit->addSeparator();
    QAction* clearInputAction = edit->addAction("Clear input", this, [this] { clearInput(); });
    QAction* clearBothAction = edit->addAction("Clear input and output", this, [this] {
        clearInput();
        output_->clear();
    });

    // ---- View ----
    QMenu* view = menuBar()->addMenu("View");
    // toggleViewActionは、ドックの表示・非表示を切り替える、Qtが用意したアクション。
    QAction* explorerAction = explorerDock_->toggleViewAction();
    explorerAction->setText("Explorer");
    explorerAction->setObjectName("toggleExplorer");
    explorerAction->setShortcut(QKeySequence("Ctrl+B"));
    view->addAction(explorerAction);
    QAction* outlineAction = outlineDock_->toggleViewAction();
    outlineAction->setText("Outline");
    outlineAction->setObjectName("toggleOutline");
    view->addAction(outlineAction);
    // 利用者が切り替えたときだけ保存する(ウィンドウを閉じるときの非表示は保存しない)。
    connect(outlineAction, &QAction::triggered, this, [this](bool visible) {
        preferences_.setFlag(kOutlineVisibleFlagName, visible);
    });
    view->addSeparator();
    auto editorAction = [this](void (CodeEditor::*method)()) {
        return [this, method] {
            if (CodeEditor* editor = currentEditor()) {
                (editor->*method)();
            }
        };
    };
    QAction* fold = view->addAction("Fold", this, editorAction(&CodeEditor::foldAtCursor));
    fold->setShortcuts({QKeySequence("Ctrl+Shift+["), QKeySequence("Ctrl+{")});
    QAction* unfold = view->addAction("Unfold", this, editorAction(&CodeEditor::unfoldAtCursor));
    unfold->setShortcuts({QKeySequence("Ctrl+Shift+]"), QKeySequence("Ctrl+}")});
    view->addAction("Fold all", this, editorAction(&CodeEditor::foldAll), QKeySequence("Ctrl+K, Ctrl+0"));
    view->addAction("Unfold all", this, editorAction(&CodeEditor::unfoldAll), QKeySequence("Ctrl+K, Ctrl+J"));
    view->addSeparator();
    QAction* zoomIn = view->addAction("Zoom in", this, [this] { setZoom(preferences_.fontPixels() + 1); });
    zoomIn->setObjectName("zoomIn");
    zoomIn->setShortcuts({QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")});
    QAction* zoomOut = view->addAction("Zoom out", this, [this] { setZoom(preferences_.fontPixels() - 1); },
                                       QKeySequence("Ctrl+-"));
    zoomOut->setObjectName("zoomOut");
    QAction* zoomReset = view->addAction("Reset zoom", this,
                                         [this] { setZoom(EditorPreferences::kDefaultFontPixels); },
                                         QKeySequence("Ctrl+0"));
    zoomReset->setObjectName("zoomReset");
    QAction* showOutputAction = view->addAction("Show output only", this, [this] { showPanels(true, false); });
    QAction* showInputAction = view->addAction("Show input only", this, [this] { showPanels(false, true); });
    QAction* showBothAction = view->addAction("Show input and output", this, [this] { showPanels(true, true); });

    // ---- Go ----
    QMenu* go = menuBar()->addMenu("Go");
    QAction* symbol = go->addAction("Go to symbol…", this, [this] { showSymbolPicker(); }, QKeySequence("Ctrl+Shift+O"));
    symbol->setObjectName("goToSymbol");
    go->addAction("Go to definition", this, [this] {
        if (CodeEditor* editor = currentEditor()) {
            goToDefinition(editor, editor->nameEndAtCursor(), false);
        }
    }, QKeySequence("F12"));
    go->addAction("Peek definition", this, [this] {
        if (CodeEditor* editor = currentEditor()) {
            goToDefinition(editor, editor->nameEndAtCursor(), true);
        }
    }, QKeySequence("Alt+F12"));
    go->addSeparator();
    go->addAction("Next problem", this, [this] {
        CodeEditor* editor = currentEditor();
        if (editor && !editor->goToProblem(1)) {
            showStatus("No problems (turn on Edit > Preferences > Static analysis)", 3000);
        }
    }, QKeySequence("F8"));
    go->addAction("Previous problem", this, [this] {
        CodeEditor* editor = currentEditor();
        if (editor && !editor->goToProblem(-1)) {
            showStatus("No problems (turn on Edit > Preferences > Static analysis)", 3000);
        }
    }, QKeySequence("Shift+F8"));
    go->addSeparator();
    go->addAction("Trigger parameter hints", this, [this] {
        CodeEditor* editor = currentEditor();
        if (editor && editor->onSignatureHelpRequested) {
            editor->onSignatureHelpRequested(true);
        }
    }, QKeySequence("Ctrl+Shift+Space"));
    go->addAction("Go to line…", this, [this] { showGoToLine(); });

    // ---- Tabs ----
    QMenu* tabMenu = menuBar()->addMenu("Tabs");
    QAction* nextTab = tabMenu->addAction("Next tab", this, [this] {
        tabs_->switchTab(1);
        currentEditor()->setFocus();
    });
    nextTab->setShortcuts({QKeySequence("Ctrl+Tab"), QKeySequence("Ctrl+PgDown")});
    QAction* previousTab = tabMenu->addAction("Previous tab", this, [this] {
        tabs_->switchTab(-1);
        currentEditor()->setFocus();
    });
    previousTab->setShortcuts({QKeySequence("Ctrl+Shift+Tab"), QKeySequence("Ctrl+PgUp")});

    // ---- History ----
    QMenu* history = menuBar()->addMenu("History");
    QAction* clearOutputAction = history->addAction("Clear output", this, [this] { output_->clear(); });

    // ---- Command ----
    QMenu* command = menuBar()->addMenu("Command");
    QAction* runSelectionAction = command->addAction("Run selection / script", this, [this] { runCode(false); });
    runSelectionAction->setShortcut(QKeySequence("Ctrl+Return"));
    QAction* runAllAction = command->addAction("Run all", this, [this] { runCode(true); });
    runAllAction->setShortcut(QKeySequence("F5"));
    command->addSeparator();
    command->addAction("Refresh completion", this, [this] { assist_->refreshCompletion(); });

    // ---- ツールバー(Maya標準のScript Editorと同じアイコン) ----
    QToolBar* toolbar = addToolBar("Script editor");
    toolbar->setObjectName("scriptToolbar");
    toolbar->setMovable(false);
    toolbar->setToolButtonStyle(Qt::ToolButtonIconOnly);
    toolbar->setIconSize(QSize(scaled(20), scaled(20)));
    // メニューと同じアクションをツールバーにも置く(機能は1つ)。アイコンはMaya同梱の画像を使い、
    // Maya無しのテストでは代わりにQt標準のアイコンを使う。
    auto addToolButton = [this, toolbar](QAction* action, const QString& image, QStyle::StandardPixmap fallback) {
        QIcon icon = loadIcon(image);
        if (icon.isNull()) {
            icon = style()->standardIcon(fallback);
        }
        action->setIcon(icon);
        QString tooltip = action->text();
        if (!action->shortcut().isEmpty()) {
            tooltip += " (" + action->shortcut().toString(QKeySequence::NativeText) + ")";
        }
        action->setToolTip(tooltip);
        toolbar->addAction(action);
    };
    addToolButton(openAction, "openScript.png", QStyle::SP_DialogOpenButton);
    addToolButton(saveAction, "save.png", QStyle::SP_DialogSaveButton);
    toolbar->addSeparator();
    addToolButton(clearOutputAction, "clearHistory.png", QStyle::SP_TrashIcon);
    addToolButton(clearInputAction, "clearInput.png", QStyle::SP_DialogResetButton);
    addToolButton(clearBothAction, "clearAll.png", QStyle::SP_DialogDiscardButton);
    toolbar->addSeparator();
    addToolButton(showOutputAction, "showHistory.png", QStyle::SP_TitleBarMaxButton);
    addToolButton(showInputAction, "showInput.png", QStyle::SP_FileIcon);
    addToolButton(showBothAction, "showBoth.png", QStyle::SP_TitleBarNormalButton);
    toolbar->addSeparator();
    addToolButton(runAllAction, "executeAll.png", QStyle::SP_MediaSkipForward);
    addToolButton(runSelectionAction, "execute.png", QStyle::SP_MediaPlay);
    toolbar->addSeparator();
    addToolButton(explorerAction, "outliner.png", QStyle::SP_DirIcon);
    toolbar->addSeparator();
    toolbar->addWidget(output_->filterSelector());  // 表示モードの選択欄。ツールバーが所有者になる。
}

void MainWindow::buildPreferencesMenu(QMenu* menu) {
    for (const OptionDefinition& definition : optionDefinitions()) {
        if (definition.separatorBefore) {
            menu->addSeparator();
        }
        const QString key = definition.key;
        QAction* action = menu->addAction(definition.label);
        action->setObjectName("option_" + key);  // テストが探すときの名前。
        action->setCheckable(true);
        action->setChecked(preferences_.option(key));
        connect(action, &QAction::toggled, this, [this, key](bool enabled) { onOptionToggled(key, enabled); });
        optionActions_.insert(key, action);
    }
    // 最後に、全ての設定を初期値に戻す項目を置く。
    menu->addSeparator();
    QAction* reset = menu->addAction("Reset to defaults…", this, [this] { resetPreferences(); });
    reset->setObjectName("resetPreferences");
    reset->setToolTip("Reset all preferences and the font size to their defaults");
}

void MainWindow::limitShortcutsToThisWindow() {
    // 標準では、メニューのショートカットはMaya全体で効いてしまう。
    // WidgetWithChildrenShortcutにすると、hedit(とその子)にフォーカスがあるときだけ効く。
    for (QAction* action : findChildren<QAction*>()) {
        if (action->shortcuts().isEmpty()) {
            continue;
        }
        addAction(action);
        action->setShortcutContext(Qt::WidgetWithChildrenShortcut);
    }
}

void MainWindow::resetPreferences() {
    const auto answer = QMessageBox::question(
        this, "Reset preferences",
        "Reset all editor preferences and the font size to their defaults?\n\n"
        "Open tabs, files and the Explorer are not changed.",
        QMessageBox::Reset | QMessageBox::Cancel, QMessageBox::Cancel);
    if (answer != QMessageBox::Reset) {
        return;
    }
    const bool saved = preferences_.resetToDefaults();

    // メニューのチェックを初期値に合わせる。QSignalBlockerがある間はtoggledが出ないので、
    // onOptionToggledが1項目ずつ保存し直すことはない(反映は下でまとめて行う)。
    for (auto it = optionActions_.begin(); it != optionActions_.end(); ++it) {
        const QSignalBlocker blocker(it.value());
        it.value()->setChecked(preferences_.option(it.key()));
    }
    // onOptionToggledで項目ごとに行う反映を、全ての項目についてまとめて行う。
    for (CodeEditor* editor : tabs_->editors()) {
        applyPreferences(editor);
        editor->hideCompletions();
    }
    output_->view()->setLineNumbersVisible(preferences_.option(option::kOutputLineNumbers));
    output_->setWrap(preferences_.option(option::kOutputWrap));
    if (services_.setExactOutput) {
        services_.setExactOutput(preferences_.option(option::kExactOutput));
    }
    assist_->scheduleAnalysis();
    assist_->scheduleSpelling();
    applyZoom();

    if (saved) {
        showStatus("Preferences reset to defaults", 3000);
    } else {
        showStatus("Could not save editor preferences");
    }
}

}  // namespace hedit
