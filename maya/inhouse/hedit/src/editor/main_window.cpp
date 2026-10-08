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
#include "editor/code_assist.h"
#include "editor/code_editor.h"
#include "editor/diff_dialog.h"
#include "editor/editor_tabs.h"
#include "editor/explorer.h"
#include "editor/find_bar.h"
#include "editor/hover_popup.h"
#include "editor/outline_panel.h"
#include "editor/output_panel.h"
#include "editor/problems_panel.h"
#include "editor/quick_pick.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QApplication>
#include <QCloseEvent>
#include <QComboBox>
#include <QCompleter>
#include <QDir>
#include <QDirIterator>
#include <QPointer>
#include <QDockWidget>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHideEvent>
#include <QIntValidator>
#include <QLabel>
#include <QLineEdit>
#include <QMenu>
#include <QMessageBox>
#include <QScrollBar>
#include <QSet>
#include <QShortcut>
#include <QSplitter>
#include <QStatusBar>
#include <QTabBar>
#include <QTextBlock>
#include <QVBoxLayout>
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>

namespace hedit {
namespace {

/// コード欄の動的プロパティ: 復元ファイルでのタブの識別子(本文のファイル名 tabs/<id>.txt)。
constexpr const char* kSessionIdProperty = "sessionId";

/// コード欄の動的プロパティ: 最後に本文のファイルへ書いたときの文書の版(QTextDocument::revision)。
/// 今の版と同じなら本文は変わっていないので、自動保存で本文のファイルを書き直さない。-1は未保存。
constexpr const char* kSavedRevisionProperty = "sessionSavedRevision";

/// アウトラインの表示の状態を保存する名前(EditorPreferences::flag)。
constexpr const char* kOutlineVisibleFlag = "outlineVisible";

/// ファイル名で開く(Ctrl+P)で、フォルダーから集めるファイルの上限。
constexpr int kMaximumPickerFiles = 5000;

/// ファイル名で開くの一覧を、集め直さずに使う時間(ミリ秒)。過ぎたら、覚えている一覧を出しつつ裏で集め直す。
constexpr int kFileListLifetime = 30000;

/// 本文・タブの並びなどの最後の変化から、自動保存するまでの時間(ミリ秒)。落ちても失うのはこの時間分まで。
constexpr int kSessionSaveDelay = 1500;

/// カーソル・選択の位置だけの変化を、まとめて保存するまでの時間(ミリ秒)。
constexpr int kCursorSaveDelay = 30000;

/// 保存に失敗したときの、次の自動保存までの間隔の上限(ミリ秒)。1.5秒から倍々に延ばす。
constexpr int kMaximumSaveRetryDelay = 60000;

/// カーソルが止まってから、アウトラインのカーソルの行の項目を選ぶまでの時間(ミリ秒)。
constexpr int kOutlineSelectDelay = 100;

/// コード欄の動的プロパティ: 本文の読み込みを遅らせている(まだ文書が空の)タブならtrue。テストやPySideから参照できる。
constexpr const char* kTextPendingProperty = "textPending";

/// 新しいタブ(復元するものが無いとき)の最初の本文。
constexpr const char* kWelcomeText =
    "import maya.cmds as cmds\n\n# Ctrl+Space: completion    Ctrl+Enter: run\nprint(cmds.ls(selection=True))\n";

/** @brief tabs.jsonと同じフォルダーのpreferences.jsonのパス。
 * @param sessionPath tabs.jsonのパス。空なら保存しない。
 * @return preferences.jsonの絶対パス。sessionPathが空なら空。
 */
QString preferencesPath(const QString& sessionPath) {
    if (sessionPath.isEmpty()) {
        return QString();
    }
    return QFileInfo(sessionPath).absolutePath() + "/preferences.json";
}

/** @brief QTextCursorの選択文字列を、普通の改行の文字列にする(実行する選択範囲に使う)。
 * @param text selectedText()の戻り値。行の区切りがU+2029(段落区切り)になっている。
 *        Shift+Enterや以前の貼り付けで入ったU+2028(行区切り)も含みうる。
 * @return 改行を``\n``にした文字列。
 */
QString normalizeSelectedText(QString text) {
    return text.replace(QChar(0x2029), '\n').replace(QChar(0x2028), '\n');
}

/** @brief ファイル名で開く(Ctrl+P)の一覧を集める。別スレッドで呼ぶ(画面の部品には触れない)。
 * @param recentFiles 最近開いたファイル(新しい順)。存在するものだけを先頭に並べる。
 * @param roots Explorerのルートフォルダー。その下の``*.py``・``*.mel``を集める。
 * @param cancel trueになったら途中でやめる。
 * @return 一覧(最近開いたファイル、続いてフォルダーのファイルを見つけた順。全体で最大kMaximumPickerFiles件)。
 * @details 隠しフォルダー(名前が``.``で始まる。.gitなど)と``__pycache__``は、中へ降りずに飛ばす。
 * 同じファイルは大文字小文字を区別せずに1回だけ載せる(QSetで調べる)。並び順は、以前の
 * QDirIteratorの再帰と同じ(フォルダーの中の順に読み、フォルダーを見つけたらその中を先に読む)。
 */
QList<QuickPickItem> collectFiles(const QStringList& recentFiles, const QStringList& roots,
                                  const std::atomic_bool& cancel) {
    QList<QuickPickItem> items;
    QSet<QString> seen;  // 大文字小文字をそろえた(toCaseFolded)絶対パス。
    auto add = [&items, &seen](const QFileInfo& info, const QString& note) {
        const QString absolute = info.absoluteFilePath();
        const QString key = absolute.toCaseFolded();
        if (seen.contains(key)) {
            return;
        }
        seen.insert(key);
        items.append({info.fileName(), note.isEmpty() ? info.absolutePath() : note, "file", absolute});
    };
    for (const QString& path : recentFiles) {
        const QFileInfo info(path);
        if (info.isFile()) {
            add(info, "recently opened  " + info.absolutePath());
        }
    }
    // フォルダーの中を見つけた順に再帰して集める(ラムダの中で自分を呼ぶため、std::functionに入れる)。
    std::function<void(const QString&)> visit = [&](const QString& directory) {
        // QDir::AllDirsは、名前の絞り込み(*.py)に関係なくフォルダーも返す。QDir::Hiddenを付けないので、
        // 隠し属性のファイル・フォルダーは返らない(以前のQDirIteratorと同じ)。
        QDirIterator entries(directory, {"*.py", "*.mel"}, QDir::Files | QDir::AllDirs | QDir::NoDotAndDotDot);
        while (entries.hasNext() && items.size() < kMaximumPickerFiles && !cancel) {
            entries.next();
            const QFileInfo info = entries.fileInfo();
            const QString name = info.fileName();
            // 名前が.で始まるもの(.gitなど)と__pycache__を含むものは飛ばす。フォルダーなら中へも降りない。
            if (name.startsWith('.') || name.contains("__pycache__")) {
                continue;
            }
            if (info.isDir()) {
                if (!info.isSymLink()) {  // リンク先のフォルダーへは降りない(以前のQDirIteratorと同じ)。
                    visit(info.filePath());
                }
                continue;
            }
            // リンク切れのリンクは、以前と同じくファイルとして扱わない(リンクでなければ、もう一度は調べない)。
            if (info.isSymLink() && !info.isFile()) {
                continue;
            }
            add(info, QString());
        }
    };
    for (const QString& root : roots) {
        if (items.size() >= kMaximumPickerFiles || cancel) {
            break;
        }
        visit(root);
    }
    return items;
}

}  // namespace

/** @brief ファイル名で開く(Ctrl+P)の一覧を、別スレッドで集める。
 * @details 頼まれたら最新の頼みを1つだけ持ち、スレッドで集めて、コンストラクターで受け取った関数で返す。
 * その関数は別スレッドから呼ばれるので、画面の部品には直接触れず、画面のスレッドへ送ること。
 * 集めている途中で新しい頼みが来たら、古い方は途中でやめる。
 * 破棄するときはスレッドを止めて合流する(hedit.mllのアンロード後にスレッドのコードが動かないように)。
 */
class FileLister {
public:
    /// 集め終えたときに呼ぶ関数(頼んだときの印, 一覧, かかったミリ秒)。
    using Callback = std::function<void(const QStringList&, const QList<QuickPickItem>&, qint64)>;

    /** @brief スレッドを始める。 @param onListed 集め終えたときに呼ぶ関数。 */
    explicit FileLister(Callback onListed) : onListed_(std::move(onListed)), worker_(&FileLister::run, this) {}

    /** @brief 集めている途中ならやめさせ、スレッドを止めて合流する。 */
    ~FileLister() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
            cancel_ = true;
        }
        wake_.notify_all();
        worker_.join();
    }

    /** @brief 一覧を集めるよう頼む。集めている途中の古い頼みはやめさせる。
     * @param key 結果と一緒に返す印(頼んだときのフォルダーと最近開いたファイル)。
     * @param recentFiles 最近開いたファイル。
     * @param roots Explorerのルートフォルダー。
     */
    void request(const QStringList& key, const QStringList& recentFiles, const QStringList& roots) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            job_ = {key, recentFiles, roots};
            hasJob_ = true;
            cancel_ = true;  // 鍵の中で立てる(スレッドは次の頼みを取るとき、鍵の中で下ろす)。
        }
        wake_.notify_one();
    }

private:
    /** @brief 1回分の頼み。 */
    struct Job {
        QStringList key;          ///< 結果と一緒に返す印。
        QStringList recentFiles;  ///< 最近開いたファイル。
        QStringList roots;        ///< ルートフォルダー。
    };

    /** @brief 別スレッドの本体。頼みが来るまで眠り、来たら集めて返す。 */
    void run() {
        while (true) {
            Job job;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                wake_.wait(lock, [this] { return stopping_ || hasJob_; });
                if (stopping_) {
                    return;
                }
                job = job_;
                hasJob_ = false;
                cancel_ = false;
            }
            QElapsedTimer timer;
            timer.start();
            const QList<QuickPickItem> items = collectFiles(job.recentFiles, job.roots, cancel_);
            if (!cancel_) {
                onListed_(job.key, items, timer.elapsed());
            }
        }
    }

    Callback onListed_;              ///< 集め終えたときに呼ぶ関数。
    std::mutex mutex_;               ///< 下の頼みと状態を守る鍵。
    std::condition_variable wake_;   ///< スレッドを起こす合図。
    Job job_;                        ///< 次に集める頼み。
    bool hasJob_ = false;            ///< 次の頼みがあるか。
    bool stopping_ = false;          ///< trueでスレッドを止める。
    std::atomic_bool cancel_{false}; ///< trueで集めている途中の頼みをやめる。
    std::thread worker_;             ///< スレッド。他のメンバーを作った後で始めるよう、最後に置く。
};

// ===========================================================================
// 組み立て
// ===========================================================================

MainWindow::MainWindow(QWidget* parent, const EditorServices& services)
    : QMainWindow(parent),
      services_(services),
      preferences_(preferencesPath(services.sessionPath)),
      session_(services.sessionPath) {
    QElapsedTimer openTimer;  // 開くのにかかった時間(計測用。動的プロパティopenMillisecondsに入れる)。
    openTimer.start();
    setObjectName("hedit");
    setWindowTitle("hedit - Python / MEL");
    resize(scaled(1050), scaled(740));
    // 親があれば(Mayaのドックの中なら)部品として、無ければ独立したウィンドウとして表示する。
    setWindowFlags(parent ? Qt::Widget : Qt::Window);

    buildLayout();
    buildStatusBar();
    // 入力の補助。一覧とステータスバーの部品を使うので、それらを作った後に作る。
    CodeAssist::Context context;
    context.currentEditor = [this] { return currentEditor(); };
    context.editors = [this] { return tabs_->editors(); };
    context.showStatus = [this](const QString& text, int timeout) { showStatus(text, timeout); };
    assist_ = std::make_unique<CodeAssist>(services_, preferences_, problems_, completionStatus_, context);
    // 保存済みの文字サイズを表示に反映する。値は変えていないので、preferences.jsonへは書かない。
    applyZoom();
    buildMenusAndToolbar();
    limitShortcutsToThisWindow();
    setUpTimers();

    restoreSession();
    if (tabs_->count() == 0) {
        // 復元するタブが無いときだけ、ようこそのタブを作る。
        CodeEditor* first = newTab();
        first->setPlainText(kWelcomeText);
        first->document()->setModified(false);
        tabs_->updateTitle(first);
    }

    // 開いた直後に1回保存する(以前の形式の変換と、前回のMayaが残した本文のファイルの片付けを兼ねる)。
    sessionTimer_.start(kSessionSaveDelay);
    assist_->refreshCompletion();
    assist_->scheduleAnalysis();
    setProperty("openMilliseconds", openTimer.nsecsElapsed() / 1000000.0);
}

MainWindow::~MainWindow() {
    // 一覧を集めるスレッドを先に止めて合流する(この後、スレッドからこのウィンドウへ結果が送られないように)。
    fileLister_.reset();
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
        if (!restoring_) {
            onCurrentTabChanged();  // 復元の途中は、最後に1回だけ呼ぶ。
        }
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

    // ---- 左のドック: アウトライン(Explorerの下。表示の状態はpreferences.jsonに保存) ----
    outlineDock_ = new QDockWidget("OUTLINE", this);
    outlineDock_->setObjectName("outlineDock");
    outline_ = new OutlinePanel(outlineDock_);
    outline_->onActivated = [this](int line, int column) {
        if (CodeEditor* editor = currentEditor()) {
            moveCursorTo(editor, line, column);
        }
    };
    outlineDock_->setWidget(outline_);
    outlineDock_->setMinimumWidth(scaled(240));
    addDockWidget(Qt::LeftDockWidgetArea, outlineDock_);
    splitDockWidget(explorerDock_, outlineDock_, Qt::Vertical);
    outlineDock_->setVisible(preferences_.flag(kOutlineVisibleFlag, false));
    connect(outlineDock_, &QDockWidget::visibilityChanged, this, [this](bool visible) {
        if (visible) {
            refreshOutline();
        }
    });

    quickPick_ = new QuickPick(this);
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
            setLanguage(editor, index == 1 ? ScriptLanguage::Mel : ScriptLanguage::Python);
        }
    });
}

void MainWindow::setUpTimers() {
    outlineTimer_.setSingleShot(true);
    outlineTimer_.setInterval(400);
    connect(&outlineTimer_, &QTimer::timeout, this, [this] { refreshOutline(); });
    outlineSelectTimer_.setSingleShot(true);
    outlineSelectTimer_.setInterval(kOutlineSelectDelay);
    connect(&outlineSelectTimer_, &QTimer::timeout, this, [this] {
        CodeEditor* editor = currentEditor();
        if (!editor || !outlineDock_->isVisible()) {
            return;
        }
        // 同じ行の中の移動では選び直さない(アウトラインの木を毎回たどらない)。
        const int line = editor->textCursor().blockNumber();
        if (line != outlineLine_) {
            outlineLine_ = line;
            outline_->selectLine(line);
        }
    });
    // 入力中に全タブをJSONにしてディスクへ書かないよう、最後の変化から1.5秒経ってから1回だけ保存する
    // (markSessionDirtyのたびに数え直す)。常に動くタイマーは使わない。
    sessionTimer_.setSingleShot(true);
    connect(&sessionTimer_, &QTimer::timeout, this, [this] { saveSession(); });
    // カーソルの位置だけの変化は、30秒後にまとめて保存する(隠す・閉じるときはすぐ保存する)。
    cursorSessionTimer_.setSingleShot(true);
    connect(&cursorSessionTimer_, &QTimer::timeout, this, [this] { saveSession(); });
    // Mayaの終了時にも必ず保存する。
    connect(qApp, &QCoreApplication::aboutToQuit, this, [this] { saveSession(); });
}

// ===========================================================================
// タブ
// ===========================================================================

CodeEditor* MainWindow::currentEditor() const {
    return tabs_->currentEditor();
}

CodeEditor* MainWindow::newTab(ScriptLanguage language) {
    auto editor = new CodeEditor;
    editor->setProperty(kSessionIdProperty, newTabId());
    editor->setProperty(kSavedRevisionProperty, -1);
    applyPreferences(editor);
    tabs_->addTab(editor, "Untitled.py");  // addTabした時点で、タブ欄が所有者になる。
    setLanguage(editor, language);
    if (!restoring_) {
        // 復元の途中は選ばない(選ぶタブは復元の最後に決める)。
        tabs_->setCurrentWidget(editor);
        editor->setFocus();
        markSessionDirty();
    }

    assist_->attach(editor);  // Ctrl+Spaceとホバーの問い合わせ先。
    editor->onRunRequested = [this] { runCode(false); };
    editor->onDefinitionRequested = [this, editor](int end, bool peek) { goToDefinition(editor, end, peek); };
    // キー入力の処理の途中でタブ(=キーを受け取った部品自身)を削除しないよう、処理の後へ予約する。
    // 予約の持ち主をeditorにしておけば、先にeditorが破棄された場合は予約も取り消される。
    editor->onCloseRequested = [this, editor] {
        QTimer::singleShot(0, editor, [this, editor] { closeTab(tabs_->indexOf(editor)); });
    };

    // 復元の途中・本文の読み込み中(restoring_)の変化は、利用者の操作ではないので、タブごとの処理を呼ばない。
    connect(editor, &QPlainTextEdit::textChanged, this, [this, editor] {
        if (!restoring_) {
            onTextChanged(editor);
        }
    });
    // 見出しの未保存の印(●)は、未保存の状態が変わったときだけ付け直す(1文字ごとには付け直さない)。
    connect(editor->document(), &QTextDocument::modificationChanged, this, [this, editor] {
        if (!restoring_) {
            markSessionDirty();
            tabs_->updateTitle(editor);
        }
    });
    connect(editor->verticalScrollBar(), &QScrollBar::valueChanged, this, [this, editor] {
        if (editor == currentEditor()) {
            assist_->scheduleSpelling();  // スクロールで表示範囲が変わったので調べ直す。
        }
    });
    connect(editor, &QPlainTextEdit::cursorPositionChanged, this, [this, editor] {
        if (!restoring_) {
            onCursorMoved(editor);
        }
    });
    return editor;
}

void MainWindow::onTextChanged(CodeEditor* editor) {
    markSessionDirty();
    assist_->onTextChanged(editor);  // 補完・構文チェック・スペルチェックを予約し直す。
    if (editor == currentEditor()) {
        findBar_->scheduleRefresh();  // 本文が変わったので、検索の件数と強調を出し直す。
        outlineTimer_.start();
    }
}

void MainWindow::onCurrentTabChanged() {
    CodeEditor* editor = currentEditor();
    if (editor) {
        ensureLoaded(editor);  // 復元したまま読み込んでいないタブなら、ここで本文を文書へ入れる。
        languageSelector_->setCurrentIndex(editor->isMel() ? 1 : 0);
    }
    markSessionDirty();  // 選択中のタブも復元するので保存する。
    if (assist_) {
        assist_->onCurrentChanged();
    }
    findBar_->scheduleRefresh();  // 検索バーを開いていれば、新しいタブで件数と強調を出し直す。
    outlineLine_ = -1;
    outlineTimer_.start();
}

void MainWindow::onCursorMoved(CodeEditor* editor) {
    markCursorDirty();  // カーソルと選択の位置も復元するので、後でまとめて保存する。
    showCursorStatus(editor);
    if (editor == currentEditor() && outlineDock_->isVisible()) {
        outlineSelectTimer_.start();  // カーソルが止まってから、アウトラインの項目を選ぶ。
    }
}

void MainWindow::showCursorStatus(CodeEditor* editor) {
    if (!editor) {
        return;
    }
    const QTextCursor cursor = editor->textCursor();
    QString status = QString("Ln %1, Col %2").arg(cursor.blockNumber() + 1).arg(cursor.positionInBlock() + 1);
    if (cursor.hasSelection()) {
        status += QString(" (%1 selected)").arg(cursor.selectionEnd() - cursor.selectionStart());
    }
    status += "  |  UTF-8";
    // 同じ文字を出し直さない(別の知らせで上書きされていれば、出し直す)。
    if (statusBar()->currentMessage() != status) {
        showStatus(status);
    }
}

bool MainWindow::canDeferText(const QString& text) {
    // QTextDocumentは、\rと段落区切り(U+2029)・フレームの印(U+FDD0/U+FDD1)を行の区切りに変え、
    // 行区切り(U+2028)とノーブレークスペースは取り出すときに改行・空白に変える。そうした文字を含む本文は、
    // 文書へ入れて取り出すと元の文字列と変わるので、遅らせずに今までどおり復元時に文書へ入れる。
    for (const QChar c : text) {
        const ushort code = c.unicode();
        if (code == '\r' || code == 0 || code == 0x00a0 || code == 0x2028 || code == 0x2029 || code == 0xfdd0
            || code == 0xfdd1 || code == 0xfffc) {
            return false;
        }
    }
    return true;
}

void MainWindow::ensureLoaded(CodeEditor* editor) {
    const auto found = pendingTabs_.find(editor);
    if (found == pendingTabs_.end()) {
        return;
    }
    const PendingTab pending = found.value();
    pendingTabs_.erase(found);
    // 文書へ入れる間の変化(本文・未保存の状態・カーソル)は、利用者の操作ではないのでタブごとの処理を止める。
    const bool wasRestoring = restoring_;
    restoring_ = true;
    editor->setPlainText(pending.text);
    // 本文はtabs/<id>.txtと同じなので、本文が変わるまで本文のファイルを書き直さない。
    editor->setProperty(kSavedRevisionProperty, editor->document()->revision());
    if (!editor->filePath().isEmpty()) {
        // 行番号の横の変更の印は、元のファイルの内容と比べる。復元時に読んでいなければ、今読む。
        QString original = pending.original;
        bool readable = pending.originalReadable;
        if (!pending.originalRead) {
            QFile file(editor->filePath());
            readable = file.open(QIODevice::ReadOnly);
            original = readable ? QString::fromUtf8(file.readAll()) : QString();
        }
        if (readable) {
            editor->setSavedText(original);
        }
    }
    editor->document()->setModified(pending.modified);
    QTextCursor cursor = editor->textCursor();
    cursor.setPosition(pending.anchor);
    cursor.setPosition(pending.position, QTextCursor::KeepAnchor);
    editor->setTextCursor(cursor);
    editor->setProperty(kTextPendingProperty, false);
    restoring_ = wasRestoring;
    tabs_->updateTitle(editor);
}

void MainWindow::closeTab(int index) {
    CodeEditor* editor = tabs_->editorAt(index);
    if (!editor || !confirmClose(editor)) {
        return;
    }
    pendingTabs_.remove(editor);  // 読み込まずに閉じたタブの本文は、もう使わない。
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

void MainWindow::setLanguage(CodeEditor* editor, ScriptLanguage language) {
    editor->setLanguage(language);
    tabs_->updateTitle(editor);
    if (restoring_) {
        return;  // 復元の途中は、自動保存の印・言語の表示・構文チェックの予約を、最後にまとめて行う。
    }
    markSessionDirty();
    if (editor == currentEditor()) {
        languageSelector_->setCurrentIndex(editor->isMel() ? 1 : 0);
        assist_->scheduleAnalysis();
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
    CodeEditor* editor = newTab(languageForPath(path));
    editor->setPlainText(text);
    editor->setFilePath(absolute);
    editor->setSavedText(text);
    editor->document()->setModified(false);
    preferences_.addRecentFile(absolute);
    tabs_->updateTitle(editor);
    explorer_->addFolder(QFileInfo(absolute).absolutePath());
    updateExplorer();
    explorerDock_->show();
}

bool MainWindow::saveFile(CodeEditor* editor, bool saveAs) {
    ensureLoaded(editor);  // 読み込んでいないタブ(閉じるときの確認で保存を選んだ場合)は、先に本文を入れる。
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
    editor->setSavedText(text);
    editor->document()->setModified(false);
    preferences_.addRecentFile(QFileInfo(path).absoluteFilePath());
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

    // 保存されていたタブを作り直す。タブごとの処理(自動保存の印・構文チェックの予約など)は、
    // タブの数だけ繰り返さないよう止めておき、最後に選んだタブについて1回だけ行う。
    restoring_ = true;
    const int active = qBound(0, data.activeTab, int(data.tabs.size()) - 1);
    for (int index = 0; index < data.tabs.size(); ++index) {
        const TabState& tab = data.tabs[index];
        CodeEditor* editor = newTab(languageFromName(tab.language));
        editor->setFilePath(tab.path);
        editor->setProperty(kSessionIdProperty, tab.id);
        // 本文のファイルがあれば、今の本文と同じなので、本文が変わるまで書き直さない。
        // 古い形式(本文をtabs.jsonに含んでいた0.2.x)から読んだタブは、最初の保存で本文のファイルを作る。
        const bool hasTextFile = session_.hasTextFile(tab.id);
        // 選んでいないタブは本文を文字列のまま持ち、初めて選んだときに文書へ入れる(色分けを後回しにする)。
        // 本文のファイルが無いタブと、文書へ入れると文字が変わる本文のタブは、今までどおりすぐ入れる。
        if (index != active && hasTextFile && canDeferText(tab.text)) {
            PendingTab pending;
            pending.text = tab.text;
            // 保存していた位置が本文より後ろ(ファイルが短くなった等)でも、範囲内に収める。
            pending.anchor = qBound(0, tab.anchor, int(tab.text.size()));
            pending.position = qBound(0, tab.position, int(tab.text.size()));
            pending.modified = tab.modified;
            if (!tab.path.isEmpty() && !tab.modified) {
                // 未保存の印(元のファイルと違うか)を、読み込む前から正しく出すため、ここで元のファイルを読む。
                // 未保存の印が付いているタブは、比べなくても印が決まるので、読み込むときに読む。
                QFile original(tab.path);
                pending.originalRead = true;
                pending.originalReadable = original.open(QIODevice::ReadOnly);
                pending.original = pending.originalReadable ? QString::fromUtf8(original.readAll()) : QString();
                pending.modified = !pending.originalReadable || pending.original != tab.text;
            }
            // 空の文書の版を「保存済み」とする。読み込むまで本文は変わらないので、本文のファイルは書き直さない。
            editor->setProperty(kSavedRevisionProperty, editor->document()->revision());
            editor->document()->setModified(pending.modified);
            editor->setProperty(kTextPendingProperty, true);
            pendingTabs_.insert(editor, pending);
            tabs_->updateTitle(editor);
            continue;
        }
        editor->setPlainText(tab.text);
        editor->setProperty(kSavedRevisionProperty, hasTextFile ? editor->document()->revision() : -1);
        // 元のファイルが削除・外部で変更されていても、復元した本文は未保存として残す。
        bool differsFromFile = false;
        if (!tab.path.isEmpty()) {
            QFile original(tab.path);
            const bool readable = original.open(QIODevice::ReadOnly);
            const QString originalText = readable ? QString::fromUtf8(original.readAll()) : QString();
            differsFromFile = !readable || originalText != editor->toPlainText();
            if (readable) {
                editor->setSavedText(originalText);  // 行番号の横の変更の印は、ファイルの内容と比べる。
            }
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
    tabs_->setCurrentIndex(active);
    restoring_ = false;
    // 止めておいたタブごとの処理を、選んだタブについて1回だけ行う。
    onCurrentTabChanged();
    currentEditor()->setFocus();
    showCursorStatus(currentEditor());
}

bool MainWindow::saveSession() {
    if (!session_.canSave()) {
        return false;
    }
    if (!sessionDirty_ && !cursorDirty_) {
        return true;  // 前回の保存から何も変わっていない。
    }
    SessionData data;
    data.activeTab = tabs_->currentIndex();
    data.folders = explorer_->roots();
    data.explorerVisible = !explorerDock_->isHidden();
    QList<QPair<CodeEditor*, int>> written;  // 本文を書いたタブと、そのときの文書の版。
    for (CodeEditor* editor : tabs_->editors()) {
        TabState tab;
        tab.id = editor->property(kSessionIdProperty).toString();
        tab.path = editor->filePath();
        tab.language = languageName(editor->language());
        tab.modified = editor->document()->isModified();
        const auto pending = pendingTabs_.constFind(editor);
        if (pending != pendingTabs_.constEnd()) {
            // 読み込んでいないタブ: 本文はtabs/<id>.txtのまま(書き直さない)。位置は復元したときの値。
            tab.textLoaded = false;
            tab.position = pending->position;
            tab.anchor = pending->anchor;
            data.tabs.append(tab);
            continue;
        }
        // 本文が変わったタブだけ本文を渡す(全タブの本文を毎回複製・書き直ししない)。
        const int revision = editor->document()->revision();
        tab.textLoaded = editor->property(kSavedRevisionProperty).toInt() != revision;
        if (tab.textLoaded) {
            tab.text = editor->toPlainText();
            written.append({editor, revision});
        }
        const QTextCursor cursor = editor->textCursor();
        tab.position = cursor.position();
        tab.anchor = cursor.anchor();
        data.tabs.append(tab);
    }
    QString error;
    if (!session_.save(data, &error)) {
        // 書けない間は、次の自動保存までの間隔を1.5秒・3秒・6秒…と最大60秒まで延ばす。
        saveRetryDelay_ = saveRetryDelay_ == 0 ? kSessionSaveDelay : qMin(saveRetryDelay_ * 2, kMaximumSaveRetryDelay);
        cursorSessionTimer_.stop();
        sessionTimer_.start(saveRetryDelay_);
        showStatus("Tab recovery save failed: " + error);
        return false;
    }
    for (const auto& entry : written) {
        entry.first->setProperty(kSavedRevisionProperty, entry.second);
    }
    sessionDirty_ = false;
    cursorDirty_ = false;
    saveRetryDelay_ = 0;
    sessionTimer_.stop();
    cursorSessionTimer_.stop();
    // 計測用: 書き込みとフォルダーの一覧の回数(テストが動的プロパティで読む)。
    setProperty("sessionWrites", session_.jsonWrites());
    setProperty("sessionTextWrites", session_.textWrites());
    setProperty("sessionListings", session_.listings());
    return true;
}

void MainWindow::markSessionDirty() {
    sessionDirty_ = true;
    if (restoring_ || !session_.canSave()) {
        return;  // 復元の途中は、最後に保存を予約する。保存できない場合は予約しない。
    }
    if (saveRetryDelay_ > 0) {
        // 保存に失敗した後は、延ばした間隔の予約を縮めない。
        if (!sessionTimer_.isActive()) {
            sessionTimer_.start(saveRetryDelay_);
        }
        return;
    }
    sessionTimer_.start(kSessionSaveDelay);  // 最後の変化から数え直す。
}

void MainWindow::markCursorDirty() {
    cursorDirty_ = true;
    if (restoring_ || !session_.canSave()) {
        return;
    }
    // 本文の保存が予約済みなら、そのついでに保存される。数え直さないので、動かし続けても30秒ごとに1回で済む。
    if (!sessionTimer_.isActive() && !cursorSessionTimer_.isActive()) {
        cursorSessionTimer_.start(kCursorSaveDelay);
    }
}

void MainWindow::hideEvent(QHideEvent* event) {
    // ドックを閉じた・最小化したときも、待っている自動保存(カーソルの位置だけの変化を含む)を済ませる。
    if (sessionDirty_ || cursorDirty_) {
        saveSession();
    }
    QMainWindow::hideEvent(event);
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
    // 全体の実行でも、残っているU+2028(行区切り)を改行にする(Pythonでは構文エラーになるため)。
    QString source = normalizeSelectedText(editor->toPlainText());
    if (!all && editor->textCursor().hasSelection()) {
        source = normalizeSelectedText(editor->textCursor().selectedText());
    }
    QString result;
    if (editor->isMel()) {
        result = services_.runMel ? services_.runMel(source) : "MEL execution is unavailable";
    } else {
        result = services_.runPython ? services_.runPython(source, editor->filePath())
                                     : "Python execution is unavailable";
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

// ===========================================================================
// 移動(Goメニュー)・アウトライン・差分
// ===========================================================================

void MainWindow::moveCursorTo(CodeEditor* editor, int line, int column, bool focus) {
    const QTextBlock block = editor->document()->findBlockByNumber(qMax(0, line));
    if (!block.isValid()) {
        return;
    }
    QTextCursor cursor(block);
    cursor.setPosition(block.position() + qBound(0, column, block.length() - 1));
    editor->setTextCursor(cursor);
    editor->centerCursor();
    if (focus) {
        editor->setFocus(Qt::OtherFocusReason);
    }
}

void MainWindow::goToDefinition(CodeEditor* editor, int end, bool peek) {
    if (!editor || editor->isMel() || !services_.definition) {
        return;
    }
    if (end < 0) {
        showStatus("No name at the cursor", 3000);
        return;
    }
    const DefinitionLocation location = services_.definition(normalizeSelectedText(editor->toPlainText()), end);
    if (!location.found()) {
        showStatus("No definition found (names without Python source, such as maya.cmds, cannot be followed)", 4000);
        return;
    }
    if (peek) {
        QString text = editor->toPlainText();
        QString title = editor->displayName();
        if (!location.path.isEmpty()) {
            QString error;
            if (!readScriptFile(location.path, &text, &error)) {
                showStatus(error, 4000);
                return;
            }
            title = QFileInfo(location.path).fileName();
        }
        const QStringList lines = text.split('\n');
        const int first = qMax(0, location.line - 2);
        const QString html = HoverPopup::snippetHtml(QString("%1:%2").arg(title).arg(location.line + 1),
                                                     lines.mid(first, 16), first + 1, location.line + 1,
                                                     editor->font().family());
        editor->showPeek(html, end);
        return;
    }
    CodeEditor* target = editor;
    if (!location.path.isEmpty()) {
        const QString absolute = QFileInfo(location.path).absoluteFilePath();
        openFile(absolute);
        target = currentEditor();
        if (!target || QFileInfo(target->filePath()).absoluteFilePath() != absolute) {
            return;
        }
    }
    moveCursorTo(target, location.line, location.column);
}

void MainWindow::showSymbolPicker() {
    CodeEditor* editor = currentEditor();
    if (!editor) {
        return;
    }
    const QList<OutlineEntry> entries = editor->outline();
    QList<QuickPickItem> items;
    for (const OutlineEntry& entry : entries) {
        QString container;
        for (int parent = entry.parent; parent >= 0; parent = entries[parent].parent) {
            container = container.isEmpty() ? entries[parent].name : entries[parent].name + "." + container;
        }
        items.append({entry.name, container.isEmpty() ? entry.kind : container, entry.kind,
                      QVariant::fromValue(QPoint(entry.column, entry.line))});
    }
    if (items.isEmpty()) {
        showStatus("No symbols in this tab", 3000);
        return;
    }
    // 一覧で選んでいる間は、その行を下見として表示する。Escで元の位置に戻す。
    const QTextCursor original = editor->textCursor();
    const int originalScroll = editor->verticalScrollBar()->value();
    QPointer<CodeEditor> guard(editor);
    pickingFiles_ = false;  // ファイルの一覧が後から届いても、この小窓へは出さない。
    quickPick_->onPreview = [this, guard](const QVariant& data) {
        if (guard) {
            const QPoint point = data.toPoint();
            moveCursorTo(guard, point.y(), point.x(), false);
        }
    };
    quickPick_->onAccepted = [this, guard](const QVariant& data) {
        if (guard) {
            const QPoint point = data.toPoint();
            moveCursorTo(guard, point.y(), point.x());
        }
    };
    quickPick_->onCanceled = [guard, original, originalScroll] {
        if (guard) {
            guard->setTextCursor(original);
            guard->verticalScrollBar()->setValue(originalScroll);
            guard->setFocus(Qt::OtherFocusReason);
        }
    };
    quickPick_->open("Go to symbol in this tab", items,
                     enclosingOutlineEntry(entries, editor->textCursor().blockNumber()));
}

void MainWindow::showFilePicker() {
    const QStringList recentFiles = preferences_.recentFiles();
    const QStringList roots = explorer_->roots();
    if (recentFiles.isEmpty() && roots.isEmpty()) {
        showStatus("No files: open a folder in the Explorer or open a file first", 4000);
        return;
    }
    // 最近開いたファイルとフォルダーが前回と同じなら、前回集めた一覧を使う。
    const QStringList key = fileListKey();
    const bool known = key == fileListKey_ && fileListAge_.isValid();
    const bool fresh = known && fileListAge_.elapsed() <= kFileListLifetime;
    if (fresh && fileList_.isEmpty()) {
        showStatus("No files: open a folder in the Explorer or open a file first", 4000);
        return;
    }
    if (!fresh) {
        requestFileList(key, recentFiles, roots);  // 古い・無い一覧は、別スレッドで集め直す。
    }
    pickingFiles_ = true;
    quickPick_->onPreview = nullptr;
    quickPick_->onAccepted = [this](const QVariant& data) {
        openFile(data.toString());
        if (CodeEditor* editor = currentEditor()) {
            editor->setFocus(Qt::OtherFocusReason);
        }
    };
    quickPick_->onCanceled = [this] {
        if (CodeEditor* editor = currentEditor()) {
            editor->setFocus(Qt::OtherFocusReason);
        }
    };
    // 覚えている一覧があれば(古くても)すぐ出す。集め終えたら、applyFileListが新しい一覧に差し替える。
    const bool cached = known && !fileList_.isEmpty();
    quickPick_->open("Search files by name (recently opened and Explorer folders)",
                     cached ? fileList_ : QList<QuickPickItem>());
    if (!cached) {
        quickPick_->setLoadingText("Loading files…");
    }
}

QStringList MainWindow::fileListKey() const {
    return preferences_.recentFiles() + QStringList{QString()} + explorer_->roots();
}

void MainWindow::requestFileList(const QStringList& key, const QStringList& recentFiles, const QStringList& roots) {
    if (key == fileListRequestedKey_) {
        return;  // 同じ内容をもう集めている。
    }
    // 一覧を集めるスレッドは、初めて使うときに作る(Ctrl+Pを使わなければスレッドを作らない)。
    if (!fileLister_) {
        fileLister_ = std::make_unique<FileLister>(
            [this](const QStringList& listedKey, const QList<QuickPickItem>& items, qint64 milliseconds) {
                // 別スレッドから呼ばれる。画面の部品には触れず、画面のスレッドへ送る。送り先(this)が
                // 先に破棄されたら、未実行の処理は捨てられる(デストラクターはスレッドを先に止めて合流する)。
                QMetaObject::invokeMethod(
                    this, [this, listedKey, items, milliseconds] { applyFileList(listedKey, items, milliseconds); },
                    Qt::QueuedConnection);
            });
    }
    fileListRequestedKey_ = key;
    fileLister_->request(key, recentFiles, roots);
}

void MainWindow::applyFileList(const QStringList& key, const QList<QuickPickItem>& items, qint64 milliseconds) {
    if (key == fileListRequestedKey_) {
        fileListRequestedKey_.clear();
    }
    fileList_ = items;
    fileListKey_ = key;
    fileListAge_.start();
    // 計測用: 集めるのにかかった時間と件数(テストが動的プロパティで読む)。
    setProperty("fileListMilliseconds", milliseconds);
    setProperty("fileListCount", items.size());
    if (!pickingFiles_ || !quickPick_->isOpen()) {
        return;  // ファイル名で開くの小窓は、もう閉じている(次に開いたときに使う)。
    }
    const QStringList current = fileListKey();
    if (key != current) {
        // 集めている間に、フォルダーか最近開いたファイルが変わった。今の内容で集め直す。
        requestFileList(current, preferences_.recentFiles(), explorer_->roots());
        return;
    }
    if (items.isEmpty()) {
        quickPick_->cancel();
        showStatus("No files: open a folder in the Explorer or open a file first", 4000);
        return;
    }
    quickPick_->setItems(items);
}

void MainWindow::compareWithSaved() {
    CodeEditor* editor = currentEditor();
    if (!editor) {
        return;
    }
    if (!editor->hasSavedText()) {
        showStatus("This tab has no saved file to compare with (save it first)", 4000);
        return;
    }
    DiffDialog dialog(this, editor->displayName(), editor->savedText(), editor->toPlainText());
    if (dialog.exec() == 2) {
        // 保存した内容へ戻す(1回のUndoで取り消せる)。
        QTextCursor cursor = editor->textCursor();
        cursor.beginEditBlock();
        cursor.select(QTextCursor::Document);
        cursor.insertText(editor->savedText());
        cursor.endEditBlock();
    }
}

void MainWindow::refreshOutline() {
    if (!outlineDock_ || !outlineDock_->isVisible()) {
        return;
    }
    CodeEditor* editor = currentEditor();
    outline_->setOutline(editor ? editor->outline() : QList<OutlineEntry>());
    if (editor) {
        outlineLine_ = editor->textCursor().blockNumber();
        outline_->selectLine(outlineLine_);
    }
}

void MainWindow::rebuildRecentMenu() {
    recentMenu_->clear();
    const QStringList recent = preferences_.recentFiles();
    for (const QString& path : recent) {
        QAction* action = recentMenu_->addAction(QFileInfo(path).fileName() + "    " + QFileInfo(path).absolutePath());
        action->setEnabled(QFileInfo(path).isFile());
        connect(action, &QAction::triggered, this, [this, path] { openFile(path); });
    }
    if (recent.isEmpty()) {
        recentMenu_->addAction("(no recent files)")->setEnabled(false);
        return;
    }
    recentMenu_->addSeparator();
    recentMenu_->addAction("Clear recently opened", this, [this] { preferences_.clearRecentFiles(); });
}

void MainWindow::refreshOutputNow() {
    output_->refreshNow();
}

void MainWindow::scheduleOutput() {
    output_->scheduleFlush();
}

// ===========================================================================
// 設定
// ===========================================================================

void MainWindow::applyPreferences(CodeEditor* editor) {
    editor->setAutoClosing(preferences_.option(option::kAutoClosing));
    editor->setStickyScroll(preferences_.option(option::kStickyScroll));
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
        assist_->scheduleAnalysis();
    } else if (key == option::kOutputLineNumbers) {
        output_->view()->setLineNumbersVisible(enabled);
    } else if (key == option::kOutputWrap) {
        output_->setWrap(enabled);
    } else if (key == option::kExactOutput && services_.setExactOutput) {
        services_.setExactOutput(enabled);
    } else if (key == option::kSpellCheck) {
        assist_->scheduleSpelling();
    }
}

}  // namespace hedit
