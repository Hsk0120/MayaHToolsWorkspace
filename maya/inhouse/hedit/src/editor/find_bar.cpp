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
#include <QElapsedTimer>
#include <QEvent>
#include <QFontMetrics>
#include <QFrame>
#include <QGraphicsDropShadowEffect>
#include <QGraphicsEffect>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QImage>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPainterPath>
#include <QShortcut>
#include <QStringMatcher>
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

/// これより多い文字数の本文では、入力・条件の切り替えから少し待ってから検索する。
constexpr int kLargeDocument = 200000;

/// 大きな本文で、入力・条件の切り替えが止まってから検索するまでの時間(ミリ秒)。
constexpr int kLargeDocumentDelay = 75;

/// 一致の件数の上限(core/text_search.cppのfindMatchesと同じ)。これを超える検索は止める。
constexpr int kMaximumMatches = 100000;

// ---- 影(VS Codeの検索ウィジェットと同じく、コードの上に重なる範囲を分かりやすくする) ----
constexpr int kShadowBlur = 12;    ///< 影のぼかしの半径(拡大率100%のときのピクセル数)。
constexpr int kShadowOffset = 1;   ///< 影の下へのずれ。
constexpr int kShadowAlpha = 150;  ///< 影の濃さ(0〜255)。

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

/** @brief バーの形(角の丸い四角)の影を、大きさが変わったときだけ描いて覚えておくグラフィック効果。
 * @details QGraphicsDropShadowEffectは、バーの中の部品が描き直されるたびに(入力欄のカーソルの点滅でも)
 * バー全体を画像に描いてぼかし直すので重い。バーは不透明で、影の形はバーの大きさだけで決まるため、
 * 大きさが変わったときだけ影を画像にし、普段はその画像を貼ってから、バーをそのまま描く(drawSource)。
 * 影の画像は、同じ形の四角に以前と同じQGraphicsDropShadowEffectを付けて1回だけ描いて作る(見た目は以前と同じ)。
 * Q_OBJECTは不要(仮想関数を上書きするだけで、シグナル・スロットは使わない)。所有者はバー。
 */
class CachedShadowEffect : public QGraphicsEffect {
public:
    /** @brief 影を作る。 @param parent 所有者(バー)。 */
    explicit CachedShadowEffect(QObject* parent) : QGraphicsEffect(parent) {}

protected:
    /** @brief 影を含めた描画範囲(QGraphicsDropShadowEffectと同じ求め方)。
     * @param rect バーの範囲。
     * @return 影まで含めた範囲。
     */
    QRectF boundingRectFor(const QRectF& rect) const override {
        const qreal blur = scaled(kShadowBlur);
        return rect.united(rect.translated(0, scaled(kShadowOffset)).adjusted(-blur, -blur, blur, blur));
    }

    /** @brief 覚えておいた影の画像を貼り、その上にバーを描く。 @param painter 描画先。 */
    void draw(QPainter* painter) override {
        const QRectF source = sourceBoundingRect(Qt::LogicalCoordinates);
        const QSize size = source.size().toSize();
        if (size != shadowSize_) {
            rebuild(size);
        }
        const int blur = scaled(kShadowBlur);
        painter->drawPixmap(source.topLeft() + QPointF(-blur, -blur), shadow_);
        drawSource(painter);
    }

private:
    /** @brief バーの大きさの影の画像を作り直す。 @param size バーの大きさ。 */
    void rebuild(const QSize& size) {
        shadowSize_ = size;
        const int blur = scaled(kShadowBlur);
        const int offset = scaled(kShadowOffset);
        QImage shadow(size.width() + blur * 2, size.height() + blur * 2 + offset, QImage::Format_ARGB32_Premultiplied);
        shadow.fill(Qt::transparent);
        if (!size.isEmpty()) {
            // バーと同じ形の黒い四角に、以前と同じQGraphicsDropShadowEffectを付けて描き(影と四角)、
            // 四角だけも描く。影の色は黒なので、2つの不透明度の差から影だけの不透明度を求められる。
            QGraphicsScene scene;
            QPainterPath path;
            path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), scaled(kBarRadius), scaled(kBarRadius));
            QGraphicsPathItem* item = scene.addPath(path, Qt::NoPen, QColor(Qt::black));
            auto effect = new QGraphicsDropShadowEffect;  // 所有者はitem(setGraphicsEffectで渡す)。
            effect->setBlurRadius(blur);
            effect->setOffset(0, offset);  // 下へのずれも画像に含める(四角の下の影は、バーの下に隠れない)。
            effect->setColor(QColor(0, 0, 0, kShadowAlpha));
            item->setGraphicsEffect(effect);
            const QRectF area(-blur, -blur, shadow.width(), shadow.height());
            auto render = [&scene, &area](QImage* image) {
                image->fill(Qt::transparent);
                QPainter painter(image);
                painter.setRenderHint(QPainter::Antialiasing, true);
                scene.render(&painter, QRectF(image->rect()), area);
            };
            QImage withShadow(shadow.size(), QImage::Format_ARGB32_Premultiplied);
            render(&withShadow);
            item->setGraphicsEffect(nullptr);  // 効果を外して破棄し、四角だけを描く。
            QImage shape(shadow.size(), QImage::Format_ARGB32_Premultiplied);
            render(&shape);
            for (int y = 0; y < shadow.height(); ++y) {
                const QRgb* both = reinterpret_cast<const QRgb*>(withShadow.constScanLine(y));
                const QRgb* only = reinterpret_cast<const QRgb*>(shape.constScanLine(y));
                QRgb* out = reinterpret_cast<QRgb*>(shadow.scanLine(y));
                for (int x = 0; x < shadow.width(); ++x) {
                    // 四角の不透明度b、影と四角の不透明度aから、影の不透明度 s = (a - b) / (1 - b) を求める。
                    // 四角で完全に隠れる所(b = 255)は、バーの下で見えないので、影の最も濃い値にする。
                    const int b = qAlpha(only[x]);
                    const int a = qAlpha(both[x]);
                    const int alpha = b == 0 ? a : b == 255 ? kShadowAlpha : qBound(0, (a - b) * 255 / (255 - b), 255);
                    out[x] = qRgba(0, 0, 0, alpha);  // 黒なので、乗算済みの色も0のまま。
                }
            }
        }
        shadow_ = QPixmap::fromImage(shadow);
    }

    QSize shadowSize_;  ///< 影を作ったときのバーの大きさ。
    QPixmap shadow_;    ///< 影の画像(バーの大きさに、上下左右へぼかしの半径と、下へのずれを足した大きさ)。
};

/** @brief UTF-16として正しいか(上位・下位のサロゲートが対になっているか)。
 * @param text 文字列。
 * @return 対になっていないサロゲートが無ければtrue。
 */
bool isValidUtf16(const QString& text) {
    const int size = text.size();
    for (int i = 0; i < size; ++i) {
        const QChar c = text.at(i);
        if (!c.isSurrogate()) {
            continue;
        }
        if (c.isHighSurrogate() && i + 1 < size && text.at(i + 1).isLowSurrogate()) {
            ++i;
            continue;
        }
        return false;
    }
    return true;
}

/** @brief 文字列がU+0000〜U+007F(英数字・記号など)だけか。 @param text 文字列。 @return そうならtrue。 */
bool isAscii(const QString& text) {
    for (const QChar c : text) {
        if (c.unicode() > 0x7f) {
            return false;
        }
    }
    return true;
}

/** @brief 2つの検索条件が、置換を除いて同じ一致箇所になるか。 @param a 条件。 @param b 条件。 @return 同じならtrue。 */
bool sameSearch(const SearchOptions& a, const SearchOptions& b) {
    return a.text == b.text && a.matchCase == b.matchCase && a.wholeWord == b.wholeWord && a.regex == b.regex
           && a.rangeStart == b.rangeStart && a.rangeEnd == b.rangeEnd;
}

}  // namespace

FindBar::FindBar(QTabWidget* tabs) : QWidget(tabs), tabs_(tabs) {
    setObjectName("findBar");
    // QWidgetの背景をスタイルシートで塗るために必要な設定。スタイルシート・アイコン・影は、
    // 初めて開くとき(ensureDecorated)に用意する。
    setAttribute(Qt::WA_StyledBackground, true);

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
        connect(toggle, &QToolButton::toggled, this, [this] { scheduleOptionRefresh(); });
    }

    // バーの中にフォーカスがあるときだけ、Escでバーを閉じる。
    auto escape = new QShortcut(QKeySequence(Qt::Key_Escape), this);
    escape->setContext(Qt::WidgetWithChildrenShortcut);
    connect(escape, &QShortcut::activated, this, [this] { closeBar(); });

    // 本文の変化の後の更新は、タイマーで1回にまとめる。
    refreshTimer_.setSingleShot(true);
    refreshTimer_.setInterval(kRefreshDelay);
    connect(&refreshTimer_, &QTimer::timeout, this, [this] { refreshMatches(); });
    // 大きな本文では、入力・条件の切り替えが止まってから1回だけ検索する。
    searchTimer_.setSingleShot(true);
    searchTimer_.setInterval(kLargeDocumentDelay);
    connect(&searchTimer_, &QTimer::timeout, this, [this] {
        if (typingPending_) {
            typingPending_ = false;
            searchWhileTypingNow();
        } else {
            refreshMatches();
        }
    });
    // 1文字が\w(Unicodeの性質を使う)に当たるかを調べる。検索の正規表現(core/text_search.cpp)と同じ設定。
    wordPattern_ = QRegularExpression("\\A\\w\\z", QRegularExpression::UseUnicodePropertiesOption);

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
    iconButtons_.append({button, icon});  // アイコンは初めて開くとき(ensureDecorated)に描く。
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
    if (decorated_) {
        toggleReplace_->setIcon(findIcon(visible ? FindIcon::ChevronDown : FindIcon::ChevronRight,
                                         QColor(theme::kFindLabel), scaled(kIconSize)));
    }
    updatePosition();
}

void FindBar::ensureDecorated() {
    if (decorated_) {
        return;
    }
    decorated_ = true;
    setStyleSheet(findBarStyleSheet());
    for (const auto& entry : iconButtons_) {
        QToolButton* button = entry.first;
        // オンの切り替えボタンは、アイコンを白くする(VS Codeと同じ)。QIcon::Onが、チェックされたときの絵。
        QIcon image = findIcon(entry.second, QColor(theme::kFindLabel), scaled(kIconSize));
        if (button->isCheckable()) {
            const QIcon checked = findIcon(entry.second, QColor(theme::kFindToggleCheckedText), scaled(kIconSize));
            image.addPixmap(checked.pixmap(scaled(kIconSize)), QIcon::Normal, QIcon::On);
        }
        button->setIcon(image);
    }
    iconButtons_.clear();
    // 開閉ボタンは、今の置換欄の開閉に合わせた絵にする。
    toggleReplace_->setIcon(findIcon(replaceField_->isHidden() ? FindIcon::ChevronRight : FindIcon::ChevronDown,
                                     QColor(theme::kFindLabel), scaled(kIconSize)));
    // コードの上に重なるので、VS Codeと同じく周りに影を付けて範囲を分かりやすくする。効果はこのバーが所有する。
    // 影は大きさが変わったときだけ描き直す(CachedShadowEffect)。
    setGraphicsEffect(new CachedShadowEffect(this));
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
    ensureDecorated();
    // 下のrefreshMatches()で数え直すので、待っている検索は要らない。
    searchTimer_.stop();
    typingPending_ = false;
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
    CodeEditor* editor = currentEditor();
    const SearchOptions current = options();
    const int revision = editor->document()->revision();
    SearchResult result;
    if (!withReplacements && resultEditor_ == editor && resultRevision_ == revision
        && sameSearch(resultOptions_, current)) {
        result = result_;  // 本文も条件も同じ(F3を続けて押した場合など)。前回の結果を使う。
        currentGeneration_ = resultGeneration_;
    } else {
        QElapsedTimer timer;  // 計測用(動的プロパティsearchMillisecondsに入れる)。
        timer.start();
        const QString replacement = replaceText_->text();
        const QString* replacementTemplate = withReplacements ? &replacement : nullptr;
        const QString& document = documentText(editor);
        bool handled = false;
        if (!current.regex) {
            result = findPlainMatches(document, current, replacementTemplate, &handled);
        }
        if (!handled) {
            result = findMatches(document, current, replacementTemplate);
        }
        setProperty("searchMilliseconds", timer.nsecsElapsed() / 1000000.0);
        setProperty("searchComputations", property("searchComputations").toInt() + 1);
        if (withReplacements) {
            currentGeneration_ = -1;  // 置換の検索は控えない(この後すぐ本文を変えるため)。
        } else {
            resultEditor_ = editor;
            resultRevision_ = revision;
            resultOptions_ = current;
            result_ = result;
            currentGeneration_ = ++resultGeneration_;
        }
    }
    if (!result.ok() && showStatus) {
        showStatus(result.error, 0);
    }
    return result;
}

const QString& FindBar::documentText(CodeEditor* editor) {
    const int revision = editor->document()->revision();
    if (textEditor_ != editor || textRevision_ != revision) {
        text_ = editor->toPlainText();
        textEditor_ = editor;
        textRevision_ = revision;
        textValidity_ = -1;
    }
    return text_;
}

bool FindBar::isLargeDocument(const CodeEditor* editor) {
    return editor && editor->document()->characterCount() > kLargeDocument;
}

bool FindBar::isWordCharacter(uint code) {
    if (code < 0x80) {
        // 英数字・記号の範囲は、\wに当たるのは英数字と_だけ(Unicodeの性質を使っても同じ)。
        return (code >= 'a' && code <= 'z') || (code >= 'A' && code <= 'Z') || (code >= '0' && code <= '9')
               || code == '_';
    }
    // それ以外は、検索で使うのと同じ正規表現に判定させて覚えておく(QtのPCRE2の版で\wの範囲が違っても同じ結果)。
    const auto found = wordCharacters_.constFind(code);
    if (found != wordCharacters_.constEnd()) {
        return found.value();
    }
    const char32_t character = char32_t(code);
    const bool word = wordPattern_.match(QString::fromUcs4(&character, 1)).hasMatch();
    wordCharacters_.insert(code, word);
    return word;
}

SearchResult FindBar::findPlainMatches(const QString& document, const SearchOptions& options,
                                       const QString* replacementTemplate, bool* handled) {
    SearchResult result;
    *handled = false;
    // 正規表現と同じ結果を保証できる場合だけ扱う。大文字小文字を区別しない比較は、英数字・記号だけの検索語なら
    // Qtの比較(QChar::toCaseFolded)と正規表現(PCRE2)で同じになる(K⇔U+212A、s⇔U+017Fもどちらも一致として扱う)。
    // 不正なUTF-16を含む文字列は、正規表現の側の扱いが違うので任せる。
    if (options.regex || options.text.isEmpty() || (!options.matchCase && !isAscii(options.text))
        || !isValidUtf16(options.text)) {
        return result;
    }
    if (&document == &text_) {
        if (textValidity_ < 0) {
            textValidity_ = isValidUtf16(document) ? 1 : 0;
        }
        if (textValidity_ == 0) {
            return result;
        }
    } else if (!isValidUtf16(document)) {
        return result;
    }
    *handled = true;
    const QStringMatcher matcher(options.text, options.matchCase ? Qt::CaseSensitive : Qt::CaseInsensitive);
    const int length = options.text.size();
    const int size = document.size();
    const bool limited = options.rangeStart >= 0 && options.rangeEnd >= options.rangeStart;
    // 1文字前・後の文字(サロゲートの対は1文字にまとめる)が\wに当たるか。
    auto wordBefore = [this, &document](int position) {
        if (position <= 0) {
            return false;
        }
        const QChar low = document.at(position - 1);
        if (low.isLowSurrogate() && position >= 2 && document.at(position - 2).isHighSurrogate()) {
            return isWordCharacter(QChar::surrogateToUcs4(document.at(position - 2), low));
        }
        return isWordCharacter(low.unicode());
    };
    auto wordAfter = [this, &document, size](int position) {
        if (position >= size) {
            return false;
        }
        const QChar high = document.at(position);
        if (high.isHighSurrogate() && position + 1 < size && document.at(position + 1).isLowSurrogate()) {
            return isWordCharacter(QChar::surrogateToUcs4(high, document.at(position + 1)));
        }
        return isWordCharacter(high.unicode());
    };
    int from = 0;
    while (true) {
        const int start = int(matcher.indexIn(document, from));
        if (start < 0) {
            break;
        }
        // 単語単位では、前後が単語の文字でない位置だけ。外れたら1文字先から探し直す(正規表現と同じ)。
        if (options.wholeWord && (wordBefore(start) || wordAfter(start + length))) {
            from = start + 1;
            continue;
        }
        if (result.matches.size() >= kMaximumMatches) {
            result.error = "Too many matches (limit 100,000)";  // findMatchesと同じ文言・同じ時点で止める。
            return result;
        }
        from = start + length;
        // 選択範囲内で検索するときは、範囲に収まる一致だけを数える。
        if (limited && (start < options.rangeStart || start + length > options.rangeEnd)) {
            continue;
        }
        result.matches.append({start, length});
        if (replacementTemplate) {
            // 通常の検索では置換の文字列をそのまま使う($記法は正規表現モードだけ)。
            QString value = *replacementTemplate;
            if (options.preserveCase) {
                value = preserveCase(value, document.mid(start, length));
            }
            result.replacements.append(value);
        }
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
    // 同じ検索の結果(本文も条件も同じ)を同じコード欄に付けてあれば、付け直さない(2000件の強調を作り直さない)。
    if (editor && editor == highlighted_ && currentGeneration_ >= 0 && currentGeneration_ == highlightedGeneration_) {
        return;
    }
    highlighted_ = editor;
    highlightedGeneration_ = currentGeneration_;
    if (editor) {
        editor->setSearchHighlights(result.ok() ? result.matches.mid(0, kMaximumHighlights) : QList<TextMatch>());
    }
}

void FindBar::clearHighlights() {
    if (highlighted_) {
        highlighted_->clearSearchHighlights();
    }
    highlighted_ = nullptr;
    highlightedGeneration_ = -1;
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
    flushPendingSearch();  // 入力中の検索を待っていれば、先に済ませてから次の一致へ移る(待たない場合と同じ結果)。
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
    if (isLargeDocument(editor)) {
        // 大きな本文では、打鍵のたびに全文を探さず、入力が止まってから1回だけ探す。
        typingPending_ = true;
        searchTimer_.start();
        return;
    }
    searchWhileTypingNow();
}

void FindBar::searchWhileTypingNow() {
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

void FindBar::scheduleOptionRefresh() {
    CodeEditor* editor = currentEditor ? currentEditor() : nullptr;
    if (isHidden() || !isLargeDocument(editor)) {
        refreshMatches();  // 小さな本文では、今までどおりすぐ数え直す。
        return;
    }
    // 入力中の検索を待っている場合は、その検索が件数も出し直すので、そのまま待つ。
    searchTimer_.start();
}

void FindBar::flushPendingSearch() {
    if (!searchTimer_.isActive()) {
        return;
    }
    searchTimer_.stop();
    if (typingPending_) {
        typingPending_ = false;
        searchWhileTypingNow();
    } else {
        refreshMatches();
    }
}

void FindBar::replace(bool all) {
    flushPendingSearch();
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
    searchTimer_.stop();
    typingPending_ = false;
    // 本文の写しと結果の控えを手放す(大きな本文の写しを、閉じた後まで持ち続けない)。
    text_.clear();
    textEditor_ = nullptr;
    textRevision_ = -1;
    result_ = SearchResult();
    resultEditor_ = nullptr;
    resultRevision_ = -1;
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
