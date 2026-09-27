// 本番と同じQtウィジェットをoffscreenで検証する。Maya GUIの検証とは区別する。
#include "editor.h"
#include "modulescan.h"
#include <QApplication>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QTemporaryDir>
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

/** @brief importの行のトップレベル名の補完(modulescan.cpp)を、一時フォルダーで検証する。
 * @return すべて期待どおりならtrue。失敗した項目は標準エラーへ出す。
 */
bool moduleScanPasses() {
    QTemporaryDir directory;
    if (!directory.isValid()) return false;
    const QDir root(directory.path());
    auto touch=[&](const QString& name) { QFile file(root.filePath(name)); return file.open(QIODevice::WriteOnly); };
    touch("sample.py"); touch("_private.py"); touch("note.txt");
    root.mkdir("pkg"); root.mkdir("not-ident");
    const auto names=hedit::scanTopLevel({root.path(), root.filePath("missing")});
    if (!names.contains("sample") || !names.contains("pkg") || !names.contains("_private")
        || names.contains("not-ident") || names.contains("note") || names.contains("note.txt")) {
        qWarning() << "scanTopLevel" << names; return false;
    }
    QString prefix;
    if (!hedit::topLevelImportPrefix("import sam",&prefix) || prefix!="sam") { qWarning() << "import prefix" << prefix; return false; }
    if (!hedit::topLevelImportPrefix("x = 1\nfrom sa",&prefix) || prefix!="sa") { qWarning() << "from prefix" << prefix; return false; }
    if (!hedit::topLevelImportPrefix("import ",&prefix) || !prefix.isEmpty()) { qWarning() << "empty prefix" << prefix; return false; }
    // ドット付き・from x import y・importでない行はPython側の補完へ渡す。
    for (const char* source: {"import maya.cm","from sample import cr","print(x)","import os\nos.pa"})
        if (hedit::topLevelImportPrefix(source,nullptr)) { qWarning() << "handled" << source; return false; }
    auto items=[](const QByteArray& json) {
        QStringList result;
        for (const auto& value: QJsonDocument::fromJson(json).object().value("items").toArray()) result.append(value.toObject().value("name").toString());
        return result;
    };
    const QSet<QString> candidates{"sample","_private","pkg","Sample2"};
    if (items(hedit::completionItems(candidates,"",false))!=QStringList{"Sample2","pkg","sample"}
        || items(hedit::completionItems(candidates,"sa",false))!=QStringList{"sample"}
        || items(hedit::completionItems(candidates,"_",false))!=QStringList{"_private"}
        || !QJsonDocument::fromJson(hedit::completionItems(QSet<QString>(),"",true)).object().value("pending").toBool()) {
        qWarning() << "completionItems" << items(hedit::completionItems(candidates,"",false)); return false;
    }
    // 走査は別スレッドで行い、呼出し元を待たせない。再走査でファイルの追加・削除に追従する。
    hedit::ModuleScanner scanner(0);
    QElapsedTimer timer; timer.start();
    scanner.refresh({root.path()});
    if (timer.elapsed()>50) { qWarning() << "refresh blocked" << timer.elapsed(); return false; }
    if (!scanner.waitForFirst(2000) || !scanner.names().contains("sample")) { qWarning() << "first scan"; return false; }
    // 1回の走査を始めて終わるまで待ち、その結果で判定する(数回までやり直す)。
    auto eventually=[&](const QString& name, bool present) {
        for (int attempt=0;attempt<20;++attempt) {
            scanner.refresh({root.path()});
            for (int wait=0;wait<200;++wait) {
                bool pending=true; const auto current=scanner.names(&pending);
                if (!pending) { if (current.contains(name)==present) return true; break; }
                QThread::msleep(10);
            }
        }
        return false;
    };
    touch("newly_added.py");
    if (!eventually("newly_added",true)) { qWarning() << "added file not found"; return false; }
    QFile::remove(root.filePath("newly_added.py"));
    if (!eventually("newly_added",false)) { qWarning() << "removed file still listed"; return false; }
    scanner.stop();
    return true;
}

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
    // 初回履歴の整形は過去の断片だけに使う。空行を省き、空白だけの行は前後をつなぐ。
    if (hedit::compactHistory("one\r\n\noptimization\n \non\n\n\nnext\n")!="one\noptimization on\nnext\n"
        || !hedit::compactHistory("").isEmpty()) return 11;
    if (!moduleScanPasses()) return 12;
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
