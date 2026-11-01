/** @file native_main.cpp
 * @brief Python/Mayaを起動せず静的Qtで動く単体exe。
 */
#include "../browser/browser_window.h"
#include "../core/directory_store.h"
#include "../core/file_operations.h"
#include "../native_browser.h"
#include "../product.h"
#include <QApplication>
#include <QDir>
#include <QTimer>
#include <QThreadPool>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QElapsedTimer>
#include <QMessageBox>
#include <stdexcept>
#include <windows.h>
#include <shellapi.h>
#include <shobjidl.h>

/** @brief Qtのイベントループを所有し、検証時だけ自動終了する。
 * @param argc 引数数。
 * @param argv [開始パス] [--smoke 出力JSON]。
 * @return 正常終了0、検証タイムアウト2。
 */
int main(int argc, char** argv) {
#ifdef QPE_PRODUCT_BUILD
    SetCurrentProcessExplicitAppUserModelID(L"QuickPathExplorer");
#else
    SetCurrentProcessExplicitAppUserModelID(L"QuickPathExplorer.NativePreview");
#endif
    QApplication app(argc, argv);
    app.setApplicationName("QuickPathExplorer");
    app.setApplicationVersion(QPE_VERSION);
    app.setOrganizationName("QuickPathExplorer");
    QElapsedTimer elapsed;
    elapsed.start();
    int result = 0;
    try {
        qpe::BrowserWindow window;
        const auto args = app.arguments();
        const auto initial = args.size() > 1 && !args[1].startsWith("--") ? args[1] : QString();
        window.restoreSession(initial, initial.isEmpty());
        window.show();
        const int smoke = args.indexOf("--smoke");
        QTimer poll;
        if (smoke >= 0 && smoke + 1 < args.size()) {
            QObject::connect(&poll, &QTimer::timeout, &window, [&] {
                if (!window.ready() && elapsed.elapsed() < 15000) return;
                const bool ok = window.ready();
                QFile output(args[smoke + 1]);
                if (!output.open(QIODevice::WriteOnly)) { app.exit(3); return; }
                output.write(QJsonDocument(QJsonObject{{"passed", ok}, {"qt", qVersion()},
                    {"pythonRuntime", false}, {"staticQt", true}, {"path", window.currentPath()},
                    {"readyMilliseconds", double(elapsed.elapsed())}}).toJson());
                window.grab().save(args[smoke + 1] + ".png");
                app.exit(ok ? 0 : 2);
            });
            poll.start(50);
        }
        result = app.exec();
    } catch (const std::exception& error) {
        // 破損した設定や起動時I/Oの失敗をabortへ進めず、原本はそのまま残す。
        const auto message = QString::fromUtf8(error.what());
        const auto args = app.arguments(); const int smoke = args.indexOf("--smoke");
        if (smoke >= 0 && smoke + 1 < args.size()) {
            QFile output(args[smoke + 1]);
            if (output.open(QIODevice::WriteOnly)) output.write(QJsonDocument(QJsonObject{{"passed", false}, {"error", message}, {"phase", "startup"}}).toJson());
        } else QMessageBox::critical(nullptr, "QuickPathExplorer could not start",
            "QPE could not read its startup data. Existing settings have not been replaced.\n\n" + message);
        result = 1;
    }
    // GUIの破棄で失効させた列挙の終了を、exeのコード解放前に待つ。
    qpe::DirectoryStore::releaseWorkers(true);
    qpe::FileJobs::releaseWorkers(true);
    QThreadPool::globalInstance()->waitForDone();
    qpe::nativeObjectsReleased();
    return result;
}
