/** @file outline_panel.h
 * @brief アウトライン(選択中のタブのクラス・関数・変数の木)。項目をクリックするとその行へ移動する。
 */
#pragma once
#include "core/code_outline.h"
#include <QTreeWidget>
#include <functional>

namespace hedit {

/** @brief アウトラインの木(objectNameは``outline``)。左のドック(OUTLINE)に入れる。 */
class OutlinePanel : public QTreeWidget {
public:
    /** @brief 木を作る。 @param parent 所有者。 */
    explicit OutlinePanel(QWidget* parent = nullptr);

    /** @brief 構成を表示し直す。開閉の状態は、同じ名前の項目について保つ。 @param outline 構成。 */
    void setOutline(const QList<OutlineEntry>& outline);

    /** @brief 行を含む項目を選ぶ(カーソルの位置を示す)。 @param line 行(0始まり)。 */
    void selectLine(int line);

    std::function<void(int line, int column)> onActivated;  ///< 項目がクリックされた(行と桁、0始まり)。

private:
    QList<OutlineEntry> outline_;  ///< 表示中の構成。
    bool selecting_ = false;       ///< selectLineで選んでいる最中か(クリックと区別する)。
};

}  // namespace hedit
