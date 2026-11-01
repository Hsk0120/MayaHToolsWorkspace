/** @file settled_tree.h @brief UIA照会へ入る前にQPEのツリー遅延レイアウトを確定する。 */
#pragma once
#include <QAbstractItemModel>
#include <QScopedValueRollback>
#include <QTreeView>
#include <QVector>

namespace qpe {
/** @brief Qtのセルstate()内で再配置・アクセシビリティ破棄が起きることを防ぐ。
 * @tparam Base QTreeViewまたはQTreeWidget。
 * @note Qt全体のアクセシビリティは変更しない。自分のビューだけで保留中の配置を消化する。
 */
template<class Base> class SettledTree : public Base {
public:
    /** @brief 所有者の下へ配置し、アイコン寸法変更も即時に確定する。 @param parent 所有者。 */
    explicit SettledTree(QWidget* parent = nullptr) : Base(parent) {
        QObject::connect(this, &QAbstractItemView::iconSizeChanged, this, [this] { settle(); });
        watchModel();
    }
    /** @brief 一つのスナップショット内の行更新をまとめ、UIAへ戻る前に一度だけ配置する。
     * @param update 同期的なモデル更新。イベントループを再入させないこと。
     * @note 行ごとの再配置は大量ファイルで二乗の処理量になるため、選択を保持した差分更新を一括で扱う。
     */
    template<class Function> void updateModel(Function update) {
        { QScopedValueRollback<bool> guard(batching_, true); update(); }
        settle();
    }
protected:
    /** @brief 表示・寸法・フォント変更後、UIAが次の照会を受ける前に配置する。
     * @param event Qtイベント。
     * @return 基底の処理結果。
     */
    bool event(QEvent* event) override {
        const bool result = Base::event(event); settle(); return result;
    }
    /** @brief スクロール領域経由のリサイズも同じ配置境界へ通す。
     * @param event ビューポートイベント。
     * @return 基底の処理結果。
     */
    bool viewportEvent(QEvent* event) override {
        const bool result = Base::viewportEvent(event); settle(); return result;
    }
    /** @brief 二重配置を避け、保留がある場合だけQt標準の配置を実行する。 */
    void settle() {
        if (settling_ || batching_) return;
        QScopedValueRollback<bool> guard(settling_, true);
        this->executeDelayedItemsLayout();
    }
    /** @brief Qt自身のビュー接続の後で、モデル変更による保留配置を消化する。 */
    void watchModel() {
        for (const auto& connection : connections_) QObject::disconnect(connection);
        connections_.clear(); auto* model = this->model(); if (!model) return;
        const auto finish = [this] { settle(); };
        connections_ << QObject::connect(model, &QAbstractItemModel::modelReset, this, finish)
                     << QObject::connect(model, &QAbstractItemModel::layoutChanged, this, finish)
                     << QObject::connect(model, &QAbstractItemModel::rowsInserted, this, finish)
                     << QObject::connect(model, &QAbstractItemModel::rowsRemoved, this, finish)
                     << QObject::connect(model, &QAbstractItemModel::columnsInserted, this, finish)
                     << QObject::connect(model, &QAbstractItemModel::columnsRemoved, this, finish);
    }
private:
    QVector<QMetaObject::Connection> connections_;
    bool settling_ = false;
    bool batching_ = false;
};
}
