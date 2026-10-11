/** @file explorer.cpp
 * @brief 標準Qt部品を使うC++試作。Qtの親子関係が全UI部品を所有する。
 */
#include "explorer.h"
#include <QColumnView>
#include <QFileSystemModel>
#include <QLineEdit>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QDesktopServices>
#include <QUrl>
#include <QDir>

/** @brief ファイルを自動実行せず、明示操作で開くブラウザー。 */
class Explorer final : public QWidget {
public:
    /** @brief UIと非同期ファイルモデルを初期化する。
     * @param parent Qt所有者。
     */
    explicit Explorer(QWidget* parent) : QWidget(parent) {
        setObjectName("qpeExplorer");
        setWindowTitle("QuickPathExplorer — C++ prototype");
        resize(1100, 600);
        auto* layout = new QVBoxLayout(this);
        auto* toolbar = new QHBoxLayout;
        auto* up = new QPushButton("Up", this);
        auto* home = new QPushButton("Home", this);
        address = new QLineEdit(this); address->setObjectName("address");
        filter = new QLineEdit(this); filter->setObjectName("filter");
        filter->setPlaceholderText("Filter: *.ma *.mb"); filter->setMaximumWidth(220);
        toolbar->addWidget(up); toolbar->addWidget(home); toolbar->addWidget(address, 1); toolbar->addWidget(filter);
        layout->addLayout(toolbar);
        model = new QFileSystemModel(this); model->setObjectName("fileModel");
        model->setReadOnly(true);
        model->setOption(QFileSystemModel::DontUseCustomDirectoryIcons, true);
        model->setFilter(QDir::AllDirs | QDir::Files | QDir::NoDotAndDotDot);
        model->setNameFilterDisables(false);
        view = new QColumnView(this); view->setObjectName("columns");
        view->setModel(model); view->setColumnWidths({240,240,240,240});
        view->setSelectionMode(QAbstractItemView::SingleSelection);
        layout->addWidget(view, 1);
        info = new QLabel("Select a file or folder", this); info->setObjectName("info");
        info->setTextFormat(Qt::PlainText); info->setWordWrap(true); layout->addWidget(info);
        auto* open = new QPushButton("Open with default application", this); layout->addWidget(open);
        // thisをコンテキストにし、画面破棄時に接続を解除する。列の展開はQt標準に委ねる。
        connect(address, &QLineEdit::returnPressed, this, [this] { navigate(address->text()); });
        connect(up, &QPushButton::clicked, this, [this] { QDir dir(model->filePath(view->rootIndex())); dir.cdUp(); navigate(dir.path()); });
        connect(home, &QPushButton::clicked, this, [this] { navigate(QDir::homePath()); });
        connect(filter, &QLineEdit::textChanged, this, [this](const QString& text) { model->setNameFilters(text.split(' ', Qt::SkipEmptyParts)); });
        connect(view->selectionModel(), &QItemSelectionModel::currentChanged, this, [this](const QModelIndex& index) {
            const auto file = model->fileInfo(index);
            info->setText(file.absoluteFilePath() + (file.isDir() ? "  [folder]" : QString("  [%1 bytes]").arg(file.size())));
        });
        connect(open, &QPushButton::clicked, this, [this] {
            const auto index = view->currentIndex();
            if (index.isValid()) QDesktopServices::openUrl(QUrl::fromLocalFile(model->filePath(index)));
        });
    }
private:
    /** @brief 指定場所をカラムの起点にする。無効なパスでは現在表示を保つ。
     * @param path 移動先フォルダー。
     */
    void navigate(const QString& path) {
        if (!QFileInfo(path).isDir()) { info->setText("Folder not found: " + path); return; }
        const auto index = model->setRootPath(QDir(path).absolutePath());
        view->setRootIndex(index); address->setText(model->filePath(index));
    }
    QFileSystemModel* model;
    QColumnView* view;
    QLineEdit* address;
    QLineEdit* filter;
    QLabel* info;
};

QWidget* qpeCreate(QWidget* parent) { return new Explorer(parent); }
