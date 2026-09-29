/** @file explorer.cpp
 * @brief Explorerの実装。
 * @details 項目のデータの使い方:
 * - Qt::UserRole     : その項目のファイル/フォルダーの絶対パス。
 * - Qt::UserRole + 1 : trueなら「まだ中身を読んでいないフォルダー」。展開時に読む。
 * 未読のフォルダーには、展開の矢印を出すための仮の子「…」を入れておく。
 */
#include "editor/explorer.h"
#include "editor/ui_scale.h"
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QPushButton>
#include <QStyle>
#include <QTreeWidget>
#include <QVBoxLayout>

namespace hedit {
namespace {

constexpr int kPathRole = Qt::UserRole;             ///< 絶対パスを入れる場所。
constexpr int kNotLoadedRole = Qt::UserRole + 1;    ///< 未読のフォルダーの印を入れる場所。

/** @brief 未読のフォルダーの印と、展開の矢印を出すための仮の子を付ける。
 * @param item フォルダーの項目。
 */
void markNotLoaded(QTreeWidgetItem* item) {
    item->setData(0, kNotLoadedRole, true);
    new QTreeWidgetItem(item, {"…"});  // 親の項目が所有する。
}

}  // namespace

Explorer::Explorer(QWidget* parent) : QWidget(parent) {
    auto layout = new QVBoxLayout(this);
    layout->setContentsMargins(scaled(3), scaled(3), scaled(3), scaled(3));

    auto buttons = new QHBoxLayout;
    auto openButton = new QPushButton("Open folder");
    auto addButton = new QPushButton("Add folder");
    auto removeButton = new QPushButton("Remove");
    buttons->addWidget(openButton);
    buttons->addWidget(addButton);
    buttons->addWidget(removeButton);
    layout->addLayout(buttons);

    tree_ = new QTreeWidget(this);
    tree_->setObjectName("explorerTree");
    tree_->setHeaderHidden(true);
    // フォルダー/ファイルのアイコンもMayaの拡大率に合わせる(文字はMaya全体の文字で拡大済み)。
    tree_->setIconSize(QSize(scaled(16), scaled(16)));
    layout->addWidget(tree_);
    openEditors_ = new QTreeWidgetItem(tree_, {"OPEN EDITORS"});
    openEditors_->setExpanded(true);

    connect(openButton, &QPushButton::clicked, this, [this] {
        addFolder(QFileDialog::getExistingDirectory(this, "Open folder"), true);
    });
    connect(addButton, &QPushButton::clicked, this, [this] {
        addFolder(QFileDialog::getExistingDirectory(this, "Add folder"));
    });
    connect(removeButton, &QPushButton::clicked, this, [this] {
        // 取り除けるのはルートフォルダーだけ(OPEN EDITORSや子の項目は対象外)。
        QTreeWidgetItem* item = tree_->currentItem();
        if (!item || item == openEditors_ || item->parent()) {
            return;
        }
        folders_.removeAll(item->data(0, kPathRole).toString());
        delete item;
    });
    connect(tree_, &QTreeWidget::itemExpanded, this, [this](QTreeWidgetItem* item) { populate(item); });
    connect(tree_, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item, int) {
        const QString path = item->data(0, kPathRole).toString();
        if (QFileInfo(path).isFile() && onFileActivated) {
            onFileActivated(path);
        }
    });
}

void Explorer::populate(QTreeWidgetItem* item) {
    if (!item->data(0, kNotLoadedRole).toBool()) {
        return;  // 読み込み済み。
    }
    item->setData(0, kNotLoadedRole, false);
    qDeleteAll(item->takeChildren());  // 仮の子「…」を消す。

    const QDir directory(item->data(0, kPathRole).toString());
    const auto entries = directory.entryInfoList(QDir::AllDirs | QDir::Files | QDir::NoDotAndDotDot,
                                                 QDir::DirsFirst | QDir::Name);
    for (const QFileInfo& info : entries) {
        if (info.isSymLink()) {
            continue;
        }
        const QString suffix = info.suffix().toLower();
        if (!info.isDir() && suffix != "py" && suffix != "mel") {
            continue;  // スクリプト以外のファイルは出さない。
        }
        if (info.isDir() && (info.fileName() == "__pycache__" || info.fileName() == ".git")) {
            continue;
        }
        auto child = new QTreeWidgetItem(item, {info.fileName()});
        child->setData(0, kPathRole, info.absoluteFilePath());
        child->setIcon(0, style()->standardIcon(info.isDir() ? QStyle::SP_DirIcon : QStyle::SP_FileIcon));
        child->setToolTip(0, info.absoluteFilePath());
        if (info.isDir()) {
            markNotLoaded(child);
        }
    }
}

void Explorer::removeRootItems() {
    // 先頭(0番)はOPEN EDITORSなので残す。
    while (tree_->topLevelItemCount() > 1) {
        delete tree_->takeTopLevelItem(1);
    }
    folders_.clear();
}

void Explorer::addFolder(const QString& path, bool replace) {
    const QFileInfo info(path);
    if (path.isEmpty() || !info.isDir()) {
        return;
    }
    const QString canonical = info.canonicalFilePath();
    if (replace) {
        removeRootItems();
    }
    if (folders_.contains(canonical, Qt::CaseInsensitive)) {
        return;
    }
    folders_.append(canonical);
    const QString label = info.fileName().isEmpty() ? canonical : info.fileName();  // ドライブ直下は名前が空。
    auto item = new QTreeWidgetItem(tree_, {label});
    item->setData(0, kPathRole, canonical);
    item->setToolTip(0, canonical);
    item->setIcon(0, style()->standardIcon(QStyle::SP_DirIcon));
    markNotLoaded(item);
    item->setExpanded(true);
}

void Explorer::setRoots(const QStringList& paths) {
    removeRootItems();
    for (const QString& path : paths) {
        addFolder(path);
    }
}

void Explorer::setOpenFiles(const QStringList& paths) {
    qDeleteAll(openEditors_->takeChildren());
    for (const QString& path : paths) {
        auto item = new QTreeWidgetItem(openEditors_, {QFileInfo(path).fileName()});
        item->setData(0, kPathRole, path);
        item->setToolTip(0, path);
    }
}

}  // namespace hedit
