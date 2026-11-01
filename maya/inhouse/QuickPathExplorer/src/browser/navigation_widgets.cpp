/** @file navigation_widgets.cpp @brief タブの見た目とファイル転送の明示境界。 */
#include "navigation_widgets.h"
#include <QAbstractButton>
#include <QCursor>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QResizeEvent>
#include <QUrl>
#include <QLineEdit>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QFileInfo>
#include <QTimer>
#include <QStyledItemDelegate>
#include <QJsonObject>
#include <QLocale>
#include <QApplication>
namespace qpe {
namespace {
/** @brief 変換中のEnter/Escapeを改名確定に使わない、一時的な編集欄。 */
class RenameEdit final : public QLineEdit {
public:
    /** @brief ビューのviewportが所有する。 @param parent 所有者。 */
    explicit RenameEdit(QWidget* parent) : QLineEdit(parent) { setObjectName("inlineRename"); }
    std::function<void(const QString&)> submit;
protected:
    /** @brief preeditの有無を追跡し、文字確定はQtへ委譲する。 @param event IME入力。 */
    void inputMethodEvent(QInputMethodEvent* event) override { composing_ = !event->preeditString().isEmpty(); QLineEdit::inputMethodEvent(event); }
    /** @brief 確定と中止を一度だけ実行する。 @param event キー入力。 */
    void keyPressEvent(QKeyEvent* event) override {
        if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter || event->key() == Qt::Key_Escape) {
            if (!composing_) finish(event->key() != Qt::Key_Escape);
            event->accept(); return;
        }
        QLineEdit::keyPressEvent(event);
    }
    /** @brief 他の欄へ移動したら一度だけ確定する。 @param event フォーカス変更。 */
    void focusOutEvent(QFocusEvent* event) override { QLineEdit::focusOutEvent(event); if (!composing_) finish(true); }
private:
    /** @brief 編集欄の破棄を遅延し、外部の実ファイル操作へ通知する。 @param commit 確定か。 */
    void finish(bool commit) {
        if (finished_) return; finished_ = true;
        const auto name = text(); const auto callback = submit;
        const bool returnFocus = hasFocus(); hide(); deleteLater();
        if (returnFocus && parentWidget()->parentWidget()) parentWidget()->parentWidget()->setFocus(Qt::OtherFocusReason);
        if (commit && callback) QTimer::singleShot(0, parentWidget(), [callback, name] { callback(name); });
    }
    bool composing_ = false, finished_ = false;
};
/** @brief ドライブを一度だけ描き、背景・容量バー・文字の重なりを防ぐ。 */
class PlacesDelegate final : public QStyledItemDelegate {
public:
    /** @brief サイドバーが所有する。 @param parent 所有者。 */
    explicit PlacesDelegate(QObject* parent) : QStyledItemDelegate(parent) {}
    /** @brief ドライブだけを2行と容量バーにする。 @param painter 描画先。 @param option 項目領域。 @param index モデル項目。 */
    void paint(QPainter* painter, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        const auto drive = index.data(Qt::UserRole + 30).toJsonObject();
        if (drive.isEmpty()) { QStyledItemDelegate::paint(painter, option, index); return; }
        auto background = option; initStyleOption(&background, index); const auto icon = background.icon;
        background.text.clear(); background.icon = QIcon();
        const auto path = index.data(Qt::UserRole + 1).toString();
        if (path.compare(parent()->property("currentDrive").toString(), Qt::CaseInsensitive) == 0) background.state |= QStyle::State_Selected;
        const auto* style = option.widget ? option.widget->style() : QApplication::style();
        style->drawControl(QStyle::CE_ItemViewItem, &background, painter, option.widget);
        painter->save(); painter->setClipRect(option.rect); painter->setFont(option.font);
        const int margin = 4, iconSize = qMax(18, option.fontMetrics.height() + 4), line = option.fontMetrics.height();
        icon.paint(painter, QRect(option.rect.left() + margin, option.rect.center().y() - iconSize / 2, iconSize, iconSize));
        const int left = option.rect.left() + iconSize + margin * 2, width = qMax(0, option.rect.right() - left - margin);
        painter->setPen(option.palette.color(background.state & QStyle::State_Selected ? QPalette::HighlightedText : QPalette::Text));
        painter->drawText(QRect(left, option.rect.top() + margin, width, line), Qt::AlignVCenter, option.fontMetrics.elidedText(index.data().toString(), Qt::ElideRight, width));
        const double capacity = drive["total"].toDouble(-1), free = drive["free"].toDouble(-1);
        const QRect bar(left, option.rect.top() + line + 7, width, 5);
        painter->fillRect(bar, option.palette.color(QPalette::Mid));
        if (capacity > 0) { auto used = bar; used.setWidth(qRound(width * qBound(0.0, 1.0 - free / capacity, 1.0))); painter->fillRect(used, free / capacity < .1 ? QColor("#c42b1c") : QColor("#0078d4")); }
        const auto info = capacity > 0 ? QLocale().formattedDataSize(qint64(free), 1, QLocale::DataSizeTraditionalFormat) + " free / " + QLocale().formattedDataSize(qint64(capacity), 1, QLocale::DataSizeTraditionalFormat) : QString("Capacity unavailable");
        painter->drawText(QRect(left, bar.bottom() + 3, width, line), Qt::AlignVCenter, option.fontMetrics.elidedText(info, Qt::ElideRight, width)); painter->restore();
    }
    /** @brief 字形寸法に合わせて2行分を予約する。 @param option フォント。 @param index 項目。 @return 必要な高さ。 */
    QSize sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        auto size = QStyledItemDelegate::sizeHint(option, index); if (!index.data(Qt::UserRole + 30).toJsonObject().isEmpty()) size.setHeight(option.fontMetrics.height() * 2 + 20); return size;
    }
};
/** @brief グループ行も含むモデルから固定パスを探す。 @param model モデル。 @param path パス。 @param parent 探索起点。 @return 一致項目。 */
QModelIndex renameIndex(QAbstractItemModel* model, const QString& path, const QModelIndex& parent = {}) {
    for (int row = 0; row < model->rowCount(parent); ++row) {
        const auto index = model->index(row, 0, parent);
        if (index.data(Qt::UserRole + 1).toString() == path) return index;
        if (model->hasChildren(index)) { const auto child = renameIndex(model, path, index); if (child.isValid()) return child; }
    }
    return {};
}
/** @brief ローカルファイルURL以外を除く。 @param data ドラッグ内容。 @return パス。 */
QStringList paths(const QMimeData* data) { QStringList result; for (const auto& url : data->urls()) if (url.isLocalFile() && !url.toLocalFile().isEmpty()) result.append(url.toLocalFile()); result.removeDuplicates(); return result; }
/** @brief 赤い四角を使わず小さな×を描く。 */
class CloseGlyph final : public QAbstractButton {
public:
    /** @brief タブ所有のボタンを作る。 @param parent 所有者。 */
    explicit CloseGlyph(QWidget* parent) : QAbstractButton(parent) { setAccessibleName("Close tab"); setToolTip("Close tab"); setFocusPolicy(Qt::NoFocus); }
protected:
    /** @brief ホバー面と細線を描く。 @param event 描画要求。 */
    void paintEvent(QPaintEvent*) override {
        QPainter p(this); p.setRenderHint(QPainter::Antialiasing); auto color = palette().color(QPalette::Text);
        if (underMouse() || isDown()) { auto background = color; background.setAlpha(isDown() ? 30 : 18); p.setPen(Qt::NoPen); p.setBrush(background); p.drawRoundedRect(QRectF(rect()).adjusted(1, 1, -1, -1), 4, 4); }
        if (!isEnabled()) color.setAlpha(75); p.setPen(QPen(color, 1.2)); const auto center = QRectF(rect()).center(); const qreal r = width() / 5.;
        p.drawLine(center + QPointF(-r, -r), center + QPointF(r, r)); p.drawLine(center + QPointF(r, -r), center + QPointF(-r, r));
    }
};
}
bool inlineRename(QAbstractItemView* view, const QString& path, std::function<void(const QString&)> submit) {
    if (!view || !view->isVisible() || !view->model()) return false;
    const auto index = renameIndex(view->model(), path); if (!index.isValid()) return false;
    if (auto* existing = view->viewport()->findChild<QLineEdit*>("inlineRename")) { existing->setFocus(); return true; }
    view->scrollTo(index); const auto rect = view->visualRect(index); if (!rect.isValid()) return false;
    auto* edit = new RenameEdit(view->viewport()); edit->submit = std::move(submit);
    edit->setFont(view->font()); edit->setText(QFileInfo(path).fileName());
    QRect area = rect.adjusted(view->iconSize().width() + 5, 0, -3, 0);
    area.setWidth(qMin(qMax(80, area.width()), view->viewport()->width() - area.left()));
    edit->setGeometry(area); edit->show(); edit->setFocus(Qt::OtherFocusReason);
    const QFileInfo info(path); const auto name = info.fileName(); const auto dot = name.lastIndexOf('.');
    edit->setSelection(0, !info.isDir() && dot > 0 ? dot : name.size()); return true;
}
NavigationTabs::NavigationTabs(QWidget* parent) : QTabBar(parent) {
    // Qt標準のTabFocusではクリックしてもMaya側の入力フォーカスが残る。明示クリックだけでQPEへ移す。
    setFocusPolicy(Qt::StrongFocus);
    setAcceptDrops(true); setMouseTracking(true); setDrawBase(false); setUsesScrollButtons(true); setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}
void NavigationTabs::setScale(qreal value) { scale_ = qBound(qreal(.5), value, qreal(4)); refreshSizes(); }
QSize NavigationTabs::tabSizeHint(int) const { return {qBound(qRound(100 * scale_), width() / qMax(1, count()), qRound(240 * scale_)), qMax(qRound(32 * scale_), fontMetrics().height() + qRound(12 * scale_))}; }
QSize NavigationTabs::minimumTabSizeHint(int index) const { return tabSizeHint(index); }
QSize NavigationTabs::sizeHint() const { return {qMax(1, count()) * qRound(240 * scale_), tabSizeHint(0).height()}; }
QSize NavigationTabs::minimumSizeHint() const { return {qRound(100 * scale_), tabSizeHint(0).height()}; }
void NavigationTabs::refreshSizes() { setMaximumWidth(qMax(1, count()) * qRound(240 * scale_)); setIconSize(QSize(qRound(16 * scale_), qRound(16 * scale_))); for (int i = 0; i < count(); ++i) if (auto* button = tabButton(i, RightSide)) button->setFixedSize(qRound(22 * scale_), qRound(22 * scale_)); setExpanding(true); setExpanding(false); updateGeometry(); update(); }
void NavigationTabs::tabInserted(int index) {
    QTabBar::tabInserted(index);
    for (const auto side : {LeftSide, RightSide}) if (auto* old = tabButton(index, side)) { setTabButton(index, side, nullptr); old->deleteLater(); }
    auto* close = new CloseGlyph(this); connect(close, &QAbstractButton::clicked, this, [this, close] { for (int i = 0; i < count(); ++i) if (tabButton(i, RightSide) == close) { emit tabCloseRequested(i); return; } });
    setTabButton(index, RightSide, close); refreshSizes();
}
void NavigationTabs::tabRemoved(int index) { QTabBar::tabRemoved(index); refreshSizes(); }
void NavigationTabs::resizeEvent(QResizeEvent* event) { QTabBar::resizeEvent(event); refreshSizes(); }
void NavigationTabs::paintEvent(QPaintEvent*) {
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing); p.fillRect(rect(), palette().color(QPalette::Window));
    const int hover = underMouse() ? tabAt(mapFromGlobal(QCursor::pos())) : -1;
    for (int i = 0; i < count(); ++i) { const QRectF area(tabRect(i)); if (!area.intersects(rect())) continue;
        if (i == currentIndex() || i == hover) { p.setPen(Qt::NoPen); p.setBrush(palette().color(i == currentIndex() ? QPalette::Base : QPalette::AlternateBase)); p.drawRoundedRect(area.adjusted(1, 1, -1, -1), 6 * scale_, 6 * scale_); }
        else if (i + 1 != currentIndex()) { auto line = palette().color(QPalette::Text); line.setAlpha(40); p.setPen(line); p.drawLine(QPointF(area.right(), area.top() + 9 * scale_), QPointF(area.right(), area.bottom() - 9 * scale_)); }
        tabIcon(i).paint(&p, QRect(qRound(area.left() + 12 * scale_), qRound(area.center().y() - 8 * scale_), qRound(16 * scale_), qRound(16 * scale_)));
        const auto text = area.adjusted(36 * scale_, 0, -32 * scale_, 0); p.setPen(palette().color(QPalette::Text)); p.drawText(text, Qt::AlignLeft | Qt::AlignVCenter, fontMetrics().elidedText(tabText(i), Qt::ElideRight, qMax(0, int(text.width()))));
    }
}
void NavigationTabs::mouseReleaseEvent(QMouseEvent* event) { if (event->button() == Qt::MiddleButton) { const int i = tabAt(event->pos()); if (i >= 0) emit tabCloseRequested(i); event->accept(); return; } QTabBar::mouseReleaseEvent(event); }
void NavigationTabs::dragEnterEvent(QDragEnterEvent* event) { if (!paths(event->mimeData()).isEmpty()) event->acceptProposedAction(); }
void NavigationTabs::dragMoveEvent(QDragMoveEvent* event) { if (!paths(event->mimeData()).isEmpty()) event->acceptProposedAction(); }
void NavigationTabs::dropEvent(QDropEvent* event) { const auto files = paths(event->mimeData()); if (files.isEmpty() || !transfer) return; transfer(files, tabAt(event->pos()), event->keyboardModifiers().testFlag(Qt::ShiftModifier)); event->setDropAction(Qt::CopyAction); event->accept(); }
PlacesTree::PlacesTree(QWidget* parent) : SettledTree(parent) { setAcceptDrops(true); setDropIndicatorShown(false); setItemDelegate(new PlacesDelegate(this)); setIndentation(12); setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff); }
void PlacesTree::dragEnterEvent(QDragEnterEvent* event) { if (!paths(event->mimeData()).isEmpty()) event->acceptProposedAction(); }
void PlacesTree::dragMoveEvent(QDragMoveEvent* event) { if (!paths(event->mimeData()).isEmpty()) event->acceptProposedAction(); }
void PlacesTree::dropEvent(QDropEvent* event) { const auto files = paths(event->mimeData()); if (files.isEmpty() || !favorite) return; favorite(files); event->setDropAction(Qt::CopyAction); event->accept(); }
}
