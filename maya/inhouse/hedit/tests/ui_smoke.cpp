// 本番と同じQtウィジェットをoffscreenで検証する。Maya GUIの検証とは区別する。
#include "editor.h"
#include <QApplication>
#include <QCompleter>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPlainTextEdit>
#include <QAbstractItemView>
#include <QAction>
#include <QTabWidget>
#include <QTimer>
#include <QDebug>
#include <QKeyEvent>
#include <QFontDatabase>
#include <QThread>
#ifdef _WIN32
#include <windows.h>
#endif

/** @brief MayaなしでQt画面の補完・表示・実行通知を検証する。
 * @param argc 引数数。3を要求する。
 * @param argv 実行ファイル名、設定JSON、画像保存先。
 * @return 成功0、機能別の失敗番号またはタイムアウト番号。
 */
int main(int argc, char** argv) {
#ifdef _WIN32
    // テストの障害は終了コードで監視し、ユーザーの画面にWERを残さない。
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
    QApplication app(argc, argv);
    // offscreenプラットフォームはWindowsのフォント登録を自動参照しない。
    QFontDatabase::addApplicationFont(qEnvironmentVariable("WINDIR") + "/Fonts/segoeui.ttf");
    QFontDatabase::addApplicationFont(qEnvironmentVariable("WINDIR") + "/Fonts/consola.ttf");
    if (argc != 3) return 2;
    QFile file(QString::fromLocal8Bit(argv[1])); if (!file.open(QIODevice::ReadOnly)) return 3;
    QByteArray config = file.readAll();
    bool outputSent=false;
    auto window = hedit::createEditor(nullptr, [](const QString& code) { return "executed: " + code; }, [config] { return config; }, [&outputSent] {
        if (outputSent) return QList<hedit::OutputMessage>();
        outputSent=true;
        return QList<hedit::OutputMessage>{{"result_marker\n",hedit::OutputKind::Result},{"history_marker\n",hedit::OutputKind::History},{"normal_marker\n",hedit::OutputKind::Normal}};
    }, [](const QString&) {
        return QByteArray("{\"items\":[{\"name\":\"createNode\",\"detail\":\"UI fixture\"}]}");
    });
    window->show();
    auto code = window->findChild<QPlainTextEdit*>("codeEditor");
    if (!code) return 4;
    code->setPlainText("import maya.cmds as cmds\n\ncmds.cre");
    auto cursor = code->textCursor(); cursor.movePosition(QTextCursor::End); code->setTextCursor(cursor); code->setFocus();
    QString imagePath = QString::fromLocal8Bit(argv[2]);
    auto poll = new QTimer(window); poll->setInterval(200);
    int updates = 0;
    QObject::connect(poll, &QTimer::timeout, window, [=, &app, &updates] {
        // offscreenではOSのアクティブ化が発生しない。実GUI相当の入力先を明示する。
        QApplication::setActiveWindow(window);
        code->setFocus(Qt::OtherFocusReason);
        QKeyEvent request(QEvent::KeyPress, Qt::Key_Space, Qt::ControlModifier);
        QApplication::sendEvent(code, &request);
        auto completer = code->findChild<QCompleter*>();
        if (!completer || !completer->popup()->isVisible() || completer->completionCount() == 0) return;
        if (++updates < 5) {
            completer->popup()->hide();
            code->setPlainText(updates % 2 ? "import maya.cmds as cmds\ncmds.create" : "import maya.cmds as cmds\ncmds.cre");
            code->moveCursor(QTextCursor::End);
            return;
        }
        poll->stop();
        auto output=window->findChild<QPlainTextEdit*>("output");
        for (const auto& pair: QList<QPair<QString,QString>>{{"result_marker","#b5cea8"},{"history_marker","#a0a0a0"},{"normal_marker","#d4d4d4"}}) {
            int position=output->toPlainText().indexOf(pair.first); if (position<0) { app.exit(9); return; }
            auto cursor=output->textCursor(); cursor.setPosition(position); cursor.movePosition(QTextCursor::Right,QTextCursor::KeepAnchor);
            if (cursor.charFormat().foreground().color().name()!=pair.second) { app.exit(10); return; }
        }
        window->grab().save(imagePath);
        completer->popup()->grab().save(imagePath + ".completion.png");
        bool found = false;
        for (int row=0; row<completer->completionCount(); ++row) {
            if (completer->completionModel()->index(row, 0).data().toString() == "createNode") found = true;
        }
        if (!found) { app.exit(5); return; }
        QMetaObject::invokeMethod(completer, "activated", Q_ARG(QString, QString("createNode")));
        if (!code->toPlainText().endsWith("cmds.createNode")) { app.exit(6); return; }
        for (auto action : window->findChildren<QAction*>()) if (action->text() == "Run all") action->trigger();
        if (!window->findChild<QPlainTextEdit*>("output")->toPlainText().contains("executed:")) { app.exit(7); return; }
        qInfo() << "UI smoke: five completion updates, insertion, execution callback and screenshot passed";
        app.exit(0);
    });
    poll->start();
    QTimer::singleShot(20000, &app, [&app, code] { qWarning() << "Completion timeout; focus:" << code->hasFocus(); app.exit(8); });
    int result = app.exec();
    delete window;
    return result;
}
