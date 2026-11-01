/** @file group_proxy.cpp @brief グループ化のためにファイルを再列挙しない表示アダプター。 */
#include "group_proxy.h"
#include <QFileInfo>
#include <QDir>
#include <QFont>
#include <QMap>
#include <QDateTime>
#include <QJsonArray>
namespace qpe {
GroupProxy::GroupProxy(QObject* parent) : QAbstractProxyModel(parent) {
    timer_.setSingleShot(true); timer_.setInterval(30);
    connect(&timer_, &QTimer::timeout, this, [this] { rebuild(); });
}
void GroupProxy::setSourceModel(QAbstractItemModel* model) {
    for (const auto& connection : connections_) disconnect(connection); connections_.clear();
    QAbstractProxyModel::setSourceModel(model);
    if (model) {
        const auto changed = [this] { timer_.start(); };
        connections_.append(connect(model, &QAbstractItemModel::modelReset, this, changed));
        connections_.append(connect(model, &QAbstractItemModel::layoutChanged, this, changed));
        connections_.append(connect(model, &QAbstractItemModel::rowsInserted, this, changed));
        connections_.append(connect(model, &QAbstractItemModel::rowsRemoved, this, changed));
        connections_.append(connect(model, &QAbstractItemModel::dataChanged, this, [this](const QModelIndex&, const QModelIndex&, const QVector<int>& roles) {
            if (roles.isEmpty() || roles.contains(Qt::DisplayRole) || roles.contains(Qt::UserRole + 1)) timer_.start();
        }));
    }
    rebuild();
}
void GroupProxy::configure(int mode, const QJsonObject& labels) { mode_ = qBound(1, mode, 4); labels_ = labels; rebuild(); }
void GroupProxy::rebuild() {
    timer_.stop(); QMap<QString, QVector<QPersistentModelIndex>> values;
    if (sourceModel()) for (int row = 0; row < sourceModel()->rowCount(); ++row) {
        const auto index = sourceModel()->index(row, 0); const auto path = index.data(Qt::UserRole + 1).toString(); if (path.isEmpty()) continue;
        const QFileInfo file(path); QString name;
        if (mode_ == 1) name = file.suffix().isEmpty() ? "No extension" : '.' + file.suffix().toLower();
        else if (mode_ == 2) name = sourceModel()->index(row, 3).data(Qt::UserRole + 3).toDateTime().date().toString(Qt::ISODate);
        else if (mode_ == 3) name = file.absolutePath();
        else { QStringList tags; for (const auto& tag : labels_[QDir::toNativeSeparators(path).toLower()].toObject()["tags"].toArray()) tags.append(tag.toString()); tags.sort(Qt::CaseInsensitive); name = tags.isEmpty() ? "No tags" : tags.join(", "); }
        values[name].append(index);
    }
    beginResetModel(); groups_.clear(); for (auto it = values.begin(); it != values.end(); ++it) groups_.append({it.key(), it.value()}); endResetModel();
}
QModelIndex GroupProxy::mapToSource(const QModelIndex& proxy) const {
    if (!proxy.isValid() || proxy.model() != this || !proxy.internalId()) return {};
    const int group = int(proxy.internalId()) - 1; if (group < 0 || group >= groups_.size() || proxy.row() >= groups_[group].rows.size()) return {};
    const auto source = groups_[group].rows[proxy.row()]; return source.isValid() ? source.sibling(source.row(), proxy.column()) : QModelIndex();
}
QModelIndex GroupProxy::mapFromSource(const QModelIndex& source) const {
    if (!source.isValid() || source.model() != sourceModel()) return {};
    for (int group = 0; group < groups_.size(); ++group) for (int row = 0; row < groups_[group].rows.size(); ++row)
        if (groups_[group].rows[row].row() == source.row() && groups_[group].rows[row].isValid()) return createIndex(row, source.column(), quintptr(group + 1));
    return {};
}
QModelIndex GroupProxy::index(int row, int column, const QModelIndex& parent) const {
    if (row < 0 || column < 0 || column >= columnCount() || row >= rowCount(parent)) return {};
    return createIndex(row, column, parent.isValid() ? quintptr(parent.row() + 1) : quintptr(0));
}
QModelIndex GroupProxy::parent(const QModelIndex& child) const { return child.isValid() && child.internalId() ? createIndex(int(child.internalId()) - 1, 0, quintptr(0)) : QModelIndex(); }
int GroupProxy::rowCount(const QModelIndex& parent) const {
    if (!parent.isValid()) return groups_.size();
    return parent.model() == this && !parent.internalId() && !parent.column() && parent.row() < groups_.size() ? groups_[parent.row()].rows.size() : 0;
}
int GroupProxy::columnCount(const QModelIndex&) const { return sourceModel() ? sourceModel()->columnCount() : 0; }
QVariant GroupProxy::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.model() != this) return {};
    if (index.internalId()) return mapToSource(index).data(role);
    if (index.row() >= groups_.size()) return {};
    if (role == Qt::DisplayRole && !index.column()) return groups_[index.row()].name + QString(" (%1)").arg(groups_[index.row()].rows.size());
    if (role == Qt::FontRole) { QFont font; font.setBold(true); return font; } return {};
}
QVariant GroupProxy::headerData(int section, Qt::Orientation orientation, int role) const { return sourceModel() ? sourceModel()->headerData(section, orientation, role) : QVariant(); }
Qt::ItemFlags GroupProxy::flags(const QModelIndex& index) const { if (!index.isValid()) return Qt::NoItemFlags; const auto source = mapToSource(index); return index.internalId() ? (source.isValid() ? sourceModel()->flags(source) : Qt::NoItemFlags) : Qt::ItemIsEnabled; }
void GroupProxy::sort(int column, Qt::SortOrder order) { if (sourceModel()) sourceModel()->sort(column, order); }
}
