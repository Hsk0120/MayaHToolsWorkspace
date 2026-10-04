/** @file outline_panel.cpp
 * @brief OutlinePanelの実装。
 */
#include "editor/outline_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QHeaderView>
#include <QSet>
#include <QTreeWidgetItemIterator>

namespace hedit {
namespace {

/// 項目の行・桁を入れる役割。
constexpr int kLineRole = Qt::UserRole + 1;
constexpr int kColumnRole = Qt::UserRole + 2;

/** @brief 項目の種類に合わせた色。 @param kind OutlineEntry::kind。 @return 色。 */
QColor kindColor(const QString& kind) {
    if (kind == "class") {
        return QColor(theme::kSymbolClass);
    }
    if (kind == "variable") {
        return QColor(theme::kSymbolVariable);
    }
    return QColor(theme::kSymbolFunction);
}

/** @brief 項目の開閉の状態を覚えるための名前(``Class/method``)。 @param item 項目。 @return 名前。 */
QString itemPath(const QTreeWidgetItem* item) {
    QString path;
    for (const QTreeWidgetItem* current = item; current; current = current->parent()) {
        path = current->text(0) + "/" + path;
    }
    return path;
}

}  // namespace

OutlinePanel::OutlinePanel(QWidget* parent) : QTreeWidget(parent) {
    setObjectName("outline");
    setHeaderHidden(true);
    setColumnCount(2);
    header()->setStretchLastSection(true);
    setIndentation(scaled(14));
    setUniformRowHeights(true);
    setStyleSheet(QString("QTreeWidget{background:%1;color:%2;border:0;}").arg(theme::kBackground, theme::kText));
    connect(this, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem* item) {
        if (!selecting_ && onActivated) {
            onActivated(item->data(0, kLineRole).toInt(), item->data(0, kColumnRole).toInt());
        }
    });
}

void OutlinePanel::setOutline(const QList<OutlineEntry>& outline) {
    if (outline.size() == outline_.size()) {
        bool same = true;
        for (int i = 0; i < outline.size() && same; ++i) {
            same = outline[i].name == outline_[i].name && outline[i].line == outline_[i].line
                   && outline[i].parent == outline_[i].parent && outline[i].kind == outline_[i].kind;
        }
        if (same) {
            return;  // 変わっていなければ作り直さない(選択とスクロールの位置を保つ)。
        }
    }
    // 閉じていた項目を覚えておき、作り直した後も閉じたままにする。
    QSet<QString> collapsed;
    for (QTreeWidgetItemIterator it(this); *it; ++it) {
        if ((*it)->childCount() > 0 && !(*it)->isExpanded()) {
            collapsed.insert(itemPath(*it));
        }
    }
    outline_ = outline;
    clear();
    QList<QTreeWidgetItem*> items;
    for (const OutlineEntry& entry : outline_) {
        QTreeWidgetItem* parentItem = entry.parent >= 0 && entry.parent < items.size() ? items[entry.parent] : nullptr;
        auto item = parentItem ? new QTreeWidgetItem(parentItem) : new QTreeWidgetItem(this);
        item->setText(0, entry.name);
        item->setText(1, entry.kind == "variable" ? QString() : QString::number(entry.line + 1));
        item->setForeground(0, kindColor(entry.kind));
        item->setForeground(1, QColor(theme::kLineNumber));
        item->setToolTip(0, entry.detail.isEmpty() ? entry.name : entry.detail);
        item->setData(0, kLineRole, entry.line);
        item->setData(0, kColumnRole, entry.column);
        items.append(item);
    }
    expandAll();
    for (QTreeWidgetItemIterator it(this); *it; ++it) {
        if (collapsed.contains(itemPath(*it))) {
            (*it)->setExpanded(false);
        }
    }
    resizeColumnToContents(1);
}

void OutlinePanel::selectLine(int line) {
    const int index = enclosingOutlineEntry(outline_, line);
    QTreeWidgetItem* found = nullptr;
    int position = 0;
    for (QTreeWidgetItemIterator it(this); *it; ++it, ++position) {
        if (position == index) {
            found = *it;
            break;
        }
    }
    selecting_ = true;
    if (found) {
        setCurrentItem(found);
        scrollToItem(found);
    } else {
        clearSelection();
    }
    selecting_ = false;
}

}  // namespace hedit
