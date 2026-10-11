/** @file main.cpp
 * @brief Mayaを起動せずに動作するネイティブEXE入口。
 */
#include "explorer.h"
#include <QApplication>
#include <QTimer>
#include <QFile>
#include <QLineEdit>
#include <QDir>
/** @brief 単体画面、または指定された計測を開始する。
 * @param argc 引数の数。
 * @param argv --bench config output ready、または閲覧するフォルダー。
 * @return イベントループの終了コード。
 */
int main(int argc, char** argv) {
    QApplication app(argc, argv);
    auto* window = qpeCreate(nullptr); window->show();
    const auto args = app.arguments();
    // イベントループ開始後に測定し、Qtの遅延初期化を両言語で揃える。
    QTimer::singleShot(0, window, [&app, window, args] {
        if (args.size() == 5 && args[1] == "--bench") {
            QFile ready(args[4]); if (ready.open(QIODevice::WriteOnly)) ready.write("ready"); ready.close();
            app.exit(qpeBenchmark(window, args[2].toUtf8().constData(), args[3].toUtf8().constData()));
        } else {
            auto* address = window->findChild<QLineEdit*>("address");
            address->setText(args.size() > 1 ? args[1] : QDir::homePath());
            QMetaObject::invokeMethod(address, "returnPressed", Qt::DirectConnection);
        }
    });
    const int code = app.exec(); delete window; return code;
}
