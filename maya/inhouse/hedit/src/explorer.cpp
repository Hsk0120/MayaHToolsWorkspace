/** @file explorer.cpp
 * @brief Explorerの遅延列挙と、ディスクを変更しない表示操作。
 */
#include "explorer.h"
#include <QTreeWidget>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QFileDialog>
#include <QFileInfo>
#include <QDir>
#include <QStyle>

namespace hedit {
Explorer::Explorer(QWidget* parent) : QWidget(parent) {
    auto layout=new QVBoxLayout(this); layout->setContentsMargins(3,3,3,3);
    auto buttons=new QHBoxLayout;
    auto open=new QPushButton("Open folder"); auto add=new QPushButton("Add folder");
    auto remove=new QPushButton("Remove");
    buttons->addWidget(open); buttons->addWidget(add); buttons->addWidget(remove); layout->addLayout(buttons);
    tree=new QTreeWidget(this); tree->setObjectName("explorerTree"); tree->setHeaderHidden(true);
    layout->addWidget(tree); opened=new QTreeWidgetItem(tree,{"OPEN EDITORS"}); opened->setExpanded(true);
    connect(open,&QPushButton::clicked,this,[this]{ addFolder(QFileDialog::getExistingDirectory(this,"Open folder"),true); });
    connect(add,&QPushButton::clicked,this,[this]{ addFolder(QFileDialog::getExistingDirectory(this,"Add folder")); });
    connect(remove,&QPushButton::clicked,this,[this]{
        auto item=tree->currentItem(); if (!item || item==opened || item->parent()) return;
        folders.removeAll(item->data(0,Qt::UserRole).toString()); delete item;
    });
    connect(tree,&QTreeWidget::itemExpanded,this,[this](QTreeWidgetItem* item){ populate(item); });
    connect(tree,&QTreeWidget::itemDoubleClicked,this,[this](QTreeWidgetItem* item,int){
        auto path=item->data(0,Qt::UserRole).toString();
        if (QFileInfo(path).isFile() && openFile) openFile(path);
    });
}
void Explorer::populate(QTreeWidgetItem* item) {
    if (!item->data(0,Qt::UserRole+1).toBool()) return;
    item->setData(0,Qt::UserRole+1,false); qDeleteAll(item->takeChildren());
    const auto entries=QDir(item->data(0,Qt::UserRole).toString()).entryInfoList(QDir::AllDirs|QDir::Files|QDir::NoDotAndDotDot,QDir::DirsFirst|QDir::Name);
    for (const auto& info:entries) {
        if (info.isSymLink()) continue;
        if (!info.isDir() && info.suffix().toLower()!="py" && info.suffix().toLower()!="mel") continue;
        if (info.isDir() && (info.fileName()=="__pycache__" || info.fileName()==".git")) continue;
        auto child=new QTreeWidgetItem(item,{info.fileName()}); child->setData(0,Qt::UserRole,info.absoluteFilePath());
        child->setIcon(0,style()->standardIcon(info.isDir()?QStyle::SP_DirIcon:QStyle::SP_FileIcon));
        child->setToolTip(0,info.absoluteFilePath());
        if (info.isDir()) { child->setData(0,Qt::UserRole+1,true); new QTreeWidgetItem(child,{"…"}); }
    }
}
void Explorer::addFolder(const QString& path,bool replace) {
    QFileInfo info(path); if (path.isEmpty() || !info.isDir()) return;
    auto canonical=info.canonicalFilePath();
    if (replace) { while(tree->topLevelItemCount()>1) delete tree->takeTopLevelItem(1); folders.clear(); }
    if (folders.contains(canonical,Qt::CaseInsensitive)) return;
    folders.append(canonical);
    auto item=new QTreeWidgetItem(tree,{info.fileName().isEmpty()?canonical:info.fileName()});
    item->setData(0,Qt::UserRole,canonical); item->setToolTip(0,canonical); item->setData(0,Qt::UserRole+1,true);
    item->setIcon(0,style()->standardIcon(QStyle::SP_DirIcon)); new QTreeWidgetItem(item,{"…"}); item->setExpanded(true);
}
QStringList Explorer::roots() const { return folders; }
void Explorer::setRoots(const QStringList& paths) {
    while(tree->topLevelItemCount()>1) delete tree->takeTopLevelItem(1);
    folders.clear(); for (const auto& path:paths) addFolder(path);
}
void Explorer::setOpenFiles(const QStringList& paths) {
    qDeleteAll(opened->takeChildren());
    for (const auto& path:paths) {
        auto item=new QTreeWidgetItem(opened,{QFileInfo(path).fileName()});
        item->setData(0,Qt::UserRole,path); item->setToolTip(0,path);
    }
}
}
