/** @file main_window.cpp
 * @brief MainWindowの実装。
 * @details Qtの基本:
 * - ``new 部品(親)``で作った部品は、親が破棄されるときに一緒に破棄される。レイアウトやタブへ
 *   追加した部品も、追加先の親が所有者になる。そのため、ここではほとんどdeleteを書かない。
 * - ``connect(送り手, &シグナル, 持ち主, ラムダ)``は「送り手のシグナルが出たらラムダを呼ぶ」という接続。
 *   持ち主(ここでは主にthis)が破棄されると接続は自動で外れる。ラムダの[this]は、このウィンドウを使う印。
 * - QTimer::singleShot(0, ...)は「今の処理(キー入力の処理など)が終わった後で実行する」予約。
 */
#include "editor/main_window.h"
#include "editor/code_editor.h"
#include "editor/editor_tabs.h"
#include "editor/explorer.h"
#include "editor/find_bar.h"
#include "editor/output_panel.h"
#include "editor/problems_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QComboBox>
#include <QCompleter>
#include <QDockWidget>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QIntValidator>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QMenuBar>
#include <QMessageBox>
#include <QRegularExpression>
#include <QSaveFile>
#include <QScrollBar>
#include <QShortcut>
#include <QSignalBlocker>
#include <QSplitter>
#include <QStatusBar>
#include <QStyle>
#include <QTextBlock>
#include <QToolBar>
#include <QVBoxLayout>

namespace hedit {
namespace {

/// 新しいタブ(復元するものが無いとき)の最初の本文。
constexpr const char* kWelcomeText =
    "import maya.cmds as cmds\n\n# Ctrl+Space: completion    Ctrl+Enter: run\nprint(cmds.ls(selection=True))\n";

/// 補完・構文チェックへ渡す本文の上限(文字数)。これを超える位置では補完しない。
constexpr int kCompletionDocumentLimit = 200000;

/** @brief tabs.jsonと同じフォルダーのpreferences.iniのパス。
 * @param sessionPath tabs.jsonのパス。空なら保存しない。
 * @return preferences.iniの絶対パス。sessionPathが空なら空。
 */
QString preferencesPath(const QString& sessionPath) {
    if (sessionPath.isEmpty()) {
        return QString();
    }
    return QFileInfo(sessionPath).absolutePath() + "/preferences.ini";
}

/** @brief QTextCursorの選択文字列を、普通の改行の文字列にする。
 * @param text selectedText()の戻り値。行の区切りがU+2029(段落区切り)になっている。
 * @return 改行を``\n``にした文字列。
 */
QString normalizeSelectedText(QString text) {
    return text.replace(QChar(0x2029), '\n');
}

}  // namespace

// ===========================================================================
// 組み立て
// ===========================================================================

MainWindow::MainWindow(QWidget* parent, const EditorServices& services)
    : QMainWindow(parent),
      services_(services),
      preferences_(preferencesPath(services.sessionPath)),
      session_(services.sessionPath) {
    setObjectName("hedit");
    setWindowTitle("hedit - Python / MEL");
    resize(scaled(1050), scaled(740));
    // 親があれば(Mayaのドックの中なら)部品として、無ければ独立したウィンドウとして表示する。
    setWindowFlags(parent ? Qt::Widget : Qt::Window);

    buildLayout();
    buildStatusBar();
    setZoom(preferences_.fontPixels());
    buildMenusAndToolbar();
    limitShortcutsToThisWindow();
    setUpTimers();

    // 最初のタブ。復元するタブがあれば、restoreSession()が置き換える。
    CodeEditor* first = newTab();
    first->setPlainText(kWelcomeText);
    first->document()->setModified(false);
    updateTabTitle(first);
    restoreSession();

    sessionTimer_.start();
    refreshCompletion();
    scheduleAnalysis();
}

MainWindow::~MainWindow() {
    saveSession();
    // この後、子の部品が破棄される途中でシグナルを出しても、破棄済みのメンバーを使わないよう接続を外す。
    QObject::disconnect(tabs_, nullptr, this, nullptr);
    for (int i = 0; i < tabs_->count(); ++i) {
        QObject::disconnect(editorAt(i), nullptr, this, nullptr);
        QObject::disconnect(editorAt(i)->verticalScrollBar(), nullptr, this, nullptr);
    }
}

void MainWindow::buildLayout() {
    // ---- タブ欄と検索バー ----
    tabs_ = new EditorTabs;
    findBar_ = new FindBar(tabs_);  // タブ欄の子として右上に重ねる。
    findBar_->currentEditor = [this] { return currentEditor(); };
    findBar_->showStatus = [this](const QString& text, int timeout) { showStatus(text, timeout); };
    connect(tabs_, &QTabWidget::tabCloseRequested, this, [this](int index) { closeTab(index); });
    connect(tabs_, &QTabWidget::currentChanged, this, [this] {
        completionTimer_.stop();
        if (CodeEditor* editor = currentEditor()) {
            languageSelector_->setCurrentIndex(editor->isMel() ? 1 : 0);
        }
        scheduleAnalysis();
        scheduleSpelling();
    });

    // ---- 出力欄 ----
    output_ = new OutputPanel(services_.takeOutput);
    output_->view()->setLineNumbersVisible(preferences_.option("outputLineNumbers"));
    output_->setWrap(preferences_.option("outputWrap"));

    // ---- 上: 出力欄 / 下: タブ欄 ----
    splitter_ = new QSplitter(Qt::Vertical);
    splitter_->setObjectName("editorSplitter");
    splitter_->addWidget(output_);
    splitter_->addWidget(tabs_);
    splitter_->setSizes({scaled(350), scaled(350)});

    // ---- 中央の部品(分割欄 + 構文チェックの一覧) ----
    auto body = new QWidget(this);
    auto bodyLayout = new QVBoxLayout(body);
    bodyLayout->setContentsMargins(0, 0, 0, 0);
    bodyLayout->addWidget(splitter_);
    problems_ = new ProblemsPanel(body);
    problems_->onLineClicked = [this](int line) {
        CodeEditor* editor = currentEditor();
        const QTextBlock block = editor->document()->findBlockByNumber(line - 1);
        if (!block.isValid()) {
            return;
        }
        QTextCursor cursor = editor->textCursor();
        cursor.setPosition(block.position());
        editor->setTextCursor(cursor);
        editor->setFocus();
        editor->ensureCursorVisible();
    };
    bodyLayout->addWidget(problems_);
    setCentralWidget(body);

    // ---- 左のドック: Explorer(初期状態は非表示) ----
    explorerDock_ = new QDockWidget("EXPLORER", this);
    explorerDock_->setObjectName("explorerDock");
    explorer_ = new Explorer(explorerDock_);
    explorer_->onFileActivated = [this](const QString& path) { openFile(path); };
    explorerDock_->setWidget(explorer_);
    explorerDock_->setMinimumWidth(scaled(240));
    addDockWidget(Qt::LeftDockWidgetArea, explorerDock_);
    explorerDock_->hide();
}

void MainWindow::buildStatusBar() {
    completionStatus_ = new QLabel("Completion: ready (in Maya)");
    completionStatus_->setObjectName("completionStatus");
    statusBar()->addPermanentWidget(completionStatus_);

    // 選択肢の順番: 0=Python, 1=MEL
    languageSelector_ = new QComboBox;
    languageSelector_->setObjectName("languageMode");
    languageSelector_->addItems({"Python", "MEL"});
    languageSelector_->setToolTip("Language mode for the active tab");
    statusBar()->addPermanentWidget(languageSelector_);
    // activatedは利用者が選んだときだけ出る(プログラムからの変更では出ない)。
    connect(languageSelector_, QOverload<int>::of(&QComboBox::activated), this, [this](int index) {
        if (CodeEditor* editor = currentEditor()) {
            setLanguage(editor, index == 1 ? "mel" : "python");
        }
    });
}

void MainWindow::buildMenusAndToolbar() {
    // addActionの第3引数(this)はラムダの持ち主。第4引数のラムダがメニューを選んだときに呼ばれる。

    // ---- File ----
    QMenu* file = menuBar()->addMenu("File");
    file->addAction("New Python tab", this, [this] { newTab(); }, QKeySequence::New);
    file->addAction("New MEL tab", this, [this] { newTab("mel"); });
    QAction* openAction = file->addAction("Open…", this, [this] {
        openFile(QFileDialog::getOpenFileName(this, "Open script", {}, "Scripts (*.py *.mel);;All files (*)"));
    }, QKeySequence::Open);
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
    QAction* zoomIn = view->addAction("Zoom in", this, [this] { setZoom(preferences_.fontPixels() + 1); });
    zoomIn->setObjectName("zoomIn");
    zoomIn->setShortcuts({QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")});
    QAction* zoomOut = view->addAction("Zoom out", this, [this] { setZoom(preferences_.fontPixels() - 1); },
                                       QKeySequence("Ctrl+-"));
    zoomOut->setObjectName("zoomOut");
    QAction* zoomReset = view->addAction("Reset zoom", this, [this] { setZoom(EditorPreferences::kDefaultFontPixels); },
                                         QKeySequence("Ctrl+0"));
    zoomReset->setObjectName("zoomReset");
    QAction* showOutputAction = view->addAction("Show output only", this, [this] { showPanels(true, false); });
    QAction* showInputAction = view->addAction("Show input only", this, [this] { showPanels(false, true); });
    QAction* showBothAction = view->addAction("Show input and output", this, [this] { showPanels(true, true); });

    // ---- Tabs ----
    QMenu* tabMenu = menuBar()->addMenu("Tabs");
    QAction* nextTab = tabMenu->addAction("Next tab", this, [this] { switchTab(1); });
    nextTab->setShortcuts({QKeySequence("Ctrl+Tab"), QKeySequence("Ctrl+PgDown")});
    QAction* previousTab = tabMenu->addAction("Previous tab", this, [this] { switchTab(-1); });
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
    command->addAction("Refresh completion", this, [this] { refreshCompletion(); });

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

void MainWindow::setUpTimers() {
    // setSingleShot(true)のタイマーは、start()の後に1回だけtimeoutを出す。
    // 入力のたびにstart()し直すので、「最後の入力から○ms後」に1回だけ動く。
    completionTimer_.setSingleShot(true);
    completionTimer_.setInterval(250);
    connect(&completionTimer_, &QTimer::timeout, this, [this] { requestCompletion(false); });

    analysisTimer_.setSingleShot(true);
    analysisTimer_.setInterval(800);
    connect(&analysisTimer_, &QTimer::timeout, this, [this] { runAnalysis(); });

    spellingTimer_.setSingleShot(true);
    connect(&spellingTimer_, &QTimer::timeout, this, [this] {
        CodeEditor* editor = currentEditor();
        if (!preferences_.option("spellCheck") || !editor) {
            return;
        }
        editor->checkSpelling(spelling_);
        if (!spelling_.available()) {
            showStatus("English spell-check dictionary is unavailable on this Windows installation", 5000);
        }
    });

    // 入力中に全タブをJSONにしてディスクへ書かないよう、最後の入力から1.5秒以上経ってから保存する。
    sessionTimer_.setInterval(1000);
    connect(&sessionTimer_, &QTimer::timeout, this, [this] {
        if (!lastEdit_.isValid() || lastEdit_.elapsed() >= 1500) {
            saveSession();
        }
    });
    // Mayaの終了時にも必ず保存する。
    connect(qApp, &QCoreApplication::aboutToQuit, this, [this] { saveSession(); });
}

// ===========================================================================
// タブ
// ===========================================================================

CodeEditor* MainWindow::currentEditor() const {
    return static_cast<CodeEditor*>(tabs_->currentWidget());
}

CodeEditor* MainWindow::editorAt(int index) const {
    return static_cast<CodeEditor*>(tabs_->widget(index));
}

CodeEditor* MainWindow::newTab(const QString& language) {
    auto editor = new CodeEditor;
    applyPreferences(editor);
    tabs_->addTab(editor, "Untitled.py");  // addTabした時点で、タブ欄が所有者になる。
    setLanguage(editor, language);
    tabs_->setCurrentWidget(editor);
    editor->setFocus();

    editor->onCompletionRequested = [this] { requestCompletion(true); };
    editor->onRunRequested = [this] { runCode(false); };
    // キー入力の処理の途中でタブ(=キーを受け取った部品自身)を削除しないよう、処理の後へ予約する。
    // 予約の持ち主をeditorにしておけば、先にeditorが破棄された場合は予約も取り消される。
    editor->onCloseRequested = [this, editor] {
        QTimer::singleShot(0, editor, [this, editor] { closeTab(tabs_->indexOf(editor)); });
    };

    connect(editor, &QPlainTextEdit::textChanged, this, [this, editor] { onTextChanged(editor); });
    connect(editor->verticalScrollBar(), &QScrollBar::valueChanged, this, [this, editor] {
        if (editor == currentEditor()) {
            scheduleSpelling();  // スクロールで表示範囲が変わったので調べ直す。
        }
    });
    connect(editor, &QPlainTextEdit::cursorPositionChanged, this, [this, editor] {
        editor->hideCompletions();
        const QTextCursor cursor = editor->textCursor();
        showStatus(QString("Ln %1, Col %2  |  UTF-8").arg(cursor.blockNumber() + 1).arg(cursor.positionInBlock() + 1));
    });
    return editor;
}

void MainWindow::onTextChanged(CodeEditor* editor) {
    lastEdit_.restart();
    editor->clearSpelling();
    editor->hideCompletions();
    completionTimer_.stop();
    // 候補の確定による変更では、次の自動補完を予約しない(Enterで確定した後、次のEnterで改行できる)。
    if (editor == currentEditor() && !editor->isInsertingCompletion()) {
        completionTimer_.start();
    }
    updateTabTitle(editor);
    if (editor == currentEditor()) {
        scheduleAnalysis();
        scheduleSpelling();
    }
}

void MainWindow::closeTab(int index) {
    CodeEditor* editor = editorAt(index);
    if (!editor || !confirmClose(editor)) {
        return;
    }
    tabs_->removeTab(index);  // タブ欄から外すと所有者がいなくなるので、自分でdeleteする。
    delete editor;
    if (tabs_->count() == 0) {
        newTab();
    }
    currentEditor()->setFocus();
    updateExplorer();
}

bool MainWindow::confirmClose(CodeEditor* editor) {
    if (!editor->document()->isModified()) {
        return true;
    }
    const auto choice = QMessageBox::question(this, "Unsaved script", "Save changes before closing?",
                                              QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel);
    if (choice == QMessageBox::Discard) {
        return true;
    }
    return choice == QMessageBox::Save && saveFile(editor);
}

void MainWindow::switchTab(int direction) {
    const int count = tabs_->count();
    tabs_->setCurrentIndex((tabs_->currentIndex() + direction + count) % count);
    currentEditor()->setFocus();
}

void MainWindow::updateTabTitle(CodeEditor* editor) {
    const QString marker = editor->document()->isModified() ? " ●" : "";
    tabs_->setTabText(tabs_->indexOf(editor), editor->displayName() + marker);
}

void MainWindow::setLanguage(CodeEditor* editor, const QString& language) {
    editor->setLanguage(language);
    updateTabTitle(editor);
    if (editor == currentEditor()) {
        languageSelector_->setCurrentIndex(editor->isMel() ? 1 : 0);
        scheduleAnalysis();
    }
}

// ===========================================================================
// ファイル
// ===========================================================================

void MainWindow::openFile(const QString& path) {
    if (path.isEmpty()) {
        return;
    }
    const QString absolute = QFileInfo(path).absoluteFilePath();
    // 開いているファイルなら、そのタブを選ぶだけ。
    for (int i = 0; i < tabs_->count(); ++i) {
        if (QFileInfo(editorAt(i)->filePath()).absoluteFilePath() == absolute) {
            tabs_->setCurrentIndex(i);
            currentEditor()->setFocus();
            return;
        }
    }
    QFile file(absolute);
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, "Open", file.errorString());
        return;
    }
    QByteArray bytes = file.readAll();
    if (bytes.startsWith("\xef\xbb\xbf")) {
        bytes.remove(0, 3);  // UTF-8のBOM(先頭の印)を取り除く。
    }
    const QString text = QString::fromUtf8(bytes);
    // UTF-8として読み直して元と一致しなければ、UTF-8以外の文字コード。
    if (text.toUtf8() != bytes) {
        QMessageBox::warning(this, "Open", "Only UTF-8 files are supported");
        return;
    }
    CodeEditor* editor = newTab(QFileInfo(path).suffix().toLower() == "mel" ? "mel" : "python");
    editor->setPlainText(text);
    editor->setFilePath(absolute);
    editor->document()->setModified(false);
    updateTabTitle(editor);
    explorer_->addFolder(QFileInfo(absolute).absolutePath());
    updateExplorer();
    explorerDock_->show();
}

bool MainWindow::saveFile(CodeEditor* editor, bool saveAs) {
    QString path = saveAs ? QString() : editor->filePath();
    if (path.isEmpty()) {
        path = QFileDialog::getSaveFileName(this, "Save script", {}, editor->isMel() ? "MEL (*.mel)" : "Python (*.py)");
    }
    if (path.isEmpty()) {
        return false;  // キャンセルされた。
    }
    QString text = editor->toPlainText();
    if (preferences_.option("trimWhitespace")) {
        static const QRegularExpression trailingSpaces("[ \\t]+(?=\\n|$)");
        text.replace(trailingSpaces, QString());
    }
    if (preferences_.option("finalNewline") && !text.endsWith('\n')) {
        text += '\n';
    }
    // QSaveFileは一時ファイルへ書いてから置き換えるので、途中で失敗しても元のファイルは壊れない。
    QSaveFile file(path);
    const QByteArray bytes = text.toUtf8();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
        QMessageBox::warning(this, "Save", file.errorString());
        return false;
    }
    // 保存時の整形(末尾の空白など)を本文にも反映する。1回のUndoで戻せる。
    if (text != editor->toPlainText()) {
        QTextCursor cursor = editor->textCursor();
        const int position = cursor.position();
        cursor.beginEditBlock();
        cursor.select(QTextCursor::Document);
        cursor.insertText(text);
        cursor.endEditBlock();
        cursor.setPosition(qMin(position, editor->document()->characterCount() - 1));
        editor->setTextCursor(cursor);
    }
    editor->setFilePath(path);
    editor->document()->setModified(false);
    updateTabTitle(editor);
    explorer_->addFolder(QFileInfo(path).absolutePath());
    updateExplorer();
    return true;
}

void MainWindow::updateExplorer() {
    QStringList paths;
    for (int i = 0; i < tabs_->count(); ++i) {
        const QString path = editorAt(i)->filePath();
        if (!path.isEmpty()) {
            paths.append(path);
        }
    }
    explorer_->setOpenFiles(paths);
}

// ===========================================================================
// 未保存タブの自動復元
// ===========================================================================

void MainWindow::restoreSession() {
    SessionData data;
    switch (session_.open(&data)) {
    case SessionStore::OpenResult::Disabled:
    case SessionStore::OpenResult::NoFile:
        return;
    case SessionStore::OpenResult::CannotCreateDirectory:
        output_->appendNote("Tab recovery unavailable: cannot create recovery directory.");
        return;
    case SessionStore::OpenResult::Locked:
        output_->appendNote("Tab recovery is in use by another Maya. This window will not overwrite it.");
        return;
    case SessionStore::OpenResult::Unreadable:
        output_->appendNote("Tab recovery file could not be read. It has been preserved: " + session_.path());
        return;
    case SessionStore::OpenResult::Loaded:
        break;
    }

    // 最初のタブ(ようこそ)を消して、保存されていたタブを作り直す。
    while (tabs_->count() > 0) {
        QWidget* widget = tabs_->widget(0);
        tabs_->removeTab(0);
        delete widget;
    }
    for (const TabState& tab : data.tabs) {
        CodeEditor* editor = newTab(tab.language);
        editor->setPlainText(tab.text);
        editor->setFilePath(tab.path);
        // 元のファイルが削除・外部で変更されていても、復元した本文は未保存として残す。
        bool differsFromFile = false;
        if (!tab.path.isEmpty()) {
            QFile original(tab.path);
            differsFromFile = !original.open(QIODevice::ReadOnly)
                              || QString::fromUtf8(original.readAll()) != editor->toPlainText();
        }
        editor->document()->setModified(tab.modified || differsFromFile);
        updateTabTitle(editor);
        // 保存していた位置が本文より後ろ(ファイルが短くなった等)でも、範囲内に収める。
        const int limit = editor->document()->characterCount() - 1;
        QTextCursor cursor = editor->textCursor();
        cursor.setPosition(qBound(0, tab.anchor, limit));
        cursor.setPosition(qBound(0, tab.position, limit), QTextCursor::KeepAnchor);
        editor->setTextCursor(cursor);
    }
    explorer_->setRoots(data.folders);
    explorerDock_->setVisible(data.explorerVisible);
    updateExplorer();
    tabs_->setCurrentIndex(qBound(0, data.activeTab, tabs_->count() - 1));
    currentEditor()->setFocus();
}

bool MainWindow::saveSession() {
    if (!session_.canSave()) {
        return false;
    }
    SessionData data;
    data.activeTab = tabs_->currentIndex();
    data.folders = explorer_->roots();
    data.explorerVisible = !explorerDock_->isHidden();
    for (int i = 0; i < tabs_->count(); ++i) {
        CodeEditor* editor = editorAt(i);
        const QTextCursor cursor = editor->textCursor();
        TabState tab;
        tab.text = editor->toPlainText();
        tab.path = editor->filePath();
        tab.language = editor->language();
        tab.modified = editor->document()->isModified();
        tab.position = cursor.position();
        tab.anchor = cursor.anchor();
        data.tabs.append(tab);
    }
    QString error;
    if (!session_.save(data, &error)) {
        showStatus("Tab recovery save failed: " + error);
        return false;
    }
    return true;
}

void MainWindow::closeEvent(QCloseEvent* event) {
    // 自動保存できれば、未保存のタブも確認なしで閉じてよい(次回復元される)。
    if (saveSession()) {
        event->accept();
        return;
    }
    for (int i = 0; i < tabs_->count(); ++i) {
        if (!confirmClose(editorAt(i))) {
            event->ignore();
            return;
        }
    }
    event->accept();
}

// ===========================================================================
// 実行と表示
// ===========================================================================

void MainWindow::runCode(bool all) {
    CodeEditor* editor = currentEditor();
    QString source = editor->toPlainText();
    if (!all && editor->textCursor().hasSelection()) {
        source = normalizeSelectedText(editor->textCursor().selectedText());
    }
    QString result;
    if (editor->isMel()) {
        result = services_.runMel ? services_.runMel(source) : "MEL execution is unavailable";
    } else {
        result = services_.runPython ? services_.runPython(source) : "Python execution is unavailable";
    }
    if (!result.isEmpty()) {
        output_->appendNote(result);
    }
    output_->flush();
}

void MainWindow::clearInput() {
    CodeEditor* editor = currentEditor();
    if (!editor) {
        return;
    }
    // 文書の編集として消すので、Ctrl+Zで本文を取り戻せる。
    QTextCursor cursor = editor->textCursor();
    cursor.select(QTextCursor::Document);
    cursor.removeSelectedText();
    editor->setTextCursor(cursor);
}

void MainWindow::showPanels(bool output, bool input) {
    output_->setVisible(output);
    tabs_->setVisible(input);
    splitter_->setSizes({output ? 1 : 0, input ? 1 : 0});
}

void MainWindow::showGoToLine() {
    // 行番号を入れる欄が既にあれば、そこへフォーカスを戻すだけ。
    if (auto existing = findChild<QLineEdit*>("lineJump")) {
        existing->setFocus();
        existing->selectAll();
        return;
    }
    // 出力欄にフォーカスがあれば出力欄、それ以外はコード欄が対象。
    QPlainTextEdit* target = output_->view()->hasFocus() ? static_cast<QPlainTextEdit*>(output_->view())
                                                         : static_cast<QPlainTextEdit*>(currentEditor());
    auto input = new QLineEdit(this);
    input->setObjectName("lineJump");
    input->setPlaceholderText("Go to line (Enter / Esc)");
    input->setValidator(new QIntValidator(1, target->document()->blockCount(), input));
    input->setText(QString::number(target->textCursor().blockNumber() + 1));
    statusBar()->addWidget(input, 1);

    // 入力欄を片付けて、対象の欄へフォーカスを戻す。
    // deleteLaterは「今のイベント処理が終わった後で破棄する」予約(処理中の自分をすぐ消さないため)。
    auto finish = [this, input, target] {
        statusBar()->removeWidget(input);
        input->setObjectName(QString());
        input->hide();
        input->deleteLater();
        target->setFocus(Qt::ShortcutFocusReason);
    };
    // 対象の欄(タブ)が先に閉じられたら、入力欄も片付ける。
    connect(target, &QObject::destroyed, input, &QObject::deleteLater);
    connect(input, &QLineEdit::returnPressed, target, [target, input, finish] {
        const QTextBlock block = target->document()->findBlockByNumber(input->text().toInt() - 1);
        if (!block.isValid()) {
            return;
        }
        QTextCursor cursor = target->textCursor();
        cursor.setPosition(block.position());
        target->setTextCursor(cursor);
        target->centerCursor();
        finish();
    });
    auto cancel = new QShortcut(QKeySequence(Qt::Key_Escape), input);
    cancel->setContext(Qt::WidgetWithChildrenShortcut);
    connect(cancel, &QShortcut::activated, target, finish);
    input->show();
    input->setFocus();
    input->selectAll();
}

void MainWindow::setZoom(int pixels) {
    preferences_.setFontPixels(pixels);
    applyZoom();
}

void MainWindow::applyZoom() {
    const int size = preferences_.fontPixels();  // 10〜28に丸めた値。
    // 保存する値は100%時のピクセル数。表示するときに拡大率を掛けるので、4Kでも同じ見た目の大きさになる。
    setStyleSheet(QString("QPlainTextEdit#codeEditor,QPlainTextEdit#output{background:%1;color:%2;"
                          "font-family:'Consolas';selection-background-color:%3;selection-color:%2;}"
                          "QPlainTextEdit#codeEditor{font-size:%4px;} QPlainTextEdit#output{font-size:%5px;}")
                      .arg(QString(theme::kBackground))
                      .arg(QString(theme::kText))
                      .arg(QString(theme::kSelection))
                      .arg(scaled(size))
                      .arg(scaled(size - 2)));
    showStatus(QString("Font size: %1 px").arg(size), 2000);
}

void MainWindow::showStatus(const QString& text, int timeout) {
    statusBar()->showMessage(text, timeout);
}

void MainWindow::refreshOutputNow() {
    output_->refreshNow();
}

// ===========================================================================
// 補完・構文チェック・スペル
// ===========================================================================

void MainWindow::refreshCompletion() {
    if (services_.refreshCompletion) {
        services_.refreshCompletion();
    }
    completionStatus_->setText("Completion: ready (in Maya)");
}

void MainWindow::requestCompletion(bool force) {
    CodeEditor* editor = currentEditor();
    if (!services_.complete || !editor || !editor->hasFocus() || editor->isMel()) {
        return;
    }
    QTextCursor cursor = editor->textCursor();
    // 直前の1文字がドットかを調べる(本文全体をコピーしない)。
    QTextCursor preceding = cursor;
    preceding.movePosition(QTextCursor::PreviousCharacter, QTextCursor::KeepAnchor);
    const bool afterDot = preceding.selectedText() == ".";
    if (!force) {
        // 自動補完は、設定でオンの場合だけ。名前の入力途中でもドットの直後でもなければ出さない。
        const bool enabled = afterDot ? preferences_.option("completeDot") : preferences_.option("completeLetters");
        if (!enabled) {
            return;
        }
        if (editor->completionPrefix().isEmpty() && !afterDot) {
            return;
        }
    }
    if (cursor.position() > kCompletionDocumentLimit) {
        completionStatus_->setText("Completion: document limit (200k)");
        return;
    }
    // 文書の先頭からカーソルまでを渡す。
    cursor.setPosition(0, QTextCursor::KeepAnchor);
    const QByteArray json = services_.complete(normalizeSelectedText(cursor.selectedText()));
    const QJsonObject response = QJsonDocument::fromJson(json).object();
    if (response.contains("error")) {
        completionStatus_->setText("Completion: " + response["error"].toString());
        return;
    }

    QList<CompletionItem> items;
    for (const QJsonValue& value : response["items"].toArray()) {
        const QJsonObject item = value.toObject();
        const QString kind = item["kind"].toString();
        if (kind == "keyword" && !preferences_.option("includeKeywords")) {
            continue;
        }
        if (kind == "builtin" && !preferences_.option("includeBuiltins")) {
            continue;
        }
        items.append({item["name"].toString(), item["detail"].toString()});
    }
    completionStatus_->setText("Completion: ready (in Maya)");
    editor->showCompletions(items);
    // import文の候補を別スレッドで集めている途中なら、少し後に問い合わせ直す(追加の入力は不要)。
    if (items.isEmpty() && response["pending"].toBool()) {
        completionTimer_.start(250);
    }
}

void MainWindow::scheduleAnalysis() {
    analysisTimer_.stop();
    problems_->clear();
    CodeEditor* editor = currentEditor();
    const bool enabled = preferences_.option("staticAnalysis") && editor && !editor->isMel();
    problems_->setVisible(enabled);
    if (enabled) {
        problems_->showWaiting();
        analysisTimer_.start();
    }
}

void MainWindow::runAnalysis() {
    CodeEditor* editor = currentEditor();
    if (!preferences_.option("staticAnalysis") || !services_.analyze || !editor || editor->isMel()) {
        return;
    }
    problems_->showResult(services_.analyze(editor->toPlainText()));
}

void MainWindow::scheduleSpelling() {
    spellingTimer_.stop();
    if (!preferences_.option("spellCheck")) {
        for (int i = 0; i < tabs_->count(); ++i) {
            editorAt(i)->clearSpelling();
        }
        return;
    }
    if (currentEditor()) {
        spellingTimer_.start(450);
    }
}

// ===========================================================================
// 設定
// ===========================================================================

void MainWindow::applyPreferences(CodeEditor* editor) {
    editor->setSmartIndent(preferences_.option("smartIndent"));
    editor->setBackspaceToIndentStop(preferences_.option("backspaceIndent"));
    editor->setWhitespaceVisible(preferences_.option("whitespace"));
}

void MainWindow::onOptionToggled(const QString& key, bool enabled) {
    if (!preferences_.setOption(key, enabled)) {
        showStatus("Could not save editor preferences");
    }
    for (int i = 0; i < tabs_->count(); ++i) {
        applyPreferences(editorAt(i));
        editorAt(i)->hideCompletions();
    }
    // 設定ごとに、すぐ反映が必要なもの。
    if (key == "staticAnalysis") {
        scheduleAnalysis();
    } else if (key == "outputLineNumbers") {
        output_->view()->setLineNumbersVisible(enabled);
    } else if (key == "outputWrap") {
        output_->setWrap(enabled);
    } else if (key == "spellCheck") {
        scheduleSpelling();
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
    for (int i = 0; i < tabs_->count(); ++i) {
        applyPreferences(editorAt(i));
        editorAt(i)->hideCompletions();
    }
    output_->view()->setLineNumbersVisible(preferences_.option("outputLineNumbers"));
    output_->setWrap(preferences_.option("outputWrap"));
    scheduleAnalysis();
    scheduleSpelling();
    applyZoom();

    if (saved) {
        showStatus("Preferences reset to defaults", 3000);
    } else {
        showStatus("Could not save editor preferences");
    }
}

}  // namespace hedit
