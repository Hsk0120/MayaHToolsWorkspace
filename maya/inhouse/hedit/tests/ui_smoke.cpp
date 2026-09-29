// 本番と同じQtウィジェットをoffscreenで検証する。Maya GUIの検証とは区別する。
#include "core/history_text.h"
#include "core/module_scanner.h"
#include "core/session_data.h"
#include "core/text_search.h"
#include "editor/edit_commands.h"
#include "editor/editor.h"
#include "editor/ui_scale.h"
#include <QApplication>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QToolBar>
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
#include <QTextBlock>
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

/** @brief 検索・置換の一致と、置換文字列の展開(core/text_search.cpp)を検証する。
 * @return すべて期待どおりならtrue。失敗した項目は標準エラーへ出す。
 */
bool textSearchPasses() {
    hedit::SearchOptions options;
    options.text = "ab";
    auto result = hedit::findMatches("ab AB xab", options);
    if (!result.ok() || result.matches.size() != 3) { qWarning() << "case-insensitive" << result.matches.size(); return false; }
    options.matchCase = true;
    result = hedit::findMatches("ab AB xab", options);
    if (result.matches.size() != 2) { qWarning() << "match case" << result.matches.size(); return false; }
    options.wholeWord = true;
    result = hedit::findMatches("ab AB xab", options);
    if (result.matches.size() != 1 || !(result.matches[0] == hedit::TextMatch{0, 2})) { qWarning() << "whole word"; return false; }
    // 正規表現の置換: $1〜$99、$&、$$。存在しない番号は$番号のまま残す。
    hedit::SearchOptions regex;
    regex.text = "h(\\d+)";
    regex.regex = true;
    const QString replacement = "$1_$$_$&_$9";
    result = hedit::findMatches("h12 h3", regex, &replacement);
    if (result.replacements != QStringList{"12_$_h12_$9", "3_$_h3_$9"}) { qWarning() << "regex replace" << result.replacements; return false; }
    // 通常の検索では$をそのまま使う。
    options = hedit::SearchOptions();
    options.text = "a";
    result = hedit::findMatches("aa", options, &replacement);
    if (result.replacements != QStringList{replacement, replacement}) { qWarning() << "literal replace"; return false; }
    // 不正な正規表現・長さ0の一致は失敗として返す。
    regex.text = "(";
    if (hedit::findMatches("x", regex).ok()) { qWarning() << "invalid regex accepted"; return false; }
    regex.text = "x*";
    if (hedit::findMatches("abc", regex).ok()) { qWarning() << "zero-length accepted"; return false; }
    return true;
}

/** @brief tabs.jsonとの変換(core/session_data.cpp)と、履歴の種類の判定を検証する。
 * @return すべて期待どおりならtrue。
 */
bool sessionDataPasses() {
    hedit::SessionData data;
    data.activeTab = 1;
    data.folders = QStringList{"C:/scripts"};
    data.explorerVisible = true;
    hedit::TabState python;
    python.text = QString::fromUtf8("print('あ')\n");
    python.modified = true;
    python.position = 3;
    python.anchor = 1;
    hedit::TabState mel;
    mel.text = "ls;";
    mel.path = "C:/scripts/a.mel";
    mel.language = "mel";
    data.tabs = {python, mel};
    hedit::SessionData loaded;
    if (!hedit::sessionFromJson(hedit::sessionToJson(data), &loaded)) { qWarning() << "session round trip"; return false; }
    const bool same = loaded.activeTab == 1 && loaded.folders == data.folders && loaded.explorerVisible
        && loaded.tabs.size() == 2 && loaded.tabs[0].text == python.text && loaded.tabs[0].modified
        && loaded.tabs[0].position == 3 && loaded.tabs[0].anchor == 1 && loaded.tabs[1].language == "mel"
        && loaded.tabs[1].path == mel.path;
    if (!same) { qWarning() << "session values differ"; return false; }
    // 壊れたファイル・タブが無いファイル・版が違うファイル・必須の型が違うファイルは読まない。
    for (const char* broken : {"{", "{\"version\":1,\"tabs\":[]}", "{\"version\":2,\"tabs\":[{}]}",
                               "{\"version\":1,\"tabs\":[{\"text\":1,\"path\":\"\",\"modified\":false}]}"}) {
        if (hedit::sessionFromJson(broken, &loaded)) { qWarning() << "accepted broken session" << broken; return false; }
    }
    if (hedit::classifyHistoryLine("// Warning: x") != hedit::OutputKind::Warning
        || hedit::classifyHistoryLine("# Error: x") != hedit::OutputKind::Error
        || hedit::classifyHistoryLine("# Result: 1") != hedit::OutputKind::Result
        || hedit::classifyHistoryLine("print") != hedit::OutputKind::Normal) {
        qWarning() << "classifyHistoryLine"; return false;
    }
    return true;
}

/** @brief 行編集(editor/edit_commands.cpp)をQPlainTextEditで検証する。
 * @return すべて期待どおりならtrue。
 */
bool editCommandsPasses() {
    QPlainTextEdit edit;
    auto place = [&](int line, int column) {
        auto cursor = edit.textCursor();
        cursor.setPosition(edit.document()->findBlockByNumber(line).position() + column);
        edit.setTextCursor(cursor);
    };
    auto check = [&](const char* name, const QString& expected) {
        if (edit.toPlainText() == expected) return true;
        qWarning() << name << edit.toPlainText();
        return false;
    };
    edit.setPlainText("a\n    b\nc");
    place(1, 5);
    hedit::applyLineCommand(&edit, hedit::EditCommand::ToggleComment, "#");
    if (!check("comment", "a\n    # b\nc") || edit.textCursor().positionInBlock() != 7) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::ToggleComment, "#");
    if (!check("uncomment", "a\n    b\nc")) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::MoveUp, "#");
    if (!check("move up", "    b\na\nc") || edit.textCursor().blockNumber() != 0) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::CopyDown, "#");
    if (!check("copy down", "    b\n    b\na\nc") || edit.textCursor().blockNumber() != 1) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::Outdent, "#");
    if (!check("outdent", "    b\nb\na\nc")) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::DeleteLines, "#");
    if (!check("delete", "    b\na\nc")) return false;
    place(2, 0);
    hedit::applyLineCommand(&edit, hedit::EditCommand::MoveDown, "#");
    if (!check("move down at end", "    b\na\nc")) return false;
    hedit::applyLineCommand(&edit, hedit::EditCommand::ToggleComment, "//");
    if (!check("mel comment", "    b\na\n// c")) return false;
    // キーと操作の対応。選択の有無でCtrl+CとTabの意味が変わる。
    QKeyEvent ctrlC(QEvent::KeyPress, Qt::Key_C, Qt::ControlModifier);
    QKeyEvent tab(QEvent::KeyPress, Qt::Key_Tab, Qt::NoModifier);
    QKeyEvent altUp(QEvent::KeyPress, Qt::Key_Up, Qt::AltModifier);
    if (hedit::editCommandForKey(&ctrlC, false) != hedit::EditCommand::CopyLine
        || hedit::editCommandForKey(&ctrlC, true) != hedit::EditCommand::None
        || hedit::editCommandForKey(&tab, true) != hedit::EditCommand::Indent
        || hedit::editCommandForKey(&tab, false) != hedit::EditCommand::None
        || hedit::editCommandForKey(&altUp, false) != hedit::EditCommand::MoveUp) {
        qWarning() << "editCommandForKey"; return false;
    }
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
    if (!textSearchPasses()) return 14;
    if (!sessionDataPasses()) return 15;
    if (!editCommandsPasses()) return 16;
    // 4K等のMayaの拡大率(Interface Scaling)を、文字・アイコンの固定寸法に掛ける。
    {
        hedit::setUiScale(2.0);
        hedit::EditorServices services;
        services.runPython=[](const QString&) { return QString(); };
        services.refreshCompletion=[] { return QByteArray("{}"); };
        auto large=hedit::createEditor(nullptr,services);
        large->show(); QApplication::processEvents();
        auto bar=large->findChild<QToolBar*>("scriptToolbar");
        auto code=large->findChild<QPlainTextEdit*>("codeEditor");
        const bool ok=hedit::scaled(20)==40 && bar && bar->iconSize()==QSize(40,40) && code && code->font().pixelSize()==28;
        if (!ok) qWarning() << "ui scale" << (bar ? bar->iconSize() : QSize()) << (code ? code->font().pixelSize() : -1);
        delete large;
        hedit::setUiScale(1.0);
        if (!ok) return 13;
    }
    QFile file(QString::fromLocal8Bit(argv[1])); if (!file.open(QIODevice::ReadOnly)) return 3;
    QByteArray config = file.readAll();
    bool outputSent=false;
    // Mayaの代わりに、決まった値を返す偽の関数を渡す。
    hedit::EditorServices services;
    services.runPython = [](const QString& code) { return "executed: " + code; };
    services.refreshCompletion = [config] { return config; };
    services.takeOutput = [&outputSent] {
        if (outputSent) return QList<hedit::OutputMessage>();
        outputSent=true;
        return QList<hedit::OutputMessage>{{"result_marker\n",hedit::OutputKind::Result},{"history_marker\n",hedit::OutputKind::History},{"normal_marker\n",hedit::OutputKind::Normal}};
    };
    services.complete = [](const QString&) {
        return QByteArray("{\"items\":[{\"name\":\"createNode\",\"detail\":\"UI fixture\"}]}");
    };
    auto window = hedit::createEditor(nullptr, services);
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
