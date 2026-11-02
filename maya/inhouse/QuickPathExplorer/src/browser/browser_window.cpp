/** @file browser_window.cpp
 * @brief 列ごとの選択/縦位置とタブごとの履歴を保持するネイティブUI。
 */
#include "browser_window.h"
#include "group_proxy.h"
#include "navigation_widgets.h"
#include "settled_tree.h"
#include "../core/directory_store.h"
#include "../native_browser.h"
#include "inspector.h"
#include "../core/media_query.h"
#include <QComboBox>
#include <QDate>
#include <QRegularExpression>
#include <QInputMethodEvent>
#include "../core/file_operations.h"
#include "../core/settings_store.h"
#include <QCloseEvent>
#include <QClipboard>
#include <QMimeData>
#include <QInputDialog>
#include <QFileDialog>
#include <QMessageBox>
#include <QJsonArray>
#include <QTreeWidgetItemIterator>
#include <stdexcept>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QCheckBox>
#include <QJsonDocument>
#include <QPushButton>
#include <QProgressBar>
#include <QCompleter>
#include <QStringListModel>
#include <QPointer>
#include <QSpinBox>
#include <QScopedValueRollback>
#include <QDrag>
#include <QDropEvent>
#include <QDragEnterEvent>
#include <QApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListView>
#include <QMenu>
#include <QPainter>
#include <QWheelEvent>
#include <QMouseEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QSettings>
#include <QShortcut>
#include <QSignalBlocker>
#include <QSortFilterProxyModel>
#include <QSplitter>
#include <QStackedWidget>
#include <QStandardItemModel>
#include <QStyledItemDelegate>
#include <QTabBar>
#include <QTextEdit>
#include <QTimer>
#include <QToolButton>
#include <QTreeView>
#include <QTreeWidget>
#include <QUrl>
#include <QUuid>
#include <QVBoxLayout>
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <shlobj.h>
#include <knownfolders.h>

namespace qpe {
namespace {
constexpr int PathRole = Qt::UserRole + 1;
constexpr int DirectoryRole = Qt::UserRole + 2;
constexpr int SortRole = Qt::UserRole + 3;
/** @brief 表示方式によらず、選択された名前列だけを取得する。
 * @param view 借用ビュー。
 * @return 実パスのある0列目の選択インデックス。
 * @note QListViewは多列モデルの0列目だけを選ぶためselectedRows()では空になる。
 */
QModelIndexList selectedPathIndexes(const QAbstractItemView* view) {
    QModelIndexList result;
    if (!view->selectionModel()) return result;
    for (const auto& index : view->selectionModel()->selectedIndexes())
        if (index.column() == 0 && !index.data(PathRole).toString().isEmpty()) result.append(index);
    return result;
}
/** @brief ファイルURLだけを転送するビュー。Qtの行移動では実ファイルを削除しない。
 * @tparam Base QListViewまたはQTreeView。
 */
template<class Base> class TransferView : public Base {
public:
    /** @brief 親が所有する転送ビューを作る。 @param parent 所有者。 */
    explicit TransferView(QWidget* parent) : Base(parent) {
        this->setDragEnabled(true); this->setAcceptDrops(true); this->setDropIndicatorShown(true);
        this->setDragDropMode(QAbstractItemView::DragDrop); this->setDefaultDropAction(Qt::CopyAction);
    }
    std::function<void(const QStringList&, const QString&, bool)> transfer;
    std::function<void(const QString&)> middleOpen;
    QString directory;
protected:
    /** @brief OSへ絶対ファイルURLだけを渡す。 @param actions Qt指定（コピーに限定）。 */
    void startDrag(Qt::DropActions actions) override {
        Q_UNUSED(actions);
        QList<QUrl> urls;
        for (const auto& index : selectedPathIndexes(this)) {
            const auto path = index.data(PathRole).toString();
            if (!path.isEmpty()) urls.append(QUrl::fromLocalFile(path));
        }
        if (urls.isEmpty()) return;
        auto* mime = new QMimeData; mime->setUrls(urls);
        QDrag drag(this); drag.setMimeData(mime); drag.exec(Qt::CopyAction, Qt::CopyAction);
    }
    /** @brief リモートURLや内部モデル専用MIMEを受け入れない。 @param event 入力。 */
    void dragEnterEvent(QDragEnterEvent* event) override { acceptFiles(event); }
    /** @brief 転送先が有効なフォルダーの時だけ受け入れる。 @param event 入力。 */
    void dragMoveEvent(QDragMoveEvent* event) override { acceptFiles(event); }
    /** @brief 対象を値で固定してファイルジョブへ渡す。 @param event 入力。 */
    void dropEvent(QDropEvent* event) override {
        if (!acceptFiles(event)) return;
        QStringList paths;
        for (const auto& url : event->mimeData()->urls()) paths.append(url.toLocalFile());
        const auto target = destination(event->pos());
        // 非同期処理の完了前に送信元へ削除を指示しない。Shift移動の削除はQPEの履歴エンジンだけが行う。
        const bool move = event->keyboardModifiers().testFlag(Qt::ShiftModifier);
        if (transfer) transfer(paths, target, move);
    }
    /** @brief 中クリックは関連付けファイル起動でなくフォルダータブ追加。 @param event 入力。 */
    void mouseReleaseEvent(QMouseEvent* event) override {
        if (event->button() == Qt::MiddleButton) {
            const auto index = this->indexAt(event->pos()); const auto path = index.sibling(index.row(), 0).data(PathRole).toString();
            if (!path.isEmpty() && QFileInfo(path).isDir() && middleOpen) middleOpen(path);
            event->accept(); return;
        }
        Base::mouseReleaseEvent(event);
    }
private:
    /** @brief 項目がフォルダーならその場所、それ以外は表示中の親。 @param pos ビュー内座標。 @return パス。 */
    QString destination(const QPoint& pos) const {
        const auto index = this->indexAt(pos); const auto item = index.sibling(index.row(), 0);
        return item.data(DirectoryRole).toBool() ? item.data(PathRole).toString() : directory;
    }
    /** @brief 同期削除を伴わないCopy応答で受理する。 @param event 入力。 @return 受理したか。 */
    bool acceptFiles(QDropEvent* event) {
        bool valid = event->mimeData()->hasUrls() && !event->mimeData()->urls().isEmpty() && !destination(event->pos()).isEmpty();
        for (const auto& url : event->mimeData()->urls()) valid = valid && url.isLocalFile();
        if (!valid || !event->possibleActions().testFlag(Qt::CopyAction)) { event->ignore(); return false; }
        event->setDropAction(Qt::CopyAction); event->accept(); return true;
    }
};
/** @brief 列の右端だけで幅を変更する。ファイル選択やドラッグ転送とは分離する。 */
class ColumnGrip final : public QWidget {
public:
    /** @brief 所有する列へ操作を返す。 @param parent 列。 */
    explicit ColumnGrip(QWidget* parent) : QWidget(parent) { setCursor(Qt::SplitHCursor); setObjectName("columnGrip"); setToolTip("Drag to resize; double-click to fit folder names"); }
    std::function<void(int)> changed;
protected:
    /** @brief 押下位置と列幅を保持する。 @param event 入力。 */
    void mousePressEvent(QMouseEvent* event) override { if (event->button() != Qt::LeftButton) return; origin_ = event->globalPos().x(); width_ = parentWidget()->width(); dragging_ = true; event->accept(); }
    /** @brief 画面座標の差でリサイズ中の列移動に影響されない。 @param event 入力。 */
    void mouseMoveEvent(QMouseEvent* event) override { if (dragging_ && changed) changed(width_ + event->globalPos().x() - origin_); event->accept(); }
    /** @brief マウス捕捉を終了する。 @param event 入力。 */
    void mouseReleaseEvent(QMouseEvent* event) override { dragging_ = false; event->accept(); }
    /** @brief 自動幅へ戻す。 @param event 入力。 */
    void mouseDoubleClickEvent(QMouseEvent* event) override { if (event->button() == Qt::LeftButton && changed) changed(0); dragging_ = false; event->accept(); }
private:
    int origin_ = 0, width_ = 0;
    bool dragging_ = false;
};
/** @brief このビューの上下端でもホイールを消費し、祖先/Mayaへ伝播させない。 */
class FolderList final : public TransferView<QListView> {
public:
    /** @brief 親が所有するリストを作る。
     * @param parent 所有者。
     */
    explicit FolderList(QWidget* parent) : TransferView(parent) { setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff); }
    /** @brief カラムだけに境界グリップを設ける。 @param callback 幅、0は自動復帰。 */
    void enableResize(std::function<void(int)> callback) { grip_ = new ColumnGrip(this); grip_->changed = std::move(callback); setViewportMargins(0, 0, 5, 0); grip_->show(); }
protected:
    /** @brief スクロールバーの外側へグリップを配置する。 @param event 寸法変更。 */
    void resizeEvent(QResizeEvent* event) override { QListView::resizeEvent(event); if (grip_) { grip_->setGeometry(width() - 5, 0, 5, height()); grip_->raise(); QTimer::singleShot(0, grip_, [this] { grip_->raise(); }); } }
    /** @brief 標準スクロール後の余剰入力を消費する。
     * @param event ホイール入力。
     */
    void wheelEvent(QWheelEvent* event) override { QListView::wheelEvent(event); event->accept(); }
    /** @brief 右クリックでは既存選択を変えない。
     * @param event マウス入力。
     */
    void mousePressEvent(QMouseEvent* event) override {
        if (event->button() == Qt::RightButton) { event->accept(); return; }
        QListView::mousePressEvent(event);
    }
private:
    ColumnGrip* grip_ = nullptr;
};
/** @brief ファイル一覧の右クリックで選択を保存する。 */
class FileTree final : public TransferView<SettledTree<QTreeView>> {
public:
    /** @brief 親所有のビューを作る。
     * @param parent 所有者。
     */
    explicit FileTree(QWidget* parent = nullptr) : TransferView(parent) {}
    /** @brief モデル切替後の遅延配置をUIA照会前に確定する。 @param model 借用モデル。 */
    void setModel(QAbstractItemModel* model) override { QTreeView::setModel(model); watchModel(); settle(); }
protected:
    /** @brief 選択外メニューも既存選択を保持する。
     * @param event マウス入力。
     */
    void mousePressEvent(QMouseEvent* event) override {
        if (event->button() == Qt::RightButton) { event->accept(); return; }
        QTreeView::mousePressEvent(event);
    }
    /** @brief 末尾の余剰ホイールを背後へ伝えない。
     * @param event 入力。
     */
    void wheelEvent(QWheelEvent* event) override { QTreeView::wheelEvent(event); event->accept(); }
};
/** @brief フォルダー名の左アイコンと右端の子階層矢印を描く。 */
class FolderDelegate final : public QStyledItemDelegate {
public:
    /** @brief ビューが所有する。
     * @param parent 所有者。
     */
    explicit FolderDelegate(QObject* parent) : QStyledItemDelegate(parent) {}
    /** @brief 文字と矢印の領域を分けて描く。
     * @param painter 描画先。
     * @param option 項目位置。
     * @param index 対象。
     */
    void paint(QPainter* painter, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        auto content = option;
        content.rect.adjust(0, 0, -16, 0);
        QStyledItemDelegate::paint(painter, content, index);
        painter->save();
        painter->setPen(option.palette.text().color());
        const QPoint center(option.rect.right() - 8, option.rect.center().y());
        painter->drawLine(center + QPoint(-2, -4), center + QPoint(2, 0));
        painter->drawLine(center + QPoint(2, 0), center + QPoint(-2, 4));
        painter->restore();
    }
    /** @brief フォントに応じた行高を返す。
     * @param option フォント。
     * @param index 項目。
     * @return 行の必要寸法。
     */
    QSize sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        auto size = QStyledItemDelegate::sizeHint(option, index);
        size.setHeight(qMax(parent()->property("qpeRowHeight").toInt(), option.fontMetrics.height() + 8));
        return size;
    }
};
/** @brief 空モデルの初回投入を一回のreset通知にまとめる。既存行の差分更新には使用しない。 */
class SnapshotItemModel final : public QStandardItemModel {
public:
    /** @brief Qt所有者を指定する。 @param parent 所有するページまたはビュー。 */
    explicit SnapshotItemModel(QObject* parent) : QStandardItemModel(parent) {}
    /** @brief 空モデルの投入開始を通知し、セル単位のシグナルを抑える。 */
    void beginInitialFill() { beginResetModel(); previousBlocked_ = blockSignals(true); }
    /** @brief プロキシとビューへ完成済みの行集合を一度だけ通知する。 */
    void endInitialFill() { blockSignals(previousBlocked_); endResetModel(); }
private:
    bool previousBlocked_ = false;
};
/** @brief 既存行を識別子で維持し、選択やShell結果を不用意に失効させない。
 * @param model 更新対象。
 * @param path 親ディレクトリ。
 * @param snapshot 新しい値。
 * @param folders フォルダー専用か。
 */
void applyRows(QStandardItemModel* model, const QString& path, const DirectorySnapshot& snapshot, bool folders, bool includeFolders = false) {
    auto* initial = model->rowCount() == 0 ? dynamic_cast<SnapshotItemModel*>(model) : nullptr;
    if (initial) initial->beginInitialFill();
    const QIcon folder = nativeFolderIcon();
    const QIcon file = QApplication::style()->standardIcon(QStyle::SP_FileIcon);
    QSet<QString> names;
    for (const auto& entry : snapshot.entries) if (entry.directory == folders || (!folders && includeFolders)) names.insert(entry.name);
    for (int row = model->rowCount() - 1; row >= 0; --row)
        if (!names.contains(model->item(row)->text())) model->removeRow(row);
    int row = 0;
    for (const auto& entry : snapshot.entries) {
        if (entry.directory != folders && !(!folders && includeFolders)) continue;
        const QString full = QDir(path).filePath(entry.name);
        QStandardItem* item = row < model->rowCount() ? model->item(row) : nullptr;
        if (!item || item->text() != entry.name) {
            QList<QStandardItem*> cells;
            for (int col = 0; col < 4; ++col) {
                auto* cell = new QStandardItem;
                cell->setEditable(false);
                cells.append(cell);
            }
            item = cells[0];
            item->setText(entry.name);
            item->setIcon(entry.directory ? folder : file);
            item->setData(entry.name, SortRole);
            item->setData(full, PathRole);
            item->setData(entry.directory, DirectoryRole);
            item->setToolTip(full);
            model->insertRow(row, cells);
        }
        const QString suffix = QFileInfo(entry.name).suffix();
        const QVariant values[] = {entry.size, suffix.isEmpty() ? QString() : "." + suffix, entry.modified};
        for (int col = 1; col < 4; ++col) {
            auto* cell = model->item(row, col);
            if (cell->data(SortRole) == values[col - 1]) continue;
            cell->setData(values[col - 1], SortRole);
            cell->setData(col == 1 ? QVariant(QLocale().formattedDataSize(entry.size))
                : col == 3 ? QVariant(QLocale().toString(entry.modified, QLocale::ShortFormat)) : values[col - 1], Qt::DisplayRole);
        }
        ++row;
    }
    if (initial) initial->endInitialFill();
}
/** @brief アイコンを持つ操作ボタンを作る。
 * @param layout 配置先。
 * @param name アクセシビリティ名。
 * @param icon リソースのファイル名。
 * @return 親レイアウトのウィジェットが所有するボタン。
 */
QToolButton* tool(QHBoxLayout* layout, const QString& name, const QString& icon = {}) {
    auto* button = new QToolButton;
    button->setText(name);
    button->setToolTip(name);
    button->setAccessibleName(name);
    if (!icon.isEmpty()) { button->setProperty("qpeSourceIcon", icon); button->setIcon(QIcon(":/qpe/icons/" + icon)); }
    layout->addWidget(button);
    return button;
}
}

/** @brief 1タブの列挙、履歴、カラム、ファイル表示をまとめて所有する。 */
class BrowserPage final : public QWidget {
    Q_OBJECT
public:
    /** @brief 非アクティブタブでも表示状態を保持する。
     * @param parent Qt所有者。
     */
    explicit BrowserPage(QWidget* parent, BrowserWindow* owner) : QWidget(parent), store_(this), owner_(owner) {
        setObjectName("browserPage");
        auto* layout = new QVBoxLayout(this);
        layout->setContentsMargins(0, 0, 0, 0);
        layout->setSpacing(4);
        auto* vertical = vertical_ = new QSplitter(Qt::Vertical, this);
        vertical->setObjectName("browserVertical");
        vertical->setChildrenCollapsible(false);
        connect(vertical, &QSplitter::splitterMoved, this, [this] { areaMode_ = "custom"; emit layoutChanged(); });
        scroll_ = new QScrollArea(vertical);
        scroll_->setObjectName("folderColumns");
        scroll_->setWidgetResizable(true);
        scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        auto* columns = new QWidget;
        columns->setObjectName("columnContainer");
        columnLayout_ = new QHBoxLayout(columns);
        columnLayout_->setContentsMargins(0, 0, 0, 0);
        columnLayout_->setSpacing(0);
        columnLayout_->addStretch(1);
        scroll_->setWidget(columns);
        auto* bottom = new QWidget(vertical);
        auto* lower = new QVBoxLayout(bottom);
        lower->setContentsMargins(0, 0, 0, 0);
        auto* filterRow = new QHBoxLayout;
        summary_ = new QLabel;
        filterRow->addWidget(summary_);
        filter_ = new QLineEdit;
        filter_->setObjectName("fileFilter");
        filter_->setPlaceholderText("Filter file names…");
        filterRow->addWidget(filter_, 1);
        auto* types = new QComboBox; types->setObjectName("fileTypes");
        for (const auto& name : QStringList{"All files", "Maya scenes", "3D formats", "Images", "Videos", "Scripts", "FBX / OBJ"}) types->addItem(name);
        filterRow->addWidget(types);
        auto* viewButton = tool(filterRow, "View");
        connect(viewButton, &QToolButton::clicked, this, [this, viewButton] {
            QMenu menu;
            for (const auto& mode : QStringList{"Details", "Thumbnails", "Extended details"}) {
                auto* a = menu.addAction(mode, this, [this, mode] { setMode(mode); }); a->setCheckable(true); a->setChecked(mode_ == mode);
            }
            auto* folders = menu.addAction("Include subfolders"); folders->setCheckable(true); folders->setChecked(recursive_);
            connect(folders, &QAction::toggled, this, [this](bool value) { setRecursive(value); });
            auto* grouping = menu.addMenu("Group by");
            const QStringList names{"None", "Extension", "Date modified (by day)", "Location", "Tag"};
            for (int i = 0; i < names.size(); ++i) { auto* action = grouping->addAction(names[i]); action->setCheckable(true); action->setChecked(groupMode_ == i); connect(action, &QAction::triggered, this, [this, i] { setGrouping(i); saveFolderView(); }); }
            auto* tags = menu.addMenu("Filter by tag"); tags->addAction("All tags", this, [this] { setTagFilter({}); });
            QSet<QString> tagNames; const auto labels = readSettings()["fileLabels"].toObject(); for (auto it = labels.begin(); it != labels.end(); ++it) for (const auto& tag : it.value().toObject()["tags"].toArray()) tagNames.insert(tag.toString());
            auto ordered = tagNames.values(); ordered.sort(Qt::CaseInsensitive); for (const auto& tag : ordered) { auto* action = tags->addAction(tag, this, [this, tag] { setTagFilter(tag); }); action->setCheckable(true); action->setChecked(tagFilter_ == tag); }
            auto* columns = menu.addMenu("File list columns");
            for (int i = 1; i < model_->columnCount(); ++i) { auto* a = columns->addAction(model_->headerData(i, Qt::Horizontal).toString()); a->setCheckable(true); a->setChecked(!files_->isColumnHidden(i)); connect(a, &QAction::toggled, this, [this, i](bool visible) { files_->setColumnHidden(i, !visible); saveFolderView(); }); }
            menu.exec(viewButton->mapToGlobal(QPoint(0, viewButton->height())));
        });
        connect(types, qOverload<int>(&QComboBox::currentIndexChanged), this, [this](int index) {
            static const QList<QStringList> extensions{{}, {"ma", "mb"}, {"ma", "mb", "fbx", "abc", "obj", "usd", "usda", "usdc"}, {"png", "jpg", "jpeg", "tif", "tiff", "exr", "hdr", "bmp"}, {"mp4", "mov", "avi", "mkv"}, {"py", "mel", "json"}, {"fbx", "obj"}};
            extensions_ = extensions.value(index); proxy_->setProperty("extensions", extensions_); proxy_->invalidate(); scheduleThumbnails(); updateConditions();
        });
        lower->addLayout(filterRow);
        conditionBar_ = new QScrollArea; conditionBar_->setObjectName("activeConditions"); conditionBar_->setWidgetResizable(true); conditionBar_->setFrameShape(QFrame::NoFrame);
        conditionBar_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff); conditionBar_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded); conditionBar_->setFixedHeight(48); conditionBar_->hide();
        auto* conditionWidget = new QWidget; auto* conditionLayout = new QHBoxLayout(conditionWidget); conditionLayout->setContentsMargins(0, 0, 0, 0); conditionLayout->setSpacing(4);
        for (const auto& name : QStringList{"Name", "Type", "Subfolders", "Tag", "Group"}) { auto* chip = new QToolButton; chip->setObjectName("clearCondition" + name); conditionLayout->addWidget(chip); conditionButtons_.append(chip); chip->hide(); }
        conditionLayout->addStretch(); conditionBar_->setWidget(conditionWidget); lower->addWidget(conditionBar_);
        connect(conditionButtons_[0], &QToolButton::clicked, filter_, &QLineEdit::clear);
        connect(conditionButtons_[1], &QToolButton::clicked, types, [types] { types->setCurrentIndex(0); });
        connect(conditionButtons_[2], &QToolButton::clicked, this, [this] { setRecursive(false); });
        connect(conditionButtons_[3], &QToolButton::clicked, this, [this] { setTagFilter({}); });
        connect(conditionButtons_[4], &QToolButton::clicked, this, [this] { setGrouping(0); saveFolderView(); });
        files_ = new FileTree;
        files_->transfer = [this](const QStringList& paths, const QString& target, bool move) { owner_->perform(move ? "moveTo" : "copyTo", paths, target); };
        files_->middleOpen = [this](const QString& path) { owner_->addTab(path); };
        files_->setObjectName("files");
        files_->viewport()->installEventFilter(this);
        files_->setRootIsDecorated(false);
        files_->setAlternatingRowColors(true);
        files_->setUniformRowHeights(true);
        files_->setSelectionMode(QAbstractItemView::ExtendedSelection);
        files_->setEditTriggers(QAbstractItemView::NoEditTriggers);
        files_->setProperty("qpeRowHeight", owner_->property("qpeRowHeight").isValid() ? owner_->property("qpeRowHeight") : QVariant(24));
        model_ = new SnapshotItemModel(this);
        model_->setHorizontalHeaderLabels({"Name", "Size", "Extension", "Date modified"});
        proxy_ = qobject_cast<QSortFilterProxyModel*>(createNative("proxy", files_));
        proxy_->setSourceModel(model_);
        proxy_->setSortCaseSensitivity(Qt::CaseInsensitive);
        proxy_->setFilterCaseSensitivity(Qt::CaseInsensitive);
        groupProxy_ = new GroupProxy(this);
        connect(groupProxy_, &QAbstractItemModel::modelAboutToBeReset, this, [this] {
            if (files_->model() != groupProxy_) return; groupSelection_.clear(); groupScroll_ = files_->verticalScrollBar()->value();
            for (const auto& index : files_->selectionModel()->selectedRows()) { const auto path = index.data(PathRole).toString(); if (!path.isEmpty()) groupSelection_.append(path); }
        });
        connect(groupProxy_, &QAbstractItemModel::modelReset, this, [this] {
            if (files_->model() != groupProxy_) return; files_->expandAll();
            if (groupRestorePending_) { restorePosition(); if (ready_) groupRestorePending_ = false; }
            else { selectPaths(groupSelection_); files_->verticalScrollBar()->setValue(groupScroll_); }
        });
        files_->setModel(proxy_);
        files_->setItemDelegate(qobject_cast<QStyledItemDelegate*>(createNative("delegate", files_)));
        createNative("icons", files_);
        files_->setSortingEnabled(true);
        files_->sortByColumn(0, Qt::AscendingOrder);
        files_->header()->setStretchLastSection(false);
        files_->header()->setSectionResizeMode(0, QHeaderView::Interactive);
        files_->setColumnWidth(1, 90);
        files_->setColumnWidth(2, 85);
        files_->setColumnWidth(3, 150);
        folderViews_ = readSettings()["folderViews"].toObject();
        viewSaveTimer_ = new QTimer(this); viewSaveTimer_->setSingleShot(true); viewSaveTimer_->setInterval(350);
        connect(viewSaveTimer_, &QTimer::timeout, this, [this] { flushFolderViews(); });
        connect(files_->header(), &QHeaderView::sectionResized, this, [this](int column) { if (column > 0) { fitFileName(); saveFolderView(); } });
        connect(files_->header(), &QHeaderView::sortIndicatorChanged, this, [this] { saveFolderView(); });
        presentations_ = new QStackedWidget; lower->addWidget(presentations_, 1); presentations_->addWidget(files_);
        thumbnails_ = new FolderList(presentations_); thumbnails_->setObjectName("thumbnails"); thumbnails_->setViewMode(QListView::IconMode);
        thumbnails_->setItemDelegate(new QStyledItemDelegate(thumbnails_)); thumbnails_->setResizeMode(QListView::Adjust); thumbnails_->setMovement(QListView::Static);
        thumbnails_->setIconSize(QSize(144, 96)); thumbnails_->setGridSize(QSize(180, 136)); thumbnails_->setWordWrap(true); thumbnails_->setUniformItemSizes(true);
        thumbnails_->setSelectionMode(QAbstractItemView::ExtendedSelection); thumbnails_->setModel(proxy_); thumbnails_->setSelectionModel(files_->selectionModel());
        thumbnails_->transfer = files_->transfer; thumbnails_->middleOpen = files_->middleOpen; presentations_->addWidget(thumbnails_);
        installViewKeys(thumbnails_); thumbnails_->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(thumbnails_, &QWidget::customContextMenuRequested, this, [this](const QPoint& p) { owner_->contextMenu(thumbnails_, p, path_); });
        connect(thumbnails_, &QListView::doubleClicked, this, [this](const QModelIndex& i) { open(i.data(PathRole).toString()); });
        media_ = new FileJobs(this); mediaTimer_ = new QTimer(this); mediaTimer_->setSingleShot(true); mediaTimer_->setInterval(100);
        connect(mediaTimer_, &QTimer::timeout, this, &BrowserPage::requestThumbnails);
        connect(thumbnails_->verticalScrollBar(), &QScrollBar::valueChanged, this, [this] { scheduleThumbnails(); });
        connect(files_->verticalScrollBar(), &QScrollBar::valueChanged, this, [this] { scheduleThumbnails(); });
        connect(media_, &FileJobs::finished, this, [this](const QJsonObject& result) {
            const auto data = fileResultFromJson(result).extra; if (data["token"].toString() != thumbnailToken_) return;
            const auto path = data["path"].toString();
            if (mode_ == "Extended details" && data["width"].toInt() > 0) {
                for (int row = 0; row < model_->rowCount(); ++row) if (model_->item(row)->data(PathRole).toString() == path) {
                    auto* cell = new QStandardItem(QString("%1 × %2").arg(data["width"].toInt()).arg(data["height"].toInt()));
                    cell->setEditable(false); cell->setData(qint64(data["width"].toInt()) * data["height"].toInt(), SortRole); model_->setItem(row, 7, cell); break;
                }
            }
            if (data["png"].toString().isEmpty() || mode_ != "Thumbnails") return;
            QPixmap image; image.loadFromData(QByteArray::fromBase64(data["png"].toString().toLatin1()), "PNG");
            for (int row = 0; row < model_->rowCount(); ++row) if (model_->item(row)->data(PathRole).toString() == path) { model_->item(row)->setIcon(QIcon(image)); model_->item(row)->setData(true, Qt::UserRole + 20); break; }
        });
        recursiveJobs_ = new FileJobs(this);
        connect(recursiveJobs_, &FileJobs::finished, this, [this](const QJsonObject& value) {
            const auto result = fileResultFromJson(value);
            if (!recursive_ || result.extra["token"].toString() != recursiveToken_ || result.cancelled) return;
            DirectorySnapshot snapshot;
            for (const auto& raw : result.extra["rows"].toArray()) {
                const auto row = raw.toObject(); snapshot.entries.append({QDir(path_).relativeFilePath(row["path"].toString()), false, qint64(row["size"].toDouble()), QDateTime::fromString(row["modified"].toString(), Qt::ISODate), 0});
            }
            const bool sorting = files_->isSortingEnabled(); files_->setSortingEnabled(false);
            files_->updateModel([&] { applyRows(model_, path_, snapshot, false); }); files_->setSortingEnabled(sorting);
            model_->setProperty("snapshotGeneration", QVariant());
            ready_ = result.errors.isEmpty(); summary_->setText(QFileInfo(path_).fileName() + QString(" · %1 files (recursive)").arg(model_->rowCount()));
            footer_->setText(result.errors.isEmpty() ? QString("%1 items").arg(model_->rowCount()) : result.errors.join("\n"));
            restorePosition(); setMode(mode_); scheduleThumbnails();
        });
        layout->addWidget(vertical, 1);
        footer_ = new QLabel;
        footer_->setObjectName("footer");
        layout->addWidget(footer_);
        vertical->setSizes({360, 420});
        connect(filter_, &QLineEdit::textChanged, this, [this](const QString& text) { proxy_->setFilterFixedString(text); updateConditions(); });
        connect(files_, &QTreeView::doubleClicked, this, [this](const QModelIndex& index) { open(index.data(PathRole).toString()); });
        connect(files_->selectionModel(), &QItemSelectionModel::currentChanged, this, [this] { emit selected(detailPath()); });
        connect(files_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this] { fileSelectionChanged(); });
        connect(&store_, &DirectoryStore::changed, this, [this](const QString& path) { apply(path); });
        installViewKeys(files_);
        files_->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(files_, &QWidget::customContextMenuRequested, this, [this](const QPoint& position) { menu(files_, position); });
    }
    /** @brief タブを閉じても未反映の表示設定を保持する。 */
    ~BrowserPage() override { flushFolderViews(); }
    /** @brief 履歴を必要時だけ追加し、共通祖先列を再生成せず移動する。
     * @param input 移動先。
     * @param record 履歴へ追加するか。
     */
    void navigate(const QString& input, bool record = true) {
        if (input.trimmed().isEmpty()) return;
        pendingReveal_.clear();
        const QString destination = DirectoryStore::normalized(input);
        if (property("locationLocked").toBool() && !path_.isEmpty() && destination != path_) { owner_->addTab(destination); return; }
        savePosition(); saveFolderView();
        QScopedValueRollback<bool> viewGuard(viewRestoring_, true);
        if (record && (history_.isEmpty() || path_ != destination)) {
            history_ = history_.mid(0, historyIndex_ + 1);
            history_.append(destination);
            historyIndex_ = history_.size() - 1;
        }
        path_ = destination;
        files_->directory = path_; thumbnails_->directory = path_; thumbnails_->setProperty("path", path_); media_->cancel(); thumbnailRequests_.clear(); thumbnailToken_ = QUuid::createUuid().toString();
        recursiveJobs_->cancel(); recursiveToken_ = QUuid::createUuid().toString();
        ready_ = false;
        restorePending_ = true; groupRestorePending_ = true;
        QStringList chain{path_};
        QString ancestor = path_;
        while (ancestor.compare(startFolder_, Qt::CaseInsensitive) != 0) {
            const QString parent = QDir::cleanPath(QFileInfo(ancestor).absolutePath());
            if (parent == ancestor || parent.isEmpty()) break;
            chain.prepend(parent);
            ancestor = parent;
        }
        int common = 0;
        while (common < columns_.size() && common < chain.size() && columns_[common].path == chain[common]) ++common;
        while (columns_.size() > common) delete columns_.takeLast().view;
        for (int i = common; i < chain.size(); ++i) {
            auto* view = new FolderList(scroll_->widget());
            auto* model = new SnapshotItemModel(view);
            view->setModel(model);
            view->setItemDelegate(new FolderDelegate(view));
            view->setUniformItemSizes(true);
            view->setEditTriggers(QAbstractItemView::NoEditTriggers);
            view->setSelectionMode(QAbstractItemView::ExtendedSelection);
            view->setObjectName("folderColumn");
            const QString columnPath = chain[i];
            view->setProperty("path", columnPath);
            view->setProperty("qpeRowHeight", owner_->property("qpeRowHeight"));
            const auto scale = owner_->property("qpeUiScale").toDouble(); view->setIconSize(QSize(qRound(16 * scale), qRound(16 * scale)));
            view->enableResize([this, columnPath](int width) {
                if (width) manualWidths_[columnPath] = qBound(100, width, 1000); else manualWidths_.remove(columnPath);
                columnWidthMode_ = "names"; fitColumns();
                try { writeSettings({{"columnWidthMode", "names"}}); } catch (const std::exception& error) { footer_->setText(error.what()); }
            });
            view->directory = columnPath;
            view->transfer = files_->transfer; view->middleOpen = files_->middleOpen;
            view->setFixedWidth(160);
            columns_.append({columnPath, view, model});
            columnLayout_->insertWidget(columnLayout_->count() - 1, view);
            connect(view, &QListView::clicked, this, [this](const QModelIndex& index) { navigate(index.data(PathRole).toString()); });
            connect(view, &QListView::activated, this, [this](const QModelIndex& index) { navigate(index.data(PathRole).toString()); });
            connect(view->selectionModel(), &QItemSelectionModel::currentChanged, this, [this, view](const QModelIndex& index) {
                // 方向キー選択も同じ階層更新へ通す。モデル反映中の選択変更は除く。
                if (!applying_ && view->hasFocus() && index.isValid()) {
                    const QString target = index.data(PathRole).toString();
                    QTimer::singleShot(0, this, [this, target] { if (path_ != target) navigate(target); });
                }
            });
            view->setContextMenuPolicy(Qt::CustomContextMenu);
            connect(view, &QWidget::customContextMenuRequested, this, [this, view](const QPoint& pos) { menu(view, pos); });
            connect(view->verticalScrollBar(), &QScrollBar::valueChanged, this, [this, view] {
                // 読込完了より利用者のスクロールを優先し、遅れて選択行へ戻さない。
                if (!applying_ && !viewRestoring_) for (auto& column : columns_)
                    if (column.view == view) column.revealPath.clear();
            });
            installViewKeys(view);
        }
        for (int i = 0; i < columns_.size(); ++i) {
            auto& column = columns_[i];
            const auto target = i + 1 < chain.size() ? chain[i + 1] : QString();
            column.revealPath = !positions_.contains(path_) && column.view->currentIndex().data(PathRole).toString() != target
                ? target : QString();
        }
        store_.activate(chain);
        // 再訪時は既存モデルを再利用し、数千行の作り直しとShellアイコン再取得を避ける。
        if (!fileModels_.contains(path_)) {
            auto* model = new SnapshotItemModel(this);
            model->setHorizontalHeaderLabels({"Name", "Size", "Extension", "Date modified"});
            fileModels_[path_] = model;
            auto* proxy = qobject_cast<QSortFilterProxyModel*>(createNative("proxy", files_));
            proxy->setSortCaseSensitivity(Qt::CaseInsensitive);
            proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
            proxy->setProperty("qpeNativePresentation", true); proxy->setProperty("includeFolders", includeFolders_); proxy->setProperty("extensions", extensions_);
            proxy->setSourceModel(model);
            fileProxies_[path_] = proxy;
        }
        model_ = fileModels_[path_];
        if (proxy_ != fileProxies_[path_]) {
            proxy_ = fileProxies_[path_];
            attachModels();
        }
        fileRecency_.removeAll(path_);
        fileRecency_.append(path_);
        while (fileRecency_.size() > 16) {
            const QString expired = fileRecency_.takeFirst();
            delete fileProxies_.take(expired);
            delete fileModels_.take(expired);
        }
        restoreFolderView();
        for (const QString& p : chain) apply(p);
        if (!store_.snapshot(path_)) summary_->setText(QFileInfo(path_).fileName() + " · Loading…");
        filter_->setText(positions_.value(path_).filter);
        reveal_ = !positions_.contains(path_);
        restorePosition();
        fitColumns();
        emit locationChanged();
        if (recursive_) requestRecursive();
    }
    /** @brief 履歴内の前後へ移動する。
     * @param delta -1または1。
     */
    void history(int delta) {
        const int target = historyIndex_ + delta;
        if (target < 0 || target >= history_.size()) return;
        if (property("locationLocked").toBool()) { owner_->addTab(history_[target]); return; }
        historyIndex_ = target;
        navigate(history_[target], false);
    }
    /** @brief 親へ移動する。 */
    void up() { navigate(QFileInfo(path_).absolutePath()); }
    /** @brief 現在要求パスを返す。
     * @return パス。
     */
    QString path() const { return path_; }
    /** @brief 現在一覧の完了状態。
     * @return 正常完了か。
     */
    bool ready() const { return ready_; }
    /** @brief 履歴ボタンの可否。
     * @param delta 移動量。
     * @return 移動可能か。
     */
    bool canHistory(int delta) const { return historyIndex_ + delta >= 0 && historyIndex_ + delta < history_.size(); }
    /** @brief サイドバー開閉時だけ末尾を可視化する。非同期反映では追従しない。 */
    void revealCurrent() { reveal_ = true; fitColumns(); }
    /** @brief 検索等の明示操作で指定ファイルを選び、読込中ならこの場所でだけ待つ。 @param path 対象絶対パス。 */
    void revealFile(const QString& path) {
        const auto parent = DirectoryStore::normalized(QFileInfo(path).absolutePath());
        if (parent != path_) navigate(parent);
        if (parent != path_) return;
        filter_->clear(); findChild<QComboBox*>("fileTypes")->setCurrentIndex(0); setTagFilter({});
        pendingReveal_ = QDir::fromNativeSeparators(QFileInfo(path).absoluteFilePath());
        restorePending_ = false; applyReveal();
    }
    /** @brief 明示更新。 */
    void refresh() { for (const auto& column : columns_) store_.request(column.path); if (recursive_) requestRecursive(); }
    /** @brief 隠しファイル表示。 @param value 表示するか。 */
    void setHiddenFiles(bool value) { hiddenFiles_ = value; store_.setShowHidden(value); if (recursive_) requestRecursive(); }
    /** @brief タブの履歴と表示位置を独立したJSON値へ保存する。 @return 復元用の状態。 */
    QJsonObject state() {
        savePosition(); saveFolderView(); flushFolderViews(); QJsonObject positions;
        for (auto it = positions_.begin(); it != positions_.end(); ++it) {
            QJsonObject columns; for (auto col = it->columns.begin(); col != it->columns.end(); ++col) columns[col.key()] = col.value();
            positions[it.key()] = QJsonObject{{"horizontal", it->horizontal}, {"vertical", it->files}, {"search", it->filter},
                {"selected", QJsonArray::fromStringList(it->selected)}, {"columns", columns}};
        }
        return {{"path", path_}, {"history", QJsonArray::fromStringList(history_)}, {"index", historyIndex_}, {"positions", positions},
            {"areaMode", areaMode_}, {"areaSizes", QJsonArray{vertical_->sizes().value(0), vertical_->sizes().value(1)}},
            {"filter", findChild<QComboBox*>("fileTypes")->currentIndex()},
            {"filterKind", findChild<QComboBox*>("fileTypes")->currentText()},
            {"pinned", property("pinned").toBool()}, {"locked", property("locationLocked").toBool()},
            {"mode", mode_}, {"recursive", recursive_}, {"includeFolders", includeFolders_}, {"startFolder", startFolder_}, {"sortColumn", files_->header()->sortIndicatorSection()}, {"sortOrder", int(files_->header()->sortIndicatorOrder())}};
    }
    /** @brief ファイル変更開始前の選択を保持し、監視が先着しても改名対象を見失わない。 */
    void beginOperation() { operationState_ = state(); }
    /** @brief 新規タブへ継承する表示値だけを返す。ディスク保存や位置の全走査は行わない。 @return 起点・領域比率・フォルダー表示の値。 */
    QJsonObject newTabView() const {
        return {{"startFolder", startFolder_}, {"areaMode", areaMode_},
            {"areaSizes", QJsonArray{vertical_->sizes().value(0), vertical_->sizes().value(1)}},
            {"includeFolders", includeFolders_}};
    }
    /** @brief 既存タブの完成済み一覧を初期表示へ再利用する。状態・非同期世代・監視は独立させる。 @param source 複製元タブ。 */
    void primeFrom(const BrowserPage& source) { store_.primeCache(source.store_); }
    /** @brief 完了後に保持値を解放する。 */
    void endOperation() { operationState_ = {}; }
    /** @brief 実際に移動したパスだけを状態へ反映する。利用者の新しい選択は優先する。
     * @param from 旧パス。 @param to 新パス。
     */
    void remapOperation(const QString& from, const QString& to) {
        auto current = state();
        if (operationState_["path"].toString() == path_ && selection().isEmpty()) {
            auto positions = current["positions"].toObject(); auto position = positions[path_].toObject();
            const auto before = operationState_["positions"].toObject()[path_].toObject()["selected"].toArray();
            if (remapPaths(before, from, to) != before) { position["selected"] = before; positions[path_] = position; current["positions"] = positions; }
        }
        const auto changed = remapPaths(current, from, to).toObject();
        operationState_ = remapPaths(operationState_, from, to).toObject();
        if (changed != current) {
            const auto visibleAreas = vertical_->sizes();
            restoreState(changed);
            // 改名・移動は表示モードの再選択ではない。現に見えている上下比率を維持する。
            vertical_->setSizes(visibleAreas);
            // この時点のキャッシュは改名前の場合もある。完了後の再列挙まで選択復元を保持する。
            restorePending_ = true;
        }
    }
    /** @brief 復元中のnavigateで保存値を上書きしない。 @param state タブの値。 */
    void restoreState(const QJsonObject& state) {
        const auto target = state["path"].toString(); if (target.isEmpty()) return;
        path_.clear(); history_.clear(); positions_.clear(); setProperty("locationLocked", false);
        for (const auto& value : state["history"].toArray()) if (value.isString() && !value.toString().isEmpty()) history_.append(value.toString());
        historyIndex_ = qBound(0, state["index"].toInt(), qMax(0, history_.size() - 1));
        if (history_.isEmpty() || DirectoryStore::normalized(history_.value(historyIndex_)) != DirectoryStore::normalized(target)) { history_ = QStringList{target}; historyIndex_ = 0; }
        auto positions = state["positions"].toObject();
        if (positions.isEmpty() && (state.contains("columns") || state.contains("vertical") || state.contains("search") || state.contains("selected"))) {
            // Python版は列の位置を訪問先ごとにネストし、ファイル選択をタブ直下へ保存している。
            const auto oldColumns = state["columns"].toObject();
            for (auto old = oldColumns.begin(); old != oldColumns.end(); ++old) {
                const auto value = old.value().toObject(); if (!value["vertical"].isObject()) continue;
                positions[DirectoryStore::normalized(old.key())] = QJsonObject{{"horizontal", value["horizontal"]}, {"columns", value["vertical"]}};
            }
            const auto currentKey = DirectoryStore::normalized(target); auto current = positions[currentKey].toObject();
            for (const auto& key : {"vertical", "search", "selected"}) current[key] = state[key];
            positions[currentKey] = current;
        }
        for (auto it = positions.begin(); it != positions.end(); ++it) {
            const auto saved = it.value().toObject(); auto& value = positions_[DirectoryStore::normalized(it.key())];
            value.horizontal = qMax(0, saved["horizontal"].toInt()); value.files = qMax(0, saved["vertical"].toInt()); value.filter = saved["search"].toString();
            for (const auto& item : saved["selected"].toArray()) if (item.isString()) value.selected.append(item.toString());
            const auto columns = saved["columns"].toObject();
            for (auto col = columns.begin(); col != columns.end(); ++col) if (col.value().isDouble()) value.columns[DirectoryStore::normalized(col.key())] = qMax(0, col.value().toInt());
        }
        files_->sortByColumn(qBound(0, state["sortColumn"].toInt(), 3), state["sortOrder"].toInt() == 1 ? Qt::DescendingOrder : Qt::AscendingOrder);
        recursive_ = state["recursive"].toBool(); includeFolders_ = state["includeFolders"].toBool();
        const auto start = state["startFolder"].toString(state["root"].toString());
        startFolder_ = start.isEmpty() ? QString{} : DirectoryStore::normalized(start);
        // Python版の並び順と異なるため、旧番号は明示変換し新規保存は種別名を使う。
        auto* types = findChild<QComboBox*>("fileTypes");
        const int typeIndex = state.contains("filterKind") ? types->findText(state["filterKind"].toString()) : QList<int>{0, 1, 3, 6, 5}.value(state["filter"].toInt(), 0);
        types->setCurrentIndex(qBound(0, typeIndex, types->count() - 1));
        navigate(target, false); if (state["mode"].isString()) setMode(state["mode"].toString());
        setAreaMode(state["areaMode"].toString("custom"));
        const auto sizes = state["areaSizes"].toArray();
        if (areaMode_ == "custom" && sizes.size() == 2 && sizes[0].toInt() >= 0 && sizes[1].toInt() >= 0 && sizes[0].toInt() + sizes[1].toInt() > 0)
            vertical_->setSizes({sizes[0].toInt(), sizes[1].toInt()});
        setProperty("pinned", state["pinned"].toBool()); setProperty("locationLocked", state["locked"].toBool());
    }
    /** @brief フォルダー/ファイル領域の比率だけを変更し、選択や一覧は再生成しない。 @param mode columns/balanced/files/custom。 */
    void setAreaMode(const QString& mode) {
        areaMode_ = QStringList{"columns", "balanced", "files"}.contains(mode) ? mode : "custom";
        if (areaMode_ != "custom") {
            const int total = qMax(100, vertical_->height() - vertical_->handleWidth());
            const double ratio = areaMode_ == "columns" ? 0.75 : areaMode_ == "files" ? 0.25 : 0.45;
            vertical_->setSizes({int(total * ratio), int(total * (1.0 - ratio))});
        }
        emit layoutChanged();
    }
    /** @brief 下段にもフォルダーを表示する。 @param value 表示するか。 */
    void includeSubfolders(bool value) { includeFolders_ = value; for (auto* model : fileModels_) model->setProperty("snapshotGeneration", QVariant()); for (auto* proxy : fileProxies_) { proxy->setProperty("includeFolders", value); proxy->invalidate(); } apply(path_); }
    /** @brief 再帰一覧の表示を切り替える。フォルダー自身の表示とは別の状態。 @param value 有効か。 */
    void setRecursive(bool value) {
        recursive_ = value; recursiveJobs_->cancel(); recursiveToken_ = QUuid::createUuid().toString();
        if (value) requestRecursive(); else { model_->setProperty("snapshotGeneration", QVariant()); apply(path_); }
        saveFolderView(); updateConditions();
    }
    /** @brief 探索起点を指定する。 @param value 新しい起点、空で解除。 */
    void setStartFolder(const QString& value) { startFolder_ = value.isEmpty() ? QString{} : DirectoryStore::normalized(value); navigate(path_, false); }
    /** @brief ディスクを読まず既存の文字幅からカラムを並べ直す。 @param mode fitまたはnames。 */
    void setColumnWidthMode(const QString& mode) { columnWidthMode_ = mode == "names" ? "names" : "fit"; fitColumns(); }
    /** @brief 主一覧の表示方式を変える。 @param mode Details/Thumbnails/Extended details。 @param preserveColumns 非同期更新では表示列の選択を保つ。 */
    void setMode(const QString& mode, bool preserveColumns = false) {
        const auto previousSelection = selection();
        if (mode_ != mode) { media_->cancel(); thumbnailRequests_.clear(); thumbnailToken_ = QUuid::createUuid().toString(); }
        mode_ = mode; presentations_->setCurrentWidget(mode == "Thumbnails" ? static_cast<QWidget*>(thumbnails_) : files_);
        if (mode == "Extended details") {
            const auto labels = readSettings()["fileLabels"].toObject();
            model_->setHorizontalHeaderLabels({"Name", "Size", "Extension", "Date modified", "Tags", "Rating", "Location", "Dimensions", "Availability"});
            for (int row = 0; row < model_->rowCount(); ++row) {
                const auto path = model_->item(row)->data(PathRole).toString(); const auto label = labels[QDir::toNativeSeparators(path).toLower()].toObject();
                QStringList tags; for (const auto& v : label["tags"].toArray()) tags.append(v.toString());
                const QString dimensions = model_->item(row, 7) ? model_->item(row, 7)->text() : QString();
                const QStringList values{tags.join(", "), QString::number(label["rating"].toInt()), QFileInfo(path).absolutePath(), dimensions, fileAvailability(path)};
                for (int col = 4; col < 9; ++col) {
                    if (col == 7 && model_->item(row, col)) continue;
                    auto* cell = new QStandardItem(values[col - 4]); cell->setEditable(false); cell->setData(col == 5 ? QVariant(label["rating"].toInt()) : QVariant(values[col - 4]), SortRole); model_->setItem(row, col, cell);
                }
            }
        }
        if (!preserveColumns) for (int col = 4; col < model_->columnCount(); ++col) files_->setColumnHidden(col, mode != "Extended details");
        selectPaths(previousSelection); saveFolderView(); scheduleThumbnails();
    }
    /** @brief フォルダーごとの表示設定をメモリに記録し、頻繁なリサイズをまとめる。 */
    void saveFolderView() {
        if (viewRestoring_ || applying_ || path_.isEmpty() || !viewSaveTimer_) return;
        const auto key = QDir::toNativeSeparators(path_).toLower(); auto state = folderViews_[key].toObject();
        state["mode"] = mode_ == "Thumbnails" ? 1 : mode_ == "Extended details" ? 2 : 0;
        state["flat"] = recursive_; state["group"] = groupMode_; state["tagFilter"] = tagFilter_; state["sort"] = files_->header()->sortIndicatorSection(); state["descending"] = files_->header()->sortIndicatorOrder() == Qt::DescendingOrder;
        QJsonArray hidden, widths; for (int col = 0; col < model_->columnCount(); ++col) { if (col && files_->isColumnHidden(col)) hidden.append(col); widths.append(files_->columnWidth(col)); }
        state["hidden"] = hidden; state["widths"] = widths;
        if (folderViews_[key] != state) { folderViews_[key] = state; dirtyViews_[key] = state; viewSaveTimer_->start(); }
    }
    /** @brief 他プロセスの別フォルダー設定を保ったまま、変更した場所だけ保存する。 */
    void flushFolderViews() {
        if (dirtyViews_.isEmpty()) return;
        try { mergeSettingsMap("folderViews", dirtyViews_); dirtyViews_ = {}; }
        catch (const std::exception& error) { if (footer_) footer_->setText("Display settings not saved: " + QString::fromUtf8(error.what())); }
    }
    /** @brief 旧Python版と共通のフォルダー設定を復元する。ナビゲーションからだけ呼ぶ。 */
    void restoreFolderView() {
        const auto key = QDir::toNativeSeparators(path_).toLower(); const auto state = folderViews_[key].toObject();
        QScopedValueRollback<bool> guard(viewRestoring_, true);
        recursive_ = state["flat"].toBool(); setTagFilter(state["tagFilter"].toString()); setGrouping(state["group"].toInt());
        setMode(QStringList{"Details", "Thumbnails", "Extended details"}.value(qBound(0, state["mode"].toInt(), 2)));
        const auto hidden = state["hidden"].toArray(), widths = state["widths"].toArray();
        for (int col = 1; col < model_->columnCount(); ++col) { files_->setColumnHidden(col, hidden.contains(col) || (col >= 4 && mode_ != "Extended details")); if (col < widths.size()) files_->setColumnWidth(col, qBound(40, widths[col].toInt(), 1000)); }
        files_->sortByColumn(qBound(0, state["sort"].toInt(), model_->columnCount() - 1), state["descending"].toBool() ? Qt::DescendingOrder : Qt::AscendingOrder);
        fitFileName();
    }
    /** @brief 並べ替え済み一覧をグループ表示へ借用し、選択モデルの所有権を更新する。 */
    void attachModels() {
        if (groupMode_) { groupProxy_->configure(groupMode_, readSettings()["fileLabels"].toObject()); groupProxy_->setSourceModel(proxy_); }
        auto* target = groupMode_ ? static_cast<QAbstractItemModel*>(groupProxy_) : proxy_;
        if (files_->model() == target && thumbnails_->model() == proxy_) return;
        QSet<QItemSelectionModel*> old{files_->selectionModel(), thumbnails_->selectionModel()};
        files_->setModel(target); thumbnails_->setModel(proxy_);
        if (!groupMode_) thumbnails_->setSelectionModel(files_->selectionModel());
        old.remove(files_->selectionModel()); old.remove(thumbnails_->selectionModel()); for (auto* selection : old) delete selection;
        connect(files_->selectionModel(), &QItemSelectionModel::currentChanged, this, [this] { emit selected(detailPath()); });
        connect(files_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this] { fileSelectionChanged(); });
        if (groupMode_) connect(thumbnails_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this] { fileSelectionChanged(); });
        if (groupMode_) connect(thumbnails_->selectionModel(), &QItemSelectionModel::currentChanged, this, [this] { emit selected(detailPath()); });
        files_->setRootIsDecorated(groupMode_ != 0); if (groupMode_) files_->expandAll();
    }
    /** @brief 実パスを両表示の索引へ変換し、見出しを選択しない。 @param paths 選択パス。 */
    void selectPaths(const QStringList& paths) {
        if (paths.isEmpty()) return;
        for (int row = 0; row < proxy_->rowCount(); ++row) { const auto index = proxy_->index(row, 0); if (!paths.contains(index.data(PathRole).toString())) continue;
            const auto tree = groupMode_ ? groupProxy_->mapFromSource(index) : index;
            if (tree.isValid()) files_->selectionModel()->select(tree, QItemSelectionModel::Select | QItemSelectionModel::Rows);
            thumbnails_->selectionModel()->select(index, QItemSelectionModel::Select | QItemSelectionModel::Rows);
        }
    }
    /** @brief 表示だけを集約し、ディスク一覧を取り直さない。 @param mode 見出しの種類、0で解除。 */
    void setGrouping(int mode) {
        const auto paths = selection(); groupMode_ = qBound(0, mode, 4); attachModels(); selectPaths(paths);
        if (!groupMode_) groupProxy_->setSourceModel(nullptr);
        updateConditions();
    }
    /** @brief ラベルによる絞込みを元一覧へ適用する。 @param tag 空で解除。 */
    void setTagFilter(const QString& tag) {
        tagFilter_ = tag; const auto labels = readSettings()["fileLabels"].toObject(); QJsonObject paths;
        for (auto it = labels.begin(); it != labels.end(); ++it) if (it.value().toObject()["tags"].toArray().contains(tag)) paths[QDir::fromNativeSeparators(it.key()).toLower()] = true;
        proxy_->setProperty("tagFilterActive", !tag.isEmpty()); proxy_->setProperty("tagPaths", QVariant::fromValue(paths)); proxy_->invalidate(); saveFolderView(); updateConditions();
    }
    /** @brief 適用中の表示条件を個別に解除できる固定ボタンへ反映する。 */
    void updateConditions() {
        if (!conditionBar_) return;
        const auto* types = findChild<QComboBox*>("fileTypes");
        const QStringList labels{filter_->text().isEmpty() ? QString() : "Name: " + filter_->text(), extensions_.isEmpty() ? QString() : "Type: " + types->currentText(), recursive_ ? "Include subfolders" : QString(), tagFilter_.isEmpty() ? QString() : "Tag: " + tagFilter_, groupMode_ ? "Group: " + QStringList{"None", "Extension", "Modified day", "Location", "Tag"}.value(groupMode_) : QString()};
        bool any = false;
        for (int i = 0; i < labels.size(); ++i) { const auto& label = labels[i]; auto* chip = conditionButtons_[i]; chip->setText(chip->fontMetrics().elidedText(label, Qt::ElideRight, 160) + " ×"); chip->setToolTip("Clear " + label); chip->setVisible(!label.isEmpty()); any |= !label.isEmpty(); }
        conditionBar_->setVisible(any);
    }
    /** @brief フォーカスのあるビューの選択。 @return パス列。 */
    QStringList selection() const {
        QAbstractItemView* active = mode_ == "Thumbnails" ? static_cast<QAbstractItemView*>(thumbnails_) : files_;
        for (const auto& col : columns_) if (col.view->hasFocus()) active = col.view;
        QStringList paths; for (const auto& index : selectedPathIndexes(active)) paths.append(index.data(PathRole).toString());
        return paths;
    }
    /** @brief タブ復帰時の詳細対象をファイル一覧から取得する。カラムのフォーカスとは分離する。
     * @return 現在の選択ファイル。選択がなければ空文字列。
     */
    QString detailPath() const {
        const QAbstractItemView* active = mode_ == "Thumbnails" ? static_cast<QAbstractItemView*>(thumbnails_) : files_;
        const auto current = active->currentIndex().sibling(active->currentIndex().row(), 0);
        if (active->selectionModel()->isSelected(current)) return current.data(PathRole).toString();
        const auto selected = selectedPathIndexes(active);
        return selected.isEmpty() ? QString() : selected.first().data(PathRole).toString();
    }
    /** @brief 明示選択を復元待ちより優先し、全選択解除も詳細・操作対象へ伝える。 */
    void fileSelectionChanged() {
        if (applying_ || viewRestoring_) return;
        operationState_ = {}; pendingReveal_.clear(); restorePending_ = false;
        emit selected(detailPath());
    }
signals:
    /** @brief 手動の分割変更と表示プリセットの保存を要求する。 */
    void layoutChanged();
    /** @brief 要求パスが変わったことを親へ通知する。 */
    void locationChanged();
    /** @brief 選択ファイルを親へ通知する。
     * @param path ファイルパス。
     */
    void selected(const QString& path);
private:
    /** @brief 所有するビューにだけショートカットを登録する。
     * @param view 登録先。
     */
    void installViewKeys(QAbstractItemView* view) {
        const auto bind = [this, view](const QKeySequence& key, auto callback) {
            auto* shortcut = new QShortcut(key, view);
            shortcut->setContext(Qt::WidgetShortcut);
            connect(shortcut, &QShortcut::activated, this, callback);
        };
        bind(QKeySequence(Qt::ALT | Qt::Key_Left), [this] { history(-1); });
        bind(QKeySequence(Qt::ALT | Qt::Key_Right), [this] { history(1); });
        bind(QKeySequence(Qt::ALT | Qt::Key_Up), [this] { up(); });
        bind(QKeySequence(Qt::Key_F5), [this] { for (const auto& column : columns_) store_.request(column.path); });
        bind(QKeySequence(Qt::Key_Return), [this, view] { const auto path = view->currentIndex().data(PathRole).toString(); if (!path.isEmpty()) owner_->perform("rename", {path}, path_); });
        bind(QKeySequence(Qt::Key_Space), [this, view] { open(view->currentIndex().data(PathRole).toString()); });
        bind(QKeySequence(Qt::Key_Left), [this, view] { if (view != files_ && view != thumbnails_) up(); });
        bind(QKeySequence(Qt::Key_Right), [this, view] { if (view != files_ && view != thumbnails_) open(view->currentIndex().data(PathRole).toString()); });
        bind(QKeySequence(Qt::CTRL | Qt::Key_Z), [this] { owner_->perform("undo"); });
        bind(QKeySequence(Qt::CTRL | Qt::Key_Y), [this] { owner_->perform("redo"); });
        bind(QKeySequence(Qt::CTRL | Qt::Key_F), [this] { owner_->perform("search"); });
        for (const auto& pair : QList<QPair<QKeySequence, QString>>{{QKeySequence::Copy, "copy"}, {QKeySequence::Cut, "cut"}, {QKeySequence::Paste, "paste"}, {QKeySequence(Qt::Key_Delete), "trash"}, {QKeySequence(Qt::Key_F2), "rename"}, {QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_N), "newFolder"}})
            bind(pair.first, [this, view, action = pair.second] {
                QStringList paths;
                for (const auto& i : selectedPathIndexes(view)) paths.append(i.data(PathRole).toString());
                const bool column = view != files_ && view != thumbnails_;
                auto destination = column ? view->property("path").toString() : path_;
                // カラムの選択行は、表示している子フォルダーそのもの。親へ貼り付けない。
                const auto selectedFolder = view->currentIndex().data(PathRole).toString();
                if (column && (action == "paste" || action == "newFolder") && !selectedFolder.isEmpty()) destination = selectedFolder;
                owner_->perform(action, paths, destination);
            });
    }
    /** @brief ディレクトリは移動、ファイルは利用者の明示操作で関連付けへ渡す。
     * @param path 対象。
     */
    void open(const QString& path) {
        if (path.isEmpty()) return;
        if (QFileInfo(path).isDir()) navigate(path);
        else owner_->openPath(path);
    }
    /** @brief 右クリック開始時の対象を値として固定する。
     * @param view 対象ビュー。
     * @param point ビュー座標。
     */
    void menu(QAbstractItemView* view, const QPoint& point) {
        owner_->contextMenu(view, point, (view == files_ || view == thumbnails_) ? path_ : view->property("path").toString());
    }
    /** @brief 採用済み結果だけで対応する一覧を更新する。
     * @param path 更新対象。
     */
    void apply(const QString& path) {
        const auto* snapshot = store_.snapshot(path);
        if (!snapshot) return;
        const quint64 revision = snapshot->generation * 2 + (snapshot->complete ? 1 : 0);
        applying_ = true;
        for (int i = 0; i < columns_.size(); ++i) {
            auto& column = columns_[i];
            if (column.path != path) continue;
            const int vertical = column.view->verticalScrollBar()->value();
            if (column.model->property("snapshotGeneration").toULongLong() != revision) {
                applyRows(column.model, path, *snapshot, true);
                column.model->setProperty("snapshotGeneration", QVariant::fromValue(revision));
                column.view->setProperty("widthFont", QVariant());
            }
            column.view->setVisible(i == 0 || column.model->rowCount() || !snapshot->complete || !snapshot->error.isEmpty());
            const QString selectedPath = i + 1 < columns_.size() ? columns_[i + 1].path : QString();
            for (int row = 0; row < column.model->rowCount(); ++row) {
                if (column.model->item(row)->data(PathRole).toString() == selectedPath)
                    column.view->selectionModel()->setCurrentIndex(column.model->index(row, 0), QItemSelectionModel::ClearAndSelect);
            }
            column.view->verticalScrollBar()->setValue(vertical);
            if (!column.revealPath.isEmpty() && column.view->currentIndex().data(PathRole).toString() == column.revealPath) {
                column.view->scrollTo(column.view->currentIndex(), QAbstractItemView::EnsureVisible);
            }
            if (snapshot->complete) column.revealPath.clear();
        }
        if (path == path_ && !recursive_) {
            if (model_->property("snapshotGeneration").toULongLong() != revision) {
                const bool sorting = files_->isSortingEnabled();
                files_->setSortingEnabled(false);
                files_->updateModel([&] { applyRows(model_, path, *snapshot, false, includeFolders_); });
                if (mode_ == "Extended details") setMode(mode_, true);
                files_->setSortingEnabled(sorting);
                model_->setProperty("snapshotGeneration", QVariant::fromValue(revision));
            }
            ready_ = snapshot->complete && snapshot->error.isEmpty();
            summary_->setText((QFileInfo(path).fileName().isEmpty() ? path : QFileInfo(path).fileName())
                             + QString(" · %1 files").arg(model_->rowCount()) + (snapshot->complete ? QString() : " · Loading…"));
            footer_->setText(snapshot->error.isEmpty() ? QString("%1 items").arg(model_->rowCount()) : snapshot->error);
            if (restorePending_) { restorePosition(); restorePending_ = !snapshot->complete; }
        }
        applying_ = false;
        if (path == path_) applyReveal();
        fitColumns(); scheduleThumbnails();
    }
    /** @brief 現在世代に到着した対象だけを選択し、フォーカスを他UIから奪わない。 */
    void applyReveal() {
        if (pendingReveal_.isEmpty()) return;
        for (int row = 0; row < proxy_->rowCount(); ++row) {
            const auto index = proxy_->index(row, 0);
            if (index.data(PathRole).toString().compare(pendingReveal_, Qt::CaseInsensitive)) continue;
            const auto tree = groupMode_ ? groupProxy_->mapFromSource(index) : index;
            pendingReveal_.clear();
            QScopedValueRollback<bool> guard(applying_, true);
            files_->selectionModel()->setCurrentIndex(tree, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            thumbnails_->selectionModel()->setCurrentIndex(index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            files_->scrollTo(tree); thumbnails_->scrollTo(index); emit selected(index.data(PathRole).toString());
            return;
        }
        if (ready_) pendingReveal_.clear();
    }
    /** @brief 非同期更新で横位置を変えず、直近4列に幅を優先配分する。 */
    void fitColumns() {
        int available = scroll_->viewport()->width();
        QVector<int> widths;
        for (const auto& column : columns_) {
            int width = column.view->property("contentWidth").toInt();
            if (column.view->property("widthFont").toString() != font().toString()) {
                width = 100;
                // 縦スクロールバーが出ても文字が省略されないよう、その予約幅も含める。
                const int chrome = 52 + column.view->style()->pixelMetric(QStyle::PM_ScrollBarExtent)
                    + 2 * column.view->frameWidth();
                for (int row = 0; row < column.model->rowCount(); ++row)
                    width = qMax(width, column.view->fontMetrics().horizontalAdvance(column.model->item(row)->text()) + chrome);
                column.view->setProperty("widthFont", font().toString()); column.view->setProperty("contentWidth", width);
            }
            const int desired = columnWidthMode_ == "names" ? manualWidths_.value(column.path, qMin(width, 1000)) : qMin(width, 320);
            widths.append(column.view->isHidden() ? 0 : desired);
            available -= widths.last();
        }
        for (int i = 0; columnWidthMode_ == "fit" && i < widths.size() && available < 0; ++i) {
            const int minimum = i < widths.size() - 4 ? 80 : 120;
            const int shrink = qMin(-available, qMax(0, widths[i] - minimum));
            widths[i] -= shrink;
            available += shrink;
        }
        for (int i = 0; i < columns_.size(); ++i) if (widths[i]) columns_[i].view->setFixedWidth(widths[i]);
        if (reveal_) {
            reveal_ = false;
            QTimer::singleShot(0, this, [this] { scroll_->horizontalScrollBar()->setValue(scroll_->horizontalScrollBar()->maximum()); });
        }
    }
    /** @brief 移動前の選択・縦横位置をパスごとに保持する。 */
    void savePosition() {
        if (path_.isEmpty()) return;
        auto& value = positions_[path_];
        value.horizontal = scroll_->horizontalScrollBar()->value();
        value.files = files_->verticalScrollBar()->value();
        value.filter = filter_->text();
        // 列挙を待つ復元対象は、まだ空のビューや古いキャッシュの選択で上書きしない。
        // ユーザーが選択を変えた場合はselectionChangedが復元待ちを解除する。
        if (!restorePending_) {
            value.selected.clear();
            auto* active = mode_ == "Thumbnails" ? static_cast<QAbstractItemView*>(thumbnails_) : files_;
            for (const auto& index : selectedPathIndexes(active)) value.selected.append(index.data(PathRole).toString());
        }
        for (const auto& col : columns_) value.columns[col.path] = col.view->verticalScrollBar()->value();
    }
    /** @brief 採用済み一覧へ記録済み位置を戻す。フォーカスは移さない。 */
    void restorePosition() {
        if (!positions_.contains(path_)) return;
        QScopedValueRollback<bool> guard(applying_, true);
        const auto value = positions_[path_];
        for (const auto& col : columns_) col.view->verticalScrollBar()->setValue(value.columns.value(col.path));
        scroll_->horizontalScrollBar()->setValue(value.horizontal);
        for (int row = 0; !value.selected.isEmpty() && row < proxy_->rowCount(); ++row) {
            const auto index = proxy_->index(row, 0);
            if (value.selected.contains(index.data(PathRole).toString())) {
                if (files_->selectionModel()->selectedRows().isEmpty()) {
                    files_->selectionModel()->setCurrentIndex(groupMode_ ? groupProxy_->mapFromSource(index) : index, QItemSelectionModel::NoUpdate);
                    thumbnails_->selectionModel()->setCurrentIndex(index, QItemSelectionModel::NoUpdate);
                }
                files_->selectionModel()->select(groupMode_ ? groupProxy_->mapFromSource(index) : index, QItemSelectionModel::Select | QItemSelectionModel::Rows);
                thumbnails_->selectionModel()->select(index, QItemSelectionModel::Select | QItemSelectionModel::Rows);
            }
        }
        files_->verticalScrollBar()->setValue(value.files);
        // 復元中のselectionChangedはユーザー操作と区別して抑止している。
        // 非同期列挙後に採用した選択を、詳細ペインへ一度明示的に通知する。
        emit selected(detailPath());
    }
    /** @brief ビュー領域の変更時に列幅だけを再計算する。
     * @param event サイズ変更。
     */
    void resizeEvent(QResizeEvent* event) override { QWidget::resizeEvent(event); fitColumns(); fitFileName(); }
    /** @brief 起動やペイン切替で子ビューの配置が確定した後に名前欄を合わせる。
     * @param watched 対象のビューポート。
     * @param event サイズ等の通知。入力は奪わない。
     * @return 基底クラスの処理結果。
     */
    bool eventFilter(QObject* watched, QEvent* event) override {
        if (files_ && watched == files_->viewport() && event->type() == QEvent::Resize && !fileFitPending_) {
            fileFitPending_ = true;
            QTimer::singleShot(0, this, [this] { fileFitPending_ = false; fitFileName(); });
        }
        return QWidget::eventFilter(watched, event);
    }
    /** @brief 狭いドックでも名前を読める幅を残し、他の情報は横スクロールで確認する。 */
    void fitFileName() {
        if (!files_ || !files_->model()) return;
        int used = 0;
        for (int column = 1; column < files_->model()->columnCount(); ++column)
            if (!files_->isColumnHidden(column)) used += files_->columnWidth(column);
        const int minimum = qMax(160, files_->fontMetrics().averageCharWidth() * 24);
        files_->setColumnWidth(0, qMax(minimum, files_->viewport()->width() - used));
    }
    /** @brief 可視画像だけを少量ずつ遅延要求する。 */
    void scheduleThumbnails() { if (mode_ == "Thumbnails" || mode_ == "Extended details") mediaTimer_->start(); }
    /** @brief メインスレッドで画像をデコードしない。最大40件の可視要求だけを予約。 */
    void requestThumbnails() {
        if ((mode_ != "Thumbnails" && mode_ != "Extended details") || !isVisible()) return;
        int count = 0;
        for (int row = 0; row < proxy_->rowCount() && count < 40; ++row) {
            const auto index = proxy_->index(row, 0); const auto path = index.data(PathRole).toString();
            const auto shown = groupMode_ ? groupProxy_->mapFromSource(index) : index;
            const bool visible = mode_ == "Thumbnails" ? thumbnails_->visualRect(index).intersects(thumbnails_->viewport()->rect()) : files_->visualRect(shown).intersects(files_->viewport()->rect());
            if (!visible || thumbnailRequests_.contains(path) || index.data(DirectoryRole).toBool()) continue;
            thumbnailRequests_.insert(path); ++count; media_->enqueue({"media", {path}, {}, "rename", {{"token", thumbnailToken_}, {"metadataOnly", mode_ == "Extended details"}}});
        }
    }
    /** @brief 世代を変えて子階層をワーカーで読む。古いA→B→Aの結果は採用しない。 */
    void requestRecursive() {
        if (path_.isEmpty()) return;
        recursiveJobs_->cancel(); recursiveToken_ = QUuid::createUuid().toString(); ready_ = false;
        footer_->setText("Reading subfolders…");
        recursiveJobs_->enqueue({"listRecursive", {path_}, {}, "rename", {{"hidden", hiddenFiles_}, {"token", recursiveToken_}}});
    }
    struct Column { QString path; FolderList* view; QStandardItemModel* model; QString revealPath; };
    struct Position { int horizontal = 0; int files = 0; QString filter; QStringList selected; QHash<QString, int> columns; };
    DirectoryStore store_;
    BrowserWindow* owner_;
    QVector<Column> columns_;
    QHash<QString, Position> positions_;
    QHash<QString, int> manualWidths_;
    QString columnWidthMode_ = readSettings()["columnWidthMode"].toString("fit");
    QHash<QString, QStandardItemModel*> fileModels_;
    QHash<QString, QSortFilterProxyModel*> fileProxies_;
    QStringList fileRecency_;
    QString path_;
    QStringList history_;
    int historyIndex_ = -1;
    QScrollArea* scroll_;
    QSplitter* vertical_;
    QString areaMode_ = "custom";
    QHBoxLayout* columnLayout_;
    FileTree* files_;
    FolderList* thumbnails_;
    QStackedWidget* presentations_;
    FileJobs* media_;
    FileJobs* recursiveJobs_;
    QString recursiveToken_;
    QString thumbnailToken_;
    bool recursive_ = false;
    bool hiddenFiles_ = false;
    QTimer* mediaTimer_;
    QSet<QString> thumbnailRequests_;
    QString mode_ = "Details";
    QStringList extensions_;
    QJsonObject operationState_;
    QString startFolder_;
    bool fileFitPending_ = false;
    bool includeFolders_ = false;
    QStandardItemModel* model_;
    QSortFilterProxyModel* proxy_;
    QScrollArea* conditionBar_ = nullptr;
    QList<QToolButton*> conditionButtons_;
    QLineEdit* filter_;
    QLabel* summary_;
    QLabel* footer_;
    GroupProxy* groupProxy_ = nullptr;
    int groupMode_ = 0, groupScroll_ = 0;
    QStringList groupSelection_;
    QString tagFilter_;
    QJsonObject folderViews_, dirtyViews_;
    QTimer* viewSaveTimer_ = nullptr;
    bool viewRestoring_ = false;
    bool applying_ = false;
    bool ready_ = false;
    bool reveal_ = false;
    bool restorePending_ = false;
    QString pendingReveal_;
    bool groupRestorePending_ = false;
};

BrowserWindow::BrowserWindow(QWidget* parent, HostServices host) : QWidget(parent), host_(std::move(host)) {
    setObjectName("qpeNativeWindow");
#ifdef QPE_PRODUCT_BUILD
    setWindowTitle("QuickPathExplorer");
#else
    setWindowTitle("QuickPathExplorer — C++ migration preview");
#endif
    setWindowIcon(QIcon(":/qpe/icons/quickPathExplorer.png"));
    resize(1200, 800);
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(8, 4, 8, 6);
    root->setSpacing(6);
    strip_ = new QWidget;
    auto* strip = new QHBoxLayout(strip_);
    strip->setContentsMargins(0, 0, 0, 0);
    tabs_ = new NavigationTabs;
    static_cast<NavigationTabs*>(tabs_)->transfer = [this](const QStringList& paths, int index, bool move) {
        const auto* target = index >= 0 ? qobject_cast<BrowserPage*>(pages_->widget(index)) : page();
        if (target) perform(move ? "moveTo" : "copyTo", paths, target->path());
    };
    tabs_->setObjectName("folderTabs");
    tabs_->setExpanding(false);
    tabs_->setTabsClosable(true);
    tabs_->setMovable(true);
    tabs_->setElideMode(Qt::ElideRight);
    strip->addWidget(tabs_);
    auto* add = tool(strip, "+");
    add->setAccessibleName("New tab");
    // ホストの別入力欄から新規タブを作った直後も、タブ切替キーの対象をQPEにする。
    add->setFocusPolicy(Qt::StrongFocus);
    strip->addStretch(1);
    if (!parent) {
        auto* minimize = tool(strip, "−");
        auto* maximize = tool(strip, "□");
        auto* close = tool(strip, "×");
        connect(minimize, &QToolButton::clicked, this, &QWidget::showMinimized);
        connect(maximize, &QToolButton::clicked, this, [this] { isMaximized() ? showNormal() : showMaximized(); });
        connect(close, &QToolButton::clicked, this, &QWidget::close);
    }
    root->addWidget(strip_);
    auto* toolbar = new QHBoxLayout;
    auto* left = tool(toolbar, "Navigation pane", "sidebar.svg");
    left->setObjectName("navigationPaneButton");
    back_ = tool(toolbar, "Back", "back.svg");
    forward_ = tool(toolbar, "Forward", "forward.svg");
    address_ = new QLineEdit;
    address_->setObjectName("address");
    toolbar->addWidget(address_, 1);
    auto* size = tool(toolbar, "Aa");
    size->setObjectName("displaySettingsButton");
    auto* right = tool(toolbar, "Details pane", "inspector.svg");
    right->setObjectName("detailsPaneButton");
    auto* tools = tool(toolbar, "Tools");
    tools->setObjectName("toolsButton"); tools->setAccessibleName("Tools");
    if (host_.maya) {
        auto* newScene = tool(toolbar, "New Scene", "newScene.svg"); newScene->setObjectName("newSceneButton");
        connect(newScene, &QToolButton::clicked, this, [this] { perform("new"); });
        auto* saveAs = tool(toolbar, "Save As…", "saveAs.svg"); saveAs->setObjectName("saveAsButton");
        connect(saveAs, &QToolButton::clicked, this, [this] { perform("prepareSave"); });
    }
    root->addLayout(toolbar);
    horizontal_ = new QSplitter(this);
    horizontal_->setChildrenCollapsible(false);
    sidebar_ = new PlacesTree(horizontal_);
    static_cast<PlacesTree*>(sidebar_)->favorite = [this](const QStringList& paths) { perform("favorite", paths); };
    sidebar_->setObjectName("places");
    sidebar_->setHeaderHidden(true);
    sidebar_->setMinimumWidth(120);
    sidebar_->setProperty("qpeIconPathRole", PathRole);
    createNative("icons", sidebar_)->setObjectName("placesIcons");
    auto* drives = new QTreeWidgetItem(sidebar_, {"Drives"});
    const DWORD mask = GetLogicalDrives();
    for (int letter = 0; letter < 26; ++letter) if (mask & (1u << letter)) {
        const QString path = QString(QChar('A' + letter)) + ":/";
        auto* item = new QTreeWidgetItem(drives, {path});
        item->setData(0, PathRole, path);
        item->setIcon(0, style()->standardIcon(QStyle::SP_DriveHDIcon));
    }
    drives->setExpanded(true);
    pages_ = new QStackedWidget(horizontal_);
    pages_->setMinimumWidth(160);
    details_ = new Inspector(host_.maya, horizontal_);
    details_->setMinimumWidth(140);
    horizontal_->setStretchFactor(1, 1);
    horizontal_->setSizes({200, 760, 240});
    sidebar_->hide();
    details_->hide();
    root->addWidget(horizontal_, 1);
    auto* notice = new QLabel;
#ifndef QPE_PRODUCT_BUILD
    notice->setText("C++ migration · validation build");
#endif
    notice->setObjectName("migrationNotice");
    root->addWidget(notice);
    status_ = notice;
    jobs_ = new FileJobs(this);
    driveJobs_ = new FileJobs(this);
    connect(driveJobs_, &FileJobs::finished, this, [this](const QJsonObject& value) {
        const auto result = fileResultFromJson(value);
        for (const auto& value : result.extra["rows"].toArray()) {
            const auto drive = value.toObject(); const auto path = drive["path"].toString();
            for (QTreeWidgetItemIterator it(sidebar_); *it; ++it) if ((*it)->data(0, PathRole).toString() == path) {
                const auto label = drive["label"].toString() + " (" + path.left(2) + ")";
                (*it)->setText(0, label);
                (*it)->setData(0, Qt::UserRole + 30, drive);
                const auto capacity = qint64(drive["total"].toDouble(-1)), free = qint64(drive["free"].toDouble(-1));
                (*it)->setToolTip(0, label + '\n' + drive["format"].toString() + (capacity > 0 ? "\n" + QLocale().formattedDataSize(free) + " free / " + QLocale().formattedDataSize(capacity) : "\nCapacity unavailable")); break;
            }
        }
    });
    saveTimer_ = new QTimer(this); saveTimer_->setSingleShot(true); saveTimer_->setInterval(400);
    connect(saveTimer_, &QTimer::timeout, this, &BrowserWindow::saveSession);
    connect(details_, &Inspector::changed, this, &BrowserWindow::scheduleSave);
    connect(details_, &Inspector::requested, this, [this](const QString& action) { perform(action, selectedPaths(), currentPath()); });
    connect(details_, &Inspector::namespaceRequested, this, [this](const QString& action) {
        try {
            if (!host_.namespaces) return;
            bool ok = false; const auto name = QInputDialog::getItem(this, "Existing namespaces", "Namespace", host_.namespaces(), 0, false, &ok);
            if (ok) details_->restore({{action, QJsonObject{{"mode", name == ":" ? "root" : "custom"}, {"name", name}}}});
        } catch (const std::exception& e) { QMessageBox::warning(this, "Namespaces", QString::fromUtf8(e.what())); }
    });
    connect(jobs_, &FileJobs::started, this, [this](const QString& action) {
        status_->setText("Working: " + action);
        for (auto* p : findChildren<BrowserPage*>()) p->beginOperation();
    });
    connect(jobs_, &FileJobs::progress, this, [this](const QString& path, qint64 bytes) { status_->setText(path + " · " + QLocale().formattedDataSize(bytes)); });
    connect(jobs_, &FileJobs::finished, this, [this](const QJsonObject& value) {
        const auto result = fileResultFromJson(value);
        if (result.extra.contains("query")) {
            showQuery(result.extra); status_->setText(result.cancelled ? "Cancelled · partial results" : "Query completed");
            if (!result.errors.isEmpty() || !result.warnings.isEmpty()) {
                status_->setText("Query incomplete"); QMessageBox::warning(this, "Query results", (result.errors + result.warnings).join('\n'));
            }
            return;
        }
        for (const auto& value : result.extra["pathChanges"].toArray()) {
            const auto change = value.toObject(); const auto from = change["from"].toString(), to = change["to"].toString();
            for (auto* p : findChildren<BrowserPage*>()) p->remapOperation(from, to);
            closedTabs_ = remapPaths(closedTabs_, from, to).toArray();
            try { const auto settings = readSettings(); QJsonObject changed;
                for (const auto& key : QStringList{"favorites", "recents", "fileLabels", "folderViews", "tabSets", "nativeTabSets", "nativeWorkspace", "nativeMayaWorkspace", "mayaLayoutTabs", "standaloneLayoutTabs"}) if (settings.contains(key)) changed[key] = remapPaths(settings[key], from, to);
                // ラベルのキーは既存Python版と同じWindows正規化表記へ戻す。
                QJsonObject labels; const auto values = changed["fileLabels"].toObject(); for (auto it = values.begin(); it != values.end(); ++it) labels[QDir::toNativeSeparators(it.key()).toLower()] = it.value(); if (changed.contains("fileLabels")) changed["fileLabels"] = labels;
                writeSettings(changed); updatePlaces();
            } catch (const std::exception& e) { status_->setText(QString::fromUtf8(e.what())); }
        }
        for (auto* p : findChildren<BrowserPage*>()) p->endOperation();
        refresh();
        // 詳細は警告ダイアログに表示し、完了表示で上下ペインの高さを変えない。
        status_->setText(QString("%1 completed%2%3").arg(result.completed.size())
            .arg(result.cancelled ? " · cancelled" : "")
            .arg(result.errors.isEmpty() && result.warnings.isEmpty() ? "" : " · see file operation details"));
        if (!result.errors.isEmpty() || !result.warnings.isEmpty()) QMessageBox::warning(this, "File operation", (result.errors + result.warnings).join('\n'));
    });
    connect(add, &QToolButton::clicked, this, [this] { addTab(currentPath().isEmpty() ? QDir::homePath() : currentPath()); });
    connect(tabs_, &QTabBar::currentChanged, this, [this](int index) { pages_->setCurrentIndex(index); updateCurrent(); });
    connect(tabs_, &QTabBar::tabMoved, this, [this](int from, int to) { auto* item = pages_->widget(from); pages_->removeWidget(item); pages_->insertWidget(to, item); pages_->setCurrentIndex(tabs_->currentIndex()); scheduleSave(); });
    connect(tabs_, &QTabBar::tabCloseRequested, this, [this](int index) {
        if (tabs_->count() <= 1 || index < 0 || pages_->widget(index)->property("pinned").toBool()) return;
        closedTabs_.append(qobject_cast<BrowserPage*>(pages_->widget(index))->state()); if (closedTabs_.size() > 30) closedTabs_.removeAt(0);
        auto* old = pages_->widget(index);
        pages_->removeWidget(old);
        tabs_->removeTab(index);
        delete old;
        pages_->setCurrentIndex(tabs_->currentIndex());
        updateCurrent();
    });
    connect(address_, &QLineEdit::returnPressed, this, [this] { navigate(address_->text()); });
    auto* addressStore = new DirectoryStore(address_);
    auto* addressModel = new QStringListModel(address_);
    auto* completer = new QCompleter(addressModel, address_);
    completer->setCaseSensitivity(Qt::CaseInsensitive); completer->setCompletionMode(QCompleter::UnfilteredPopupCompletion); address_->setCompleter(completer);
    auto* addressTimer = new QTimer(address_); addressTimer->setSingleShot(true); addressTimer->setInterval(180);
    const auto suggest = [this, addressStore, addressModel, completer](const QString& parent) {
        if (!address_->hasFocus() || address_->text() != address_->property("completionInput").toString() || parent != address_->property("completionParent").toString()) return;
        const auto* snapshot = addressStore->snapshot(parent); if (!snapshot || !snapshot->error.isEmpty()) return;
        const auto prefix = address_->property("completionPrefix").toString(); QStringList matches;
        for (const auto& entry : snapshot->entries) if (entry.directory && entry.name.startsWith(prefix, Qt::CaseInsensitive)) {
            matches.append(QDir::toNativeSeparators(QDir(parent).filePath(entry.name))); if (matches.size() >= 150) break;
        }
        addressModel->setStringList(matches); if (!matches.isEmpty()) completer->complete(); else completer->popup()->hide();
    };
    connect(address_, &QLineEdit::textEdited, addressTimer, [addressTimer, completer] { completer->popup()->hide(); addressTimer->start(); });
    connect(addressTimer, &QTimer::timeout, this, [this, addressStore, suggest] {
        const QString input = address_->text(); QString expanded = QDir::fromNativeSeparators(input);
        if (expanded.startsWith("~/")) expanded.replace(0, 1, QDir::homePath());
        const int slash = expanded.lastIndexOf('/'); if (slash < 0) { addressStore->activate({}); return; }
        const auto parent = DirectoryStore::normalized(expanded.left(slash + 1));
        address_->setProperty("completionInput", input); address_->setProperty("completionParent", parent); address_->setProperty("completionPrefix", expanded.mid(slash + 1));
        addressStore->activate({parent}); suggest(parent);
    });
    connect(addressStore, &DirectoryStore::changed, this, suggest);
    address_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(address_, &QWidget::customContextMenuRequested, this, [this](const QPoint& position) {
        std::unique_ptr<QMenu> menu(address_->createStandardContextMenu()); auto* ancestors = menu->addMenu("Parent folders");
        QString path = currentPath();
        while (true) { const auto parent = QFileInfo(path).absolutePath(); if (parent == path || parent.isEmpty()) break;
            ancestors->addAction(QDir::toNativeSeparators(parent), this, [this, parent] { navigate(parent); }); path = parent;
        }
        auto* recent = menu->addMenu("Recent folders");
        for (const auto& path : pathHistory_) if (!path.isEmpty()) recent->addAction(QDir::toNativeSeparators(path), this, [this, path] { navigate(path); });
        recent->setEnabled(!recent->actions().isEmpty());
        menu->exec(address_->mapToGlobal(position));
    });
    tabs_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(tabs_, &QWidget::customContextMenuRequested, this, [this](const QPoint& position) {
        const int index = tabs_->tabAt(position); if (index < 0) return; QPointer<QWidget> target = pages_->widget(index); QMenu menu;
        for (const auto& pair : QList<QPair<QString, QString>>{{"Pin tab (prevent closing)", "pinned"}, {"Lock location (navigate in new tab)", "locationLocked"}}) {
            auto* action = menu.addAction(pair.first); action->setCheckable(true); action->setChecked(target->property(pair.second.toUtf8()).toBool());
            connect(action, &QAction::toggled, this, [this, target, key = pair.second](bool value) { if (target) { target->setProperty(key.toUtf8(), value); scheduleSave(); } });
        }
        menu.addAction("Duplicate tab", this, [this, target] { if (target) addTab(qobject_cast<BrowserPage*>(target.data())->path()); });
        menu.addAction("Close tab", this, [this, index] { emit tabs_->tabCloseRequested(index); })->setEnabled(!target->property("pinned").toBool());
        menu.exec(tabs_->mapToGlobal(position));
    });
    connect(back_, &QToolButton::clicked, this, [this] { if (page()) page()->history(-1); });
    connect(forward_, &QToolButton::clicked, this, [this] { if (page()) page()->history(1); });
    connect(left, &QToolButton::clicked, this, [this] {
        if (detailsFullWidth_) { details_->hide(); sidebarRequested_ = true; }
        else sidebarRequested_ = !sidebarRequested_;
        updateResponsiveLayout(); if (page()) page()->revealCurrent(); scheduleSave();
    });
    connect(right, &QToolButton::clicked, this, [this] { details_->setVisible(details_->isHidden()); updateResponsiveLayout(); if (page()) page()->revealCurrent(); scheduleSave(); });
    connect(horizontal_, &QSplitter::splitterMoved, this, &BrowserWindow::scheduleSave);
    connect(sidebar_, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem* item) {
        const auto search = item->data(0, Qt::UserRole + 101).toString(); if (!search.isEmpty()) { perform("savedSearch:" + search); return; }
        const auto path = item->data(0, PathRole).toString(); if (path.isEmpty()) return; if (item->data(0, DirectoryRole).toBool() || QFileInfo(path).isDir()) navigate(path); else showDetails(path);
    });
    connect(sidebar_, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item) { const auto path = item->data(0, PathRole).toString(); if (!path.isEmpty() && !item->data(0, DirectoryRole).toBool() && !QFileInfo(path).isDir()) openPath(path); });
    sidebar_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(sidebar_, &QWidget::customContextMenuRequested, this, [this](const QPoint& p) {
        auto* item = sidebar_->itemAt(p); if (!item) return;
        const auto search = item->data(0, Qt::UserRole + 101).toString();
        if (!search.isEmpty()) { QMenu menu;
            menu.addAction("Search", this, [this, search] { perform("savedSearch:" + search); });
            menu.addAction("Delete saved search…", this, [this, search] {
                if (QMessageBox::question(this, "Delete saved search", search, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                try { auto values = readSettings()["savedSearches"].toObject(); values.remove(search); writeSettings({{"savedSearches", values}}); updatePlaces(); } catch (const std::exception& e) { status_->setText(e.what()); }
            }); menu.exec(sidebar_->viewport()->mapToGlobal(p)); return;
        }
        if (item->data(0, PathRole).toString().isEmpty()) return; const auto path = item->data(0, PathRole).toString(); QMenu menu;
        const bool directory = item->data(0, DirectoryRole).toBool();
        menu.addAction("Open", this, [this, path, directory] { if (directory) navigate(path); else openPath(path); }); menu.addAction("Open in new tab", this, [this, path, directory] { addTab(directory || QFileInfo(path).isDir() ? path : QFileInfo(path).absolutePath()); });
        if (favorites_.contains(path)) menu.addAction("Remove from Favorites", this, [this, path] { favorites_.removeAll(path); try { writeSettings({{"favorites", QJsonArray::fromStringList(favorites_)}}); updatePlaces(); } catch (const std::exception& e) { status_->setText(e.what()); } }); menu.exec(sidebar_->viewport()->mapToGlobal(p));
    });
    connect(size, &QToolButton::clicked, this, &BrowserWindow::appearanceDialog);
    connect(tools, &QToolButton::clicked, this, [this, tools] {
        QMenu menu(tools); menu.setObjectName("toolsMenu"); menu.addAction("Find command…", this, [this] { perform("palette"); });
        auto* search = menu.addMenu("Search / organize"); search->setObjectName("toolsSearch");
        auto* view = menu.addMenu("View"); view->setObjectName("toolsView");
        auto* transfers = menu.addMenu("Transfers / history"); transfers->setObjectName("toolsTransfers");
        auto* sets = menu.addMenu("Tabs / tab sets"); sets->setObjectName("toolsTabs");
        auto* settings = menu.addMenu("Settings / diagnostics"); settings->setObjectName("toolsSettings");
        view->addAction("Display settings…", this, [this] { perform("appearance"); });
        settings->addAction("QPE settings / keyboard shortcuts…", this, [this] { perform("settings"); }); organizerMenu(&menu);
        auto* theme = view->addMenu("Theme");
        for (const QString mode : {QString("system"), QString("light"), QString("dark")})
            theme->addAction(mode, this, [this, mode] { theme_ = mode; applyAppearance(); });
        for (const auto& pair : QList<QPair<QString, QString>>{{"Search subfolders…", "search"}, {"Find duplicate files…", "duplicates"}, {"Compare folders…", "compare"}, {"Calculate size / count…", "size"}, {"SHA-256", "hash"}, {"Diagnose availability…", "diagnose"}})
            search->addAction(pair.first, this, [this, action = pair.second] { try { query(action); } catch (const std::exception& e) { QMessageBox::warning(this, "Search", QString::fromUtf8(e.what())); } });
        search->addAction("Tags / rating / collection…", this, [this] { perform("tag", selectedPaths()); });
        sets->addAction("Save tab set…", this, [this] { perform("saveTabs"); });
        sets->addAction("Open tab set…", this, [this] { perform("loadTabs"); });
        sets->addAction("Delete tab set…", this, [this] { perform("deleteTabs"); });
        settings->addAction("Export QPE settings…", this, [this] { perform("exportSettings"); });
        settings->addAction("Import QPE settings…", this, [this] { perform("importSettings"); });
        search->addAction("New Folder…", this, [this] { perform("newFolder", {}, currentPath()); });
        search->addAction("New Text File…", this, [this] { perform("newFile", {}, currentPath()); });
        transfers->addAction("Undo file operation", this, [this] { perform("undo"); });
        transfers->addAction("Redo file operation", this, [this] { perform("redo"); });
        transfers->addAction("Cancel file operations", jobs_, &FileJobs::cancel)->setEnabled(jobs_->busy());
        auto* hidden = view->addAction("Show hidden files"); hidden->setCheckable(true); hidden->setChecked(hidden_);
        connect(hidden, &QAction::toggled, this, [this](bool value) { hidden_ = value; for (int i = 0; i < pages_->count(); ++i) qobject_cast<BrowserPage*>(pages_->widget(i))->setHiddenFiles(value); scheduleSave(); });
        search->addAction("Add current folder to Favorites", this, [this] { perform("favorite", {currentPath()}); });
        sets->addAction("Reopen closed tab", this, [this] { reopenTab(); })->setEnabled(!closedTabs_.isEmpty());
        settings->addAction("Licenses and source", this, [this] {
            // DLL解除時に所有する別ウィンドウも破棄し、ホストへ残さない。
            auto* viewer = new QTextEdit(this);
            viewer->setWindowFlags(Qt::Window);
            viewer->setAttribute(Qt::WA_DeleteOnClose);
            viewer->setReadOnly(true);
            viewer->setWindowTitle("QuickPathExplorer — Licenses and source");
            QFile notices(":/qpe/licenses/NOTICES.txt");
            if (notices.open(QIODevice::ReadOnly)) viewer->setPlainText(QString::fromUtf8(notices.readAll()));
            else viewer->setPlainText("License resources are missing. See third_party/NOTICES.txt and BUILDING.md in the distribution.");
            viewer->resize(750, 600); viewer->show();
        });
        menu.exec(tools->mapToGlobal(QPoint(0, tools->height())));
    });
    const auto bind = [this](const QKeySequence& key, auto callback) {
        auto* shortcut = new QShortcut(key, this);
        shortcut->setContext(Qt::WidgetWithChildrenShortcut);
        connect(shortcut, &QShortcut::activated, this, callback);
        return shortcut;
    };
    const auto fontKey = [&](const QKeySequence& key, auto callback) {
        auto* shortcut = bind(key, callback);
        // 編集欄・IME・モーダルでは入力を奪わず、QPEの一覧にフォーカスがある時だけ使う。
        const auto update = [this, shortcut] {
            auto* focus = QApplication::focusWidget(); bool allowed = focus && isAncestorOf(focus);
            for (auto* widget = focus; allowed && widget && widget != this; widget = widget->parentWidget()) {
                if (widget->inherits("QLineEdit") || widget->inherits("QTextEdit") || widget->inherits("QPlainTextEdit") || widget->inherits("QAbstractSpinBox") || widget->inherits("QComboBox") || widget->isWindow()) allowed = false;
            }
            shortcut->setEnabled(allowed);
        };
        shortcut->setObjectName("fontSizeShortcut"); update(); connect(qApp, &QApplication::focusChanged, shortcut, update);
    };
    bind(QKeySequence(Qt::CTRL | Qt::Key_T), [this] { addTab(currentPath()); });
    bind(QKeySequence(Qt::CTRL | Qt::Key_Tab), [this] { tabs_->setCurrentIndex((tabs_->currentIndex() + 1) % tabs_->count()); });
    bind(QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_Tab), [this] { tabs_->setCurrentIndex((tabs_->currentIndex() + tabs_->count() - 1) % tabs_->count()); });
    bind(QKeySequence(Qt::CTRL | Qt::Key_L), [this] { address_->setFocus(); address_->selectAll(); });
    for (auto key : {int(Qt::CTRL | Qt::Key_Plus), int(Qt::CTRL | Qt::Key_Equal), int(Qt::CTRL | Qt::SHIFT | Qt::Key_Plus), int(Qt::CTRL | Qt::SHIFT | Qt::Key_Equal)}) fontKey(QKeySequence(key), [this] { textSize_ = qMin(24, textSize_ + 1); applyAppearance(); });
    fontKey(QKeySequence(Qt::CTRL | Qt::Key_0), [this] { textSize_ = 12; applyAppearance(); });
    fontKey(QKeySequence(Qt::CTRL | Qt::Key_Minus), [this] { textSize_ = qMax(10, textSize_ - 1); applyAppearance(); });
    bind(QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_T), [this] { reopenTab(); });
    bind(QKeySequence(Qt::CTRL | Qt::Key_W), [this] { emit tabs_->tabCloseRequested(tabs_->currentIndex()); });
    if (host_.maya) theme_ = "dark";
    installCommandKeys();
    updatePlaces();
    applyAppearance();
}
BrowserPage* BrowserWindow::page() const { return qobject_cast<BrowserPage*>(pages_->currentWidget()); }
QStringList BrowserWindow::selectedPaths() const {
    if (secondPane_ && secondPane_->isAncestorOf(QApplication::focusWidget())) { auto* second = secondPane_->findChild<BrowserPage*>("secondPage"); if (second) return second->selection(); }
    const auto paths = page() ? page()->selection() : QStringList();
    return paths.isEmpty() && !selected_.isEmpty() ? QStringList{selected_} : paths;
}
bool BrowserWindow::busy() const { return jobs_->busy(); }
void BrowserWindow::scheduleSave() { if (!restoring_ && saveTimer_) saveTimer_->start(); }
void BrowserWindow::saveSession() {
    if (restoring_ || !pages_->count()) return;
    QJsonArray paths, flags, states; for (int i = 0; i < pages_->count(); ++i) {
        auto* item = qobject_cast<BrowserPage*>(pages_->widget(i)); paths.append(item->path()); states.append(item->state());
        flags.append(QJsonObject{{"pinned", item->property("pinned").toBool()}, {"locked", item->property("locationLocked").toBool()}});
    }
    QJsonObject workspace{{"closed", closedTabs_}, {"paths", paths}, {"current", tabs_->currentIndex()}, {"geometry", QString::fromLatin1(saveGeometry().toBase64())},
        {"splitter", QString::fromLatin1((detailsFullWidth_ ? horizontal_->property("wideState").toByteArray() : horizontal_->saveState()).toBase64())}, {"flags", flags}, {"states", states}, {"left", sidebarRequested_}, {"right", !details_->isHidden()}};
    if (secondPane_) {
        workspace["secondVisible"] = !secondPane_->isHidden() || secondPane_->property("responsiveHidden").toBool();
        if (auto* second = secondPane_->findChild<BrowserPage*>("secondPage")) workspace["secondState"] = second->state();
    }
    try { writeSettings({{host_.maya ? "nativeMayaWorkspace" : "nativeWorkspace", workspace}, {host_.maya ? "nativeMayaAppearance" : "nativeAppearance", QJsonObject{{"theme", theme_}, {"textSize", textSize_}, {"uiPercent", uiPercent_}, {"density", density_}}},
        {"nativeHidden", hidden_}, {"nativeReadOptions", details_->options()}, {"pathHistory", QJsonArray::fromStringList(pathHistory_)}}); }
    catch (const std::exception& error) { status_->setText("Settings not saved: " + QString::fromUtf8(error.what())); }
}
void BrowserWindow::restoreSession(const QString& fallback, bool restoreTabs) {
    restoring_ = true; saveTimer_->stop();
    try {
        const auto state = readSettings(); auto workspace = state[host_.maya ? "nativeMayaWorkspace" : "nativeWorkspace"].toObject();
        QJsonObject legacyLayout;
        if (workspace.isEmpty()) {
            legacyLayout = state[host_.maya ? "mayaLayout" : "standaloneLayout"].toObject();
            const auto legacy = state[host_.maya ? "mayaLayoutTabs" : "standaloneLayoutTabs"].toObject();
            workspace["states"] = legacy["states"]; workspace["current"] = legacy["active"]; workspace["closed"] = legacy["closed"];
            const auto outer = legacyLayout["outer"].toArray();
            if (outer.size() == 3) { workspace["left"] = outer[0].toInt() > 0; workspace["right"] = outer[2].toInt() > 0; }
        }
        const auto appearance = state[host_.maya ? "nativeMayaAppearance" : "nativeAppearance"].toObject();
        const auto oldAppearance = state[host_.maya ? "mayaAppearance" : "standaloneAppearance"].toObject();
        textSize_ = qBound(10, appearance["textSize"].toInt(state["nativeTextSize"].toInt(oldAppearance["fontSize"].toInt(12))), 24);
        uiPercent_ = qBound(75, appearance["uiPercent"].toInt(oldAppearance["uiPercent"].toInt(100)), 200);
        density_ = appearance["density"].toString(oldAppearance["density"].toString("compact"));
        theme_ = appearance["theme"].toString(host_.maya ? "dark" : state["standaloneTheme"].toString("system")); hidden_ = state["nativeHidden"].toBool(state["showHidden"].toBool());
        details_->restore(readOptionsFromSettings(state)); closedTabs_ = workspace["closed"].toArray();
        if (!restoreTabs) addTab(fallback.isEmpty() ? QDir::homePath() : fallback);
        if (restoreTabs) for (const auto& value : workspace["states"].toArray()) {
            auto tab = value.toObject(); if (tab["path"].toString().isEmpty()) continue;
            if (!legacyLayout.isEmpty()) { tab["areaMode"] = legacyLayout["browserMode"]; tab["areaSizes"] = legacyLayout["vertical"]; }
            addTab(tab["path"].toString()); page()->restoreState(tab);
        }
        if (!pages_->count()) for (const auto& value : workspace["paths"].toArray()) if (value.isString() && !value.toString().isEmpty()) addTab(value.toString());
        const auto flags = workspace["flags"].toArray();
        for (int i = 0; restoreTabs && i < qMin(flags.size(), pages_->count()); ++i) {
            pages_->widget(i)->setProperty("pinned", flags[i].toObject()["pinned"].toBool());
            pages_->widget(i)->setProperty("locationLocked", flags[i].toObject()["locked"].toBool());
        }
        if (!pages_->count()) addTab(fallback.isEmpty() ? state["lastPath"].toString(QDir::homePath()) : fallback);
        tabs_->setCurrentIndex(qBound(0, workspace["current"].toInt(), tabs_->count() - 1));
        if (!host_.maya && workspace.contains("geometry")) restoreGeometry(QByteArray::fromBase64(workspace["geometry"].toString().toLatin1()));
        else if (!host_.maya && legacyLayout["size"].toArray().size() == 2) {
            const auto size = legacyLayout["size"].toArray(); resize(qBound(320, size[0].toInt(1200), 3000), qBound(240, size[1].toInt(800), 2000));
        }
        if (workspace.contains("secondState")) {
            if (!secondPane_) perform("secondPane");
            if (auto* second = secondPane_->findChild<BrowserPage*>("secondPage")) second->restoreState(workspace["secondState"].toObject());
            secondPane_->setVisible(workspace["secondVisible"].toBool());
        }
        if (workspace.contains("splitter")) horizontal_->restoreState(QByteArray::fromBase64(workspace["splitter"].toString().toLatin1()));
        sidebarRequested_ = workspace["left"].toBool(); details_->setVisible(workspace["right"].toBool());
        applyAppearance();
    } catch (const std::exception& error) { status_->setText(QString::fromUtf8(error.what())); if (!pages_->count()) addTab(fallback.isEmpty() ? QDir::homePath() : fallback); }
    restoring_ = false;
}
void BrowserWindow::updatePlaces() {
    sidebar_->clear();
    try {
        const auto state = readSettings(); favorites_.clear(); recents_.clear();
        for (const auto& path : state["favorites"].toArray()) if (path.isString()) favorites_.append(path.toString());
        for (const auto& path : state["recents"].toArray()) if (path.isString()) recents_.append(path.toString());
        if (pathHistory_.isEmpty()) for (const auto& path : state["pathHistory"].toArray()) if (path.isString()) pathHistory_.append(path.toString());
    } catch (const std::exception& error) { status_->setText(QString::fromUtf8(error.what())); }
    const auto group = [this](const QString& label, const QStringList& paths) {
        auto* root = new QTreeWidgetItem(sidebar_, {label}); root->setExpanded(true);
        // パスの名前だけを描画し、ネットワークを含む属性・Shell照会は可視アイコンのワーカーへ任せる。
        for (const auto& path : paths) {
            const auto name = QFileInfo(path).fileName(); auto* item = new QTreeWidgetItem(root, {name.isEmpty() ? path : name});
            item->setData(0, PathRole, path); item->setToolTip(0, path);
            item->setIcon(0, label == "Drives" ? style()->standardIcon(QStyle::SP_DriveHDIcon) : nativeFolderIcon());
        }
    };
    group("Favorites", favorites_); group("Recent", recents_);
    const struct { const KNOWNFOLDERID* id; const char* label; } folders[] = {
        {&FOLDERID_Desktop, "Desktop"}, {&FOLDERID_Documents, "Documents"}, {&FOLDERID_Downloads, "Downloads"},
        {&FOLDERID_Pictures, "Pictures"}, {&FOLDERID_Music, "Music"}, {&FOLDERID_Videos, "Videos"}
    };
    // 現在の登録先を使う。DONT_VERIFYにより、移動先のNAS等を起動時に同期照会しない。
    // フォルダーを作成するフラグは指定せず、Shellアイコンは既存ワーカーへ任せる。
    for (const auto& folder : folders) {
        PWSTR registered = nullptr;
        const auto result = SHGetKnownFolderPath(*folder.id, KF_FLAG_DONT_VERIFY, nullptr, &registered);
        const auto path = SUCCEEDED(result) && registered ? QDir::cleanPath(QDir::fromNativeSeparators(QString::fromWCharArray(registered))) : QString();
        CoTaskMemFree(registered);
        if (path.isEmpty()) continue;
        auto* item = new QTreeWidgetItem(sidebar_, {QString::fromLatin1(folder.label)});
        item->setData(0, PathRole, path); item->setData(0, DirectoryRole, true);
        item->setToolTip(0, QDir::toNativeSeparators(path)); item->setIcon(0, nativeFolderIcon());
    }
    const auto searches = readSettings()["savedSearches"].toObject();
    for (const auto& name : searches.keys()) { auto* item = new QTreeWidgetItem(sidebar_->topLevelItem(0), {name}); item->setData(0, Qt::UserRole + 101, name); item->setIcon(0, QIcon(":/qpe/icons/search.svg")); item->setToolTip(0, "Saved search: " + name); }
    QStringList drives; const DWORD mask = GetLogicalDrives();
    for (int letter = 0; letter < 26; ++letter) if (mask & (1u << letter)) drives.append(QString(QChar('A' + letter)) + ":/");
    group("Drives", drives);
    if (driveJobs_ && !driveJobs_->busy()) driveJobs_->enqueue({"drives"});
}
void BrowserWindow::openPath(const QString& path) {
    if (path.isEmpty()) return;
    if (QFileInfo(path).isDir()) { navigate(path); return; }
    perform("open", {path});
}
void BrowserWindow::refresh() {
    for (int i = 0; i < pages_->count(); ++i) {
        auto* item = qobject_cast<BrowserPage*>(pages_->widget(i));
        // 削除した階層を開いていたタブは最も近い既存の親へ戻す。
        QString path = item->path(); while (!path.isEmpty() && !QFileInfo::exists(path)) { const auto parent = QFileInfo(path).absolutePath(); if (path == parent) break; path = parent; }
        if (path != item->path()) item->navigate(path); item->refresh();
    }
}
void BrowserWindow::writeClipboard(const QString& action, const QStringList& paths, quint64 generation, quint32 sequence, int attempt) {
    if (generation != clipboardGeneration_) return;
    if (GetClipboardSequenceNumber() != sequence) {
        clipboardPending_ = false; status_->setText("Clipboard changed in another application. Copy again if needed."); return;
    }
    // QtのOleSetClipboard内の待機に入る前に占有だけを確認する。内容は変更しない。
    if (OpenClipboard(nullptr)) {
        CloseClipboard();
        auto* mime = new QMimeData;
        if (action == "copyPath") mime->setText(paths.join('\n'));
        else {
            QList<QUrl> urls; for (const auto& path : paths) urls.append(QUrl::fromLocalFile(path)); mime->setUrls(urls);
            QByteArray effect(4, '\0'); effect[0] = action == "cut" ? 2 : 1;
            mime->setData("Preferred DropEffect", effect); mime->setData("application/x-qt-windows-mime;value=\"Preferred DropEffect\"", effect);
        }
        QApplication::clipboard()->setMimeData(mime);
        if (QApplication::clipboard()->ownsClipboard()) {
            clipboardPending_ = false; status_->setText(action == "cut" ? "Cut to clipboard" : "Copied to clipboard"); return;
        }
    }
    if (attempt >= 20) { clipboardPending_ = false; status_->setText("Could not access the clipboard. Please copy again."); return; }
    status_->setText("Clipboard is busy. Retrying Copy…");
    QTimer::singleShot(75, this, [this, action, paths, generation, sequence, attempt] { writeClipboard(action, paths, generation, sequence, attempt + 1); });
}
void BrowserWindow::perform(const QString& action, const QStringList& paths, const QString& directory) {
    try {
        if (action == "palette") { commandPalette(); return; }
        if (action == "appearance") { appearanceDialog(); return; }
        if (action == "reveal" && paths.size() == 1) {
            const QFileInfo info(paths.first()); navigate(info.isDir() ? paths.first() : info.absolutePath());
            if (!info.isDir() && page()) page()->revealFile(paths.first()); return;
        }
        if (action.startsWith("savedSearch:")) {
            // 一時QJsonObjectのQJsonValueRefを保持すると破棄後参照になるため、値をコピーする。
            const QJsonValue value = readSettings()["savedSearches"].toObject().value(action.mid(12)); if (!value.isObject()) throw std::invalid_argument("Saved search no longer exists");
            auto options = value.toObject(); const auto roots = options["roots"].toString(options["root"].toString(currentPath()));
            const double unit = options["sizeUnit"].toString() == "bytes" || (!options.contains("sizeUnit") && options.contains("roots")) ? 1.0 : 1024.0;
            options["minimum"] = options["minimum"].toDouble() * unit; options["maximum"] = options["maximum"].toDouble() * unit;
            options["extensions"] = options["extensions"].toString(options["types"].toString()); options["hidden"] = options["hidden"].toBool(hidden_);
            FileRequest request; request.action = "search"; request.options = options;
            for (const auto& path : roots.split(';', Qt::SkipEmptyParts)) if (!path.trimmed().isEmpty()) request.paths.append(path.trimmed());
            if (request.paths.isEmpty()) throw std::invalid_argument("Saved search has no scope folders");
            streamingSearch(request); return;
        }
        if (action.startsWith("area:")) { if (page()) page()->setAreaMode(action.mid(5)); return; }
        if (action.startsWith("columnWidth:")) { const auto mode = action.mid(12); writeSettings({{"columnWidthMode", mode}}); for (auto* item : findChildren<BrowserPage*>()) item->setColumnWidthMode(mode); return; }
        if (action == "settings") { preferencesDialog(); return; }
        if (extendedAction(action, paths, directory)) return;
        if (action == "prepareSave") { details_->setDirectory(directory.isEmpty() ? currentPath() : directory); details_->showAction("saveAs"); details_->show(); updateResponsiveLayout(); if (page()) page()->revealCurrent(); return; }
        if (action == "restoreTabSet") { const auto saved = previousTabSet_; for (const auto& value : saved) { const auto state = value.toObject(); addTab(state["path"].toString()); page()->restoreState(state); } previousTabSet_ = {}; return; }
        if (action == "secondPane") {
            if (!secondPane_) {
                secondPane_ = new QWidget(horizontal_); secondPane_->setObjectName("secondPane"); auto* layout = new QVBoxLayout(secondPane_); layout->setContentsMargins(0, 0, 0, 0);
                auto* path = new QLineEdit(currentPath()); path->setObjectName("secondAddress"); auto* up = new QPushButton("Parent folder"); layout->addWidget(path); layout->addWidget(up);
                auto* second = new BrowserPage(secondPane_, this); second->setObjectName("secondPage"); layout->addWidget(second); second->includeSubfolders(true); second->setMode("Details");
                second->findChild<QScrollArea*>("folderColumns")->hide(); second->navigate(currentPath());
                connect(path, &QLineEdit::returnPressed, second, [second, path] { second->navigate(path->text()); });
                connect(up, &QPushButton::clicked, second, [second] { second->up(); });
                connect(second, &BrowserPage::locationChanged, path, [this, second, path] { path->setText(second->path()); scheduleSave(); });
                connect(second, &BrowserPage::selected, this, &BrowserWindow::showDetails);
                auto* transfers = new QHBoxLayout; layout->insertLayout(2, transfers);
                for (const auto& operation : {QString("copyTo"), QString("moveTo")}) for (const bool intoSecond : {true, false}) {
                    auto* button = new QPushButton((intoSecond ? QString("→ ") : QString("← ")) + (operation == "copyTo" ? "Copy" : "Move"));
                    button->setObjectName(operation + (intoSecond ? "Second" : "Main"));
                    button->setToolTip(intoSecond ? "Transfer the main pane selection to this folder" : "Transfer this pane selection to the main folder");
                    transfers->addWidget(button);
                    connect(button, &QPushButton::clicked, this, [this, second, operation, intoSecond] {
                        if (!page()) return; const auto sources = intoSecond ? page()->selection() : second->selection();
                        if (!sources.isEmpty()) perform(operation, sources, intoSecond ? second->path() : page()->path());
                    });
                }
                horizontal_->setSizes({180, 600, 250, 400});
            } else secondPane_->setVisible(secondPane_->isHidden());
            if (page()) page()->revealCurrent(); scheduleSave(); return;
        }
        if (action.startsWith("view:")) { if (page()) page()->setMode(action.mid(5)); return; }
        if (action == "recursiveToggle") { if (page()) page()->setRecursive(!page()->state()["recursive"].toBool()); return; }
        if (action == "recursiveOn" || action == "recursiveOff") { if (page()) page()->setRecursive(action == "recursiveOn"); return; }
        if (QStringList{"search", "duplicates", "compare", "size", "hash", "diagnose"}.contains(action)) { query(action); return; }
        if (action == "startFolder") { if (page()) page()->setStartFolder(paths.value(0)); return; }
        if (action == "exportSettings") { const auto file = QFileDialog::getSaveFileName(this, "Export QPE settings", {}, "JSON (*.json)"); if (!file.isEmpty()) { const auto include = QMessageBox::question(this, "Export settings", "Include computer-specific paths, favorites, tags and saved searches?", QMessageBox::Yes | QMessageBox::No | QMessageBox::Cancel, QMessageBox::No); if (include != QMessageBox::Cancel) exportPreferences(file, include == QMessageBox::Yes); } return; }
        if (action == "importSettings") { const auto file = QFileDialog::getOpenFileName(this, "Import QPE settings", {}, "JSON (*.json)"); if (!file.isEmpty() && QMessageBox::question(this, "Import settings", "Replace matching QPE settings?", QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) == QMessageBox::Yes) { importPreferences(file); const auto state = readSettings(); const auto appearance = state[host_.maya ? "nativeMayaAppearance" : "nativeAppearance"].toObject(); const auto legacy = state[host_.maya ? "mayaAppearance" : "standaloneAppearance"].toObject(); textSize_ = qBound(10, appearance["textSize"].toInt(legacy["fontSize"].toInt(textSize_)), 24); theme_ = appearance["theme"].toString(host_.maya ? theme_ : state["standaloneTheme"].toString(theme_)); uiPercent_ = qBound(75, appearance["uiPercent"].toInt(legacy["uiPercent"].toInt(uiPercent_)), 200); density_ = appearance["density"].toString(legacy["density"].toString(density_)); applyAppearance(); installCommandKeys(); updatePlaces(); } return; }
        if (action == "saveTabs" || action == "loadTabs" || action == "deleteTabs") {
            const auto settings = readSettings(); auto sets = settings.contains("nativeTabSets") ? settings["nativeTabSets"].toObject() : settings["tabSets"].toObject(); bool ok = false;
            const auto name = action == "saveTabs" ? QInputDialog::getText(this, "Save tab set", "Name", QLineEdit::Normal, {}, &ok)
                : QInputDialog::getItem(this, "Tab sets", "Name", sets.keys(), 0, false, &ok);
            if (!ok || name.trimmed().isEmpty()) return;
            if (action == "saveTabs") {
                if (sets.contains(name) && QMessageBox::question(this, "Replace tab set", name, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                QJsonArray values; for (int i = 0; i < pages_->count(); ++i) values.append(qobject_cast<BrowserPage*>(pages_->widget(i))->state()); sets[name] = QJsonObject{{"states", values}, {"active", tabs_->currentIndex()}};
            }
            else if (action == "loadTabs") {
                previousTabSet_ = {}; for (int i = 0; i < pages_->count(); ++i) previousTabSet_.append(qobject_cast<BrowserPage*>(pages_->widget(i))->state());
                const auto saved = sets[name]; const auto values = saved.isArray() ? saved.toArray() : saved.toObject()["states"].toArray();
                if (values.isEmpty()) return;
                const int oldCount = pages_->count();
                for (const auto& value : values) { const auto state = value.isString() ? QJsonObject{{"path", value.toString()}} : value.toObject(); if (state["path"].toString().isEmpty()) continue; addTab(state["path"].toString()); page()->restoreState(state); }
                if (pages_->count() > oldCount) for (int i = oldCount - 1; i >= 0; --i) { auto* old = pages_->widget(i); pages_->removeWidget(old); tabs_->removeTab(i); delete old; }
                tabs_->setCurrentIndex(qBound(0, saved.toObject()["active"].toInt(), tabs_->count() - 1)); return;
            }
            else sets.remove(name);
            writeSettings({{"nativeTabSets", sets}}); return;
        }
        if (action == "tag") {
            if (paths.isEmpty()) return; auto values = readSettings()["fileLabels"].toObject();
            const auto key = [](const QString& path) { return QDir::toNativeSeparators(QFileInfo(path).absoluteFilePath()).toLower(); };
            const auto initial = paths.size() == 1 ? values[key(paths[0])].toObject() : QJsonObject();
            QDialog dialog(this); dialog.setWindowTitle("QPE labels (local to this user)"); auto* form = new QFormLayout(&dialog);
            QStringList names; for (const auto& tag : initial["tags"].toArray()) names.append(tag.toString());
            QLineEdit tags(names.join(", ")), collection(initial["collection"].toString()); QSpinBox rating; rating.setRange(0, 5); rating.setValue(initial["rating"].toInt());
            form->addRow("Tags (comma separated)", &tags); form->addRow("Collection", &collection); form->addRow("Rating (0–5)", &rating);
            QDialogButtonBox buttons(QDialogButtonBox::Save | QDialogButtonBox::Cancel); form->addRow(&buttons);
            connect(&buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept); connect(&buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
            if (dialog.exec() == QDialog::Accepted) {
                QJsonArray entries; QSet<QString> seen;
                for (const auto& value : tags.text().split(',')) if (!value.trimmed().isEmpty() && !seen.contains(value.trimmed())) { seen.insert(value.trimmed()); entries.append(value.trimmed()); }
                for (const auto& path : paths) values[key(path)] = QJsonObject{{"tags", entries}, {"collection", collection.text().trimmed()}, {"rating", rating.value()}};
                writeSettings({{"fileLabels", values}});
            }
            return;
        }
        if (action == "batchRename") {
            if (paths.isEmpty()) return;
            QDialog dialog(this); dialog.setObjectName("batchRenameDialog"); dialog.setWindowTitle("Batch Rename — preview before applying"); dialog.resize(750, 500);
            auto* layout = new QVBoxLayout(&dialog); auto* form = new QFormLayout; layout->addLayout(form);
            QLineEdit find, replace, prefix, suffix; QCheckBox numbered("Add sequence number"), regex("Use regular expression"); QSpinBox first, digits;
            find.setObjectName("renameFind"); replace.setObjectName("renameReplace"); prefix.setObjectName("renamePrefix"); regex.setObjectName("renameRegex");
            first.setRange(0, 999999); first.setValue(1); digits.setRange(1, 8); digits.setValue(3);
            form->addRow("Find in base name", &find); form->addRow("Replace with", &replace); form->addRow("Prefix", &prefix); form->addRow("Suffix before extension", &suffix);
            form->addRow(&regex); form->addRow(&numbered); form->addRow("Start", &first); form->addRow("Digits", &digits);
            QTreeWidget preview; preview.setHeaderLabels({"Original", "New name"}); layout->addWidget(&preview);
            QLabel problem; problem.setObjectName("renameProblem"); problem.setWordWrap(true); layout->addWidget(&problem);
            QDialogButtonBox buttons(QDialogButtonBox::Apply | QDialogButtonBox::Cancel); layout->addWidget(&buttons); QJsonObject names;
            const auto update = [&] {
                names = {}; preview.clear(); QStringList errors; QSet<QString> targets;
                const QRegularExpression expression(find.text());
                if (regex.isChecked() && !expression.isValid()) errors.append(expression.errorString());
                for (int i = 0; i < paths.size(); ++i) {
                    const QFileInfo info(paths[i]); const auto extension = info.isDir() || info.suffix().isEmpty() ? QString() : '.' + info.suffix();
                    QString base = extension.isEmpty() ? info.fileName() : info.completeBaseName();
                    if (!find.text().isEmpty()) {
                        if (regex.isChecked()) { if (expression.isValid()) base.replace(expression, replace.text()); }
                        else base.replace(find.text(), replace.text());
                    }
                    auto name = prefix.text() + base + suffix.text(); if (numbered.isChecked()) name += QString::number(first.value() + i).rightJustified(digits.value(), '0'); name += extension;
                    new QTreeWidgetItem(&preview, {info.fileName(), name}); if (name != info.fileName()) names[paths[i]] = name;
                    try { validateFileName(name); } catch (const std::exception& e) { errors.append(QString::fromUtf8(e.what())); }
                    const auto target = info.dir().absoluteFilePath(name).toCaseFolded();
                    if (targets.contains(target) || (QFileInfo::exists(target) && target != info.absoluteFilePath().toCaseFolded())) errors.append("Destination already exists or is duplicated: " + name);
                    targets.insert(target);
                }
                errors.removeDuplicates(); problem.setText(errors.join('\n')); problem.setVisible(!errors.isEmpty());
                preview.resizeColumnToContents(0); buttons.button(QDialogButtonBox::Apply)->setEnabled(!names.isEmpty() && errors.isEmpty());
            };
            for (auto* field : {&find, &replace, &prefix, &suffix}) connect(field, &QLineEdit::textChanged, &dialog, update);
            connect(&regex, &QCheckBox::toggled, &dialog, update); connect(&numbered, &QCheckBox::toggled, &dialog, update); connect(&first, qOverload<int>(&QSpinBox::valueChanged), &dialog, update); connect(&digits, qOverload<int>(&QSpinBox::valueChanged), &dialog, update);
            connect(buttons.button(QDialogButtonBox::Apply), &QPushButton::clicked, &dialog, &QDialog::accept); connect(&buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject); update();
            if (dialog.exec() == QDialog::Accepted) jobs_->enqueue({"batchRename", names.keys(), {}, "rename", {{"names", names}}});
            return;
        }
        if (action == "open") {
            if (host_.maya && paths.size() > 1) {
                status_->setText("Select one file to open in Maya. Use Import or Reference for multiple files."); return;
            }
            for (const auto& path : paths) {
                if (QFileInfo(path).isDir()) { navigate(path); continue; }
                if (!QFileInfo::exists(path)) throw std::runtime_error("File no longer exists");
                const auto extension = QFileInfo(path).suffix().toLower();
                if (host_.maya && QStringList{"ma", "mb", "fbx"}.contains(extension)) {
                    if (mayaActionRunning_) return; QScopedValueRollback<bool> running(mayaActionRunning_, true);
                    if (!host_.perform(action, {path}, details_->options())) continue;
                }
                else if (!QDesktopServices::openUrl(QUrl::fromLocalFile(path))) throw std::runtime_error("Could not launch associated application");
                recents_.removeAll(path); recents_.prepend(path); recents_ = recents_.mid(0, 50);
            }
            writeSettings({{"recents", QJsonArray::fromStringList(recents_)}}); updatePlaces(); return;
        }
        if (QStringList{"new", "save", "saveAs", "export", "import", "reference", "options", "project", "sceneFolder", "sidecar", "namespaces"}.contains(action)) {
            if (action == "project" && host_.projectPath) { navigate(host_.projectPath()); return; }
            if (action == "sceneFolder" && host_.scenePath) { const auto scene = host_.scenePath(); if (!scene.isEmpty()) navigate(QFileInfo(scene).absolutePath()); return; }
            if (host_.perform && !mayaActionRunning_) { QScopedValueRollback<bool> running(mayaActionRunning_, true); if (host_.perform(action, paths, details_->options())) refresh(); } return;
        }
        if (action == "favorite") {
            for (const auto& path : paths) if (!favorites_.contains(path)) favorites_.append(path);
            writeSettings({{"favorites", QJsonArray::fromStringList(favorites_)}}); updatePlaces(); return;
        }
        if (action == "copy" || action == "cut" || action == "copyPath") {
            clipboardPending_ = true;
            writeClipboard(action, paths, ++clipboardGeneration_, GetClipboardSequenceNumber()); return;
        }
        FileRequest request; request.action = action == "copyTo" ? "copy" : action == "moveTo" ? "move" : action;
        request.paths = paths; request.destination = directory.isEmpty() ? currentPath() : directory;
        if (action == "paste") {
            if (clipboardPending_) { status_->setText("Clipboard is busy. Wait for Copy to finish before pasting."); return; }
            const auto* mime = QApplication::clipboard()->mimeData(); if (!mime->hasUrls()) return;
            request.paths.clear(); for (const auto& url : mime->urls()) if (url.isLocalFile()) request.paths.append(url.toLocalFile());
            const auto effect = mime->data("Preferred DropEffect"); request.action = !effect.isEmpty() && effect[0] == 2 ? "move" : "copy";
        }
        if (action == "newFolder" || action == "newFile" || action == "rename") {
            if (action == "rename" && paths.size() != 1) throw std::runtime_error("Select one item to rename");
            if (action == "rename") {
                const auto target = paths[0];
                for (auto* view : findChildren<QAbstractItemView*>()) {
                    if (inlineRename(view, target, [this, target](const QString& name) {
                        try { if (name == QFileInfo(target).fileName()) return; validateFileName(name); jobs_->enqueue({"rename", {target}, {}, "rename", {{"name", name}}}); }
                        catch (const std::exception& error) { QMessageBox::warning(this, "Rename", QString::fromUtf8(error.what())); }
                    })) return;
                }
            }
            bool ok = false; const auto name = QInputDialog::getText(this, action == "rename" ? "Rename" : "Create", "Name", QLineEdit::Normal,
                action == "rename" ? QFileInfo(paths[0]).fileName() : action == "newFolder" ? "New folder" : "New file.txt", &ok);
            if (!ok) return; validateFileName(name);
            if (action == "rename") request.options["name"] = name; else request.destination = QDir(request.destination).filePath(name);
        }
        if (request.action == "copy" || request.action == "move") {
            bool conflicts = false; for (const auto& path : request.paths) if (QFileInfo::exists(QDir(request.destination).filePath(QFileInfo(path).fileName()))) conflicts = true;
            if (conflicts) { bool ok = false; QStringList choices{"Keep both", "Skip", "Replace (keep Undo backup)"}; if (request.action == "copy") choices.append("Merge folders (replace matching files; keep Undo backup)"); const QString mode = QInputDialog::getItem(this, "Existing items", "Conflict handling", choices, 0, false, &ok); if (!ok) return; request.conflict = mode == "Skip" ? "skip" : mode.startsWith("Replace") ? "replace" : mode.startsWith("Merge") ? "merge" : "rename"; }
        }
        if (request.conflict == "merge" && !confirmMerge(request)) return;
        if (action == "trash" && (paths.isEmpty() || QMessageBox::question(this, "Delete", "Move to Recycle Bin?\n" + paths.join('\n'), QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes)) return;
        jobs_->enqueue(request);
    } catch (const std::exception& error) { QMessageBox::warning(this, "QuickPathExplorer", QString::fromUtf8(error.what())); }
}
void BrowserWindow::contextMenu(QAbstractItemView* view, const QPoint& point, const QString& directory) {
    const auto index = view->indexAt(point).siblingAtColumn(0); const QString clicked = index.data(PathRole).toString(); QStringList paths;
    if (index.isValid()) {
        if (view->selectionModel()->isSelected(index)) for (const auto& row : selectedPathIndexes(view)) paths.append(row.data(PathRole).toString());
        else paths.append(clicked);
    }
    QMenu menu(view); menu.setAttribute(Qt::WA_NoMouseReplay);
    const QString destination = paths.size() == 1 && index.data(DirectoryRole).toBool() ? clicked : directory;
    const auto add = [&](QMenu* parent, const QString& label, const QString& action, bool enabled = true) {
        const auto targetDirectory = action == "paste" || action == "newFolder" || action == "newFile" ? destination : directory;
        parent->addAction(label, this, [this, action, paths, targetDirectory] { perform(action, paths, targetDirectory); })->setEnabled(enabled);
    };
    if (!paths.isEmpty()) {
        add(&menu, "Open", "open", paths.size() == 1); add(&menu, "Open with…", "openWith", paths.size() == 1 && !QFileInfo(clicked).isDir());
        if (QFileInfo(clicked).isDir()) menu.addAction("Open in new tab", this, [this, clicked] { addTab(clicked); });
        if (host_.maya && !QFileInfo(clicked).isDir()) { add(&menu, "Import", "import"); add(&menu, "Reference", "reference"); }
        menu.addSeparator(); add(&menu, "Cut", "cut"); add(&menu, "Copy", "copy"); add(&menu, "Rename…", "rename", paths.size() == 1); add(&menu, "Delete", "trash"); add(&menu, "Copy Path", "copyPath");
    }
    add(&menu, "Paste", "paste", QApplication::clipboard()->mimeData()->hasUrls());
    auto* create = menu.addMenu("New"); add(create, "New Folder…", "newFolder"); add(create, "New Text File…", "newFile");
    auto* organize = menu.addMenu("Organize"); add(organize, "Add to Favorites", "favorite", !paths.isEmpty()); add(organize, "Create Copy", "duplicate", !paths.isEmpty()); add(organize, "Undo file operation", "undo"); add(organize, "Redo file operation", "redo");
    add(organize, "Tags / rating / collection…", "tag", !paths.isEmpty());
    add(organize, "Batch Rename…", "batchRename", !paths.isEmpty());
    if (!paths.isEmpty()) {
        auto* archive = menu.addMenu("ZIP"); add(archive, "Create ZIP…", "createZip");
        if (paths.size() == 1 && QFileInfo(clicked).suffix().compare("zip", Qt::CaseInsensitive) == 0) { add(archive, "Browse ZIP…", "browseZip"); add(archive, "Extract ZIP…", "extractZip"); }
        add(&menu, "Properties", "properties", paths.size() == 1);
        if (QFileInfo(clicked).isDir()) add(organize, "Set as start folder", "startFolder");
    }
    add(organize, "Show in Windows Explorer", "explorer"); add(organize, "Open terminal here", "terminal");
    menu.addAction("Refresh", this, &BrowserWindow::refresh);
    menu.exec(view->viewport()->mapToGlobal(point));
}
void BrowserWindow::prepareHostShutdown() {
    saveTimer_->stop(); saveSession(); restoring_ = true;
    for (auto* timer : findChildren<QTimer*>()) timer->stop();
    for (auto* jobs : findChildren<FileJobs*>()) jobs->cancel();
    hide();
}
void BrowserWindow::closeEvent(QCloseEvent* event) {
    if (busy()) { QMessageBox::information(this, "QuickPathExplorer", "File operations are running. Wait or cancel them from Tools before closing."); event->ignore(); return; }
    saveTimer_->stop(); saveSession(); QWidget::closeEvent(event);
}
void BrowserWindow::query(const QString& action) {
    FileRequest request; request.action = action; request.paths = selectedPaths().isEmpty() ? QStringList{currentPath()} : selectedPaths(); request.options["hidden"] = hidden_;
    if (action == "search") {
        request.paths = QStringList{currentPath()};
        QDialog dialog(this); dialog.setWindowTitle("Search subfolders"); dialog.setObjectName("qpeSearchOptions"); dialog.resize(720, 620);
        auto* box = new QVBoxLayout(&dialog); auto* scroll = new QScrollArea; scroll->setWidgetResizable(true); auto* fields = new QWidget; auto* form = new QFormLayout(fields);
        form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow); form->setRowWrapPolicy(QFormLayout::WrapLongRows); scroll->setWidget(fields); box->addWidget(scroll);
        QLineEdit pattern, extensions, content, minimum, maximum, since, roots(currentPath()), exclude, tags; QCheckBox regex("Regular expression"), live("Refresh every 10 seconds"); QSpinBox days; days.setRange(0, 36500); QComboBox kind, tagMode; kind.addItems({"Files", "Folders", "Both"}); tagMode.addItems({"All", "Any"});
        QComboBox backend; backend.addItem("Folder scan", "scan"); backend.addItem("Everything CLI", "everything");
        QComboBox saved; saved.addItem("New search"); auto presets = readSettings()["savedSearches"].toObject(); for (const auto& name : presets.keys()) saved.addItem(name);
        form->addRow("Saved search", &saved); form->addRow("Scope folders (; separated)", &roots); form->addRow("Search using", &backend);
        form->addRow("Name / wildcard", &pattern); form->addRow(&regex); form->addRow("Extensions", &extensions); form->addRow("Text contains (up to 16 MB)", &content);
        form->addRow("Items", &kind); form->addRow("Exclude folders / relative paths (;)", &exclude); form->addRow("Minimum KiB", &minimum); form->addRow("Maximum KiB (blank: any)", &maximum); form->addRow("Modified within days (0: any)", &days); form->addRow("Modified since (ISO date)", &since); form->addRow("Tags (, separated)", &tags); form->addRow("Match tags", &tagMode); form->addRow(&live);
        connect(&saved, qOverload<int>(&QComboBox::currentIndexChanged), &dialog, [&](int i) {
            if (i == 0) return; const auto state = presets[saved.currentText()].toObject();
            pattern.setText(state["query"].toString()); extensions.setText(state["extensions"].toString(state["types"].toString())); content.setText(state["content"].toString());
            roots.setText(state["roots"].toString(state["root"].toString(currentPath()))); exclude.setText(state["exclude"].toString());
            const double unit = state["sizeUnit"].toString() == "bytes" || (!state.contains("sizeUnit") && state.contains("roots")) ? 1024.0 : 1.0; minimum.setText(QString::number(state["minimum"].toDouble() / unit)); maximum.setText(QString::number(state["maximum"].toDouble() / unit)); days.setValue(state["days"].toInt()); kind.setCurrentText(state["kind"].toString("Files")); tags.setText(state["tags"].toString()); tagMode.setCurrentText(state["tagMode"].toString("All")); live.setChecked(state["live"].toBool()); since.setText(state["since"].toString()); regex.setChecked(state["regex"].toBool()); backend.setCurrentIndex(state["backend"].toString() == "everything" ? 1 : 0);
        });
        const auto options = [&] { return QJsonObject{{"query", pattern.text()}, {"extensions", extensions.text()}, {"content", content.text()}, {"regex", regex.isChecked()},
            {"minimum", minimum.text().toDouble()}, {"maximum", maximum.text().toDouble()}, {"sizeUnit", "KiB"}, {"days", days.value()}, {"kind", kind.currentText()}, {"tags", tags.text()}, {"tagMode", tagMode.currentText()}, {"live", live.isChecked()}, {"since", since.text()}, {"hidden", hidden_}, {"roots", roots.text()}, {"exclude", exclude.text()}, {"backend", backend.currentData().toString()}}; };
        auto* save = new QPushButton("Save search…"); box->addWidget(save);
        connect(save, &QPushButton::clicked, &dialog, [&] { bool ok = false; const auto name = QInputDialog::getText(&dialog, "Save search", "Name", QLineEdit::Normal, {}, &ok); if (!ok || name.isEmpty()) return;
            try { auto values = readSettings()["savedSearches"].toObject(); if (values.contains(name) && QMessageBox::question(&dialog, "Replace search", name, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return; values[name] = options(); writeSettings({{"savedSearches", values}}); presets = values; updatePlaces(); if (saved.findText(name) < 0) saved.addItem(name); saved.setCurrentText(name); }
            catch (const std::exception& e) { QMessageBox::warning(&dialog, "Save search", QString::fromUtf8(e.what())); }
        });
        auto* remove = new QPushButton("Delete saved search…"); box->addWidget(remove);
        connect(remove, &QPushButton::clicked, &dialog, [&] { if (saved.currentIndex() <= 0) return; const auto name = saved.currentText(); if (QMessageBox::question(&dialog, "Delete saved search", name, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
            try { auto values = readSettings()["savedSearches"].toObject(); values.remove(name); writeSettings({{"savedSearches", values}}); presets = values; updatePlaces(); saved.removeItem(saved.currentIndex()); } catch (const std::exception& e) { QMessageBox::warning(&dialog, "Settings", QString::fromUtf8(e.what())); }
        });
        auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel); box->addWidget(buttons);
        connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
            bool lowOk = true, highOk = true; const auto low = minimum.text().isEmpty() ? 0.0 : minimum.text().toDouble(&lowOk); const auto high = maximum.text().isEmpty() ? 0.0 : maximum.text().toDouble(&highOk);
            if (!lowOk || !highOk || low < 0 || high < 0 || (high > 0 && high < low)) { QMessageBox::warning(&dialog, "Search", "Enter non-negative sizes. Maximum must be at least Minimum."); return; }
            if (!since.text().isEmpty() && !QDate::fromString(since.text(), Qt::ISODate).isValid()) { QMessageBox::warning(&dialog, "Search", "Use YYYY-MM-DD for Modified since."); return; }
            if (roots.text().trimmed().isEmpty()) { roots.setFocus(); return; } dialog.accept();
        }); connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        if (dialog.exec() != QDialog::Accepted) return;
        request.options = options(); request.options["minimum"] = minimum.text().toDouble() * 1024; request.options["maximum"] = maximum.text().toDouble() * 1024; request.paths.clear(); for (const auto& value : roots.text().split(';', Qt::SkipEmptyParts)) request.paths.append(value.trimmed());
    } else if (action == "compare") {
        request.paths = QStringList{currentPath()}; request.destination = QFileDialog::getExistingDirectory(this, "Compare with folder"); if (request.destination.isEmpty()) return;
    }
    if (action == "search") { if (request.paths.isEmpty()) throw std::invalid_argument("Choose search scope folders"); streamingSearch(request); } else jobs_->enqueue(request);
}
void BrowserWindow::showQuery(const QJsonObject& result) {
    auto* dialog = new QDialog(this); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setWindowTitle(result["query"].toString()); dialog->resize(900, 550);
    auto* layout = new QVBoxLayout(dialog);
    layout->addWidget(new QLabel(QString("%1 files · %2 folders · %3").arg(result["files"].toDouble()).arg(result["directories"].toDouble()).arg(QLocale().formattedDataSize(qint64(result["bytes"].toDouble())))));
    auto* list = new QTreeWidget; list->setHeaderLabels({"Path", "Size", "SHA-256 / State"}); list->setSelectionMode(QAbstractItemView::ExtendedSelection); layout->addWidget(list);
    for (const auto& value : result["rows"].toArray()) {
        const auto row = value.toObject(); const auto path = row["path"].toString(); auto* item = new QTreeWidgetItem(list, {path, QLocale().formattedDataSize(qint64(row["size"].toDouble())), row.contains("sha256") ? row["sha256"].toString() : row["state"].toString()}); item->setData(0, PathRole, path);
        QStringList matches; for (const auto& match : row["matches"].toArray()) matches.append(match.toString()); item->setToolTip(0, matches.join('\n'));
    }
    list->header()->setSectionResizeMode(0, QHeaderView::Stretch); list->setColumnWidth(1, 100); list->setColumnWidth(2, 260);
    if (!result["detail"].toString().isEmpty()) { auto* detail = new QTextEdit; detail->setReadOnly(true); detail->setPlainText(result["detail"].toString()); detail->setMaximumHeight(180); layout->addWidget(detail); }
    connect(list, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item) { const auto path = item->data(0, PathRole).toString(); navigate(QFileInfo(path).isDir() ? path : QFileInfo(path).absolutePath()); });
    list->setContextMenuPolicy(Qt::CustomContextMenu); connect(list, &QTreeWidget::customContextMenuRequested, this, [this, list](const QPoint& point) { contextMenu(list, point, currentPath()); });
    if (result["query"] == "browseZip") {
        auto* button = new QPushButton("Extract selected…"); layout->addWidget(button);
        connect(button, &QPushButton::clicked, dialog, [this, list, result] {
            const auto parent = QFileDialog::getExistingDirectory(this, "Choose parent folder"); if (parent.isEmpty()) return;
            bool ok = false; const auto name = QInputDialog::getText(this, "Extract selected", "New folder name", QLineEdit::Normal, "Extracted", &ok); if (!ok) return;
            try { validateFileName(name); QJsonArray entries; for (const auto* item : list->selectedItems()) entries.append(item->data(0, PathRole).toString());
                if (entries.isEmpty()) return; jobs_->enqueue({"extractZip", {result["archive"].toString()}, QDir(parent).filePath(name), "rename", {{"entries", entries}}});
            } catch (const std::exception& e) { QMessageBox::warning(this, "ZIP", QString::fromUtf8(e.what())); }
        });
    }
    if (result["query"] == "compare") {
        auto* button = new QPushButton("Copy selected changes → destination…"); layout->addWidget(button);
        connect(button, &QPushButton::clicked, dialog, [this, list, result] {
            if (list->selectedItems().isEmpty() || QMessageBox::question(this, "Copy changes", "Copy selected files and retain overwritten files for Undo?", QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
            try { for (const auto* item : list->selectedItems()) for (const auto& v : result["rows"].toArray()) { const auto row = v.toObject(); if (row["path"].toString() != item->data(0, PathRole).toString()) continue;
                jobs_->enqueue({"syncFile", {row["path"].toString()}, row["destination"].toString(), "replace"});
            } } catch (const std::exception& e) { QMessageBox::warning(this, "Copy changes", QString::fromUtf8(e.what())); }
        });
    }
    dialog->show();
}
void BrowserWindow::addTab(const QString& path) {
    const auto* previousPage = page();
    QJsonObject initial{{"path", path.isEmpty() ? QDir::homePath() : path}};
    if (!restoring_ && page()) {
        // 新規タブでも探索起点と領域比率は維持する。履歴・選択・場所ロックは共有しない。
        const auto previous = page()->newTabView();
        for (auto it = previous.begin(); it != previous.end(); ++it) initial[it.key()] = it.value();
    }
    auto* item = new BrowserPage(pages_, this);
    connect(item, &BrowserPage::layoutChanged, this, &BrowserWindow::scheduleSave);
    item->setHiddenFiles(hidden_);
    if (!restoring_ && previousPage) item->primeFrom(*previousPage);
    pages_->addWidget(item);
    connect(item, &BrowserPage::locationChanged, this, [this, item] {
        const int index = pages_->indexOf(item);
        const QString name = QFileInfo(item->path()).fileName();
        tabs_->setTabText(index, name.isEmpty() ? item->path() : name);
        tabs_->setTabToolTip(index, item->path());
        if (page() == item) updateCurrent();
    });
    connect(item, &BrowserPage::selected, this, [this, item](const QString& selected) { if (page() == item) showDetails(selected); });
    const int index = tabs_->addTab(nativeFolderIcon(), "New tab");
    tabs_->setCurrentIndex(index);
    item->restoreState(initial);
}
void BrowserWindow::reopenTab() {
    if (closedTabs_.isEmpty()) return; const auto state = closedTabs_.last().toObject(); closedTabs_.removeLast();
    addTab(state["path"].toString()); page()->restoreState(state);
}
void BrowserWindow::navigate(const QString& path) { if (page()) page()->navigate(path); else addTab(path); }
QString BrowserWindow::currentPath() const { return page() ? page()->path() : QString(); }
bool BrowserWindow::ready() const { return page() && page()->ready(); }
void BrowserWindow::updateCurrent() {
    // 表示はWindows形式にし、列挙・履歴の内部パスは従来の正規化値を保持する。
    address_->setText(QDir::toNativeSeparators(currentPath()));
    if (!currentPath().isEmpty()) { pathHistory_.removeAll(currentPath()); pathHistory_.prepend(currentPath()); pathHistory_ = pathHistory_.mid(0, 30); }
    back_->setEnabled(page() && page()->canHistory(-1));
    forward_->setEnabled(page() && page()->canHistory(1));
    // タブ切替では選択モデルは変わらずselectedシグナルも来ないため、保持された対象を読み直す。
    showDetails(page() ? page()->detailPath() : QString()); details_->setDirectory(currentPath());
    sidebar_->setProperty("currentDrive", currentPath().size() > 2 && currentPath()[1] == ':' ? currentPath().left(3) : QString()); sidebar_->viewport()->update();
    QTreeWidgetItem* currentPlace = nullptr;
    for (QTreeWidgetItemIterator it(sidebar_); *it; ++it) {
        const auto path = (*it)->data(0, PathRole).toString();
        if (!currentPlace && path.size() == 3 && currentPath().startsWith(path, Qt::CaseInsensitive)) currentPlace = *it;
        if ((*it)->data(0, DirectoryRole).toBool() && path.compare(currentPath(), Qt::CaseInsensitive) == 0) currentPlace = *it;
    }
    if (currentPlace) { QSignalBlocker block(sidebar_); sidebar_->setCurrentItem(currentPlace); }
    scheduleSave();
}
void BrowserWindow::showDetails(const QString& path) {
    selected_ = path; details_->setPath(path);
}
void BrowserWindow::applyAppearance() {
    // 旧stylesheetのパレットキャッシュを先に解除する。保持したままsetPaletteすると
    // 再polish時に以前の文字色が復活するため、明示テーマ切替で白地に白文字になる。
    setStyleSheet(QString());
    QSettings settings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", QSettings::NativeFormat);
    const bool light = theme_ == "finder" || theme_ == "light" || (theme_ == "system" && settings.value("AppsUseLightTheme", 1).toInt());
    const QString window = light ? "#f9f9f9" : "#222222", base = light ? "#ffffff" : "#191919";
    const QString text = light ? "#1a1a1a" : "#f2f2f2", border = light ? "#e5e5e5" : "#383838";
    const QString selection = light ? "#d9d9d9" : "#505050", alternate = light ? "#fafafa" : "#1d1d1d";
    QFont font = QApplication::font();
    const qreal scale = host_.dpi * uiPercent_ / 100.;
    font.setPixelSize(qRound(textSize_ * scale));
    setFont(font);
    static_cast<NavigationTabs*>(tabs_)->setScale(scale);
    const int rowHeight = qMax(qRound((density_ == "comfortable" ? 28 : 24) * scale), QFontMetrics(font).height() + qRound(6 * scale));
    setProperty("qpeUiScale", scale); setProperty("qpeRowHeight", rowHeight);
    for (auto* view : findChildren<QAbstractItemView*>()) { view->setProperty("qpeRowHeight", rowHeight); if (view->objectName() != "thumbnails") view->setIconSize(QSize(qRound(16 * scale), qRound(16 * scale))); view->doItemsLayout(); }
    auto colors = palette();
    colors.setColor(QPalette::Window, QColor(window)); colors.setColor(QPalette::WindowText, QColor(text));
    colors.setColor(QPalette::Base, QColor(base)); colors.setColor(QPalette::Text, QColor(text));
    colors.setColor(QPalette::Button, QColor(window)); colors.setColor(QPalette::ButtonText, QColor(text));
    colors.setColor(QPalette::Highlight, QColor(selection)); colors.setColor(QPalette::HighlightedText, QColor(text));
    colors.setColor(QPalette::AlternateBase, QColor(alternate));
    // ホストがダークでも、明示ライト表示の容量バー背景を暗色で残さない。
    colors.setColor(QPalette::Mid, QColor(light ? "#d6d6d6" : "#555555"));
    colors.setColor(QPalette::PlaceholderText, QColor(light ? "#707070" : "#a0a0a0"));
    setPalette(colors);
    setAutoFillBackground(true);
    setStyleSheet(QString(
        "QWidget#qpeNativeWindow { background:%1; color:%3; }"
        "QWidget { font-size:%7px; color:%3; background:%1; }"
        "QWidget#columnContainer { background:%2; }"
        "QLineEdit, QTextEdit { background:%2; color:%3; border:1px solid %4; border-radius:5px; padding:6px; }"
        "QToolButton { background:transparent; color:%3; border:0; padding:7px; border-radius:4px; }"
        "QToolButton:hover { background:%5; } QToolButton:disabled { color:#808080; }"
        "QTreeView, QListView { background:%2; alternate-background-color:%6; color:%3; border:0; }"
        "QListView#folderColumn { border-right:1px solid %4; }"
        "QTreeView::item:selected, QListView::item:selected { background:%5; color:%3; }"
        "QHeaderView::section { background:%2; color:%3; border:0; border-bottom:1px solid %4; padding:6px; }"
        "QTabBar#folderTabs::tab { background:transparent; color:%3; padding:8px; border-right:1px solid %4; }"
        "QTabBar#folderTabs::tab:selected { background:%2; border-top-left-radius:6px; border-top-right-radius:6px; }"
        "QScrollArea { border:0; } QScrollBar:vertical { background:transparent; width:8px; }"
        "QScrollBar:horizontal { background:transparent; height:8px; }"
        "QScrollBar::handle { background:#808080; border-radius:3px; min-height:24px; min-width:24px; }"
        "QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }"
        "QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }"
        "QSplitter::handle { background:%1; } QLabel#migrationNotice { color:#808080; }"
    ).arg(window, base, text, border, selection, alternate, QString::number(font.pixelSize())));
    // stylesheet再適用時に保持される子の旧パレットも更新する。
    // ホストや他ツールのパレットは変更せず、自分の所有するウィジェットだけに配布する。
    for (auto* child : findChildren<QWidget*>()) child->setPalette(colors);
    for (auto* button : findChildren<QToolButton*>()) {
        const auto source = button->property("qpeSourceIcon").toString();
        if (source.isEmpty()) continue;
        const int extent = qRound(16 * scale), pixels = qRound(extent * devicePixelRatioF());
        QIcon original(":/qpe/icons/" + source);
        auto image = original.pixmap(pixels, pixels).toImage().convertToFormat(QImage::Format_ARGB32);
        // 中立色の線だけをテーマへ合わせ、アイコンのアクセント色と透明度を保持する。
        for (int y = 0; y < image.height(); ++y) for (int x = 0; x < image.width(); ++x) {
            const auto old = image.pixelColor(x, y);
            if (old.alpha() && old.saturation() < 45 && old.lightness() > 140) {
                auto replacement = QColor(text); replacement.setAlpha(old.alpha()); image.setPixelColor(x, y, replacement);
            }
        }
        image.setDevicePixelRatio(devicePixelRatioF());
        button->setIcon(QIcon(QPixmap::fromImage(image))); button->setIconSize(QSize(extent, extent));
    }
    updateResponsiveLayout();
    scheduleSave();
}
void BrowserWindow::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    updateResponsiveLayout();
}
void BrowserWindow::updateResponsiveLayout() {
    // コンストラクターの最初のresizeでは、子ウィジェットはまだ存在しない。
    if (!details_ || !pages_ || !address_ || !sidebar_) return;
    const double scale = qMax(0.75, property("qpeUiScale").toDouble());
    const bool compact = width() < qRound(620 * scale);
    for (const auto& name : {"displaySettingsButton", "newSceneButton", "saveAsButton"})
        if (auto* button = findChild<QToolButton*>(name)) button->setVisible(!compact);
    if (auto* button = findChild<QToolButton*>("toolsButton")) button->setText(compact ? QString("…") : QString("Tools"));
    address_->setMinimumWidth(qRound(100 * scale));
    const bool full = width() < qRound(720 * scale) && !details_->isHidden();
    if (full != detailsFullWidth_) {
        // 全幅表示中のゼロ幅を通常レイアウトの比率として保存しない。
        if (full) horizontal_->setProperty("wideState", horizontal_->saveState());
        pages_->setVisible(!full); detailsFullWidth_ = full;
        if (!full && horizontal_->property("wideState").isValid()) {
            const bool detailsVisible = !details_->isHidden();
            horizontal_->restoreState(horizontal_->property("wideState").toByteArray());
            details_->setVisible(detailsVisible);
        }
    }
    sidebar_->setVisible(sidebarRequested_ && !full);
    if (secondPane_) {
        if (full && !secondPane_->isHidden()) { secondPane_->setProperty("responsiveHidden", true); secondPane_->hide(); }
        else if (!full && secondPane_->property("responsiveHidden").toBool()) { secondPane_->setProperty("responsiveHidden", false); secondPane_->show(); }
    }
}
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
bool BrowserWindow::nativeEvent(const QByteArray& type, void* message, qintptr* result) {
#else
bool BrowserWindow::nativeEvent(const QByteArray& type, void* message, long* result) {
#endif
    if (parentWidget()) return QWidget::nativeEvent(type, message, result);
    const auto* msg = static_cast<MSG*>(message);
    if (msg->message == WM_NCCALCSIZE && msg->wParam) {
        auto* rect = reinterpret_cast<RECT*>(msg->lParam);
        if (IsZoomed(msg->hwnd)) {
            MONITORINFO info{sizeof(MONITORINFO)};
            if (GetMonitorInfoW(MonitorFromWindow(msg->hwnd, MONITOR_DEFAULTTONEAREST), &info)) *rect = info.rcWork;
        }
        *result = 0; return true;
    }
    if (msg->message == WM_NCHITTEST) {
        POINT point{GET_X_LPARAM(msg->lParam), GET_Y_LPARAM(msg->lParam)};
        ScreenToClient(msg->hwnd, &point);
        const QPoint pos(qRound(point.x / devicePixelRatioF()), qRound(point.y / devicePixelRatioF()));
        if (!isMaximized()) {
            const bool l = pos.x() < 5, r = pos.x() >= width() - 5, t = pos.y() < 5, b = pos.y() >= height() - 5;
            if (l || r || t || b) {
                *result = t ? (l ? HTTOPLEFT : r ? HTTOPRIGHT : HTTOP) : b ? (l ? HTBOTTOMLEFT : r ? HTBOTTOMRIGHT : HTBOTTOM) : l ? HTLEFT : HTRIGHT;
                return true;
            }
        }
        const QPoint local = strip_->mapFrom(this, pos);
        *result = strip_->rect().contains(local) && !strip_->childAt(local) ? HTCAPTION : HTCLIENT;
        return true;
    }
    return QWidget::nativeEvent(type, message, result);
}
}
#include "browser_window.moc"
