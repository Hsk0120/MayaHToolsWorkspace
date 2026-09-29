/** @file find_bar.cpp
 * @brief FindBarの実装。
 * @details 見た目はスタイルシート(findBarStyleSheet)にまとめてある。入力欄の枠の「入力中」「エラー」は、
 * 枠の動的プロパティ(focused・error)を切り替え、スタイルシートの``[focused="true"]``などで色を変える。
 * プロパティを変えた後は、unpolish/polishでスタイルシートを当て直す必要がある(Qtの決まり)。
 * アイコンはfind_icons.cppがその場で描く(画像ファイルは使わない。hedit.mllに組み込まれる)。
 */
#include "editor/find_bar.h"
#include "editor/code_editor.h"
#include "editor/find_icons.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QEvent>
#include <QFontMetrics>
#include <QFrame>
#include <QGraphicsDropShadowEffect>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QShortcut>
#include <QStyle>
#include <QTabBar>
#include <QTabWidget>
#include <QToolButton>

namespace hedit {
namespace {

/// 本文の中で背景を付ける一致箇所の上限。これより多い分は件数だけ数える(描画が重くならないように)。
constexpr int kMaximumHighlights = 2000;

/// 本文の変化から、件数と強調を更新するまでの待ち時間(ミリ秒)。
constexpr int kRefreshDelay = 150;

// ---- VS Codeの検索ウィジェットの寸法(拡大率100%のときのピクセル数) ----
constexpr int kBarWidth = 419;          ///< バーの幅。
constexpr int kInputHeight = 25;        ///< 入力欄の高さ(文字が大きいときは文字に合わせて高くする)。
constexpr int kButtonSize = 22;         ///< ↑↓≡×・置換ボタンの大きさ。
constexpr int kOptionSize = 20;         ///< 入力欄の中の切り替えボタン(Aa など)の大きさ。
constexpr int kIconSize = 16;           ///< アイコンの大きさ。
constexpr int kToggleWidth = 18;        ///< 左端の開閉ボタンの幅。
constexpr int kCountWidth = 69;         ///< 件数の欄の幅。
constexpr int kBarRadius = 8;           ///< バーの角の丸み。
constexpr int kInputRadius = 4;         ///< 入力欄の角の丸み。

/** @brief 検索バーのスタイルシート。
 * @return 拡大率を反映したスタイルシート。%1〜は下の.arg()で順に置き換わる。
 * @note 文字の大きさはスタイルシートでは指定しない(setEditorFontでエディターと同じフォントを設定する)。
 */
QString findBarStyleSheet() {
    return QString(
               // バー全体: 背景・枠線・角の丸み。
               "QWidget#findBar{background:%1;border:%2px solid %3;border-radius:%4px;}"
               // 入力欄の枠。普段は細い枠、入力中は青、不正な正規表現は赤。
               "QFrame#findField,QFrame#replaceField{background:%5;border:%2px solid %6;border-radius:%7px;}"
               "QFrame#findField[focused=\"true\"],QFrame#replaceField[focused=\"true\"]{border-color:%8;}"
               "QFrame#findField[error=\"true\"]{border-color:%9;}"
               // 入力欄そのものは枠を持たない(外側の枠で表す)。
               "QLineEdit{background:transparent;border:0;color:%10;padding:0 %11px;"
               "selection-background-color:%12;selection-color:%10;}"
               // ボタン: 普段はアイコンだけ。マウスを重ねると背景、オンの切り替えボタンは青い背景と枠。
               "QToolButton{background:transparent;border:%2px solid transparent;border-radius:%13px;padding:0;}"
               "QToolButton:hover{background:%14;}"
               "QToolButton#searchCase,QToolButton#searchWord,QToolButton#searchRegex,QToolButton#preserveCase"
               "{border-radius:%15px;}"
               "QToolButton:checked{background:%16;border-color:%17;}"
               // 件数。一致なしのときは赤。
               "QLabel#searchCount{color:%18;padding-left:%15px;}"
               "QLabel#searchCount[error=\"true\"]{color:%19;}")
        .arg(QString(theme::kFindBarBackground))        // %1
        .arg(scaled(1))                                  // %2
        .arg(QString(theme::kFindBarBorder))            // %3
        .arg(scaled(kBarRadius))                         // %4
        .arg(QString(theme::kFindFieldBackground))      // %5
        .arg(QString(theme::kFindFieldBorder))          // %6
        .arg(scaled(kInputRadius))                       // %7
        .arg(QString(theme::kFindFieldFocusBorder))     // %8
        .arg(QString(theme::kFindFieldErrorBorder))     // %9
        .arg(QString(theme::kText))                     // %10
        .arg(scaled(4))                                  // %11
        .arg(QString(theme::kSelection))                // %12
        .arg(scaled(5))                                  // %13
        .arg(QString(theme::kFindButtonHover))          // %14
        .arg(scaled(3))                                  // %15
        .arg(QString(theme::kFindToggleChecked))        // %16
        .arg(QString(theme::kFindToggleCheckedBorder))  // %17
        .arg(QString(theme::kFindLabel))                // %18
        .arg(QString(theme::kFindErrorLabel));          // %19
}

/** @brief 不正な正規表現の吹き出しのスタイルシート。 @return スタイルシート。 */
QString errorBubbleStyleSheet() {
    return QString("QLabel#findError{background:%1;border:%2px solid %3;color:%4;padding:%5px %6px;}")
        .arg(QString(theme::kFindErrorBackground))
        .arg(scaled(1))
        .arg(QString(theme::kFindFieldErrorBorder))
        .arg(QString(theme::kText))
        .arg(scaled(4))
        .arg(scaled(6));
}

}  // namespace

FindBar::FindBar(QTabWidget* tabs) : QWidget(tabs), tabs_(tabs) {
    setObjectName("findBar");
    // QWidgetの背景をスタイルシートで塗るために必要な設定。
    setAttribute(Qt::WA_StyledBackground, true);
    setStyleSheet(findBarStyleSheet());
    // コードの上に重なるので、VS Codeと同じく周りに影を付けて範囲を分かりやすくする。効果はこのバーが所有する。
    auto shadow = new QGraphicsDropShadowEffect(this);
    shadow->setBlurRadius(scaled(12));
    shadow->setOffset(0, scaled(1));
    shadow->setColor(QColor(0, 0, 0, 150));
    setGraphicsEffect(shadow);

    // ---- 部品 ----
    toggleReplace_ = makeButton(FindIcon::ChevronRight, "toggleReplace", "Toggle Replace", false, false);
    // 開閉ボタンは幅18pxで、置換欄を開いたときは2行分の高さに伸ばす。
    toggleReplace_->setFixedWidth(scaled(kToggleWidth));
    toggleReplace_->setMinimumHeight(scaled(kButtonSize));
    toggleReplace_->setMaximumHeight(QWIDGETSIZE_MAX);
    toggleReplace_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);

    findText_ = new QLineEdit;
    findText_->setObjectName("findText");
    findText_->setPlaceholderText("Find");
    findField_ = makeField(findText_, "findField");
    matchCase_ = makeButton(FindIcon::MatchCase, "searchCase", "Match Case", true, true);
    wholeWord_ = makeButton(FindIcon::WholeWord, "searchWord", "Match Whole Word", true, true);
    regex_ = makeButton(FindIcon::Regex, "searchRegex",
                        "Use Regular Expression (replacements support $1, $2, $& and $$)", true, true);
    findField_->layout()->addWidget(matchCase_);
    findField_->layout()->addWidget(wholeWord_);
    findField_->layout()->addWidget(regex_);

    matchCount_ = new QLabel;
    matchCount_->setObjectName("searchCount");
    matchCount_->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    matchCount_->setFixedWidth(scaled(kCountWidth));  // 件数の文字が変わっても、右のボタンの位置を動かさない。

    auto previous = makeButton(FindIcon::ArrowUp, "findPrevious", "Previous Match (Shift+Enter, Shift+F3)", false, false);
    auto next = makeButton(FindIcon::ArrowDown, "findNextMatch", "Next Match (Enter, F3)", false, false);
    inSelection_ = makeButton(FindIcon::Selection, "findInSelection", "Find in Selection", true, false);
    auto close = makeButton(FindIcon::Close, "closeFind", "Close (Escape)", false, false);

    replaceText_ = new QLineEdit;
    replaceText_->setObjectName("replaceText");
    replaceText_->setPlaceholderText("Replace");
    replaceField_ = makeField(replaceText_, "replaceField");
    preserveCase_ = makeButton(FindIcon::PreserveCase, "preserveCase", "Preserve Case", true, true);
    replaceField_->layout()->addWidget(preserveCase_);
    replaceOne_ = makeButton(FindIcon::Replace, "replaceOne", "Replace (Enter in the replace field)", false, false);
    replaceAll_ = makeButton(FindIcon::ReplaceAll, "replaceAll", "Replace All (one undo step)", false, false);

    // 不正な正規表現の理由の吹き出し。バーの外(下)へはみ出して表示するため、タブ欄の子にする。
    errorBubble_ = new QLabel(tabs_);
    errorBubble_->setObjectName("findError");
    errorBubble_->setWordWrap(true);
    errorBubble_->setStyleSheet(errorBubbleStyleSheet());
    errorBubble_->hide();

    // ---- 格子状の配置 ----
    // 列: 0=開閉 / 1=入力欄(伸びる) / 2=件数 / 3〜6=↑↓≡×。2行目の置換ボタンは列2〜6をまとめて使う。
    // 余白・間隔はVS Codeの寸法(左3px+開閉18px+間7pxで入力欄が28pxから始まる、上下4px、行の間4px)。
    auto grid = new QGridLayout(this);
    grid->setContentsMargins(scaled(3), scaled(4), scaled(4), scaled(4));
    grid->setHorizontalSpacing(scaled(3));
    grid->setVerticalSpacing(scaled(4));
    grid->addWidget(toggleReplace_, 0, 0, 2, 1);  // 2行分の高さ。
    grid->setColumnMinimumWidth(0, scaled(kToggleWidth + 4));  // 開閉ボタンと入力欄の間を7pxにする。
    grid->addWidget(findField_, 0, 1);
    grid->addWidget(matchCount_, 0, 2);
    grid->addWidget(previous, 0, 3);
    grid->addWidget(next, 0, 4);
    grid->addWidget(inSelection_, 0, 5);
    grid->addWidget(close, 0, 6);
    auto replaceButtons = new QHBoxLayout;
    replaceButtons->setSpacing(scaled(3));
    replaceButtons->addWidget(replaceOne_);
    replaceButtons->addWidget(replaceAll_);
    replaceButtons->addStretch();
    grid->addWidget(replaceField_, 1, 1);
    grid->addLayout(replaceButtons, 1, 2, 1, 5);
    grid->setColumnStretch(1, 1);

    // ---- ボタンと入力の接続 ----
    connect(previous, &QToolButton::clicked, this, [this] { findNext(true); });
    connect(next, &QToolButton::clicked, this, [this] { findNext(); });
    connect(close, &QToolButton::clicked, this, [this] { closeBar(); });
    connect(toggleReplace_, &QToolButton::clicked, this, [this] { setReplaceVisible(replaceField_->isHidden()); });
    connect(inSelection_, &QToolButton::toggled, this, [this](bool enabled) { setFindInSelection(enabled); });
    connect(findText_, &QLineEdit::returnPressed, this, [this] { findNext(); });
    connect(findText_, &QLineEdit::textEdited, this, [this] { searchWhileTyping(); });
    connect(replaceText_, &QLineEdit::returnPressed, this, [this] { replace(false); });
    connect(replaceOne_, &QToolButton::clicked, this, [this] { replace(false); });
    connect(replaceAll_, &QToolButton::clicked, this, [this] { replace(true); });
    // 条件を切り替えたら、今の検索語で数え直す(カーソルは動かさない)。
    for (QToolButton* toggle : {matchCase_, wholeWord_, regex_}) {
        connect(toggle, &QToolButton::toggled, this, [this] { refreshMatches(); });
    }

    // バーの中にフォーカスがあるときだけ、Escでバーを閉じる。
    auto escape = new QShortcut(QKeySequence(Qt::Key_Escape), this);
    escape->setContext(Qt::WidgetWithChildrenShortcut);
    connect(escape, &QShortcut::activated, this, [this] { closeBar(); });

    // 本文の変化の後の更新は、タイマーで1回にまとめる。
    refreshTimer_.setSingleShot(true);
    refreshTimer_.setInterval(kRefreshDelay);
    connect(&refreshTimer_, &QTimer::timeout, this, [this] { refreshMatches(); });

    // タブ欄の大きさの変化と、入力欄のフォーカス・キーをeventFilterで受け取る。
    tabs_->installEventFilter(this);
    findText_->installEventFilter(this);
    replaceText_->installEventFilter(this);
    setReplaceVisible(false);
    hide();
}

QToolButton* FindBar::makeButton(FindIcon icon, const QString& name, const QString& tooltip, bool checkable,
                                 bool inputOption) {
    auto button = new QToolButton;
    button->setObjectName(name);
    button->setToolTip(tooltip);
    button->setCheckable(checkable);
    button->setFocusPolicy(Qt::NoFocus);  // クリックしても入力欄のフォーカスを奪わない。
    // オンの切り替えボタンは、アイコンを白くする(VS Codeと同じ)。QIcon::Onが、チェックされたときの絵。
    QIcon image = findIcon(icon, QColor(theme::kFindLabel), scaled(kIconSize));
    if (checkable) {
        const QIcon checked = findIcon(icon, QColor(theme::kFindToggleCheckedText), scaled(kIconSize));
        image.addPixmap(checked.pixmap(scaled(kIconSize)), QIcon::Normal, QIcon::On);
    }
    button->setIcon(image);
    button->setIconSize(QSize(scaled(kIconSize), scaled(kIconSize)));
    const int size = scaled(inputOption ? kOptionSize : kButtonSize);
    button->setFixedSize(size, size);
    return button;
}

QFrame* FindBar::makeField(QLineEdit* edit, const QString& name) {
    auto field = new QFrame;
    field->setObjectName(name);
    field->setFixedHeight(scaled(kInputHeight));
    field->setMinimumWidth(scaled(120));
    auto layout = new QHBoxLayout(field);
    layout->setContentsMargins(scaled(1), 0, scaled(2), 0);
    layout->setSpacing(scaled(2));
    layout->addWidget(edit, 1);
    return field;
}

void FindBar::setEditorFont(const QFont& font) {
    for (QWidget* widget : {static_cast<QWidget*>(findText_), static_cast<QWidget*>(replaceText_),
                            static_cast<QWidget*>(matchCount_), static_cast<QWidget*>(errorBubble_)}) {
        widget->setFont(font);
    }
    // 文字が大きいときは、入力欄を文字に合わせて高くする(VS Codeの25pxより小さくはしない)。
    const QFontMetrics metrics(font);
    const int height = qMax(scaled(kInputHeight), metrics.height() + scaled(6));
    // 件数の欄も、最も長い「No results」が切れない幅にする(VS Codeの69pxより狭くはしない)。
    matchCount_->setFixedWidth(qMax(scaled(kCountWidth), metrics.horizontalAdvance("No results") + scaled(6)));
    findField_->setFixedHeight(height);
    replaceField_->setFixedHeight(height);
    updatePosition();
}

void FindBar::setReplaceVisible(bool visible) {
    replaceField_->setVisible(visible);
    replaceOne_->setVisible(visible);
    replaceAll_->setVisible(visible);
    const bool open = visible;
    toggleReplace_->setIcon(findIcon(open ? FindIcon::ChevronDown : FindIcon::ChevronRight,
                                     QColor(theme::kFindLabel), scaled(kIconSize)));
    updatePosition();
}

void FindBar::setState(QWidget* widget, const char* property, bool value) {
    if (widget->property(property).toBool() == value) {
        return;
    }
    widget->setProperty(property, value);
    // 動的プロパティを変えただけでは、スタイルシートは当て直されない。
    widget->style()->unpolish(widget);
    widget->style()->polish(widget);
    widget->update();
}

void FindBar::showCount(const QString& text, bool error) {
    matchCount_->setText(text);
    setState(matchCount_, "error", error);
}

void FindBar::showError(const QString& message) {
    setState(findField_, "error", !message.isEmpty());
    errorBubble_->setText(message);
    errorBubble_->setVisible(!message.isEmpty() && !isHidden());
    updatePosition();
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
    setReplaceVisible(withReplace);
    findText_->setFocus();
    findText_->selectAll();
    refreshMatches();
}

SearchOptions FindBar::options() const {
    SearchOptions options;
    options.text = findText_->text();
    options.matchCase = matchCase_->isChecked();
    options.wholeWord = wholeWord_->isChecked();
    options.regex = regex_->isChecked();
    options.preserveCase = preserveCase_->isChecked();
    // 「選択範囲内で検索」は、範囲を覚えたコード欄を検索するときだけ効かせる。
    if (inSelection_->isChecked() && scopeEditor_ && scopeEditor_ == (currentEditor ? currentEditor() : nullptr)) {
        options.rangeStart = scope_.selectionStart();
        options.rangeEnd = scope_.selectionEnd();
    }
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

void FindBar::showResult(const SearchResult& result, int current) {
    highlight(result);
    showError(result.ok() ? QString() : result.error);
    if (!result.ok() || result.matches.isEmpty()) {
        // VS Codeと同じく、不正な正規表現も「No results」と表示する(理由は吹き出しに出す)。
        showCount("No results", true);
        return;
    }
    const QString position = current >= 0 ? QString::number(current + 1) : QString("?");
    showCount(QString("%1 of %2").arg(position).arg(result.matches.size()), false);
}

void FindBar::highlight(const SearchResult& result) {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (highlighted_ && highlighted_ != editor) {
        highlighted_->clearSearchHighlights();  // 前に付けた別のタブの強調を消す。
    }
    highlighted_ = editor;
    if (editor) {
        editor->setSearchHighlights(result.ok() ? result.matches.mid(0, kMaximumHighlights) : QList<TextMatch>());
    }
}

void FindBar::clearHighlights() {
    if (highlighted_) {
        highlighted_->clearSearchHighlights();
    }
    highlighted_ = nullptr;
}

void FindBar::setFindInSelection(bool enabled) {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (enabled) {
        // オンにした時点の選択範囲を覚える。QTextCursorは本文の編集に合わせて位置が動く。
        if (!editor || !editor->textCursor().hasSelection()) {
            inSelection_->setChecked(false);  // 選択が無ければ、範囲を決められないのでオフに戻す。
            if (showStatus) {
                showStatus("Select the text to search in first", 3000);
            }
            return;
        }
        scope_ = editor->textCursor();
        scopeEditor_ = editor;
    } else {
        scope_ = QTextCursor();
        scopeEditor_ = nullptr;
    }
    refreshMatches();
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
    const QList<TextMatch>& matches = result.matches;
    if (!result.ok() || matches.isEmpty()) {
        showResult(result, -1);
        if (result.ok() && showStatus) {
            showStatus("No matches", 2000);
        }
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
    showResult(result, index);
    if (showStatus) {
        showStatus(QString("Match %1 of %2").arg(index + 1).arg(matches.size()), 2000);
    }
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
        showCount(QString(), false);
        showError(QString());
        clearHighlights();
        return;
    }
    const SearchResult result = search(false);
    if (!result.ok() || result.matches.isEmpty()) {
        editor->setTextCursor(cursor);
        showResult(result, -1);
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
    showResult(result, index);
}

void FindBar::refreshMatches() {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (isHidden() || !editor) {
        return;
    }
    if (findText_->text().isEmpty()) {
        showCount(QString(), false);
        showError(QString());
        clearHighlights();
        return;
    }
    const SearchResult result = search(false);
    // 選択が一致箇所そのものなら何件目か、そうでなければ「?」(VS Codeと同じ表示)。
    const QTextCursor cursor = editor->textCursor();
    const TextMatch selected{cursor.selectionStart(), cursor.selectionEnd() - cursor.selectionStart()};
    showResult(result, result.matches.indexOf(selected));
}

void FindBar::scheduleRefresh() {
    if (!isHidden()) {
        refreshTimer_.start();
    }
}

void FindBar::replace(bool all) {
    if (findText_->text().isEmpty()) {
        return;
    }
    // 置換の前に、元の本文で一致箇所と置換後の文字列を全て決めておく。
    const SearchResult result = search(true);
    if (!result.ok()) {
        showResult(result, -1);
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
    if (showStatus) {
        showStatus(QString("Replaced %1 matches").arg(result.matches.size()), 2000);
    }
    refreshMatches();
}

bool FindBar::eventFilter(QObject* watched, QEvent* event) {
    if (watched == tabs_ && event->type() == QEvent::Resize) {
        updatePosition();
    }
    // 入力中の欄の枠を青くする(スタイルシートだけでは、中の入力欄のフォーカスを枠に反映できないため)。
    if (watched == findText_ || watched == replaceText_) {
        QFrame* field = watched == findText_ ? findField_ : replaceField_;
        if (event->type() == QEvent::FocusIn) {
            setState(field, "focused", true);
        } else if (event->type() == QEvent::FocusOut) {
            setState(field, "focused", false);
        }
    }
    // 検索欄のShift+Enterは前の一致へ(VS Codeと同じ)。
    if (watched == findText_ && event->type() == QEvent::KeyPress) {
        auto key = static_cast<QKeyEvent*>(event);
        const bool enter = key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter;
        if (enter && key->modifiers() == Qt::ShiftModifier) {
            findNext(true);
            return true;
        }
    }
    return QWidget::eventFilter(watched, event);
}

void FindBar::hideEvent(QHideEvent* event) {
    refreshTimer_.stop();
    clearHighlights();
    errorBubble_->hide();
    QWidget::hideEvent(event);
}

void FindBar::updatePosition() {
    if (isHidden()) {
        return;
    }
    // レイアウトを先に確定させてから、必要な高さ(sizeHint)を読む。
    layout()->activate();
    const int width = qMin(scaled(kBarWidth), qMax(0, tabs_->width() - scaled(12)));
    resize(width, sizeHint().height());
    const int x = qMax(0, tabs_->width() - this->width() - scaled(6));
    const int y = tabs_->tabBar()->height() + scaled(4);
    move(x, y);
    raise();  // タブの中身より手前に表示する。
    // 吹き出しは検索欄の真下に、同じ幅で重ねる。
    if (errorBubble_->isVisible()) {
        const QPoint origin = findField_->mapTo(tabs_, QPoint(0, findField_->height()));
        // 折り返した文字が全て入る高さを、幅から求める(adjustSizeは折り返しの高さを正しく求めないため)。
        errorBubble_->setFixedWidth(findField_->width());
        errorBubble_->setFixedHeight(errorBubble_->heightForWidth(findField_->width()));
        errorBubble_->move(origin);
        errorBubble_->raise();
    }
}

void FindBar::closeBar() {
    hide();
    if (CodeEditor* editor = currentEditor ? currentEditor() : nullptr) {
        editor->setFocus();
    }
}

}  // namespace hedit
