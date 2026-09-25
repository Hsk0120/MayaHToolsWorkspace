#include "editor.h"
#include <QApplication>
#include <QCloseEvent>
#include <QCompleter>
#include <QFileDialog>
#include <QFile>
#include <QFileInfo>
#include <QStandardItemModel>
#include <QFontDatabase>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QLabel>
#include <QInputDialog>
#include <QMenuBar>
#include <QMessageBox>
#include <QPainter>
#include <QPlainTextEdit>
#include <QProcess>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSaveFile>
#include <QScrollBar>
#include <QSplitter>
#include <QStatusBar>
#include <QStringListModel>
#include <QSyntaxHighlighter>
#include <QTabWidget>
#include <QTextBlock>
#include <QTimer>
#include <QToolBar>
#include <QAbstractItemView>

namespace heditor {
class Highlight : public QSyntaxHighlighter {
public:
    explicit Highlight(QTextDocument* doc) : QSyntaxHighlighter(doc) {}
    void highlightBlock(const QString& text) override {
        const QList<QPair<QString, QColor>> rules = {
            {"\\b[0-9]+(?:\\.[0-9]+)?\\b", QColor("#b5cea8")},
            {"\\b[A-Za-z_][A-Za-z_0-9]*(?=\\s*\\()", QColor("#dcdcaa")},
            {"\\b(?:def|class|import|from|as|return|if|else|elif|for|while|in|try|except|finally|with|yield|raise|pass|and|or|not|lambda|async|await)\\b", QColor("#c586c0")},
            {"\\b(?:True|False|None|self)\\b", QColor("#569cd6")},
            {"(?:\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*')", QColor("#ce9178")}
        };
        for (const auto& rule : rules) {
            auto matches = QRegularExpression(rule.first).globalMatch(text);
            while (matches.hasNext()) {
                auto m = matches.next(); setFormat(m.capturedStart(), m.capturedLength(), rule.second);
            }
        }
        // コメント記号は引用符の外だけを扱う。
        QChar quote; bool escape = false;
        for (int i = 0; i < text.size(); ++i) {
            QChar c = text[i];
            if (escape) { escape = false; continue; }
            if (c == '\\') { escape = true; continue; }
            if (!quote.isNull()) { if (c == quote) quote = QChar(); }
            else if (c == '\'' || c == '"') quote = c;
            else if (c == '#') { setFormat(i, text.size()-i, QColor("#6a9955")); break; }
        }
    }
};

class Code : public QPlainTextEdit {
public:
    QCompleter* completer;
    std::function<void()> request;
    explicit Code(QWidget* parent = nullptr) : QPlainTextEdit(parent) {
        setObjectName("codeEditor");
        setFont(QFont("Consolas", 11)); setLineWrapMode(NoWrap);
        setTabStopDistance(fontMetrics().horizontalAdvance(' ') * 4);
        setViewportMargins(54, 0, 0, 0);
        new Highlight(document());
        completer = new QCompleter(this);
        completer->setModel(new QStandardItemModel(completer));
        completer->setWidget(this); completer->setCaseSensitivity(Qt::CaseSensitive);
        completer->setCompletionMode(QCompleter::PopupCompletion);
        completer->popup()->setFont(QFont("Consolas", 11));
        completer->popup()->setStyleSheet("QAbstractItemView{background:#252526;color:#d4d4d4;border:1px solid #454545;selection-background-color:#094771;selection-color:#ffffff;padding:3px;}");
        connect(completer, QOverload<const QString&>::of(&QCompleter::activated), this, [this](const QString& value) {
            auto cursor = textCursor();
            cursor.movePosition(QTextCursor::Left, QTextCursor::KeepAnchor, prefix().size());
            cursor.insertText(value); setTextCursor(cursor);
        });
        connect(this, &QPlainTextEdit::updateRequest, this, [this] { update(); });
        connect(this, &QPlainTextEdit::cursorPositionChanged, this, [this] {
            QTextEdit::ExtraSelection line;
            line.format.setBackground(QColor("#282828"));
            line.format.setProperty(QTextFormat::FullWidthSelection, true);
            line.cursor = textCursor(); line.cursor.clearSelection(); setExtraSelections({line});
        });
    }
    QString prefix() const {
        auto cursor = textCursor(); cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
        return QRegularExpression("[A-Za-z_0-9]*$").match(cursor.selectedText()).captured();
    }
    void paintEvent(QPaintEvent* event) override { QPlainTextEdit::paintEvent(event); }
    bool event(QEvent* event) override {
        if (event->type() == QEvent::Paint) {
            QPainter painter(this); painter.fillRect(0, 0, 52, height(), QColor("#1e1e1e"));
            painter.setPen(QColor("#858585")); painter.setFont(font());
            auto block = firstVisibleBlock();
            while (block.isValid()) {
                auto rect = blockBoundingGeometry(block).translated(contentOffset());
                if (rect.top() > height()) break;
                painter.drawText(QRectF(0, rect.top(), 43, fontMetrics().height()), Qt::AlignRight, QString::number(block.blockNumber()+1));
                block = block.next();
            }
        }
        return QPlainTextEdit::event(event);
    }
    void keyPressEvent(QKeyEvent* event) override {
        if (completer->popup()->isVisible()) {
            switch (event->key()) {
            case Qt::Key_Enter: case Qt::Key_Return: case Qt::Key_Escape: case Qt::Key_Tab:
                event->ignore(); return;
            }
        }
        if (event->key() == Qt::Key_Space && event->modifiers() == Qt::ControlModifier) {
            if (request) request(); return;
        }
        if (event->key() == Qt::Key_Tab && event->modifiers() == Qt::NoModifier) { insertPlainText("    "); return; }
        if (event->key() == Qt::Key_Return && event->modifiers() == Qt::NoModifier) {
            auto cursor = textCursor(); cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
            QString before = cursor.selectedText();
            QString indent = QRegularExpression("^ *").match(before).captured();
            if (before.trimmed().endsWith(':')) indent += "    ";
            insertPlainText("\n" + indent); return;
        }
        QPlainTextEdit::keyPressEvent(event);
    }
};

class Window : public QMainWindow {
    QTabWidget* tabs;
    QPlainTextEdit* output;
    QLabel* completionStatus;
    QProcess worker;
    QTimer debounce;
    QTimer deadline;
    QByteArray buffer;
    qint64 generation = 0;
    bool ready = false;
    bool busy = false;
    bool pending = false;
    Execute execute;
    Configuration configuration;
    OutputReader outputReader;
    QTimer outputTimer;
    QJsonObject config;
public:
    Window(QWidget* parent, Execute run, Configuration snapshot, OutputReader reader) : QMainWindow(parent), execute(run), configuration(snapshot), outputReader(reader) {
        setObjectName("HEditor"); setWindowTitle("HEditor — Python / Maya"); resize(1050, 740);
        setFont(QFont("Segoe UI", 10));
        setWindowFlags(Qt::Window);
        setStyleSheet(
            "QMainWindow,QWidget{background:#1e1e1e;color:#d4d4d4;font-family:'Segoe UI';font-size:13px;}"
            "QPlainTextEdit{font-family:'Consolas';font-size:14px;border:0;selection-background-color:#264f78;}"
            "QMenuBar,QMenu,QToolBar{background:#323233;} QMenu::item:selected{background:#094771;}"
            "QTabWidget::pane{border:0;} QTabBar::tab{background:#2d2d2d;padding:9px 20px;}"
            "QTabBar::tab:selected{background:#1e1e1e;border-top:2px solid #007acc;}"
            "QStatusBar{background:#007acc;color:white;} QSplitter::handle{background:#333333;}"
            "QAbstractItemView{background:#252526;color:#d4d4d4;selection-background-color:#094771;}"
            "QToolButton{padding:7px;} QToolButton:hover{background:#454545;}"
        );
        auto split = new QSplitter(Qt::Vertical, this);
        tabs = new QTabWidget; tabs->setTabsClosable(true); tabs->setMovable(true);
        output = new QPlainTextEdit; output->setObjectName("output"); output->setReadOnly(true);
        output->setFont(QFont("Consolas", 10)); output->setMaximumBlockCount(5000);
        connect(&outputTimer, &QTimer::timeout, this, [this] { flushOutput(); });
        if (outputReader) outputTimer.start(25);
        output->setPlaceholderText("OUTPUT — Ctrl+Enter: selection / current script    F5: current script");
        completionStatus = new QLabel("Completion: starting");
        completionStatus->setObjectName("completionStatus");
        statusBar()->addPermanentWidget(completionStatus);
        split->addWidget(tabs); split->addWidget(output); split->setSizes({550, 160}); setCentralWidget(split);
        auto file = menuBar()->addMenu("File");
        auto add = file->addAction("New Python tab", this, [this] { newTab(); }); add->setShortcut(QKeySequence::New);
        file->addAction("Open…", this, [this] {
            auto path = QFileDialog::getOpenFileName(this, "Open Python", {}, "Python (*.py);;All files (*)");
            if (path.isEmpty()) return;
            QFile f(path); if (!f.open(QIODevice::ReadOnly)) { QMessageBox::warning(this, "Open", f.errorString()); return; }
            QByteArray bytes = f.readAll();
            if (bytes.startsWith("\xef\xbb\xbf")) bytes.remove(0, 3);
            QString text = QString::fromUtf8(bytes);
            if (text.toUtf8() != bytes) { QMessageBox::warning(this, "Open", "This version supports UTF-8 files only."); return; }
            auto code = newTab(); code->setPlainText(text); code->setProperty("path", path);
            code->document()->setModified(false); updateTitle(code);
        }, QKeySequence::Open);
        file->addAction("Save", this, [this] { save(current()); }, QKeySequence::Save);
        auto edit = menuBar()->addMenu("Edit");
        edit->addAction("Find…", this, [this] {
            bool ok = false;
            auto term = QInputDialog::getText(this, "Find", "Text", QLineEdit::Normal, {}, &ok);
            if (!ok || term.isEmpty()) return;
            if (!current()->find(term)) { current()->moveCursor(QTextCursor::Start); current()->find(term); }
        }, QKeySequence::Find);
        auto toolbar = addToolBar("Run"); toolbar->setMovable(false);
        auto action = toolbar->addAction("▶ Run selection / script", this, [this] { runCode(false); });
        action->setShortcut(QKeySequence("Ctrl+Return"));
        auto all = toolbar->addAction("Run all", this, [this] { runCode(true); }); all->setShortcut(QKeySequence("F5"));
        toolbar->addAction("Refresh completion", this, [this] { startWorker(); });
        toolbar->addAction("Clear output", output, &QPlainTextEdit::clear);
        connect(tabs, &QTabWidget::tabCloseRequested, this, [this](int index) {
            auto code = static_cast<Code*>(tabs->widget(index));
            if (!mayClose(code)) return;
            tabs->removeTab(index); delete code; if (!tabs->count()) newTab();
        });
        connect(tabs, &QTabWidget::currentChanged, this, [this] { ++generation; });
        debounce.setSingleShot(true); debounce.setInterval(100);
        connect(&debounce, &QTimer::timeout, this, [this] { request(false); });
        deadline.setSingleShot(true); deadline.setInterval(10000);
        connect(&deadline, &QTimer::timeout, this, [this] {
            worker.kill(); ready = false; completionStatus->setText("Completion timed out — Refresh completion");
        });
        connect(&worker, &QProcess::started, this, [this] { send(config); deadline.start(); });
        connect(&worker, &QProcess::readyReadStandardOutput, this, [this] { receive(); });
        connect(&worker, &QProcess::readyReadStandardError, this, [this] { output->appendPlainText(QString::fromUtf8(worker.readAllStandardError())); });
        connect(&worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) { ready = false; deadline.stop(); completionStatus->setText("Completion: " + worker.errorString()); });
        connect(&worker, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this, [this](int, QProcess::ExitStatus) { ready = false; deadline.stop(); });
        newTab()->setPlainText("import maya.cmds as cmds\n\n# Ctrl+Space: completion    Ctrl+Enter: run\nprint(cmds.ls(selection=True))\n");
        current()->document()->setModified(false); updateTitle(current());
        startWorker();
    }
    ~Window() override { worker.kill(); worker.waitForFinished(1000); }
    Code* current() const { return static_cast<Code*>(tabs->currentWidget()); }
    Code* newTab() {
        auto code = new Code;
        tabs->addTab(code, "Untitled.py"); tabs->setCurrentWidget(code);
        code->request = [this] { request(); };
        connect(code, &QPlainTextEdit::textChanged, this, [this, code] {
            ++generation; code->completer->popup()->hide(); debounce.start(); updateTitle(code);
        });
        connect(code, &QPlainTextEdit::cursorPositionChanged, this, [this, code] {
            ++generation; code->completer->popup()->hide();
            statusBar()->showMessage(QString("Ln %1, Col %2  |  Python  |  UTF-8").arg(code->textCursor().blockNumber()+1).arg(code->textCursor().positionInBlock()+1));
        });
        return code;
    }
    void updateTitle(Code* code) {
        QString path = code->property("path").toString();
        QString title = path.isEmpty() ? "Untitled.py" : QFileInfo(path).fileName();
        tabs->setTabText(tabs->indexOf(code), title + (code->document()->isModified() ? " ●" : ""));
    }
    bool save(Code* code) {
        auto path = code->property("path").toString();
        if (path.isEmpty()) path = QFileDialog::getSaveFileName(this, "Save Python", {}, "Python (*.py)");
        if (path.isEmpty()) return false;
        QSaveFile file(path); QByteArray bytes = code->toPlainText().toUtf8();
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
            QMessageBox::warning(this, "Save", file.errorString()); return false;
        }
        code->setProperty("path", path); code->document()->setModified(false); updateTitle(code); return true;
    }
    bool mayClose(Code* code) {
        if (!code->document()->isModified()) return true;
        auto choice = QMessageBox::question(this, "Unsaved script", "Save changes before closing?", QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel);
        return choice == QMessageBox::Discard || (choice == QMessageBox::Save && save(code));
    }
    void closeEvent(QCloseEvent* event) override {
        for (int i=0; i<tabs->count(); ++i) if (!mayClose(static_cast<Code*>(tabs->widget(i)))) { event->ignore(); return; }
        event->accept(); // Mayaセッション内ではウィンドウ/タブを保持する。
    }
    void flushOutput() {
        if (!outputReader) return;
        QString text = outputReader();
        if (text.isEmpty()) return;
        auto cursor = output->textCursor(); cursor.movePosition(QTextCursor::End);
        cursor.insertText(text); output->setTextCursor(cursor); output->ensureCursorVisible();
    }
    void runCode(bool all) {
        QString source = current()->toPlainText();
        if (!all && current()->textCursor().hasSelection()) source = current()->textCursor().selectedText().replace(QChar(0x2029), '\n');
        QString result = execute(source);
        if (!result.isEmpty()) output->appendPlainText(result);
        flushOutput();
    }
    void startWorker() {
        ++generation; ready = false; busy = false; pending = false; deadline.stop(); worker.kill(); worker.waitForFinished(1000); buffer.clear();
        config = QJsonDocument::fromJson(configuration()).object();
        auto env = QProcessEnvironment::systemEnvironment();
        env.insert("PYTHONIOENCODING", "utf-8"); env.insert("MAYA_SKIP_USERSETUP_PY", "1");
        worker.setProcessEnvironment(env);
        worker.start(config["python"].toString(), {"-S", "-u", config["worker"].toString()});
        completionStatus->setText("Completion: starting…");
    }
    void send(const QJsonObject& object) { worker.write(QJsonDocument(object).toJson(QJsonDocument::Compact) + '\n'); }
    void request(bool force = true) {
        if (!ready || !current()->hasFocus()) return;
        if (!force && current()->prefix().isEmpty() && !current()->toPlainText().left(current()->textCursor().position()).endsWith('.')) return;
        if (busy) { pending = true; return; }
        busy = true;
        auto cursor = current()->textCursor(); cursor.setPosition(0, QTextCursor::KeepAnchor);
        send({{"id", double(++generation)}, {"source", cursor.selectedText().replace(QChar(0x2029), '\n')}});
        if (!deadline.isActive()) deadline.start();
    }
    void receive() {
        buffer += worker.readAllStandardOutput();
        int newline;
        while ((newline = buffer.indexOf('\n')) >= 0) {
            auto response = QJsonDocument::fromJson(buffer.left(newline)).object(); buffer.remove(0, newline+1);
            if (response.isEmpty()) continue;
            if (response["ready"].toBool()) { ready = true; deadline.stop(); completionStatus->setText("Completion: ready"); debounce.start(); continue; }
            busy = false;
            deadline.stop();
            if (pending) { pending = false; request(); continue; }
            if (qint64(response["id"].toDouble()) != generation) continue;
            if (response.contains("error")) { statusBar()->showMessage(response["error"].toString()); continue; }
            if (response["items"].toArray().isEmpty() || !current()->hasFocus()) continue;
            auto completer = current()->completer;
            auto model = static_cast<QStandardItemModel*>(completer->model());
            model->clear();
            for (const auto& value : response["items"].toArray()) {
                auto item = new QStandardItem(value.toObject()["name"].toString());
                item->setToolTip(value.toObject()["detail"].toString()); model->appendRow(item);
            }
            completer->setCompletionPrefix(current()->prefix());
            completer->popup()->setCurrentIndex(completer->completionModel()->index(0, 0));
            auto rect = current()->cursorRect(); rect.setWidth(380); completer->complete(rect);
        }
    }
};

QMainWindow* createEditor(QWidget* parent, Execute execute, Configuration configuration, OutputReader outputReader) {
    return new Window(parent, execute, configuration, outputReader);
}
}
