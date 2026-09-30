/** @file hover_popup.cpp
 * @brief HoverPopupの実装。
 */
#include "editor/hover_popup.h"
#include "core/script_lexer.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QCursor>
#include <QEvent>
#include <QGuiApplication>
#include <QRegularExpression>
#include <QScreen>
#include <QScrollBar>
#include <QTextBrowser>
#include <QTextDocument>
#include <QVBoxLayout>
#include <cmath>

namespace hedit {
namespace {

/// 小窓の最大の幅と高さ(拡大率100%のときのピクセル数)。VS Codeのホバーとほぼ同じ大きさ。
constexpr int kMaximumWidth = 560;
constexpr int kMaximumHeight = 320;

/// 名前とこの小窓の外へマウスが出てから閉じるまでの待ち時間(ミリ秒)。小窓へマウスを移せるように少し待つ。
constexpr int kHideDelay = 300;

/** @brief HTMLの特殊文字(``<``・``>``・``&``)を置き換える。 @param text 文字列。 @return HTMLに入れられる文字列。 */
QString escaped(const QString& text) {
    return text.toHtmlEscaped();
}

/** @brief 色を付けたHTMLの断片を作る。 @param text 文字列。 @param color 色。 @return ``<span>``。 */
QString colored(const QString& text, const char* color) {
    return QString("<span style=\"color:%1\">%2</span>").arg(QString(color), escaped(text));
}

/** @brief 見出し(``def show(floating=None)``)を、エディターと同じ色で塗ったHTMLにする。
 * @param signature 見出し。
 * @return HTMLの断片。
 */
QString signatureHtml(const QString& signature) {
    const QList<Token> tokens = tokenizeLine(signature, ScriptLanguage::Python, kLexerNormal, nullptr);
    QString html;
    int position = 0;
    const char* nextNameColor = nullptr;  // def・classの直後の名前の色。
    for (const Token& token : tokens) {
        html += escaped(signature.mid(position, token.start - position));
        const QString text = signature.mid(token.start, token.length);
        position = token.start + token.length;
        switch (token.type) {
        case TokenType::Name:
            if (text == "module") {
                // module maya.cmds: 点を含むモジュール名全体をクラス名の色にする。
                return html + colored(text, theme::kSyntaxConstant)
                       + colored(signature.mid(position), theme::kSyntaxClassName);
            }
            if (text == "def" || text == "class" || text == "property") {
                html += colored(text, theme::kSyntaxConstant);
                nextNameColor = text == "def" || text == "property" ? theme::kSyntaxFunction : theme::kSyntaxClassName;
            } else if (nextNameColor) {
                html += colored(text, nextNameColor);
                nextNameColor = nullptr;
            } else if (isConstant(text, ScriptLanguage::Python)) {
                html += colored(text, theme::kSyntaxConstant);
            } else if (isKeyword(text, ScriptLanguage::Python)) {
                html += colored(text, theme::kSyntaxKeyword);
            } else {
                html += colored(text, theme::kSyntaxIdentifier);
            }
            break;
        case TokenType::String:
            html += colored(text, theme::kSyntaxString);
            break;
        case TokenType::Number:
            html += colored(text, theme::kSyntaxNumber);
            break;
        default:
            html += escaped(text);
            break;
        }
    }
    html += escaped(signature.mid(position));
    return html;
}

/** @brief 文の中の``code``・`code`を、コードの色にする。 @param text HTMLへ置き換える前の1行。 @param codeFamily コードのフォント。
 * @return HTMLの断片。
 */
QString inlineHtml(const QString& text, const QString& codeFamily) {
    static const QRegularExpression code("``([^`]+)``|`([^`]+)`");
    QString html;
    int position = 0;
    auto matches = code.globalMatch(text);
    while (matches.hasNext()) {
        const QRegularExpressionMatch match = matches.next();
        html += escaped(text.mid(position, match.capturedStart() - position));
        const QString value = match.captured(1).isEmpty() ? match.captured(2) : match.captured(1);
        html += QString("<span style=\"font-family:'%1';color:%2\">%3</span>")
                    .arg(codeFamily, QString(theme::kHoverInlineCode), escaped(value));
        position = match.capturedEnd();
    }
    html += escaped(text.mid(position));
    return html;
}

/** @brief docstringを、Google形式の見出しと引数名を目立たせたHTMLにする。
 * @param doc docstring。
 * @param codeFamily コードのフォント。
 * @return HTMLの断片(改行と字下げは white-space:pre-wrap で保つ)。
 */
QString docHtml(const QString& doc, const QString& codeFamily) {
    // Google形式・NumPy形式でよく使う見出し。
    static const QRegularExpression section(
        "^(Args|Arguments|Parameters|Params|Keyword Args|Keyword Arguments|Returns?|Yields?|Raises|Attributes|"
        "Examples?|Notes?|Warnings?|See Also|Todo|References)\\s*:?\\s*$");
    // 見出しの中の「名前 (型): 説明」の行。
    static const QRegularExpression argument("^(\\s+)(\\*{0,2}[A-Za-z_]\\w*)(\\s*\\([^)]*\\))?(\\s*:)(.*)$");
    QStringList lines;
    bool inSection = false;
    for (const QString& line : doc.split('\n')) {
        const bool indented = line.startsWith(' ');
        if (!indented && section.match(line).hasMatch()) {
            lines.append("<b>" + escaped(line) + "</b>");
            inSection = true;
            continue;
        }
        if (!indented && !line.trimmed().isEmpty()) {
            inSection = false;
        }
        const QRegularExpressionMatch match = argument.match(line);
        if (inSection && match.hasMatch()) {
            lines.append(escaped(match.captured(1))
                         + QString("<span style=\"font-family:'%1';color:%2\">%3</span>")
                               .arg(codeFamily, QString(theme::kSyntaxIdentifier), escaped(match.captured(2)))
                         + escaped(match.captured(3)) + escaped(match.captured(4))
                         + inlineHtml(match.captured(5), codeFamily));
            continue;
        }
        lines.append(inlineHtml(line, codeFamily));
    }
    return lines.join('\n');
}

}  // namespace

HoverPopup::HoverPopup(QWidget* parent) : QFrame(parent, Qt::ToolTip | Qt::FramelessWindowHint) {
    setObjectName("hoverPopup");
    // 表示してもコード欄からフォーカスを奪わない(入力を続けられる)。
    setAttribute(Qt::WA_ShowWithoutActivating, true);
    setStyleSheet(QString("QFrame#hoverPopup{background:%1;border:%2px solid %3;}"
                          "QTextBrowser{background:%1;color:%4;border:0;}")
                      .arg(QString(theme::kPopupBackground))
                      .arg(scaled(1))
                      .arg(QString(theme::kPopupBorder))
                      .arg(QString(theme::kText)));
    view_ = new QTextBrowser(this);
    view_->setObjectName("hoverText");
    view_->setFrameShape(QFrame::NoFrame);
    view_->setOpenLinks(false);
    view_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    view_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    view_->document()->setDocumentMargin(scaled(8));
    auto layout = new QVBoxLayout(this);
    layout->setContentsMargins(scaled(1), scaled(1), scaled(1), scaled(1));
    layout->addWidget(view_);

    hideTimer_.setSingleShot(true);
    hideTimer_.setInterval(kHideDelay);
    connect(&hideTimer_, &QTimer::timeout, this, [this] {
        // 待つ間にマウスが小窓か名前の上へ戻っていれば閉じない。
        const QPoint mouse = QCursor::pos();
        if (!geometry().contains(mouse) && !anchor_.contains(mouse)) {
            hide();
        }
    });
    hide();
}

QString HoverPopup::toHtml(const HoverInfo& info, const QString& codeFamily) {
    QString html = QString("<div style=\"font-family:'%1';white-space:pre-wrap\">%2</div>")
                       .arg(codeFamily, signatureHtml(info.signature));
    if (!info.doc.isEmpty()) {
        html += QString("<hr style=\"background:%1\"/>").arg(QString(theme::kPopupBorder));
        html += "<div style=\"white-space:pre-wrap\">" + docHtml(info.doc, codeFamily) + "</div>";
    }
    return html;
}

void HoverPopup::showInfo(const HoverInfo& info, const QRect& anchor, const QFont& codeFont) {
    hideTimer_.stop();
    anchor_ = anchor;
    // docstringは読みやすいUIのフォント、見出しとコードはエディターのフォント(VS Codeと同じ)。
    const int pixels = codeFont.pixelSize() > 0 ? codeFont.pixelSize() : scaled(14);
    QFont textFont("Segoe UI");
    textFont.setPixelSize(qMax(1, pixels - 1));
    const QString html = toHtml(info, codeFont.family());
    view_->document()->setDefaultFont(textFont);
    view_->setHtml(html);

    // 大きさ: 最大幅で折り返したときに実際に使う幅と高さ。長いdocstringは最大の高さでスクロールさせる。
    // 表示用の文書はQTextBrowserが自分の幅で並べ直すため、測るのは別の文書で行う。
    QTextDocument measure;
    measure.setDefaultFont(textFont);
    measure.setDocumentMargin(view_->document()->documentMargin());
    measure.setHtml(html);
    const int maximumWidth = scaled(kMaximumWidth);
    const int maximumHeight = scaled(kMaximumHeight);
    measure.setTextWidth(maximumWidth);
    const int width = qMin(maximumWidth, int(std::ceil(measure.idealWidth())) + scaled(8));
    measure.setTextWidth(width);
    const int contentHeight = int(std::ceil(measure.size().height()));
    const int height = qMin(maximumHeight, contentHeight);
    const int scrollBar = contentHeight > maximumHeight ? view_->verticalScrollBar()->sizeHint().width() : 0;
    const int border = scaled(1) * 2;
    resize(width + scrollBar + border, height + border);
    // 実際の表示欄の幅で並べ直すと、折り返しが1行増えることがある。その高さで合わせ直す。
    layout()->activate();
    view_->document()->setTextWidth(view_->viewport()->width());
    const int shownHeight = int(std::ceil(view_->document()->size().height()));
    if (shownHeight > height && height < maximumHeight) {
        resize(this->width(), qMin(maximumHeight, shownHeight) + border);
    }

    // 位置: 名前の上。上に入らなければ下。画面の右端からはみ出さない。
    QScreen* screen = QGuiApplication::screenAt(anchor.center());
    const QRect area = screen ? screen->availableGeometry() : QRect(0, 0, 100000, 100000);
    int y = anchor.top() - this->height() - scaled(2);
    if (y < area.top()) {
        y = anchor.bottom() + scaled(2);
    }
    const int x = qMax(area.left(), qMin(anchor.left(), area.right() - this->width()));
    move(x, y);
    view_->verticalScrollBar()->setValue(0);
    show();
    raise();
}

void HoverPopup::scheduleHide() {
    if (isVisible() && !hideTimer_.isActive()) {
        hideTimer_.start();
    }
}

bool HoverPopup::event(QEvent* event) {
    if (event->type() == QEvent::Enter) {
        cancelHide();
    } else if (event->type() == QEvent::Leave) {
        scheduleHide();
    }
    return QFrame::event(event);
}

}  // namespace hedit
