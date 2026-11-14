/** @file native_browser.cpp
 * @brief Pythonへの行ごとの往復と全件Shellアイコン取得を避ける。
 */
#include "native_browser.h"
#include <QApplication>
#include <QCache>
#include <QCollator>
#include <QDateTime>
#include <QDir>
#include <QEvent>
#include <QIcon>
#include <QImage>
#include <QImageReader>
#include <QLocale>
#include <QPointer>
#include <QRegularExpression>
#include <QSortFilterProxyModel>
#include <QJsonObject>
#include <QScrollBar>
#include <QStandardItemModel>
#include <QStyledItemDelegate>
#include <QThreadPool>
#include <QTimer>
#include <QTreeView>
#include <QListView>
#include <QRunnable>
#include <QMutex>
#include <QMutexLocker>
#include <memory>
#include <cstring>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <objbase.h>

/** @brief GILを解放した呼出元で画像ヘッダー/縮小画像を読む。
 * @param path UTF-16パス。 @param output 呼出元所有のQImage。寸法だけならnullptr。
 * @param width 元画像の幅。 @param height 元画像の高さ。
 * @param error UTF-8エラーの出力先。 @param capacity エラー領域のバイト数。
 * @return 0は成功、1は読込失敗、2は画素上限超過。
 * @note MayaのQObject生成フックとPython QObject破棄のロック順序を逆転させない。
 * readerと内部QFileは同じワーカー内で生成/破棄し、UIやMaya APIへ触れない。
 */
extern "C" __declspec(dllexport) int qpeReadImage(
    const wchar_t* path, void* output, int* width, int* height, char* error, int capacity) {
    if (!path || !width || !height || !error || capacity < 1) return 1;
    error[0] = '\0';
    *width = *height = 0;
    try {
        QImageReader reader(QString::fromWCharArray(path));
        const QSize size = reader.size();
        *width = size.width();
        *height = size.height();
        if (output && size.isValid() && qint64(size.width()) * size.height() > 64000000) return 2;
        if (size.isValid() && !output) return 0;
        if (size.isValid()) {
            reader.setAutoTransform(true);
            reader.setScaledSize(size.scaled(720, 480, Qt::KeepAspectRatio));
            *static_cast<QImage*>(output) = reader.read();
            if (!static_cast<QImage*>(output)->isNull()) return 0;
        }
        const QByteArray message = reader.errorString().toUtf8();
        const int count = qMin(capacity - 1, int(message.size()));
        std::memcpy(error, message.constData(), count);
        error[count] = '\0';
    } catch (...) {
        // C ABI境界へC++例外を出さず、Python側で通常の読込失敗として表示する。
        return 1;
    }
    return 1;
}

namespace qpe {
namespace {
constexpr int PathRole = Qt::UserRole + 1;
constexpr int DirectoryRole = Qt::UserRole + 2;
constexpr int SortValueRole = Qt::UserRole + 3;
QList<QPointer<QObject>> objects;
// UIを閉じる処理をShellの応答待ちで止めない。DLL解除時に稼働中なら拒否する。
QPointer<QThreadPool> iconPool;

/** @brief QStandardItemの保持値を読む。Pythonの仮想dataへの往復を避ける。
 * @param index ソースモデルの索引。 @param role 役割。 @return 保持値。
 */
QVariant stored(const QModelIndex& index, int role = Qt::DisplayRole) {
    auto model = qobject_cast<const QStandardItemModel*>(index.model());
    auto item = model && index.isValid() ? model->itemFromIndex(index) : nullptr;
    return item ? item->data(role) : QVariant();
}

/** @brief 表示・比較・検索をC++で行い、ソースの世代管理は変更しない。 */
class FileProxy final : public QSortFilterProxyModel {
public:
    /** @brief 親に所有させる。 @param parent 所有者。 */
    explicit FileProxy(QObject* parent) : QSortFilterProxyModel(parent) { nameCollator_.setNumericMode(true); }
    /** @brief 更新時に整形済みの値を描画し、再描画での単位変換を避ける。
     * @param index 表示索引。 @param role 役割。 @return 表示値。
     */
    QVariant data(const QModelIndex& index, int role) const override {
        auto source = mapToSource(index);
        return stored(source, role);
    }
protected:
    /** @brief ファイル名検索と現在ルート直下のフォルダー除外。 @param row 行。 @param parent 親。 @return 採用か。 */
    bool filterAcceptsRow(int row, const QModelIndex& parent) const override {
        auto model = qobject_cast<QStandardItemModel*>(sourceModel());
        if (!model) return false;
        auto item = parent.isValid() ? model->itemFromIndex(parent) : model->invisibleRootItem();
        auto child = item ? item->child(row) : nullptr;
        if (!child) return false;
        if (property("qpeNativePresentation").toBool()) {
              if (property("tagFilterActive").toBool() && !property("tagPaths").toJsonObject().contains(QDir::fromNativeSeparators(child->data(PathRole).toString()).toLower())) return false;
            if (child->data(DirectoryRole).toBool() && !property("includeFolders").toBool()) return false;
            const auto extensions = property("extensions").toStringList();
            if (!extensions.isEmpty() && !child->data(DirectoryRole).toBool() && !extensions.contains(QFileInfo(child->data(PathRole).toString()).suffix().toLower())) return false;
        }
        if (child->data(DirectoryRole).toBool()) {
            auto root = property("directoryRoot").toString();
            auto path = QDir::fromNativeSeparators(item->data(PathRole).toString()).toLower();
            while (path.endsWith('/')) path.chop(1);
            return root.isEmpty() || root != path;
        }
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
        return filterRegularExpression().match(child->text()).hasMatch();
#else
        return filterRegExp().indexIn(child->text()) >= 0;
#endif
    }
    /** @brief サイズ・日時・文字列の順序を維持する。
     * @param left 左。 @param right 右。 @return 左が小さいか。
     */
    bool lessThan(const QModelIndex& left, const QModelIndex& right) const override {
        auto a = stored(left, SortValueRole), b = stored(right, SortValueRole);
        if (left.column() == 1 || left.column() == 5 || left.column() == 7) return a.toLongLong() < b.toLongLong();
        if (left.column() == 3) return a.toDateTime() < b.toDateTime();
        if (left.column() == 0) {
            // Explorerの番号付き名前に合わせ、file2をfile10より先にする。比較器を毎行作らない。
            if (nameCollator_.caseSensitivity() != sortCaseSensitivity()) nameCollator_.setCaseSensitivity(sortCaseSensitivity());
            return nameCollator_.compare(a.toString(), b.toString()) < 0;
        }
        return QString::compare(a.toString(), b.toString(), sortCaseSensitivity()) < 0;
    }
private:
    mutable QCollator nameCollator_;
};

/** @brief 既存配色を維持した行高だけの高速デリゲート。 */
class FileDelegate final : public QStyledItemDelegate {
public:
    /** @brief ビューが所有する。 @param parent ファイルビュー。 */
    explicit FileDelegate(QObject* parent) : QStyledItemDelegate(parent) { setProperty("qpeNativeDelegate", true); }
    /** @brief Mayaの補助列だけ文字の強弱を付け、名前と選択中の可読性を維持する。
     * @param option 描画情報。 @param index 対象セル。
     */
    void initStyleOption(QStyleOptionViewItem* option, const QModelIndex& index) const override {
        QStyledItemDelegate::initStyleOption(option, index);
        const auto secondary = parent()->property("qpeSecondaryText").toString();
        if (index.column() > 0 && !secondary.isEmpty() && !(option->state & QStyle::State_Selected))
            option->palette.setColor(QPalette::Text, QColor(secondary));
    }

    /** @brief DPIとユーザー指定を反映する。
     * @param option 描画情報。 @param index 項目。 @return 寸法。
     */
    QSize sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        auto size = QStyledItemDelegate::sizeHint(option, index);
        size.setHeight(qMax(parent()->property("qpeRowHeight").toInt(), option.fontMetrics.height() + 4));
        return size;
    }
};

/** @brief HICONをGUI依存のない画像へ移す。
 * @param path ファイル名。 @param smallIcon 小さいアイコンか。 @param genericFolder 実在照会を省くか。 @return RGBA画像。
 */
QImage shellImage(const QString& path, bool smallIcon, bool genericFolder = false) {
    SHFILEINFOW info{};
    const auto nativePath = QDir::toNativeSeparators(path);
    if (!SHGetFileInfoW(reinterpret_cast<LPCWSTR>(nativePath.utf16()), genericFolder ? FILE_ATTRIBUTE_DIRECTORY : 0, &info, sizeof(info),
                       (genericFolder ? SHGFI_USEFILEATTRIBUTES : 0) | SHGFI_ICON | (smallIcon ? SHGFI_SMALLICON : SHGFI_LARGEICON))) return {};
    const int size = smallIcon ? 16 : 32;
    BITMAPINFO bitmap{};
    bitmap.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bitmap.bmiHeader.biWidth = size;
    bitmap.bmiHeader.biHeight = -size;
    bitmap.bmiHeader.biPlanes = 1;
    bitmap.bmiHeader.biBitCount = 32;
    bitmap.bmiHeader.biCompression = BI_RGB;
    void* pixels = nullptr;
    HDC dc = CreateCompatibleDC(nullptr);
    HBITMAP dib = CreateDIBSection(dc, &bitmap, DIB_RGB_COLORS, &pixels, nullptr, 0);
    QImage image;
    if (dc && dib && pixels) {
        auto old = SelectObject(dc, dib);
        memset(pixels, 0, size * size * 4);
        DrawIconEx(dc, 0, 0, info.hIcon, size, size, 0, nullptr, DI_NORMAL);
        image = QImage(static_cast<uchar*>(pixels), size, size, QImage::Format_ARGB32_Premultiplied).copy();
        SelectObject(dc, old);
    }
    if (dib) DeleteObject(dib);
    if (dc) DeleteDC(dc);
    DestroyIcon(info.hIcon);
    return image;
}

/** @brief ワーカーはQtウィジェットを参照せず、値だけ共有する。 */
struct IconResult {
    QMutex mutex;
    bool ready = false;
    QImage smallIcon, large;
};
/** @brief 最大2並列、GUIコールバックを待たないShell取得。 */
class IconJob final : public QRunnable {
    QString path;
    std::shared_ptr<IconResult> result;
public:
    /** @brief 入力をコピーする。 @param p ファイル。 @param r 結果の共有所有権。 */
    IconJob(QString p, std::shared_ptr<IconResult> r) : path(std::move(p)), result(std::move(r)) {}
    /** @brief COMをこのスレッドだけで初期化する。 */
    void run() override {
        const HRESULT initialized = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        auto smallIcon = shellImage(path, true), large = shellImage(path, false);
        { QMutexLocker lock(&result->mutex); result->smallIcon = smallIcon; result->large = large; result->ready = true; }
        if (SUCCEEDED(initialized)) CoUninitialize();
    }
};

/** @brief 可視行にだけ非同期アイコンを付け、古い索引・対象を照合する。 */
class VisibleIcons final : public QObject {
    QAbstractItemView* view;
    QTimer timer;
    QCache<QString, QIcon> cache{2048};
    struct Pending { QPersistentModelIndex index; QString key; std::shared_ptr<IconResult> result; };
    QList<Pending> pending;
    QHash<QPersistentModelIndex, QString> applied;
public:
    /** @brief ビュー所有。タイマーも部品破棄時に停止する。 @param v 対象ビュー。 */
    explicit VisibleIcons(QAbstractItemView* v) : QObject(v), view(v) {
        // QCoreApplicationより前にQObjectを静的生成しない。Qt所有にして終了順を保つ。
        if (!iconPool) iconPool = new QThreadPool(QCoreApplication::instance());
        iconPool->setMaxThreadCount(2);
        timer.setInterval(30);
        connect(&timer, &QTimer::timeout, this, [this]() { update(); });
        view->installEventFilter(this);
        view->viewport()->installEventFilter(this);
        connect(view->verticalScrollBar(), &QScrollBar::valueChanged, this, [this]() { wake(); });
        connect(view->horizontalScrollBar(), &QScrollBar::valueChanged, this, [this]() { wake(); });
        timer.start();
    }
    /** @brief 画面破棄は待たない。ジョブは独立した共有結果だけを所有する。 */
    ~VisibleIcons() override { timer.stop(); }
private:
    /** @brief 表示変化をまとめて処理する。アイコン取得待ちの間だけ定期実行する。 */
    void wake() { if (!timer.isActive()) timer.start(); }
    /** @brief モデル更新・ルート変更の再描画と表示範囲の変更で確認を再開する。
     * @param watched 監視するビューまたはviewport。 @param event Qtイベント。
     * @return 入力を消費しないため常にfalse。
     */
    bool eventFilter(QObject* watched, QEvent* event) override {
        Q_UNUSED(watched);
        if (event->type() == QEvent::Paint || event->type() == QEvent::Show || event->type() == QEvent::Resize) wake();
        return false;
    }
    /** @brief メタデータも照合して変更されたファイルの古い画像を排除する。
     * @param i 表示索引。 @return ファイルと内容世代を表すキー。
     */
    QString key(const QModelIndex& i) const {
        if (view->property("qpeIconPathRole").isValid())
            return i.data(view->property("qpeIconPathRole").toInt()).toString() + '\n' + i.data(Qt::UserRole + 101).toString();
        return i.data(PathRole).toString() + '\n' + i.sibling(i.row(), 1).data(SortValueRole).toString()
            + '\n' + QString::number(i.sibling(i.row(), 3).data(Qt::EditRole).toDateTime().toMSecsSinceEpoch());
    }
    /** @brief 結果反映と次の可視行要求。QPixmapはGUIスレッドだけで生成する。 */
    void update() {
        for (int n = pending.size() - 1; n >= 0; --n) {
            auto request = pending[n];
            QMutexLocker lock(&request.result->mutex);
            if (!request.result->ready) continue;
            QIcon icon;
            if (!request.result->smallIcon.isNull()) icon.addPixmap(QPixmap::fromImage(request.result->smallIcon));
            if (!request.result->large.isNull()) icon.addPixmap(QPixmap::fromImage(request.result->large));
            cache.insert(request.key, new QIcon(icon));
            setProperty("completed", property("completed").toInt() + 1);
            setProperty("lastImageValid", !icon.isNull());
            // キャッシュされた旧タブの索引は有効でも、現在ビューのモデルとは限らない。
            // 別モデルへsetDataすると警告や無関係な行の更新を起こすため、所有モデルも照合する。
            if (request.index.isValid() && request.index.model() == view->model() && key(request.index) == request.key) {
                if (!icon.isNull() && !request.index.data(Qt::UserRole + 102).toBool())
                    view->model()->setData(request.index, icon, Qt::DecorationRole);
                applied.insert(request.index, request.key);
                setProperty("applied", property("applied").toInt() + 1);
            }
            pending.removeAt(n);
        }
        if (!view->isVisible() || !view->model()) {
            if (pending.isEmpty()) timer.stop();
            return;
        }
        if (applied.size() > 4096) applied.clear();
        auto i = view->indexAt(QPoint(2, 2));
        int budget = qMax(2, view->viewport()->height() / qMax(12, view->property("qpeRowHeight").toInt()) + 2);
        auto tree = qobject_cast<QTreeView*>(view);
        if (auto grid = qobject_cast<QListView*>(view)) {
            const int width = qMax(1, grid->gridSize().width()), height = qMax(1, grid->gridSize().height());
            const int columns = qMax(1, view->viewport()->width() / width);
            i = view->indexAt(QPoint(qMin(width / 2, view->viewport()->width() - 1), height / 2));
            if (i.isValid()) i = view->model()->index(qMax(0, i.row() - columns), 0, view->rootIndex());
            budget = (view->viewport()->height() / height + 4) * columns;
        }
        if (!i.isValid()) i = view->model()->index(0, 0, view->rootIndex());
        for (; i.isValid() && budget-- > 0; i = tree ? tree->indexBelow(i) : view->model()->index(i.row() + 1, 0, view->rootIndex())) {
            const auto k = key(i);
            const int pathRole = view->property("qpeIconPathRole").isValid() ? view->property("qpeIconPathRole").toInt() : PathRole;
            // 上段カラムは共通フォルダーアイコン、サイドバーは標準フォルダー固有のShellアイコンを使う。
            if (i.data(pathRole).toString().isEmpty() || (i.data(DirectoryRole).toBool() && !view->property("qpeIconPathRole").isValid())
                || i.data(Qt::UserRole + 102).toBool() || applied.value(i) == k) continue;
            if (auto icon = cache.object(k)) {
                if (!icon->isNull()) view->model()->setData(i, *icon, Qt::DecorationRole);
                applied.insert(i, k);
                continue;
            }
            bool queued = false;
            for (const auto& p : pending) if (p.key == k) queued = true;
            if (queued || pending.size() >= 2) continue;
            auto result = std::make_shared<IconResult>();
            pending.append({i, k, result});
            setProperty("requested", property("requested").toInt() + 1);
            iconPool->start(new IconJob(i.data(pathRole).toString(), result));
        }
        if (pending.isEmpty()) timer.stop();
    }
};
}

QIcon nativeFolderIcon() { static const QIcon icon(QPixmap::fromImage(shellImage("folder", false, true))); return icon; }
QObject* createNative(const QString& kind, QWidget* parent) {
    QObject* object = nullptr;
    if (kind == "proxy") object = new FileProxy(parent);
    else if (kind == "delegate") object = new FileDelegate(parent);
    else if (kind == "icons") {
        if (auto view = qobject_cast<QAbstractItemView*>(parent)) object = new VisibleIcons(view);
    }
    if (object) objects.append(object);
    return object;
}
bool nativeObjectsReleased() {
    for (auto object : objects) if (object) return false;
    if (iconPool) {
        iconPool->clear();
        if (iconPool->activeThreadCount()) return false;
        // 稼働ジョブがない時だけアイドルスレッドをjoinし、DLL解除より先に破棄する。
        iconPool->waitForDone();
        delete iconPool;
    }
    objects.clear();
    return true;
}
}
