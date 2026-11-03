/** @file cpp_migration_test.cpp
 * @brief 専用データで列挙の競合とタブ/カラム操作を検証するQtテスト。
 */
#include "../src/core/directory_store.h"
#include "../src/core/file_operations.h"
#include "../src/core/settings_store.h"
#include "../src/core/legacy_history.h"
#include "../src/core/shell_recycle.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QCryptographicHash>
#include <QLockFile>
#include "../src/browser/browser_window.h"
#include "../src/browser/inspector.h"
#include "../src/browser/group_proxy.h"
#include "../src/browser/navigation_widgets.h"
#include "../src/browser/ui_language.h"
#include "../src/browser/inspector.h"
#include <QAbstractItemModelTester>
#include <QStandardItemModel>
#include "../src/native_browser.h"
#include <QApplication>
#include <QAccessible>
#include <QDir>
#include <QFile>
#include <QTemporaryDir>
#include <QSignalSpy>
#include <QTabBar>
#include <QTabWidget>
#include <QStackedWidget>
#include <QCompleter>
#include <QTreeView>
#include <QListView>
#include <QLineEdit>
#include <QInputMethodEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QElapsedTimer>
#include <QSplitter>
#include <QComboBox>
#include <QCheckBox>
#include <QSpinBox>
#include <QToolButton>
#include <QPushButton>
#include <QLabel>
#include <QShortcut>
#include <QKeySequenceEdit>
#include <QDialog>
#include <QInputDialog>
#include <QMenu>
#include <QDialogButtonBox>
#include <QTreeWidget>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QTimer>
#include <QMimeData>
#include <QClipboard>
#include <QProcess>
#include <QProcessEnvironment>
#include <QDropEvent>
#include <QDragEnterEvent>
#include <QThreadPool>
#include <QtTest>
#include <future>
#include "../src/core/archive.h"
#include "../src/core/media_query.h"
#include "../src/core/media_decoder.h"
#include "../third_party/miniz/miniz.h"
#include <QImage>
#include <QStyleOptionFrame>
#include <QStandardPaths>
#include <QImageReader>
#define NOMINMAX
#include <windows.h>

/** @brief ユーザーデータへ触れず、実ワーカーと実Qtビューを検証する。 */
class MigrationTest final : public QObject {
    Q_OBJECT
private:
    QTemporaryDir data_{QCoreApplication::applicationDirPath() + "/fixtures-XXXXXX"};
    /** @brief 専用フォルダー下のパスを返す。
     * @param name 相対名。
     * @return 絶対パス。
     */
    QString path(const QString& name) const { return data_.path() + '/' + name; }
    /** @brief 専用データを作る。
     * @param name 相対ファイル名。
     * @param bytes サイズ。
     * @return 作成成功か。
     */
    bool file(const QString& name, int bytes = 8) {
        QFile output(path(name));
        return output.open(QIODevice::WriteOnly) && output.write(QByteArray(bytes, 'x')) == bytes;
    }
private slots:
    /** @brief 段階表示の追加行で配置が行数に比例せず、更新完了直後のUIAセルも有効である。 */
    void streamedRowsSettleOnce() {
        /** @brief 配置回数を計測する専用ビュー。 */
        class CountingTree final : public qpe::SettledTree<QTreeView> {
        public:
            int layouts = 0;
            /** @brief Qtの配置を維持して呼出回数を記録する。 */
            void doItemsLayout() override { ++layouts; QTreeView::doItemsLayout(); }
            /** @brief 実ビューと同じモデル接続順を作る。 @param model 専用モデル。 */
            void setModel(QAbstractItemModel* model) override { QTreeView::setModel(model); watchModel(); settle(); }
        } tree;
        QStandardItemModel model; model.setColumnCount(4);
        for (int row = 0; row < 100; ++row) model.appendRow(new QStandardItem(QString::number(row)));
        tree.setUniformRowHeights(true); tree.setModel(&model); tree.show(); QTest::qWait(10);
        SendMessageW(reinterpret_cast<HWND>(tree.winId()), WM_GETOBJECT, 0, -25);
        QVERIFY(QAccessible::isActive());
        tree.layouts = 0;
        tree.updateModel([&] {
            for (int row = 100; row < 2000; ++row) model.appendRow(new QStandardItem(QString::number(row)));
        });
        qInfo() << "streamed rows layouts" << tree.layouts;
        QVERIFY2(tree.layouts <= 2, "One directory snapshot must not lay out once per inserted row");
        QCOMPARE(model.rowCount(), 2000);
        auto* accessible = QAccessible::queryAccessibleInterface(&tree); QVERIFY(accessible);
        auto* cell = accessible->child(1); QVERIFY(cell);
        const auto id = QAccessible::uniqueId(cell); cell->state();
        QCOMPARE(QAccessible::accessibleInterface(id), cell);
    }
    /** @brief UIAと同じ順序の子取得・state照会で、遅延レイアウトが照会中のセルを破棄しない。 */
    void accessibleCellsSurviveNavigation() {
        qpe::BrowserWindow window; window.resize(1200, 800); window.show();
        // 自分のテスト窓へUIAの最初の照会を送り、Qtの実バックエンドを有効にする。
        SendMessageW(reinterpret_cast<HWND>(window.winId()), WM_GETOBJECT, 0, -25);
        QVERIFY(QAccessible::isActive());
        window.navigate(path("A")); QTRY_VERIFY(window.ready());
        auto* files = window.findChild<QTreeView*>("files"); QVERIFY(files);
        for (int turn = 0; turn < 12; ++turn) {
            window.navigate(path(turn % 2 ? "A" : "B")); QTRY_VERIFY(window.ready());
            files->setColumnWidth(0, 160 + turn * 5);
            files->hide(); files->show();
            window.perform(turn % 2 ? "view:Thumbnails" : "view:Details");
            files->setIconSize(QSize(17 + turn, 17 + turn));
            files->viewport()->resize(files->viewport()->width() - 1, files->viewport()->height());
            auto* accessible = QAccessible::queryAccessibleInterface(files); QVERIFY(accessible);
            for (int i = 0; i < accessible->childCount(); ++i) {
                auto* child = accessible->child(i); if (!child) continue;
                const auto id = QAccessible::uniqueId(child);
                child->state();
                QVERIFY2(QAccessible::accessibleInterface(id) == child, "state() invalidated the cell being inspected by UIA");
            }
        }
    }
    /** @brief Shell連携の所有者取得が、ドックの子階層や兄弟Qtをネイティブ化しない。 */
    void shellOwnerPreservesDockWidgets() {
        QWidget host; auto* layout = new QHBoxLayout(&host); auto* dock = new QWidget; layout->addWidget(dock);
        auto* inner = new QHBoxLayout(dock); auto* content = new QWidget; auto* sibling = new QLineEdit;
        inner->addWidget(content); inner->addWidget(sibling); host.show(); QTest::qWait(50);
        QVERIFY(!content->testAttribute(Qt::WA_NativeWindow)); QVERIFY(!dock->testAttribute(Qt::WA_NativeWindow));
        QVERIFY(!sibling->testAttribute(Qt::WA_NativeWindow));
        const auto owner = qpe::shellDialogOwner(content); QVERIFY(owner); QCOMPARE(owner, host.winId());
        QVERIFY(!content->testAttribute(Qt::WA_NativeWindow)); QVERIFY(!dock->testAttribute(Qt::WA_NativeWindow));
        QVERIFY(!sibling->testAttribute(Qt::WA_NativeWindow));
        QVERIFY_EXCEPTION_THROWN(qpe::shellDialogOwner(nullptr), std::invalid_argument);
    }
    /** @brief 設定が破損した製品を別プロセスで起動し、異常終了と原本上書きを防ぐ。 */
    void startupFailureReport() {
        const auto settings = path("invalid-startup.json"), report = path("invalid-startup-report.json");
        QFile original(settings); QVERIFY(original.open(QIODevice::WriteOnly));
        const QByteArray contents("{ invalid json"); QCOMPARE(original.write(contents), qint64(contents.size())); original.close();
        const auto directory = QCoreApplication::applicationDirPath();
        const auto exe = QFileInfo::exists(directory + "/QuickPathExplorer.exe") ? directory + "/QuickPathExplorer.exe" : directory + "/QuickPathExplorerNative.exe";
        auto environment = QProcessEnvironment::systemEnvironment(); environment.insert("QPE_SETTINGS_FILE", settings);
        QProcess process; process.setProcessEnvironment(environment); process.start(exe, {"--smoke", report});
        QVERIFY(process.waitForStarted()); QVERIFY(process.waitForFinished(15000));
        QCOMPARE(process.exitStatus(), QProcess::NormalExit); QCOMPARE(process.exitCode(), 1);
        const auto result = qpe::loadJson(report); QCOMPARE(result["phase"].toString(), QString("startup"));
        QVERIFY(!result["passed"].toBool()); QVERIFY(result["error"].toString().contains("Invalid JSON"));
        QVERIFY(original.open(QIODevice::ReadOnly)); QCOMPARE(original.readAll(), contents);
    }
    /** @brief Windows形式の開始パスを復元し、初回表示とペイン切替後の名前幅を確認する。 */
    void startupLayoutAndStartFolder() {
        const auto before = qpe::readSettings();
        QVERIFY(QDir().mkpath(path("startup-root/deep")));
        const auto root = QDir::toNativeSeparators(path("startup-root")).toUpper();
        qpe::writeSettings({{"nativeWorkspace", QJsonObject{{"states", QJsonArray{QJsonObject{{"path", path("startup-root/deep")}, {"startFolder", root}}}}}}});
        qpe::BrowserWindow window; window.restoreSession(); window.resize(1300, 700); window.show(); QTRY_VERIFY(window.ready());
        auto* columns = window.findChild<QScrollArea*>("folderColumns"); QVERIFY(columns);
        QTRY_COMPARE(columns->findChildren<QListView*>().size(), 2);
        auto* files = window.findChild<QTreeView*>("files"); QVERIFY(files);
        QTRY_VERIFY(qAbs(files->header()->length() - files->viewport()->width()) <= 2);
        window.findChild<QToolButton*>("navigationPaneButton")->click();
        QTRY_VERIFY(qAbs(files->header()->length() - files->viewport()->width()) <= 2);
        window.findChild<QToolButton*>("detailsPaneButton")->click();
        QTRY_VERIFY(qAbs(files->header()->length() - files->viewport()->width()) <= 2);
        window.close(); qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 多数フォルダーの縦バーが現れても、空間に余裕がある列の名前を省略しない。 */
    void columnScrollbarNameWidth() {
        for (int i = 0; i < 70; ++i) QVERIFY(QDir().mkpath(path(QString("column-scroll/Folder_%1").arg(i, 2, 10, QChar('0')))));
        qpe::BrowserWindow window; window.navigate(path("column-scroll")); window.perform("startFolder", {path("column-scroll")});
        window.resize(1200, 600); window.show(); QTRY_VERIFY(window.ready());
        const auto columns = window.findChildren<QListView*>("folderColumn"); QCOMPARE(columns.size(), 1);
        auto* column = columns.first(); QTRY_VERIFY(column->verticalScrollBar()->isVisible());
        QTRY_VERIFY(column->viewport()->width() >= column->fontMetrics().horizontalAdvance("Folder_00") + 52);
        window.close();
    }
    /** @brief UNCの親検査は共有内を保持し、サーバー自体をファイルとして検査しない。 */
    void uncOperationBoundary() {
        QCOMPARE(qpe::detail::operationAncestors("//qpe-test-server/share/folder/file.txt"),
                 QStringList({"//qpe-test-server/share/folder/file.txt", "//qpe-test-server/share/folder", "//qpe-test-server/share"}));
        QCOMPARE(qpe::detail::operationAncestors("//qpe-test-server/share/"), QStringList({"//qpe-test-server/share"}));
        QCOMPARE(qpe::detail::operationAncestors("Z:/folder/file.txt"), QStringList({"Z:/folder/file.txt", "Z:/folder", "Z:/"}));
        QCOMPARE(qpe::detail::operationAncestors("//qpe-test-server/share/folder/../file.txt"),
                 QStringList({"//qpe-test-server/share/file.txt", "//qpe-test-server/share"}));
        QVERIFY_EXCEPTION_THROWN(qpe::detail::operationAncestors("relative/file.txt"), std::invalid_argument);
    }
    /** @brief 狭い行と通常入力欄の余白が共存しても改名の字形領域を確保する。 */
    void inlineRenameTextGeometry() {
        for (const int pixels : {10, 12, 20}) {
            QTreeView view; QStandardItemModel model;
            auto* item = new QStandardItem(QString::fromUtf8("長いファイル名_original_scene.mb"));
            const QString target = path("長いファイル名_original_scene.mb");
            item->setData(target, Qt::UserRole + 1); model.appendRow(item); view.setModel(&model);
            QFont font = view.font(); font.setPixelSize(pixels); view.setFont(font);
            view.setStyleSheet("QLineEdit { padding:6px; } QTreeView::item { padding:0px; }");
            view.resize(520, 180); view.setColumnWidth(0, 150); view.show(); QTest::qWait(30);
            QVERIFY(qpe::inlineRename(&view, target, {}));
            auto* edit = view.findChild<QLineEdit*>("inlineRename"); QVERIFY(edit);
            QStyleOptionFrame option; option.initFrom(edit); option.rect = edit->rect();
            const auto contents = edit->style()->subElementRect(QStyle::SE_LineEditContents, &option, edit);
            QVERIFY2(contents.height() >= edit->fontMetrics().height(), "Rename glyphs must fit without vertical clipping");
            QVERIFY(edit->width() >= edit->fontMetrics().horizontalAdvance(edit->text()) + 12);
            QVERIFY(view.viewport()->rect().contains(edit->geometry()));
            QCOMPARE(edit->selectedText(), QString::fromUtf8("長いファイル名_original_scene"));
            QTest::keyClick(edit, Qt::Key_Escape);
            QTRY_VERIFY(!view.findChild<QLineEdit*>("inlineRename"));
        }
    }
    /** @brief 3表示とカラムで一覧内改名を行い、拡張子選択・中止・IME境界を確認する。 */
    void inlineRenameViews() {
        QVERIFY(QDir().mkpath(path("inline-folder/child"))); QVERIFY(file("inline-folder/original.txt"));
        qpe::BrowserWindow window; window.navigate(path("inline-folder")); window.show(); QTRY_VERIFY(window.ready());
        window.perform("area:balanced"); window.resize(1100, 1100); QTest::qWait(80);
        auto* vertical = window.findChild<QSplitter*>("browserVertical"); QVERIFY(vertical);
        const double areaBefore = double(vertical->sizes()[0]) / (vertical->sizes()[0] + vertical->sizes()[1]);
        auto* tree = window.findChild<QTreeView*>("files"); QVERIFY(tree);
        tree->setCurrentIndex(tree->model()->index(0, 0));
        window.perform("rename", {path("inline-folder/original.txt")});
        auto* editor = tree->findChild<QLineEdit*>("inlineRename"); QVERIFY(editor); QCOMPARE(editor->selectedText(), QString("original"));
        QInputMethodEvent preedit(QString::fromUtf8("仮"), {}); QApplication::sendEvent(editor, &preedit);
        QTest::keyClick(editor, Qt::Key_Return); QVERIFY(editor->isVisible()); QVERIFY(QFileInfo::exists(path("inline-folder/original.txt")));
        QInputMethodEvent committed; committed.setCommitString(QString::fromUtf8("変更")); QApplication::sendEvent(editor, &committed);
        editor->setText("renamed.txt"); QTest::keyClick(editor, Qt::Key_Return);
        QTRY_VERIFY(QFileInfo::exists(path("inline-folder/renamed.txt"))); QTRY_VERIFY(!window.busy());
        QTRY_VERIFY(tree->hasFocus());
        QTRY_COMPARE(window.selectedPaths(), QStringList{path("inline-folder/renamed.txt")});
        const double areaAfter = double(vertical->sizes()[0]) / (vertical->sizes()[0] + vertical->sizes()[1]);
        QVERIFY2(qAbs(areaAfter - areaBefore) < 0.02, "Rename must preserve the visible column/file area ratio");
        QCOMPARE(tree->currentIndex().data(Qt::UserRole + 1).toString(), path("inline-folder/renamed.txt"));
        window.perform("undo"); QTRY_VERIFY(!window.busy()); QTRY_COMPARE(window.selectedPaths(), QStringList{path("inline-folder/original.txt")});
        window.perform("redo"); QTRY_VERIFY(!window.busy()); QTRY_COMPARE(window.selectedPaths(), QStringList{path("inline-folder/renamed.txt")});
        QTRY_VERIFY(!tree->findChild<QLineEdit*>("inlineRename"));
        window.refresh(); QTRY_VERIFY(window.ready());
        window.perform("rename", {path("inline-folder/renamed.txt")}); editor = tree->findChild<QLineEdit*>("inlineRename"); QVERIFY(editor);
        editor->setText("cancelled.txt"); QTest::keyClick(editor, Qt::Key_Escape); QTRY_VERIFY(!tree->findChild<QLineEdit*>("inlineRename"));
        QTRY_VERIFY(tree->hasFocus());
        QVERIFY(!QFileInfo::exists(path("inline-folder/cancelled.txt")));
        for (const auto& mode : QStringList{"Thumbnails", "Extended details"}) {
            window.perform("view:" + mode);
            window.perform("rename", {path("inline-folder/renamed.txt")});
            editor = window.findChild<QLineEdit*>("inlineRename"); QVERIFY(editor); QVERIFY(editor->isVisible()); QTest::keyClick(editor, Qt::Key_Escape);
            QTRY_VERIFY(!window.findChild<QLineEdit*>("inlineRename"));
        }
        window.perform("rename", {path("inline-folder/child")}); editor = window.findChild<QLineEdit*>("inlineRename"); QVERIFY(editor);
        QCOMPARE(editor->selectedText(), QString("child")); editor->setText("renamed-folder"); QTest::keyClick(editor, Qt::Key_Return);
        QTRY_VERIFY(QFileInfo::exists(path("inline-folder/renamed-folder"))); QTRY_VERIFY(!window.busy()); window.close();
    }
    /** @brief 起動時に復元した上下比率がファイル改名によって再計算されない。 */
    void renameRestoredAreaLayout() {
        QVERIFY(QDir().mkpath(path("rename-layout/scenes"))); QVERIFY(file("rename-layout/scenes/before.txt"));
        qpe::saveJson(qpe::settingsPath(), {{"nativeWorkspace", QJsonObject{{"states", QJsonArray{
            QJsonObject{{"path", path("rename-layout/scenes")}, {"startFolder", path("rename-layout")}, {"areaMode", "balanced"}}}}}}});
        qpe::BrowserWindow window; window.restoreSession(); window.show(); QTRY_VERIFY(window.ready()); QTest::qWait(100);
        auto* vertical = window.findChild<QSplitter*>("browserVertical"); QVERIFY(vertical);
        const auto ratio = [vertical] { const auto sizes = vertical->sizes(); return double(sizes[0]) / (sizes[0] + sizes[1]); };
        const double before = ratio();
        const int heightBefore = vertical->height();
        auto* tree = window.findChild<QTreeView*>("files"); tree->setCurrentIndex(tree->model()->index(0, 0));
        window.perform("rename", {path("rename-layout/scenes/before.txt")});
        auto* editor = tree->findChild<QLineEdit*>("inlineRename"); QVERIFY(editor);
        editor->setText("after.txt"); QTest::keyClick(editor, Qt::Key_Return);
        QTRY_VERIFY(QFileInfo::exists(path("rename-layout/scenes/after.txt"))); QTRY_VERIFY(!window.busy());
        QTRY_COMPARE(window.selectedPaths(), QStringList{path("rename-layout/scenes/after.txt")});
        QVERIFY2(qAbs(before - ratio()) < 0.02, qPrintable(QString("Before %1; after %2").arg(before).arg(ratio())));
        QTRY_COMPARE(vertical->height(), heightBefore);
        window.close(); qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief 狭い右欄の操作選択と、ドライブ2行描画が子ウィジェットなしで成立する。 */
    void sidebarCompactPresentation() {
        qpe::Inspector inspector(true, nullptr); inspector.resize(220, 600); inspector.show();
        auto* selector = inspector.findChild<QComboBox*>("inspectorOperation"); QVERIFY(selector); QTRY_VERIFY(selector->isVisible());
        QCOMPARE(selector->count(), 4); selector->setCurrentIndex(3);
        auto* tabs = inspector.findChild<QTabWidget*>("readOptions"); QCOMPARE(tabs->currentIndex(), 3);
        QVERIFY(inspector.findChild<QPushButton*>("saveAs")->isVisible());
        inspector.resize(450, 600); QTRY_VERIFY(!selector->isVisible()); QVERIFY(tabs->tabBar()->isVisible());
        qpe::PlacesTree places; places.setHeaderHidden(true); places.resize(190, 300); places.show();
        auto* row = new QTreeWidgetItem(&places, {"A long drive name (C:)"}); row->setData(0, Qt::UserRole + 1, "C:/");
        row->setData(0, Qt::UserRole + 30, QJsonObject{{"total", 1000.0}, {"free", 60.0}}); places.setProperty("currentDrive", "C:/");
        QTRY_VERIFY(places.visualItemRect(row).height() >= places.fontMetrics().height() * 2 + 20);
        QVERIFY(!places.itemWidget(row, 0)); QVERIFY(places.findChildren<QLabel*>().isEmpty());
        QVERIFY(!places.grab().isNull()); inspector.close(); places.close();
        qpe::BrowserWindow narrow; narrow.restoreSession(path("A")); narrow.resize(380, 500); narrow.show(); QTRY_VERIFY(narrow.ready());
        auto* files = narrow.findChild<QTreeView*>("files"); QVERIFY(files); QTRY_VERIFY(files->columnWidth(0) >= 160);
        const int compactWidth = files->columnWidth(0); narrow.resize(1400, 700); QTRY_VERIFY(files->columnWidth(0) > compactWidth); narrow.close();
    }
    /** @brief 狭いMayaドックでもアドレスと詳細を読め、幅を戻すと左欄・一覧が復元される。 */
    void responsiveMayaDock() {
        const auto before = qpe::readSettings(); const auto palette = QApplication::palette();
        qpe::HostServices host; host.maya = true;
        QWidget parent; auto* layout = new QHBoxLayout(&parent);
        auto* window = new qpe::BrowserWindow(&parent, host); layout->addWidget(window);
        window->navigate(path("A")); parent.resize(1000, 600); parent.show(); QTRY_VERIFY(window->ready());
        auto* left = window->findChild<QToolButton*>("navigationPaneButton"); auto* right = window->findChild<QToolButton*>("detailsPaneButton");
        auto* places = window->findChild<QTreeWidget*>("places"); auto* inspector = window->findChild<qpe::Inspector*>(); auto* files = window->findChild<QTreeView*>("files");
        left->click(); QVERIFY(places->isVisible()); parent.resize(360, 600);
        QTRY_VERIFY(!window->findChild<QToolButton*>("newSceneButton")->isVisible());
        QVERIFY(window->findChild<QLineEdit*>("address")->width() >= 100);
        right->click(); QTRY_VERIFY(inspector->isVisible()); QVERIFY(!files->isVisible()); QVERIFY(!places->isVisible());
        QTRY_VERIFY(inspector->width() >= window->width() - 30);
        parent.resize(1100, 650); QTRY_VERIFY(files->isVisible()); QVERIFY(places->isVisible()); QVERIFY(inspector->isVisible());
        parent.resize(360, 600); QTRY_VERIFY(!files->isVisible()); right->click(); QTRY_VERIFY(files->isVisible()); QVERIFY(places->isVisible());
        QCOMPARE(window->currentPath(), qpe::DirectoryStore::normalized(path("A"))); QCOMPARE(QApplication::palette(), palette);
        parent.close(); window->close(); qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief Toolsの操作を分類して狭い画面で縦長にならず、各入口が残る。 */
    void categorizedToolsMenu() {
        qpe::HostServices host; host.maya = true; qpe::BrowserWindow window(nullptr, host); window.navigate(path("A")); window.show();
        bool seen = false;
        QTimer::singleShot(50, &window, [&] {
            auto* menu = window.findChild<QMenu*>("toolsMenu"); if (!menu) return;
            seen = menu->actions().size() <= 9 && menu->findChild<QMenu*>("toolsView") && menu->findChild<QAction*>("optionsAction") && menu->findChild<QMenu*>("toolsTabs");
            QStringList names; for (auto* child : menu->findChildren<QMenu*>()) for (auto* action : child->actions()) names.append(action->text());
            seen = seen && !names.contains("Theme") && !names.contains("External applications") && names.contains("New Scene") && names.contains("Saved searches") && names.contains("Undo file operation");
            // 項目の存在だけでは、実際にサブメニューへ進めない不具合を検出できない。
            auto* search = menu->findChild<QMenu*>("toolsSearch");
            QTest::mouseClick(menu, Qt::LeftButton, {}, menu->actionGeometry(search->menuAction()).center());
            QTest::qWait(100);
            seen = seen && search->isVisible();
            QTest::keyClick(search, Qt::Key_Escape);
            seen = seen && !search->isVisible() && menu->isVisible();
            QTest::keyClick(menu, Qt::Key_Escape);
            seen = seen && !menu->isVisible();
        });
        window.findChild<QToolButton*>("toolsButton")->click(); QVERIFY(seen); window.close();
    }
    /** @brief 標準フォルダーはRecent直下で登録先を指し、移動後も選択を維持する。 */
    void userFoldersSidebar() {
        qpe::BrowserWindow window; window.navigate(path("A")); window.show();
        auto* places = window.findChild<QTreeWidget*>("places"); QVERIFY(places);
        QCOMPARE(places->topLevelItem(1)->text(0), QString("Recent"));
        auto* desktop = places->topLevelItem(2); QCOMPARE(desktop->text(0), QString("Desktop"));
        QCOMPARE(places->topLevelItem(8)->text(0), QString("Drives"));
        QCOMPARE(desktop->data(0, Qt::UserRole + 1).toString(), QDir::cleanPath(QStandardPaths::writableLocation(QStandardPaths::DesktopLocation)));
        auto* documents = places->topLevelItem(3); QCOMPARE(documents->text(0), QString("Documents"));
        QCOMPARE(documents->data(0, Qt::UserRole + 1).toString(), QDir::cleanPath(QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation)));
        for (int row = 2; row < 8; ++row) {
            QVERIFY(places->topLevelItem(row)->data(0, Qt::UserRole + 2).toBool());
            QVERIFY(!places->topLevelItem(row)->icon(0).isNull());
            QCOMPARE(places->topLevelItem(row)->childCount(), 0);
        }
        const auto desktopIcon = desktop->icon(0).cacheKey();
        auto* toggle = window.findChild<QToolButton*>("navigationPaneButton"); toggle->click();
        QTRY_VERIFY_WITH_TIMEOUT(desktop->icon(0).cacheKey() != desktopIcon, 10000);
        for (int cycle = 0; cycle < 20; ++cycle) {
            toggle->click(); QTest::qWait(20);
            toggle->click(); QTest::qWait(20);
            QVERIFY(places->isVisible());
            QVERIFY(!places->visualItemRect(desktop).isEmpty());
        }
        // 実ユーザーのDocumentsは列挙せず、移動操作は専用データへ差し替えて調べる。
        documents->setData(0, Qt::UserRole + 1, qpe::DirectoryStore::normalized(path("B")));
        emit places->itemClicked(documents, 0);
        QTRY_COMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B")));
        QCOMPARE(places->currentItem(), documents);
        window.close();
    }
    /** @brief サイドバーのファイル・フォルダーも可視範囲のShellアイコンを非同期で取得する。 */
    void sidebarNativeIcons() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"favorites", QJsonArray{path("A"), path("B/別のファイル.txt")}}});
        qpe::BrowserWindow window; window.navigate(path("A")); window.show();
        auto* icons = window.findChild<QObject*>("placesIcons"); QVERIFY(icons);
        window.findChild<QToolButton*>("navigationPaneButton")->click();
        QTRY_VERIFY_WITH_TIMEOUT(icons->property("applied").toInt() >= 2, 10000);
        auto* places = window.findChild<QTreeWidget*>("places"); QCOMPARE(places->topLevelItem(0)->childCount(), 2);
        QVERIFY(!places->topLevelItem(0)->child(0)->icon(0).isNull()); QVERIFY(!places->topLevelItem(0)->child(1)->icon(0).isNull());
        window.close(); qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief ホスト別表示の倍率・最小文字・行間・列幅を変更して再起動後も戻す。 */
    void appearanceControls() {
        qpe::writeSettings({{"nativeAppearance", QJsonObject{{"textSize", 12}, {"uiPercent", 100}, {"density", "compact"}}}});
        {
            qpe::BrowserWindow window; window.restoreSession(path("A")); window.show(); QTRY_VERIFY(window.ready());
            QTimer::singleShot(0, &window, [&] {
                auto* dialog = window.findChild<QDialog*>("qpePreferences"); QVERIFY(dialog);
                auto* pixels = dialog->findChild<QSpinBox*>("displayFontSize"); auto* scale = dialog->findChild<QSpinBox*>("displayUiScale"); auto* density = dialog->findChild<QComboBox*>("displayDensity");
                QVERIFY(pixels && scale && density); pixels->setValue(10); scale->setValue(125); density->setCurrentIndex(1);
                QCOMPARE(window.font().pixelSize(), 13); QCOMPARE(window.findChild<QTreeView*>("files")->font().pixelSize(), 13); QCOMPARE(window.findChild<QTreeView*>("files")->property("qpeRowHeight").toInt(), 35);
                auto* widths = dialog->findChild<QComboBox*>("columnWidthMode"); widths->setCurrentIndex(1);
                dialog->findChild<QDialogButtonBox*>()->button(QDialogButtonBox::Save)->click();
            });
            window.perform("appearance"); QCOMPARE(qpe::readSettings()["columnWidthMode"].toString(), QString("names")); window.close();
        }
        { qpe::BrowserWindow next; next.restoreSession(path("A")); QCOMPARE(next.font().pixelSize(), 13); next.close(); }
        qpe::writeSettings({{"nativeAppearance", QJsonObject{{"textSize", 12}, {"uiPercent", 100}, {"density", "compact"}}}, {"columnWidthMode", "fit"}});
    }
    /** @brief OSの配色と逆の明示テーマでも、子の文字・空白領域・独自描画タブが同じ配色になる。 */
    void explicitThemeChildren() {
        const auto original = QApplication::palette();
        for (const QString theme : {QString("light"), QString("dark")}) {
            qpe::writeSettings({{"nativeAppearance", QJsonObject{{"theme", theme}}}});
            qpe::BrowserWindow window; window.restoreSession(path("A"), false); window.show(); QTRY_VERIFY(window.ready());
            const bool light = theme == "light";
            auto* tabs = window.findChild<QTabBar*>("folderTabs");
            auto* columns = window.findChild<QScrollArea*>("folderColumns");
            auto* footer = window.findChild<QLabel*>("footer");
            auto* types = window.findChild<QComboBox*>("fileTypes");
            for (QWidget* widget : QList<QWidget*>{tabs, columns->widget(), footer, types}) {
                QVERIFY2((widget->palette().color(QPalette::Window).lightness() > 128) == light,
                         qPrintable(theme + " " + widget->objectName() + " " + widget->palette().color(QPalette::Window).name()));
                QVERIFY2((widget->palette().color(QPalette::WindowText).lightness() < 128) == light, qPrintable(widget->objectName()));
            }
            window.addTab(path("B")); QTRY_VERIFY(window.ready());
            window.addTab(path("A")); QTRY_VERIFY(window.ready()); tabs->setCurrentIndex(1);
            QTest::mouseMove(&window, QPoint(100, window.height() - 30)); QTest::qWait(30);
            const auto tabImage = tabs->grab().toImage(); const auto dpr = tabImage.devicePixelRatio();
            const auto pixel = [&](const QPoint& point) { return tabImage.pixelColor(qRound(point.x() * dpr), qRound(point.y() * dpr)); };
            const auto activeColor = pixel(tabs->tabRect(1).topLeft() + QPoint(45, 5));
            const auto inactiveColor = pixel(tabs->tabRect(0).topLeft() + QPoint(45, 5));
            QVERIFY2(qAbs(activeColor.lightness() - inactiveColor.lightness()) >= 12, "Active tab surface must be distinct in both themes");
            auto* close = tabs->tabButton(1, QTabBar::RightSide); QVERIFY(close);
            const auto closeCorner = pixel(close->geometry().topLeft() + QPoint(1, 1));
            QVERIFY2(qAbs(closeCorner.lightness() - activeColor.lightness()) <= 4, "Close button must not cover the selected surface with an opaque box");
            for (auto* label : window.findChildren<QLabel*>("footer"))
                QVERIFY((label->palette().color(QPalette::WindowText).lightness() < 128) == light);
            const auto placeholder = window.findChild<QLineEdit*>("fileFilter")->palette().color(QPalette::PlaceholderText);
            QVERIFY(placeholder.lightness() >= 80 && placeholder.lightness() <= 190);
            QCOMPARE(window.findChild<QTreeWidget*>("places")->palette().color(QPalette::Mid),
                     QColor(light ? "#d6d6d6" : "#555555"));
            const auto glyph = window.findChild<QToolButton*>("navigationPaneButton")->icon().pixmap(32, 32).toImage();
            bool visibleLine = false;
            for (int y = 0; y < glyph.height(); ++y) for (int x = 0; x < glyph.width(); ++x) {
                const auto color = glyph.pixelColor(x, y);
                if (color.alpha() > 150 && color.saturation() < 45 && (color.lightness() < 128) == light) visibleLine = true;
            }
            QVERIFY(visibleLine);
            QCOMPARE(QApplication::palette(), original); window.close();
        }
    }
    /** @brief Explorerと同じ初期順・数値入り名前・昇降順の矢印を、白/暗の実描画で確認する。 */
    void explorerSortingPresentation() {
        const auto before = qpe::readSettings();
        QVERIFY(QDir().mkpath(path("sort-ui")));
        const QStringList names{"alpha.ma", "beta.txt", "file2.txt", "file10.txt", "gamma.mb"};
        const QList<int> sizes{2000, 500, 30, 40, 1000};
        for (int i = 0; i < names.size(); ++i) {
            QVERIFY(file("sort-ui/" + names[i], sizes[i]));
            QFile item(path("sort-ui/" + names[i])); QVERIFY(item.open(QIODevice::ReadWrite));
            QVERIFY(item.setFileTime(QDateTime(QDate(2026, 10, i + 1), QTime(12, 0), Qt::UTC), QFileDevice::FileModificationTime));
        }
        for (const auto& theme : {QString("light"), QString("dark")}) {
            qpe::writeSettings({{"nativeAppearance", QJsonObject{{"theme", theme}}}, {"folderViews", QJsonObject{}}});
            qpe::BrowserWindow window; window.restoreSession(path("sort-ui"), false); window.show(); QTRY_VERIFY(window.ready());
            auto* files = window.findChild<QTreeView*>("files"); auto* header = files->header();
            QCOMPARE(header->defaultAlignment(), Qt::Alignment(Qt::AlignLeft | Qt::AlignVCenter));
            QTRY_COMPARE(files->model()->rowCount(), names.size());
            for (int row = 0; row < names.size(); ++row) QCOMPARE(files->model()->index(row, 0).data().toString(), names[row]);
            const auto click = [&](int column) {
                QTest::mouseClick(header->viewport(), Qt::LeftButton, Qt::NoModifier, QPoint(header->sectionViewportPosition(column) + 12, header->height() / 2));
            };
            for (const int column : {1, 3, 2, 0}) {
                click(column);
                QCOMPARE(header->sortIndicatorSection(), column);
                const auto first = column == 1 || column == 3 ? Qt::DescendingOrder : Qt::AscendingOrder;
                QCOMPARE(header->sortIndicatorOrder(), first);
                for (int pass = 0; pass < 2; ++pass) {
                    const bool ascending = header->sortIndicatorOrder() == Qt::AscendingOrder;
                    for (int row = 1; row < files->model()->rowCount(); ++row) {
                        const auto a = files->model()->index(row - 1, column).data(Qt::UserRole + 3);
                        const auto b = files->model()->index(row, column).data(Qt::UserRole + 3);
                        if (column == 1) QVERIFY(ascending ? a.toLongLong() <= b.toLongLong() : a.toLongLong() >= b.toLongLong());
                        else if (column == 3) QVERIFY(ascending ? a.toDateTime() <= b.toDateTime() : a.toDateTime() >= b.toDateTime());
                        else if (column == 2) QVERIFY(ascending ? a.toString() <= b.toString() : a.toString() >= b.toString());
                    }
                    if (column == 0) for (int row = 0; row < names.size(); ++row)
                        QCOMPARE(files->model()->index(row, 0).data().toString(), names[ascending ? row : names.size() - row - 1]);
                    QVERIFY(files->model()->headerData(column, Qt::Horizontal, Qt::ToolTipRole).toString().contains(ascending ? "Ascending" : "Descending"));
                    QTest::mouseMove(&window, QPoint(100, window.height() - 30));
                    // 上中央の12×8px領域を読み、実際の頂点方向とテーマ上のコントラストを検査する。
                    const QRect arrow(header->sectionViewportPosition(column) + (header->sectionSize(column) - 1) / 2 - 6, 1, 12, 8);
                    const auto image = header->viewport()->grab().toImage(); const auto dpr = image.devicePixelRatio();
                    const auto background = header->palette().color(QPalette::Base);
                    int centerY = 0, centerCount = 0, edgeY = 0, edgeCount = 0;
                    for (int y = 0; y < arrow.height(); ++y) for (int x = 0; x < arrow.width(); ++x) {
                        const auto ink = image.pixelColor(qRound((arrow.x() + x) * dpr), qRound((arrow.y() + y) * dpr));
                        if (qAbs(ink.lightness() - background.lightness()) < 60) continue;
                        if (x >= arrow.width() / 3 && x < arrow.width() * 2 / 3) { centerY += y; ++centerCount; }
                        else { edgeY += y; ++edgeCount; }
                    }
                    QVERIFY2(centerCount > 0 && edgeCount > 0, "Sort chevron must have visible contrast in both themes");
                    const double delta = double(centerY) / centerCount - double(edgeY) / edgeCount;
                    QVERIFY2(ascending ? delta < -.5 : delta > .5, "Sort chevron must point up for ascending and down for descending");
                    click(column);
                }
            }
            window.close();
        }
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 明示パス起動でも表示設定を読み、旧タブを開かず編集入力を保護する。 */
    void explicitPathAppearanceAndKeys() {
        qpe::writeSettings({{"nativeAppearance", QJsonObject{{"textSize", 14}, {"uiPercent", 100}}}, {"nativeWorkspace", QJsonObject{{"paths", QJsonArray{path("B")}}}}});
        qpe::BrowserWindow window; window.restoreSession(path("A"), false); window.show(); window.activateWindow(); QTRY_VERIFY(window.ready());
        QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("A"))); QCOMPARE(window.findChild<QTabBar*>("folderTabs")->count(), 1); QCOMPARE(window.font().pixelSize(), 14);
        auto* files = window.findChild<QTreeView*>("files"); files->setFocus(); QTRY_VERIFY(files->hasFocus());
        QTest::keyClick(files, Qt::Key_Minus, Qt::ControlModifier); QCOMPARE(window.font().pixelSize(), 13);
        QTest::keyClick(files, Qt::Key_Plus, Qt::ControlModifier | Qt::ShiftModifier); QCOMPARE(window.font().pixelSize(), 14);
        auto* address = window.findChild<QLineEdit*>("address"); address->setFocus(); QTRY_VERIFY(address->hasFocus());
        for (auto* key : window.findChildren<QShortcut*>("fontSizeShortcut")) QVERIFY(!key->isEnabled());
        QTest::keyClick(address, Qt::Key_Minus, Qt::ControlModifier); QCOMPARE(window.font().pixelSize(), 14);
        files->setFocus(); QTest::keyClick(files, Qt::Key_0, Qt::ControlModifier); QCOMPARE(window.font().pixelSize(), 12); window.close();
    }
    /** @brief 絞込みの個別解除で他条件を保持し、すべて解除後は余分な行を隠す。 */
    void filterConditionChips() {
        qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
        auto* filter = window.findChild<QLineEdit*>("fileFilter"); auto* types = window.findChild<QComboBox*>("fileTypes"); auto* bar = window.findChild<QScrollArea*>("activeConditions");
        filter->setText("小さい"); types->setCurrentIndex(1); QVERIFY(bar->isVisible());
        auto* name = window.findChild<QToolButton*>("clearConditionName"); auto* type = window.findChild<QToolButton*>("clearConditionType"); QVERIFY(name->isVisible() && type->isVisible());
        name->click(); QVERIFY(filter->text().isEmpty()); QCOMPARE(types->currentIndex(), 1); QVERIFY(!name->isVisible()); QVERIFY(bar->isVisible());
        type->click(); QCOMPARE(types->currentIndex(), 0); QVERIFY(!bar->isVisible());
        window.close();
    }
    /** @brief クラウド未取得を同期成功と混同せず、診断がフォルダーを再帰列挙しない。 */
    void availabilityAndDiagnosis() {
        QVERIFY(qpe::availabilityFromFlags(0x1000).avoidRead);
        QVERIFY(qpe::availabilityFromFlags(0, 1 | 0x10).avoidRead);
        QVERIFY(!qpe::availabilityFromFlags(0x80000, 1 | 8).avoidRead);
        QVERIFY(qpe::availabilityFromFlags(0x80000, 1 | 8).text.contains("in sync"));
        QVERIFY(qpe::availabilityFromFlags(0, 1).text.contains("not in sync"));
        QVERIFY(!qpe::availabilityFromFlags(0, 0xffffffff).text.contains("in sync"));
        qpe::FileOperations operations(path("diagnose-history")); const auto result = operations.run({"diagnose", {path("A")}});
        QCOMPARE(result.extra["rows"].toArray().size(), 1); QVERIFY(result.extra["detail"].toString().contains("File Locksmith"));
    }
    /** @brief Python/PATHのデコーダーなしで、内蔵Cヘルパーが動画とEXRを読み込む。 */
    void embeddedMediaThumbnails() {
        qputenv("QPE_MEDIA_CACHE_ROOT", path("media-cache").toUtf8()); qunsetenv("QPE_FFMPEG");
        qpe::writeSettings({{"ffmpegExecutable", ""}});
        const auto decoder = qpe::mediaDecoder(); QVERIFY(decoder.startsWith(path("media-cache"))); QVERIFY(QFileInfo(decoder).isFile());
        for (const auto& extension : {QString("mp4"), QString("exr")}) {
            const auto fixture = QFINDTESTDATA("media/sample." + extension); QVERIFY(!fixture.isEmpty());
            const auto result = qpe::queryMedia({"media", {fixture}}, {}); const auto png = QByteArray::fromBase64(result.extra["png"].toString().toLatin1());
            QImage decoded; QVERIFY2(decoded.loadFromData(png, "PNG"), qPrintable(QString::fromUtf8(QJsonDocument(result.extra).toJson()))); QCOMPARE(decoded.size(), QSize(320, 240));
        }
        const auto cancel = std::make_shared<std::atomic_bool>(true); QVERIFY(qpe::mediaDecoder(cancel).isEmpty());
    }
    /** @brief ホスト終了は待機転送を記録したまま止め、モーダルを出さず自分のUIを破棄できる。 */
    void hostShutdownDuringQueuedTransfer() {
        QVERIFY(QDir().mkpath(path("shutdown-to"))); QVERIFY(file("shutdown-source.txt", 12));
        auto* window = new qpe::BrowserWindow; window->navigate(path("A")); window->show(); QTRY_VERIFY(window->ready());
        qpe::FileJobs* queue = nullptr; for (auto* jobs : window->findChildren<qpe::FileJobs*>(QString(), Qt::FindDirectChildrenOnly)) { queue = jobs; break; } QVERIFY(queue);
        queue->pauseQueue(true); queue->enqueue({"copy", {path("shutdown-source.txt")}, path("shutdown-to")}); const auto id = queue->records().first().toObject()["id"].toString();
        window->prepareHostShutdown(); QVERIFY(!QApplication::activeModalWidget()); QVERIFY(!window->isVisible()); delete window;
        QVERIFY(QFileInfo::exists(qpe::operationsDirectory() + "/jobs/" + id + ".json")); QVERIFY(QFileInfo::exists(path("shutdown-source.txt"))); QVERIFY(!QFileInfo::exists(path("shutdown-to/shutdown-source.txt")));
    }
    /** @brief 待機中止と記録除外は原本に触れず、除外後の再開も拒否する。 */
    void discardTransferRecord() {
        QVERIFY(QDir().mkpath(path("discard-to"))); QVERIFY(file("discard-source.txt", 15));
        qpe::FileJobs jobs; jobs.pauseQueue(true); jobs.enqueue({"copy", {path("discard-source.txt")}, path("discard-to")});
        const auto id = jobs.records().first().toObject()["id"].toString(); QVERIFY_EXCEPTION_THROWN(jobs.discard(id), std::runtime_error);
        jobs.cancelQueued(); QCOMPARE(qpe::loadJson(qpe::operationsDirectory() + "/jobs/" + id + ".json")["state"].toString(), QString("cancelled"));
        jobs.discard(id); QVERIFY_EXCEPTION_THROWN(jobs.resume(id), std::runtime_error); QVERIFY(QFileInfo::exists(path("discard-source.txt"))); QVERIFY(!QFileInfo::exists(path("discard-to/discard-source.txt")));
    }
    /** @brief 複数ファイルの進捗は最後の1ファイルのサイズへ戻らない。 */
    void transferByteProgress() {
        QVERIFY(QDir().mkpath(path("progress-to"))); QVERIFY(file("progress-one.txt", 1200)); QVERIFY(file("progress-two.txt", 3400));
        qpe::FileJobs jobs; QSignalSpy progress(&jobs, &qpe::FileJobs::progress), done(&jobs, &qpe::FileJobs::finished);
        jobs.enqueue({"copy", {path("progress-one.txt"), path("progress-two.txt")}, path("progress-to")}); QTRY_COMPARE_WITH_TIMEOUT(done.count(), 1, 5000);
        QVERIFY(!progress.isEmpty()); QCOMPARE(progress.last()[1].toLongLong(), 4600ll); QCOMPARE(done[0][0].toJsonObject()["extra"].toObject()["transferredBytes"].toDouble(), 4600.);
    }
    /** @brief タブの均等縮小、中央クリック、URL転送の固定対象を確認する。 */
    void nativeNavigationControls() {
        QWidget host; host.resize(900, 300); qpe::NavigationTabs tabs(&host); QHBoxLayout layout(&host); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(&tabs); layout.addStretch();
        tabs.addTab("One"); tabs.addTab("A very long name that must not take extra width"); host.show();
        QTRY_COMPARE(tabs.tabRect(0).width(), 240); QCOMPARE(tabs.tabRect(1).width(), 240);
        tabs.addTab("Three"); tabs.addTab("Four"); host.resize(600, 300); QTRY_COMPARE(tabs.tabRect(0).width(), 150); QCOMPARE(tabs.tabRect(3).width(), 150);
        host.resize(300, 300); QTRY_COMPARE(tabs.tabRect(0).width(), 100);
        QSignalSpy closed(&tabs, &QTabBar::tabCloseRequested); QTest::mouseClick(&tabs, Qt::MiddleButton, Qt::NoModifier, tabs.tabRect(0).center()); QCOMPARE(closed.count(), 1); QCOMPARE(closed[0][0].toInt(), 0);
        QMimeData urls; urls.setUrls({QUrl::fromLocalFile(path("A"))}); int target = -2; bool move = false;
        tabs.transfer = [&](const QStringList& paths, int index, bool moved) { QCOMPARE(paths, QStringList{path("A")}); target = index; move = moved; };
        QDragEnterEvent enter(tabs.tabRect(0).center(), Qt::CopyAction | Qt::MoveAction, &urls, Qt::LeftButton, Qt::ShiftModifier); QApplication::sendEvent(&tabs, &enter); QVERIFY(enter.isAccepted());
        QDropEvent drop(tabs.tabRect(0).center(), Qt::CopyAction | Qt::MoveAction, &urls, Qt::LeftButton, Qt::ShiftModifier); QApplication::sendEvent(&tabs, &drop); QCOMPARE(target, 0); QVERIFY(move); QCOMPARE(drop.dropAction(), Qt::CopyAction);
        qpe::PlacesTree places(&host); places.setGeometry(0, 50, 200, 200); places.show(); QStringList registered; places.favorite = [&](const QStringList& paths) { registered = paths; };
        QDragEnterEvent pe(QPoint(30, 30), Qt::CopyAction, &urls, Qt::LeftButton, Qt::NoModifier); QApplication::sendEvent(places.viewport(), &pe);
        QDropEvent pd(QPointF(30, 30), Qt::CopyAction, &urls, Qt::LeftButton, Qt::NoModifier); QApplication::sendEvent(places.viewport(), &pd); QCOMPARE(registered, QStringList{path("A")});
    }
    /** @brief 境界ドラッグで列だけを広げ、ダブルクリックで内容幅へ戻す。 */
    void columnWidthControls() {
        qpe::writeSettings({{"columnWidthMode", "names"}}); qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
        const auto columns = window.findChildren<QListView*>("folderColumn"); QVERIFY(!columns.isEmpty());
        // 深いソース配置では末尾列が画面外になり、QTestのOSカーソル移動が画面端で制限される。
        auto* scroll = window.findChild<QScrollArea*>("folderColumns"); QVERIFY(scroll);
        QCoreApplication::processEvents(); scroll->horizontalScrollBar()->setValue(0);
        auto* column = columns.first(); auto* grip = column->findChild<QWidget*>("columnGrip"); QVERIFY(grip);
        QVERIFY(grip->isVisible()); const int original = column->width();
        QTRY_COMPARE(column->childAt(grip->geometry().center()), grip);
        QTest::mousePress(grip, Qt::LeftButton, Qt::NoModifier, QPoint(2, 30)); QTest::mouseMove(grip, QPoint(102, 30)); QTest::mouseRelease(grip, Qt::LeftButton, Qt::NoModifier, QPoint(2, 30));
        QCOMPARE(column->width(), qMin(1000, original + 100)); QTest::mouseDClick(grip, Qt::LeftButton, Qt::NoModifier, QPoint(2, 30)); QCOMPARE(column->width(), original);
        qpe::writeSettings({{"columnWidthMode", "fit"}});
    }
    /** @brief 結合プレビューで根の異なる同名ファイルを区別し、表示後の変更を拒否する。 */
    void mergeConflictPreview() {
        for (const auto& name : {"merge-preview/from/one", "merge-preview/from/two", "merge-preview/to/one", "merge-preview/to/two"}) QVERIFY(QDir().mkpath(path(name)));
        for (const auto& name : {"merge-preview/from/one/same.txt", "merge-preview/from/two/same.txt"}) QVERIFY(file(name, 10));
        for (const auto& name : {"merge-preview/to/one/same.txt", "merge-preview/to/two/same.txt"}) QVERIFY(file(name, 20));
        qpe::FileOperations engine(path("merge-preview/history"));
        const QStringList sources{path("merge-preview/from/one"), path("merge-preview/from/two")};
        const auto rows = engine.run({"mergeConflicts", sources, path("merge-preview/to")}).extra["rows"].toArray(); QCOMPARE(rows.size(), 2);
        QJsonObject choices{{"_requireReviewed", true}, {sources[0] + "/same.txt", "skip"}, {sources[1] + "/same.txt", "replace"}};
        qpe::FileRequest request{"copy", sources, path("merge-preview/to"), "merge", {{"choices", choices}, {"mergeReviewed", rows}}};
        const auto result = engine.run(request); QVERIFY(result.errors.isEmpty()); QCOMPARE(QFileInfo(path("merge-preview/to/one/same.txt")).size(), 20ll); QCOMPARE(QFileInfo(path("merge-preview/to/two/same.txt")).size(), 10ll);
        QVERIFY_EXCEPTION_THROWN(engine.run(request), std::runtime_error);
        QVERIFY(file("merge-preview/from/new.txt", 5)); QVERIFY(file("merge-preview/to/new.txt", 8));
        const auto unreviewed = engine.run({"copy", {path("merge-preview/from/new.txt")}, path("merge-preview/to"), "merge", {{"choices", QJsonObject{{"_requireReviewed", true}}}}});
        QVERIFY(!unreviewed.errors.isEmpty()); QCOMPARE(QFileInfo(path("merge-preview/to/new.txt")).size(), 8ll);
    }
    /** @brief 旧保存転送を明示再開し、準備時から変わった原本を拒否する。 */
    void legacyTransferResume() {
        QVERIFY(QDir().mkpath(path("legacy-job-from"))); QVERIFY(QDir().mkpath(path("legacy-job-to"))); QVERIFY(file("legacy-job-from/a.txt", 6));
        const auto id = QString("12345678901234567890123456789012"), source = path("legacy-job-from/a.txt");
        QJsonObject record{{"version", 1}, {"id", id}, {"action", "copy"}, {"paths", QJsonArray{source}}, {"destination", path("legacy-job-to")}, {"conflict", "rename"}, {"state", "Stopped"}, {"prepared", true},
            {"items", QJsonArray{QJsonObject{{"source", source}, {"stamp", qpe::legacyFingerprint(source)}, {"targetStamp", QJsonValue::Null}, {"state", "Pending"}, {"transaction", "abc"}}}}};
        qpe::saveJson(path("jobs/") + id + ".json", record);
        qpe::FileJobs jobs; QSignalSpy done(&jobs, &qpe::FileJobs::finished); jobs.resume("legacy:" + id); QTRY_COMPARE_WITH_TIMEOUT(done.count(), 1, 5000);
        const auto result = qpe::fileResultFromJson(done[0][0].toJsonObject()); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join(';'))); QVERIFY(QFileInfo::exists(path("legacy-job-to/a.txt")));
        QCOMPARE(qpe::loadJson(path("jobs/") + id + ".json"), record);
        const auto other = QString("22345678901234567890123456789012"); record["id"] = other; record["destination"] = path("legacy-job-other"); QVERIFY(QDir().mkpath(path("legacy-job-other")));
        qpe::saveJson(path("jobs/") + other + ".json", record); QVERIFY(file("legacy-job-from/a.txt", 7)); done.clear(); jobs.resume("legacy:" + other); QTRY_COMPARE_WITH_TIMEOUT(done.count(), 1, 5000);
        QVERIFY(!qpe::fileResultFromJson(done[0][0].toJsonObject()).errors.isEmpty()); QVERIFY(!QFileInfo::exists(path("legacy-job-other/a.txt")));
    }
    /** @brief Pythonのstat/Unicode順と独立比較し、64bitごみ箱IDを丸めない。 */
    void legacyMetadataParity() {
        QVERIFY(QDir().mkpath(path("legacy-meta/日本語"))); QVERIFY(file("legacy-meta/A.txt", 17)); QVERIFY(file("legacy-meta/b.exe", 9)); QVERIFY(file("legacy-meta/日本語/😀.txt", 4));
        QProcess python;
        const QString code = "import pathlib,hashlib,sys,json\n"
            "def f(p,meta):\n"
            " s=p.lstat();h=hashlib.sha256()\n"
            " if meta:h.update(repr((s.st_dev&0xffffffff,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)).encode('ascii'))\n"
            " else:h.update(b'D' if p.is_dir() else b'F')\n"
            " if p.is_dir():\n"
            "  for c in sorted(p.iterdir(),key=lambda x:x.name):h.update(c.name.encode('utf8'));h.update(f(c,meta).encode('ascii'))\n"
            " elif not meta:h.update(p.read_bytes())\n"
            " return h.hexdigest()\n"
            "p=pathlib.Path(sys.argv[1]);print(json.dumps([f(p,False),f(p,True)]))\n";
        python.start(qEnvironmentVariable("QPE_TEST_PYTHON", "python"), {"-c", code, path("legacy-meta")}); QVERIFY(python.waitForFinished(10000)); QCOMPARE(python.exitCode(), 0);
        const auto values = QJsonDocument::fromJson(python.readAllStandardOutput()).array(); QCOMPARE(values.size(), 2);
        QCOMPARE(qpe::legacyFingerprint(path("legacy-meta")), values[0].toString()); QCOMPARE(qpe::legacyMetadataFingerprint(path("legacy-meta")), values[1].toString());
        QVERIFY(QDir().mkpath(path("legacy-meta/undo"))); QFile journal(path("legacy-meta/undo/journal.json")); QVERIFY(journal.open(QIODevice::WriteOnly));
        journal.write(R"([{"id":"receipt","action":"trash","entries":[{"source":"C:/example","recycle":{"identity":[4294967295,18446744073709551615]}}]}])"); journal.close();
        const auto migrated = qpe::migrateLegacyHistory(path("legacy-meta/undo"), {});
        QCOMPARE(migrated["undo"].toArray()[0].toObject()["recycle"].toObject()["identity"].toString(), QString("4294967295:18446744073709551615"));
    }
    /** @brief 旧版でUndo済みのコピーと作成を、検証付きのC++ Redoへ移す。 */
    void legacyRedoMigration() {
        for (const auto& action : {QString("copy"), QString("create"), QString("move"), QString("rename")}) {
            const auto root = path("legacy-redo-" + action); QVERIFY(QDir().mkpath(root + "/undo")); QVERIFY(QDir().mkpath(root + "/source")); QVERIFY(QDir().mkpath(root + "/target"));
            const auto source = root + "/source/a.txt", target = root + "/target/a.txt"; QVERIFY(file("legacy-redo-" + action + "/source/a.txt", 7));
            const auto stamp = qpe::legacyFingerprint(source);
            const QJsonObject entry{{"source", action == "create" ? target : source}, {"target", target}, {"backup", ""}, {"stamp", stamp}, {"redoCopy", source}};
            qpe::saveJson(root + "/undo/redo.json", {{"id", "redo1"}, {"action", action}, {"entries", QJsonArray{entry}}, {"expected", QJsonObject{{source, stamp}, {target, QJsonValue::Null}}}});
            qpe::FileOperations operations(root + "/native-file-history"); const auto result = operations.run({"redo"}); QCOMPARE(result.completed.size(), 1); QVERIFY(QFileInfo::exists(target));
            QCOMPARE(qpe::legacyFingerprint(target), stamp); QCOMPARE(operations.run({"undo"}).completed.size(), 1); QVERIFY(!QFileInfo::exists(target));
            QVERIFY(QFileInfo::exists(source));
        }
    }
    /** @brief 旧SHA256を照合してコピー履歴を移行し、外部変更と旧版同時操作を拒否する。 */
    void legacyHistoryMigration() {
        const auto root = path("legacy-case"); QVERIFY(QDir().mkpath(root + "/undo")); QVERIFY(QDir().mkpath(root + "/source")); QVERIFY(QDir().mkpath(root + "/target"));
        QVERIFY(file("legacy-case/source/a.txt", 12)); QVERIFY(file("legacy-case/target/a.txt", 12));
        const auto stamp = qpe::legacyFingerprint(root + "/target/a.txt");
        QCOMPARE(stamp, qpe::fileFingerprint(root + "/target/a.txt"));
        const QJsonObject entry{{"source", root + "/source/a.txt"}, {"target", root + "/target/a.txt"}, {"backup", ""}, {"stamp", stamp}};
        const QJsonArray records{QJsonObject{{"id", "case1"}, {"action", "copy"}, {"time", 123456}, {"entries", QJsonArray{entry}}}};
        const auto original = QJsonDocument(records).toJson();
        { QFile output(root + "/undo/journal.json"); QVERIFY(output.open(QIODevice::WriteOnly)); QCOMPARE(output.write(original), original.size()); }
        qpe::FileOperations operations(root + "/native-file-history");
        {
            qpe::LegacyHistoryLease lease(root + "/undo");
            QVERIFY_EXCEPTION_THROWN(operations.run({"undo"}), std::runtime_error);
        }
        auto result = operations.run({"undo"}); QCOMPARE(result.completed.size(), 1); QVERIFY(!QFileInfo::exists(root + "/target/a.txt")); QVERIFY(QFileInfo::exists(root + "/source/a.txt"));
        result = operations.run({"redo"}); QCOMPARE(result.completed.size(), 1); QCOMPARE(qpe::legacyFingerprint(root + "/target/a.txt"), stamp);
        { QFile originalFile(root + "/undo/journal.json"); QVERIFY(originalFile.open(QIODevice::ReadOnly)); QCOMPARE(originalFile.readAll(), original); }
        QVERIFY(file("legacy-case/target/a.txt", 13)); QVERIFY_EXCEPTION_THROWN(operations.run({"undo"}), std::runtime_error); QVERIFY(QFileInfo::exists(root + "/target/a.txt"));
        { QFile oldWriter(root + "/undo/journal.json"); QVERIFY(oldWriter.open(QIODevice::Append)); oldWriter.write(" "); }
        QVERIFY_EXCEPTION_THROWN(operations.run({"newFile", {}, root + "/should-not-create"}), std::runtime_error); QVERIFY(!QFileInfo::exists(root + "/should-not-create"));
    }
    /** @brief 旧バックアップ方式の削除と退避なし移動を、原本検証付きでUndo/Redoする。 */
    void legacyBackupRoundTrip() {
        for (const auto& action : {QString("trash"), QString("move")}) {
            const auto name = "legacy-backup-" + action; const auto root = path(name); QVERIFY(QDir().mkpath(root + "/undo"));
            QVERIFY(file(name + "/original.txt", 17)); QVERIFY(file(name + "/replacement.txt", 9));
            const auto source = root + "/original.txt", target = root + "/target.txt", backup = root + "/undo/retained";
            const auto originalStamp = qpe::legacyFingerprint(source), replacedStamp = qpe::legacyFingerprint(root + "/replacement.txt");
            if (action == "trash") QVERIFY(QFile::rename(source, backup));
            else { QVERIFY(QFile::rename(source, target)); QVERIFY(QFile::rename(root + "/replacement.txt", backup)); }
            QJsonObject entry{{"source", source}, {"target", action == "trash" ? QString() : target}, {"backup", backup}, {"stamp", originalStamp}, {"moved", true}};
            if (action == "move") entry["backupStamp"] = replacedStamp;
            QFile journal(root + "/undo/journal.json"); QVERIFY(journal.open(QIODevice::WriteOnly)); journal.write(QJsonDocument(QJsonArray{QJsonObject{{"id", "legacy1"}, {"action", action}, {"entries", QJsonArray{entry}}}}).toJson()); journal.close();
            qpe::FileOperations operations(root + "/native-file-history"); QCOMPARE(operations.run({"undo"}).completed.size(), 1); QCOMPARE(qpe::legacyFingerprint(source), originalStamp);
            if (action == "move") QCOMPARE(qpe::legacyFingerprint(target), replacedStamp);
            QCOMPARE(operations.run({"redo"}).completed.size(), 1); QVERIFY(!QFileInfo::exists(source));
            QCOMPARE(operations.run({"undo"}).completed.size(), 1); QCOMPARE(qpe::legacyFingerprint(source), originalStamp);
        }
    }
    /** @brief 旧Pythonの64bit数値IDを含む実ごみ箱記録から正しい項目だけを復元する。 */
    void legacyRecycleReceipt() {
        const auto root = path("legacy-bin"); QVERIFY(QDir().mkpath(root + "/undo")); QVERIFY(file("legacy-bin/専用.txt", 31)); const auto source = root + "/専用.txt";
        QJsonObject receipt;
        try { receipt = std::async(std::launch::async, [source] { return qpe::recyclePath(source, {}); }).get(); }
        catch (const std::exception& e) { QFAIL(qPrintable(QString("Recycle preparation: ") + e.what())); }
        const QJsonArray records{QJsonObject{{"id", "receipt1"}, {"action", "trash"}, {"entries", QJsonArray{QJsonObject{{"source", source}, {"recycle", receipt}}}}}};
        auto bytes = QJsonDocument(records).toJson();
        for (const auto& key : {"identity", "metadataIdentity"}) { const auto identity = receipt[key].toString(); if (!identity.isEmpty()) bytes.replace('"' + identity.toLatin1() + '"', '[' + identity.toLatin1().replace(':', ',') + ']'); }
        QFile output(root + "/undo/journal.json"); QVERIFY(output.open(QIODevice::WriteOnly)); output.write(bytes); output.close();
        const auto migratedReceipt = qpe::migrateLegacyHistory(root + "/undo", {})["undo"].toArray().first().toObject()["recycle"].toObject();
        QCOMPARE(migratedReceipt, receipt);
        qpe::FileResult result;
        try { result = std::async(std::launch::async, [root] { return qpe::FileOperations(root + "/native-file-history").run({"undo"}); }).get(); }
        catch (const std::exception& e) {
            const QString failure = QString("Legacy restore: ") + e.what();
            qInfo().noquote() << QJsonDocument(receipt).toJson(QJsonDocument::Compact);
            qInfo().noquote() << QJsonDocument(qpe::loadJson(root + "/native-file-history/journal.json")).toJson(QJsonDocument::Compact);
            if (!QFileInfo::exists(source)) { try { std::async(std::launch::async, [receipt, source] { qpe::restoreRecycled(receipt, source); }).get(); } catch (...) {} }
            QFAIL(qPrintable(failure));
        }
        QCOMPARE(result.completed.size(), 1); QCOMPARE(QFileInfo(source).size(), 31LL);
    }
    /** @brief 第2ペインの場所を復元し、明示した方向へだけコピーする。 */
    void secondPaneRoundTrip() {
        const auto before = qpe::readSettings();
        QVERIFY(QDir().mkpath(path("pane-from"))); QVERIFY(QDir().mkpath(path("pane-to"))); QVERIFY(file("pane-from/example.txt"));
        {
            qpe::BrowserWindow window; window.navigate(path("pane-from")); window.show(); QTRY_VERIFY(window.ready());
            auto* files = window.findChild<QTreeView*>("files");
            window.perform("secondPane");
            auto* address = window.findChild<QLineEdit*>("secondAddress"); QVERIFY(address); address->setText(path("pane-to")); QTest::keyClick(address, Qt::Key_Return);
            QTRY_COMPARE(files->model()->rowCount(), 1);
            files->selectionModel()->select(files->model()->index(0, 0), QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            window.findChild<QPushButton*>("copyToSecond")->click(); QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 5000);
            QVERIFY(QFileInfo::exists(path("pane-to/example.txt"))); QVERIFY(QFileInfo::exists(path("pane-from/example.txt")));
            window.close();
        }
        {
            qpe::BrowserWindow window; window.restoreSession(); window.show();
            auto* address = window.findChild<QLineEdit*>("secondAddress"); QVERIFY(address); QCOMPARE(address->text(), path("pane-to"));
            QVERIFY(!window.findChild<QWidget*>("secondPane")->isHidden()); window.close();
        }
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief グループ見出しは操作対象にせず、絞込み・追加後も実パスと対応する。 */
    void groupedFilePresentation() {
        const auto before = qpe::readSettings(); QVERIFY(QDir().mkpath(path("group-ui")));
        QVERIFY(file("group-ui/a.txt")); QVERIFY(file("group-ui/b.txt")); QVERIFY(file("group-ui/c.mb"));
        const auto key = QDir::toNativeSeparators(path("group-ui")).toLower();
        qpe::writeSettings({{"folderViews", QJsonObject{{key, QJsonObject{{"mode", 0}, {"group", 1}}}}}});
        {
            qpe::BrowserWindow window; window.navigate(path("group-ui")); window.show(); QTRY_VERIFY(window.ready());
            auto* files = window.findChild<QTreeView*>("files"); auto* model = files->model();
            QAbstractItemModelTester tester(model, QAbstractItemModelTester::FailureReportingMode::QtTest);
            QTRY_COMPARE(model->rowCount(), 2); int count = 0;
            for (int group = 0; group < model->rowCount(); ++group) {
                const auto parent = model->index(group, 0); QVERIFY(!(parent.flags() & Qt::ItemIsSelectable)); QVERIFY(parent.data(Qt::UserRole + 1).toString().isEmpty());
                for (int row = 0; row < model->rowCount(parent); ++row) { const auto child = model->index(row, 0, parent); QVERIFY(QFileInfo::exists(child.data(Qt::UserRole + 1).toString())); ++count; }
            }
            QCOMPARE(count, 3); window.findChild<QLineEdit*>("fileFilter")->setText("a.txt"); QTRY_COMPARE(model->rowCount(), 1);
            QCOMPARE(model->rowCount(model->index(0, 0)), 1); QCOMPARE(model->index(0, 0, model->index(0, 0)).data().toString(), QString("a.txt"));
            const auto selected = model->index(0, 0, model->index(0, 0));
            files->selectionModel()->select(selected, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            const auto selectedPath = selected.data(Qt::UserRole + 1).toString();
            window.navigate(path("B")); QTRY_VERIFY(window.ready());
            window.navigate(path("group-ui")); QTRY_VERIFY(window.ready());
            QTRY_COMPARE(files->selectionModel()->selectedRows().size(), 1);
            QTest::qWait(100);
            QCOMPARE(files->selectionModel()->selectedRows().size(), 1);
            QCOMPARE(files->selectionModel()->selectedRows().first().data(Qt::UserRole + 1).toString(), selectedPath);
            window.close();
        }
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 旧版のフォルダー表示設定を読み、移動・再起動でも列幅と非表示列を保つ。 */
    void folderViewRoundTrip() {
        const auto before = qpe::readSettings(); const auto a = QDir::toNativeSeparators(path("A")).toLower();
        const QJsonObject saved{{"mode", 2}, {"sort", 1}, {"descending", true}, {"hidden", QJsonArray{2}}, {"widths", QJsonArray{400, 173, 100, 180}}};
        qpe::writeSettings({{"folderViews", QJsonObject{{a, saved}}}});
        {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
            auto* files = window.findChild<QTreeView*>("files"); QVERIFY(files);
            QCOMPARE(files->model()->columnCount(), 9); QVERIFY(files->isColumnHidden(2)); QCOMPARE(files->columnWidth(1), 173);
            files->setColumnWidth(1, 191); files->sortByColumn(3, Qt::AscendingOrder);
            window.navigate(path("B")); QTRY_VERIFY(window.ready()); window.navigate(path("A")); QTRY_VERIFY(window.ready());
            QCOMPARE(files->columnWidth(1), 191); QVERIFY(files->isColumnHidden(2)); QCOMPARE(files->header()->sortIndicatorSection(), 3);
            window.close();
        }
        {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
            auto* files = window.findChild<QTreeView*>("files"); QCOMPARE(files->columnWidth(1), 191); QVERIFY(files->isColumnHidden(2));
            window.close();
        }
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 検索条件を小さくしても操作ボタンを隠さず、結果の名前をパスと別に表示する。 */
    void searchDialogLayout() {
        QVERIFY(QDir().mkpath(path("search-ui"))); QVERIFY(file("search-ui/visible-name.txt"));
        qpe::BrowserWindow window; window.navigate(path("search-ui")); window.show();
        bool seen = false;
        QTimer::singleShot(100, &window, [&] {
            auto* dialog = window.findChild<QDialog*>("qpeSearchOptions");
            if (!dialog) return; seen = true;
            const bool wide = dialog->width() >= 650;
            dialog->resize(500, 420); QApplication::processEvents();
            auto* scroll = dialog->findChild<QScrollArea*>(); auto* buttons = dialog->findChild<QDialogButtonBox*>();
            const bool usable = scroll && buttons && dialog->rect().contains(buttons->mapTo(dialog, buttons->rect().bottomRight()));
            dialog->accept(); QVERIFY(wide); QVERIFY(usable);
        });
        window.perform("search"); QVERIFY(seen);
        auto* results = window.findChild<QDialog*>("qpeSearchResults"); QVERIFY(results);
        auto* rows = results->findChild<QTreeWidget*>(); QVERIFY(rows);
        QTRY_COMPARE_WITH_TIMEOUT(rows->topLevelItemCount(), 1, 5000);
        QCOMPARE(rows->topLevelItem(0)->text(0), QString("visible-name.txt"));
        QCOMPARE(rows->topLevelItem(0)->data(0, Qt::UserRole + 1).toString(), path("search-ui/visible-name.txt"));
        QTRY_VERIFY(!results->findChild<QPushButton*>("searchStop")->isEnabled());
        results->close();
    }
    /** @brief 左サイドバーから旧KiB単位の保存検索を開き、名前をファイルパスと混同しない。 */
    void savedSearchSidebar() {
        const auto before = qpe::readSettings();
        QVERIFY(QDir().mkpath(path("saved-search"))); QVERIFY(file("saved-search/small.txt", 8)); QVERIFY(file("saved-search/large.txt", 2048));
        qpe::writeSettings({{"savedSearches", QJsonObject{{"Saved test", QJsonObject{{"root", path("saved-search")}, {"minimum", 1}, {"types", "*.txt"}}}}}});
        {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
            auto* places = window.findChild<QTreeWidget*>("places"); QVERIFY(places);
            QTreeWidgetItem* saved = nullptr;
            for (int i = 0; i < places->topLevelItem(0)->childCount(); ++i) {
                auto* item = places->topLevelItem(0)->child(i); if (item->data(0, Qt::UserRole + 101).toString() == "Saved test") saved = item;
            }
            QVERIFY(saved); QVERIFY(!saved->icon(0).isNull());
            emit places->itemClicked(saved, 0);
            auto* results = window.findChild<QDialog*>("qpeSearchResults"); QVERIFY(results);
            QTRY_VERIFY(!results->findChild<QPushButton*>("searchStop")->isEnabled());
            auto* rows = results->findChild<QTreeWidget*>(); QCOMPARE(rows->topLevelItemCount(), 1);
            QCOMPARE(rows->topLevelItem(0)->text(0), QString("large.txt"));
            QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("A")));
            emit rows->itemDoubleClicked(rows->topLevelItem(0), 0);
            QTRY_VERIFY(window.ready()); QTRY_COMPARE(window.selectedPaths(), QStringList{path("saved-search/large.txt")});
            results->close();
        }
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 一括改名の正規表現・不正入力・衝突を適用前に検証し、成功分だけUndoできる。 */
    void batchRenameRegexPreview() {
        QVERIFY(QDir().mkpath(path("rename-regex"))); QVERIFY(file("rename-regex/shot01.ma")); QVERIFY(file("rename-regex/shot02.ma"));
        qpe::BrowserWindow window; window.navigate(path("rename-regex")); window.show(); QTRY_VERIFY(window.ready());
        bool checked = false;
        QTimer::singleShot(50, &window, [&] {
            auto* dialog = window.findChild<QDialog*>("batchRenameDialog"); if (!dialog) return;
            auto* find = dialog->findChild<QLineEdit*>("renameFind"); auto* replacement = dialog->findChild<QLineEdit*>("renameReplace");
            auto* regex = dialog->findChild<QCheckBox*>("renameRegex"); auto* buttons = dialog->findChild<QDialogButtonBox*>();
            regex->setChecked(true); find->setText("["); const bool invalid = !buttons->button(QDialogButtonBox::Apply)->isEnabled();
            find->setText("[0-9]+"); replacement->setText("00"); const bool collision = !buttons->button(QDialogButtonBox::Apply)->isEnabled();
            find->setText("^shot([0-9]+)$"); replacement->setText("take\\1"); const bool valid = buttons->button(QDialogButtonBox::Apply)->isEnabled();
            checked = invalid && collision && valid; if (checked) buttons->button(QDialogButtonBox::Apply)->click(); else dialog->reject();
        });
        window.perform("batchRename", {path("rename-regex/shot01.ma"), path("rename-regex/shot02.ma")}); QVERIFY(checked);
        QTRY_VERIFY(!window.busy()); QVERIFY(QFileInfo::exists(path("rename-regex/take01.ma"))); QVERIFY(QFileInfo::exists(path("rename-regex/take02.ma")));
        window.perform("undo"); QTRY_VERIFY(!window.busy()); QVERIFY(QFileInfo::exists(path("rename-regex/shot01.ma"))); QVERIFY(QFileInfo::exists(path("rename-regex/shot02.ma")));
        window.close();
    }
    /** @brief 検索からの選択要求の後に別フォルダーへ移動すると、古い選択を適用しない。 */
    void revealGenerationAndRecentPaths() {
        const auto before = qpe::readSettings();
        qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
        window.perform("reveal", {path("many/日本語_04999.txt")}); window.navigate(path("B")); QTRY_VERIFY(window.ready());
        QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B"))); QVERIFY(window.selectedPaths().isEmpty());
        window.perform("reveal", {path("A/小さい.mb")}); QTRY_COMPARE(window.selectedPaths(), QStringList{path("A/小さい.mb")});
        window.close(); const auto recent = qpe::readSettings()["pathHistory"].toArray(); QVERIFY(recent.contains(qpe::DirectoryStore::normalized(path("B"))));
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief タグAll/Any、種類、相対除外と100件の途中配送を検証する。 */
    void advancedSearchStreaming() {
        QVERIFY(QDir().mkpath(path("search-stream/nested/skip"))); QVERIFY(file("search-stream/nested/skip/hidden.txt"));
        for (int i = 0; i < 205; ++i) QVERIFY(file(QString("search-stream/file%1.txt").arg(i)));
        qpe::FileOperations engine(path("search-stream-history")); QList<QJsonObject> batches;
        const auto result = engine.run({"search", {path("search-stream")}, {}, "rename", {{"extensions", "*.txt"}, {"exclude", "nested/skip"}, {"token", "generation-5"}}}, {}, {}, [&](const QJsonObject& rows) { batches.append(rows); });
        QCOMPARE(result.extra["rows"].toArray().size(), 205); QCOMPARE(batches.size(), 3); QCOMPARE(batches[0]["rows"].toArray().size(), 100); QCOMPARE(batches[2]["rows"].toArray().size(), 5); QCOMPARE(batches[0]["token"].toString(), QString("generation-5"));
        const auto before = qpe::readSettings(); qpe::writeSettings({{"fileLabels", QJsonObject{{QDir::toNativeSeparators(path("search-stream/file0.txt")).toLower(), QJsonObject{{"tags", QJsonArray{"Hero", "Rig"}}}}}}});
        auto matching = engine.run({"search", {path("search-stream")}, {}, "rename", {{"tags", "hero,missing"}, {"tagMode", "All"}}}); QVERIFY(matching.extra["rows"].toArray().isEmpty());
        matching = engine.run({"search", {path("search-stream")}, {}, "rename", {{"tags", "hero,missing"}, {"tagMode", "Any"}}}); QCOMPARE(matching.extra["rows"].toArray().size(), 1);
        matching = engine.run({"search", {path("search-stream")}, {}, "rename", {{"kind", "Folders"}, {"exclude", "nested/skip"}}}); QCOMPARE(matching.extra["rows"].toArray().size(), 1);
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 一括Undoは競合を先に全件検証し、大小文字だけの改名も戻せる。 */
    void batchUndoPreflight() {
        QVERIFY(QDir().mkpath(path("preflight/from"))); QVERIFY(QDir().mkpath(path("preflight/to")));
        QVERIFY(file("preflight/from/a.txt", 10)); QVERIFY(file("preflight/from/b.txt", 12));
        qpe::FileOperations engine(path("preflight/history"));
        const auto result = engine.run({"copy", {path("preflight/from/a.txt"), path("preflight/from/b.txt")}, path("preflight/to")}); QCOMPARE(result.completed.size(), 2);
        QFile external(path("preflight/to/a.txt")); QVERIFY(external.open(QIODevice::Append)); external.write("changed"); external.close();
        QVERIFY_EXCEPTION_THROWN(engine.run({"undo"}), std::runtime_error);
        QVERIFY(QFileInfo::exists(path("preflight/to/b.txt"))); QVERIFY(QFileInfo::exists(path("preflight/to/a.txt")));
        auto renamed = engine.run({"rename", {path("preflight/from/b.txt")}, {}, "rename", {{"name", "B.TXT"}}}); QVERIFY(renamed.errors.isEmpty());
        QVERIFY(QDir(path("preflight/from")).entryList().contains("B.TXT")); engine.run({"undo"}); QVERIFY(QDir(path("preflight/from")).entryList().contains("b.txt"));
    }
    /** @brief 一時ロックの解放を限定時間だけ待ち、持続ロックでは原本を保持して失敗する。 */
    void transientRenameLock() {
        QVERIFY(file("temporary-lock.txt"));
        const auto source = QDir::toNativeSeparators(path("temporary-lock.txt"));
        const auto handle = CreateFileW(reinterpret_cast<LPCWSTR>(source.utf16()), GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        QVERIFY(handle != INVALID_HANDLE_VALUE);
        auto release = std::async(std::launch::async, [handle] { Sleep(150); CloseHandle(handle); });
        qpe::FileOperations engine(path("temporary-lock-history"));
        const auto result = engine.run({"rename", {path("temporary-lock.txt")}, {}, "rename", {{"name", "lock-released.txt"}}});
        release.get(); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join("\n")));
        QVERIFY(QFileInfo::exists(path("lock-released.txt"))); engine.run({"undo"});
        QVERIFY(QFileInfo::exists(path("temporary-lock.txt")));
        const auto persistent = CreateFileW(reinterpret_cast<LPCWSTR>(source.utf16()), GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        QVERIFY(persistent != INVALID_HANDLE_VALUE);
        QElapsedTimer duration; duration.start();
        const auto failure = engine.run({"rename", {path("temporary-lock.txt")}, {}, "rename", {{"name", "must-not-exist.txt"}}});
        CloseHandle(persistent);
        const auto elapsed = duration.elapsed();
        qInfo() << "Persistent rename lock: total operation milliseconds" << elapsed;
        QVERIFY(!failure.errors.isEmpty()); QVERIFY2(elapsed < 3000, qPrintable(QString("Persistent lock took %1 ms").arg(elapsed)));
        QVERIFY(QFileInfo::exists(path("temporary-lock.txt"))); QVERIFY(!QFileInfo::exists(path("must-not-exist.txt")));
        QVERIFY(QDir().mkpath(path("locked-directory")));
        QVERIFY(file("locked-directory/retained.txt"));
        const auto directory = QDir::toNativeSeparators(path("locked-directory"));
        const auto directoryHandle = CreateFileW(reinterpret_cast<LPCWSTR>(directory.utf16()), GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
        QVERIFY(directoryHandle != INVALID_HANDLE_VALUE);
        auto releaseDirectory = std::async(std::launch::async, [directoryHandle] { Sleep(150); CloseHandle(directoryHandle); });
        qpe::FileOperations directoryEngine(path("directory-lock-history"));
        const auto movedDirectory = directoryEngine.run({"rename", {path("locked-directory")}, {}, "rename", {{"name", "released-directory"}}});
        releaseDirectory.get(); QVERIFY2(movedDirectory.errors.isEmpty(), qPrintable(movedDirectory.errors.join("\n")));
        QVERIFY(QFileInfo::exists(path("released-directory/retained.txt")));
        directoryEngine.run({"undo"}); QVERIFY(QFileInfo::exists(path("locked-directory/retained.txt")));
    }
    /** @brief 手動履歴整理は原本を残し、外部変更と古い復旧確認を拒否する。 */
    void historyMaintenance() {
        QVERIFY(QDir().mkpath(path("maintenance/from"))); QVERIFY(QDir().mkpath(path("maintenance/to")));
        QVERIFY(file("maintenance/from/item.txt", 12)); QVERIFY(file("maintenance/to/item.txt", 7));
        const auto location = path("maintenance/history"); qpe::FileOperations engine(location);
        const auto copied = engine.run({"copy", {path("maintenance/from/item.txt")}, path("maintenance/to"), "replace"}); QVERIFY(copied.errors.isEmpty());
        auto journal = qpe::loadJson(location + "/journal.json"); auto entry = journal["undo"].toArray()[0].toObject(); const auto backup = entry["backup"].toString(); QVERIFY(QFileInfo::exists(backup));
        entry["time"] = "2000-01-01T00:00:00Z"; journal["undo"] = QJsonArray{entry}; qpe::saveJson(location + "/journal.json", journal);
        const auto clean = engine.run({"historyCleanup", {}, {}, "rename", {{"days", 30}, {"budget", 1048576}}}); QCOMPARE(clean.completed.size(), 1);
        QVERIFY(!QFileInfo::exists(backup)); QVERIFY(QFileInfo::exists(path("maintenance/from/item.txt"))); QCOMPARE(QFileInfo(path("maintenance/to/item.txt")).size(), qint64(12));
        QVERIFY(qpe::loadJson(location + "/journal.json")["undo"].toArray().isEmpty());
        auto result = engine.run({"copy", {path("maintenance/from/item.txt")}, path("maintenance/to"), "replace"}); QVERIFY(result.errors.isEmpty());
        journal = qpe::loadJson(location + "/journal.json"); entry = journal["undo"].toArray()[0].toObject(); entry["time"] = "2000-01-01T00:00:00Z"; journal["undo"] = QJsonArray{entry}; qpe::saveJson(location + "/journal.json", journal);
        QFile changed(entry["backup"].toString()); QVERIFY(changed.open(QIODevice::Append)); changed.write("external"); changed.close();
        QVERIFY_EXCEPTION_THROWN(engine.run({"historyCleanup", {}, {}, "rename", {{"days", 30}, {"budget", 1048576}}}), std::runtime_error); QVERIFY(QFileInfo::exists(entry["backup"].toString()));
        journal["pending"] = entry; qpe::saveJson(location + "/journal.json", journal);
        QVERIFY_EXCEPTION_THROWN(engine.run({"historyReview", {}, {}, "rename", {{"acknowledge", true}, {"journalDigest", "stale"}}}), std::runtime_error);
        const auto digest = QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(journal).toJson(QJsonDocument::Compact), QCryptographicHash::Sha256).toHex());
        engine.run({"historyReview", {}, {}, "rename", {{"acknowledge", true}, {"journalDigest", digest}}});
        journal = qpe::loadJson(location + "/journal.json"); QVERIFY(journal["pending"].toObject().isEmpty()); QVERIFY(journal["undo"].toArray().isEmpty()); QVERIFY(!journal["reviewed"].toArray().isEmpty()); QVERIFY(QFileInfo::exists(entry["backup"].toString()));
    }
    /** @brief カスタムキーがビュー内だけで有効になり、編集欄や他ツールを奪わない。 */
    void commandInputBoundary() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"commandKeys", QJsonObject{{"metadata", "Ctrl+Alt+M"}}}});
        qpe::BrowserWindow window; window.navigate(path("A")); window.show(); window.activateWindow(); QTRY_VERIFY(window.ready());
        auto* view = window.findChild<QTreeView*>("files"); QVERIFY(view); view->setFocus(); QTest::qWait(50);
        QShortcut* command = nullptr; for (auto* shortcut : window.findChildren<QShortcut*>("qpeCustomCommand")) if (shortcut->property("commandId").toString() == "metadata") command = shortcut;
        QVERIFY(command); QTRY_VERIFY(command->isEnabled());
        QTest::keyClick(view, Qt::Key_M, Qt::ControlModifier | Qt::AltModifier); QTRY_COMPARE(view->model()->columnCount(), 9);
        auto* editor = window.findChild<QLineEdit*>(); QVERIFY(editor); editor->setFocus(); QTRY_VERIFY(!command->isEnabled());
        QWidget external; QLineEdit outside(&external); external.show(); external.activateWindow(); outside.setFocus(); QTest::qWait(50); QVERIFY(!command->isEnabled());
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 外部入力からタブをクリックした直後もQPE内のタブキー操作へ移れる。 */
    void clickedTabKeyboardFocus() {
        QWidget host; auto* layout = new QVBoxLayout(&host); auto* outside = new QLineEdit;
        auto* browser = new qpe::BrowserWindow(&host); layout->addWidget(outside); layout->addWidget(browser);
        browser->navigate(path("A")); browser->addTab(path("B"));
        host.resize(1000, 700); host.show(); host.activateWindow(); QTRY_VERIFY(browser->ready());
        outside->setFocus(); QTRY_VERIFY(outside->hasFocus());
        auto* tabs = browser->findChild<QTabBar*>("folderTabs"); QVERIFY(tabs);
        QTest::mouseClick(tabs, Qt::LeftButton, {}, tabs->tabRect(0).center());
        QTRY_VERIFY(tabs->hasFocus());
        QTest::keyClick(tabs, Qt::Key_Tab, Qt::ControlModifier); QCOMPARE(tabs->currentIndex(), 1);
        QTest::keyClick(tabs, Qt::Key_Tab, Qt::ControlModifier | Qt::ShiftModifier); QCOMPARE(tabs->currentIndex(), 0);
        outside->setFocus(); QTRY_VERIFY(outside->hasFocus());
        QToolButton* add = nullptr;
        for (auto* button : browser->findChildren<QToolButton*>()) if (button->accessibleName() == "New tab") add = button;
        QVERIFY(add); QTest::mouseClick(add, Qt::LeftButton); QTRY_VERIFY(add->hasFocus());
        const int created = tabs->currentIndex();
        QTest::keyClick(add, Qt::Key_Tab, Qt::ControlModifier | Qt::ShiftModifier);
        QCOMPARE(tabs->currentIndex(), (created + tabs->count() - 1) % tabs->count());
        outside->setFocus(); QTRY_VERIFY(outside->hasFocus());
        const int before = tabs->currentIndex(); QTest::keyClick(outside, Qt::Key_Tab, Qt::ControlModifier);
        QCOMPARE(tabs->currentIndex(), before); host.close();
    }
    /** @brief 旧設定形式の往復、固有パスの除外、不正入力の全件拒否を確認する。 */
    void portablePreferences() {
        const auto before = qpe::readSettings();
        qpe::writeSettings({{"favorites", QJsonArray{path("A")}}, {"preferences", QJsonObject{{"undoDays", 30}}}, {"nativeAppearance", QJsonObject{{"textSize", 10}, {"theme", "dark"}}}, {"commandKeys", QJsonObject{{"palette", "Ctrl+Shift+P"}}}});
        const auto target = path("preferences.json"); qpe::exportPreferences(target);
        auto data = qpe::loadJson(target); QCOMPARE(data["format"].toString(), QString("qpe.preferences"));
        QVERIFY(!data["settings"].toObject().contains("favorites")); QVERIFY(!data["settings"].toObject().contains("nativeWorkspace"));
        qpe::importPreferences(target); QCOMPARE(qpe::readSettings()["nativeAppearance"].toObject()["textSize"].toInt(), 10);
        qpe::exportPreferences(target, true); data = qpe::loadJson(target); QVERIFY(data["settings"].toObject().contains("favorites"));
        const auto valid = qpe::readSettings(); auto items = data["settings"].toObject(); items["commandKeys"] = QJsonObject{{"palette", "Ctrl+C"}}; data["settings"] = items; qpe::saveJson(target, data);
        QVERIFY_EXCEPTION_THROWN(qpe::importPreferences(target), std::invalid_argument); QCOMPARE(qpe::readSettings(), valid);
        items.remove("commandKeys"); items["fileLabels"] = QJsonObject{{"bad", QJsonObject{{"rating", 1.5}}}}; data["settings"] = items; qpe::saveJson(target, data);
        QVERIFY_EXCEPTION_THROWN(qpe::importPreferences(target), std::invalid_argument); QCOMPARE(qpe::readSettings(), valid);
        items.remove("fileLabels"); items["nativeWorkspace"] = QJsonObject{}; data["settings"] = items; qpe::saveJson(target, data);
        QVERIFY_EXCEPTION_THROWN(qpe::importPreferences(target), std::invalid_argument);
        QVERIFY_EXCEPTION_THROWN(qpe::validateCommandKeys({{"a", "Ctrl+Shift+J"}, {"b", "Ctrl+Shift+J"}}), std::invalid_argument);
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 空/日本語/多数ファイルを用意する。 */
    void initTestCase() {
        QVERIFY(data_.isValid());
        qputenv("QPE_SETTINGS_FILE", path("settings.json").toUtf8());
        qpe::writeSettings({{"uiLanguage", "en"}}); qpe::setUiLanguage("en");
        QVERIFY(QDir().mkpath(path("A/子フォルダー/empty")));
        QVERIFY(QDir().mkpath(path("B")));
        QVERIFY(file("A/小さい.mb", 20));
        QVERIFY(file("A/大きい.ma", 100));
        QVERIFY(file("A/.hidden.txt"));
        QVERIFY(file("B/別のファイル.txt"));
        QVERIFY(QDir().mkpath(path("many")));
        for (int i = 0; i < 5000; ++i) QVERIFY(file(QString("many/日本語_%1.txt").arg(i, 5, 10, QChar('0'))));
    }
    /** @brief 既存の英語UI検査は言語を明示し、日本語ケースでは各ケース内で既定値を検査する。 */
    void init() { qpe::writeSettings({{"uiLanguage", "en"}}); qpe::setUiLanguage("en"); }
    /** @brief 日本語既定と英語の再表示でも、名前・フィルターID・Mayaオプションを翻訳しない。 */
    void japaneseUiAndStableValues() {
        const auto before = qpe::readSettings(); auto defaults = before; defaults.remove("uiLanguage");
        QVERIFY(QDir().mkpath(path("i18n"))); QVERIFY(file("i18n/Name.ma")); QVERIFY(file("i18n/Open.txt")); QVERIFY(file("i18n/Name"));
        defaults["favorites"] = QJsonArray{path("i18n/Name")}; qpe::saveJson(qpe::settingsPath(), defaults);
        QCOMPARE(qpe::savedUiLanguage(), QString("ja")); const auto globalPalette = QApplication::palette(); const auto locale = QLocale().name();
        QLabel unrelated("Open");
        {
            qpe::BrowserWindow window; window.restoreSession(path("i18n"), false); window.show(); QTRY_VERIFY(window.ready());
            QCOMPARE(window.property("uiLanguage").toString(), QString("ja"));
            auto* files = window.findChild<QTreeView*>("files"); QCOMPARE(files->model()->headerData(0, Qt::Horizontal).toString(), QString::fromUtf8("名前"));
            auto* types = window.findChild<QComboBox*>("fileTypes"); QCOMPARE(types->itemText(0), QString::fromUtf8("すべてのファイル")); QCOMPARE(types->itemData(0).toString(), QString("All files"));
            types->setCurrentIndex(1); QTRY_COMPARE(files->model()->rowCount(), 1); QCOMPARE(types->currentData().toString(), QString("Maya scenes"));
            auto* places = window.findChild<QTreeWidget*>("places"); QCOMPARE(places->topLevelItem(0)->text(0), QString::fromUtf8("お気に入り")); QCOMPARE(places->topLevelItem(0)->child(0)->text(0), QString("Name"));
            qpe::Inspector inspector(true, &window);
            QCOMPARE(inspector.findChild<QComboBox*>("import_mode")->itemText(0), QString::fromUtf8("ファイル名"));
            inspector.restore({{"reference", QJsonObject{{"mode", "custom"}, {"name", "Open"}}}, {"fbx", QJsonObject{{"mode", "exmerge"}}}});
            QCOMPARE(inspector.findChild<QLineEdit*>("reference_name")->text(), QString("Open"));
            QCOMPARE(inspector.options()["reference"].toObject()["mode"].toString(), QString("custom"));
            QCOMPARE(inspector.findChild<QComboBox*>("fbx_mode")->currentText(), QString::fromUtf8("アニメーションのみを更新"));
            bool settingsSeen = false;
            QTimer::singleShot(0, &window, [&] {
                auto* dialog = window.findChild<QDialog*>("qpePreferences"); QVERIFY(dialog);
                auto* language = dialog->findChild<QComboBox*>("uiLanguage"); QVERIFY(language);
                QCOMPARE(language->currentData().toString(), QString("ja")); auto* buttons = dialog->findChild<QDialogButtonBox*>(); QVERIFY(buttons);
                QCOMPARE(buttons->button(QDialogButtonBox::Save)->text(), QString::fromUtf8("保存"));
                language->setCurrentIndex(1); settingsSeen = true; buttons->button(QDialogButtonBox::Save)->click();
            });
            window.perform("settings"); QVERIFY(settingsSeen); QCOMPARE(qpe::savedUiLanguage(), QString("en"));
            QCOMPARE(window.property("uiLanguage").toString(), QString("ja")); window.close();
        }
        const auto states = qpe::readSettings()["nativeWorkspace"].toObject()["states"].toArray(); QVERIFY(!states.isEmpty());
        QCOMPARE(states.first().toObject()["filterKind"].toString(), QString("Maya scenes"));
        {
            qpe::BrowserWindow window; window.restoreSession(); window.show(); QTRY_VERIFY(window.ready());
            QCOMPARE(window.property("uiLanguage").toString(), QString("en"));
            QCOMPARE(window.findChild<QTreeView*>("files")->model()->headerData(0, Qt::Horizontal).toString(), QString("Name"));
            QCOMPARE(window.findChild<QComboBox*>("fileTypes")->currentData().toString(), QString("Maya scenes")); window.close();
        }
        QCOMPARE(unrelated.text(), QString("Open")); QCOMPARE(QApplication::palette(), globalPalette); QCOMPARE(QLocale().name(), locale);
        qpe::saveJson(qpe::settingsPath(), before); qpe::setUiLanguage("en");
    }
    /** @brief ダイアログ本文・入力と設定の転送で、ユーザーの英語名を翻訳しない。 */
    void languageDialogsAndSettingsValidation() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"uiLanguage", "ja"}}); qpe::setUiLanguage("ja");
        QWidget parent;
        QTimer::singleShot(0, &parent, [&] {
            auto* dialog = parent.findChild<QMessageBox*>(); QVERIFY(dialog); QCOMPARE(dialog->text(), QString("Open"));
            QCOMPARE(dialog->button(QMessageBox::Cancel)->text(), QString::fromUtf8("キャンセル")); dialog->button(QMessageBox::Cancel)->click();
        });
        QCOMPARE(qpe::UiMessageBox::question(&parent, qpe::uiText("Delete"), "Open", QMessageBox::Yes | QMessageBox::Cancel), QMessageBox::Cancel);
        bool accepted = false;
        QTimer::singleShot(0, &parent, [&] {
            auto* dialog = parent.findChild<QInputDialog*>(); QVERIFY(dialog); QCOMPARE(dialog->textValue(), QString("Name"));
            QCOMPARE(dialog->cancelButtonText(), QString::fromUtf8("キャンセル")); dialog->accept();
        });
        QCOMPARE(qpe::UiInputDialog::getText(&parent, qpe::uiText("Rename"), qpe::uiText("Name"), QLineEdit::Normal, "Name", &accepted), QString("Name")); QVERIFY(accepted);
        qpe::exportPreferences(path("language-settings.json"));
        QCOMPARE(qpe::loadJson(path("language-settings.json"))["settings"].toObject()["uiLanguage"].toString(), QString("ja"));
        qpe::writeSettings({{"uiLanguage", "en"}}); qpe::importPreferences(path("language-settings.json")); QCOMPARE(qpe::savedUiLanguage(), QString("ja"));
        qpe::saveJson(path("bad-language.json"), {{"format", "qpe.preferences"}, {"version", 1}, {"settings", QJsonObject{{"uiLanguage", "JP"}}}});
        QVERIFY_EXCEPTION_THROWN(qpe::importPreferences(path("bad-language.json")), std::invalid_argument);
        QCOMPARE(qpe::savedUiLanguage(), QString("ja")); QVERIFY_EXCEPTION_THROWN(qpe::setUiLanguage("JP"), std::invalid_argument);
        qpe::saveJson(qpe::settingsPath(), before); qpe::setUiLanguage("en");
    }
    /** @brief 日本語の詳細チェック項目を大きめの文字・狭いペインでも横スクロールなしで読める。 */
    void japaneseInspectorNarrow() {
        qpe::setUiLanguage("ja");
        qpe::Inspector inspector(true, nullptr); QFont font = inspector.font(); font.setPixelSize(15); inspector.setFont(font); inspector.resize(280, 650); inspector.show();
        inspector.showAction("import");
        for (auto* button : inspector.findChildren<QToolButton*>()) if (button->text() == qpe::uiText("Advanced options")) button->setChecked(true);
        QTest::qWait(30); auto* scroll = inspector.findChild<QScrollArea*>("inspectorScroll"); QVERIFY(scroll);
        QCOMPARE(scroll->horizontalScrollBar()->maximum(), 0);
        inspector.close(); qpe::setUiLanguage("en");
    }
    /** @brief 日本語で保存した検索種別と一致条件を英語UIで読み戻し、検索名も変更しない。 */
    void japaneseSearchStoredIds() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"uiLanguage", "ja"}, {"savedSearches", QJsonObject{}}});
        {
            qpe::BrowserWindow window; window.restoreSession(path("B"), false); window.show(); QTRY_VERIFY(window.ready());
            QTimer::singleShot(0, &window, [&] {
                auto* dialog = window.findChild<QDialog*>("qpeSearchOptions"); QVERIFY(dialog);
                auto* kind = dialog->findChild<QComboBox*>("searchKind"); auto* tags = dialog->findChild<QComboBox*>("searchTagMode"); QVERIFY(kind && tags);
                QCOMPARE(kind->itemText(2), QString::fromUtf8("ファイルとフォルダー")); kind->setCurrentIndex(2); tags->setCurrentIndex(1);
                QPushButton* save = nullptr; for (auto* button : dialog->findChildren<QPushButton*>()) if (button->text() == qpe::uiText("Save search…")) save = button; QVERIFY(save);
                QTimer::singleShot(0, dialog, [&] { auto* prompt = window.findChild<QInputDialog*>(); QVERIFY(prompt); prompt->setTextValue("Open"); prompt->accept(); });
                save->click(); dialog->reject();
            });
            window.perform("search"); window.close();
        }
        const auto saved = qpe::readSettings()["savedSearches"].toObject(); QVERIFY(saved.contains("Open"));
        QCOMPARE(saved["Open"].toObject()["kind"].toString(), QString("Both")); QCOMPARE(saved["Open"].toObject()["tagMode"].toString(), QString("Any"));
        qpe::writeSettings({{"uiLanguage", "en"}});
        {
            qpe::BrowserWindow window; window.restoreSession(path("B"), false); window.show(); QTRY_VERIFY(window.ready()); bool checked = false;
            QTimer::singleShot(0, &window, [&] {
                auto* dialog = window.findChild<QDialog*>("qpeSearchOptions"); QVERIFY(dialog);
                QComboBox* presets = nullptr; for (auto* combo : dialog->findChildren<QComboBox*>()) if (combo->findText("Open") >= 0) presets = combo; QVERIFY(presets);
                presets->setCurrentIndex(presets->findText("Open"));
                QCOMPARE(dialog->findChild<QComboBox*>("searchKind")->currentData().toString(), QString("Both"));
                QCOMPARE(dialog->findChild<QComboBox*>("searchTagMode")->currentData().toString(), QString("Any")); checked = true; dialog->reject();
            });
            window.perform("search"); QVERIFY(checked); window.close();
        }
        qpe::saveJson(qpe::settingsPath(), before); qpe::setUiLanguage("en");
    }
    /** @brief 日本語の同名確認でスキップ/置き換えを正しく実行し、元に戻せる。 */
    void japaneseConflictPolicies() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"uiLanguage", "ja"}});
        qpe::setUiLanguage("ja");
        for (const auto& caption : {"Rename…", "Copy Path", "Create Copy", "Batch Rename…", "Use regular expression"}) QVERIFY(qpe::uiText(caption) != caption);
        QVERIFY(QDir().mkpath(path("jp-copy/source"))); QVERIFY(QDir().mkpath(path("jp-copy/target")));
        QVERIFY(file("jp-copy/source/Name.txt", 8)); QVERIFY(file("jp-copy/target/Name.txt", 15));
        qpe::BrowserWindow window; window.restoreSession(path("jp-copy/source"), false); window.show(); QTRY_VERIFY(window.ready());
        for (const int choice : {1, 2}) {
            QTimer::singleShot(0, &window, [&] {
                auto* prompt = window.findChild<QInputDialog*>(); QVERIFY(prompt); auto* items = prompt->findChild<QComboBox*>(); QVERIFY(items);
                QCOMPARE(items->itemText(choice), qpe::uiText(choice == 1 ? "Skip" : "Replace (keep Undo backup)")); items->setCurrentIndex(choice);
                QCOMPARE(prompt->textValue(), items->currentText()); prompt->accept();
            });
            window.perform("copyTo", {path("jp-copy/source/Name.txt")}, path("jp-copy/target")); QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 10000);
            QCOMPARE(QFileInfo(path("jp-copy/target/Name.txt")).size(), qint64(choice == 1 ? 15 : 8));
            // 置き換えでは同じボリュームへUndo用の隠しバックアップを残す。
            if (choice == 1) QCOMPARE(QDir(path("jp-copy/target")).entryList(QDir::Files).size(), 1);
        }
        window.perform("undo"); QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 10000); QCOMPARE(QFileInfo(path("jp-copy/target/Name.txt")).size(), qint64(15));
        window.close(); qpe::saveJson(qpe::settingsPath(), before); qpe::setUiLanguage("en");
    }
    /** @brief 右クリックのヘルパー経由でも日本語の操作名が表示される。 */
    void japaneseContextMenu() {
        const auto before = qpe::readSettings(); qpe::writeSettings({{"uiLanguage", "ja"}});
        QVERIFY(QDir().mkpath(path("menu-jp/child")));
        qpe::BrowserWindow window; window.navigate(path("menu-jp")); window.show(); QTRY_VERIFY(window.ready());
        QListView* column = nullptr;
        for (auto* candidate : window.findChildren<QListView*>("folderColumn"))
            if (candidate->property("path").toString() == path("menu-jp")) column = candidate;
        QVERIFY(column); QTRY_COMPARE(column->model()->rowCount(), 1);
        QStringList labels;
        QTimer::singleShot(50, &window, [&] {
            auto* menu = qobject_cast<QMenu*>(QApplication::activePopupWidget());
            if (!menu) return;
            for (auto* action : menu->actions()) labels.append(action->text());
            for (auto* child : menu->findChildren<QMenu*>()) for (auto* action : child->actions()) labels.append(action->text());
            menu->close();
        });
        window.contextMenu(column, column->visualRect(column->model()->index(0, 0)).center(), path("menu-jp"));
        for (const auto& label : {"名前の変更…", "パスとしてコピー", "コピーの作成", "名前の一括変更…", "開始フォルダーに設定"}) QVERIFY2(labels.contains(label), label);
        QVERIFY(QFileInfo::exists(path("menu-jp/child")));
        window.close(); qpe::saveJson(qpe::settingsPath(), before); qpe::setUiLanguage("en");
    }
    /** @brief ファイルと背景を区別し、別項目への右クリックで選択と固定対象を取り違えない。 */
    void focusedContextMenu() {
        QVERIFY(QDir().mkpath(path("menu-focused"))); QVERIFY(file("menu-focused/first.txt", 4)); QVERIFY(file("menu-focused/second.txt", 5));
        qpe::BrowserWindow window; window.navigate(path("menu-focused")); window.show(); QTRY_VERIFY(window.ready());
        auto* files = window.findChild<QTreeView*>("files"); auto* model = files->model(); QCOMPARE(model->rowCount(), 2);
        const auto first = model->index(0, 0), second = model->index(1, 0); const auto expected = first.data(Qt::UserRole + 1).toString();
        files->selectionModel()->setCurrentIndex(second, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
        bool selectedMenu = false;
        QTimer::singleShot(20, &window, [&] {
            auto* menu = qobject_cast<QMenu*>(QApplication::activePopupWidget()); if (!menu) return;
            selectedMenu = menu->actions().size() <= 15 && menu->findChild<QMenu*>("contextMore") && !menu->findChild<QMenu*>("contextNew")
                && !menu->findChild<QAction*>("context_refresh") && !menu->findChild<QAction*>("context_undo")
                && menu->defaultAction() && menu->defaultAction()->objectName() == "context_open" && files->selectionModel()->selectedRows().first() == second;
            // 固定された対象は選択変更で置き換えられない。コピー結果の実URLまで照合する。
            files->selectionModel()->setCurrentIndex(second, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            QTest::keyClick(menu, Qt::Key_C, Qt::ControlModifier);
            menu->close();
        });
        window.contextMenu(files, files->visualRect(first).center(), path("menu-focused")); QVERIFY(selectedMenu);
        QTRY_VERIFY(QApplication::clipboard()->mimeData()->hasUrls()); QCOMPARE(QApplication::clipboard()->mimeData()->urls().first().toLocalFile(), expected);
        bool background = false;
        QTimer::singleShot(20, &window, [&] {
            auto* menu = qobject_cast<QMenu*>(QApplication::activePopupWidget()); if (!menu) return;
            background = menu->findChild<QMenu*>("contextNew") && menu->findChild<QAction*>("context_refresh") && !menu->findChild<QAction*>("context_trash") && !menu->findChild<QAction*>("context_copy"); menu->close();
        });
        window.contextMenu(files, QPoint(-10, -10), path("menu-focused")); QVERIFY(background);
        QCOMPARE(files->selectionModel()->selectedRows().first(), second); window.close();
    }
    /** @brief 用途別の設定を検索し、Cancelでプレビューを復元し、Saveで全ページの編集を保存する。 */
    void organizedPreferences() {
        const auto before = qpe::readSettings(); qpe::BrowserWindow window; window.navigate(path("A")); window.show();
        const auto font = window.font(); const auto width = qpe::readSettings()["columnWidthMode"].toString("fit"); bool inspected = false;
        QTimer::singleShot(0, &window, [&] {
            auto* dialog = window.findChild<QDialog*>("qpePreferences"); if (!dialog) return;
            auto* tabs = dialog->findChild<QTabWidget*>("settingsTabs");
            inspected = tabs && tabs->count() == 5 && tabs->currentIndex() == 0;
            tabs->setCurrentIndex(1); dialog->findChild<QSpinBox*>("displayFontSize")->setValue(18); inspected &= window.font() != font;
            dialog->findChild<QComboBox*>("columnWidthMode")->setCurrentIndex(width == "fit" ? 1 : 0);
            tabs->setCurrentIndex(3); dialog->findChild<QLineEdit*>("shortcutFilter")->setText("Ctrl+Shift+J");
            auto* tree = dialog->findChild<QTreeWidget*>("shortcutCommands"); int visible = 0; for (int i = 0; i < tree->topLevelItemCount(); ++i) visible += !tree->topLevelItem(i)->isHidden(); inspected &= visible == 1;
            tabs->setCurrentIndex(4); dialog->findChild<QLineEdit*>("everythingExecutable")->setText("not-saved.exe"); dialog->reject();
        });
        window.perform("settings"); QVERIFY(inspected); QCOMPARE(window.font(), font); QCOMPARE(qpe::readSettings()["columnWidthMode"].toString("fit"), width);
        QCOMPARE(qpe::readSettings().value("everythingExecutable"), before.value("everythingExecutable"));
        QTimer::singleShot(0, &window, [&] {
            auto* dialog = window.findChild<QDialog*>("qpePreferences"); if (!dialog) return;
            dialog->findChild<QSpinBox*>("undoDays")->setValue(42); dialog->findChild<QLineEdit*>("everythingExecutable")->setText("selected.exe");
            dialog->findChild<QDialogButtonBox*>()->button(QDialogButtonBox::Save)->click();
        });
        window.perform("settings"); QCOMPARE(qpe::readSettings()["preferences"].toObject()["undoDays"].toInt(), 42);
        QCOMPARE(qpe::readSettings()["everythingExecutable"].toString(), QString("selected.exe"));
        window.close(); qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief ホストがダークでも設定の明示ライトを保ち、表示プレビューでコントラストが壊れない。 */
    void preferencesThemeContrast() {
        const auto before = qpe::readSettings(); const auto appPalette = QApplication::palette();
        auto dark = appPalette; dark.setColor(QPalette::Base, QColor("#202020")); dark.setColor(QPalette::Text, Qt::white); dark.setColor(QPalette::Window, QColor("#202020"));
        QApplication::setPalette(dark);
        qpe::writeSettings({{"nativeAppearance", QJsonObject{{"theme", "light"}}}});
        qpe::BrowserWindow window; window.restoreSession(path("A"), false); window.show(); bool contrast = true;
        QTimer::singleShot(0, &window, [&] {
            auto* dialog = window.findChild<QDialog*>("qpePreferences"); auto* tabs = dialog->findChild<QTabWidget*>("settingsTabs");
            auto* language = dialog->findChild<QComboBox*>("uiLanguage");
            const auto check = [&] {
                language->ensurePolished(); const auto image = language->grab().toImage();
                const auto background = image.pixelColor(qRound(image.width() * .75), image.height() / 2);
                const bool light = window.palette().color(QPalette::Base).lightness() > 128;
                contrast &= (background.lightness() > 128) == light;
                contrast &= (language->palette().color(QPalette::Text).lightness() < 128) == light;
            };
            check(); tabs->setCurrentIndex(1);
            for (auto* combo : dialog->findChildren<QComboBox*>()) if (combo->findData("light") >= 0) {
                combo->setCurrentIndex(combo->findData("dark")); tabs->setCurrentIndex(0); check();
                tabs->setCurrentIndex(1); combo->setCurrentIndex(combo->findData("light")); tabs->setCurrentIndex(0); check(); break;
            }
            dialog->reject();
        });
        window.perform("settings"); window.close(); QApplication::setPalette(appPalette); qpe::saveJson(qpe::settingsPath(), before); QVERIFY(contrast);
    }
    /** @brief 設定のキー保存、破損保護、ロック競合を検証する。 */
    void persistentSettings() {
        qpe::writeSettings({{"favorites", QJsonArray{path("A")}}});
        qpe::writeSettings({{"nativeTheme", "dark"}});
        QCOMPARE(qpe::readSettings()["favorites"].toArray().size(), 1);
        QLockFile lock(qpe::settingsPath() + ".lock"); QVERIFY(lock.tryLock());
        QVERIFY_EXCEPTION_THROWN(qpe::writeSettings({{"nativeTheme", "light"}}), std::runtime_error);
        lock.unlock();
        QFile corrupt(qpe::settingsPath()); QVERIFY(corrupt.open(QIODevice::WriteOnly)); corrupt.write("{broken"); corrupt.close();
        QVERIFY_EXCEPTION_THROWN(qpe::writeSettings({{"nativeTheme", "light"}}), std::runtime_error);
        QVERIFY(corrupt.open(QIODevice::ReadOnly)); QCOMPARE(corrupt.readAll(), QByteArray("{broken")); corrupt.close();
        qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief 日本語ZIPの作成・部分展開・Undo・不正な出力先を実ファイルで検証する。 */
    void archives() {
        qpe::FileOperations operations(path("zip-history"));
        auto result = operations.run({"createZip", {path("A")}, path("日本語.zip")});
        QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join("\n")));
        QVERIFY(QFileInfo::exists(path("日本語.zip")));
        result = operations.run({"browseZip", {path("日本語.zip")}});
        QVERIFY(result.extra["rows"].toArray().size() >= 4);
        result = operations.run({"extractZip", {path("日本語.zip")}, path("extracted"), "rename", {{"entries", QJsonArray{"A/小さい.mb"}}}});
        QVERIFY(result.errors.isEmpty()); QVERIFY(QFileInfo::exists(path("extracted/A/小さい.mb")));
        QVERIFY(!QFileInfo::exists(path("extracted/A/大きい.ma")));
        QVERIFY(operations.run({"undo"}).errors.isEmpty()); QVERIFY(!QFileInfo::exists(path("extracted")));
        QVERIFY(operations.run({"redo"}).errors.isEmpty()); QVERIFY(QFileInfo::exists(path("extracted/A/小さい.mb")));
        QVERIFY_EXCEPTION_THROWN(operations.run({"createZip", {path("A")}, path("A/recursive.zip")}), std::runtime_error);
    }
    /** @brief 外部ZIPの逸脱/重複を、ファイル作成前に拒否する。 */
    void unsafeArchives() {
        for (const auto& names : QList<QStringList>{{"../escape.txt"}, {"A.txt", "a.txt"}, {"safe/CON.txt"}, {"file", "file/child"}}) {
            mz_zip_archive zip{}; QVERIFY(mz_zip_writer_init_heap(&zip, 0, 0));
            for (const auto& name : names) QVERIFY(mz_zip_writer_add_mem(&zip, name.toUtf8().constData(), "test", 4, 0));
            void* bytes = nullptr; size_t size = 0; QVERIFY(mz_zip_writer_finalize_heap_archive(&zip, &bytes, &size));
            QFile file(path("unsafe.zip")); QVERIFY(file.open(QIODevice::WriteOnly)); file.write(static_cast<char*>(bytes), qint64(size)); file.close(); mz_free(bytes); mz_zip_writer_end(&zip);
            QVERIFY_EXCEPTION_THROWN(qpe::inspectArchive(path("unsafe.zip")), std::exception);
            QVERIFY(!QFileInfo::exists(path("escape.txt")));
        }
    }
    /** @brief 結合は行先専用の項目を保ち、元と置換先をUndo/Redoで戻せる。 */
    void folderMerge() {
        for (const auto& name : {"merge-source/shared", "merge-target/shared"}) QVERIFY(QDir().mkpath(path(name)));
        QVERIFY(file("merge-source/shared/conflict.txt", 30)); QVERIFY(file("merge-source/shared/added.txt", 40));
        QVERIFY(file("merge-target/shared/conflict.txt", 10)); QVERIFY(file("merge-target/shared/retained.txt", 20));
        const auto sourceStamp = qpe::fileFingerprint(path("merge-source/shared"));
        const auto targetStamp = qpe::fileFingerprint(path("merge-target/shared"));
        qpe::FileOperations engine(path("merge-history"));
        QVERIFY_EXCEPTION_THROWN(engine.run({"move", {path("merge-source/shared")}, path("merge-target"), "merge"}), std::runtime_error);
        auto result = engine.run({"copy", {path("merge-source/shared")}, path("merge-target"), "merge", {{"choices", QJsonObject{{"conflict.txt", "rename"}}}}});
        QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join("\n")));
        QCOMPARE(qpe::fileFingerprint(path("merge-source/shared")), sourceStamp);
        QCOMPARE(QFileInfo(path("merge-target/shared/conflict.txt")).size(), qint64(10));
        QCOMPARE(QFileInfo(path("merge-target/shared/conflict (2).txt")).size(), qint64(30));
        QVERIFY(QFileInfo::exists(path("merge-target/shared/retained.txt")));
        QVERIFY(QFileInfo::exists(path("merge-target/shared/added.txt")));
        QVERIFY(engine.run({"undo"}).errors.isEmpty());
        QCOMPARE(qpe::fileFingerprint(path("merge-source/shared")), sourceStamp);
        QCOMPARE(qpe::fileFingerprint(path("merge-target/shared")), targetStamp);
        QVERIFY(engine.run({"redo"}).errors.isEmpty());
        QVERIFY(QFileInfo::exists(path("merge-target/shared/added.txt")));
        QVERIFY(file("merge-target/shared/retained.txt", 21));
        QVERIFY_EXCEPTION_THROWN(engine.run({"undo"}), std::runtime_error);
    }
    /** @brief 待機記録は明示再開し、完了済みを重複コピーしない。 */
    void resumableTransfers() {
        QVERIFY(QDir().mkpath(path("resume/source"))); QVERIFY(QDir().mkpath(path("resume/destination"))); QVERIFY(file("resume/source/file.txt", 192));
        QString id;
        {
            qpe::FileJobs jobs; jobs.pauseQueue(true); jobs.enqueue({"copy", {path("resume/source/file.txt")}, path("resume/destination")});
            id = jobs.records()[0].toObject()["id"].toString(); QVERIFY(!id.isEmpty());
            QVERIFY(!QFileInfo::exists(path("resume/destination/file.txt")));
        }
        {
            qpe::FileJobs jobs; QSignalSpy finished(&jobs, &qpe::FileJobs::finished); jobs.resume(id);
            QTRY_COMPARE_WITH_TIMEOUT(finished.size(), 1, 10000);
            const auto result = qpe::fileResultFromJson(finished[0][0].toJsonObject()); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join("\n")));
        }
        const auto recordPath = qpe::operationsDirectory() + "/jobs/" + id + ".json"; auto record = qpe::loadJson(recordPath);
        QCOMPARE(record["state"].toString(), QString("completed"));
        // 確定直後に結果通知を失った状況を再現。履歴の確定記録を照合して転送を重複しない。
        record["state"] = "running"; qpe::saveJson(recordPath, record);
        qpe::FileJobs jobs; QSignalSpy finished(&jobs, &qpe::FileJobs::finished); jobs.resume(id);
        QTRY_COMPARE_WITH_TIMEOUT(finished.size(), 1, 10000);
        QVERIFY(qpe::fileResultFromJson(finished[0][0].toJsonObject()).errors.isEmpty());
        QCOMPARE(QDir(path("resume/destination")).entryList(QDir::Files).size(), 1);
        record["state"] = "failed"; qpe::saveJson(recordPath, record); QVERIFY(file("resume/destination/file.txt", 200));
        jobs.resume(id); QTRY_COMPARE_WITH_TIMEOUT(finished.size(), 2, 10000);
        QVERIFY(!qpe::fileResultFromJson(finished[1][0].toJsonObject()).errors.isEmpty());
    }
    /** @brief 静止画像と文字コード検索をアプリ/シーン起動なしで取得する。 */
    void mediaAndEncodedSearch() {
        QImage source(640, 480, QImage::Format_RGB32); source.fill(Qt::red); QVERIFY(source.save(path("thumbnail.png")));
        qpe::FileOperations engine(path("media-history")); auto result = engine.run({"media", {path("thumbnail.png")}, {}, "rename", {{"token", "generation-2"}}});
        QCOMPARE(result.extra["token"].toString(), QString("generation-2")); QCOMPARE(result.extra["width"].toInt(), 640);
        QImage image; QVERIFY(image.loadFromData(QByteArray::fromBase64(result.extra["png"].toString().toLatin1()))); QCOMPARE(image.size(), QSize(320, 240));
        QVERIFY(QDir().mkpath(path("encoded/skip"))); QFile utf16(path("encoded/file.txt")); QVERIFY(utf16.open(QIODevice::WriteOnly));
        utf16.write(QByteArray::fromHex("fffe41000a00668a139a")); utf16.close();
        result = engine.run({"media", {path("encoded/file.txt")}}); QCOMPARE(result.extra["text"].toString(), QString::fromUtf8("A\n試験"));
        QFile cp932(path("encoded/sjis.txt")); QVERIFY(cp932.open(QIODevice::WriteOnly)); cp932.write(QByteArray::fromHex("8e8e8cb1")); cp932.close();
        result = engine.run({"media", {path("encoded/sjis.txt")}}); QCOMPARE(result.extra["text"].toString(), QString::fromUtf8("試験"));
        result = engine.run({"search", {path("encoded"), path("encoded")}, {}, "rename", {{"content", "試験"}, {"exclude", "skip"}}});
        QCOMPARE(result.extra["rows"].toArray().size(), 2); QVERIFY(result.extra["rows"].toArray()[0].toObject()["matches"].toArray()[0].toString().startsWith("2:"));
    }
    /** @brief Windowsの短い共有削除ロックでも既存JSONを壊さず保存する。 */
    void transientSettingsLock() {
        const auto name = path("locked-settings.json"); qpe::saveJson(name, {{"value", 1}});
        const auto native = QDir::toNativeSeparators(name);
        const auto handle = CreateFileW(reinterpret_cast<LPCWSTR>(native.utf16()), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        QVERIFY(handle != INVALID_HANDLE_VALUE);
        auto release = std::async(std::launch::async, [handle] { QThread::msleep(100); CloseHandle(handle); });
        qpe::saveJson(name, {{"value", 2}}); release.get(); QCOMPARE(qpe::loadJson(name)["value"].toInt(), 2);
    }
    /** @brief 旧Import/FBXとプリセットを変更せず復元し、ホスト別の文字設定も保つ。 */
    void legacySettings() {
        const QJsonObject import{{"mode", 1}, {"name", "shot:asset"}, {"loadReferenceDepth", 2}, {"executeScriptNodes", false}};
        const QJsonObject original{{"readOptions", QJsonObject{{"import", import}}},
            {"fbxOpenOptions", QJsonObject{{"mode", "exmerge"}, {"timeline", false}}},
            {"readPresets", QJsonObject{{"animation", QJsonObject{{"import", import}}}}},
            {"mayaAppearance", QJsonObject{{"fontSize", 10}}}, {"standaloneAppearance", QJsonObject{{"fontSize", 14}}}};
        qpe::saveJson(qpe::settingsPath(), original);
        qpe::HostServices host; host.maya = true;
        {
            qpe::BrowserWindow window(nullptr, host); window.restoreSession(path("A"));
            QCOMPARE(window.findChild<QComboBox*>("import_mode")->currentData().toString(), QString("custom"));
            QCOMPARE(window.findChild<QLineEdit*>("import_name")->text(), QString("shot:asset"));
            QCOMPARE(window.findChild<QComboBox*>("import_loadReferenceDepth")->currentData().toString(), QString("topOnly"));
            QCOMPARE(window.findChild<QComboBox*>("fbx_mode")->currentData().toString(), QString("exmerge"));
            QVERIFY(!window.findChild<QCheckBox*>("import_executeScriptNodes")->isChecked());
            QCOMPARE(window.font().pixelSize(), 10);
        }
        QCOMPARE(qpe::readSettings(), original);
        QCOMPARE(qpe::readPresetsFromSettings(original, "import")["animation"].toObject(), import);
        auto removed = original; removed["nativeReadPresets"] = QJsonObject{{"import", QJsonObject()}};
        QVERIFY(qpe::readPresetsFromSettings(removed, "import").isEmpty());
        {
            qpe::BrowserWindow window; window.restoreSession(path("A")); QCOMPARE(window.font().pixelSize(), 14);
        }
        qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief 右ペインの各読込タブがフォルダータブの幅指定を継承しない。 */
    void narrowInspector() {
        qpe::HostServices host; host.maya = true;
        qpe::BrowserWindow window(nullptr, host); window.navigate(path("A")); window.show();
        auto* inspector = window.findChild<qpe::Inspector*>(); QVERIFY(inspector);
        inspector->setFixedWidth(260); inspector->show();
        inspector->setPath(path("A/非常に長い名前を持ったシーンファイルの内容確認.mb"));
        auto* tabs = inspector->findChild<QTabWidget*>("readOptions"); QVERIFY(tabs);
        QCOMPARE(tabs->count(), 4);
        QCOMPARE(tabs->tabText(0), QString("Open")); QCOMPARE(tabs->tabText(3), QString("Save"));
        auto* scroll = inspector->findChild<QScrollArea*>("inspectorScroll"); QVERIFY(scroll);
        for (int index = 0; index < tabs->count(); ++index) {
            tabs->setCurrentIndex(index);
            QTRY_COMPARE(scroll->horizontalScrollBar()->maximum(), 0);
            QVERIFY(tabs->tabBar()->tabRect(index).width() < 150);
            QVERIFY(tabs->currentWidget()->isVisible());
        }
        tabs->setCurrentIndex(0); inspector->setPath(path("A/animation.fbx"));
        auto* mode = inspector->findChild<QComboBox*>("fbx_mode"); QVERIFY(mode);
        QTRY_VERIFY(mode->isVisible());
        const int paneWidth = inspector->width();
        mode->showPopup(); QTRY_VERIFY(mode->view()->isVisible());
        QVERIFY(mode->view()->width() >= mode->fontMetrics().horizontalAdvance(mode->itemText(4)) + 20);
        mode->hidePopup(); mode->setCurrentIndex(4);
        QCOMPARE(mode->toolTip(), mode->currentText()); QCOMPARE(inspector->width(), paneWidth);
        QTRY_COMPARE(scroll->horizontalScrollBar()->maximum(), 0);
    }
    /** @brief 下段再帰表示は子フォルダーのファイルを集約し、別タブへ混入しない。 */
    void recursivePresentation() {
        QVERIFY(QDir().mkpath(path("recursive/child"))); QVERIFY(file("recursive/root.txt")); QVERIFY(file("recursive/child/nested.txt"));
        qpe::BrowserWindow window; window.navigate(path("recursive")); window.show(); QTRY_VERIFY(window.ready());
        auto* files = window.findChild<QTreeView*>("files"); QCOMPARE(files->model()->rowCount(), 1);
        window.perform("recursiveOn"); QTRY_VERIFY(window.ready()); QCOMPARE(files->model()->rowCount(), 2);
        window.navigate(path("B")); window.navigate(path("recursive")); QTRY_VERIFY(window.ready()); QCOMPARE(files->model()->rowCount(), 2);
        window.perform("recursiveOff"); QTRY_VERIFY(window.ready()); QCOMPARE(files->model()->rowCount(), 1);
        window.perform("view:Thumbnails"); auto* thumbs = window.findChild<QListView*>("thumbnails"); QVERIFY(thumbs->isVisible());
        window.perform("view:Extended details"); QVERIFY(files->isVisible()); QCOMPARE(files->model()->columnCount(), 9);
        window.close();
    }
    /** @brief 詳細は展開時だけ読み、選択変更後の古い成功/失敗は無視する。 */
    void inspectorGeneration() {
        qpe::Inspector inspector(false, nullptr); inspector.show();
        inspector.setPath(path("A/小さい.mb"));
        auto* jobs = inspector.findChild<qpe::FileJobs*>("inspectorMedia"); QVERIFY(jobs); QVERIFY(!jobs->busy());
        inspector.findChild<QToolButton*>("fileDetailsToggle")->click();
        inspector.setPath(path("B/別のファイル.txt"));
        emit jobs->finished({{"errors", QJsonArray{"STALE ERROR"}}, {"extra", QJsonObject{{"path", path("B/別のファイル.txt")}, {"token", "old-generation"}}}});
        QTRY_VERIFY_WITH_TIMEOUT(!jobs->busy(), 10000);
        QCOMPARE(inspector.findChild<QLabel*>("fileTitle")->text(), QString("別のファイル.txt"));
        for (auto* label : inspector.findChildren<QLabel*>()) QVERIFY(!label->text().contains("STALE ERROR"));
        inspector.close();
    }
    /** @brief ウィンドウ再生成後の戻る/進むと絞込み・選択を実モデルで検証する。 */
    void sessionRoundTrip() {
#if QT_VERSION >= QT_VERSION_CHECK(6, 3, 0)
        QTest::failOnWarning(QRegularExpression(".*index from wrong model.*"));
#endif
        qpe::saveJson(qpe::settingsPath(), {});
        {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show();
            QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
            window.findChild<QLineEdit*>("fileFilter")->setText("小さい");
            window.findChild<QComboBox*>("fileTypes")->setCurrentIndex(1);
            auto* files = window.findChild<QTreeView*>("files");
            QCOMPARE(files->model()->rowCount(), 1);
            files->setCurrentIndex(files->model()->index(0, 0));
            window.navigate(path("B")); QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
            window.close();
        }
        {
            qpe::BrowserWindow window; window.restoreSession(); window.show(); window.activateWindow();
            QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
            QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B")));
            QCOMPARE(window.findChild<QComboBox*>("fileTypes")->currentIndex(), 1);
            auto* files = window.findChild<QTreeView*>("files"); files->setFocus();
            QTest::keyClick(files, Qt::Key_Left, Qt::AltModifier);
            QTRY_COMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("A")));
            QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
            QCOMPARE(window.findChild<QLineEdit*>("fileFilter")->text(), QString("小さい"));
            QCOMPARE(files->model()->rowCount(), 1);
            QCOMPARE(window.selectedPaths(), QStringList{path("A/小さい.mb")});
            QTest::keyClick(files, Qt::Key_Right, Qt::AltModifier);
            QTRY_COMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B")));
        }
        qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief 旧Pythonタブの種別番号・選択・閉じたタブを失わず読み込む。 */
    void legacySessionMigration() {
        for (int kind = 0; kind < 5; ++kind) {
            const QJsonObject columnPosition{{"horizontal", 0}, {"vertical", QJsonObject{{path("A"), 0}}}};
            const QJsonObject columnStates{{QDir::toNativeSeparators(path("A")).toLower(), columnPosition}};
            const QJsonObject old{{"path", path("A")}, {"root", path("A")}, {"history", QJsonArray{path("A")}}, {"index", 0},
                {"columns", columnStates},
                {"search", ""}, {"filter", kind}, {"selected", QJsonArray{path("A/小さい.mb")}}, {"vertical", 0}, {"pinned", true}, {"locked", true}};
            qpe::saveJson(qpe::settingsPath(), {{"standaloneLayoutTabs", QJsonObject{{"version", 1}, {"active", 0}, {"states", QJsonArray{old}}, {"closed", QJsonArray{old}}}}});
            qpe::BrowserWindow window; window.restoreSession(); window.show(); QTRY_VERIFY(window.ready());
            QCOMPARE(window.findChild<QComboBox*>("fileTypes")->currentIndex(), QList<int>({0, 1, 3, 6, 5})[kind]);
            if (kind < 2) QTRY_COMPARE(window.selectedPaths(), QStringList{path("A/小さい.mb")});
            window.close();
            const auto current = qpe::readSettings()["nativeWorkspace"].toObject();
            QCOMPARE(current["closed"].toArray().size(), 1);
            QVERIFY(current["states"].toArray()[0].toObject()["pinned"].toBool());
            QVERIFY(current["states"].toArray()[0].toObject()["locked"].toBool());
        }
        qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief 上下比率の切替が選択を保持し、閉じて再生成しても復元される。 */
    void areaLayoutPersistence() {
        qpe::saveJson(qpe::settingsPath(), {});
        {
            qpe::BrowserWindow window; window.navigate(path("A")); window.resize(1100, 850); window.show();
            QTRY_VERIFY(window.ready());
            auto* vertical = window.findChild<QSplitter*>("browserVertical"); QVERIFY(vertical);
            window.perform("area:columns");
            QTRY_VERIFY(vertical->sizes()[0] > vertical->sizes()[1]);
            window.perform("area:files");
            QTRY_VERIFY(vertical->sizes()[0] < vertical->sizes()[1]);
            window.perform("area:balanced");
            QVERIFY(vertical->sizes()[0] > vertical->height() / 3);
            vertical->setSizes({230, 510}); emit vertical->splitterMoved(230, 1);
            window.close();
        }
        const auto saved = qpe::readSettings()["nativeWorkspace"].toObject()["states"].toArray()[0].toObject();
        QCOMPARE(saved["areaMode"].toString(), QString("custom"));
        {
            qpe::BrowserWindow window; window.restoreSession(); window.show(); QTRY_VERIFY(window.ready());
            auto* vertical = window.findChild<QSplitter*>("browserVertical"); QVERIFY(vertical);
            QTRY_VERIFY(vertical->sizes()[0] < vertical->sizes()[1]);
            const auto sizes = saved["areaSizes"].toArray();
            const double before = double(sizes[0].toInt()) / (sizes[0].toInt() + sizes[1].toInt());
            const double after = double(vertical->sizes()[0]) / (vertical->sizes()[0] + vertical->sizes()[1]);
            QVERIFY(qAbs(before - after) < 0.08);
        }
        qpe::saveJson(qpe::settingsPath(), {});
    }
    /** @brief URLドロップのコピー/Shift移動/UndoとリモートURL拒否。Qtイベントによる検証。 */
    void fileDrops() {
        QVERIFY(QDir().mkpath(path("drop/source"))); QVERIFY(QDir().mkpath(path("drop/target")));
        QVERIFY(file("drop/source/copy.txt", 23)); QVERIFY(file("drop/source/move.txt", 41));
        qpe::BrowserWindow window; window.navigate(path("drop/target")); window.show();
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
        auto* target = window.findChild<QTreeView*>("files")->viewport();
        const QPoint point(20, target->height() - 20);
        const auto drop = [&](const QUrl& url, Qt::KeyboardModifiers modifiers) {
            QMimeData mime; mime.setUrls({url});
            QDragEnterEvent enter(point, Qt::CopyAction | Qt::MoveAction, &mime, Qt::LeftButton, modifiers);
            QApplication::sendEvent(target, &enter);
            if (!enter.isAccepted()) return false;
            QDropEvent event(point, Qt::CopyAction | Qt::MoveAction, &mime, Qt::LeftButton, modifiers);
            QApplication::sendEvent(target, &event);
            return event.isAccepted() && event.dropAction() == Qt::CopyAction;
        };
        QVERIFY(!drop(QUrl("https://example.invalid/item"), Qt::NoModifier));
        QVERIFY(drop(QUrl::fromLocalFile(path("drop/source/copy.txt")), Qt::NoModifier));
        QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 10000);
        QCOMPARE(QFileInfo(path("drop/target/copy.txt")).size(), 23LL); QVERIFY(QFileInfo::exists(path("drop/source/copy.txt")));
        QVERIFY(drop(QUrl::fromLocalFile(path("drop/source/move.txt")), Qt::ShiftModifier));
        QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 10000);
        QCOMPARE(QFileInfo(path("drop/target/move.txt")).size(), 41LL); QVERIFY(!QFileInfo::exists(path("drop/source/move.txt")));
        window.perform("undo"); QTRY_VERIFY_WITH_TIMEOUT(!window.busy(), 10000);
        QVERIFY(QFileInfo::exists(path("drop/source/move.txt"))); QVERIFY(!QFileInfo::exists(path("drop/target/move.txt")));
    }
    /** @brief カラムで選択した空フォルダーへのCtrl+Vが親へ誤配達されない。 */
    void pasteIntoSelectedColumnFolder() {
        QVERIFY(QDir().mkpath(path("column-paste/empty"))); QVERIFY(file("column-paste-source.txt", 31));
        qpe::BrowserWindow window; window.navigate(path("column-paste")); window.show(); QTRY_VERIFY(window.ready());
        QListView* column = nullptr;
        for (auto* candidate : window.findChildren<QListView*>("folderColumn"))
            if (candidate->property("path").toString() == path("column-paste")) column = candidate;
        QVERIFY(column); QTRY_COMPARE(column->model()->rowCount(), 1);
        const auto index = column->model()->index(0, 0);
        QTest::mouseClick(column->viewport(), Qt::LeftButton, Qt::NoModifier, column->visualRect(index).center());
        QTRY_COMPARE(window.currentPath(), path("column-paste/empty")); QTRY_VERIFY(window.ready());
        window.perform("copy", {path("column-paste-source.txt")});
        QTRY_COMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(path("column-paste-source.txt"))});
        column->setFocus(); QTest::keyClick(column, Qt::Key_V, Qt::ControlModifier);
        QTRY_VERIFY(!window.busy());
        QVERIFY2(QFileInfo::exists(path("column-paste/empty/column-paste-source.txt")), "Paste must target the selected folder");
        QVERIFY(!QFileInfo::exists(path("column-paste/column-paste-source.txt")));
        window.perform("undo"); QTRY_VERIFY(!window.busy());
        QVERIFY(!QFileInfo::exists(path("column-paste/empty/column-paste-source.txt")));
        QVERIFY(QFileInfo::exists(path("column-paste-source.txt")));
        const auto pasteMenu = [&](const QPoint& point) {
            QTimer::singleShot(50, &window, [] {
                auto* menu = qobject_cast<QMenu*>(QApplication::activePopupWidget()); QVERIFY(menu);
                for (auto* action : menu->actions()) if (action->text() == "Paste") { action->trigger(); menu->close(); return; }
                menu->close(); QFAIL("Paste action was not found");
            });
            window.contextMenu(column, point, path("column-paste"));
        };
        pasteMenu(column->visualRect(column->model()->index(0, 0)).center());
        QTRY_VERIFY(!window.busy()); QVERIFY(QFileInfo::exists(path("column-paste/empty/column-paste-source.txt")));
        window.perform("undo"); QTRY_VERIFY(!window.busy());
        pasteMenu(QPoint(10, column->viewport()->height() - 5));
        QTRY_VERIFY(!window.busy()); QVERIFY(QFileInfo::exists(path("column-paste/column-paste-source.txt")));
        QVERIFY(!QFileInfo::exists(path("column-paste/empty/column-paste-source.txt")));
        window.perform("undo"); QTRY_VERIFY(!window.busy());
        column->setFocus(); QTest::keyClick(column, Qt::Key_C, Qt::ControlModifier);
        QTRY_COMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(path("column-paste/empty"))});
    }
    /** @brief サムネイルの複数選択は行全体でなくてもコピー対象に含める。 */
    void thumbnailSelectionClipboard() {
        QVERIFY(QDir().mkpath(path("thumb-selection")));
        QVERIFY(file("thumb-selection/first.txt")); QVERIFY(file("thumb-selection/second.txt"));
        qpe::BrowserWindow window; window.navigate(path("thumb-selection")); window.show(); QTRY_VERIFY(window.ready());
        window.perform("view:Thumbnails");
        auto* view = window.findChild<QListView*>("thumbnails"); QVERIFY(view); QTRY_VERIFY(view->isVisible());
        QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::NoModifier, view->visualRect(view->model()->index(0, 0)).center());
        QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::ControlModifier, view->visualRect(view->model()->index(1, 0)).center());
        view->setFocus(); QTest::keyClick(view, Qt::Key_C, Qt::ControlModifier);
        QTRY_COMPARE(QApplication::clipboard()->mimeData()->urls().size(), 2);
        auto urls = QApplication::clipboard()->mimeData()->urls();
        QVERIFY(urls.contains(QUrl::fromLocalFile(path("thumb-selection/first.txt"))));
        QVERIFY(urls.contains(QUrl::fromLocalFile(path("thumb-selection/second.txt"))));
        window.navigate(path("B")); QTRY_VERIFY(window.ready());
        window.navigate(path("thumb-selection")); QTRY_VERIFY(window.ready());
        QTRY_COMPARE(window.selectedPaths().size(), 2);
    }
    /** @brief OSクリップボードが占有されても応答を保ち、最後のCopy/Cut要求だけを書き込む。 */
    void transientClipboardLock() {
        qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
        std::promise<bool> acquired; auto ready = acquired.get_future();
        auto blocker = std::async(std::launch::async, [&acquired] {
            // NULLでは同じtaskに関連付くため、別ウィンドウによる占有を明示する。
            const auto owner = CreateWindowExW(0, L"STATIC", L"QPE clipboard test owner", 0, 0, 0, 0, 0,
                                              HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
            bool opened = false;
            for (int i = 0; owner && i < 100 && !opened; ++i) { opened = OpenClipboard(owner); if (!opened) Sleep(10); }
            acquired.set_value(opened);
            if (opened) { Sleep(600); CloseClipboard(); }
            if (owner) DestroyWindow(owner);
        });
        QVERIFY(ready.get());
        QElapsedTimer timer; timer.start();
        window.perform("copy", {path("A/小さい.mb")});
        window.perform("cut", {path("B/別のファイル.txt")});
        QVERIFY2(timer.elapsed() < 200, qPrintable(QString("Copy/Cut blocked for %1 ms").arg(timer.elapsed())));
        blocker.get();
        QTRY_COMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(path("B/別のファイル.txt"))});
        const auto effect = QApplication::clipboard()->mimeData()->data("Preferred DropEffect");
        QCOMPARE(effect.size(), 4); QCOMPARE(effect.at(0), char(2));
    }
    /** @brief 改名後の一覧が届く前に閉じても、復元対象の選択を空で上書きしない。 */
    void renameSelectionBeforeEnumeration() {
        QVERIFY(QDir().mkpath(path("rename-pending"))); QVERIFY(file("rename-pending/before.txt"));
        {
            qpe::BrowserWindow window; window.navigate(path("rename-pending")); window.show(); QTRY_VERIFY(window.ready());
            auto* tree = window.findChild<QTreeView*>("files"); tree->setCurrentIndex(tree->model()->index(0, 0));
            auto jobs = window.findChildren<qpe::FileJobs*>(QString(), Qt::FindDirectChildrenOnly); QVERIFY(!jobs.isEmpty());
            emit jobs.first()->started("rename");
            QVERIFY(QFile::rename(path("rename-pending/before.txt"), path("rename-pending/after.txt")));
            emit jobs.first()->finished({{"completed", QJsonArray{path("rename-pending/after.txt")}},
                {"extra", QJsonObject{{"pathChanges", QJsonArray{QJsonObject{{"from", path("rename-pending/before.txt")}, {"to", path("rename-pending/after.txt")}}}}}}});
            // 列挙完了イベントは意図的に処理せず、保存を先着させる。
            window.close();
        }
        qpe::BrowserWindow restored; restored.restoreSession(); restored.show(); QTRY_VERIFY(restored.ready());
        QTRY_COMPARE(restored.selectedPaths(), QStringList{path("rename-pending/after.txt")});
    }
    /** @brief コピー/移動/置換/作成/リネームを再生成エンジンからUndo/Redoする。 */
    void transactions() {
        QVERIFY(QDir().mkpath(path("ops/source"))); QVERIFY(QDir().mkpath(path("ops/dest")));
        QVERIFY(file("ops/source/日本語.txt", 17));
        const auto history = path("ops/history");
        const auto run = [&](const qpe::FileRequest& req) { try { return qpe::FileOperations(history).run(req); } catch (const std::exception& e) { qWarning() << req.action << e.what(); throw; } };
        auto result = run({"copy", {path("ops/source/日本語.txt")}, path("ops/dest")}); QVERIFY(result.errors.isEmpty());
        QCOMPARE(qpe::fileFingerprint(path("ops/source/日本語.txt")), qpe::fileFingerprint(path("ops/dest/日本語.txt")));
        QVERIFY(run({"undo"}).errors.isEmpty()); QVERIFY(!QFileInfo::exists(path("ops/dest/日本語.txt")));
        QVERIFY(run({"redo"}).errors.isEmpty()); QVERIFY(QFileInfo::exists(path("ops/dest/日本語.txt")));
        QVERIFY(file("ops/source/日本語.txt", 40));
        QVERIFY(run({"move", {path("ops/source/日本語.txt")}, path("ops/dest"), "replace"}).errors.isEmpty());
        QVERIFY(!QFileInfo::exists(path("ops/source/日本語.txt"))); QCOMPARE(QFileInfo(path("ops/dest/日本語.txt")).size(), 40LL);
        run({"undo"}); QCOMPARE(QFileInfo(path("ops/source/日本語.txt")).size(), 40LL); QCOMPARE(QFileInfo(path("ops/dest/日本語.txt")).size(), 17LL);
        run({"redo"}); QVERIFY(!QFileInfo::exists(path("ops/source/日本語.txt"))); QCOMPARE(QFileInfo(path("ops/dest/日本語.txt")).size(), 40LL);
        QVERIFY(file("ops/dest/日本語.txt", 99));
        QVERIFY_EXCEPTION_THROWN(run({"undo"}), std::runtime_error);
        QVERIFY(run({"rename", {path("ops/dest/日本語.txt")}, {}, "rename", {{"name", "changed.txt"}}}).errors.isEmpty());
        run({"undo"}); QVERIFY(QFileInfo::exists(path("ops/dest/日本語.txt")));
        run({"redo"}); QVERIFY(QFileInfo::exists(path("ops/dest/changed.txt")));
        QVERIFY(run({"newFolder", {}, path("ops/dest/new")}).errors.isEmpty());
        run({"undo"}); QVERIFY(!QFileInfo::exists(path("ops/dest/new"))); run({"redo"}); QVERIFY(QFileInfo::exists(path("ops/dest/new")));
        QVERIFY(!run({"copy", {path("ops/dest")}, path("ops/dest/new")}).errors.isEmpty());
        QVERIFY_EXCEPTION_THROWN(qpe::validateFileName("CON.txt"), std::invalid_argument);
        QVERIFY_EXCEPTION_THROWN(qpe::validateFileName("../escape"), std::invalid_argument);
        auto flag = std::make_shared<std::atomic_bool>(true);
        const auto cancelled = qpe::FileOperations(history).run({"copy", {path("ops/dest/changed.txt")}, path("ops/source")}, flag);
        QVERIFY(cancelled.cancelled); QVERIFY(!QFileInfo::exists(path("ops/source/changed.txt")));
    }
    /** @brief 専用ファイルだけをごみ箱へ送り、正確な項目を復元する。 */
    void recycleRoundTrip() {
        QVERIFY(QDir().mkpath(path("recycle")));
        QVERIFY(file("recycle/専用テスト.txt", 71));
        const auto item = path("recycle/専用テスト.txt"), history = path("recycle/history");
        // Shell STAはUIのCOM初期化から分離する。製品と同じワーカー実行条件。
        const auto run = [&](const QString& action) {
            try { return std::async(std::launch::async, [=] { return qpe::FileOperations(history).run({action, {item}}); }).get(); }
            catch (const std::exception& e) { qpe::FileResult failure; failure.errors.append(action + ": " + QString::fromUtf8(e.what())); return failure; }
        };
        auto result = run("trash"); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join('\n')));
        QVERIFY(!QFileInfo::exists(item));
        result = run("undo"); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join('\n')));
        QCOMPARE(QFileInfo(item).size(), 71LL);
        result = run("redo"); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join('\n')));
        QVERIFY(!QFileInfo::exists(item));
        result = run("undo"); QVERIFY2(result.errors.isEmpty(), qPrintable(result.errors.join('\n')));
        QCOMPARE(QFileInfo(item).size(), 71LL);
    }
    /** @brief 検索条件・標準SHA256・重複と比較を実ファイルで検証する。 */
    void queries() {
        QVERIFY(QDir().mkpath(path("queries/a"))); QVERIFY(QDir().mkpath(path("queries/b")));
        QVERIFY(file("queries/a/one.txt", 12)); QVERIFY(file("queries/a/two.txt", 12)); QVERIFY(file("queries/b/one.txt", 15));
        qpe::FileOperations engine(path("query-history"));
        auto result = engine.run({"search", {path("queries/a")}, {}, "rename", {{"query", "o*"}, {"extensions", ".txt"}}});
        QCOMPARE(result.extra["rows"].toArray().size(), 1);
        QCOMPARE(result.extra["rows"].toArray()[0].toObject()["path"].toString(), path("queries/a/one.txt"));
        result = engine.run({"hash", {path("queries/a/one.txt")}});
        QCOMPARE(result.extra["rows"].toArray()[0].toObject()["sha256"].toString(), QString("59ffe12a70df15109e0345955e3230a978f31ebc28d8fe3e42d306afb28b8e81"));
        result = engine.run({"duplicates", {path("queries/a")}}); QCOMPARE(result.extra["rows"].toArray().size(), 2);
        result = engine.run({"compare", {path("queries/a")}, path("queries/b")}); QCOMPARE(result.extra["rows"].toArray().size(), 2);
        result = engine.run({"size", {path("queries/a")}}); QCOMPARE(result.extra["bytes"].toDouble(), 24.0);
        QVERIFY_EXCEPTION_THROWN(engine.run({"search", {path("queries/a")}, {}, "rename", {{"query", "["}, {"regex", true}}}), std::invalid_argument);
    }
    /** @brief 一括リネームは事前衝突検査を行い、一回のUndoで全件を戻す。 */
    void batchRename() {
        QVERIFY(QDir().mkpath(path("batch"))); QVERIFY(file("batch/a.txt")); QVERIFY(file("batch/b.txt"));
        qpe::FileOperations engine(path("batch-history"));
        QJsonObject names{{path("batch/a.txt"), "new_a.txt"}, {path("batch/b.txt"), "new_b.txt"}};
        auto result = engine.run({"batchRename", names.keys(), {}, "rename", {{"names", names}}}); QVERIFY(result.errors.isEmpty()); QCOMPARE(result.completed.size(), 2);
        QVERIFY(QFileInfo::exists(path("batch/new_a.txt"))); QVERIFY(!QFileInfo::exists(path("batch/a.txt")));
        result = engine.run({"undo"}); QCOMPARE(result.completed.size(), 2); QVERIFY(QFileInfo::exists(path("batch/a.txt"))); QVERIFY(QFileInfo::exists(path("batch/b.txt")));
        result = engine.run({"redo"}); QCOMPARE(result.completed.size(), 2); QVERIFY(QFileInfo::exists(path("batch/new_a.txt"))); QVERIFY(QFileInfo::exists(path("batch/new_b.txt")));
        names = {{path("batch/new_a.txt"), "same.txt"}, {path("batch/new_b.txt"), "same.txt"}};
        QVERIFY_EXCEPTION_THROWN(engine.run({"batchRename", names.keys(), {}, "rename", {{"names", names}}}), std::runtime_error);
        QVERIFY(QFileInfo::exists(path("batch/new_a.txt"))); QVERIFY(!QFileInfo::exists(path("batch/same.txt")));
    }
    /** @brief A→B→Aで古い成功/失敗と二重完了をすべて拒否する。 */
    void generationOrdering() {
        qpe::DirectoryStore store;
        store.activate({path("A")});
        const auto old = store.request(path("A"));
        store.activate({path("B")});
        const auto b = store.request(path("B"));
        store.activate({path("A")});
        const auto current = store.request(path("A"));
        QVERIFY(current > old);
        QVERIFY(!store.deliver(path("A"), old, {}, "old failure"));
        QVERIFY(!store.deliver(path("B"), b, {}, {}));
        qpe::DirectoryEntries expected{{"current.txt", false, 123, QDateTime(), 0}};
        QVERIFY(store.deliver(path("A"), current, expected, {}));
        QVERIFY(!store.deliver(path("A"), old, {}, {}));
        QVERIFY(!store.deliver(path("A"), current, {}, "duplicate"));
        QCOMPARE(store.snapshot(path("A"))->entries[0].name, QString("current.txt"));
    }
    /** @brief 部分表示の世代、完了・エラー・再訪・再照会での既存一覧維持を確認する。 */
    void partialEnumerationOrdering() {
        qpe::DirectoryStore store; store.activate({path("A")});
        const auto first = store.request(path("A"));
        const qpe::DirectoryEntries part{{"first.txt", false, 1, {}, 0}};
        QVERIFY(store.deliver(path("A"), first, part, {}, false));
        QVERIFY(!store.snapshot(path("A"))->complete);
        QVERIFY(!store.deliver(path("A"), first, {}, {}, false));
        store.activate({path("B")}); store.activate({path("A")});
        const auto next = store.request(path("A"));
        QVERIFY(!store.deliver(path("A"), first, {}, {}, false));
        QVERIFY(!store.deliver(path("A"), first, {}, "stale error"));
        QVERIFY(store.deliver(path("A"), next, part, {}, false));
        auto full = part; full.append({"last.txt", false, 2, {}, 0});
        QVERIFY(store.deliver(path("A"), next, full, {}));
        QVERIFY(store.snapshot(path("A"))->complete); QCOMPARE(store.snapshot(path("A"))->entries.size(), 2);
        QVERIFY(!store.deliver(path("A"), next, part, {}, false));
        const auto refresh = store.request(path("A"));
        QVERIFY(!store.deliver(path("A"), refresh, part, {}, false));
        QCOMPARE(store.snapshot(path("A"))->entries.size(), 2);
        QVERIFY(store.deliver(path("A"), refresh, {}, "deleted"));
        QVERIFY(store.snapshot(path("A"))->complete); QVERIFY(store.snapshot(path("A"))->entries.isEmpty());
        QCOMPARE(store.snapshot(path("A"))->error, QString("deleted"));
        qpe::DirectoryStore actual; int firstCount = 0, fullCount = 0;
        connect(&actual, &qpe::DirectoryStore::changed, &actual, [&](const QString& directory) {
            const auto* snapshot = actual.snapshot(directory);
            if (snapshot->complete) fullCount = snapshot->entries.size(); else firstCount = snapshot->entries.size();
        });
        actual.activate({path("many")});
        QTRY_COMPARE_WITH_TIMEOUT(fullCount, 5000, 10000); QCOMPARE(firstCount, 100);
    }
    /** @brief 空フォルダー・読込失敗・隠し項目を区別する。 */
    void enumeration() {
        qpe::DirectoryStore store;
        store.activate({path("A"), path("A/子フォルダー/empty"), path("missing")});
        QTRY_VERIFY_WITH_TIMEOUT(store.snapshot(path("A")), 5000);
        QCOMPARE(store.snapshot(path("A"))->entries.size(), 3);
        QTRY_VERIFY_WITH_TIMEOUT(store.snapshot(path("A/子フォルダー/empty")), 5000);
        QVERIFY(store.snapshot(path("A/子フォルダー/empty"))->error.isEmpty());
        QVERIFY(store.snapshot(path("A/子フォルダー/empty"))->entries.isEmpty());
        QTRY_VERIFY_WITH_TIMEOUT(store.snapshot(path("missing")), 5000);
        QVERIFY(!store.snapshot(path("missing"))->error.isEmpty());
        store.setShowHidden(true);
        QTRY_VERIFY_WITH_TIMEOUT(store.snapshot(path("A")), 5000);
        QCOMPARE(store.snapshot(path("A"))->entries.size(), 4);
    }
    /** @brief アクティブ一覧で外部削除が反映される。 */
    void watcherDeletion() {
        QVERIFY(file("B/delete-me.txt"));
        qpe::DirectoryStore store;
        store.activate({path("B")});
        QTRY_VERIFY_WITH_TIMEOUT(store.snapshot(path("B")), 5000);
        QCOMPARE(store.snapshot(path("B"))->entries.size(), 2);
        QVERIFY(QFile::remove(path("B/delete-me.txt")));
        QTRY_COMPARE_WITH_TIMEOUT(store.snapshot(path("B"))->entries.size(), 1, 5000);
    }
    /** @brief 大量列挙直後の破棄でGUIへアクセスしない。 */
    void closeDuringEnumeration() {
        for (int i = 0; i < 20; ++i) {
            auto* store = new qpe::DirectoryStore;
            store->activate({path("many")});
            delete store;
        }
        QTRY_COMPARE_WITH_TIMEOUT(qpe::DirectoryStore::liveWorkers(), 0, 10000);
    }
    /** @brief 選択とサイズソート、独立タブ、逆方向切替、絞込を確認する。 */
    void navigationAndTabs() {
        qpe::BrowserWindow window;
        window.navigate(path("A"));
        window.show();
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
        auto* tabs = window.findChild<QTabBar*>("folderTabs");
        auto trees = window.findChildren<QTreeView*>("files");
        QCOMPARE(trees.size(), 1);
        auto* files = trees[0];
        QCOMPARE(files->model()->rowCount(), 2);
        files->sortByColumn(1, Qt::AscendingOrder);
        QCOMPARE(files->model()->index(0, 0).data().toString(), QString("小さい.mb"));
        files->setCurrentIndex(files->model()->index(0, 0));
        const QString selected = files->currentIndex().data(Qt::UserRole + 1).toString();
        const QModelIndex other = files->model()->index(1, 0);
        QTest::mousePress(files->viewport(), Qt::RightButton, Qt::NoModifier, files->visualRect(other).center());
        QCOMPARE(files->currentIndex().data(Qt::UserRole + 1).toString(), selected);
        window.addTab(path("B"));
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 10000);
        QCOMPARE(tabs->count(), 2);
        tabs->setCurrentIndex(0);
        QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("A")));
        QCOMPARE(files->currentIndex().data(Qt::UserRole + 1).toString(), selected);
        QWidget* pageWidget = files; while (pageWidget && pageWidget->objectName() != "browserPage") pageWidget = pageWidget->parentWidget();
        QVERIFY(pageWidget); auto* filter = pageWidget->findChild<QLineEdit*>("fileFilter");
        QVERIFY(filter);
        filter->setText("小さい");
        QCOMPARE(files->model()->rowCount(), 1);
        window.navigate(path("A/子フォルダー/empty"));
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 5000);
        QCOMPARE(files->model()->rowCount(), 0);
        window.navigate(path("A"));
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 5000);
        QCOMPARE(filter->text(), QString("小さい"));
        QCOMPARE(files->model()->rowCount(), 1);
    }
    /** @brief タブと履歴へ復帰した際、一覧の選択と右詳細が同じファイルを示す。 */
    void restoredSelectionDetails() {
        for (const auto& mode : {QString("Details"), QString("Thumbnails")}) {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
            window.perform("view:" + mode);
            auto* view = mode == "Thumbnails" ? static_cast<QAbstractItemView*>(window.findChild<QListView*>("thumbnails"))
                                               : window.findChild<QTreeView*>("files");
            QVERIFY(view); const auto index = view->model()->index(0, 0); view->setCurrentIndex(index);
            const auto selected = index.data(Qt::UserRole + 1).toString(); QVERIFY(!selected.isEmpty());
            auto* title = window.findChild<QLabel*>("fileTitle"); QVERIFY(title);
            QCOMPARE(title->text(), QFileInfo(selected).fileName());
            window.addTab(path("B")); QTRY_VERIFY(window.ready());
            auto* tabs = window.findChild<QTabBar*>("folderTabs"); tabs->setCurrentIndex(0);
            QCOMPARE(window.selectedPaths(), QStringList{selected});
            QTRY_COMPARE(title->text(), QFileInfo(selected).fileName());
            window.navigate(path("B")); QTRY_VERIFY(window.ready());
            QToolButton* back = nullptr;
            for (auto* button : window.findChildren<QToolButton*>()) if (button->accessibleName() == "Back") back = button;
            QVERIFY(back && back->isEnabled()); back->click(); QTRY_VERIFY(window.ready());
            QTRY_COMPARE(window.selectedPaths(), QStringList{selected});
            QTRY_COMPARE(title->text(), QFileInfo(selected).fileName());
            window.close();
            qpe::BrowserWindow restarted; restarted.restoreSession(); restarted.show(); QTRY_VERIFY(restarted.ready());
            QTRY_COMPARE(restarted.selectedPaths(), QStringList{selected});
            QTRY_COMPARE(restarted.findChild<QLabel*>("fileTitle")->text(), QFileInfo(selected).fileName());
        }
    }
    /** @brief 最後の選択を解除した後に古い詳細対象をファイル操作へ転用しない。 */
    void deselectedFileTarget() {
        for (const auto& mode : {QString("Details"), QString("Thumbnails")}) {
            qpe::BrowserWindow window; window.navigate(path("A")); window.show(); QTRY_VERIFY(window.ready());
            window.perform("view:" + mode);
            auto* view = mode == "Thumbnails" ? static_cast<QAbstractItemView*>(window.findChild<QListView*>("thumbnails"))
                                               : window.findChild<QTreeView*>("files");
            QVERIFY(view); const auto index = view->model()->index(0, 0); view->setCurrentIndex(index);
            QVERIFY(!window.selectedPaths().isEmpty());
            QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::ControlModifier, view->visualRect(index).center());
            QVERIFY(view->selectionModel()->selectedIndexes().isEmpty());
            QVERIFY(window.selectedPaths().isEmpty());
            QCOMPARE(window.findChild<QLabel*>("fileTitle")->text(), QString("Select a file below"));
        }
    }
    /** @brief 初めて開く深いパスの祖先選択を可視化し、以後の手動スクロールを更新で奪わない。 */
    void initialAncestorSelectionVisible() {
        const auto root = path("ancestor-many");
        for (int i = 0; i < 180; ++i) QVERIFY(QDir().mkpath(root + QString("/folder_%1").arg(i, 3, 10, QChar('0'))));
        qpe::BrowserWindow window; window.resize(900, 620); window.show();
        window.navigate(root + "/folder_179"); QTRY_VERIFY(window.ready());
        QListView* column = nullptr;
        for (auto* view : window.findChildren<QListView*>("folderColumn")) if (view->property("path").toString() == root) column = view;
        QVERIFY(column); QTRY_COMPARE(column->model()->rowCount(), 180);
        QTRY_COMPARE(column->currentIndex().data(Qt::UserRole + 1).toString(), root + "/folder_179");
        QTRY_VERIFY(column->viewport()->rect().intersects(column->visualRect(column->currentIndex())));
        auto* horizontal = window.findChild<QScrollArea*>("folderColumns")->horizontalScrollBar();
        QTest::qWait(200); QTRY_COMPARE(horizontal->value(), horizontal->maximum());
        column->verticalScrollBar()->setValue(0);
        horizontal->setValue(0);
        window.refresh(); QTest::qWait(400);
        QCOMPARE(column->verticalScrollBar()->value(), 0);
        QCOMPARE(horizontal->value(), 0);
        window.navigate(root + "/folder_178"); QTRY_VERIFY(window.ready());
        QToolButton* back = nullptr;
        for (auto* button : window.findChildren<QToolButton*>()) if (button->accessibleName() == "Back") back = button;
        QVERIFY(back); back->click(); QTRY_VERIFY(window.ready()); QTest::qWait(100);
        QCOMPARE(column->verticalScrollBar()->value(), 0); QCOMPARE(horizontal->value(), 0);
    }
    /** @brief 新規タブは探索起点と表示比率を引き継ぎ、選択・履歴・ロックは独立させる。 */
    void newTabViewInheritance() {
        const auto before = qpe::readSettings();
        qpe::BrowserWindow window; window.navigate(path("A")); window.resize(1200, 800); window.show();
        QTRY_VERIFY(window.ready()); window.perform("startFolder", {path("A")});
        auto* split = window.findChild<QSplitter*>("browserVertical"); QVERIFY(split);
        split->setSizes({450, 200}); emit split->splitterMoved(450, 1);
        auto* files = window.findChild<QTreeView*>("files"); QVERIFY(files);
        files->setCurrentIndex(files->model()->index(0, 0));
        window.addTab(path("A/子フォルダー/empty")); QTRY_VERIFY(window.ready());
        auto* pages = window.findChild<QStackedWidget*>(); QVERIFY(pages);
        auto* current = pages->currentWidget(); QVERIFY(current);
        auto* columns = current->findChild<QScrollArea*>("folderColumns"); QVERIFY(columns);
        // 空の末尾列は非表示だが、非同期更新用のQObject自体は保持される。
        QTRY_COMPARE(columns->findChildren<QListView*>().size(), 3);
        auto* inheritedSplit = current->findChild<QSplitter*>("browserVertical"); QVERIFY(inheritedSplit);
        QTRY_VERIFY(inheritedSplit->sizes()[0] > inheritedSplit->sizes()[1]);
        QVERIFY(window.selectedPaths().isEmpty()); QVERIFY(!current->property("locationLocked").toBool());
        window.close();
        const auto state = qpe::readSettings()["nativeWorkspace"].toObject()["states"].toArray()[1].toObject();
        QCOMPARE(state["startFolder"].toString(), qpe::DirectoryStore::normalized(path("A")));
        QCOMPARE(state["history"].toArray().size(), 1);
        qpe::saveJson(qpe::settingsPath(), before);
    }
    /** @brief 5000件の初期表示と再訪を計測し、処理中もイベント配送を確認する。 */
    void largeFolderResponsiveness() {
        qpe::BrowserWindow window;
        window.show();
        QElapsedTimer elapsed;
        elapsed.start();
        window.navigate(path("many"));
        const qint64 callMs = elapsed.elapsed();
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 15000);
        const qint64 firstMs = elapsed.elapsed();
        auto* files = window.findChild<QTreeView*>("files");
        QCOMPARE(files->model()->rowCount(), 5000);
        window.navigate(path("B"));
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 5000);
        elapsed.restart();
        window.navigate(path("many"));
        QTRY_VERIFY_WITH_TIMEOUT(window.ready(), 5000);
        qInfo() << "5000 files: navigate call ms" << callMs << "ready ms" << firstMs << "revisit ms" << elapsed.elapsed();
        const QString evidence = qEnvironmentVariable("QPE_NATIVE_EVIDENCE_DIR");
        if (!evidence.isEmpty()) {
            QVERIFY(QDir().mkpath(evidence));
            QVERIFY(window.grab().save(evidence + "/native-many.png"));
        }
        QVERIFY(callMs < 1000);  // OS速度の合否ではなく、GUIで全ディスク列挙しないための上限。
    }
    /** @brief 移動・戻る・タブ切替の完了件数と内部待ち時間を同条件で記録する。OS入力の測定値ではない。 */
    void navigationTimingEvidence() {
        QVERIFY(QDir().mkpath(path("timing1000")));
        for (int i = 0; i < 1000; ++i) QVERIFY(file(QString("timing1000/item_%1.txt").arg(i, 5, 10, QChar('0'))));
        qpe::BrowserWindow window; window.resize(1280, 900); window.show();
        window.navigate(path("A/子フォルダー/empty")); QTRY_VERIFY(window.ready());
        window.perform("startFolder", {data_.path()});
        auto* tabs = window.findChild<QTabBar*>("folderTabs"); QVERIFY(tabs);
        auto* pages = window.findChild<QStackedWidget*>(); QVERIFY(pages);
        QToolButton* back = nullptr; QToolButton* forward = nullptr;
        for (auto* button : window.findChildren<QToolButton*>()) {
            if (button->toolTip() == "Back") back = button;
            if (button->toolTip() == "Forward") forward = button;
        }
        QVERIFY(back); QVERIFY(forward);
        QJsonArray samples;
        const auto measure = [&](const QString& name, const std::function<void()>& action, int expected) {
            QTest::qWait(100); QElapsedTimer elapsed; elapsed.start(); action();
            const double handler = elapsed.nsecsElapsed() / 1000000.0;
            while (!window.ready() && elapsed.elapsed() < 15000) QTest::qWait(5);
            QApplication::processEvents();
            const double completed = elapsed.nsecsElapsed() / 1000000.0;
            QVERIFY2(window.ready(), qPrintable(name));
            auto* files = pages->currentWidget()->findChild<QTreeView*>("files"); QVERIFY(files);
            QCOMPARE(files->model()->rowCount(), expected);
            samples.append(QJsonObject{{"name", name}, {"handler_ms", handler}, {"ready_ms", completed}, {"rows", expected}});
        };
        measure("first_A_1000", [&] { window.navigate(path("timing1000")); }, 1000);
        measure("first_B_5000", [&] { window.navigate(path("many")); }, 5000);
        for (int i = 0; i < 3; ++i) {
            measure(QString("back_A_%1").arg(i), [&] { back->click(); }, 1000);
            measure(QString("forward_B_%1").arg(i), [&] { forward->click(); }, 5000);
        }
        measure("new_tab_A", [&] { window.addTab(path("timing1000")); }, 1000);
        for (int i = 0; i < 3; ++i) {
            measure(QString("tab_B_%1").arg(i), [&] { tabs->setCurrentIndex(0); }, 5000);
            measure(QString("tab_A_%1").arg(i), [&] { tabs->setCurrentIndex(1); }, 1000);
        }
        measure("empty_after_browsing", [&] { window.navigate(path("A/子フォルダー/empty")); }, 0);
        qInfo().noquote() << "QPE_NAVIGATION_TIMINGS" << QJsonDocument(samples).toJson(QJsonDocument::Compact);
    }
    /** @brief 新規タブ用キャッシュは完成値だけを借り、別世代・外部変更・隠し設定を分離する。 */
    void independentPrimedCache() {
        QVERIFY(QDir().mkpath(path("prime/complete"))); QVERIFY(QDir().mkpath(path("prime/partial")));
        const auto completePath = path("prime/complete"), partialPath = path("prime/partial");
        qpe::DirectoryStore source; source.activate({completePath, partialPath});
        auto generation = source.request(completePath);
        QVERIFY(source.deliver(completePath, generation, {{"stale.txt", false, 5, {}, 0}}, {}));
        const auto partialGeneration = source.request(partialPath);
        QVERIFY(source.deliver(partialPath, partialGeneration, {{"partial.txt", false, 2, {}, 0}}, {}, false));
        qpe::DirectoryStore target; target.primeCache(source);
        QVERIFY(target.snapshot(completePath)); QVERIFY(!target.snapshot(partialPath));
        QCOMPARE(target.snapshot(completePath)->entries[0].name, QString("stale.txt"));
        generation = source.request(completePath);
        QVERIFY(source.deliver(completePath, generation, {{"source-only.txt", false, 9, {}, 0}}, {}));
        QCOMPARE(target.snapshot(completePath)->entries[0].name, QString("stale.txt"));
        QVERIFY(file("prime/complete/current.txt")); target.activate({completePath});
        QTRY_VERIFY(target.snapshot(completePath) && target.snapshot(completePath)->entries.size() == 1
            && target.snapshot(completePath)->entries[0].name == "current.txt");
        QVERIFY_EXCEPTION_THROWN(target.primeCache(source), std::logic_error);
        qpe::DirectoryStore hidden; hidden.setShowHidden(true); hidden.primeCache(source); QVERIFY(!hidden.snapshot(completePath));
    }
    /** @brief 固定タブと場所ロックはUI操作でも移動/削除を防ぐ。 */
    void pinnedAndLockedTabs() {
        qpe::BrowserWindow window; window.navigate(path("A")); window.addTab(path("B")); window.show();
        auto* tabs = window.findChild<QTabBar*>("folderTabs");
        auto* stack = window.findChild<QStackedWidget*>(); QVERIFY(stack);
        stack->currentWidget()->setProperty("pinned", true);
        emit tabs->tabCloseRequested(1); QCOMPARE(tabs->count(), 2);
        stack->currentWidget()->setProperty("locationLocked", true);
        window.navigate(path("A")); QCOMPARE(tabs->count(), 3);
        tabs->setCurrentIndex(1); QCOMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B")));
        stack->currentWidget()->setProperty("pinned", false); emit tabs->tabCloseRequested(1); QCOMPARE(tabs->count(), 2);
    }
    /** @brief パス候補が入力対象の変更後に混入せず、フォーカスを維持する。 */
    void addressCompletion() {
        qpe::BrowserWindow window; window.navigate(path("A")); window.show(); window.activateWindow();
        auto* address = window.findChild<QLineEdit*>("address"); QVERIFY(address && address->completer());
        QCOMPARE(address->text(), QDir::toNativeSeparators(window.currentPath()));
        address->setFocus(); address->setText(QDir::toNativeSeparators(path("A/"))); emit address->textEdited(address->text());
        QTRY_VERIFY_WITH_TIMEOUT(address->completer()->model()->rowCount() > 0, 5000);
        QVERIFY(!address->completer()->model()->index(0, 0).data().toString().contains('/'));
        QVERIFY(address->hasFocus());
        address->completer()->popup()->hide();
        address->setText(QDir::toNativeSeparators(path("B"))); QTest::keyClick(address, Qt::Key_Return);
        QTRY_COMPARE(window.currentPath(), qpe::DirectoryStore::normalized(path("B")));
        QCOMPARE(address->text(), QDir::toNativeSeparators(window.currentPath()));
        address->setFocus();
        address->setText(path("B/no-matching-name")); emit address->textEdited(address->text());
        QTRY_COMPARE_WITH_TIMEOUT(address->completer()->model()->rowCount(), 0, 5000);
    }
    /** @brief DLL解除後にホストへ古い関数ポインターを残す独自型登録を検出する。 */
    void unloadSafeTransport() {
        qpe::FileJobs jobs;
        QSignalSpy done(&jobs, &qpe::FileJobs::finished);
        jobs.enqueue({"size", {path("A")}});
        QTRY_COMPARE_WITH_TIMEOUT(done.count(), 1, 10000);
        const auto result = qpe::fileResultFromJson(done.takeFirst().at(0).toJsonObject());
        QVERIFY(result.errors.isEmpty());
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
        QVERIFY(!QMetaType::fromName("qpe::FileResult").isValid());
        QVERIFY(!QMetaType::fromName("qpe::DirectoryEntries").isValid());
#else
        QCOMPARE(QMetaType::type("qpe::FileResult"), int(QMetaType::UnknownType));
        QCOMPARE(QMetaType::type("qpe::DirectoryEntries"), int(QMetaType::UnknownType));
#endif
        QTRY_VERIFY_WITH_TIMEOUT(qpe::FileJobs::releaseWorkers(), 10000);
        jobs.enqueue({"size", {path("B")}});
        QTRY_COMPARE_WITH_TIMEOUT(done.count(), 1, 10000);
    }
    /** @brief QApplicationの破棄前に専用ワーカーを回収する。 */
    void cleanupTestCase() {
        QTRY_VERIFY_WITH_TIMEOUT(qpe::DirectoryStore::releaseWorkers(), 10000);
        QTRY_VERIFY_WITH_TIMEOUT(qpe::FileJobs::releaseWorkers(), 10000);
        QTRY_VERIFY_WITH_TIMEOUT(qpe::nativeObjectsReleased(), 10000);
    }
};
QTEST_MAIN(MigrationTest)
#include "cpp_migration_test.moc"
