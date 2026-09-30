/** @file main_window.cpp
 * @brief MainWindowの実装(メニューとツールバーはmain_window_menus.cpp)。
 * @details Qtの基本:
 * - ``new 部品(親)``で作った部品は、親が破棄されるときに一緒に破棄される。レイアウトやタブへ
 *   追加した部品も、追加先の親が所有者になる。そのため、ここではほとんどdeleteを書かない。
 * - ``connect(送り手, &シグナル, 持ち主, ラムダ)``は「送り手のシグナルが出たらラムダを呼ぶ」という接続。
 *   持ち主(ここでは主にthis)が破棄されると接続は自動で外れる。ラムダの[this]は、このウィンドウを使う印。
 * - QTimer::singleShot(0, ...)は「今の処理(キー入力の処理など)が終わった後で実行する」予約。
 */
#include "editor/main_window.h"
#include "core/script_file.h"
#include "editor/code_editor.h"
#include "editor/editor_tabs.h"
#include "editor/explorer.h"
#include "editor/find_bar.h"
#include "editor/output_panel.h"
#include "editor/problems_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QApplication>
#include <QCloseEvent>
#include <QComboBox>
#include <QCompleter>
#include <QDockWidget>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QIntValidator>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QScrollBar>
#include <QShortcut>
#include <QSplitter>
#include <QStatusBar>
#include <QTabBar>
#include <QTextBlock>
#include <QVBoxLayout>

namespace hedit {
namespace {

/// 新しいタブ(復元するものが無いとき)の最初の本文。
constexpr const char* kWelcomeText =
    "import maya.cmds as cmds\n\n# Ctrl+Space: completion    Ctrl+Enter: run\nprint(cmds.ls(selection=True))\n";

/// 補完へ渡す本文の上限(文字数)。これを超える位置では補完しない。
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
    tabs_->updateTitle(first);
    restoreSession();

    sessionTimer_.start();
    refreshCompletion();
    scheduleAnalysis();
}

MainWindow::~MainWindow() {
    saveSession();
    // この後、子の部品が破棄される途中でシグナルを出しても、破棄済みのメンバーを使わないよう接続を外す。
    QObject::disconnect(tabs_, nullptr, this, nullptr);
    QObject::disconnect(tabs_->tabBar(), nullptr, this, nullptr);
    for (CodeEditor* editor : tabs_->editors()) {
        QObject::disconnect(editor, nullptr, this, nullptr);
        QObject::disconnect(editor->document(), nullptr, this, nullptr);
        QObject::disconnect(editor->verticalScrollBar(), nullptr, this, nullptr);
    }
    explorer_->onRootsChanged = nullptr;
}

void MainWindow::buildLayout() {
    // ---- タブ欄と検索バー ----
    tabs_ = new EditorTabs;
    findBar_ = new FindBar(tabs_);  // タブ欄の子として右上に重ねる。
    findBar_->currentEditor = [this] { return currentEditor(); };
    findBar_->showStatus = [this](const QString& text, int timeout) { showStatus(text, timeout); };
    connect(tabs_, &QTabWidget::tabCloseRequested, this, [this](int index) { closeTab(index); });
    connect(tabs_, &QTabWidget::currentChanged, this, [this] {
        markSessionDirty();
        completionTimer_.stop();
        if (CodeEditor* editor = currentEditor()) {
            languageSelector_->setCurrentIndex(editor->isMel() ? 1 : 0);
        }
        scheduleAnalysis();
        scheduleSpelling();
        findBar_->scheduleRefresh();  // 検索バーを開いていれば、新しいタブで件数と強調を出し直す。
    });
    // ドラッグでタブを並べ替えたら、その順番も自動保存する。
    connect(tabs_->tabBar(), &QTabBar::tabMoved, this, [this] { markSessionDirty(); });

    // ---- 出力欄 ----
    output_ = new OutputPanel(services_.takeOutput);
    output_->view()->setLineNumbersVisible(preferences_.option(option::kOutputLineNumbers));
    output_->setWrap(preferences_.option(option::kOutputWrap));

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
    explorer_->onRootsChanged = [this] { markSessionDirty(); };
    explorerDock_->setWidget(explorer_);
    explorerDock_->setMinimumWidth(scaled(240));
    addDockWidget(Qt::LeftDockWidgetArea, explorerDock_);
    explorerDock_->hide();
    connect(explorerDock_, &QDockWidget::visibilityChanged, this, [this] { markSessionDirty(); });
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
        if (!preferences_.option(option::kSpellCheck) || !editor) {
            return;
        }
        editor->checkSpelling(spelling_);
        if (!spelling_.available()) {
            showStatus("English spell-check dictionary is unavailable on this Windows installation", 5000);
        }
    });

    // 入力中に全タブをJSONにしてディスクへ書かないよう、最後の入力から1.5秒以上経ってから保存する。
    // 変化が無ければsaveSession()は何もしない(全タブをJSONにする処理も省く)。
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
    return tabs_->currentEditor();
}

CodeEditor* MainWindow::newTab(const QString& language) {
    auto editor = new CodeEditor;
    applyPreferences(editor);
    tabs_->addTab(editor, "Untitled.py");  // addTabした時点で、タブ欄が所有者になる。
    setLanguage(editor, language);
    tabs_->setCurrentWidget(editor);
    editor->setFocus();
    markSessionDirty();

    editor->onCompletionRequested = [this] { requestCompletion(true); };
    editor->onHoverRequested = [this, editor](int end) { return describeName(editor, end); };
    editor->onRunRequested = [this] { runCode(false); };
    // キー入力の処理の途中でタブ(=キーを受け取った部品自身)を削除しないよう、処理の後へ予約する。
    // 予約の持ち主をeditorにしておけば、先にeditorが破棄された場合は予約も取り消される。
    editor->onCloseRequested = [this, editor] {
        QTimer::singleShot(0, editor, [this, editor] { closeTab(tabs_->indexOf(editor)); });
    };

    connect(editor, &QPlainTextEdit::textChanged, this, [this, editor] { onTextChanged(editor); });
    connect(editor->document(), &QTextDocument::modificationChanged, this, [this] { markSessionDirty(); });
    connect(editor->verticalScrollBar(), &QScrollBar::valueChanged, this, [this, editor] {
        if (editor == currentEditor()) {
            scheduleSpelling();  // スクロールで表示範囲が変わったので調べ直す。
        }
    });
    connect(editor, &QPlainTextEdit::cursorPositionChanged, this, [this, editor] {
        markSessionDirty();  // カーソルと選択の位置も復元するので保存する。
        editor->hideCompletions();
        const QTextCursor cursor = editor->textCursor();
        showStatus(QString("Ln %1, Col %2  |  UTF-8").arg(cursor.blockNumber() + 1).arg(cursor.positionInBlock() + 1));
    });
    return editor;
}

void MainWindow::onTextChanged(CodeEditor* editor) {
    lastEdit_.restart();
    markSessionDirty();
    editor->clearSpelling();
    editor->hideCompletions();
    completionTimer_.stop();
    // 候補の確定による変更では、次の自動補完を予約しない(Enterで確定した後、次のEnterで改行できる)。
    if (editor == currentEditor() && !editor->isInsertingCompletion()) {
        completionTimer_.start();
    }
    tabs_->updateTitle(editor);
    if (editor == currentEditor()) {
        scheduleAnalysis();
        scheduleSpelling();
        findBar_->scheduleRefresh();  // 本文が変わったので、検索の件数と強調を出し直す。
    }
}

void MainWindow::closeTab(int index) {
    CodeEditor* editor = tabs_->editorAt(index);
    if (!editor || !confirmClose(editor)) {
        return;
    }
    tabs_->removeTab(index);  // タブ欄から外すと所有者がいなくなるので、自分でdeleteする。
    delete editor;
    markSessionDirty();
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

void MainWindow::setLanguage(CodeEditor* editor, const QString& language) {
    editor->setLanguage(language);
    tabs_->updateTitle(editor);
    markSessionDirty();
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
    const int opened = tabs_->indexOfFile(absolute);
    if (opened >= 0) {
        tabs_->setCurrentIndex(opened);
        currentEditor()->setFocus();
        return;
    }
    QString text;
    QString error;
    if (!readScriptFile(absolute, &text, &error)) {
        QMessageBox::warning(this, "Open", error);
        return;
    }
    CodeEditor* editor = newTab(QFileInfo(path).suffix().toLower() == "mel" ? "mel" : "python");
    editor->setPlainText(text);
    editor->setFilePath(absolute);
    editor->document()->setModified(false);
    tabs_->updateTitle(editor);
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
    const QString text = formatForSave(editor->toPlainText(), preferences_.option(option::kTrimWhitespace),
                                       preferences_.option(option::kFinalNewline));
    QString error;
    if (!writeScriptFile(path, text, &error)) {
        QMessageBox::warning(this, "Save", error);
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
    tabs_->updateTitle(editor);
    markSessionDirty();
    explorer_->addFolder(QFileInfo(path).absolutePath());
    updateExplorer();
    return true;
}

void MainWindow::updateExplorer() {
    explorer_->setOpenFiles(tabs_->filePaths());
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
        tabs_->updateTitle(editor);
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
    if (!sessionDirty_) {
        return true;  // 前回の保存から何も変わっていない。
    }
    SessionData data;
    data.activeTab = tabs_->currentIndex();
    data.folders = explorer_->roots();
    data.explorerVisible = !explorerDock_->isHidden();
    for (CodeEditor* editor : tabs_->editors()) {
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
    sessionDirty_ = false;
    return true;
}

void MainWindow::closeEvent(QCloseEvent* event) {
    // 自動保存できれば、未保存のタブも確認なしで閉じてよい(次回復元される)。
    if (saveSession()) {
        event->accept();
        return;
    }
    for (CodeEditor* editor : tabs_->editors()) {
        if (!confirmClose(editor)) {
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
    // 検索バーの入力欄も、エディターと同じフォントと大きさにする(VS Codeと違い、文字サイズの変更に追従する)。
    QFont font("Consolas");
    font.setPixelSize(scaled(size));
    findBar_->setEditorFont(font);
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
        const bool enabled = afterDot ? preferences_.option(option::kCompleteDot)
                                      : preferences_.option(option::kCompleteLetters);
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
    const CompletionResult result = services_.complete(normalizeSelectedText(cursor.selectedText()));
    if (!result.error.isEmpty()) {
        completionStatus_->setText("Completion: " + result.error);
        return;
    }

    QList<CompletionItem> items;
    for (const CompletionItem& item : result.items) {
        if (item.kind == "keyword" && !preferences_.option(option::kIncludeKeywords)) {
            continue;
        }
        if (item.kind == "builtin" && !preferences_.option(option::kIncludeBuiltins)) {
            continue;
        }
        items.append(item);
    }
    completionStatus_->setText("Completion: ready (in Maya)");
    editor->showCompletions(items);
    // import文の候補を別スレッドで集めている途中なら、少し後に問い合わせ直す(追加の入力は不要)。
    if (items.isEmpty() && result.pending) {
        completionTimer_.start(250);
    }
}

HoverInfo MainWindow::describeName(CodeEditor* editor, int end) {
    // 補完と同じ上限を超える大きな本文や、MELのタブでは説明を出さない。
    if (!services_.describe || editor->isMel() || editor->document()->characterCount() > kCompletionDocumentLimit) {
        return HoverInfo();
    }
    return services_.describe(editor->toPlainText(), end);
}

void MainWindow::scheduleAnalysis() {
    analysisTimer_.stop();
    problems_->clear();
    CodeEditor* editor = currentEditor();
    const bool enabled = preferences_.option(option::kStaticAnalysis) && editor && !editor->isMel();
    problems_->setVisible(enabled);
    if (enabled) {
        problems_->showWaiting();
        analysisTimer_.start();
    }
}

void MainWindow::runAnalysis() {
    CodeEditor* editor = currentEditor();
    if (!preferences_.option(option::kStaticAnalysis) || !services_.analyze || !editor || editor->isMel()) {
        return;
    }
    problems_->showResult(services_.analyze(editor->toPlainText()));
}

void MainWindow::scheduleSpelling() {
    spellingTimer_.stop();
    if (!preferences_.option(option::kSpellCheck)) {
        for (CodeEditor* editor : tabs_->editors()) {
            editor->clearSpelling();
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
    editor->setSmartIndent(preferences_.option(option::kSmartIndent));
    editor->setBackspaceToIndentStop(preferences_.option(option::kBackspaceIndent));
    editor->setWhitespaceVisible(preferences_.option(option::kWhitespace));
}

void MainWindow::onOptionToggled(const QString& key, bool enabled) {
    if (!preferences_.setOption(key, enabled)) {
        showStatus("Could not save editor preferences");
    }
    for (CodeEditor* editor : tabs_->editors()) {
        applyPreferences(editor);
        editor->hideCompletions();
    }
    // 設定ごとに、すぐ反映が必要なもの。
    if (key == option::kStaticAnalysis) {
        scheduleAnalysis();
    } else if (key == option::kOutputLineNumbers) {
        output_->view()->setLineNumbersVisible(enabled);
    } else if (key == option::kOutputWrap) {
        output_->setWrap(enabled);
    } else if (key == option::kSpellCheck) {
        scheduleSpelling();
    }
}

}  // namespace hedit
