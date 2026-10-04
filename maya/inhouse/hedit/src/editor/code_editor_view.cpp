/** @file code_editor_view.cpp
 * @brief CodeEditorのうち、表示の部分(同じ名前と括弧の強調・問題の波線・保存前との差分の印・折りたたみ・
 * 見出しの固定表示・インデントの縦線・スクロールバーの印)。
 * @details 折りたたみはQTextBlock::setVisible(false)で行を隠す(QPlainTextEditのレイアウトが隠した行を詰める)。
 * 畳んだ見出しはQTextCursorで覚えるので、上の行を編集しても見出しの位置に追従する。
 */
#include "editor/code_editor.h"
#include "editor/code_navigation.h"
#include "editor/hover_popup.h"
#include "editor/marker_scroll_bar.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QCompleter>
#include <QHash>
#include <QItemSelectionModel>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRegularExpression>
#include <QScrollBar>
#include <QTextBlock>
#include <QTextLayout>
#include <algorithm>

namespace hedit {

namespace {

/// 見出しの固定表示に出す最大の行数。
constexpr int kMaximumStickyLines = 5;

/// 同じ名前を強調する最大の件数。
constexpr int kMaximumWordHighlights = 1000;

/// スクロールバーの印の種類ごとの最大の件数。
constexpr int kMaximumMarkers = 2000;

/** @brief 問題の波線の範囲(行の中の先頭と終わり)を求める。
 * @param block 行。
 * @param diagnostic 問題。
 * @param start 先頭(行の中の位置)を入れる。
 * @param end 終わりを入れる。
 */
void diagnosticRange(const QTextBlock& block, const Diagnostic& diagnostic, int* start, int* end) {
    const QString text = block.text();
    if (diagnostic.column > 0) {
        *start = qMin(diagnostic.column - 1, int(text.size()));
        *end = diagnostic.length > 0 ? qMin(*start + diagnostic.length, int(text.size())) : int(text.size());
    } else {
        *start = 0;
        while (*start < text.size() && text[*start].isSpace()) {
            ++*start;
        }
        *end = text.size();
    }
    if (*end <= *start) {
        // 行末の位置(閉じ括弧の不足など)は、直前の1文字に引く。
        if (*start > 0) {
            --*start;
        } else {
            *end = qMin(*start + 1, int(text.size()));
        }
    }
}

}  // namespace

/** @brief 見出しの固定表示(表示部分の上端に重ねる部品)。描画とクリックはCodeEditorに任せる。 */
class StickyHeader : public QWidget {
public:
    /** @brief 部品を作る。作成直後は非表示。 @param editor 持ち主のコード欄(表示部分が親になる)。 */
    explicit StickyHeader(CodeEditor* editor) : QWidget(editor->viewport()), editor_(editor) {
        setObjectName("stickyScroll");
        setCursor(Qt::PointingHandCursor);
        hide();
    }

protected:
    /** @brief 見出しを描く。 @param event 描き直す範囲。 */
    void paintEvent(QPaintEvent* event) override {
        Q_UNUSED(event);
        QPainter painter(this);
        editor_->paintSticky(painter);
    }

    /** @brief クリックした見出しの行へ移る。 @param event マウスの操作。 */
    void mousePressEvent(QMouseEvent* event) override { editor_->stickyClicked(event->pos().y()); }

private:
    CodeEditor* editor_;  ///< 持ち主のコード欄。
};

void CodeEditor::setUpView() {
    // 印を描くスクロールバーに置き換える(コード欄が所有する)。
    markers_ = new MarkerScrollBar(this);
    setVerticalScrollBar(markers_);
    sticky_ = new StickyHeader(this);

    wordTimer_.setSingleShot(true);
    wordTimer_.setInterval(150);
    connect(&wordTimer_, &QTimer::timeout, this, [this] { updateWordHighlights(); });
    diffTimer_.setSingleShot(true);
    diffTimer_.setInterval(300);
    connect(&diffTimer_, &QTimer::timeout, this, [this] { updateLineChanges(); });
    markerTimer_.setSingleShot(true);
    markerTimer_.setInterval(100);
    connect(&markerTimer_, &QTimer::timeout, this, [this] { updateScrollMarkers(); });

    updateGutter();  // 折りたたみの矢印の欄の幅を足す(基底クラスの作成中は、この欄の幅を知らない)。
    connect(document(), &QTextDocument::contentsChanged, this, [this] { onContentsChanged(); });
    connect(verticalScrollBar(), &QScrollBar::valueChanged, this, [this] { updateSticky(); });
    // 補完の一覧: 選んでいる候補が変わったら説明を出し直し、一覧が閉じたら説明も閉じる。
    completer_->popup()->installEventFilter(this);
    connect(completer_->popup()->selectionModel(), &QItemSelectionModel::currentChanged, this, [this] {
        if (onCompletionSelectionChanged && completer_->popup()->isVisible()) {
            onCompletionSelectionChanged();
        }
    });
}

CodeEditor::~CodeEditor() {
    // 子の部品(スクロールバー・補完の一覧・文書)は基底クラスの破棄の中で消える。その途中のシグナルが、
    // 既に破棄したこのクラスのメンバー(タイマー・一覧など)を使わないよう、先に接続を外す。
    wordTimer_.stop();
    diffTimer_.stop();
    markerTimer_.stop();
    QObject::disconnect(document(), nullptr, this, nullptr);
    QObject::disconnect(verticalScrollBar(), nullptr, this, nullptr);
    QObject::disconnect(horizontalScrollBar(), nullptr, this, nullptr);
    QObject::disconnect(this, nullptr, this, nullptr);
    if (completer_->popup()) {
        completer_->popup()->removeEventFilter(this);
        QObject::disconnect(completer_->popup()->selectionModel(), nullptr, this, nullptr);
    }
}

void CodeEditor::onCursorMoved() {
    const QTextCursor cursor = textCursor();
    revealCursor();
    lastCursorBlock_ = textCursor().blockNumber();
    if (!expanding_ && (cursor.selectionStart() != lastExpanded_.first || cursor.selectionEnd() != lastExpanded_.second)) {
        selectionStack_.clear();  // 選択範囲の拡大以外で選択が変わったら、戻る先を捨てる。
        lastExpanded_ = {-1, -1};
    }
    updateBracketMatch();
    wordTimer_.start();
    markerTimer_.start();
    if (isSignatureHelpVisible() && onSignatureHelpRequested) {
        onSignatureHelpRequested(false);
    }
}

// ===========================================================================
// 同じ名前・括弧
// ===========================================================================

void CodeEditor::updateWordHighlights() {
    wordMarks_.clear();
    wordPositions_.clear();
    const QTextCursor cursor = textCursor();
    QString name;
    static const QRegularExpression identifier("^\\$?[A-Za-z_]\\w*$");
    if (cursor.hasSelection()) {
        // 単語1つを選んでいるときだけ、同じ単語を強調する。
        const QString selected = cursor.selectedText();
        if (identifier.match(selected).hasMatch()) {
            name = selected;
        }
    } else {
        const QTextBlock block = cursor.block();
        const int column = cursor.positionInBlock();
        for (const Token& token : blockTokens(block, language_)) {
            if (column < token.start || column > token.start + token.length) {
                continue;
            }
            const QString text = block.text().mid(token.start, token.length);
            if ((token.type == TokenType::Name && !isKeyword(text, language_)) || token.type == TokenType::Variable) {
                name = text;
                break;
            }
        }
    }
    if (!name.isEmpty()) {
        wordPositions_ = nameOccurrences(document(), language_, name, kMaximumWordHighlights);
        for (const int position : wordPositions_) {
            QTextEdit::ExtraSelection mark;
            mark.cursor = QTextCursor(document());
            mark.cursor.setPosition(position);
            mark.cursor.setPosition(position + name.size(), QTextCursor::KeepAnchor);
            mark.format.setBackground(QColor(theme::kWordHighlight));
            wordMarks_.append(mark);
        }
    }
    updateDecorations();
    markerTimer_.start();
}

void CodeEditor::updateBracketMatch() {
    bracketMarks_.clear();
    bracketPositions_.clear();
    int first = 0;
    int second = 0;
    if (!textCursor().hasSelection()
        && findMatchingBracket(document(), language_, textCursor().position(), &first, &second)) {
        for (const int position : {first, second}) {
            QTextEdit::ExtraSelection mark;
            mark.cursor = QTextCursor(document());
            mark.cursor.setPosition(position);
            mark.cursor.setPosition(position + 1, QTextCursor::KeepAnchor);
            mark.format.setBackground(QColor(theme::kBracketMatch));
            mark.format.setUnderlineStyle(QTextCharFormat::SingleUnderline);
            mark.format.setUnderlineColor(QColor(theme::kBracketMatchBorder));
            bracketMarks_.append(mark);
            bracketPositions_.append(position);
        }
    }
}

// ===========================================================================
// 問題
// ===========================================================================

void CodeEditor::setDiagnostics(const QList<Diagnostic>& diagnostics) {
    diagnostics_ = diagnostics;
    diagnosticMarks_.clear();
    for (const Diagnostic& diagnostic : diagnostics_) {
        const QTextBlock block = document()->findBlockByNumber(diagnostic.line - 1);
        if (!block.isValid() || block.text().isEmpty()) {
            continue;
        }
        int start = 0;
        int end = 0;
        diagnosticRange(block, diagnostic, &start, &end);
        QTextEdit::ExtraSelection mark;
        mark.cursor = QTextCursor(document());
        mark.cursor.setPosition(block.position() + start);
        mark.cursor.setPosition(block.position() + end, QTextCursor::KeepAnchor);
        mark.format.setUnderlineStyle(QTextCharFormat::WaveUnderline);
        mark.format.setUnderlineColor(QColor(diagnostic.severity == "error" ? theme::kProblemError
                                                                             : theme::kProblemWarning));
        diagnosticMarks_.append(mark);
    }
    updateDecorations();
    markerTimer_.start();
}

QStringList CodeEditor::problemsAt(int position) const {
    QStringList problems;
    const QTextBlock block = document()->findBlock(position);
    for (const Diagnostic& diagnostic : diagnostics_) {
        if (diagnostic.line - 1 != block.blockNumber()) {
            continue;
        }
        int start = 0;
        int end = 0;
        diagnosticRange(block, diagnostic, &start, &end);
        const int column = position - block.position();
        if (column >= start && column <= end) {
            problems.append(diagnostic.message);
        }
    }
    return problems;
}

bool CodeEditor::goToProblem(int direction) {
    if (diagnostics_.isEmpty()) {
        return false;
    }
    QList<Diagnostic> sorted = diagnostics_;
    std::sort(sorted.begin(), sorted.end(), [](const Diagnostic& a, const Diagnostic& b) {
        return a.line != b.line ? a.line < b.line : a.column < b.column;
    });
    const QTextCursor cursor = textCursor();
    const int line = cursor.blockNumber() + 1;
    const int column = cursor.positionInBlock() + 1;
    auto key = [](const Diagnostic& d) { return qint64(d.line) * 100000 + qMax(1, d.column); };
    const qint64 here = qint64(line) * 100000 + column;
    int target = -1;
    if (direction > 0) {
        for (int i = 0; i < sorted.size() && target < 0; ++i) {
            if (key(sorted[i]) > here) {
                target = i;
            }
        }
        if (target < 0) {
            target = 0;
        }
    } else {
        for (int i = sorted.size() - 1; i >= 0 && target < 0; --i) {
            if (key(sorted[i]) < here) {
                target = i;
            }
        }
        if (target < 0) {
            target = sorted.size() - 1;
        }
    }
    const Diagnostic& diagnostic = sorted[target];
    const QTextBlock block = document()->findBlockByNumber(diagnostic.line - 1);
    if (!block.isValid()) {
        return false;
    }
    int start = 0;
    int end = 0;
    diagnosticRange(block, diagnostic, &start, &end);
    QTextCursor moved(document());
    moved.setPosition(block.position() + start);
    setTextCursor(moved);
    ensureCursorVisible();
    // 行の下に、その問題の説明を出す(VS Codeの F8 と同じく、一覧を見に行かなくてよい)。
    // ホバーの小窓と違い、マウスの位置では閉じない(キー入力・クリック・スクロールで閉じる)。
    if (!problemPopup_) {
        problemPopup_ = new HoverPopup(this);
        problemPopup_->setObjectName("problemPopup");
    }
    QTextCursor endCursor(document());
    endCursor.setPosition(block.position() + end);
    const QRect first = cursorRect(moved);
    const QRect last = cursorRect(endCursor);
    const QRect local(first.topLeft(), QPoint(qMax(first.right(), last.right()), first.bottom()));
    const QString position = QString("Line %1 (%2 of %3)").arg(diagnostic.line).arg(target + 1).arg(sorted.size());
    problemPopup_->showHtml(HoverPopup::problemsHtml({diagnostic.message, position}),
                     QRect(viewport()->mapToGlobal(local.topLeft()), local.size()), font(),
                     HoverPopup::Placement::Below);
    return true;
}

// ===========================================================================
// 保存前との差分
// ===========================================================================

void CodeEditor::setSavedText(const QString& text) {
    savedText_ = text;
    savedText_.replace("\r\n", "\n");
    hasSavedText_ = true;
    updateLineChanges();
}

void CodeEditor::clearSavedText() {
    savedText_.clear();
    hasSavedText_ = false;
    lineChanges_.clear();
    changeKinds_.clear();
    deletedAbove_.clear();
    gutter()->update();
    markerTimer_.start();
}

void CodeEditor::updateLineChanges() {
    diffTimer_.stop();
    if (!hasSavedText_) {
        return;
    }
    lineChanges_ = diffLines(savedText_.split('\n'), toPlainText().split('\n'));
    const int count = blockCount();
    changeKinds_.fill(0, count);
    deletedAbove_.fill(0, count + 1);
    for (const LineChange& change : lineChanges_) {
        if (change.afterCount == 0) {
            deletedAbove_[qBound(0, change.afterStart, count)] = 1;
            continue;
        }
        for (int line = change.afterStart; line < change.afterStart + change.afterCount && line < count; ++line) {
            changeKinds_[line] = change.beforeCount == 0 ? 1 : 2;
        }
    }
    gutter()->update();
    markerTimer_.start();
}

// ===========================================================================
// 構成と折りたたみ
// ===========================================================================

const QList<OutlineEntry>& CodeEditor::outline() const {
    if (outlineRevision_ != document()->revision()) {
        outline_ = buildOutline(toPlainText(), language_);
        outlineRevision_ = document()->revision();
    }
    return outline_;
}

const QList<FoldRange>& CodeEditor::foldRanges() const {
    if (foldRevision_ != document()->revision()) {
        foldRanges_ = indentationFoldRanges(toPlainText().split('\n'));
        foldRevision_ = document()->revision();
    }
    return foldRanges_;
}

bool CodeEditor::isFolded(int line) const {
    for (const QTextCursor& header : foldedHeaders_) {
        if (header.blockNumber() == line) {
            return true;
        }
    }
    return false;
}

bool CodeEditor::foldAt(int line) {
    for (const FoldRange& range : foldRanges()) {
        if (range.start != line) {
            continue;
        }
        if (!isFolded(line)) {
            // カーソルが隠れる行にあれば、見出しの行末へ移す(隠れた行で入力しないように)。
            const int cursorLine = textCursor().blockNumber();
            const QTextBlock header = document()->findBlockByNumber(line);
            if (cursorLine > range.start && cursorLine <= range.end) {
                QTextCursor cursor(header);
                cursor.movePosition(QTextCursor::EndOfBlock);
                setTextCursor(cursor);
            }
            foldedHeaders_.append(QTextCursor(header));
            applyFolds();
        }
        return true;
    }
    return false;
}

bool CodeEditor::unfoldAt(int line) {
    const int before = foldedHeaders_.size();
    for (int i = foldedHeaders_.size() - 1; i >= 0; --i) {
        if (foldedHeaders_[i].blockNumber() == line) {
            foldedHeaders_.removeAt(i);
        }
    }
    if (foldedHeaders_.size() == before) {
        return false;
    }
    applyFolds();
    return true;
}

void CodeEditor::foldAtCursor() {
    const int line = textCursor().blockNumber();
    int best = -1;
    for (const FoldRange& range : foldRanges()) {
        if (range.start <= line && range.end >= line && range.start > best && !isFolded(range.start)) {
            best = range.start;
        }
    }
    if (best >= 0) {
        foldAt(best);
    }
}

void CodeEditor::unfoldAtCursor() {
    unfoldAt(textCursor().blockNumber());
}

void CodeEditor::foldAll() {
    const int cursorLine = textCursor().blockNumber();
    int outermost = -1;
    for (const FoldRange& range : foldRanges()) {
        if (!isFolded(range.start)) {
            foldedHeaders_.append(QTextCursor(document()->findBlockByNumber(range.start)));
        }
        if (range.start < cursorLine && range.end >= cursorLine && (outermost < 0 || range.start < outermost)) {
            outermost = range.start;
        }
    }
    if (outermost >= 0) {
        QTextCursor cursor(document()->findBlockByNumber(outermost));
        cursor.movePosition(QTextCursor::EndOfBlock);
        setTextCursor(cursor);
    }
    applyFolds();
}

void CodeEditor::unfoldAll() {
    if (foldedHeaders_.isEmpty()) {
        return;
    }
    foldedHeaders_.clear();
    applyFolds();
}

void CodeEditor::applyFolds() {
    QHash<int, int> ends;  // 見出しの行 → 畳む最後の行。
    for (const FoldRange& range : foldRanges()) {
        ends.insert(range.start, range.end);
    }
    const int count = blockCount();
    QVector<char> hidden(count, 0);
    QList<QTextCursor> kept;
    QList<int> keptLines;
    for (const QTextCursor& header : foldedHeaders_) {
        const int line = header.blockNumber();
        if (!ends.contains(line) || keptLines.contains(line)) {
            continue;  // もう畳めない(中身が無くなった)見出しは捨てる。
        }
        kept.append(header);
        keptLines.append(line);
        for (int i = line + 1; i <= ends.value(line) && i < count; ++i) {
            hidden[i] = 1;
        }
    }
    foldedHeaders_ = kept;
    int changedFrom = -1;
    int changedTo = -1;
    QTextBlock block = document()->begin();
    for (int i = 0; block.isValid(); ++i, block = block.next()) {
        const bool visible = i >= count || !hidden[i];
        if (block.isVisible() != visible) {
            block.setVisible(visible);
            if (changedFrom < 0) {
                changedFrom = block.position();
            }
            changedTo = block.position() + block.length();
        }
    }
    if (changedFrom >= 0) {
        // 隠した行の高さを0にして並べ直す。
        document()->markContentsDirty(changedFrom, changedTo - changedFrom);
        viewport()->update();
        gutter()->update();
    }
    updateSticky();
    markerTimer_.start();
}

void CodeEditor::revealCursor() {
    QTextBlock block = textCursor().block();
    if (block.isVisible() || foldedHeaders_.isEmpty()) {
        return;
    }
    // 畳んだ見出しのうち、カーソルの行を隠しているもの。
    const int line = block.blockNumber();
    int header = -1;
    int headerEnd = -1;
    for (const FoldRange& range : foldRanges()) {
        if (range.start < line && range.end >= line && isFolded(range.start) && range.start > header) {
            header = range.start;
            headerEnd = range.end;
        }
    }
    if (header < 0) {
        applyFolds();
        return;
    }
    // 矢印キーで見出しの行から下へ(範囲の下の行から上へ)動いたなら、畳んだまま飛び越える。
    if (!textCursor().hasSelection() && (lastCursorBlock_ == header || lastCursorBlock_ == headerEnd + 1)) {
        const bool down = lastCursorBlock_ == header;
        const QTextBlock target = document()->findBlockByNumber(down ? headerEnd + 1 : header);
        if (target.isValid()) {
            const int column = qMin(textCursor().positionInBlock(), target.length() - 1);
            QTextCursor cursor(target);
            cursor.setPosition(target.position() + column);
            setTextCursor(cursor);
            return;
        }
    }
    // それ以外(検索・行へ移動など)は、隠れていた範囲を開く。
    for (int i = foldedHeaders_.size() - 1; i >= 0; --i) {
        const int start = foldedHeaders_[i].blockNumber();
        for (const FoldRange& range : foldRanges()) {
            if (range.start == start && range.start < line && range.end >= line) {
                foldedHeaders_.removeAt(i);
                break;
            }
        }
    }
    applyFolds();
}

void CodeEditor::onContentsChanged() {
    if (!foldedHeaders_.isEmpty()) {
        applyFolds();
    }
    if (hasSavedText_) {
        diffTimer_.start();
    }
    updateSticky();
    markerTimer_.start();
}

// ===========================================================================
// 見出しの固定表示
// ===========================================================================

void CodeEditor::setStickyScroll(bool enabled) {
    stickyScroll_ = enabled;
    updateSticky();
}

int CodeEditor::stickyLineHeight() const {
    const QTextBlock block = firstVisibleBlock();
    if (block.isValid() && block.layout() && block.layout()->lineCount() > 0) {
        return qMax(1, qRound(block.layout()->lineAt(0).height()));
    }
    return fontMetrics().height();
}

void CodeEditor::updateSticky() {
    if (!sticky_) {
        return;  // 作成の途中(setUpViewより前)。
    }
    QList<int> lines;
    const QTextBlock first = firstVisibleBlock();
    if (stickyScroll_ && first.isValid() && first.blockNumber() > 0) {
        const QList<OutlineEntry>& entries = outline();
        // 固定表示の行の数だけ下の行を基準に、それを含むクラス・関数を外側から並べる(行の数が決まるまで繰り返す)。
        for (int iteration = 0; iteration < kMaximumStickyLines + 1; ++iteration) {
            QTextBlock below = first;
            for (int row = 0; row < lines.size() && below.next().isValid(); ++row) {
                below = below.next();
                while (below.isValid() && !below.isVisible() && below.next().isValid()) {
                    below = below.next();
                }
            }
            const int line = below.blockNumber();
            QList<int> chain;
            for (const OutlineEntry& entry : entries) {
                if (entry.kind != "variable" && entry.line < line && entry.endLine >= line) {
                    chain.append(entry.line);
                }
            }
            std::sort(chain.begin(), chain.end());
            while (chain.size() > kMaximumStickyLines) {
                chain.removeFirst();
            }
            if (chain == lines) {
                break;
            }
            lines = chain;
        }
    }
    const bool changed = lines != stickyLines_;
    stickyLines_ = lines;
    if (stickyLines_.isEmpty()) {
        sticky_->hide();
    } else {
        sticky_->setGeometry(0, 0, viewport()->width(), stickyLineHeight() * stickyLines_.size() + scaled(2));
        sticky_->show();
        sticky_->raise();
        sticky_->update();
    }
    if (changed) {
        gutter()->update();
    }
}

void CodeEditor::paintSticky(QPainter& painter) {
    const int height = stickyLineHeight();
    painter.fillRect(sticky_->rect(), QColor(theme::kBackground));
    const qreal x = contentOffset().x() + document()->documentMargin();
    painter.setPen(QColor(theme::kText));
    for (int row = 0; row < stickyLines_.size(); ++row) {
        const QTextBlock block = document()->findBlockByNumber(stickyLines_[row]);
        if (!block.isValid() || !block.layout()) {
            continue;
        }
        // 画面の外の行はレイアウトされていない(QPlainTextEditは見える行だけ並べる)ので、構文強調の色
        // (行のレイアウトのformats)を写した一時的なレイアウトで1行を描く。
        QTextLayout layout(block.text(), font());
        QTextOption option = document()->defaultTextOption();
        option.setWrapMode(QTextOption::NoWrap);
        option.setTabStopDistance(tabStopDistance());
        layout.setTextOption(option);
        layout.setFormats(block.layout()->formats());
        layout.beginLayout();
        QTextLine line = layout.createLine();
        if (line.isValid()) {
            line.setLineWidth(1000000);
        }
        layout.endLayout();
        painter.save();
        painter.setClipRect(QRect(0, row * height, sticky_->width(), height));
        layout.draw(&painter, QPointF(x, row * height));
        painter.restore();
    }
    // 下の影(本文と見分けるため)。
    const int bottom = stickyLines_.size() * height;
    QColor shadow(theme::kStickyShadow);
    for (int i = 0; i < scaled(2); ++i) {
        shadow.setAlpha(120 - i * 50);
        painter.setPen(shadow);
        painter.drawLine(0, bottom + i, sticky_->width(), bottom + i);
    }
}

void CodeEditor::stickyClicked(int y) {
    const int row = y / qMax(1, stickyLineHeight());
    if (row < 0 || row >= stickyLines_.size()) {
        return;
    }
    QTextCursor cursor(document()->findBlockByNumber(stickyLines_[row]));
    setTextCursor(cursor);
    centerCursor();
    setFocus(Qt::MouseFocusReason);
}

void CodeEditor::paintGutterOverlay(QPainter& painter, const QRect& rect) {
    Q_UNUSED(rect);
    if (stickyLines_.isEmpty()) {
        return;
    }
    const int height = stickyLineHeight();
    painter.fillRect(QRect(0, 0, gutterWidth(), height * stickyLines_.size() + scaled(2)), QColor(theme::kBackground));
    painter.setPen(QColor(theme::kLineNumber));
    for (int row = 0; row < stickyLines_.size(); ++row) {
        const QRectF numberArea(0, row * height, numberWidth() - scaled(10), height);
        painter.drawText(numberArea, Qt::AlignRight, QString::number(stickyLines_[row] + 1));
    }
}

// ===========================================================================
// 行番号の欄(変更の印・折りたたみの矢印)
// ===========================================================================

int CodeEditor::extraGutterWidth() const {
    return scaled(16);
}

void CodeEditor::paintGutterBlock(QPainter& painter, const QTextBlock& block, const QRectF& rect) {
    const int line = block.blockNumber();
    const qreal barX = numberWidth() - scaled(6);
    if (line < changeKinds_.size() && changeKinds_[line] != 0) {
        painter.fillRect(QRectF(barX, rect.top(), scaled(3), rect.height()),
                         QColor(changeKinds_[line] == 1 ? theme::kChangeAdded : theme::kChangeModified));
    }
    if (line < deletedAbove_.size() && deletedAbove_[line] != 0) {
        // 削除: 行の上端に小さな三角形。
        QPainterPath triangle;
        const qreal size = scaled(4);
        triangle.moveTo(barX, rect.top() - size);
        triangle.lineTo(barX + size, rect.top());
        triangle.lineTo(barX, rect.top() + size);
        triangle.closeSubpath();
        painter.fillPath(triangle, QColor(theme::kChangeDeleted));
    }
    // 折りたたみの矢印(畳める見出しの行だけ)。
    bool foldable = false;
    for (const FoldRange& range : foldRanges()) {
        if (range.start == line) {
            foldable = true;
            break;
        }
        if (range.start > line) {
            break;
        }
    }
    if (!foldable) {
        return;
    }
    const bool folded = isFolded(line);
    const qreal size = scaled(4);
    const QPointF center(numberWidth() + extraGutterWidth() / 2.0, rect.top() + fontMetrics().height() / 2.0);
    QPainterPath arrow;
    if (folded) {
        arrow.moveTo(center.x() - size / 2, center.y() - size);
        arrow.lineTo(center.x() + size / 2 + 1, center.y());
        arrow.lineTo(center.x() - size / 2, center.y() + size);
    } else {
        arrow.moveTo(center.x() - size, center.y() - size / 2);
        arrow.lineTo(center.x(), center.y() + size / 2 + 1);
        arrow.lineTo(center.x() + size, center.y() - size / 2);
    }
    QColor color(theme::kFoldMarker);
    color.setAlpha(folded ? 255 : 110);
    painter.save();
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(QPen(color, qMax(1.0, scaled(1) * 1.4)));
    painter.drawPath(arrow);
    painter.restore();
}

void CodeEditor::gutterPressed(const QPoint& position) {
    const int stickyHeight = stickyLines_.isEmpty() ? 0 : stickyLineHeight() * stickyLines_.size();
    if (position.y() < stickyHeight) {
        stickyClicked(position.y());
        return;
    }
    if (position.x() < numberWidth()) {
        return;
    }
    for (QTextBlock block = firstVisibleBlock(); block.isValid(); block = block.next()) {
        if (!block.isVisible()) {
            continue;
        }
        const QRectF rect = blockBoundingGeometry(block).translated(contentOffset());
        if (rect.top() > position.y()) {
            break;
        }
        if (position.y() <= rect.bottom()) {
            const int line = block.blockNumber();
            if (!unfoldAt(line)) {
                foldAt(line);
            }
            return;
        }
    }
}

// ===========================================================================
// 描画(インデントの縦線・畳んだ見出しの「⋯」)
// ===========================================================================

void CodeEditor::paintEvent(QPaintEvent* event) {
    NumberedTextEdit::paintEvent(event);
    QPainter painter(viewport());
    const qreal spaceWidth = fontMetrics().horizontalAdvance(' ');
    const qreal left = contentOffset().x() + document()->documentMargin();
    const int viewportHeight = viewport()->height();

    // カーソルのあるブロック(カーソル行と同じかより深いインデントが続く範囲)の縦線を明るくする。
    const QTextBlock cursorBlock = textCursor().block();
    auto blank = [](const QTextBlock& block) { return block.text().trimmed().isEmpty(); };
    QTextBlock reference = cursorBlock;
    for (int i = 0; i < 200 && reference.isValid() && blank(reference); ++i) {
        reference = reference.next();
    }
    const int cursorIndent = reference.isValid() && !blank(reference) ? lineIndentWidth(reference.text()) : 0;
    const int activeLevel = cursorIndent / 4 - 1;
    int activeTop = cursorBlock.blockNumber();
    int activeBottom = activeTop;
    if (activeLevel >= 0) {
        for (QTextBlock b = cursorBlock.previous(); b.isValid(); b = b.previous()) {
            if (!blank(b) && lineIndentWidth(b.text()) < cursorIndent) {
                break;
            }
            activeTop = b.blockNumber();
        }
        for (QTextBlock b = cursorBlock.next(); b.isValid(); b = b.next()) {
            if (!blank(b) && lineIndentWidth(b.text()) < cursorIndent) {
                break;
            }
            activeBottom = b.blockNumber();
        }
    }

    // 空行の縦線は、前後の空でない行のうち浅い方のインデントに合わせる。
    int previousIndent = 0;
    for (QTextBlock b = firstVisibleBlock().previous(); b.isValid(); b = b.previous()) {
        if (!blank(b)) {
            previousIndent = lineIndentWidth(b.text());
            break;
        }
    }
    for (QTextBlock block = firstVisibleBlock(); block.isValid(); block = block.next()) {
        if (!block.isVisible()) {
            continue;
        }
        const QRectF rect = blockBoundingGeometry(block).translated(contentOffset());
        if (rect.top() > viewportHeight) {
            break;
        }
        int indent = 0;
        if (blank(block)) {
            int nextIndent = 0;
            QTextBlock next = block.next();
            for (int i = 0; i < 200 && next.isValid(); ++i, next = next.next()) {
                if (!blank(next)) {
                    nextIndent = lineIndentWidth(next.text());
                    break;
                }
            }
            indent = qMin(previousIndent, nextIndent);
        } else {
            indent = lineIndentWidth(block.text());
            previousIndent = indent;
        }
        const int line = block.blockNumber();
        for (int level = 0; level < indent / 4; ++level) {
            const qreal x = qRound(left + level * 4 * spaceWidth) + 0.5;
            const bool active = level == activeLevel && line >= activeTop && line <= activeBottom;
            painter.setPen(QColor(active ? theme::kIndentGuideActive : theme::kIndentGuide));
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()));
        }
        // 畳んだ見出しの後ろに「⋯」を描く。
        if (isFolded(line) && block.layout() && block.layout()->lineCount() > 0) {
            const qreal textEnd = left + block.layout()->lineAt(0).naturalTextWidth() + spaceWidth;
            const QRectF box(textEnd, rect.top() + scaled(2), spaceWidth * 3, fontMetrics().height() - scaled(4));
            painter.fillRect(box, QColor(theme::kFoldedBackground));
            painter.setPen(QColor(theme::kLineNumber));
            painter.drawText(box, Qt::AlignCenter, QString(QChar(0x22EF)));
        }
    }
}

void CodeEditor::resizeEvent(QResizeEvent* event) {
    NumberedTextEdit::resizeEvent(event);
    updateSticky();
}

bool CodeEditor::eventFilter(QObject* watched, QEvent* event) {
    // QAbstractScrollAreaは表示部分とスクロールバーのイベントフィルターでもあるので、作成の途中にも呼ばれる。
    if (completer_ && watched == completer_->popup() && event->type() == QEvent::Hide) {
        hideCompletionDetail();
    }
    return NumberedTextEdit::eventFilter(watched, event);
}

// ===========================================================================
// スクロールバーの印
// ===========================================================================

void CodeEditor::updateScrollMarkers() {
    markerTimer_.stop();
    if (!markers_) {
        return;
    }
    QList<MarkerScrollBar::Marker> markers;
    for (const LineChange& change : lineChanges_) {
        const QColor color(change.kind() == "added" ? theme::kChangeAdded
                           : change.kind() == "deleted" ? theme::kChangeDeleted : theme::kChangeModified);
        for (int i = 0; i < qMax(1, change.afterCount) && markers.size() < kMaximumMarkers; ++i) {
            markers.append({change.afterStart + i, color, 0});
        }
    }
    int count = 0;
    for (const QTextEdit::ExtraSelection& mark : searchMarks_) {
        if (++count > kMaximumMarkers) {
            break;
        }
        markers.append({mark.cursor.blockNumber(), QColor(theme::kScrollMarkerSearch), 1});
    }
    count = 0;
    for (const int position : wordPositions_) {
        if (++count > kMaximumMarkers) {
            break;
        }
        markers.append({document()->findBlock(position).blockNumber(), QColor(theme::kScrollMarkerWord), 1});
    }
    for (const Diagnostic& diagnostic : diagnostics_) {
        markers.append({diagnostic.line - 1,
                        QColor(diagnostic.severity == "error" ? theme::kProblemError : theme::kProblemWarning), 2});
    }
    markers.append({textCursor().blockNumber(), QColor(theme::kScrollMarkerCursor), 3});
    markers_->setMarkers(markers, blockCount());
}

// ===========================================================================
// 小窓(引数のヒント・補完の説明・定義をその場で見る)
// ===========================================================================

void CodeEditor::showSignatureHelp(const QString& html) {
    if (!signature_) {
        signature_ = new HoverPopup(this);
        signature_->setObjectName("signatureHelp");
    }
    const QRect rect = cursorRect();
    signature_->showHtml(html, QRect(viewport()->mapToGlobal(rect.topLeft()), rect.size()), font(),
                         HoverPopup::Placement::Above, 640, 220);
}

void CodeEditor::hideSignatureHelp() {
    if (signature_) {
        signature_->cancelHide();
        signature_->hide();
    }
}

bool CodeEditor::isSignatureHelpVisible() const {
    return signature_ && signature_->isVisible();
}

QString CodeEditor::currentCompletion() const {
    if (!completer_->popup()->isVisible()) {
        return QString();
    }
    return completer_->popup()->currentIndex().data().toString();
}

void CodeEditor::showCompletionDetail(const HoverInfo& info) {
    if (info.isEmpty() || !completer_->popup()->isVisible()) {
        hideCompletionDetail();
        return;
    }
    if (!completionDetail_) {
        completionDetail_ = new HoverPopup(this);
        completionDetail_->setObjectName("completionDetail");
    }
    completionDetail_->showHtml(HoverPopup::toHtml(info, font().family()), completer_->popup()->geometry(), font(),
                                HoverPopup::Placement::Right, 420, 300);
}

void CodeEditor::hideCompletionDetail() {
    if (completionDetail_) {
        completionDetail_->cancelHide();
        completionDetail_->hide();
    }
}

void CodeEditor::showPeek(const QString& html, int position) {
    if (!peek_) {
        peek_ = new HoverPopup(this);
        peek_->setObjectName("peekDefinition");
    }
    QTextCursor cursor(document());
    cursor.setPosition(qBound(0, position, document()->characterCount() - 1));
    const QRect rect = cursorRect(cursor);
    peek_->showHtml(html, QRect(viewport()->mapToGlobal(rect.topLeft()), rect.size()), font(),
                    HoverPopup::Placement::Below, 780, 360);
}

void CodeEditor::hidePeek() {
    for (HoverPopup* popup : {peek_, problemPopup_}) {
        if (popup) {
            popup->cancelHide();
            popup->hide();
        }
    }
}

// ===========================================================================
// 選択範囲の拡大
// ===========================================================================

void CodeEditor::expandSelection() {
    const QTextCursor cursor = textCursor();
    int start = 0;
    int end = 0;
    if (!expandedSelection(document(), language_, cursor.selectionStart(), cursor.selectionEnd(), &start, &end)) {
        return;
    }
    selectionStack_.append({cursor.anchor(), cursor.position()});
    expanding_ = true;
    QTextCursor expanded(document());
    expanded.setPosition(start);
    expanded.setPosition(end, QTextCursor::KeepAnchor);
    lastExpanded_ = {start, end};
    setTextCursor(expanded);
    expanding_ = false;
}

void CodeEditor::shrinkSelection() {
    if (selectionStack_.isEmpty()) {
        return;
    }
    const QPair<int, int> previous = selectionStack_.takeLast();
    expanding_ = true;
    QTextCursor cursor(document());
    cursor.setPosition(previous.first);
    cursor.setPosition(previous.second, QTextCursor::KeepAnchor);
    lastExpanded_ = {cursor.selectionStart(), cursor.selectionEnd()};
    setTextCursor(cursor);
    expanding_ = false;
}

}  // namespace hedit
