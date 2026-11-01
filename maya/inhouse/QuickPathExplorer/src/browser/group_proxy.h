/** @file group_proxy.h @brief 平坦なファイル一覧を複製せず、表示だけグループ化する。 */
#pragma once
#include <QAbstractProxyModel>
#include <QPersistentModelIndex>
#include <QJsonObject>
#include <QTimer>
#include <QVector>
namespace qpe {
/** @brief 元モデルの値を借用する2階層表示。見出しは選択/操作対象にならない。 */
class GroupProxy final : public QAbstractProxyModel {
public:
    /** @brief 親が所有する集約モデル。 @param parent Qt所有者。 */
    explicit GroupProxy(QObject* parent = nullptr);
    /** @brief 一覧変更通知を接続する。 @param model 借用する平坦なモデル。 */
    void setSourceModel(QAbstractItemModel* model) override;
    /** @brief 集約条件を変える。 @param mode 1拡張子/2日付/3場所/4タグ。 @param labels 保存ラベル。 */
    void configure(int mode, const QJsonObject& labels);
    /** @brief 元行へ変換する。 @param proxy 表示索引。 @return 見出しなら無効。 */
    QModelIndex mapToSource(const QModelIndex& proxy) const override;
    /** @brief 表示行へ変換する。 @param source 元索引。 @return 表示索引。 */
    QModelIndex mapFromSource(const QModelIndex& source) const override;
    /** @brief 見出し/子の索引を作る。 @param row 行。 @param column 列。 @param parent 親。 @return 索引。 */
    QModelIndex index(int row, int column, const QModelIndex& parent = {}) const override;
    /** @brief 子の見出しを返す。 @param child 子。 @return 親。 */
    QModelIndex parent(const QModelIndex& child) const override;
    /** @brief 見出し/子の件数。 @param parent 親。 @return 行数。 */
    int rowCount(const QModelIndex& parent = {}) const override;
    /** @brief 元と同じ列数。 @param parent 親。 @return 列数。 */
    int columnCount(const QModelIndex& parent = {}) const override;
    /** @brief 見出し以外は元データを返す。 @param index 索引。 @param role 用途。 @return 値。 */
    QVariant data(const QModelIndex& index, int role = Qt::DisplayRole) const override;
    /** @brief 列名を元モデルから借用する。 @param section 番号。 @param orientation 方向。 @param role 用途。 @return 値。 */
    QVariant headerData(int section, Qt::Orientation orientation, int role = Qt::DisplayRole) const override;
    /** @brief 見出しをファイル操作から除外する。 @param index 索引。 @return 操作権限。 */
    Qt::ItemFlags flags(const QModelIndex& index) const override;
    /** @brief グループ内の並びは元モデルのソートに従う。 @param column 列。 @param order 方向。 */
    void sort(int column, Qt::SortOrder order = Qt::AscendingOrder) override;
private:
    /** @brief 行の追加をまとめて見出しを再計算する。 */
    void rebuild();
    struct Group { QString name; QVector<QPersistentModelIndex> rows; };
    QVector<Group> groups_;
    QVector<QMetaObject::Connection> connections_;
    QTimer timer_;
    QJsonObject labels_;
    int mode_ = 1;
};
}
