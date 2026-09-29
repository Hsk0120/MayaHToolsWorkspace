/** @file editor_tabs.cpp
 * @brief ScrollTabBarとEditorTabsの実装。
 */
#include "editor/editor_tabs.h"
#include <QWheelEvent>

namespace hedit {

ScrollTabBar::ScrollTabBar(QWidget* parent) : QTabBar(parent) {
    setUsesScrollButtons(true);
    setExpanding(false);
    setElideMode(Qt::ElideNone);
}

void ScrollTabBar::wheelEvent(QWheelEvent* event) {
    // 縦のホイールを優先し、無ければ横(タッチパッドの横スクロール)を使う。
    int delta = event->angleDelta().y();
    if (delta == 0) {
        delta = event->angleDelta().x();
    }
    if (delta != 0 && count() > 0) {
        const int step = delta < 0 ? 1 : -1;
        setCurrentIndex(qBound(0, currentIndex() + step, count() - 1));
    }
    event->accept();
}

EditorTabs::EditorTabs(QWidget* parent) : QTabWidget(parent) {
    // setTabBarで渡したタブバーは、このタブ欄が所有する。
    setTabBar(new ScrollTabBar(this));
    setTabsClosable(true);
    setMovable(true);
}

}  // namespace hedit
