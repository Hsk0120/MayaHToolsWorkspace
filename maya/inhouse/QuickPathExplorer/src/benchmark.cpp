/** @file benchmark.cpp
 * @brief 同じデータ件数・イベント待機条件によるC++側の計測。
 */
#include "explorer.h"
#include <QFile>
#include <QFileSystemModel>
#include <QColumnView>
#include <QLineEdit>
#include <QLabel>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QElapsedTimer>
#include <QApplication>
#include <QThread>
#include <QSet>
#include <QDir>
#include <functional>

/** @brief 条件成立までGUIイベントを処理する。
 * @param condition 完了条件。
 * @return 15秒以内に成立した場合true。
 * @note 1ms待機を含むため、微小差は分解できない。
 */
static bool waitFor(const std::function<bool()>& condition) {
    QElapsedTimer timer; timer.start();
    while (!condition()) {
        QApplication::processEvents();
        if (timer.elapsed() > 15000) return false;
        QThread::msleep(1);
    }
    QApplication::processEvents();
    return true;
}

int qpeBenchmark(QWidget* widget, const char* config, const char* output) {
    QFile input(QString::fromUtf8(config));
    if (!input.open(QIODevice::ReadOnly)) return 1;
    const auto settings = QJsonDocument::fromJson(input.readAll()).object();
    auto* model = widget->findChild<QFileSystemModel*>("fileModel");
    auto* view = widget->findChild<QColumnView*>("columns");
    auto* address = widget->findChild<QLineEdit*>("address");
    QSet<QString> loaded;
    // ローカル変数を参照する接続は関数終了前に必ず解除する。
    const auto connection = QObject::connect(model, &QFileSystemModel::directoryLoaded, widget, [&loaded](const QString& path) { loaded.insert(QDir::cleanPath(path)); });
    QJsonArray results; bool passed = true;
    for (const auto value : settings["cases"].toArray()) {
        const auto item = value.toObject();
        const auto path = QDir::cleanPath(item["path"].toString());
        const auto mode = item["mode"].toString();
        QElapsedTimer timer; timer.start();
        QModelIndex index;
        if (mode == "select") {
            index = model->index(path);
            view->setCurrentIndex(index);
            if (model->canFetchMore(index)) model->fetchMore(index);
        } else {
            address->setText(path);
            QMetaObject::invokeMethod(address, "returnPressed", Qt::DirectConnection);
            index = view->rootIndex();
        }
        const bool ok = waitFor([&] { return loaded.contains(path) && model->rowCount(index) == item["count"].toInt(); });
        const double ms = timer.nsecsElapsed() / 1e6;
        passed = passed && ok;
        results.append(QJsonObject{{"name", item["name"]}, {"ms", ms}, {"rows", model->rowCount(index)}, {"passed", ok}});
    }
    // 正常なファイル選択・フィルター・無効パスでの表示保持を検証する。
    const QString checkPath = settings["check_path"].toString();
    address->setText(checkPath); QMetaObject::invokeMethod(address, "returnPressed", Qt::DirectConnection);
    const bool checkLoaded = waitFor([&] { return loaded.contains(QDir::cleanPath(checkPath)); });
    auto* filter = widget->findChild<QLineEdit*>("filter"); filter->setText("*.ma");
    const bool filtered = waitFor([&] { return model->rowCount(view->rootIndex()) == 2; });
    const auto selected = model->index(checkPath + "/日本語 scene.ma"); view->setCurrentIndex(selected);
    QApplication::processEvents();
    const bool selectedOk = widget->findChild<QLabel*>("info")->text().contains("日本語 scene.ma");
    const auto oldRoot = view->rootIndex();
    address->setText(checkPath + "/missing"); QMetaObject::invokeMethod(address, "returnPressed", Qt::DirectConnection);
    const bool invalidOk = oldRoot == view->rootIndex();
    filter->clear(); address->setText(checkPath);
    const bool cleared = waitFor([&] { return model->rowCount(view->rootIndex()) == 3; });
    view->setCurrentIndex(model->index(checkPath + "/image.txt"));
    view->setCurrentIndex(selected); QApplication::processEvents();
    passed = passed && filtered && selectedOk && invalidOk && checkLoaded && cleared;
    widget->grab().save(QString::fromUtf8(output) + ".png");
    // 計測中のgrab/PNG圧縮は次のケースへ影響するため、証跡用の階層を最後に再表示する。
    for (const auto value : settings["cases"].toArray()) {
        const auto item = value.toObject(); const auto name = item["name"].toString();
        if (name == "deep_root") {
            address->setText(item["path"].toString()); QMetaObject::invokeMethod(address, "returnPressed", Qt::DirectConnection);
        } else if (name.startsWith("depth_")) {
            view->setCurrentIndex(model->index(item["path"].toString()));
        } else continue;
        QApplication::processEvents();
        if (name == "depth_03") { widget->grab().save(QString::fromUtf8(output) + ".columns.png"); break; }
    }
    QObject::disconnect(connection);
    QFile file(QString::fromUtf8(output));
    if (!file.open(QIODevice::WriteOnly)) return 1;
    file.write(QJsonDocument(QJsonObject{{"implementation", "cpp"}, {"qt", qVersion()}, {"passed", passed},
        {"filter_check", filtered}, {"unicode_selection_check", selectedOk}, {"invalid_path_check", invalidOk}, {"cases", results}}).toJson());
    return passed ? 0 : 1;
}
