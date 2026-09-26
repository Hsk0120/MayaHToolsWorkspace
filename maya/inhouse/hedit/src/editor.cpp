/** @file editor.cpp
 * @brief Mayaに依存しないQt編集画面の実装。
 * @details Qtのparentが子オブジェクトを所有する。newしたUI部品は親の破棄時に解放される。
 * connectのラムダで[this]は現在のWindowを捕捉する。接続のcontextに所有者を指定し、
 * 破棄後にコールバックが動かないようにする。deleteLaterはイベント処理後に破棄する予約。
 * Maya呼出はeditor.hのstd::functionを経由し、同じ画面をMayaなしでもテストできる。
 */
#include "editor.h"
#include "explorer.h"
#include "spelling.h"
#include <QElapsedTimer>
#include <QDockWidget>
#include <QComboBox>
#include <QWheelEvent>
#include <QApplication>
#include <QCloseEvent>
#include <QClipboard>
#include <QLineEdit>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QPushButton>
#include <QTabBar>
#include <QShortcut>
#include <QCompleter>
#include <QFileDialog>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QLockFile>
#include <QSettings>
#include <QTextOption>
#include <QListWidget>
#include <QCheckBox>
#include <memory>
#include <QStandardItemModel>
#include <QFontDatabase>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QLabel>
#include <QInputDialog>
#include <QIntValidator>
#include <QMenuBar>
#include <QMessageBox>
#include <QPainter>
#include <QPlainTextEdit>
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
#include <QStyle>
#include <QAbstractItemView>

namespace hedit {
/** @brief マウスホイールと矢印ボタンで多数のタブを移動する。 */
class ScrollTabs : public QTabBar {
public:
    /**
     * @brief スクロールボタン付きのタブバーを作る。
     * @param parent タブバーを所有する親。
     */
    explicit ScrollTabs(QWidget* parent=nullptr) : QTabBar(parent) { setUsesScrollButtons(true); setExpanding(false); setElideMode(Qt::ElideNone); }
    /** @brief ホイール1段で隣のタブを選択し、そのタブを表示範囲へ入れる。 */
    void wheelEvent(QWheelEvent* event) override {
        int delta=event->angleDelta().y(); if (!delta) delta=event->angleDelta().x();
        if (delta && count()) setCurrentIndex(qBound(0,currentIndex()+(delta<0?1:-1),count()-1));
        event->accept();
    }
};
/** @brief スクロール対応のタブバーを組み込む。 */
class EditorTabs : public QTabWidget {
public:
    /**
     * @brief スクロール対応のタブバーをタブウィジェットに設定する。
     * @param parent タブ全体を所有する親。
     */
    explicit EditorTabs(QWidget* parent=nullptr) : QTabWidget(parent) { setTabBar(new ScrollTabs(this)); }
};

/** @brief Python/MEL本文の簡易構文強調。構文解析器ではなく表示専用。 */
class Highlight : public QSyntaxHighlighter {
public:
    /**
     * @brief 文書に構文強調を取り付ける。Qtが文書とともに破棄する。
     * @param doc 表示色を付ける文書。
     */
    explicit Highlight(QTextDocument* doc) : QSyntaxHighlighter(doc) {}
    /**
     * @brief 1行を簡易ルールで色分けする。ソースの実行やimportは行わない。
     * @param text Qtから渡される行の文字列。
     */
    void highlightBlock(const QString& text) override {
        const bool mel=document()->property("language").toString()=="mel";
        const QList<QPair<QString, QColor>> rules = {
            {"\\b[A-Za-z_][A-Za-z_0-9]*\\b", QColor("#9cdcfe")},
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
        auto classes=QRegularExpression("\\bclass\\s+([A-Za-z_][A-Za-z_0-9]*)").globalMatch(text);
        while (classes.hasNext()) { auto m=classes.next(); setFormat(m.capturedStart(1),m.capturedLength(1),QColor("#4ec9b0")); }
        auto strings=QRegularExpression("(?:\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*')").globalMatch(text);
        while (strings.hasNext()) { auto m=strings.next(); setFormat(m.capturedStart(),m.capturedLength(),QColor("#ce9178")); }
        // コメント記号は引用符の外だけを扱う。
        QChar quote; bool escape = false;
        for (int i = 0; i < text.size(); ++i) {
            QChar c = text[i];
            if (escape) { escape = false; continue; }
            if (c == '\\') { escape = true; continue; }
            if (!quote.isNull()) { if (c == quote) quote = QChar(); }
            else if (c == '\'' || c == '"') quote = c;
            else if ((!mel && c == '#') || (mel && c=='/' && i+1<text.size() && text[i+1]=='/')) { setFormat(i, text.size()-i, QColor("#6a9955")); break; }
        }
    }
};

/** @brief コードと出力に共通の行番号欄。番号は文書データに含めない。 */
class NumberedText : public QPlainTextEdit {
    int gutterWidth=54;
    bool showNumbers=true;
    /**
     * @brief 桁数とフォントから行番号欄の幅を再計算する。
     */
    void updateGutter() {
        int digits=QString::number(qMax(1,blockCount())).size();
        gutterWidth=showNumbers ? qMax(44,fontMetrics().horizontalAdvance('9')*digits+20) : 0;
        setViewportMargins(gutterWidth,0,0,0);
        setTabStopDistance(fontMetrics().horizontalAdvance(' ')*4);
        update();
    }
public:
    /** @brief 行番号と余白の表示を切り替える。本文や行移動には影響しない。
     * @param visible trueで行番号を表示する。
     */
    void setLineNumbersVisible(bool visible) { showNumbers=visible; updateGutter(); }
    /**
     * @brief 行数・フォント・スクロールの変更を行番号欄に反映する。
     * @param parent 所有者。省略時は後でレイアウトへ追加する。
     */
    explicit NumberedText(QWidget* parent=nullptr) : QPlainTextEdit(parent) {
        connect(this,&QPlainTextEdit::blockCountChanged,this,[this]{ updateGutter(); });
        connect(this,&QPlainTextEdit::updateRequest,this,[this]{ update(); });
        updateGutter();
    }
    /**
     * @brief Qtイベントを受け取り、対象外のイベントは基底クラスへ渡す。
     * @param event Qt所有のイベント。ここでは削除しない。
     * @return このウィジェットでイベントを処理した場合true。
     */
    bool event(QEvent* event) override {
        if (event->type()==QEvent::FontChange) { bool result=QPlainTextEdit::event(event); updateGutter(); return result; }
        if (event->type()==QEvent::Paint && showNumbers) {
            QPainter painter(this); painter.fillRect(0,0,gutterWidth,height(),QColor("#1e1e1e"));
            painter.setPen(QColor("#858585")); painter.setFont(font());
            auto block=firstVisibleBlock();
            while (block.isValid()) {
                auto rect=blockBoundingGeometry(block).translated(contentOffset());
                if (rect.top()>height()) break;
                if (block.isVisible()) painter.drawText(QRectF(0,rect.top(),gutterWidth-10,fontMetrics().height()),Qt::AlignRight,QString::number(block.blockNumber()+1));
                block=block.next();
            }
        }
        return QPlainTextEdit::event(event);
    }
};

/** @brief 選択・コピーができる読み取り専用の出力欄。 */
class Output : public NumberedText {
public:
    /**
     * @brief マウスとキーボードで選択可能な読み取り専用ログを作る。
     */
    Output() {
        setLineNumbersVisible(false);
        setLineWrapMode(NoWrap);
        setReadOnly(true);
        setTextInteractionFlags(Qt::TextSelectableByMouse | Qt::TextSelectableByKeyboard);
        setFocusPolicy(Qt::StrongFocus);
    }
    /**
     * @brief Qtイベントを受け取り、対象外のイベントは基底クラスへ渡す。
     * @param event Qt所有のイベント。ここでは削除しない。
     * @return このウィジェットでイベントを処理した場合true。
     */
    bool event(QEvent* event) override {
        if (event->type()==QEvent::ShortcutOverride) {
            auto key=static_cast<QKeyEvent*>(event);
            if (key->matches(QKeySequence::Copy) || key->matches(QKeySequence::SelectAll)) { event->accept(); return true; }
        }
        return NumberedText::event(event);
    }
    /**
     * @brief エディタ専用キーを処理し、残りはQt標準の入力処理へ渡す。
     * @param event キーと修飾キーの情報。Qtが所有する。
     */
    void keyPressEvent(QKeyEvent* event) override {
        if (event->matches(QKeySequence::Copy)) { copy(); event->accept(); return; }
        if (event->matches(QKeySequence::SelectAll)) { selectAll(); event->accept(); return; }
        QPlainTextEdit::keyPressEvent(event);
    }
};

/** @brief 1つのタブの本文・編集ショートカット・補完表示を担当する。 */
class Code : public NumberedText {
public:
    QList<QTextEdit::ExtraSelection> spellingSelections;
    /** @brief 現在行の背景とスペル波線を合成し、カーソル移動でも波線を保持する。 */
    void updateDecorations() {
        QTextEdit::ExtraSelection line;
        line.format.setBackground(QColor("#282828"));
        line.format.setProperty(QTextFormat::FullWidthSelection,true);
        line.cursor=textCursor(); line.cursor.clearSelection();
        auto selections=spellingSelections; selections.prepend(line); setExtraSelections(selections);
    }
    /** @brief 表示範囲だけを検査し、文字の位置に青い波線を付ける。
     * @param spelling Windows辞書を所有するエンジン。
     */
    void checkSpelling(Spelling& spelling) {
        spellingSelections.clear();
        auto block=firstVisibleBlock(); const int base=block.position(); QString text;
        while (block.isValid() && text.size()<8000 && blockBoundingGeometry(block).translated(contentOffset()).top()<viewport()->height()) {
            text+=block.text()+'\n'; block=block.next();
        }
        QElapsedTimer elapsed; elapsed.start();
        for (const auto& range: spelling.check(text)) {
            QTextEdit::ExtraSelection marker;
            marker.cursor=QTextCursor(document()); marker.cursor.setPosition(base+range.first);
            marker.cursor.setPosition(base+range.first+range.second,QTextCursor::KeepAnchor);
            marker.format.setUnderlineStyle(QTextCharFormat::WaveUnderline);
            marker.format.setUnderlineColor(QColor("#4fc1ff"));
            marker.format.setToolTip("Unknown English word"); spellingSelections.append(marker);
        }
        setProperty("spellCheckMilliseconds",elapsed.elapsed());
        setProperty("spellCheckAvailable",spelling.available()); updateDecorations();
    }
    bool smartIndent = true;
    Highlight* highlight;
    /**
     * @brief タブが保持する言語モードを確認する。
     * @return MELならtrue、Pythonならfalse。
     */
    bool isMel() const { return property("language").toString()=="mel"; }
    bool backspaceIndent = true;
    QCompleter* completer;
    std::function<void()> request;
    std::function<void()> closeTab;
    std::function<void()> runSelection;
    /**
     * @brief Ctrl+EnterまたはテンキーEnterの実行操作を判定する。
     * @param e 判定するキーイベント。
     * @return スクリプト実行用の組み合わせならtrue。
     */
    bool executionKey(QKeyEvent* e) const {
        const auto mods = e->modifiers() & ~Qt::KeypadModifier;
        return ((e->key() == Qt::Key_Return || e->key() == Qt::Key_Enter) && mods == Qt::ControlModifier)
            || (e->key() == Qt::Key_Enter && mods == Qt::NoModifier);
    }
    /**
     * @brief 本文・行番号・補完候補・現在行の強調表示を構築する。
     * @param parent コード欄の所有者。
     */
    explicit Code(QWidget* parent = nullptr) : NumberedText(parent) {
        setObjectName("codeEditor");
        setFont(QFont("Consolas", 11)); setLineWrapMode(NoWrap);
        setTabStopDistance(fontMetrics().horizontalAdvance(' ') * 4);
        highlight=new Highlight(document());
        completer = new QCompleter(this);
        completer->setModel(new QStandardItemModel(completer));
        completer->setWidget(this); completer->setCaseSensitivity(Qt::CaseSensitive);
        completer->setCompletionMode(QCompleter::PopupCompletion);
        completer->popup()->setFont(QFont("Consolas", 11));
        completer->popup()->setStyleSheet("QAbstractItemView{background:#252526;color:#d4d4d4;border:1px solid #454545;selection-background-color:#094771;selection-color:#ffffff;padding:3px;}");
        connect(completer, QOverload<const QString&>::of(&QCompleter::activated), this, [this](const QString& value) {
            acceptingCompletion=true;
            auto cursor = textCursor();
            cursor.movePosition(QTextCursor::Left, QTextCursor::KeepAnchor, prefix().size());
            cursor.insertText(value); setTextCursor(cursor);
            acceptingCompletion=false;
            completer->popup()->hide();
        });
        connect(this, &QPlainTextEdit::updateRequest, this, [this] { update(); });
        connect(this, &QPlainTextEdit::cursorPositionChanged, this, [this] {
            updateDecorations();
        });
    }
    enum EditOp { None, Comment, Indent, Outdent, MoveUp, MoveDown, CopyUp, CopyDown, DeleteLines, SelectLine, CopyLine, CutLine, Redo, Wrap, CloseTab };
    // 候補挿入はユーザーの次の入力とは区別し、再補完を予約しない。
    bool acceptingCompletion=false;
    /**
     * @brief キー入力をテキスト編集操作の列挙値へ変換する。
     * @param e 判定するキーイベント。
     * @return 対応する編集操作。対象外ならNone。
     */
    EditOp operation(QKeyEvent* e) const {
        const auto mods = e->modifiers(); const int key = e->key();
        if (mods == Qt::ControlModifier) {
            if (key == Qt::Key_W || key == Qt::Key_F4) return CloseTab;
            if (key == Qt::Key_Slash) return Comment;
            if (key == Qt::Key_BracketRight) return Indent;
            if (key == Qt::Key_BracketLeft) return Outdent;
            if (key == Qt::Key_L) return SelectLine;
            if (!textCursor().hasSelection() && key == Qt::Key_C) return CopyLine;
            if (!textCursor().hasSelection() && key == Qt::Key_X) return CutLine;
        }
        if (mods == (Qt::ControlModifier | Qt::ShiftModifier)) {
            if (key == Qt::Key_K) return DeleteLines;
            if (key == Qt::Key_Z) return Redo;
        }
        if (mods == Qt::AltModifier) {
            if (key == Qt::Key_Up) return MoveUp;
            if (key == Qt::Key_Down) return MoveDown;
            if (key == Qt::Key_Z) return Wrap;
        }
        if (mods == (Qt::AltModifier | Qt::ShiftModifier)) {
            if (key == Qt::Key_Up) return CopyUp;
            if (key == Qt::Key_Down) return CopyDown;
        }
        if ((key == Qt::Key_Backtab || key == Qt::Key_Tab) && mods == Qt::ShiftModifier) return Outdent;
        if (key == Qt::Key_Tab && mods == Qt::NoModifier && textCursor().hasSelection()) return Indent;
        return None;
    }
    /**
     * @brief 選択範囲が触れる行を求める。次行の先頭だけの選択は除く。
     * @return 0始まりの先頭行・末尾行。選択なしなら現在行。
     */
    QPair<int, int> lines() const {
        auto c = textCursor();
        int first = document()->findBlock(c.selectionStart()).blockNumber();
        int end = c.selectionEnd();
        if (c.hasSelection() && end > 0 && document()->findBlock(end).position() == end) --end;
        return {first, document()->findBlock(end).blockNumber()};
    }
    /**
     * @brief 行編集を1つのUndo単位で行い、カーソルと選択範囲を戻す。
     * @param op 移動・複製・コメントなどの編集種別。
     */
    void editLines(EditOp op) {
        if (op == Redo) { redo(); return; }
        if (op == Wrap) { setLineWrapMode(lineWrapMode() == NoWrap ? WidgetWidth : NoWrap); return; }
        const auto range = lines(); const int first = range.first, last = range.second;
        const bool selected = textCursor().hasSelection();
        const int column = textCursor().positionInBlock();
        auto c = textCursor();
        auto startBlock = document()->findBlockByNumber(first);
        auto endBlock = document()->findBlockByNumber(last);
        int start = startBlock.position(), end = endBlock.position() + endBlock.text().size();
        if (op == SelectLine) {
            // Ctrl+Lを繰り返すと次の行まで選択を拡張する。
            int target = selected && endBlock.next().isValid() ? endBlock.next().position() + endBlock.next().length() : end + 1;
            c.setPosition(start); c.setPosition(qMin(target, document()->characterCount()-1), QTextCursor::KeepAnchor); setTextCursor(c); return;
        }
        if (op == CopyLine || op == CutLine) QApplication::clipboard()->setText(startBlock.text() + "\n");
        if (op == CopyLine) return;
        if (op == DeleteLines || op == CutLine) {
            if (endBlock.next().isValid()) ++end;
            else if (start > 0) --start;
            c.beginEditBlock(); c.setPosition(start); c.setPosition(end, QTextCursor::KeepAnchor); c.removeSelectedText(); c.endEditBlock(); setTextCursor(c); return;
        }
        QStringList text;
        for (int i=first; i<=last; ++i) text.append(document()->findBlockByNumber(i).text());
        int resultFirst = first;
        if (op == MoveUp || op == MoveDown || op == CopyUp || op == CopyDown) {
            QStringList replacement = text;
            if (op == MoveUp) {
                if (!first) return;
                start = startBlock.previous().position(); replacement.append(startBlock.previous().text()); resultFirst--;
            } else if (op == MoveDown) {
                if (!endBlock.next().isValid()) return;
                end = endBlock.next().position() + endBlock.next().text().size(); replacement.prepend(endBlock.next().text()); resultFirst++;
            } else {
                replacement.append(text); if (op == CopyDown) resultFirst += text.size();
            }
            c.beginEditBlock(); c.setPosition(start); c.setPosition(end, QTextCursor::KeepAnchor); c.insertText(replacement.join("\n")); c.endEditBlock();
            auto target = document()->findBlockByNumber(resultFirst);
            c.setPosition(target.position() + qMin(column, int(target.text().size())));
            if (selected) { c.setPosition(target.position()); auto tail=document()->findBlockByNumber(resultFirst+text.size()-1); c.setPosition(tail.position()+tail.text().size(), QTextCursor::KeepAnchor); }
            setTextCursor(c); return;
        }
        const QString marker=isMel()?"//":"#";
        bool uncomment = true;
        for (const auto& line : text) if (!line.trimmed().isEmpty() && !line.trimmed().startsWith(marker)) uncomment=false;
        int columnDelta = 0;
        for (int i=0; i<text.size(); ++i) {
            auto& line = text[i]; int delta=0;
            if (op == Indent) { line.prepend("    "); delta=4; }
            else if (op == Outdent) {
                int count=0; if (line.startsWith('\t')) count=1;
                else while (count < 4 && count < line.size() && line[count]==' ') ++count;
                line.remove(0,count); delta=-count;
            } else if (op == Comment && !line.trimmed().isEmpty()) {
                int pos=0; while (pos<line.size() && line[pos].isSpace()) ++pos;
                if (uncomment) { int count=marker.size(); if (pos+count<line.size() && line[pos+count]==' ') ++count; line.remove(pos,count); if (column>pos) delta=-count; }
                else { line.insert(pos,marker+" "); if (column>=pos) delta=marker.size()+1; }
            }
            if (i==0) columnDelta=delta;
        }
        c.beginEditBlock(); c.setPosition(start); c.setPosition(end,QTextCursor::KeepAnchor); c.insertText(text.join("\n")); c.endEditBlock();
        if (selected) { c.setPosition(start); c.setPosition(start+text.join("\n").size(),QTextCursor::KeepAnchor); }
        else c.setPosition(start+qBound(0,column+columnDelta,int(text[0].size())));
        setTextCursor(c);
    }
    /**
     * @brief カーソル直前の識別子を補完用に取得する。
     * @return 現在行の英数字とアンダースコア。ドットは含まない。
     */
    QString prefix() const {
        auto cursor = textCursor(); cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
        return QRegularExpression("[A-Za-z_0-9]*$").match(cursor.selectedText()).captured();
    }
    /**
     * @brief 本文の描画をQtへ委譲する。行番号は親ウィジェット側で描く。
     * @param event 再描画対象を持つQtイベント。
     */
    void paintEvent(QPaintEvent* event) override { QPlainTextEdit::paintEvent(event); }
    /**
     * @brief Qtイベントを受け取り、対象外のイベントは基底クラスへ渡す。
     * @param event Qt所有のイベント。ここでは削除しない。
     * @return このウィジェットでイベントを処理した場合true。
     */
    bool event(QEvent* event) override {
        if (event->type() == QEvent::ShortcutOverride && executionKey(static_cast<QKeyEvent*>(event))) { event->accept(); return true; }
        if (event->type() == QEvent::ShortcutOverride && operation(static_cast<QKeyEvent*>(event)) != None) { event->accept(); return true; }
        return NumberedText::event(event);
    }
    /**
     * @brief エディタ専用キーを処理し、残りはQt標準の入力処理へ渡す。
     * @param event キーと修飾キーの情報。Qtが所有する。
     */
    void keyPressEvent(QKeyEvent* event) override {
        if (executionKey(event)) {
            completer->popup()->hide();
            if (runSelection) runSelection();
            event->accept(); return;
        }
        if (completer->popup()->isVisible()) {
            switch (event->key()) {
            case Qt::Key_Enter: case Qt::Key_Return: case Qt::Key_Escape: case Qt::Key_Tab:
                event->ignore(); return;
            }
        }
        auto op = operation(event);
        if (op == CloseTab) { if (closeTab) closeTab(); event->accept(); return; }
        if (op != None) { editLines(op); event->accept(); return; }
        if (event->key() == Qt::Key_Space && event->modifiers() == Qt::ControlModifier) {
            if (request) request(); return;
        }
        if (event->key() == Qt::Key_Tab && event->modifiers() == Qt::NoModifier) { insertPlainText("    "); return; }
        if (backspaceIndent && event->key()==Qt::Key_Backspace && event->modifiers()==Qt::NoModifier && !textCursor().hasSelection()) {
            auto c=textCursor(); auto before=c.block().text().left(c.positionInBlock());
            if (!before.isEmpty() && before==QString(before.size(),' ')) {
                int count=(before.size()-1)%4+1; c.beginEditBlock();
                for (int i=0;i<count;++i) c.deletePreviousChar();
                c.endEditBlock(); setTextCursor(c); return;
            }
        }
        if (event->key() == Qt::Key_Return && event->modifiers() == Qt::NoModifier) {
            if (!smartIndent) { insertPlainText("\n"); return; }
            auto cursor = textCursor(); cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
            QString before = cursor.selectedText();
            QString indent = QRegularExpression("^ *").match(before).captured();
            if (before.trimmed().endsWith(isMel()?'{':':')) indent += "    ";
            insertPlainText("\n" + indent); return;
        }
        QPlainTextEdit::keyPressEvent(event);
    }
};

/** @brief 編集画面全体を所有し、Mayaへの処理は注入されたコールバックへ委譲する。 */
class Window : public QMainWindow {
    QTabWidget* tabs;
    Explorer* explorer;
    QDockWidget* explorerDock;
    QComboBox* languageMode;
    QLabel* searchCount;
    Execute executeMel;
    Output* output;
    QWidget* outputPanel;
    QComboBox* outputMode;
    QList<OutputMessage> outputHistory;
    int outputHistorySize=0;
    QLabel* completionStatus;
    QWidget* findBar;
    QWidget* replacePanel;
    QLineEdit* findText;
    QLineEdit* replacement;
    QCheckBox* matchCase;
    QCheckBox* wholeWord;
    QCheckBox* regexSearch;
    QTimer debounce;
    Completion complete;
    Execute execute;
    Configuration configuration;
    OutputReader outputReader;
    QTimer outputTimer;
    QElapsedTimer directOutputClock;
    bool refreshingOutput=false;
    QTimer spellingTimer;
    Spelling spelling;
    /** @brief 入力が止まるまで検査を待ち、OFF時は全タブの古い波線も消す。 */
    void scheduleSpelling() {
        spellingTimer.stop();
        if (!option("spellCheck")) {
            for (int i=0;i<tabs->count();++i) { auto code=static_cast<Code*>(tabs->widget(i)); code->spellingSelections.clear(); code->updateDecorations(); }
        } else if (current()) spellingTimer.start(450);
    }
public:
    QString sessionPath;
    std::unique_ptr<QLockFile> sessionLock;
    QTimer sessionTimer;
    QElapsedTimer lastEdit;
    QByteArray lastSession;
    std::unique_ptr<QSettings> preferences;
    QHash<QString, bool> options;
    int fontPixels=14;
    /**
     * @brief コードと出力の文字サイズを10〜28pxに制限して保存する。
     * @param size 要求されたピクセル単位の文字サイズ。
     */
    void setZoom(int size) {
        fontPixels=qBound(10,size,28);
        setStyleSheet(QString("QPlainTextEdit#codeEditor,QPlainTextEdit#output{background:#1e1e1e;color:#d4d4d4;"
            "font-family:'Consolas';selection-background-color:#264f78;selection-color:#d4d4d4;}"
            "QPlainTextEdit#codeEditor{font-size:%1px;} QPlainTextEdit#output{font-size:%2px;}").arg(fontPixels).arg(fontPixels-2));
        if (preferences) { preferences->setValue("fontPixels",fontPixels); preferences->sync(); }
        statusBar()->showMessage(QString("Font size: %1 px").arg(fontPixels),2000);
    }
    Completion analyze;
    QTimer analysisTimer;
    QListWidget* problems;
    /**
     * @brief 古い診断を消し、アクティブなPythonタブだけを遅延解析する。
     */
    void scheduleAnalysis() {
        analysisTimer.stop(); problems->clear();
        problems->setVisible(option("staticAnalysis") && current() && !current()->isMel());
        if (option("staticAnalysis") && current() && !current()->isMel()) { problems->addItem("Checking after typing stops…"); analysisTimer.start(); }
    }
    /**
     * @brief アクティブタブを実行せずに構文診断し、問題一覧へ反映する。
     */
    void runAnalysis() {
        if (!option("staticAnalysis") || !analyze || !current() || current()->isMel()) return;
        problems->clear();
        auto response=QJsonDocument::fromJson(analyze(current()->toPlainText())).object();
        if (response.contains("skipped")) { problems->addItem(response["skipped"].toString()); return; }
        if (!response.contains("diagnostics")) { problems->addItem("Analysis unavailable"); return; }
        for (auto entry: response["diagnostics"].toArray()) {
            auto diagnostic=entry.toObject(); int line=diagnostic["line"].toInt(1);
            auto item=new QListWidgetItem(QString("%1 — Line %2: %3").arg(diagnostic["severity"].toString()).arg(line).arg(diagnostic["message"].toString()),problems);
            item->setData(Qt::UserRole,line);
            item->setForeground(diagnostic["severity"].toString()=="error" ? QColor("#f48771") : QColor("#dcdcaa"));
        }
        if (!problems->count()) problems->addItem("No syntax problems found (type checking is not performed)");
    }
    /**
     * @brief 保持している編集設定を取得する。
     * @param key 設定の識別名。
     * @return オンならtrue。未登録はfalse。
     */
    bool option(const QString& key) const { return options.value(key); }
    /**
     * @brief 設定を指定のコード欄へ適用する。
     * @param code 適用先のタブ。
     */
    void applyOptions(Code* code) {
        code->smartIndent=option("smartIndent"); code->backspaceIndent=option("backspaceIndent");
        auto format=code->document()->defaultTextOption();
        format.setFlags(option("whitespace") ? format.flags() | QTextOption::ShowTabsAndSpaces : format.flags() & ~QTextOption::ShowTabsAndSpaces);
        code->document()->setDefaultTextOption(format);
    }
    /**
     * @brief 各部品・メニュー・タイマーを組み立て、保存済みタブを復元する。
     * @param parent Qtの所有者。
     * @param run Python実行用コールバック。
     * @param snapshot 補完環境を更新するコールバック。
     * @param reader Maya出力を取り出すコールバック。
     * @param completion Pythonの補完候補を返すコールバック。
     * @param recoveryPath 復元JSONの絶対パス。空なら復元を無効化。
     * @param analyzer 構文診断用コールバック。
     * @param melRun MEL実行用コールバック。
     */
    Window(QWidget* parent, Execute run, Configuration snapshot, OutputReader reader, Completion completion, QString recoveryPath, Completion analyzer, Execute melRun) : QMainWindow(parent), execute(run), configuration(snapshot), outputReader(reader), complete(completion), sessionPath(recoveryPath), analyze(analyzer), executeMel(melRun) {
        setObjectName("hedit"); setWindowTitle("hedit - Python / MEL"); resize(1050, 740);
        setWindowFlags(parent ? Qt::Widget : Qt::Window);
        setStyleSheet(
            "QPlainTextEdit#codeEditor,QPlainTextEdit#output{background:#1e1e1e;color:#d4d4d4;"
            "font-family:'Consolas';font-size:14px;selection-background-color:#264f78;selection-color:#d4d4d4;}"
        );
        auto split = new QSplitter(Qt::Vertical, this);
        tabs = new EditorTabs; tabs->setTabsClosable(true); tabs->setMovable(true);
        output = new Output; output->setObjectName("output");
        output->setFont(QFont("Consolas", 10)); output->setMaximumBlockCount(5000);
        connect(&outputTimer, &QTimer::timeout, this, [this] { flushOutput(); });
        if (outputReader) outputTimer.start(25);
        output->setPlaceholderText(QString());
        output->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(output, &QWidget::customContextMenuRequested, this, [this](const QPoint& point) {
            auto menu = output->createStandardContextMenu();
            menu->setObjectName("outputContextMenu");
            menu->addSeparator();
            auto clear = menu->addAction("Clear output", this, [this] { clearOutput(); });
            clear->setObjectName("clearOutputAction");
            menu->exec(output->mapToGlobal(point));
            delete menu;
        });
        completionStatus = new QLabel("Completion: ready (in Maya)");
        completionStatus->setObjectName("completionStatus");
        statusBar()->addPermanentWidget(completionStatus);
        languageMode=new QComboBox; languageMode->setObjectName("languageMode"); languageMode->addItems({"Python","MEL"});
        languageMode->setToolTip("Language mode for the active tab"); statusBar()->addPermanentWidget(languageMode);
        connect(languageMode,QOverload<int>::of(&QComboBox::activated),this,[this](int index){ if (current()) setLanguage(current(),index==1?"mel":"python"); });
        explorerDock=new QDockWidget("EXPLORER",this); explorerDock->setObjectName("explorerDock");
        explorer=new Explorer(explorerDock); explorerDock->setWidget(explorer); addDockWidget(Qt::LeftDockWidgetArea,explorerDock);
        explorerDock->setMinimumWidth(240); explorerDock->hide();
        explorer->openFile=[this](const QString& path){ openPath(path); };
        outputPanel=new QWidget; outputPanel->setObjectName("outputPanel");
        auto outputLayout=new QVBoxLayout(outputPanel); outputLayout->setContentsMargins(0,0,0,0); outputLayout->setSpacing(0);
        outputMode=new QComboBox; outputMode->setObjectName("outputMode");
        outputMode->addItems({"Normal","Output only","Warnings + Errors","Errors only"});
        outputMode->setToolTip("Output display mode"); outputMode->setFixedWidth(150);
        outputLayout->addWidget(output);
        connect(outputMode,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this]{ output->clear(); appendOutput(outputHistory); });
        split->setObjectName("editorSplitter"); split->addWidget(outputPanel); split->addWidget(tabs); split->setSizes({350, 350});
        auto body = new QWidget(this); auto bodyLayout = new QVBoxLayout(body); bodyLayout->setContentsMargins(0,0,0,0);
        findBar = new QWidget(tabs); findBar->setObjectName("findBar"); auto searchRows = new QVBoxLayout(findBar); searchRows->setContentsMargins(3,2,3,2);
        auto searchLayout = new QHBoxLayout; searchRows->addLayout(searchLayout);
        searchLayout->setSpacing(2);
        auto expandReplace=new QPushButton(">"); expandReplace->setFixedWidth(22); expandReplace->setToolTip("Toggle replace"); searchLayout->addWidget(expandReplace);
        findBar->setStyleSheet("QWidget#findBar{background:#252526;} QLineEdit{background:#3c3c3c;color:#d4d4d4;border:1px solid #555;padding:2px;} QCheckBox,QLabel{color:#bdbdbd;font-size:12px;} QCheckBox{spacing:0;padding:2px;font-weight:bold;font-size:13px;} QCheckBox::indicator{width:0;height:0;} QCheckBox:checked{background:#515151;color:#ffffff;} QPushButton{background:transparent;border:0;color:#bdbdbd;padding:1px;font-weight:bold;font-size:16px;} QPushButton:hover{background:#505050;} QLineEdit:focus{border:1px solid #6b93b0;}");
        findText = new QLineEdit; findText->setObjectName("findText"); findText->setPlaceholderText("Find"); searchLayout->addWidget(findText);
        findText->setMinimumWidth(60);
        matchCase=new QCheckBox("Tt"); matchCase->setObjectName("searchCase"); matchCase->setToolTip("Match case"); searchLayout->addWidget(matchCase);
        wholeWord=new QCheckBox("Abc"); wholeWord->setObjectName("searchWord"); wholeWord->setToolTip("Whole words"); searchLayout->addWidget(wholeWord);
        regexSearch=new QCheckBox(".*"); regexSearch->setObjectName("searchRegex"); regexSearch->setToolTip("Regular expression; replacements support $1, $2, $& and $$"); searchLayout->addWidget(regexSearch);
        searchCount=new QLabel; searchCount->setMinimumWidth(54); searchCount->setObjectName("searchCount"); searchLayout->addWidget(searchCount);
        auto previous = new QPushButton("←"); previous->setToolTip("Previous match (Shift+F3)"); auto next = new QPushButton("→"); next->setToolTip("Next match (F3)"); searchLayout->addWidget(previous); searchLayout->addWidget(next);
        previous->setFixedWidth(24); next->setFixedWidth(24);
        connect(previous,&QPushButton::clicked,this,[this]{ findNext(true); }); connect(next,&QPushButton::clicked,this,[this]{ findNext(); });
        connect(findText,&QLineEdit::returnPressed,this,[this]{ findNext(); });
        connect(findText,&QLineEdit::textEdited,this,[this]{ searchWhileTyping(); });
        replacePanel = new QWidget; auto replaceLayout=new QHBoxLayout(replacePanel); replaceLayout->setContentsMargins(0,0,0,0);
        replacement = new QLineEdit; replacement->setObjectName("replaceText"); replacement->setPlaceholderText("Replace"); replaceLayout->addWidget(replacement);
        auto replaceOne=new QPushButton("Replace"); replaceOne->setObjectName("replaceOne"); auto replaceAll=new QPushButton("Replace all"); replaceAll->setObjectName("replaceAll");
        replaceLayout->addWidget(replaceOne); replaceLayout->addWidget(replaceAll); searchRows->addWidget(replacePanel);
        connect(replaceOne,&QPushButton::clicked,this,[this]{ replace(false); }); connect(replaceAll,&QPushButton::clicked,this,[this]{ replace(true); });
        auto closeSearch=new QPushButton("×"); searchLayout->addWidget(closeSearch);
        closeSearch->setFixedWidth(24);
        connect(expandReplace,&QPushButton::clicked,this,[this]{ replacePanel->setVisible(!replacePanel->isVisible()); positionSearch(); });
        connect(closeSearch,&QPushButton::clicked,this,[this]{ findBar->hide(); current()->setFocus(); });
        auto escape=new QShortcut(QKeySequence(Qt::Key_Escape),findBar); escape->setContext(Qt::WidgetWithChildrenShortcut);
        connect(escape,&QShortcut::activated,closeSearch,&QPushButton::click);
        bodyLayout->addWidget(split); findBar->hide(); tabs->installEventFilter(this); setCentralWidget(body);
        problems=new QListWidget(body); problems->setObjectName("analysisProblems"); problems->setMaximumHeight(140); problems->hide(); bodyLayout->addWidget(problems);
        connect(problems,&QListWidget::itemClicked,this,[this](QListWidgetItem* item) {
            int line=item->data(Qt::UserRole).toInt(); if (line<1) return;
            auto block=current()->document()->findBlockByNumber(line-1); if (!block.isValid()) return;
            auto cursor=current()->textCursor(); cursor.setPosition(block.position()); current()->setTextCursor(cursor); current()->setFocus(); current()->ensureCursorVisible();
        });
        analysisTimer.setSingleShot(true); analysisTimer.setInterval(800);
        connect(&analysisTimer,&QTimer::timeout,this,[this]{ runAnalysis(); });
        auto file = menuBar()->addMenu("File");
        auto add = file->addAction("New Python tab", this, [this] { newTab(); }); add->setShortcut(QKeySequence::New);
        file->addAction("New MEL tab", this, [this] { newTab("mel"); });
        auto openScript=file->addAction("Open…", this, [this] {
            openPath(QFileDialog::getOpenFileName(this,"Open script",{},"Scripts (*.py *.mel);;All files (*)"));
        }, QKeySequence::Open);
        file->addAction("Open folder…",this,[this]{ auto path=QFileDialog::getExistingDirectory(this,"Open folder"); if (!path.isEmpty()) { explorer->addFolder(path,true); explorerDock->show(); } });
        file->addAction("Add folder…",this,[this]{ auto path=QFileDialog::getExistingDirectory(this,"Add folder"); if (!path.isEmpty()) { explorer->addFolder(path); explorerDock->show(); } });
        auto saveScript=file->addAction("Save", this, [this] { save(current()); }, QKeySequence::Save);
        auto edit = menuBar()->addMenu("Edit");
        if (!sessionPath.isEmpty()) preferences.reset(new QSettings(QFileInfo(sessionPath).absolutePath()+"/preferences.ini",QSettings::IniFormat));
        setZoom(preferences ? preferences->value("fontPixels",14).toInt() : 14);
        auto view=menuBar()->addMenu("View");
        auto sidebar=explorerDock->toggleViewAction(); sidebar->setText("Explorer"); sidebar->setObjectName("toggleExplorer"); sidebar->setShortcut(QKeySequence("Ctrl+B")); view->addAction(sidebar);
        auto zoomIn=view->addAction("Zoom in",this,[this]{ setZoom(fontPixels+1); }); zoomIn->setObjectName("zoomIn");
        zoomIn->setShortcuts({QKeySequence("Ctrl++"),QKeySequence("Ctrl+=" )});
        auto zoomOut=view->addAction("Zoom out",this,[this]{ setZoom(fontPixels-1); },QKeySequence("Ctrl+-")); zoomOut->setObjectName("zoomOut");
        auto zoomReset=view->addAction("Reset zoom",this,[this]{ setZoom(14); },QKeySequence("Ctrl+0")); zoomReset->setObjectName("zoomReset");
        auto settings=edit->addMenu("Preferences");
        auto toggle=[this,settings](const QString& key,const QString& label,bool fallback) {
            options[key]=preferences ? preferences->value(key,fallback).toBool() : fallback;
            auto action=settings->addAction(label); action->setObjectName("option_"+key); action->setCheckable(true); action->setChecked(option(key));
            connect(action,&QAction::toggled,this,[this,key](bool enabled) {
                options[key]=enabled;
                if (preferences) { preferences->setValue(key,enabled); preferences->sync();
                    if (preferences->status()!=QSettings::NoError) statusBar()->showMessage("Could not save editor preferences"); }
                for (int i=0;i<tabs->count();++i) { auto code=static_cast<Code*>(tabs->widget(i)); applyOptions(code); code->completer->popup()->hide(); }
                if (key=="staticAnalysis") scheduleAnalysis();
                if (key=="outputLineNumbers") output->setLineNumbersVisible(enabled);
                if (key=="outputWrap") output->setLineWrapMode(enabled ? QPlainTextEdit::WidgetWidth : QPlainTextEdit::NoWrap);
                if (key=="spellCheck") scheduleSpelling();
            });
        };
        toggle("completeLetters","Completion while typing",true);
        toggle("completeDot","Completion after dot",true);
        toggle("includeKeywords","Include Python keywords",true);
        toggle("includeBuiltins","Include Python built-ins",true);
        toggle("staticAnalysis","Static analysis (syntax / warnings)",false);
        toggle("outputLineNumbers","Show output line numbers",false);
        output->setLineNumbersVisible(option("outputLineNumbers"));
        toggle("outputWrap","Wrap output lines",false);
        output->setLineWrapMode(option("outputWrap") ? QPlainTextEdit::WidgetWidth : QPlainTextEdit::NoWrap);
        toggle("spellCheck","Spell check (English)",true);
        spellingTimer.setSingleShot(true);
        connect(&spellingTimer,&QTimer::timeout,this,[this]{
            if (option("spellCheck") && current()) {
                current()->checkSpelling(spelling);
                if (!spelling.available()) statusBar()->showMessage("English spell-check dictionary is unavailable on this Windows installation",5000);
            }
        });
        settings->addSeparator();
        toggle("smartIndent","Smart indentation",true);
        toggle("backspaceIndent","Backspace to indentation stop",true);
        toggle("whitespace","Show spaces and tabs",false);
        settings->addSeparator();
        toggle("trimWhitespace","Trim trailing spaces on file save",false);
        toggle("finalNewline","Ensure final newline on file save",false);
        edit->addAction("Find…", this, [this] { openFind(false); }, QKeySequence("Ctrl+F"));
        edit->addAction("Replace…", this, [this] { openFind(true); }, QKeySequence("Ctrl+H"));
        edit->addAction("Find next", this, [this] { findNext(); }, QKeySequence("F3"));
        edit->addAction("Find previous", this, [this] { findNext(true); }, QKeySequence("Shift+F3"));
        edit->addAction("Go to line…", this, [this] {
            QPlainTextEdit* target=output->hasFocus() ? output : static_cast<QPlainTextEdit*>(current());
            if (auto existing=findChild<QLineEdit*>("lineJump")) { existing->setFocus(); existing->selectAll(); return; }
            auto input=new QLineEdit(this);
            input->setObjectName("lineJump");
            input->setPlaceholderText("Go to line (Enter / Esc)");
            input->setValidator(new QIntValidator(1,target->document()->blockCount(),input));
            input->setText(QString::number(target->textCursor().blockNumber()+1));
            statusBar()->addWidget(input,1);
            auto finish=[this,input,target] {
                statusBar()->removeWidget(input);
                input->setObjectName(QString());
                input->hide(); input->deleteLater();
                target->setFocus(Qt::ShortcutFocusReason);
            };
            connect(target,&QObject::destroyed,input,&QObject::deleteLater);
            connect(input,&QLineEdit::returnPressed,target,[target,input,finish] {
                auto block=target->document()->findBlockByNumber(input->text().toInt()-1);
                if (!block.isValid()) return;
                auto cursor=target->textCursor(); cursor.setPosition(block.position());
                target->setTextCursor(cursor); target->centerCursor(); finish();
            });
            auto cancel=new QShortcut(QKeySequence(Qt::Key_Escape),input);
            cancel->setContext(Qt::WidgetWithChildrenShortcut);
            connect(cancel,&QShortcut::activated,target,finish);
            input->show(); input->setFocus(); input->selectAll();
        }, QKeySequence("Ctrl+G"));
        file->addAction("Save as…", this, [this] { save(current(),true); }, QKeySequence("Ctrl+Shift+S"));
        auto closeTab=file->addAction("Close tab", this, [this] { close(tabs->currentIndex()); });
        closeTab->setShortcuts({QKeySequence("Ctrl+W"),QKeySequence("Ctrl+F4")});
        auto tabMenu=menuBar()->addMenu("Tabs");
        auto nextTab=tabMenu->addAction("Next tab",this,[this]{ switchTab(1); });
        nextTab->setShortcuts({QKeySequence("Ctrl+Tab"),QKeySequence("Ctrl+PgDown")});
        auto prevTab=tabMenu->addAction("Previous tab",this,[this]{ switchTab(-1); });
        prevTab->setShortcuts({QKeySequence("Ctrl+Shift+Tab"),QKeySequence("Ctrl+PgUp")});
        auto history=menuBar()->addMenu("History");
        auto clearLog=history->addAction("Clear output",this,[this]{ clearOutput(); });
        // 入力消去は文書の編集として実行する。Ctrl+Zで本文を取り戻せる。
        auto clearInput=[this]{ if (auto code=current()) { auto cursor=code->textCursor(); cursor.select(QTextCursor::Document); cursor.removeSelectedText(); code->setTextCursor(cursor); } };
        auto clearCode=edit->addAction("Clear input",this,clearInput);
        auto clearBoth=edit->addAction("Clear input and output",this,[this,clearInput]{ clearInput(); clearOutput(); });
        auto showOutput=view->addAction("Show output only",this,[this,split]{ outputPanel->show(); tabs->hide(); split->setSizes({1,0}); });
        auto showInput=view->addAction("Show input only",this,[this,split]{ tabs->show(); outputPanel->hide(); split->setSizes({0,1}); });
        auto showBoth=view->addAction("Show input and output",this,[this,split]{ outputPanel->show(); tabs->show(); split->setSizes({1,1}); });
        auto command=menuBar()->addMenu("Command");
        auto action = command->addAction("Run selection / script", this, [this] { runCode(false); });
        action->setShortcut(QKeySequence("Ctrl+Return"));
        auto all = command->addAction("Run all", this, [this] { runCode(true); }); all->setShortcut(QKeySequence("F5"));
        command->addSeparator();
        command->addAction("Refresh completion", this, [this] { refreshCompletion(); });
        auto toolbar = addToolBar("Script editor"); toolbar->setObjectName("scriptToolbar"); toolbar->setMovable(false);
        toolbar->setToolButtonStyle(Qt::ToolButtonIconOnly); toolbar->setIconSize(QSize(20,20));
        // Maya同梱リソースを直接参照し、画像を複製・同梱しない。
        // MayaなしのテストではQt標準アイコンを代用する。メニューと同じActionで機能を共有する。
        auto iconAction=[this,toolbar](QAction* item,const QString& image,QStyle::StandardPixmap fallback) {
            QIcon icon(":"+QString("/")+image);
            if (icon.isNull()) icon=style()->standardIcon(fallback);
            item->setIcon(icon); item->setToolTip(item->text()+(item->shortcut().isEmpty()?QString():" ("+item->shortcut().toString(QKeySequence::NativeText)+")"));
            toolbar->addAction(item);
        };
        iconAction(openScript,"openScript.png",QStyle::SP_DialogOpenButton);
        iconAction(saveScript,"save.png",QStyle::SP_DialogSaveButton);
        toolbar->addSeparator();
        iconAction(clearLog,"clearHistory.png",QStyle::SP_TrashIcon);
        iconAction(clearCode,"clearInput.png",QStyle::SP_DialogResetButton);
        iconAction(clearBoth,"clearAll.png",QStyle::SP_DialogDiscardButton);
        toolbar->addSeparator();
        iconAction(showOutput,"showHistory.png",QStyle::SP_TitleBarMaxButton);
        iconAction(showInput,"showInput.png",QStyle::SP_FileIcon);
        iconAction(showBoth,"showBoth.png",QStyle::SP_TitleBarNormalButton);
        toolbar->addSeparator();
        iconAction(all,"executeAll.png",QStyle::SP_MediaSkipForward);
        iconAction(action,"execute.png",QStyle::SP_MediaPlay);
        toolbar->addSeparator();
        iconAction(sidebar,"outliner.png",QStyle::SP_DirIcon);
        toolbar->addSeparator(); toolbar->addWidget(outputMode);
        connect(tabs, &QTabWidget::tabCloseRequested, this, [this](int index) { close(index); });
        // Mayaの他パネルにフォーカスがある時にはショートカットを横取りしない。
        for (auto action : findChildren<QAction*>()) {
            if (action->shortcuts().isEmpty()) continue;
            addAction(action); action->setShortcutContext(Qt::WidgetWithChildrenShortcut);
        }
        connect(tabs, &QTabWidget::currentChanged, this, [this] { debounce.stop(); if(current()) languageMode->setCurrentIndex(current()->isMel()?1:0); scheduleAnalysis(); scheduleSpelling(); });
        debounce.setSingleShot(true); debounce.setInterval(250);
        connect(&debounce, &QTimer::timeout, this, [this] { request(false); });
        newTab()->setPlainText("import maya.cmds as cmds\n\n# Ctrl+Space: completion    Ctrl+Enter: run\nprint(cmds.ls(selection=True))\n");
        current()->document()->setModified(false); updateTitle(current());
        restoreSession();
        sessionTimer.setInterval(1000);
        // 入力中に全タブをJSON化してディスクへ書かない。終了時は別途必ず保存する。
        connect(&sessionTimer, &QTimer::timeout, this, [this] { if (!lastEdit.isValid() || lastEdit.elapsed()>=1500) saveSession(); });
        connect(qApp, &QCoreApplication::aboutToQuit, this, [this] { saveSession(); });
        sessionTimer.start();
        refreshCompletion();
        scheduleAnalysis();
    }
    /**
     * @brief 破棄前に未保存のタブ内容を復元ファイルへ保存する。
     */
    ~Window() override { saveSession(); }
    /**
     * @brief 本文・言語・選択・Explorerを原子的に保存する。元ファイルは変更しない。
     * @return 保存成功または変更なしならtrue。ロック失敗や書込失敗はfalse。
     */
    bool saveSession() {
        if (!sessionLock || !sessionLock->isLocked()) return false;
        QJsonArray entries;
        for (int i=0; i<tabs->count(); ++i) {
            auto code=static_cast<Code*>(tabs->widget(i)); auto cursor=code->textCursor();
            entries.append(QJsonObject{{"text",code->toPlainText()},{"path",code->property("path").toString()},
                {"language",code->isMel()?"mel":"python"},{"modified",code->document()->isModified()},{"position",cursor.position()},{"anchor",cursor.anchor()}});
        }
        auto bytes=QJsonDocument(QJsonObject{{"version",1},{"active",tabs->currentIndex()},{"tabs",entries},{"folders",QJsonArray::fromStringList(explorer->roots())},{"explorerVisible",!explorerDock->isHidden()}}).toJson();
        if (bytes==lastSession) return true;
        QSaveFile file(sessionPath);
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes)!=bytes.size() || !file.commit()) {
            statusBar()->showMessage("Tab recovery save failed: " + file.errorString()); return false;
        }
        lastSession=bytes; return true;
    }
    /**
     * @brief 復元ファイルを検証して読み込む。破損時は元ファイルを保持する。
     */
    void restoreSession() {
        if (sessionPath.isEmpty()) return;
        if (!QDir().mkpath(QFileInfo(sessionPath).absolutePath())) {
            output->appendPlainText("Tab recovery unavailable: cannot create recovery directory."); return;
        }
        sessionLock.reset(new QLockFile(sessionPath+".lock"));
        if (!sessionLock->tryLock(0)) {
            output->appendPlainText("Tab recovery is in use by another Maya. This window will not overwrite it."); return;
        }
        QFile file(sessionPath);
        if (!file.exists()) return;
        QJsonParseError error;
        bool readable=file.open(QIODevice::ReadOnly);
        auto doc=QJsonDocument::fromJson(readable ? file.readAll() : QByteArray(), &error);
        auto root=doc.object(); auto entries=root.value("tabs").toArray();
        bool valid=readable && error.error==QJsonParseError::NoError && root.value("version").toInt()==1 && !entries.isEmpty();
        for (auto entry: entries) { auto obj=entry.toObject(); valid=valid && obj.value("text").isString() && obj.value("path").isString() && obj.value("modified").isBool(); }
        if (!valid) {
            output->appendPlainText("Tab recovery file could not be read. It has been preserved: " + sessionPath);
            sessionLock->unlock(); return;
        }
        while (tabs->count()) { auto widget=tabs->widget(0); tabs->removeTab(0); delete widget; }
        for (auto entry: entries) {
            auto obj=entry.toObject(); auto code=newTab(obj.value("language").toString("python")); code->setPlainText(obj.value("text").toString());
            auto path=obj.value("path").toString(); code->setProperty("path",path);
            // 元ファイルが削除・外部変更されていても復元した本文を未保存扱いで保持する。
            QFile original(path); bool differs=false;
            if (!path.isEmpty()) differs=!original.open(QIODevice::ReadOnly) || QString::fromUtf8(original.readAll())!=code->toPlainText();
            code->document()->setModified(obj.value("modified").toBool() || differs); updateTitle(code);
            auto cursor=code->textCursor(); int limit=code->document()->characterCount()-1;
            cursor.setPosition(qBound(0,obj.value("anchor").toInt(),limit));
            cursor.setPosition(qBound(0,obj.value("position").toInt(),limit),QTextCursor::KeepAnchor); code->setTextCursor(cursor);
        }
        QStringList folders; for (auto value:root.value("folders").toArray()) if(value.isString()) folders.append(value.toString());
        explorer->setRoots(folders); explorerDock->setVisible(root.value("explorerVisible").toBool()); updateExplorer();
        tabs->setCurrentIndex(qBound(0,root.value("active").toInt(),tabs->count()-1)); current()->setFocus();
    }
    /** @brief タブの言語を変更し、補完と静的解析の対象を切り替える。
     * @param code 対象のタブ。
     * @param language melまたはpython。未知の値はPython扱い。
     */
    void setLanguage(Code* code,const QString& language) {
        auto value=language=="mel"?QString("mel"):QString("python");
        code->setProperty("language",value); code->document()->setProperty("language",value);
        code->highlight->rehighlight(); code->completer->popup()->hide(); updateTitle(code);
        if (code==current()) { languageMode->setCurrentIndex(code->isMel()?1:0); scheduleAnalysis(); }
    }
    /** @brief 保存先を持つ全タブをExplorerのOPEN EDITORSへ同期する。 */
    void updateExplorer() {
        QStringList paths;
        for (int i=0;i<tabs->count();++i) { auto path=tabs->widget(i)->property("path").toString(); if (!path.isEmpty()) paths.append(path); }
        explorer->setOpenFiles(paths);
    }
    /** @brief UTF-8のスクリプトを開く。同一ファイルは既存タブを選択する。
     * @param path 保存済みファイルのパス。空文字は何もしない。
     */
    void openPath(const QString& path) {
        if (path.isEmpty()) return;
        auto absolute=QFileInfo(path).absoluteFilePath();
        for (int i=0;i<tabs->count();++i) if (QFileInfo(tabs->widget(i)->property("path").toString()).absoluteFilePath()==absolute) { tabs->setCurrentIndex(i); current()->setFocus(); return; }
        QFile file(absolute); if (!file.open(QIODevice::ReadOnly)) { QMessageBox::warning(this,"Open",file.errorString()); return; }
        auto bytes=file.readAll(); if (bytes.startsWith("\xef\xbb\xbf")) bytes.remove(0,3);
        auto text=QString::fromUtf8(bytes);
        if (text.toUtf8()!=bytes) { QMessageBox::warning(this,"Open","Only UTF-8 files are supported"); return; }
        auto code=newTab(QFileInfo(path).suffix().toLower()=="mel"?"mel":"python");
        code->setPlainText(text); code->setProperty("path",absolute); code->document()->setModified(false); updateTitle(code);
        explorer->addFolder(QFileInfo(absolute).absolutePath()); updateExplorer(); explorerDock->show();
    }
    /**
     * @brief 現在選択されているコード欄を取得する。
     * @return タブがない構築途中はnullptr。それ以外はQt所有のCode。
     */
    Code* current() const { return static_cast<Code*>(tabs->currentWidget()); }
    /**
     * @brief 指定言語のタブを作り、入力・実行・閉じる通知を接続する。
     * @param language pythonまたはmel。未知の値はPython扱い。
     * @return タブウィジェットが所有する新しいCode。呼出側でdeleteしない。
     */
    Code* newTab(const QString& language="python") {
        auto code = new Code;
        applyOptions(code);
        tabs->addTab(code, "Untitled.py"); setLanguage(code,language); tabs->setCurrentWidget(code);
        code->setFocus();
        code->request = [this] { request(); };
        code->runSelection = [this] { runCode(false); };
        // キーイベントの処理中にエディタ自身を削除しない。
        code->closeTab = [this, code] { QTimer::singleShot(0, code, [this, code] { close(tabs->indexOf(code)); }); };
        connect(code, &QPlainTextEdit::textChanged, this, [this, code] {
            lastEdit.restart();
            code->spellingSelections.clear(); code->updateDecorations();
            code->completer->popup()->hide(); debounce.stop();
            if (code==current() && !code->acceptingCompletion) debounce.start();
            updateTitle(code);
            if (code==current()) { scheduleAnalysis(); scheduleSpelling(); }
        });
        connect(code->verticalScrollBar(),&QScrollBar::valueChanged,this,[this,code]{ if (code==current()) scheduleSpelling(); });
        connect(code, &QPlainTextEdit::cursorPositionChanged, this, [this, code] {
            code->completer->popup()->hide();
            statusBar()->showMessage(QString("Ln %1, Col %2  |  UTF-8").arg(code->textCursor().blockNumber()+1).arg(code->textCursor().positionInBlock()+1));
        });
        return code;
    }
    /**
     * @brief 保存先・言語・未保存状態をタブ名に反映する。
     * @param code タイトルを更新するタブ。
     */
    void updateTitle(Code* code) {
        QString path = code->property("path").toString();
        QString title = path.isEmpty() ? (code->isMel()?"Untitled.mel":"Untitled.py") : QFileInfo(path).fileName();
        tabs->setTabText(tabs->indexOf(code), title + (code->document()->isModified() ? " ●" : ""));
    }
    /**
     * @brief UTF-8で元ファイルを原子的に保存し、成功後に未保存状態を解除する。
     * @param code 保存対象の本文。
     * @param saveAs trueなら保存先を毎回選択する。
     * @return 保存成功ならtrue。取消・書込失敗ならfalse。
     */
    bool save(Code* code, bool saveAs = false) {
        auto path = saveAs ? QString() : code->property("path").toString();
        if (path.isEmpty()) path = QFileDialog::getSaveFileName(this, "Save script", {}, code->isMel()?"MEL (*.mel)":"Python (*.py)");
        if (path.isEmpty()) return false;
        QString text=code->toPlainText();
        if (option("trimWhitespace")) text.replace(QRegularExpression("[ \\t]+(?=\\n|$)"),QString());
        if (option("finalNewline") && !text.endsWith('\n')) text+='\n';
        QSaveFile file(path); QByteArray bytes = text.toUtf8();
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
            QMessageBox::warning(this, "Save", file.errorString()); return false;
        }
        if (text!=code->toPlainText()) {
            auto cursor=code->textCursor(); int position=cursor.position(); cursor.beginEditBlock(); cursor.select(QTextCursor::Document); cursor.insertText(text); cursor.endEditBlock();
            cursor.setPosition(qMin(position,code->document()->characterCount()-1)); code->setTextCursor(cursor);
        }
        code->setProperty("path", path); code->document()->setModified(false); updateTitle(code); explorer->addFolder(QFileInfo(path).absolutePath()); updateExplorer(); return true;
    }
    /**
     * @brief 未保存の確認後にタブを閉じる。最後のタブを閉じたら空タブを作る。
     * @param index 0始まりのタブ番号。
     */
    void close(int index) {
        auto code=static_cast<Code*>(tabs->widget(index)); if (!code || !mayClose(code)) return;
        tabs->removeTab(index); delete code; if (!tabs->count()) newTab(); current()->setFocus(); updateExplorer();
    }
    /**
     * @brief 次または前のタブへ移動する。先頭と末尾で折り返す。
     * @param direction 次は1、前は-1。
     */
    void switchTab(int direction) { tabs->setCurrentIndex((tabs->currentIndex()+direction+tabs->count())%tabs->count()); current()->setFocus(); }
    /**
     * @brief 検索欄を開き、単一行の選択文字列を初期検索語にする。
     * @param withReplace trueなら置換欄も表示する。
     */
    void openFind(bool withReplace) {
        auto selection=current()->textCursor().selectedText();
        if (!selection.isEmpty() && !selection.contains(QChar(0x2029))) findText->setText(selection);
        findBar->show(); replacePanel->setVisible(withReplace); positionSearch(); findText->setFocus(); findText->selectAll();
    }
    /**
     * @brief 次または前の一致箇所を選択し、件数を表示する。
     * @param backward trueなら前方向。
     * @return 一致箇所へ移動できた場合true。
     */
    bool findNext(bool backward=false) {
        if (findText->text().isEmpty()) { openFind(false); return false; }
        QList<QPair<int,int>> matches; if (!searchMatches(matches)) return false;
        if (matches.isEmpty()) { searchCount->setText("No results"); statusBar()->showMessage("No matches",2000); return false; }
        auto cursor=current()->textCursor(); int index=backward ? matches.size()-1 : 0;
        if (backward) { for (int i=matches.size()-1;i>=0;--i) if (matches[i].first+matches[i].second<=cursor.selectionStart()) { index=i; break; } }
        else { for (int i=0;i<matches.size();++i) if (matches[i].first>=cursor.selectionEnd()) { index=i; break; } }
        cursor.setPosition(matches[index].first); cursor.setPosition(matches[index].first+matches[index].second,QTextCursor::KeepAnchor);
        current()->setTextCursor(cursor); current()->ensureCursorVisible();
        searchCount->setText(QString("%1 of %2").arg(index+1).arg(matches.size()));
        statusBar()->showMessage(QString("Match %1 of %2").arg(index+1).arg(matches.size()),2000); return true;
    }
    /** @brief 検索語を入力するたびに現在の一致を絞り込む。検索欄のフォーカスは移さない。 */
    void searchWhileTyping() {
        if (!current()) return;
        auto cursor=current()->textCursor();
        const int start=cursor.selectionStart();
        cursor.setPosition(start);
        if (findText->text().isEmpty()) {
            current()->setTextCursor(cursor); searchCount->clear(); return;
        }
        QList<QPair<int,int>> matches;
        if (!searchMatches(matches)) { current()->setTextCursor(cursor); searchCount->setText("Invalid"); return; }
        if (matches.isEmpty()) { current()->setTextCursor(cursor); searchCount->setText("No results"); return; }
        int index=0;
        // h→hl→hliと伸ばしても、選択末尾から次の一致へ飛ばないよう先頭を基準にする。
        for (int i=0;i<matches.size();++i) if (matches[i].first>=start) { index=i; break; }
        cursor.setPosition(matches[index].first);
        cursor.setPosition(matches[index].first+matches[index].second,QTextCursor::KeepAnchor);
        current()->setTextCursor(cursor); current()->ensureCursorVisible();
        searchCount->setText(QString("%1 of %2").arg(index+1).arg(matches.size()));
    }
    /**
     * @brief 元本文で一致範囲を確定し、一括置換中の再検索を避ける。
     * @param matches 一致位置と長さを書き込む出力先。
     * @param replacements 指定時は各一致に対応した置換結果も書き込む。
     * @return 不正な式・ゼロ長一致・件数上限でfalse。本文は変更しない。
     */
    bool searchMatches(QList<QPair<int,int>>& matches, QStringList* replacements=nullptr) {
        QString pattern=regexSearch->isChecked() ? findText->text() : QRegularExpression::escape(findText->text());
        if (wholeWord->isChecked()) pattern="(?<!\\w)(?:"+pattern+")(?!\\w)";
        auto flags=QRegularExpression::UseUnicodePropertiesOption | QRegularExpression::MultilineOption;
        if (!matchCase->isChecked()) flags|=QRegularExpression::CaseInsensitiveOption;
        QRegularExpression regex(pattern,flags);
        if (!regex.isValid()) { statusBar()->showMessage("Invalid expression: "+regex.errorString()); return false; }
        auto iterator=regex.globalMatch(current()->toPlainText());
        while (iterator.hasNext()) {
            auto match=iterator.next();
            if (!match.capturedLength()) { statusBar()->showMessage("Zero-length matches are not supported"); return false; }
            if (matches.size()>=100000) { statusBar()->showMessage("Too many matches (limit 100,000)"); return false; }
            matches.append({match.capturedStart(),match.capturedLength()});
            if (replacements) {
                // VS Codeで使う$1〜$99、$&、$$を展開。通常検索では文字をそのまま扱う。
                auto value=replacement->text(); QString expanded;
                for (int i=0;i<value.size();++i) {
                    if (!regexSearch->isChecked() || value[i]!='$' || i+1==value.size()) { expanded+=value[i]; continue; }
                    auto next=value[i+1];
                    if (next=='$') { expanded+='$'; ++i; }
                    else if (next=='&') { expanded+=match.captured(); ++i; }
                    else if (next>='1' && next<='9') {
                        int number=next.digitValue(); ++i;
                        if (i+1<value.size() && value[i+1].isDigit() && number*10+value[i+1].digitValue()<=regex.captureCount()) number=number*10+value[++i].digitValue();
                        if (number<=regex.captureCount()) expanded+=match.captured(number);
                        else expanded+='$'+QString::number(number);
                    } else expanded+='$';
                }
                replacements->append(expanded);
            }
        }
        return true;
    }
    /**
     * @brief 1件または全件を置換する。一括置換は末尾から処理し1Undoにまとめる。
     * @param all trueなら全件、falseなら現在選択している一致箇所。
     */
    void replace(bool all) {
        if (findText->text().isEmpty()) return;
        QList<QPair<int,int>> matches; QStringList values; if (!searchMatches(matches,&values)) return;
        if (!all) {
            auto c=current()->textCursor();
            if (matches.contains({c.selectionStart(),c.selectionEnd()-c.selectionStart()})) {
                int index=matches.indexOf({c.selectionStart(),c.selectionEnd()-c.selectionStart()});
                c.beginEditBlock(); c.insertText(values[index]); c.endEditBlock(); current()->setTextCursor(c);
            }
            findNext(); return;
        }
        QTextCursor group(current()->document()); group.beginEditBlock();
        QTextCursor c(current()->document());
        for (int i=matches.size()-1;i>=0;--i) {
            c.setPosition(matches[i].first); c.setPosition(matches[i].first+matches[i].second,QTextCursor::KeepAnchor);
            c.insertText(values[i]);
        }
        group.endEditBlock(); statusBar()->showMessage(QString("Replaced %1 matches").arg(matches.size()),2000);
    }
    /**
     * @brief 未保存のタブを閉じてよいか確認する。
     * @param code 確認対象。
     * @return 破棄または保存成功でtrue。キャンセルならfalse。
     */
    bool mayClose(Code* code) {
        if (!code->document()->isModified()) return true;
        auto choice = QMessageBox::question(this, "Unsaved script", "Save changes before closing?", QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel);
        return choice == QMessageBox::Discard || (choice == QMessageBox::Save && save(code));
    }
    /**
     * @brief 自動復元保存を試み、失敗した場合だけ未保存確認を行う。
     * @param event accept/ignoreで閉じる処理を許可または中止する。
     */
    void closeEvent(QCloseEvent* event) override {
        if (saveSession()) { event->accept(); return; }
        for (int i=0; i<tabs->count(); ++i) if (!mayClose(static_cast<Code*>(tabs->widget(i)))) { event->ignore(); return; }
        event->accept(); // Mayaセッション内ではウィンドウ/タブを保持する。
    }
    /** @brief 検索をコード欄の右上へ重ね、ドッキング後の幅にも追従させる。 */
    void positionSearch() {
        if (findBar->isHidden()) return;
        findBar->layout()->activate();
        findBar->resize(qMin(470,qMax(0,tabs->width()-12)),findBar->sizeHint().height());
        findBar->move(qMax(0,tabs->width()-findBar->width()-6),tabs->tabBar()->height()+4);
        findBar->raise();
    }
    /** @brief タブ領域のリサイズ時に検索パネルの位置だけ更新する。 */
    bool eventFilter(QObject* watched,QEvent* event) override {
        if (watched==tabs && event->type()==QEvent::Resize) positionSearch();
        return QMainWindow::eventFilter(watched,event);
    }
    /** @brief 長いMaya処理中も最大約40fpsで描画する。再入やUIイベントの処理を避ける。 */
    void refreshOutputNow() {
        if (refreshingOutput || (directOutputClock.isValid() && directOutputClock.elapsed()<25)) return;
        refreshingOutput=true; directOutputClock.restart();
        flushOutput();
        if (output->isVisible()) output->viewport()->repaint();
        refreshingOutput=false;
    }
    /** @brief 待機中のMayaログを一度だけ取得し、保持と描画へ渡す。 */
    void flushOutput() {
        if (!outputReader) return;
        auto messages = outputReader();
        if (messages.isEmpty()) return;
        // モードを戻せるよう表示前のログを保持する。ただし1Mi文字を超えて蓄積しない。
        for (auto message: messages) {
            message.text=message.text.right(1024*1024);
            outputHistorySize+=message.text.size(); outputHistory.append(message);
        }
        while (outputHistorySize>1024*1024 && !outputHistory.isEmpty()) {
            outputHistorySize-=outputHistory.first().text.size(); outputHistory.removeFirst();
        }
        appendOutput(messages);
    }
    /** @brief 現在の表示モードでログを描画する。元ログは変更しない。 */
    void appendOutput(const QList<OutputMessage>& messages) {
        auto vertical=output->verticalScrollBar(); auto horizontal=output->horizontalScrollBar();
        int oldVertical=vertical->value(), oldHorizontal=horizontal->value();
        bool follow=oldVertical>=vertical->maximum() && !output->textCursor().hasSelection();
        bool selected=output->textCursor().hasSelection();
        QTextCursor anchor(output->document()), caret(output->document());
        anchor.setPosition(output->textCursor().anchor()); caret.setPosition(output->textCursor().position());
        anchor.setKeepPositionOnInsert(true); caret.setKeepPositionOnInsert(true);
        // 表示用のカーソルとは別のカーソルで追記し、ユーザーの選択を保持する。
        QTextCursor cursor(output->document()); cursor.movePosition(QTextCursor::End);
        for (const auto& message: messages) {
            const int mode=outputMode->currentIndex();
            if (mode==1 && message.kind==OutputKind::History) continue;
            if (mode==2 && message.kind!=OutputKind::Warning && message.kind!=OutputKind::Error) continue;
            if (mode==3 && message.kind!=OutputKind::Error) continue;
            QColor color("#d4d4d4");
            switch (message.kind) {
            case OutputKind::Warning: color=QColor("#ffff00"); break;
            case OutputKind::Error: color=QColor("#ff0000"); break;
            case OutputKind::Result: color=QColor("#b5cea8"); break;
            case OutputKind::Info: color=QColor("#9cdcfe"); break;
            case OutputKind::History: color=QColor("#a0a0a0"); break;
            default: break;
            }
            QTextCharFormat format; format.setForeground(color); cursor.insertText(message.text,format);
        }
        QTextCharFormat normal; normal.setForeground(QColor("#d4d4d4")); cursor.setCharFormat(normal);
        if (selected) { auto selection=anchor; selection.setPosition(caret.position(),QTextCursor::KeepAnchor); output->setTextCursor(selection); }
        vertical->setValue(follow ? vertical->maximum() : oldVertical);
        horizontal->setValue(oldHorizontal);
    }
    /**
     * @brief 選択範囲または全体を、現在の言語でMayaへ渡す。
     * @param all trueなら全体。falseでも選択がなければ全体。
     */
    void runCode(bool all) {
        QString source = current()->toPlainText();
        if (!all && current()->textCursor().hasSelection()) source = current()->textCursor().selectedText().replace(QChar(0x2029), '\n');
        QString result = current()->isMel() ? (executeMel ? executeMel(source) : "MEL execution is unavailable") : execute(source);
        if (!result.isEmpty()) output->appendPlainText(result);
        flushOutput();
    }
    /**
     * @brief heditの待機中ログと表示だけを消す。他エディタは変更しない。
     */
    void clearOutput() {
        if (outputReader) outputReader(); // 直前の未描画ログも消去する。
        outputHistory.clear(); outputHistorySize=0;
        output->clear();
    }
    /**
     * @brief Maya内の補完環境を更新する。別プロセスは起動しない。
     */
    void refreshCompletion() {
        configuration();
        completionStatus->setText("Completion: ready (in Maya)");
    }
    /**
     * @brief アクティブなPythonタブで現在位置までの補完候補を問い合わせる。
     * @param force Ctrl+Spaceからの呼出ならtrue。自動補完設定を無視できる。
     */
    void request(bool force = true) {
        if (!complete || !current()->hasFocus() || current()->isMel()) return;
        auto cursor = current()->textCursor();
        // 末尾1文字を見るために毎回ドキュメント全体をコピーしない。
        auto preceding = cursor; preceding.movePosition(QTextCursor::PreviousCharacter, QTextCursor::KeepAnchor);
        const bool dot=preceding.selectedText()==".";
        if (!force) {
            if (dot ? !option("completeDot") : !option("completeLetters")) return;
        }
        if (!force && current()->prefix().isEmpty() && !dot) return;
        if (cursor.position()>200000) { completionStatus->setText("Completion: document limit (200k)"); return; }
        cursor.setPosition(0, QTextCursor::KeepAnchor);
        auto response = QJsonDocument::fromJson(complete(cursor.selectedText().replace(QChar(0x2029), '\n'))).object();
        if (response.contains("error")) { completionStatus->setText("Completion: " + response["error"].toString()); return; }
        auto completer = current()->completer;
        auto model = static_cast<QStandardItemModel*>(completer->model());
        model->clear();
        for (const auto& value : response["items"].toArray()) {
            auto kind=value.toObject()["kind"].toString();
            if ((kind=="keyword" && !option("includeKeywords")) || (kind=="builtin" && !option("includeBuiltins"))) continue;
            auto item = new QStandardItem(value.toObject()["name"].toString());
            item->setToolTip(value.toObject()["detail"].toString()); model->appendRow(item);
        }
        completionStatus->setText("Completion: ready (in Maya)");
        if (!model->rowCount()) {
            completer->popup()->hide();
            // 初回の非同期import走査が完了したら、追加入力なしでも候補を取得する。
            if (response["pending"].toBool()) debounce.start(250);
            return;
        }
        completer->setCompletionPrefix(current()->prefix());
        completer->popup()->setCurrentIndex(completer->completionModel()->index(0, 0));
        auto rect = current()->cursorRect(); rect.setWidth(380); completer->complete(rect);
    }
};

QMainWindow* createEditor(QWidget* parent, Execute execute, Configuration configuration, OutputReader outputReader, Completion completion, QString sessionPath, Completion analyzer, Execute melExecute) {
    return new Window(parent, execute, configuration, outputReader, completion, sessionPath, analyzer, melExecute);
}
void refreshEditorOutput(QMainWindow* editor) {
    if (editor) static_cast<Window*>(editor)->refreshOutputNow();
}
}
