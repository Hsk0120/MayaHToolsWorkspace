/** @file editor_tabs.h
 * @brief タブが多いときに、マウスホイールと矢印ボタンで移動できるタブ欄。
 */
#pragma once
#include <QTabBar>
#include <QTabWidget>

namespace hedit {

/** @brief スクロールボタン付きで、ホイール1段ごとに隣のタブを選ぶタブバー。 */
class ScrollTabBar : public QTabBar {
public:
    /** @brief スクロールボタン付きのタブバーを作る。
     * @param parent タブバーを所有する親。
     */
    explicit ScrollTabBar(QWidget* parent = nullptr);

protected:
    /** @brief ホイール1段で隣のタブを選び、そのタブを表示範囲へ入れる。
     * @param event ホイールの回転量。Qtが所有する。
     */
    void wheelEvent(QWheelEvent* event) override;
};

/** @brief ScrollTabBarを使うタブ欄。コード欄(CodeEditor)を1タブに1つ入れる。 */
class EditorTabs : public QTabWidget {
public:
    /** @brief タブ欄を作る。閉じるボタンとドラッグでの並べ替えを有効にする。
     * @param parent タブ欄を所有する親。
     */
    explicit EditorTabs(QWidget* parent = nullptr);
};

}  // namespace hedit
