/** @file find_bar.cpp
 * @brief FindBarの実装。
 */
#include "editor/find_bar.h"
#include "editor/code_editor.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QCheckBox>
#include <QEvent>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QShortcut>
#include <QTabBar>
#include <QTabWidget>
#include <QVBoxLayout>

namespace hedit {
namespace {

/** @brief 検索バーのスタイルシート(VS Code風の暗い見た目)。
 * @return 拡大率を反映したスタイルシート。
 */
QString findBarStyleSheet() {
    return QString("QWidget#findBar{background:%1;}"
                   " QLineEdit{background:%2;color:%3;border:%4px solid %5;padding:%6px;}"
                   " QCheckBox,QLabel{color:%7;font-size:%8px;}"
                   " QCheckBox{spacing:0;padding:%6px;font-weight:bold;font-size:%9px;}"
                   " QCheckBox::indicator{width:0;height:0;}"
                   " QCheckBox:checked{background:%10;color:%11;}"
                   " QPushButton{background:transparent;border:0;color:%7;padding:%4px;font-weight:bold;font-size:%12px;}"
                   " QPushButton:hover{background:%13;}"
                   " QLineEdit:focus{border:%4px solid %14;}")
        .arg(QString(theme::kFindBarBackground))      // %1
        .arg(QString(theme::kFindFieldBackground))    // %2
        .arg(QString(theme::kText))                   // %3
        .arg(scaled(1))                               // %4
        .arg(QString(theme::kFindFieldBorder))        // %5
        .arg(scaled(2))                               // %6
        .arg(QString(theme::kFindLabel))              // %7
        .arg(scaled(12))                              // %8
        .arg(scaled(13))                              // %9
        .arg(QString(theme::kFindToggleChecked))      // %10
        .arg(QString(theme::kFindToggleCheckedText))  // %11
        .arg(scaled(16))                              // %12
        .arg(QString(theme::kFindButtonHover))        // %13
        .arg(QString(theme::kFindFieldFocusBorder));  // %14
}

/** @brief 文字だけの小さな切り替えボタン(``Tt``など)を作る。
 * @param text ボタンの文字。
 * @param name objectName(テストが探すときの名前)。
 * @param tooltip マウスを重ねたときの説明。
 * @return 新しいチェックボックス。レイアウトへ追加した時点で親が所有する。
 */
QCheckBox* makeToggle(const QString& text, const QString& name, const QString& tooltip) {
    auto toggle = new QCheckBox(text);
    toggle->setObjectName(name);
    toggle->setToolTip(tooltip);
    return toggle;
}

}  // namespace

FindBar::FindBar(QTabWidget* tabs) : QWidget(tabs), tabs_(tabs) {
    setObjectName("findBar");
    setStyleSheet(findBarStyleSheet());

    // 1行目: [>] [検索語] [Tt] [Abc] [.*] [件数] [←] [→] [×]
    auto rows = new QVBoxLayout(this);
    rows->setContentsMargins(scaled(3), scaled(2), scaled(3), scaled(2));
    auto searchRow = new QHBoxLayout;
    searchRow->setSpacing(scaled(2));
    rows->addLayout(searchRow);

    auto toggleReplace = new QPushButton(">");
    toggleReplace->setFixedWidth(scaled(22));
    toggleReplace->setToolTip("Toggle replace");
    searchRow->addWidget(toggleReplace);

    findText_ = new QLineEdit;
    findText_->setObjectName("findText");
    findText_->setPlaceholderText("Find");
    findText_->setMinimumWidth(scaled(60));
    searchRow->addWidget(findText_);

    matchCase_ = makeToggle("Tt", "searchCase", "Match case");
    wholeWord_ = makeToggle("Abc", "searchWord", "Whole words");
    regex_ = makeToggle(".*", "searchRegex", "Regular expression; replacements support $1, $2, $& and $$");
    searchRow->addWidget(matchCase_);
    searchRow->addWidget(wholeWord_);
    searchRow->addWidget(regex_);

    matchCount_ = new QLabel;
    matchCount_->setObjectName("searchCount");
    matchCount_->setMinimumWidth(scaled(54));
    searchRow->addWidget(matchCount_);

    auto previous = new QPushButton("←");
    previous->setToolTip("Previous match (Shift+F3)");
    previous->setFixedWidth(scaled(24));
    auto next = new QPushButton("→");
    next->setToolTip("Next match (F3)");
    next->setFixedWidth(scaled(24));
    searchRow->addWidget(previous);
    searchRow->addWidget(next);

    // 2行目: [置換の文字列] [Replace] [Replace all]
    replaceRow_ = new QWidget;
    auto replaceLayout = new QHBoxLayout(replaceRow_);
    replaceLayout->setContentsMargins(0, 0, 0, 0);
    replaceText_ = new QLineEdit;
    replaceText_->setObjectName("replaceText");
    replaceText_->setPlaceholderText("Replace");
    auto replaceOne = new QPushButton("Replace");
    replaceOne->setObjectName("replaceOne");
    auto replaceAll = new QPushButton("Replace all");
    replaceAll->setObjectName("replaceAll");
    replaceLayout->addWidget(replaceText_);
    replaceLayout->addWidget(replaceOne);
    replaceLayout->addWidget(replaceAll);
    rows->addWidget(replaceRow_);

    auto closeButton = new QPushButton("×");
    closeButton->setFixedWidth(scaled(24));
    searchRow->addWidget(closeButton);

    // ---- ボタンと入力の接続 ----
    connect(previous, &QPushButton::clicked, this, [this] { findNext(true); });
    connect(next, &QPushButton::clicked, this, [this] { findNext(); });
    connect(findText_, &QLineEdit::returnPressed, this, [this] { findNext(); });
    connect(findText_, &QLineEdit::textEdited, this, [this] { searchWhileTyping(); });
    connect(replaceOne, &QPushButton::clicked, this, [this] { replace(false); });
    connect(replaceAll, &QPushButton::clicked, this, [this] { replace(true); });
    connect(toggleReplace, &QPushButton::clicked, this, [this] {
        replaceRow_->setVisible(!replaceRow_->isVisible());
        updatePosition();
    });
    connect(closeButton, &QPushButton::clicked, this, [this] { closeBar(); });

    // バーの中にフォーカスがあるときだけ、Escでバーを閉じる。
    auto escape = new QShortcut(QKeySequence(Qt::Key_Escape), this);
    escape->setContext(Qt::WidgetWithChildrenShortcut);
    connect(escape, &QShortcut::activated, closeButton, &QPushButton::click);

    // タブ欄の大きさの変化を、eventFilterで受け取る。
    tabs_->installEventFilter(this);
    hide();
}

void FindBar::open(bool withReplace) {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (editor) {
        const QString selection = editor->textCursor().selectedText();
        // U+2029は、QTextCursorが選択文字列の中の改行を表す文字。複数行の選択は検索語にしない。
        if (!selection.isEmpty() && !selection.contains(QChar(0x2029))) {
            findText_->setText(selection);
        }
    }
    show();
    replaceRow_->setVisible(withReplace);
    updatePosition();
    findText_->setFocus();
    findText_->selectAll();
}

SearchOptions FindBar::options() const {
    SearchOptions options;
    options.text = findText_->text();
    options.matchCase = matchCase_->isChecked();
    options.wholeWord = wholeWord_->isChecked();
    options.regex = regex_->isChecked();
    return options;
}

SearchResult FindBar::search(bool withReplacements) {
    const QString replacement = replaceText_->text();
    SearchResult result = findMatches(currentEditor()->toPlainText(), options(),
                                      withReplacements ? &replacement : nullptr);
    if (!result.ok() && showStatus) {
        showStatus(result.error, 0);
    }
    return result;
}

void FindBar::selectMatch(const TextMatch& match) {
    CodeEditor* editor = currentEditor();
    QTextCursor cursor = editor->textCursor();
    cursor.setPosition(match.start);
    cursor.setPosition(match.start + match.length, QTextCursor::KeepAnchor);
    editor->setTextCursor(cursor);
    editor->ensureCursorVisible();
}

bool FindBar::findNext(bool backward) {
    if (findText_->text().isEmpty()) {
        open(false);
        return false;
    }
    const SearchResult result = search(false);
    if (!result.ok()) {
        return false;
    }
    const QList<TextMatch>& matches = result.matches;
    if (matches.isEmpty()) {
        matchCount_->setText("No results");
        showStatus("No matches", 2000);
        return false;
    }

    // 現在の選択の後ろ(前)にある最初の一致を探す。無ければ先頭(末尾)へ折り返す。
    const QTextCursor cursor = currentEditor()->textCursor();
    int index = backward ? matches.size() - 1 : 0;
    if (backward) {
        for (int i = matches.size() - 1; i >= 0; --i) {
            if (matches[i].start + matches[i].length <= cursor.selectionStart()) {
                index = i;
                break;
            }
        }
    } else {
        for (int i = 0; i < matches.size(); ++i) {
            if (matches[i].start >= cursor.selectionEnd()) {
                index = i;
                break;
            }
        }
    }
    selectMatch(matches[index]);
    matchCount_->setText(QString("%1 of %2").arg(index + 1).arg(matches.size()));
    showStatus(QString("Match %1 of %2").arg(index + 1).arg(matches.size()), 2000);
    return true;
}

void FindBar::searchWhileTyping() {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (!editor) {
        return;
    }
    // 選択の先頭を基準にする。h→hl→hliと伸ばしても、選択末尾から次の一致へ飛ばないため。
    QTextCursor cursor = editor->textCursor();
    const int start = cursor.selectionStart();
    cursor.setPosition(start);
    if (findText_->text().isEmpty()) {
        editor->setTextCursor(cursor);
        matchCount_->clear();
        return;
    }
    const SearchResult result = search(false);
    if (!result.ok()) {
        editor->setTextCursor(cursor);
        matchCount_->setText("Invalid");
        return;
    }
    if (result.matches.isEmpty()) {
        editor->setTextCursor(cursor);
        matchCount_->setText("No results");
        return;
    }
    int index = 0;
    for (int i = 0; i < result.matches.size(); ++i) {
        if (result.matches[i].start >= start) {
            index = i;
            break;
        }
    }
    selectMatch(result.matches[index]);
    matchCount_->setText(QString("%1 of %2").arg(index + 1).arg(result.matches.size()));
}

void FindBar::replace(bool all) {
    if (findText_->text().isEmpty()) {
        return;
    }
    // 置換の前に、元の本文で一致箇所と置換後の文字列を全て決めておく。
    const SearchResult result = search(true);
    if (!result.ok()) {
        return;
    }
    CodeEditor* editor = currentEditor();
    if (!all) {
        // 選択が一致箇所そのものなら、その1件だけを置換して次の一致へ移る。
        QTextCursor cursor = editor->textCursor();
        const TextMatch selected{cursor.selectionStart(), cursor.selectionEnd() - cursor.selectionStart()};
        const int index = result.matches.indexOf(selected);
        if (index >= 0) {
            cursor.beginEditBlock();
            cursor.insertText(result.replacements[index]);
            cursor.endEditBlock();
            editor->setTextCursor(cursor);
        }
        findNext();
        return;
    }
    // 後ろから置換すると、前の一致の位置がずれない。全体を1回のUndoにまとめる。
    QTextCursor group(editor->document());
    group.beginEditBlock();
    QTextCursor cursor(editor->document());
    for (int i = result.matches.size() - 1; i >= 0; --i) {
        const TextMatch& match = result.matches[i];
        cursor.setPosition(match.start);
        cursor.setPosition(match.start + match.length, QTextCursor::KeepAnchor);
        cursor.insertText(result.replacements[i]);
    }
    group.endEditBlock();
    showStatus(QString("Replaced %1 matches").arg(result.matches.size()), 2000);
}

bool FindBar::eventFilter(QObject* watched, QEvent* event) {
    if (watched == tabs_ && event->type() == QEvent::Resize) {
        updatePosition();
    }
    return QWidget::eventFilter(watched, event);
}

void FindBar::updatePosition() {
    if (isHidden()) {
        return;
    }
    // レイアウトを先に確定させてから、必要な高さ(sizeHint)を読む。
    layout()->activate();
    const int width = qMin(scaled(470), qMax(0, tabs_->width() - scaled(12)));
    resize(width, sizeHint().height());
    const int x = qMax(0, tabs_->width() - this->width() - scaled(6));
    const int y = tabs_->tabBar()->height() + scaled(4);
    move(x, y);
    raise();  // タブの中身より手前に表示する。
}

void FindBar::closeBar() {
    hide();
    if (CodeEditor* editor = currentEditor ? currentEditor() : nullptr) {
        editor->setFocus();
    }
}

}  // namespace hedit
