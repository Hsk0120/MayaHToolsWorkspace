/** @file native_test.cpp
 * @brief Mayaを起動せず、同じQt ABIでC++一覧の表示契約と破棄を検証する。
 */
#include "native_browser.h"
#include <QApplication>
#include <QDateTime>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocale>
#include <QSortFilterProxyModel>
#include <QStandardItemModel>
#include <QStyledItemDelegate>
#include <QTemporaryDir>
#include <QThread>
#include <QTreeView>
#include <stdexcept>

/** @brief Release構成でも無効にしない検証。
 * @param condition 合格条件。 @param message 失敗箇所。
 */
void check(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

/** @brief 件数・検索・数値順序・非同期中の即時破棄を確認する。
 * @param argc 引数数。 @param argv 出力JSONパス。 @return 合否コード。
 */
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    QApplication app(argc, argv);
    QJsonObject result;
    try {
        QTemporaryDir fixture(QFileInfo(argv[1]).absolutePath() + "/native-fixture-XXXXXX");
        check(fixture.isValid(), "temporary fixture");
        QFile file(fixture.path() + "/native.txt");
        check(file.open(QIODevice::WriteOnly), "fixture file");
        file.write("test"); file.close();
        auto view = new QTreeView;
        auto model = new QStandardItemModel(view);
        model->setHorizontalHeaderLabels({"Name", "Size", "Extension", "Date modified"});
        auto proxy = qobject_cast<QSortFilterProxyModel*>(qpe::createNative("proxy", view));
        proxy->setSourceModel(model);
        proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
        view->setModel(proxy);
        view->setItemDelegate(qobject_cast<QStyledItemDelegate*>(qpe::createNative("delegate", view)));
        view->setProperty("qpeRowHeight", 24);
        view->setUniformRowHeights(true);
        auto iconController = qpe::createNative("icons", view);
        QElapsedTimer clock; clock.start();
        for (int i = 0; i < 5000; ++i) {
            auto name = new QStandardItem(QString("file_%1.txt").arg(i, 5, 10, QChar('0')));
            name->setData(file.fileName(), Qt::UserRole + 1);
            name->setData(false, Qt::UserRole + 2);
            auto size = new QStandardItem;
            size->setData(5000 - i, Qt::DisplayRole);
            auto date = new QStandardItem;
            date->setData(QDateTime::fromMSecsSinceEpoch(i * 1000), Qt::DisplayRole);
            model->appendRow({name, size, new QStandardItem(".txt"), date});
        }
        proxy->sort(1);
        check(proxy->index(0, 1).data(Qt::EditRole).toInt() == 1, "numeric sort");
        check(proxy->index(4999, 1).data(Qt::EditRole).toInt() == 5000, "numeric tail");
        check(proxy->index(0, 1).data().toString() == QLocale::system().formattedDataSize(1), "size units");
        proxy->setFilterFixedString("FILE_000");
        check(proxy->rowCount() == 100, "case insensitive search");
        proxy->setFilterFixedString("");
        check(proxy->rowCount() == 5000, "clear search");
        view->resize(800, 500); view->show(); app.processEvents();
        result["create_sort_show_5000_ms"] = double(clock.elapsed());
        check(!qpe::nativeObjectsReleased(), "live view blocks unload");
        QElapsedTimer icons; icons.start();
        while (proxy->index(0, 0).data(Qt::DecorationRole).value<QIcon>().isNull() && icons.elapsed() < 30000) {
            app.processEvents(); QThread::msleep(5);
        }
        result["requested"] = iconController->property("requested").toInt();
        result["completed"] = iconController->property("completed").toInt();
        result["applied"] = iconController->property("applied").toInt();
        result["imageValid"] = iconController->property("lastImageValid").toBool();
        result["firstVisibleRow"] = view->indexAt(QPoint(2, 2)).row();
        check(!proxy->index(0, 0).data(Qt::DecorationRole).value<QIcon>().isNull(), "visible shell icon");
        // 索引失効後の古いワーカー結果が新しい行へ書き込まないことと破棄安全性。
        model->clear();
        delete view;
        while (!qpe::nativeObjectsReleased() && icons.elapsed() < 30000) {
            app.processEvents(); QThread::msleep(5);
        }
        check(qpe::nativeObjectsReleased(), "workers drained after deleting view");
        result["status"] = "passed";
        result["checks"] = "5000 rows, numeric sort, units, case insensitive search, async icon, clear/delete, unload guard";
    } catch (const std::exception& error) {
        result["status"] = "failed"; result["error"] = error.what();
    }
    QFile output(argv[1]); output.open(QIODevice::WriteOnly); output.write(QJsonDocument(result).toJson());
    return result["status"] == "passed" ? 0 : 1;
}
