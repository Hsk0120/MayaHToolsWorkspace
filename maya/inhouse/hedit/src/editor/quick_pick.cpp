/** @file quick_pick.cpp
 * @brief QuickPickの実装。
 */
#include "editor/quick_pick.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QApplication>
#include <QKeyEvent>
#include <QLineEdit>
#include <QListWidget>
#include <QSignalBlocker>
#include <QVBoxLayout>
#include <algorithm>

namespace hedit {
namespace {

/// 一覧に出す項目の上限(多すぎると絞り込みのたびに重くなる)。
constexpr int kMaximumShown = 300;

/// 項目の位置を入れる役割。
constexpr int kIndexRole = Qt::UserRole + 10;

}  // namespace

QuickPick::QuickPick(QWidget* parent) : QFrame(parent) {
    setObjectName("quickPick");
    setFrameShape(QFrame::NoFrame);
    setStyleSheet(QString("QFrame#quickPick{background:%1;border:%2px solid %3;}"
                          "QLineEdit{background:%4;color:%5;border:%2px solid %6;padding:%7px;}"
                          "QListWidget{background:%1;color:%5;border:0;outline:0;}"
                          "QListWidget::item{padding:%8px;}"
                          "QListWidget::item:selected{background:%9;color:#ffffff;}")
                      .arg(QString(theme::kPopupBackground))
                      .arg(scaled(1))
                      .arg(QString(theme::kPopupBorder))
                      .arg(QString(theme::kFindFieldBackground))
                      .arg(QString(theme::kText))
                      .arg(QString(theme::kFindFieldFocusBorder))
                      .arg(scaled(4))
                      .arg(scaled(2))
                      .arg(QString(theme::kPopupSelection)));
    input_ = new QLineEdit(this);
    input_->setObjectName("quickPickInput");
    list_ = new QListWidget(this);
    list_->setObjectName("quickPickList");
    list_->setFocusPolicy(Qt::NoFocus);
    list_->setUniformItemSizes(true);
    auto layout = new QVBoxLayout(this);
    layout->setContentsMargins(scaled(6), scaled(6), scaled(6), scaled(6));
    layout->setSpacing(scaled(4));
    layout->addWidget(input_);
    layout->addWidget(list_);
    input_->installEventFilter(this);
    connect(input_, &QLineEdit::textChanged, this, [this] { refilter(); });
    connect(list_, &QListWidget::currentRowChanged, this, [this](int row) {
        QListWidgetItem* item = list_->item(row);
        if (item && onPreview) {
            onPreview(items_.value(item->data(kIndexRole).toInt()).data);
        }
    });
    connect(list_, &QListWidget::itemClicked, this, [this] { accept(); });
    hide();
}

int QuickPick::matchScore(const QString& text, const QString& filter) {
    if (filter.isEmpty()) {
        return 0;
    }
    const QString lower = text.toLower();
    const QString wanted = filter.toLower();
    if (lower.startsWith(wanted)) {
        return 3000 - text.size();
    }
    const int contiguous = lower.indexOf(wanted);
    if (contiguous >= 0) {
        // 単語の先頭(_ . / の後・大文字)での一致を上にする。
        const bool wordStart = contiguous > 0 && (QString("_./\\ ").contains(lower[contiguous - 1]) || text[contiguous].isUpper());
        return (wordStart ? 2500 : 2000) - contiguous;
    }
    // 文字が順に含まれるか(あいまい検索)。
    int position = 0;
    int gaps = 0;
    for (const QChar c : wanted) {
        const int found = lower.indexOf(c, position);
        if (found < 0) {
            return -1;
        }
        gaps += found - position;
        position = found + 1;
    }
    return qMax(1, 1000 - gaps);
}

void QuickPick::open(const QString& placeholder, const QList<QuickPickItem>& items, int current) {
    items_ = items;
    closing_ = false;
    input_->setPlaceholderText(placeholder);
    {
        const QSignalBlocker blocker(input_);
        input_->clear();
    }
    refilter();
    if (current >= 0) {
        for (int row = 0; row < list_->count(); ++row) {
            if (list_->item(row)->data(kIndexRole).toInt() == current) {
                list_->setCurrentRow(row);
                list_->scrollToItem(list_->item(row), QAbstractItemView::PositionAtCenter);
                break;
            }
        }
    }
    // 親の上部の中央に、親の幅の6割(最大700px)で出す。
    QWidget* owner = parentWidget();
    const int width = qMin(scaled(700), qMax(scaled(360), owner->width() * 6 / 10));
    const int rowHeight = qMax(list_->sizeHintForRow(0), fontMetrics().height() + scaled(6));
    const int height = input_->sizeHint().height() + rowHeight * qMin(12, qMax(1, list_->count())) + scaled(20);
    setGeometry((owner->width() - width) / 2, scaled(28), width, height);
    show();
    raise();
    input_->setFocus(Qt::PopupFocusReason);
}

void QuickPick::refilter() {
    const QString filter = input_->text();
    QList<QPair<int, int>> ranked;  // (点数, 項目の位置)
    for (int i = 0; i < items_.size(); ++i) {
        const int score = matchScore(items_[i].label, filter);
        if (score >= 0) {
            ranked.append({score, i});
        }
    }
    if (!filter.isEmpty()) {
        std::stable_sort(ranked.begin(), ranked.end(),
                         [](const QPair<int, int>& a, const QPair<int, int>& b) { return a.first > b.first; });
    }
    const QSignalBlocker blocker(list_);
    list_->clear();
    for (int i = 0; i < ranked.size() && i < kMaximumShown; ++i) {
        const QuickPickItem& item = items_[ranked[i].second];
        auto row = new QListWidgetItem(item.description.isEmpty() ? item.label
                                                                  : item.label + "    " + item.description,
                                       list_);
        row->setData(kIndexRole, ranked[i].second);
        row->setToolTip(item.description);
    }
    if (list_->count() > 0) {
        list_->setCurrentRow(0);
    }
    if (list_->count() > 0 && onPreview && !filter.isEmpty()) {
        onPreview(items_.value(list_->item(0)->data(kIndexRole).toInt()).data);
    }
}

void QuickPick::accept() {
    QListWidgetItem* item = list_->currentItem();
    if (!item) {
        cancel();
        return;
    }
    const QVariant data = items_.value(item->data(kIndexRole).toInt()).data;
    closing_ = true;
    hide();
    if (onAccepted) {
        onAccepted(data);
    }
}

void QuickPick::cancel() {
    if (closing_ || !isVisible()) {
        return;
    }
    closing_ = true;
    hide();
    if (onCanceled) {
        onCanceled();
    }
}

bool QuickPick::eventFilter(QObject* watched, QEvent* event) {
    if (watched == input_ && event->type() == QEvent::KeyPress) {
        auto key = static_cast<QKeyEvent*>(event);
        const int row = list_->currentRow();
        switch (key->key()) {
        case Qt::Key_Down:
            list_->setCurrentRow(qMin(list_->count() - 1, row + 1));
            return true;
        case Qt::Key_Up:
            list_->setCurrentRow(qMax(0, row - 1));
            return true;
        case Qt::Key_PageDown:
            list_->setCurrentRow(qMin(list_->count() - 1, row + 10));
            return true;
        case Qt::Key_PageUp:
            list_->setCurrentRow(qMax(0, row - 10));
            return true;
        case Qt::Key_Return:
        case Qt::Key_Enter:
            accept();
            return true;
        case Qt::Key_Escape:
            cancel();
            return true;
        default:
            break;
        }
    }
    if (watched == input_ && event->type() == QEvent::ShortcutOverride) {
        // Esc・Enter・矢印をMayaやメニューのショートカットへ渡さない。
        auto key = static_cast<QKeyEvent*>(event);
        if (key->key() == Qt::Key_Escape || key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter
            || key->key() == Qt::Key_Up || key->key() == Qt::Key_Down) {
            event->accept();
            return true;
        }
    }
    if (watched == input_ && event->type() == QEvent::FocusOut) {
        // 一覧のクリック以外でフォーカスが外れたら閉じる。
        QWidget* focus = QApplication::focusWidget();
        if (!focus || !isAncestorOf(focus)) {
            cancel();
        }
    }
    return QFrame::eventFilter(watched, event);
}

}  // namespace hedit
