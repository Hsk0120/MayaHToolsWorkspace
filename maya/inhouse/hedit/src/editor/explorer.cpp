/** @file explorer.cpp
 * @brief Explorerと、フォルダーを別スレッドで読むDirectoryListerの実装。
 * @details 項目のデータの使い方:
 * - Qt::UserRole     : その項目のファイル/フォルダーの絶対パス。
 * - Qt::UserRole + 1 : trueなら「まだ中身を読んでいないフォルダー」。展開時に読む。
 * - Qt::UserRole + 2 : trueなら「中身を別スレッドで読んでいる途中」。
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
#include <QTreeWidgetItemIterator>
#include <QVBoxLayout>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>

namespace hedit {

/** @brief フォルダーの中身を別スレッドで読む。
 * @details 頼まれたフォルダーを順に読み、読み終えるたびにコンストラクターで受け取った関数を呼ぶ。
 * その関数は別スレッドから呼ばれるので、画面の部品には直接触れないこと(画面のスレッドへ送る)。
 * 破棄するときはスレッドを止めて合流する(hedit.mllのアンロード後にスレッドのコードが動かないように)。
 */
class DirectoryLister {
public:
    /// 読み終えたときに呼ぶ関数(フォルダー, 名前の一覧, 各項目がフォルダーか)。
    using Callback = std::function<void(const QString&, const QStringList&, const QList<bool>&)>;

    /** @brief スレッドを始める。 @param onListed 読み終えたときに呼ぶ関数。 */
    explicit DirectoryLister(Callback onListed) : onListed_(std::move(onListed)), worker_(&DirectoryLister::run, this) {}

    /** @brief スレッドを止めて合流する。読んでいる途中のフォルダーは、読み終わるまで待つ。 */
    ~DirectoryLister() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
        }
        wake_.notify_all();
        worker_.join();
    }

    /** @brief フォルダーの読み込みを頼む。 @param path フォルダーの絶対パス。 */
    void request(const QString& path) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            queue_.push_back(path);
        }
        wake_.notify_one();
    }

private:
    /** @brief 別スレッドの本体。頼まれたフォルダーを順に読む。 */
    void run() {
        while (true) {
            QString path;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                // 頼みごとか停止の合図が来るまで眠って待つ。
                wake_.wait(lock, [this] { return stopping_ || !queue_.empty(); });
                if (stopping_) {
                    return;
                }
                path = queue_.front();
                queue_.pop_front();
            }
            QStringList names;
            QList<bool> directories;
            const auto entries = QDir(path).entryInfoList(QDir::AllDirs | QDir::Files | QDir::NoDotAndDotDot,
                                                          QDir::DirsFirst | QDir::Name);
            for (const QFileInfo& info : entries) {
                if (info.isSymLink()) {
                    continue;  // リンク先へは降りない。
                }
                const QString suffix = info.suffix().toLower();
                if (!info.isDir() && suffix != "py" && suffix != "mel") {
                    continue;  // スクリプト以外のファイルは出さない。
                }
                if (info.isDir() && (info.fileName() == "__pycache__" || info.fileName() == ".git")) {
                    continue;
                }
                names.append(info.fileName());
                directories.append(info.isDir());
            }
            onListed_(path, names, directories);
        }
    }

    Callback onListed_;                ///< 読み終えたときに呼ぶ関数。
    std::mutex mutex_;                 ///< 下の2つを守る鍵。
    std::deque<QString> queue_;        ///< 読むフォルダーの順番待ち。
    bool stopping_ = false;            ///< trueでスレッドを止める。
    std::condition_variable wake_;     ///< スレッドを起こす合図。
    std::thread worker_;               ///< スレッド。他のメンバーを作った後で始めるよう、最後に置く。
};

namespace {

constexpr int kPathRole = Qt::UserRole;           ///< 絶対パスを入れる場所。
constexpr int kNotLoadedRole = Qt::UserRole + 1;  ///< 未読のフォルダーの印を入れる場所。
constexpr int kLoadingRole = Qt::UserRole + 2;    ///< 読んでいる途中の印を入れる場所。

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

    // 別スレッドで読み終えたら、画面のスレッドへ反映を送る。QueuedConnectionの処理は、画面のスレッドの
    // イベントループで実行される。送り先(this)が先に破棄されたら、未実行の処理は捨てられる。
    lister_ = std::make_unique<DirectoryLister>(
        [this](const QString& path, const QStringList& names, const QList<bool>& directories) {
            QMetaObject::invokeMethod(
                this, [this, path, names, directories] { applyListing(path, names, directories); },
                Qt::QueuedConnection);
        });

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
        notifyRootsChanged();
    });
    connect(tree_, &QTreeWidget::itemExpanded, this, [this](QTreeWidgetItem* item) { populate(item); });
    connect(tree_, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item, int) {
        const QString path = item->data(0, kPathRole).toString();
        if (QFileInfo(path).isFile() && onFileActivated) {
            onFileActivated(path);
        }
    });
}

Explorer::~Explorer() {
    // QObjectとしての破棄(送られた処理の取り消し)より前に、スレッドを止めて合流する。
    lister_.reset();
}

void Explorer::populate(QTreeWidgetItem* item) {
    if (!item->data(0, kNotLoadedRole).toBool()) {
        return;  // 読み込み済み、または読んでいる途中。
    }
    item->setData(0, kNotLoadedRole, false);
    item->setData(0, kLoadingRole, true);
    qDeleteAll(item->takeChildren());  // 仮の子「…」を消す。
    new QTreeWidgetItem(item, {"Loading…"});
    lister_->request(item->data(0, kPathRole).toString());
}

void Explorer::applyListing(const QString& path, const QStringList& names, const QList<bool>& directories) {
    // 読んでいる間に項目が消された(Removeなど)場合は、見つからないので何もしない。
    QList<QTreeWidgetItem*> targets;
    for (QTreeWidgetItemIterator it(tree_); *it; ++it) {
        if ((*it)->data(0, kLoadingRole).toBool() && (*it)->data(0, kPathRole).toString() == path) {
            targets.append(*it);
        }
    }
    const QDir directory(path);
    for (QTreeWidgetItem* item : targets) {
        item->setData(0, kLoadingRole, false);
        qDeleteAll(item->takeChildren());  // 「Loading…」を消す。
        for (int i = 0; i < names.size(); ++i) {
            const QString childPath = directory.absoluteFilePath(names[i]);
            auto child = new QTreeWidgetItem(item, {names[i]});
            child->setData(0, kPathRole, childPath);
            child->setIcon(0, style()->standardIcon(directories[i] ? QStyle::SP_DirIcon : QStyle::SP_FileIcon));
            child->setToolTip(0, childPath);
            if (directories[i]) {
                markNotLoaded(child);
            }
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

void Explorer::notifyRootsChanged() {
    if (onRootsChanged) {
        onRootsChanged();
    }
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
        if (replace) {
            notifyRootsChanged();
        }
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
    notifyRootsChanged();
}

void Explorer::setRoots(const QStringList& paths) {
    removeRootItems();
    for (const QString& path : paths) {
        addFolder(path);
    }
    notifyRootsChanged();
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
