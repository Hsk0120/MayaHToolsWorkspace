// 本番と同じQtウィジェットをoffscreenで検証する。Maya GUIの検証とは区別する。
#include "core/code_outline.h"
#include "core/completion_engine.h"
#include "core/fuzzy_match.h"
#include "core/line_diff.h"
#include "core/signature_help.h"
#include "core/docstrings.h"
#include "core/history_text.h"
#include "core/python_declarations.h"
#include "core/script_file.h"
#include "core/script_lexer.h"
#include "core/module_scanner.h"
#include "core/session_data.h"
#include "editor/session_store.h"
#include "editor/editor_preferences.h"
#include "core/json_file.h"
#include <QSettings>
#include "core/text_search.h"
#include "editor/edit_commands.h"
#include "editor/editor.h"
#include "editor/code_editor.h"
#include "editor/code_navigation.h"
#include "editor/diff_dialog.h"
#include "editor/hover_popup.h"
#include "editor/marker_scroll_bar.h"
#include "editor/outline_panel.h"
#include "editor/output_panel.h"
#include "editor/quick_pick.h"
#include <QListWidget>
#include <QLineEdit>
#include <QScrollBar>
#include <QTextDocument>
#include <QTreeWidget>
#include "editor/ui_scale.h"
#include <QApplication>
#include <algorithm>
#include <functional>
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
#include <QHelpEvent>
#include <QFrame>
#include <QFontDatabase>
#include <QThread>
#include <QTextBlock>
#include <QClipboard>
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
    // importできない名前(識別子でない)は出さない。拡張モジュール(.pyd)は、最初の点より前の名前で出す。
    touch("my-tool.py"); touch("ext.cp311-win_amd64.pyd"); touch("plain.pyd"); touch("bad-name.pyd");
    root.mkdir("pkg"); root.mkdir("not-ident");
    const auto names=hedit::scanTopLevel({root.path(), root.filePath("missing")});
    if (!names.contains("sample") || !names.contains("pkg") || !names.contains("_private")
        || names.contains("not-ident") || names.contains("note") || names.contains("note.txt")
        || names.contains("my-tool") || !names.contains("ext") || !names.contains("plain") || names.contains("bad-name")
        || names.contains("ext.cp311-win_amd64") || names.size() != 5) {
        qWarning() << "scanTopLevel" << names; return false;
    }
    QString prefix;
    if (!hedit::topLevelImportPrefix("import sam",&prefix) || prefix!="sam") { qWarning() << "import prefix" << prefix; return false; }
    if (!hedit::topLevelImportPrefix("x = 1\nfrom sa",&prefix) || prefix!="sa") { qWarning() << "from prefix" << prefix; return false; }
    if (!hedit::topLevelImportPrefix("import ",&prefix) || !prefix.isEmpty()) { qWarning() << "empty prefix" << prefix; return false; }
    // ドット付き・from x import y・importでない行はPython側の補完へ渡す。
    for (const char* source: {"import maya.cm","from sample import cr","print(x)","import os\nos.pa"})
        if (hedit::topLevelImportPrefix(source,nullptr)) { qWarning() << "handled" << source; return false; }
    auto items=[](const hedit::CompletionResult& result) {
        QStringList names;
        for (const auto& item: result.items) names.append(item.name);
        return names;
    };
    const QSet<QString> candidates{"sample","_private","pkg","Sample2"};
    // 大文字小文字を区別しない名前の順。入力があれば、一致の度合いの順(大文字小文字まで同じ前方一致が先)。
    if (items(hedit::completionItems(candidates,"",false))!=QStringList{"pkg","sample","Sample2"}
        || items(hedit::completionItems(candidates,"sa",false))!=QStringList{"sample","Sample2"}
        || items(hedit::completionItems(candidates,"spl",false))!=QStringList{"sample","Sample2"}
        || !items(hedit::completionItems(candidates,"amp",false)).isEmpty()
        || items(hedit::completionItems(candidates,"_",false))!=QStringList{"_private"}
        || !hedit::completionItems(QSet<QString>(),"",true).pending) {
        qWarning() << "completionItems" << items(hedit::completionItems(candidates,"",false)); return false;
    }
    // あいまい一致: 1文字目は名前の先頭か単語の頭(_の後・小文字の後の大文字)。前方一致が上に並ぶ。
    if (hedit::fuzzyScore(u"pcube", u"polyCube") < 0 || hedit::fuzzyScore(u"ube", u"polyCube") >= 0
        || hedit::fuzzyScore(u"gat", u"getAttr") < 0 || hedit::fuzzyScore(u"cn", u"createNode") < 0
        || hedit::fuzzyScore(u"jn", u"joint_name") < 0 || hedit::fuzzyScore(u"", u"anything") != 0
        || hedit::fuzzyScore(u"ls", u"ls") <= hedit::fuzzyScore(u"ls", u"listRelatives")
        || hedit::fuzzyScore(u"Poly", u"PolyCube") <= hedit::fuzzyScore(u"Poly", u"polyCube")
        || hedit::fuzzyScore(u"toolong", u"tool") >= 0
        || hedit::fuzzyScore(u"ls", u"listSets") <= hedit::fuzzyScore(u"ls", u"dR_lockSelTGL")) {
        qWarning() << "fuzzyScore"; return false;
    }
    // 250件を超える候補は、度合い(ここでは全て同じ)と名前の順の先頭250件だけ(先頭だけを並べ替えても同じ)。
    QSet<QString> many;
    for (int i = 0; i < 1000; ++i) many.insert(QString("m%1").arg((i * 7919) % 1000, 4, 10, QChar('0')));
    QStringList sortedMany(many.begin(), many.end());
    std::sort(sortedMany.begin(), sortedMany.end());
    if (items(hedit::completionItems(many, "m", false)) != sortedMany.mid(0, 250)) {
        qWarning() << "completionItems top 250"; return false;
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
    // 選択範囲内で検索: 範囲に収まる一致だけを数える。
    options = hedit::SearchOptions();
    options.text = "ab";
    options.rangeStart = 3;
    options.rangeEnd = 9;
    result = hedit::findMatches("ab AB xab", options);
    if (result.matches.size() != 2 || !(result.matches[0] == hedit::TextMatch{3, 2})) { qWarning() << "range" << result.matches.size(); return false; }
    // 範囲の末尾をまたぐ一致・範囲の後ろの一致は数えない。範囲の外の文字も、行頭・後読みの判定には使う。
    options.rangeStart = 2;
    options.rangeEnd = 8;
    result = hedit::findMatches("ab AB xab ab", options);
    if (result.matches.size() != 1 || !(result.matches[0] == hedit::TextMatch{3, 2})) { qWarning() << "range end" << result.matches.size(); return false; }
    regex = hedit::SearchOptions();
    regex.regex = true;
    regex.text = "(?<=x)ab|^cd";
    regex.rangeStart = 8;
    regex.rangeEnd = 12;
    result = hedit::findMatches("ab xab\nxab\ncd", regex);
    if (result.matches.size() != 1 || !(result.matches[0] == hedit::TextMatch{8, 2})) { qWarning() << "range lookbehind" << result.matches.size(); return false; }
    regex.rangeStart = 11;
    regex.rangeEnd = 13;
    result = hedit::findMatches("ab xab\nxab\ncd", regex);
    if (result.matches.size() != 1 || !(result.matches[0] == hedit::TextMatch{11, 2})) { qWarning() << "range line start" << result.matches.size(); return false; }
    // 大文字小文字を保つ置換(AB): 一致した文字列の形に合わせる。
    options = hedit::SearchOptions();
    options.text = "cmds";
    options.preserveCase = true;
    const QString lower = "hlib";
    result = hedit::findMatches("cmds CMDS Cmds", options, &lower);
    if (result.replacements != QStringList{"hlib", "HLIB", "Hlib"}) { qWarning() << "preserve case" << result.replacements; return false; }
    if (hedit::preserveCase("x", "123") != "x") { qWarning() << "preserve case without letters"; return false; }
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
    python.id = hedit::newTabId();
    python.text = QString::fromUtf8("print('あ')\n");
    python.modified = true;
    python.position = 3;
    python.anchor = 1;
    hedit::TabState mel;
    mel.id = hedit::newTabId();
    mel.text = "ls;";
    mel.path = "C:/scripts/a.mel";
    mel.language = "mel";
    data.tabs = {python, mel};
    // version 2: tabs.jsonには本文を入れない(本文は tabs/<id>.txt)。
    const QByteArray json = hedit::sessionToJson(data);
    hedit::SessionData loaded;
    if (json.contains("print") || !hedit::sessionFromJson(json, &loaded)) { qWarning() << "session round trip" << json; return false; }
    const bool same = loaded.activeTab == 1 && loaded.folders == data.folders && loaded.explorerVisible
        && loaded.tabs.size() == 2 && loaded.tabs[0].id == python.id && !loaded.tabs[0].textLoaded && loaded.tabs[0].modified
        && loaded.tabs[0].position == 3 && loaded.tabs[0].anchor == 1 && loaded.tabs[1].language == "mel"
        && loaded.tabs[1].path == mel.path;
    if (!same) { qWarning() << "session values differ"; return false; }
    // 0.2.xの version 1(本文をtabs.jsonに含む形)も読める。識別子はその場で付ける。
    const QByteArray legacy = "{\"version\":1,\"tabs\":[{\"text\":\"x = 1\",\"path\":\"\",\"modified\":true}]}";
    if (!hedit::sessionFromJson(legacy, &loaded) || loaded.tabs.size() != 1 || loaded.tabs[0].text != "x = 1"
        || !loaded.tabs[0].textLoaded || !hedit::isValidTabId(loaded.tabs[0].id)) {
        qWarning() << "legacy session"; return false;
    }
    // 壊れたファイル・タブが無いファイル・版が違うファイル・必須の型が違うファイル・不正な識別子は読まない。
    for (const char* broken : {"{", "{\"version\":2,\"tabs\":[]}", "{\"version\":3,\"tabs\":[{}]}",
                               "{\"version\":1,\"tabs\":[{\"text\":1,\"path\":\"\",\"modified\":false}]}",
                               "{\"version\":2,\"tabs\":[{\"id\":\"../x\",\"path\":\"\",\"modified\":false}]}"}) {
        if (hedit::sessionFromJson(broken, &loaded)) { qWarning() << "accepted broken session" << broken; return false; }
    }
    // SessionStore: 本文は変わったタブだけ書き、閉じたタブの本文のファイルは消す。
    {
        QTemporaryDir directory;
        const QString path = QDir(directory.path()).filePath("tabs.json");
        hedit::SessionStore store(path);
        hedit::SessionData opened;
        if (store.open(&opened) != hedit::SessionStore::OpenResult::NoFile) { qWarning() << "store open"; return false; }
        QString error;
        if (!store.save(data, &error)) { qWarning() << "store save" << error; return false; }
        const QString melText = store.textPath(mel.id);
        QFile::remove(melText);  // 2回目の保存で本文を書かないタブは、ファイルが作り直されないことで確かめる。
        hedit::SessionData unchanged = data;
        unchanged.tabs[1].textLoaded = false;
        unchanged.tabs.removeFirst();  // 1つ目のタブを閉じた。
        if (!store.save(unchanged, &error) || QFile::exists(melText) || QFile::exists(store.textPath(python.id))) {
            qWarning() << "store incremental save"; return false;
        }
        hedit::SessionStore other(path);
        if (other.open(&opened) != hedit::SessionStore::OpenResult::Locked) { qWarning() << "store lock"; return false; }
    }
    if (hedit::classifyHistoryLine("// Warning: x") != hedit::OutputKind::Warning
        || hedit::classifyHistoryLine("# Error: x") != hedit::OutputKind::Error
        || hedit::classifyHistoryLine("# Result: 1") != hedit::OutputKind::Result
        || hedit::classifyHistoryLine("print") != hedit::OutputKind::Normal) {
        qWarning() << "classifyHistoryLine"; return false;
    }
    // reporterが見つからないMayaでの代わりの取り込み: 通知の本文を整える。
    // Script Editorのreporterと同じ形(output_format_smoke.pyでMayaの実物と突き合わせた形)。
    if (hedit::formatCommandOutput("x", hedit::OutputKind::Warning) != "// Warning: x\n"
        || hedit::formatCommandOutput("bad\n", hedit::OutputKind::Error) != "// Error: bad\n"
        || hedit::formatCommandOutput("printed\n", hedit::OutputKind::Normal) != "printed\n"
        || hedit::formatCommandOutput("a\nsecond\n\nlast\n", hedit::OutputKind::Warning) != "// Warning: a\n// second\n// \n// last\n"
        || hedit::formatCommandOutput("info\nsecond\n\nlast\n", hedit::OutputKind::Info) != "// info\n// second\n// \n// last\n"
        || hedit::formatCommandOutput("about", hedit::OutputKind::Result) != "// Result: about\n"
        || hedit::formatCommandOutput("ValueError: file <maya console> line 1: bad", hedit::OutputKind::Error)
               != "# Error: ValueError: file <maya console> line 1: bad\n"
        || hedit::formatCommandOutput("file: C:/t.mel line 32: ModuleNotFoundError: file C:/a.py line 14: No module",
                                      hedit::OutputKind::Error)
               != "# Error: file: C:/t.mel line 32: ModuleNotFoundError: file C:/a.py line 14: No module\n"
        || hedit::formatCommandOutput("a\nsecond\n\nlast\n", hedit::OutputKind::Warning, true) != "// Warning: a\nsecond\n\nlast\n // \n"
        || hedit::formatCommandOutput("bad\nsecond", hedit::OutputKind::Error, true) != "// Error: bad\nsecond // \n"
        || hedit::formatCommandOutput("2022", hedit::OutputKind::Result, true) != "// Result: 2022 // \n"
        || hedit::formatCommandOutput("ValueError: file <maya console> line 1: x", hedit::OutputKind::Error, true)
               != "# Error: ValueError: file <maya console> line 1: x # \n"
        || hedit::formatCommandOutput("line 1: mel", hedit::OutputKind::Warning) != "// Warning: line 1: mel\n"
        || hedit::formatCommandOutput("file: C:/a.mel line 12: bad", hedit::OutputKind::Error)
               != "// Error: file: C:/a.mel line 12: bad\n") {
        qWarning() << "formatCommandOutput"; return false;
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

/** @brief 字句解析(core/script_lexer.cpp)を検証する。行をまたぐ文字列・コメントの状態も確かめる。
 * @return すべて期待どおりならtrue。
 */
bool lexerPasses() {
    auto types = [](const QVector<hedit::Token>& tokens) {
        QList<int> result;
        for (const auto& token : tokens) result.append(int(token.type));
        return result;
    };
    int state = 0;
    // 文字列の中の # はコメントではない。
    auto tokens = hedit::tokenizeLine("x = '#' # note", hedit::ScriptLanguage::Python, 0, &state);
    if (types(tokens) != QList<int>{int(hedit::TokenType::Name), int(hedit::TokenType::Operator),
                                    int(hedit::TokenType::String), int(hedit::TokenType::Comment)} || state != 0) {
        qWarning() << "python line" << types(tokens); return false;
    }
    // 三重引用符の文字列は次の行へ続き、閉じた後の名前は名前として読む。
    hedit::tokenizeLine("doc = r\"\"\"first", hedit::ScriptLanguage::Python, 0, &state);
    if (state != hedit::kPythonRawTripleDouble) { qWarning() << "triple open" << state; return false; }
    tokens = hedit::tokenizeLine("end\"\"\" + value", hedit::ScriptLanguage::Python, state, &state);
    if (state != 0 || tokens.size() != 3 || tokens[0].type != hedit::TokenType::String || tokens[2].type != hedit::TokenType::Name) {
        qWarning() << "triple close" << state << types(tokens); return false;
    }
    // == と = は別の記号。
    tokens = hedit::tokenizeLine("a==b", hedit::ScriptLanguage::Python, 0, &state);
    if (tokens.size() != 3 || tokens[1].length != 2) { qWarning() << "operator"; return false; }
    // MEL: $変数、ブロックコメントの継続、予約語。
    tokens = hedit::tokenizeLine("string $name = \"a\"; /* start", hedit::ScriptLanguage::Mel, 0, &state);
    if (tokens[1].type != hedit::TokenType::Variable || state != hedit::kMelBlockComment
        || !hedit::isKeyword("string", hedit::ScriptLanguage::Mel) || hedit::isKeyword("string", hedit::ScriptLanguage::Python)) {
        qWarning() << "mel" << types(tokens) << state; return false;
    }
    tokens = hedit::tokenizeLine("end */ ls;", hedit::ScriptLanguage::Mel, state, &state);
    if (state != 0 || tokens[0].type != hedit::TokenType::Comment || tokens[1].type != hedit::TokenType::Name) {
        qWarning() << "mel close" << types(tokens); return false;
    }
    // 字句の位置と長さを「種類:開始:長さ」の並びにする。
    auto spans = [](const QString& line, int start, int* end) {
        QStringList result;
        for (const auto& token : hedit::tokenizeLine(line, hedit::ScriptLanguage::Python, start, end))
            result.append(QString("%1:%2:%3").arg(int(token.type)).arg(token.start).arg(token.length));
        return result.join(' ');
    };
    const int S = int(hedit::TokenType::String);
    const int N = int(hedit::TokenType::Name);
    const int O = int(hedit::TokenType::Operator);
    const int C = int(hedit::TokenType::Comment);
    auto expect = [](const QStringList& parts) { return parts.join(' '); };
    auto span = [](int type, int start, int length) { return QString("%1:%2:%3").arg(type).arg(start).arg(length); };
    // 生文字列でも、\ の直後の引用符では閉じない(Pythonのtokenizeで確かめた位置と同じ)。\ は値に残る。
    const QList<QPair<QString, QString>> raw{
        {"x = r\"\\\"\"", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 5)})},
        {"s = r'\\'' + 'a'", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 5), span(O, 10, 1), span(S, 12, 3)})},
        {"p = r\"\\\\\" # c", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 5), span(C, 10, 3)})},
        {"q = rb'\\'x' + y", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 7), span(O, 12, 1), span(N, 14, 1)})},
        {"d = r\"\"\"a\\\"\"\"\" + z", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 10), span(O, 15, 1), span(N, 17, 1)})},
        {"u = R\"\\\"\" + Rb\"x\\\"y\"", expect({span(N, 0, 1), span(O, 2, 1), span(S, 4, 5), span(O, 10, 1), span(S, 12, 8)})},
    };
    for (const auto& probe : raw) {
        int end = -1;
        if (spans(probe.first, 0, &end) != probe.second || end != 0) {
            qWarning() << "raw string" << probe.first << spans(probe.first, 0, &end); return false;
        }
    }
    // 生文字列の三重引用符も、\' では閉じずに次の行へ続く。
    int end = 0;
    spans("t = r'''start\\'''", 0, &end);
    if (end != hedit::kPythonRawTripleSingle || spans("end''' + w", end, &end) != expect({span(S, 0, 6), span(O, 7, 1), span(N, 9, 1)})
        || end != 0) {
        qWarning() << "raw triple" << end; return false;
    }
    if (hedit::stringLiteralValue("r\"\\\"\"") != "\\\"") { qWarning() << "raw value"; return false; }
    // 2・3文字の記号は長いものを優先する(先頭の文字で分岐する実装を、以前の一覧と同じ結果か確かめる)。
    const QList<QPair<QString, int>> operators{
        {"**=", 3}, {"//=", 3}, {">>=", 3}, {"<<=", 3}, {"...", 3}, {"==", 2}, {"!=", 2}, {"<=", 2}, {">=", 2},
        {"->", 2}, {":=", 2}, {"+=", 2}, {"-=", 2}, {"*=", 2}, {"/=", 2}, {"%=", 2}, {"&=", 2}, {"|=", 2},
        {"^=", 2}, {"@=", 2}, {"**", 2}, {"//", 2}, {"<<", 2}, {">>", 2}, {"&&", 2}, {"||", 2}, {"++", 2},
        {"--", 2}, {"..", 1}, {"<>", 1}, {"=>", 1}, {"~", 1}, {"-", 1}, {"*", 1}, {">", 1}, {"!", 1},
    };
    for (const auto& probe : operators) {
        const auto found = hedit::tokenizeLine(probe.first + "x", hedit::ScriptLanguage::Python, 0, nullptr);
        if (found.isEmpty() || found[0].type != hedit::TokenType::Operator || found[0].length != probe.second) {
            qWarning() << "operator length" << probe.first << (found.isEmpty() ? -1 : found[0].length); return false;
        }
    }
    // 予約語・定数の判定(行の一部をコピーしない版も同じ結果)。
    const QString line = "if True: return selfish";
    if (!hedit::isKeyword(QStringView(line).mid(0, 2), hedit::ScriptLanguage::Python)
        || !hedit::isConstant(QStringView(line).mid(3, 4), hedit::ScriptLanguage::Python)
        || !hedit::isConstant(QStringView(line).mid(16, 4), hedit::ScriptLanguage::Python)
        || hedit::isConstant(QStringView(line).mid(16, 7), hedit::ScriptLanguage::Python)
        || hedit::isKeyword(QStringView(), hedit::ScriptLanguage::Python) || hedit::isKeyword("If", hedit::ScriptLanguage::Python)
        || !hedit::isConstant("on", hedit::ScriptLanguage::Mel) || hedit::isKeyword("def", hedit::ScriptLanguage::Mel)) {
        qWarning() << "keywords"; return false;
    }
    // 文字列の接頭辞は大文字小文字を問わない。接頭辞にならない組合せ(bu)は名前として読む。
    if (spans("Rb'x' + fR\"y\" + bu'z'", 0, &end) != expect({span(S, 0, 5), span(O, 6, 1), span(S, 8, 5), span(O, 14, 1),
                                                            span(N, 16, 2), span(S, 18, 3)})) {
        qWarning() << "prefixes" << spans("Rb'x' + fR\"y\" + bu'z'", 0, &end); return false;
    }
    return true;
}

/** @brief 宣言の抽出(core/python_declarations.cpp)を検証する。Pythonのastで読んでいたときと同じ結果になるか。
 * @return すべて期待どおりならtrue。
 */
bool declarationsPasses() {
    const QString source =
        "import os, maya.cmds as cmds\n"
        "from . import nodes\n"
        "from .api import (Joint as J,\n"
        "    Mesh)\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from hlib.nodes import Node\n"
        "value = other = 1; flag: bool = True\n"
        "annotated: int\n"
        "a.b = 2\n"
        "x, y = 1, 2\n"
        "total += 1\n"
        "@decorator\n"
        "def create(name, /, *args, key=lambda a, b: a, **kwargs) -> dict:\n"
        "    inner = 1\n"
        "    def nested(): pass\n"
        "async def fetch(url,\n"
        "                *, timeout=3): pass\n"
        "class Example(Base, metaclass=Meta):\n"
        "    r\"\"\"docstring with def fake(): and # not comment\"\"\"\n"
        "    attribute = 1\n"
        "    def method(self): pass\n"
        "    class Inner: pass\n"
        "for item in items:\n"
        "    hidden = 1\n"
        "text = \"\"\"\n"
        "def not_a_function(): pass\n"
        "\"\"\"\n";
    const auto result = hedit::extractPythonDeclarations(source, "package.module");
    const auto& symbols = result.symbols;
    const QStringList expected{"Example", "J", "Mesh", "Node", "TYPE_CHECKING", "annotated", "cmds", "create", "fetch",
                               "flag", "nodes", "os", "other", "text", "value"};
    if (symbols.keys() != expected || !result.complete) { qWarning() << "declaration names" << symbols.keys(); return false; }
    if (symbols["create"].detail != "create(name, *args, key, **kwargs)" || symbols["fetch"].detail != "fetch(url, timeout)") {
        qWarning() << "detail" << symbols["create"].detail << symbols["fetch"].detail; return false;
    }
    if (symbols["cmds"].target != "maya.cmds" || symbols["os"].target != "os" || symbols["nodes"].target != "package.nodes"
        || symbols["J"].fromModule != "package.api" || symbols["J"].fromName != "Joint" || symbols["Node"].fromModule != "hlib.nodes") {
        qWarning() << "imports" << symbols["cmds"].target << symbols["nodes"].target << symbols["J"].fromModule; return false;
    }
    const auto members = symbols["Example"].members;
    if (!members || members->keys() != QStringList{"Inner", "attribute", "method"} || symbols["Example"].detail != "class Example") {
        qWarning() << "class members" << (members ? members->keys() : QStringList()); return false;
    }
    // 構文エラーがあっても、読める部分の宣言は取り出す。閉じていない括弧は「書きかけ」として知らせる。
    const auto broken = hedit::extractPythonDeclarations("import sample\ninvalid (\nvalue = 1\n");
    if (!broken.symbols.contains("sample") || broken.complete) { qWarning() << "broken source"; return false; }
    return true;
}

/** @brief 補完エンジン(core/completion_engine.cpp)を、Pythonの代わりの偽の情報で検証する。
 * @param config mayapyが書き出した、組み込みの名前と予約語のJSON(tests/maya_smoke.py)。
 * @return すべて期待どおりならtrue。
 */
bool completionEnginePasses(const QByteArray& config) {
    QTemporaryDir directory;
    const QDir root(directory.path());
    auto write = [&](const QString& name, const QByteArray& text) {
        QDir().mkpath(QFileInfo(root.filePath(name)).absolutePath());
        QFile file(root.filePath(name));
        return file.open(QIODevice::WriteOnly) && file.write(text) == text.size();
    };
    write("sample.py", "raise RuntimeError('must not execute')\n\ndef create_node(name, **kwargs):\n    pass\n\n"
                       "class Example:\n    def get_value(self):\n        pass\n");
    write("package/__init__.py", "from . import nodes\n");
    write("package/nodes/__init__.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .joint import Joint\n");
    write("package/nodes/joint.py", "class Joint:\n    def get_matrix(self): pass\n");
    write("docsample.py", "\"\"\"Sample module.\"\"\"\ndef make(name):\n    \"\"\"Make a thing.\"\"\"\n\n"
                          "class Thing:\n    \"\"\"A thing.\"\"\"\n    def run(self):\n        \"\"\"Run it.\"\"\"\n");

    hedit::ModuleSource source;
    source.searchPaths = [&] { return QStringList{root.path()}; };
    source.loadedModule = [](const QString& name, hedit::LoadedModule* module) {
        if (name != "maya.cmds") return false;
        module->members.insert("ls", hedit::Symbol());
        module->members.insert("createNode", hedit::Symbol());
        return true;
    };
    // ソースの無い名前(maya.cmds・builtins)の説明は、Pythonに問い合わせる代わりにここで返す。
    source.describe = [](const QString& module, const QStringList& path, QString* signature, QString* doc) {
        if (module == "maya.cmds" && path == QStringList{"ls"}) {
            *signature = "def ls(...)";
            *doc = "List objects.";
            return true;
        }
        if (module == "maya.cmds" && path.isEmpty()) {
            *signature = "module maya.cmds";
            *doc = "Maya commands.";
            return true;
        }
        if (module == "builtins" && path == QStringList{"len"}) {
            *signature = "def len(obj, /)";
            *doc = "Return the number of items.";
            return true;
        }
        return false;
    };
    hedit::CompletionEngine engine(source);
    hedit::CompletionEnvironment environment;
    const auto data = QJsonDocument::fromJson(config).object();
    for (const auto& value : data.value("builtins").toArray()) environment.builtins.append(value.toString());
    for (const auto& value : data.value("keywords").toArray()) environment.keywords.append(value.toString());
    engine.setEnvironment(environment);

    auto names = [&](const QString& text) {
        QStringList result;
        for (const auto& item : engine.complete(text).items) result.append(item.name);
        return result;
    };
    const auto signature = engine.complete("import sample as s\ns.cre").items;
    if (signature.size() != 1 || signature[0].name != "create_node" || signature[0].detail != "create_node(name, **kwargs)") {
        qWarning() << "signature" << names("import sample as s\ns.cre"); return false;
    }
    if (names("import maya.cmds as cmds\ncmds.") != QStringList{"createNode", "ls"}
        || names("from sample import cre") != QStringList{"create_node"}
        || names("import sample\nsample.Example.get_") != QStringList{"get_value"}
        || names("from sample import Example as E\nE.get") != QStringList{"get_value"}
        || !names("import package\npackage.nodes.").contains("Joint")
        || names("import package as p\np.nodes.Joint.get_") != QStringList{"get_matrix"}
        || !names("def function(arg):\n    pass\nfun").contains("function")
        || names("import maya.m") != QStringList()
        || names("import maya.cmds as cmds\ncmds.cn") != QStringList{"createNode"}
        || names("import maya.cmds as cmds\ncmds.CREATE") != QStringList{"createNode"}) {
        qWarning() << "engine names" << names("import package\npackage.nodes.") << names("import package as p\np.nodes.Joint.get_");
        return false;
    }
    // 組み込みの名前と予約語の種類(Preferencesでの絞り込みに使う)。
    const auto keyword = engine.complete("ret").items;
    const auto builtin = engine.complete("pri").items;
    if (keyword.isEmpty() || keyword[0].kind != "keyword" || builtin.isEmpty() || builtin[0].name != "print" || builtin[0].kind != "builtin") {
        qWarning() << "kinds"; return false;
    }
    // ファイルが変わったら読み直す。書きかけのファイルは、前回の正しい結果を使い続ける。
    write("sample.py", "def changed_function():\n    pass\n");
    if (names("import sample\nsample.ch") != QStringList{"changed_function"}) { qWarning() << "cache refresh"; return false; }
    write("sample.py", "def broken_function(:\n    pass\n    # longer so that the size differs\n");
    if (names("import sample\nsample.ch") != QStringList{"changed_function"}) { qWarning() << "incomplete keeps cache" << names("import sample\nsample."); return false; }
    // 5,000行の書きかけの本文でも、C++で読むので短時間で終わる。
    QString large = "import sample\ninvalid (\n";
    for (int i = 0; i < 5000; ++i) large += "value_" + QString::number(i) + " = " + QString::number(i) + "\n";
    QElapsedTimer timer;
    timer.start();
    const auto largeNames = names(large + "sample.cre");
    const qint64 elapsed = timer.elapsed();
    if (largeNames != QStringList{"create_node"} && largeNames != QStringList()) { qWarning() << "large" << largeNames; return false; }
    qInfo() << "completion of a 5,000-line source took" << elapsed << "ms";
    if (elapsed > 200) { qWarning() << "large source too slow" << elapsed; return false; }
    // ホバーの説明: 未読込のファイル・from import・クラスのメソッド・本文の関数・読み込み済み・組み込み・モジュール。
    auto describe = [&](const QString& text) { return engine.describe(text, text.size()); };
    const QList<QPair<QString, hedit::HoverInfo>> hovers{
        {"import docsample\ndocsample.make", {"def make(name)", "Make a thing."}},
        {"from docsample import Thing\nThing", {"class Thing", "A thing."}},
        {"from docsample import Thing\nThing.run", {"def run(self)", "Run it."}},
        {"def local(a):\n    '''Local doc.'''\nlocal", {"def local(a)", "Local doc."}},
        {"import maya.cmds as cmds\ncmds.ls", {"def ls(...)", "List objects."}},
        {"import maya.cmds as cmds\ncmds", {"module maya.cmds", "Maya commands."}},
        {"import docsample\ndocsample", {"module docsample", "Sample module."}},
        {"len", {"def len(obj, /)", "Return the number of items."}},
    };
    for (const auto& hover : hovers) {
        const hedit::HoverInfo info = describe(hover.first);
        if (info.signature != hover.second.signature || info.doc != hover.second.doc) {
            qWarning() << "describe" << hover.first << info.signature << info.doc; return false;
        }
    }
    if (!describe("return").isEmpty() || !describe("value = 1\nvalue.unknown").isEmpty() || !describe("unknown_name").isEmpty()) {
        qWarning() << "describe empty" << describe("unknown_name").signature; return false;
    }
    // 変数の型の推論: 呼出しの代入・型ヒント・引数の型ヒント・関数の中。親クラスのメンバーも出す。
    const QString classes = "class A:\n    def run(self): pass\nclass B(A):\n    def walk(self): pass\n";
    const QList<QPair<QString, QStringList>> inferred{
        {classes + "obj = B()\nobj.", {"run", "walk"}},
        {classes + "obj: A = make()\nobj.", {"run"}},
        {classes + "obj: \"B\"\nobj.", {"run", "walk"}},
        {classes + "def f(o: B, n: int):\n    o.", {"run", "walk"}},
        {classes + "def g():\n    o = A(1, (2, 3))\n    o.", {"run"}},
        {"import docsample\nt = docsample.Thing()\nt.", {"run"}},
        {"from docsample import Thing\nt = Thing()\nt.", {"run"}},
    };
    for (const auto& probe : inferred) {
        const QStringList found = names(probe.first);
        for (const QString& expected : probe.second) {
            if (!found.contains(expected)) { qWarning() << "inferred" << probe.first << found; return false; }
        }
    }
    // 推論できない代入が後にあれば、古い型は使わない。呼出しの結果にさらに続く形も推論しない。
    if (!names(classes + "o = A()\no = 1\no.").isEmpty() || !names(classes + "o = A().run\no.").isEmpty()) {
        qWarning() << "stale inference" << names(classes + "o = A()\no = 1\no."); return false;
    }
    if (hedit::inferredTypeExpression("x = 1\nx: pkg.A\n", "x") != "pkg.A"
        || hedit::inferredTypeExpression("def f(a, x: 'pkg.B' = None):\n", "x") != "pkg.B"
        || hedit::inferredTypeExpression("x = make()  # comment\n", "x") != "make"
        || !hedit::inferredTypeExpression("x: list[A]\n", "x").isEmpty()) {
        qWarning() << "inferredTypeExpression"; return false;
    }
    // 比較(x == y)は代入ではないので、推論を止めない。x += 1 は推論できない代入なので止める。空の本文は推論しない。
    if (hedit::inferredTypeExpression("x = make()\nx == other\n", "x") != "make"
        || hedit::inferredTypeExpression("x = make()\n  x  ==  other", "x") != "make"
        || !hedit::inferredTypeExpression("x = make()\nx += 1\n", "x").isEmpty()
        || !hedit::inferredTypeExpression("x = make()\nx = 2", "x").isEmpty()
        || hedit::inferredTypeExpression("x = make()\nxx = 2\nself.x = 3\nfoo(x)\n", "x") != "make"
        || hedit::inferredTypeExpression("def f(\n    a,\n    x: Node,\n):\n", "x") != "Node"
        || hedit::inferredTypeExpression("x = A()\r\ny = 1\r\n", "x") != "A"
        || !hedit::inferredTypeExpression(QString(), "x").isEmpty() || !hedit::inferredTypeExpression("x: A", "1x").isEmpty()) {
        qWarning() << "inferredTypeExpression comparison" << hedit::inferredTypeExpression("x = make()\nx == other\n", "x");
        return false;
    }
    if (names(classes + "o = A()\no == 1\no.") != QStringList{"run"}) {
        qWarning() << "comparison keeps inference" << names(classes + "o = A()\no == 1\no."); return false;
    }
    // 名前だけの補完: 本文の宣言は、同じ名前の組み込みの名前より優先する(候補の種類が空になる)。
    {
        const auto shadowed = engine.complete("print = 1\nprin").items;
        if (shadowed.isEmpty() || shadowed[0].name != "print" || !shadowed[0].kind.isEmpty()) {
            qWarning() << "shadowed builtin" << (shadowed.isEmpty() ? QString() : shadowed[0].kind); return false;
        }
    }
    // 宣言の控え: 補完(カーソルの行より前)の控えをホバーが使っても、結果は控えが無い場合と同じ。
    {
        hedit::CompletionEngine fresh(source);
        fresh.setEnvironment(environment);
        const QList<QPair<QString, QString>> flows{
            {classes + "obj = B()\nobj.", classes + "obj = B()\nobj.walk"},
            {"def f():\n    ", "def f():\n    'Doc.'"},  // 最後の行が文字列: 前の行の関数のdocstringになる。
            {"x = (1,\n", "x = (1,\ny)"},
            {"import docsample\n", "import docsample\ndocsample.make"},
            {"value = 1 \\\n", "value = 1 \\\n+ make"},
        };
        for (const auto& flow : flows) {
            engine.complete(flow.first);
            engine.complete(flow.second);
            for (const int end : {int(flow.second.size()), 1, 5}) {
                const hedit::HoverInfo cached = engine.describe(flow.second, end);
                const hedit::HoverInfo uncached = fresh.describe(flow.second, end);
                fresh.clearCaches();
                if (cached.signature != uncached.signature || cached.doc != uncached.doc) {
                    qWarning() << "cached locals" << flow.second << end << cached.signature << uncached.signature;
                    return false;
                }
            }
        }
        if (engine.describe("def f():\n    'Doc.'", 5).doc != "Doc.") { qWarning() << "docstring on the last line"; return false; }
    }
    // Windowsでは、以前(QFileInfoで調べていた)と同じく、モジュールのファイル名の大文字小文字を区別しない。
#ifdef Q_OS_WIN
    if (!names("import DocSample\nDocSample.").contains("make")) { qWarning() << "case-insensitive module"; return false; }
#endif
    // フォルダーの一覧は控えるが、Refresh(clearCaches)の後は新しいファイルも見つかる。
    write("fresh_module.py", "def brand_new(): pass\n");
    engine.clearCaches();
    if (names("import fresh_module\nfresh_module.b") != QStringList{"brand_new"}) { qWarning() << "new module"; return false; }
    // ホバーも推論した型で説明を出す。
    const hedit::HoverInfo method = describe("import docsample\nt = docsample.Thing()\nt.run");
    if (method.signature != "def run(self)" || method.doc != "Run it.") {
        qWarning() << "describe inferred" << method.signature; return false;
    }
    // 定義の場所: 本文の中のクラス・推論した変数のメソッド・関数の引数と変数・ファイルの中・モジュール。
    {
        const QString text = classes + "def g(p):\n    o = B()\n    o.walk()\n    return p\n";
        auto at = [&](const QString& source, const QString& needle) {
            return engine.definition(source, source.indexOf(needle) + needle.size());
        };
        const auto classB = at(text, "o = B");
        const auto walk = at(text, "o.walk");
        const auto parameter = at(text, "return p");
        const auto variable = engine.definition(text, text.indexOf("o.walk") + 1);
        const QString methodText = "import docsample\nt = docsample.Thing()\nt.run";
        const auto method = engine.definition(methodText, methodText.size());
        const auto module = engine.definition("import docsample", 16);
        const auto noSource = engine.definition("import maya.cmds as cmds\ncmds.ls", 32);
        if (classB.line != 2 || !classB.path.isEmpty() || walk.line != 3 || walk.column != 8 || parameter.line != 4
            || parameter.column != 6 || variable.line != 5 || !method.path.endsWith("docsample.py") || method.line != 6
            || !module.path.endsWith("docsample.py") || module.line != 0 || noSource.found()) {
            qWarning() << "definition" << classB.line << walk.line << walk.column << parameter.line << variable.line
                       << method.path << method.line << module.line << noSource.line;
            return false;
        }
        // 補完の一覧のアイコンの種類。
        QStringList categories;
        for (const auto& item : engine.complete("import docsample\ndocsample.").items) categories.append(item.name + ":" + item.category);
        if (categories != QStringList{"make:function", "Thing:class"}) {
            qWarning() << "categories" << categories; return false;
        }
    }
    // 読み込み済みのモジュール: 公開名とファイルの宣言を重ねた結果は控えるが、どちらかが変われば作り直す。
    {
        write("loadedpkg/__init__.py", "def declared_one(a): pass\n");
        hedit::LoadedModule loaded;
        loaded.members.insert("live_one", hedit::Symbol());
        loaded.file = root.filePath("loadedpkg/__init__.py");
        hedit::ModuleSource live = source;
        live.loadedModule = [&loaded](const QString& name, hedit::LoadedModule* module) {
            if (name != "loadedpkg") return false;
            *module = loaded;  // hedit.bridgeと同じく、変わっていなければ同じ表(暗黙の共有)を渡す。
            return true;
        };
        hedit::CompletionEngine liveEngine(live);
        auto liveNames = [&liveEngine] {
            QStringList result;
            for (const auto& item : liveEngine.complete("import loadedpkg\nloadedpkg.").items) result.append(item.name + ":" + item.detail);
            return result;
        };
        const QStringList first{"declared_one:declared_one(a)", "live_one:"};
        if (liveNames() != first || liveNames() != first) { qWarning() << "merged module" << liveNames(); return false; }
        loaded.members.insert("live_two", hedit::Symbol());
        if (liveNames() != QStringList{"declared_one:declared_one(a)", "live_one:", "live_two:"}) {
            qWarning() << "merged module members changed" << liveNames(); return false;
        }
        write("loadedpkg/__init__.py", "def declared_two(b, c): pass\n# the size differs from the first version\n");
        if (liveNames() != QStringList{"declared_two:declared_two(b, c)", "live_one:", "live_two:"}) {
            qWarning() << "merged module file changed" << liveNames(); return false;
        }
    }
    // 末尾の名前の判定(Pythonの正規表現 [A-Za-z_][\w.]*$ と同じ)。
    if (hedit::trailingDottedName("x = 1abc.de") != "abc.de" || hedit::trailingDottedName("cmds.") != "cmds."
        || hedit::trailingDottedName("f(") != "") {
        qWarning() << "trailing" << hedit::trailingDottedName("x = 1abc.de"); return false;
    }
    return true;
}

/** @brief 設定の保存(preferences.json)と、0.2.xのpreferences.iniからの移行を検証する。
 * @return すべて期待どおりならtrue。
 */
bool preferencesPasses() {
    QTemporaryDir directory;
    const QString json = QDir(directory.path()).filePath("preferences.json");
    {
        // 0.2.xのpreferences.iniがあれば、preferences.jsonが無いときに1回だけ移す。
        QSettings legacy(QDir(directory.path()).filePath("preferences.ini"), QSettings::IniFormat);
        legacy.setValue("spellCheck", false);
        legacy.setValue("fontPixels", 18);
        legacy.sync();
    }
    hedit::EditorPreferences first(json);
    if (first.option(hedit::option::kSpellCheck) || first.fontPixels() != 18 || !QFile::exists(json)) {
        qWarning() << "preferences migration"; return false;
    }
    // 別のMayaが別の項目を変えても、1項目ずつ書き換えるので互いの変更を消さない。
    hedit::EditorPreferences second(json);
    first.setOption(hedit::option::kWhitespace, true);
    second.setOption(hedit::option::kOutputWrap, true);
    QJsonObject saved;
    if (!hedit::readJsonFile(json, &saved) || !saved.value("whitespace").toBool() || !saved.value("outputWrap").toBool()
        || saved.value("spellCheck").toBool(true)) {
        qWarning() << "preferences merge" << saved; return false;
    }
    // 最近開いたファイル(新しい順・重複なし)と、メニューに無い表示の状態は、作り直しても残る。
    first.addRecentFile("C:/a.py");
    first.addRecentFile("C:/b.py");
    first.addRecentFile("C:/a.py");
    first.setFlag("outlineVisible", true);
    hedit::EditorPreferences reloaded(json);
    if (reloaded.recentFiles() != QStringList{"C:/a.py", "C:/b.py"} || !reloaded.flag("outlineVisible", false)
        || reloaded.flag("missing", true) != true || !reloaded.option(hedit::option::kAutoClosing)
        || !reloaded.option(hedit::option::kStickyScroll)) {
        qWarning() << "recent files" << reloaded.recentFiles(); return false;
    }
    // 初期値に戻すとheditの項目を消し、知らない項目は残す。
    hedit::updateJsonFile(json, "futureOption", 1);
    if (!first.resetToDefaults() || !hedit::readJsonFile(json, &saved) || saved.contains("whitespace")
        || !saved.contains("futureOption") || !first.option(hedit::option::kSpellCheck)) {
        qWarning() << "preferences reset" << saved; return false;
    }
    return true;
}

/** @brief 文字列リテラルの値・docstringの整形・宣言のdocstringと見出し(ホバー用)を検証する。
 * @return すべて期待どおりならtrue。
 */
bool docstringsPasses() {
    if (hedit::stringLiteralValue("'''a\\nb'''") != "a\nb" || hedit::stringLiteralValue("r\"a\\nb\"") != "a\\nb"
        || hedit::stringLiteralValue("\"\"\"unterminated") != "unterminated"
        || hedit::stringLiteralsValue({"'a'", "\"b\""}) != "ab") {
        qWarning() << "literal" << hedit::stringLiteralValue("'''a\\nb'''"); return false;
    }
    if (hedit::cleanDocstring("  First.\n\n    Args:\n        x: value.\n    ") != "First.\n\nArgs:\n    x: value.") {
        qWarning() << "cleandoc" << hedit::cleanDocstring("  First.\n\n    Args:\n        x: value.\n    "); return false;
    }
    const QString source =
        "\"\"\"Module doc.\"\"\"\n"
        "def make(name, size: int = 1, *args, **kwargs) -> str:\n"
        "    \"\"\"Make a thing.\n"
        "\n"
        "    Args:\n"
        "        name (str): The name.\n"
        "    \"\"\"\n"
        "    return name\n"
        "\n"
        "class Thing(Base):\n"
        "    '''A thing.'''\n"
        "    def run(self): 'Run it.'\n"
        "def plain(a, b=2): pass\n";
    const hedit::DeclarationResult result = hedit::extractPythonDeclarations(source);
    const hedit::Symbol make = result.symbols.value("make");
    const hedit::Symbol thing = result.symbols.value("Thing");
    const hedit::Symbol plain = result.symbols.value("plain");
    if (result.docstring != "Module doc."
        || make.signature != "def make(name, size: int = 1, *args, **kwargs) -> str"
        || make.doc != "Make a thing.\n\nArgs:\n    name (str): The name."
        || make.detail != "make(name, size, *args, **kwargs)"
        || thing.signature != "class Thing(Base)" || thing.doc != "A thing."
        || !thing.members || thing.members->value("run").doc != "Run it."
        || plain.signature != "def plain(a, b=2)" || !plain.doc.isEmpty()) {
        qWarning() << "declarations" << result.docstring << make.signature << make.doc << thing.signature << thing.doc
                   << plain.signature;
        return false;
    }
    // 改行がCRLFの本文: 行をまたぐdocstringの行の区切りは\nにする(タブは8桁の空白として字下げを除く)。
    const auto crlf = hedit::extractPythonDeclarations("def f():\r\n    \"\"\"A\r\n\tB\r\n    \"\"\"\r\n    return 1\r\nclass K: '''k\r\n  doc'''\r\n");
    if (crlf.symbols.value("f").doc != "A\nB" || crlf.symbols.value("K").doc != "k\ndoc" || !crlf.complete) {
        qWarning() << "crlf docstring" << crlf.symbols.value("f").doc << crlf.symbols.value("K").doc; return false;
    }
    // ホバーのHTML: 見出しの色分けとGoogle形式の見出し。
    const QString html = hedit::HoverPopup::toHtml({make.signature, make.doc}, "Consolas");
    if (!html.contains("#569cd6\">def</span>") || !html.contains("#dcdcaa\">make</span>") || !html.contains("<b>Args:</b>")
        || !html.contains(">name</span>")) {
        qWarning() << "hover html" << html; return false;
    }
    return true;
}

/** @brief ファイルの読み書き(core/script_file.cpp)を検証する。 @return すべて期待どおりならtrue。 */
bool scriptFilePasses() {
    if (hedit::formatForSave("a = 1  \n# c\t", true, true) != "a = 1\n# c\n" || hedit::formatForSave("x", false, false) != "x") {
        qWarning() << "formatForSave"; return false;
    }
    QTemporaryDir directory;
    const QString path = QDir(directory.path()).filePath("script.py");
    QString error;
    if (!hedit::writeScriptFile(path, QString::fromUtf8("print('日本語')\n"), &error)) { qWarning() << "write" << error; return false; }
    QString text;
    if (!hedit::readScriptFile(path, &text, &error) || text != QString::fromUtf8("print('日本語')\n")) { qWarning() << "read" << error; return false; }
    QFile latin(QDir(directory.path()).filePath("latin.py"));
    latin.open(QIODevice::WriteOnly);
    latin.write("caf\xe9\n");
    latin.close();
    if (hedit::readScriptFile(latin.fileName(), &text, &error) || error != "Only UTF-8 files are supported") { qWarning() << "latin" << error; return false; }
    // UTF-8の判定は、以前の方法(読んでUTF-8へ書き戻し、元と一致するか)と同じ結果になる。
    const QList<QByteArray> samples{
        "ascii", "\xc3\xa9", "\xe3\x81\x82", "\xf0\x9f\x98\x80", "\xef\xbf\xbe", "\xef\xbf\xbf", "\xef\xb7\x90",
        "\xf4\x8f\xbf\xbf", QByteArray("a\0b", 3), "\xef\xbb\xbf" "after", "x\xef\xbb\xbfy", "\xef\xbb\xbf\xef\xbb\xbfz",
        "\xc0\xaf", "\xe0\x80\xaf", "\xf0\x80\x80\xaf", "\xed\xa0\x80", "\xed\xbf\xbf", "\xf4\x90\x80\x80", "\xf8\x88\x80\x80\x80",
        "\x80", "\xbf", "\xc3", "\xe3\x81", "\xf0\x9f\x98", "\xc3\x28", "\xe3\x28\x81", "\xfe", "\xff", "ok\xe9", "\xed\x9f\xbf",
    };
    for (int i = 0; i < samples.size(); ++i) {
        QFile sample(QDir(directory.path()).filePath(QString("utf8_%1.py").arg(i)));
        sample.open(QIODevice::WriteOnly);
        sample.write(samples[i]);
        sample.close();
        QByteArray bytes = samples[i];
        if (bytes.startsWith("\xef\xbb\xbf")) bytes.remove(0, 3);
        const bool roundTrip = QString::fromUtf8(bytes).toUtf8() == bytes;
        QString read;
        if (hedit::readScriptFile(sample.fileName(), &read, &error) != roundTrip || (roundTrip && read != QString::fromUtf8(bytes))) {
            qWarning() << "utf8 check" << samples[i].toHex() << roundTrip; return false;
        }
    }
    return true;
}

/** @brief MayaなしでQt画面の補完・表示・実行通知を検証する。
 * @param argc 引数数。3を要求する。
 * @param argv 実行ファイル名、設定JSON、画像保存先。
 * @return 成功0、機能別の失敗番号またはタイムアウト番号。
 */
/** @brief 名前の付いた1つの検査。 */
struct TestCase {
    const char* name;            ///< 失敗したときに表示する名前。
    std::function<bool()> run;   ///< 検査の本体。期待どおりならtrue。
};

/** @brief 検査を順に実行し、1件ずつ PASS / FAIL を表示する(途中で失敗しても残りを続ける)。
 * @param cases 検査の一覧。
 * @return 失敗した件数。
 */
int runCases(const QList<TestCase>& cases) {
    int failed = 0;
    for (const TestCase& test : cases) {
        const bool ok = test.run();
        qInfo().noquote() << (ok ? "PASS" : "FAIL") << test.name;
        failed += ok ? 0 : 1;
    }
    qInfo().noquote() << QString("%1 of %2 checks passed").arg(cases.size() - failed).arg(cases.size());
    return failed;
}


/** @brief 本文の構成・折りたたみの範囲・関数の中の定義の位置(core/code_outline.cpp)。 @return 期待どおりならtrue。 */
bool codeOutlinePasses() {
    const QString text =
        "import maya.cmds as cmds\n"            // 0
        "LIMIT = 3\n"                           // 1
        "class Builder(object):\n"              // 2
        "    count = 1\n"                       // 3
        "    def build(self, radius=1.0):\n"    // 4
        "        \"\"\"Doc\n"                   // 5
        "def fake(): inside string\n"           // 6
        "        \"\"\"\n"                      // 7
        "        value = (1,\n"                 // 8
        "    2)\n"                              // 9
        "        return value\n"                // 10
        "\n"                                    // 11
        "async def run(job):\n"                 // 12
        "    for item in job:\n"                // 13
        "        print(item)\n";                // 14
    const QList<hedit::OutlineEntry> outline = hedit::buildOutline(text, hedit::ScriptLanguage::Python);
    QStringList summary;
    for (const auto& entry : outline) {
        summary.append(QString("%1:%2:%3-%4:%5").arg(entry.name, entry.kind).arg(entry.line).arg(entry.endLine).arg(entry.parent));
    }
    const QStringList expected{"LIMIT:variable:1-1:-1", "Builder:class:2-10:-1", "count:variable:3-3:1",
                               "build:method:4-10:1", "run:function:12-14:-1"};
    if (summary != expected) {
        qWarning() << "outline" << summary; return false;
    }
    if (hedit::findOutlinePath(outline, {"Builder", "build"}) != 3 || hedit::findOutlinePath(outline, {"build"}) != -1
        || hedit::enclosingOutlineEntry(outline, 9) != 3 || hedit::enclosingOutlineEntry(outline, 13) != 4
        || hedit::enclosingOutlineEntry(outline, 0) != -1) {
        qWarning() << "outline lookup"; return false;
    }
    // MELのproc。
    const auto mel = hedit::buildOutline("global proc string helper(string $a)\n{\n    return $a;\n}\nproc local() {}\n",
                                         hedit::ScriptLanguage::Mel);
    if (mel.size() != 2 || mel[0].name != "helper" || mel[0].endLine != 3 || mel[1].name != "local" || mel[1].line != 4) {
        qWarning() << "mel outline" << mel.size(); return false;
    }
    // 折りたたみ: インデントで決め、範囲の最後の空行は含めない。
    const auto ranges = hedit::indentationFoldRanges(QString("a:\n    b\n\n    c:\n        d\n\ne\n").split('\n'));
    if (ranges.size() != 2 || ranges[0].start != 0 || ranges[0].end != 4 || ranges[1].start != 3 || ranges[1].end != 4) {
        qWarning() << "fold ranges" << ranges.size(); return false;
    }
    // 以前の実装(閉じた順に集めて最後に並べ替える)と同じ結果になるか、タブ・空白だけの行・深い入れ子で確かめる。
    auto referenceFolds = [](const QStringList& lines) {
        QList<QPair<int, int>> result;
        QVector<QPair<int, int>> open;  // (インデント, 行)
        int lastNonBlank = -1;
        auto closeTo = [&](int indent) {
            while (!open.isEmpty() && open.last().first >= indent) {
                if (lastNonBlank > open.last().second) result.append({open.last().second, lastNonBlank});
                open.removeLast();
            }
        };
        for (int i = 0; i < lines.size(); ++i) {
            if (lines[i].trimmed().isEmpty()) continue;
            closeTo(hedit::lineIndentWidth(lines[i]));
            open.append({hedit::lineIndentWidth(lines[i]), i});
            lastNonBlank = i;
        }
        closeTo(-1);
        std::sort(result.begin(), result.end());
        return result;
    };
    const QStringList pieces{"a", "    b", "\tc", "  \t d", "", "   ", "\t", "        e", "\f f", "  \r", "x:"};
    for (int seed = 1; seed < 400; ++seed) {
        QStringList lines;
        unsigned value = unsigned(seed) * 2654435761u;
        for (int i = 0; i < 2 + seed % 23; ++i) {
            value = value * 1103515245u + 12345u;
            lines.append(pieces[(value >> 16) % pieces.size()]);
        }
        QList<QPair<int, int>> actual;
        for (const auto& range : hedit::indentationFoldRanges(lines)) actual.append({range.start, range.end});
        if (actual != referenceFolds(lines)) { qWarning() << "fold ranges reference" << lines; return false; }
    }
    // 構成: コメントだけの行・行末の\r・同じ名前の変数(最初だけ)・クラスの中の関数の後の代入。
    const auto crlf = hedit::buildOutline("X = 1  # c\r\n# only\r\nX = 2\r\nclass K:\r\n    def m(self):\r\n        pass\r\n    y = 1\r\n    y = 2\r\n", hedit::ScriptLanguage::Python);
    QStringList crlfSummary;
    for (const auto& entry : crlf) crlfSummary.append(QString("%1:%2:%3-%4:%5:%6").arg(entry.name, entry.kind).arg(entry.line).arg(entry.endLine).arg(entry.parent).arg(entry.detail));
    if (crlfSummary != QStringList{"X:variable:0-0:-1:", "K:class:3-7:-1:class K", "m:method:4-5:1:def m(self)", "y:variable:6-6:1:"}) {
        qWarning() << "outline crlf" << crlfSummary; return false;
    }
    // 関数の中の変数・引数・for の変数の定義の位置。
    const QString body = "def f(alpha, beta=2):\n    gamma = alpha\n    for delta, eps in []:\n        print(gamma, beta, delta)\n";
    int column = -1;
    if (hedit::localDefinitionLine(body, "gamma", 4, &column) != 1 || column != 4
        || hedit::localDefinitionLine(body, "beta", 4, &column) != 0 || column != 13
        || hedit::localDefinitionLine(body, "alpha", 1, &column) != 0 || column != 6
        || hedit::localDefinitionLine(body, "delta", 4) != 2 || hedit::localDefinitionLine(body, "eps", 4) != 2
        || hedit::localDefinitionLine(body, "pha", 4) != -1 || hedit::localDefinitionLine(body, "gamma", 2, &column) != 1
        || column != 4 || hedit::localDefinitionLine(body, "gamma", 1) != -1 || hedit::localDefinitionLine(body, "eps", 99) != 2
        || hedit::localDefinitionLine(body, "gamma", 0) != -1) {
        qWarning() << "local definition"; return false;
    }
    return true;
}

/** @brief 行単位の差分(core/line_diff.cpp)。 @return 期待どおりならtrue。 */
bool lineDiffPasses() {
    auto kinds = [](const QStringList& before, const QStringList& after) {
        QStringList result;
        for (const auto& change : hedit::diffLines(before, after)) {
            result.append(QString("%1@%2+%3/%4").arg(change.kind()).arg(change.afterStart).arg(change.afterCount).arg(change.beforeCount));
        }
        return result;
    };
    const QStringList base{"a", "b", "c", "d"};
    if (!kinds(base, base).isEmpty()
        || kinds(base, {"a", "b", "x", "c", "d"}) != QStringList{"added@2+1/0"}
        || kinds(base, {"a", "c", "d"}) != QStringList{"deleted@1+0/1"}
        || kinds(base, {"a", "B", "c", "D"}) != QStringList{"modified@1+1/1", "modified@3+1/1"}
        || kinds({}, {"new"}) != QStringList{"added@0+1/0"}) {
        qWarning() << "diff" << kinds(base, {"a", "B", "c", "D"}); return false;
    }
    // 以前の実装(最長共通部分列の表を後ろから作り、先頭からたどる)と同じまとまりになるか。
    // Myersのアルゴリズムでも、同じ行は対応させ、違う行では追加を先にする同じ規則で選ぶ。
    auto reference = [](const QStringList& before, const QStringList& after) {
        QStringList result;
        int prefix = 0;
        const int shorter = int(qMin(before.size(), after.size()));
        while (prefix < shorter && before[prefix] == after[prefix]) ++prefix;
        int suffix = 0;
        while (suffix < shorter - prefix && before[before.size() - 1 - suffix] == after[after.size() - 1 - suffix]) ++suffix;
        const int n = int(before.size()) - prefix - suffix;
        const int m = int(after.size()) - prefix - suffix;
        auto add = [&result](int bs, int bc, int as, int ac) { result.append(QString("%1+%2/%3+%4").arg(bs).arg(bc).arg(as).arg(ac)); };
        if (n == 0 && m == 0) return result;
        if (n == 0 || m == 0) { add(prefix, n, prefix, m); return result; }
        QVector<int> table((n + 1) * (m + 1), 0);
        auto at = [&table, m](int i, int j) -> int& { return table[i * (m + 1) + j]; };
        for (int i = n - 1; i >= 0; --i)
            for (int j = m - 1; j >= 0; --j)
                at(i, j) = before[prefix + i] == after[prefix + j] ? at(i + 1, j + 1) + 1 : qMax(at(i + 1, j), at(i, j + 1));
        int i = 0, j = 0, bs = -1, bc = 0, as = -1, ac = 0;
        auto flush = [&] { if (bc > 0 || ac > 0) add(bs, bc, as, ac); bs = -1; bc = 0; as = -1; ac = 0; };
        auto begin = [&] { if (bs < 0) { bs = prefix + i; as = prefix + j; } };
        while (i < n || j < m) {
            if (i < n && j < m && before[prefix + i] == after[prefix + j]) { flush(); ++i; ++j; }
            else if (j < m && (i >= n || at(i, j + 1) >= at(i + 1, j))) { begin(); ++ac; ++j; }
            else { begin(); ++bc; ++i; }
        }
        flush();
        return result;
    };
    auto actual = [](const QStringList& before, const QStringList& after) {
        QStringList result;
        for (const auto& c : hedit::diffLines(before, after))
            result.append(QString("%1+%2/%3+%4").arg(c.beforeStart).arg(c.beforeCount).arg(c.afterStart).arg(c.afterCount));
        return result;
    };
    // 少ない種類の行で作ると、同じ行が多く、対応の選び方が何通りもある並びになる。
    unsigned value = 12345u;
    auto next = [&value](unsigned range) { value = value * 1103515245u + 12345u; return (value >> 16) % range; };
    for (int round = 0; round < 3000; ++round) {
        const unsigned alphabet = 2 + round % 5;
        QStringList before;
        QStringList after;
        const int length = int(next(40));
        for (int i = 0; i < length; ++i) before.append(QString(QChar('a' + int(next(alphabet)))));
        after = before;
        const int edits = 1 + int(next(round < 1500 ? 4u : 40u));
        for (int e = 0; e < edits; ++e) {
            const int kind = int(next(3));
            const int position = after.isEmpty() ? 0 : int(next(unsigned(after.size())));
            if (kind == 0 || after.isEmpty()) after.insert(position, QString(QChar('a' + int(next(alphabet)))));
            else if (kind == 1) after.removeAt(position);
            else after[position] = QString(QChar('a' + int(next(alphabet))));
        }
        if (actual(before, after) != reference(before, after)) {
            qWarning() << "diff reference" << before << after << actual(before, after) << reference(before, after); return false;
        }
    }
    // 違う行が多い1,200行どうし: Myersで求める場合(3種類の行)と、予算を超えて表で求める場合(20種類の行)。
    for (const unsigned alphabet : {3u, 20u}) {
        QStringList before;
        QStringList after;
        for (int i = 0; i < 1200; ++i) {
            before.append(QString::number(next(alphabet)));
            after.append(QString::number(next(alphabet)));
        }
        if (actual(before, after) != reference(before, after)) {
            qWarning() << "diff reference large" << alphabet; return false;
        }
    }
    // 大きな本文(行数の積が250万を超える)でも、違う行が少なければ、両端の変更を別々のまとまりとして求める。
    QStringList large;
    for (int i = 0; i < 6000; ++i) large.append(QString("line %1").arg(i));
    QStringList largeEdited = large;
    largeEdited[2] = "changed";
    largeEdited.insert(5990, "added");
    if (kinds(large, largeEdited) != QStringList{"modified@2+1/1", "added@5990+1/0"}) {
        qWarning() << "large diff" << kinds(large, largeEdited); return false;
    }
    // 全く違う大きな本文は、以前と同じく残り全体を1つの変更にする(画面を止めない)。
    QStringList other;
    for (int i = 0; i < 6000; ++i) other.append(QString("other %1").arg(i));
    if (kinds(large, other) != QStringList{"modified@0+6000/6000"}) {
        qWarning() << "large different" << kinds(large, other); return false;
    }
    // 差分の画面の行: 削除は -、追加は +、前後の行は空白で始まる。
    const QStringList lines = hedit::DiffDialog::diffLinesText("a\nb\nc\n", "a\nB\nc\n", 1);
    if (lines != QStringList{"@@ -1 +1 @@", " a", "-b", "+B", " c"}) {
        qWarning() << "diff text" << lines; return false;
    }
    return true;
}

/** @brief 引数のヒントの解析(core/signature_help.cpp)。 @return 期待どおりならtrue。 */
bool signatureHelpPasses() {
    auto context = [](const QString& before) { return hedit::findCallContext(before); };
    const auto simple = context("builder.build(1, ");
    if (simple.nameEnd != 13 || simple.argumentIndex != 1 || !simple.attribute || !simple.keyword.isEmpty()) {
        qWarning() << "call simple" << simple.nameEnd << simple.argumentIndex; return false;
    }
    const auto keyword = context("cmds.joint(name='a,b', radius=");
    const auto nested = context("f(a, [1, 2, 3], g(x), ");
    const auto inList = context("f(a, [1, ");
    if (keyword.keyword != "radius" || keyword.argumentIndex != 1 || nested.argumentIndex != 3
        || nested.nameEnd != 1 || inList.nameEnd != 1 || inList.argumentIndex != 1
        || context("if (a").nameEnd != -1 || context("x = (1, ").nameEnd != -1 || context("f(a)").nameEnd != -1
        || context("make(\n    1,\n    ").argumentIndex != 1) {
        qWarning() << "call context" << keyword.keyword << nested.argumentIndex << inList.argumentIndex; return false;
    }
    hedit::SignatureParts parts = hedit::splitSignature("def build(self, radius: float = 1.0, *args, flag=(1, 2), **kw) -> list");
    if (!parts.valid || parts.head != "def build(" || parts.tail != ") -> list"
        || parts.parameters != QStringList{"self", "radius: float = 1.0", "*args", "flag=(1, 2)", "**kw"}) {
        qWarning() << "split" << parts.parameters; return false;
    }
    hedit::dropBoundParameter(&parts);
    if (parts.parameters.first() != "radius: float = 1.0" || hedit::splitSignature("module x").valid
        || !hedit::splitSignature("def f()").parameters.isEmpty()) {
        qWarning() << "drop self"; return false;
    }
    const QStringList p{"a", "b=1", "*args", "c=2", "**kw"};
    if (hedit::activeParameterIndex(p, 0, {}) != 0 || hedit::activeParameterIndex(p, 1, {}) != 1
        || hedit::activeParameterIndex(p, 5, {}) != 2 || hedit::activeParameterIndex(p, 0, "c") != 3
        || hedit::activeParameterIndex(p, 0, "zzz") != 4 || hedit::activeParameterIndex({"x", "/", "y"}, 1, {}) != 2
        || hedit::activeParameterIndex({"x"}, 3, {}) != -1) {
        qWarning() << "active parameter"; return false;
    }
    return true;
}

/** @brief 括弧の対応・同じ名前・選択範囲の拡大(editor/code_navigation.cpp)。 @return 期待どおりならtrue。 */
bool navigationPasses() {
    QTextDocument document;
    document.setPlainText("value = foo(bar.baz, [1, ')'])  # (x)\nprint(value, 'value')\n");
    const auto py = hedit::ScriptLanguage::Python;
    int first = -1;
    int second = -1;
    // foo( の ( は 29 文字目の ) と対応する(文字列の中の ')' とコメントの中は数えない)。
    if (!hedit::findMatchingBracket(&document, py, 11, &first, &second) || first != 11 || second != 29
        || !hedit::findMatchingBracket(&document, py, 30, &first, &second) || first != 29 || second != 11
        || hedit::findMatchingBracket(&document, py, 34, &first, &second)) {
        qWarning() << "brackets" << first << second; return false;
    }
    const QList<int> occurrences = hedit::nameOccurrences(&document, py, "value", 100);
    if (occurrences != QList<int>{0, 44}) {
        qWarning() << "occurrences" << occurrences; return false;
    }
    if (!hedit::isInsideStringOrComment(&document, py, 26) || hedit::isInsideStringOrComment(&document, py, 12)
        || !hedit::isInsideStringOrComment(&document, py, 36)) {
        qWarning() << "inside string"; return false;
    }
    // 選択範囲の拡大: baz → bar.baz → 括弧の中身 → 括弧を含む → 行の中身(この行は字下げが無いので行全体)。
    QList<QPair<int, int>> steps;
    int start = 17;
    int end = 17;
    for (int i = 0; i < 5; ++i) {
        int s = 0;
        int e = 0;
        if (!hedit::expandedSelection(&document, py, start, end, &s, &e)) {
            break;
        }
        steps.append({s, e});
        start = s;
        end = e;
    }
    const QList<QPair<int, int>> expected{{16, 19}, {12, 19}, {12, 29}, {11, 30}, {0, 37}};
    if (steps != expected) {
        qWarning() << "expand" << steps; return false;
    }
    return true;
}


/** @brief 出力欄は、表示の上限(5000行)を超える古い行を最初から入れず、末尾を正しく表示する。 @return 期待どおりならtrue。 */
bool outputPanelPasses() {
    QList<QList<hedit::OutputMessage>> batches;
    QString many;
    for (int i = 0; i < 6000; ++i) many += QString("flood %1\n").arg(i);
    batches.append({{"before\n", hedit::OutputKind::Normal}});
    batches.append({{"warn\n", hedit::OutputKind::Warning}, {many, hedit::OutputKind::Error}});
    batches.append({{"after\n", hedit::OutputKind::Normal}});
    int next = 0;
    hedit::OutputPanel panel([&] { return next < batches.size() ? batches[next++] : QList<hedit::OutputMessage>(); });
    panel.flush();
    if (panel.view()->toPlainText() != "before\n") { qWarning() << "output first" << panel.view()->toPlainText(); return false; }
    panel.flush();  // 新しい出力だけで上限を超える: 前の表示は押し出され、末尾の5000行だけが入る。
    const QString text = panel.view()->toPlainText();
    if (text.contains("before") || text.contains("warn") || text.contains("flood 1000\n") || !text.startsWith("flood 1001\n")
        || !text.endsWith("flood 5999\n") || panel.view()->blockCount() > 5001) {
        qWarning() << "output trim" << panel.view()->blockCount() << text.left(40); return false;
    }
    panel.flush();  // 上限内の追記は、そのまま後ろに付く(上限で先頭が1行押し出される)。
    if (!panel.view()->toPlainText().endsWith("flood 5999\nafter\n") || panel.view()->blockCount() > 5001) {
        qWarning() << "output append"; return false;
    }
    // エラーの色(最後の行の手前)が付いている。
    QTextCursor cursor(panel.view()->document()->findBlockByNumber(panel.view()->blockCount() - 3));
    cursor.movePosition(QTextCursor::NextCharacter, QTextCursor::KeepAnchor);
    if (cursor.charFormat().foreground().color() != QColor("#ff0000")) {
        qWarning() << "output color" << cursor.charFormat().foreground().color().name(); return false;
    }
    return true;
}

/** @brief コード欄の入力・カーソル移動・描画の所要時間を測る(約4,000行のクラス中心の本文)。
 * @return 極端に遅くなっていなければtrue(時間はログに出す。上限は回帰を見つけるための緩いもの)。
 * @details 1回あたりのミリ秒を「editor 名前: 値 ms」の形で表示する。描画は表示部分をその場で描き直して測る。
 */
bool editorPerformancePasses() {
    QString source;
    for (int c = 0; c < 50; ++c) {
        source += QString("class Widget%1(object):\n    \"\"\"Widget %1.\"\"\"\n\n").arg(c);
        for (int m = 0; m < 10; ++m) {
            source += QString("    def method_%1(self, value, scale=1.0):\n").arg(m);
            source += "        result = []\n";
            source += "        for index in range(value):\n";
            source += "            item = (index * scale, {\"key\": [index, value]})\n";
            source += "            result.append(item)\n";
            source += "        self.cache = dict(result=result)\n";
            source += "        return result\n";
            source += "\n";
        }
    }
    // 最後に、2,000行にわたる括弧(対応する括弧を遠くまで探す)。
    source += "values = (\n";
    for (int i = 0; i < 2000; ++i) source += QString("    %1,\n").arg(i);
    source += ")\n";
    hedit::CodeEditor editor;
    editor.resize(900, 700);
    editor.show();
    editor.setPlainText(source);
    QApplication::processEvents();
    auto key = [&editor](int code, const QString& text) {
        QKeyEvent press(QEvent::KeyPress, code, Qt::NoModifier, text);
        QApplication::sendEvent(&editor, &press);
        QKeyEvent release(QEvent::KeyRelease, code, Qt::NoModifier, text);
        QApplication::sendEvent(&editor, &release);
    };
    auto paint = [&editor] {
        QApplication::processEvents();
        editor.viewport()->repaint();
    };
    auto measure = [](const char* name, int count, const std::function<void()>& step) {
        QElapsedTimer timer;
        timer.start();
        for (int i = 0; i < count; ++i) step();
        const double milliseconds = timer.nsecsElapsed() / 1e6 / count;
        qInfo().noquote() << QString("editor %1: %2 ms").arg(name).arg(milliseconds, 0, 'f', 3);
        return milliseconds;
    };
    // 本文の中ほどのメソッドの中へ移り、見出しの固定表示が出る位置までスクロールする。
    const int middle = editor.blockCount() / 3;
    QTextCursor cursor(editor.document()->findBlockByNumber(middle));
    while (!cursor.block().text().startsWith("            item")) cursor.movePosition(QTextCursor::NextBlock);
    cursor.movePosition(QTextCursor::EndOfBlock);
    editor.setTextCursor(cursor);
    editor.centerCursor();
    paint();
    double worst = 0;
    worst = qMax(worst, measure("keystroke", 100, [&] { key(Qt::Key_X, "x"); paint(); }));
    worst = qMax(worst, measure("backspace", 100, [&] { key(Qt::Key_Backspace, QString()); paint(); }));
    worst = qMax(worst, measure("caret blink paint", 200, [&] {
        editor.viewport()->repaint(editor.cursorRect().adjusted(-2, 0, 2, 0));
    }));
    worst = qMax(worst, measure("cursor down/up", 100, [&] {
        key(Qt::Key_Down, QString());
        paint();
        key(Qt::Key_Up, QString());
        paint();
    }));
    QScrollBar* bar = editor.verticalScrollBar();
    worst = qMax(worst, measure("scroll", 100, [&] {
        bar->setValue(bar->value() + 3);
        paint();
    }));
    // 同じ名前(result)の上で、同じ名前の強調を求め直す(入力が止まった0.15秒後と同じ処理)。
    cursor = editor.textCursor();
    cursor.movePosition(QTextCursor::StartOfBlock);
    while (!cursor.block().text().contains("result.append")) cursor.movePosition(QTextCursor::NextBlock);
    cursor.setPosition(cursor.block().position() + cursor.block().text().indexOf("result") + 2);
    editor.setTextCursor(cursor);
    worst = qMax(worst, measure("word highlight", 50, [&] { editor.updateWordHighlights(); }));
    // 2,000行先の括弧の対応(開き括弧の前後を行き来する)。
    QTextCursor bracket(editor.document()->findBlockByNumber(editor.blockCount() - 2003));
    while (!bracket.block().text().startsWith("values = (")) bracket.movePosition(QTextCursor::NextBlock);
    bracket.movePosition(QTextCursor::EndOfBlock);
    editor.setTextCursor(bracket);
    worst = qMax(worst, measure("far bracket match", 50, [&] {
        key(Qt::Key_Left, QString());
        key(Qt::Key_Right, QString());
    }));
    // 全て畳んだまま入力する。
    editor.foldAll();
    paint();
    worst = qMax(worst, measure("keystroke while folded", 50, [&] { key(Qt::Key_Y, "y"); paint(); }));
    editor.unfoldAll();
    if (worst > 200) {
        qWarning() << "editor operation too slow" << worst;
        return false;
    }
    return true;
}

/** @brief 画面の拡大率(4K等のInterface Scaling)が、文字・アイコンの固定寸法に掛かるか。 @return 期待どおりならtrue。 */
bool uiScalePasses() {
    hedit::setUiScale(2.0);
    hedit::EditorServices services;
    services.runPython = [](const QString&, const QString&) { return QString(); };
    auto large = hedit::createEditor(nullptr, services);
    large->show();
    QApplication::processEvents();
    auto bar = large->findChild<QToolBar*>("scriptToolbar");
    auto code = large->findChild<QPlainTextEdit*>("codeEditor");
    const bool ok = hedit::scaled(20) == 40 && bar && bar->iconSize() == QSize(40, 40) && code && code->font().pixelSize() == 28;
    if (!ok) qWarning() << "ui scale" << (bar ? bar->iconSize() : QSize()) << (code ? code->font().pixelSize() : -1);
    delete large;
    hedit::setUiScale(1.0);
    return ok;
}

/** @brief 初回履歴の整形(空行を省き、空白だけの行は前後をつなぐ)。 @return 期待どおりならtrue。 */
bool historyPasses() {
    return hedit::compactHistory("one\r\n\noptimization\n \non\n\n\nnext\n") == "one\noptimization on\nnext\n"
           && hedit::compactHistory("").isEmpty();
}

/** @brief 性能の計測に使う、クラスの多い約5,000行のPythonの本文を作る。
 * @return 構文エラーの無い本文(末尾は最後のクラスの中身の途中で、改行で終わる)。
 * @details クラスごとに、docstring・型ヒント付きの引数・``self.x = ...``・関数の中の変数・入れ子の関数・コメントを含む。
 * 最後のクラスの後ろへ、計測用のメソッドを書き足して使う(ホバー・補完・引数のヒントの位置)。
 */
QString benchmarkSource() {
    QString source =
        "\"\"\"Benchmark module for hedit.\n\nIt contains many classes.\n\"\"\"\n"
        "import os\nimport maya.cmds as cmds\nfrom typing import TYPE_CHECKING, List\n"
        "if TYPE_CHECKING:\n    from package.nodes import Joint\n\nLIMIT = 10\nNAMES: List[str] = []\n\n";
    int lines = source.count('\n');
    for (int c = 0; lines < 4950; ++c) {
        const QString n = QString::number(c);
        const QString name = "Widget" + n;
        const QString base = c == 0 ? QString("object") : "Widget" + QString::number(c - 1);
        QString block = "class " + name + "(" + base + "):\n"
            "    \"\"\"" + name + " docstring.\n\n    Longer description of the widget.\n\n"
            "    Attributes:\n        name (str): The name.\n    \"\"\"\n\n"
            "    COUNT = " + n + "\n"
            "    def __init__(self, name: str, size: int = 1, parent: \"Widget0\" = None):\n"
            "        \"\"\"Create the widget.\"\"\"\n"
            "        self.name = name\n        self.size = size\n        self.parent = parent\n"
            "        self.children = []  # child widgets\n        self.cache_" + n + " = {}\n\n";
        for (int m = 0; m < 6; ++m) {
            block += "    def method_" + QString::number(m) + "(self, radius: float = 1.0, *args, **kwargs) -> list:\n"
                "        \"\"\"Method docstring.\n\n        Args:\n            radius (float): The radius.\n        \"\"\"\n"
                "        result = []\n        count = 0\n"
                "        for index in range(self.size):\n            value = index * radius + self.COUNT\n"
                "            if value > LIMIT and value != count:\n                result.append(value)\n"
                "            count += 1\n"
                "        def helper(x, y=2):\n            return x + y\n"
                "        total = helper(count, len(result))\n"
                "        label = \"%s_%d\" % (self.name, total)  # format the label\n"
                "        return result\n\n";
        }
        block += "    @property\n    def label(self):\n        return '%s_%d' % (self.name, self.size)\n\n";
        source += block;
        lines += block.count('\n');
    }
    return source;
}

/** @brief core/の重い処理の時間を計る(性能の退行を見つけるため)。
 * @param config mayapyが書き出した、組み込みの名前と予約語のJSON(tests/maya_smoke.py)。
 * @return どの処理も上限の時間に収まり、結果が期待どおりならtrue。
 * @details 約5,000行の本文で、補完・ホバー・引数のヒント・構成・字句解析・宣言の抽出・差分などを繰り返し実行し、
 * 1回あたりの時間をqInfoで出す。上限はかなり緩くしてあり、極端に遅くなったときだけ失敗にする(計測の揺れで失敗しないため)。
 * 「cold」は、毎回少し違う本文(先頭の行を変えたもの)で問い合わせる。入力のたびに本文が変わる場合にあたる。
 */
bool corePerformancePasses(const QByteArray& config) {
    // sys.pathの代わりのフォルダー(Mayaのsys.pathと同じくらいの数)と、読み込み済みのmaya.cmdsの代わり。
    QTemporaryDir directory;
    if (!directory.isValid()) return false;
    const QDir root(directory.path());
    QStringList paths;
    for (int i = 0; i < 24; ++i) {
        const QString folder = root.filePath(QString("site%1").arg(i));
        QDir().mkpath(folder);
        for (int f = 0; f < 20; ++f) {
            QFile file(QDir(folder).filePath(QString("module_%1_%2.py").arg(i).arg(f)));
            if (file.open(QIODevice::WriteOnly)) file.write("def run():\n    pass\n");
        }
        paths.append(folder);
    }
    QDir().mkpath(root.filePath("site3/maya/cmds"));
    {
        QFile file(root.filePath("site3/maya/cmds/__init__.py"));
        if (file.open(QIODevice::WriteOnly)) file.write("\"\"\"Maya commands.\"\"\"\ndef ls(*args, **kwargs):\n    \"\"\"List.\"\"\"\n");
    }
    // Pythonから受け取る公開名の控え。hedit.bridgeと同じく、変わっていなければ同じ表(暗黙の共有)を返す。
    hedit::LoadedModule commands;
    for (int i = 0; i < 4000; ++i) commands.members.insert(QString("command%1").arg(i, 4, 10, QChar('0')), hedit::Symbol());
    commands.members.insert("ls", hedit::Symbol());
    commands.file = root.filePath("site3/maya/cmds/__init__.py");
    hedit::ModuleSource moduleSource;
    moduleSource.searchPaths = [paths] { return paths; };
    moduleSource.loadedModule = [&commands](const QString& name, hedit::LoadedModule* module) {
        if (name != "maya.cmds") return false;
        *module = commands;
        return true;
    };
    moduleSource.describe = [](const QString&, const QStringList&, QString*, QString*) { return false; };
    hedit::CompletionEngine engine(moduleSource);
    hedit::CompletionEnvironment environment;
    const auto data = QJsonDocument::fromJson(config).object();
    for (const auto& value : data.value("builtins").toArray()) environment.builtins.append(value.toString());
    for (const auto& value : data.value("keywords").toArray()) environment.keywords.append(value.toString());
    engine.setEnvironment(environment);

    const QString source = benchmarkSource();
    const QStringList lines = source.split('\n');
    // 最後のクラスに書き足すメソッド。ホバー・補完・引数のヒントは、この中の位置で行う。
    const QString tail = source
        + "    def tail(self, item: \"Widget2\", amount: int = 3):\n"
          "        local_value = item.size + amount\n"
          "        print(local_value)\n";
    const QString selfText = tail + "        self.";
    const QString nameText = tail + "        lab";
    const QString commandText = tail + "        cmds.l";
    const QString hoverText = tail + "        item.size\n        return local_value\n";
    const QString localNeedle = "print(local_value";
    const int localEnd = hoverText.indexOf(localNeedle) + int(localNeedle.size());
    const int itemEnd = hoverText.lastIndexOf("item.size");
    const QString callText = tail + "        result = Widget4(local_value, ";
    QStringList edited = lines;
    edited[3] = "import sys";
    edited.insert(20, "EXTRA = 1");
    edited.removeAt(40);
    edited[edited.size() - 10] = "        return None";
    edited.insert(edited.size() - 30, "    # added near the end");

    bool ok = true;
    qint64 sink = 0;  // 結果を使い、最適化で処理が消えないようにする。
    int revision = 0;
    // 1つの処理を、300ms経つか200回になるまで繰り返し、1回あたりの時間を出す。
    auto measure = [&ok](const char* name, double limit, const std::function<void()>& run) {
        QElapsedTimer timer;
        timer.start();
        int count = 0;
        do {
            run();
            ++count;
        } while (count < 200 && timer.elapsed() < 300);
        const double perRun = double(timer.nsecsElapsed()) / 1e6 / count;
        qInfo().noquote() << QString("benchmark %1: %2 ms/op (%3 runs)").arg(QString::fromLatin1(name), -26).arg(perRun, 0, 'f', 3).arg(count);
        if (perRun > limit) {
            qWarning() << "too slow" << name << perRun << "ms, limit" << limit;
            ok = false;
        }
    };
    auto variant = [&revision](const QString& text) { return "# edit " + QString::number(++revision) + "\n" + text; };
    measure("complete self.", 30, [&] { sink += engine.complete(selfText).items.size(); });
    measure("complete self. cold", 60, [&] { sink += engine.complete(variant(selfText)).items.size(); });
    measure("complete name", 20, [&] { sink += engine.complete(nameText).items.size(); });
    measure("complete name cold", 60, [&] { sink += engine.complete(variant(nameText)).items.size(); });
    measure("complete cmds.", 20, [&] { sink += engine.complete(commandText).items.size(); });
    measure("describe local", 20, [&] { sink += engine.describe(hoverText, localEnd).signature.size(); });
    measure("describe local cold", 60, [&] {
        const QString text = variant(hoverText);
        sink += engine.describe(text, localEnd + int(text.size() - hoverText.size())).signature.size();
    });
    measure("describe parameter", 20, [&] { sink += engine.describe(hoverText, itemEnd + 4).signature.size(); });
    measure("definition local", 30, [&] { sink += engine.definition(hoverText, localEnd).line; });
    measure("signature context", 20, [&] { sink += hedit::findCallContext(callText).argumentIndex; });
    measure("buildOutline", 60, [&] { sink += hedit::buildOutline(source, hedit::ScriptLanguage::Python).size(); });
    measure("tokenizeLine (all)", 60, [&] {
        int state = 0;
        for (const QString& line : lines) sink += hedit::tokenizeLine(line, hedit::ScriptLanguage::Python, state, &state).size();
    });
    measure("extractDeclarations", 80, [&] { sink += hedit::extractPythonDeclarations(source).symbols.size(); });
    measure("indentationFoldRanges", 30, [&] { sink += hedit::indentationFoldRanges(lines).size(); });
    measure("diffLines both ends", 30, [&] { sink += hedit::diffLines(lines, edited).size(); });
    // 1,500行: 以前のLCSの表(行数の積が250万以下)を使う大きさで、両端を変えた場合。
    const QStringList medium = lines.mid(0, 1500);
    QStringList mediumEdited = medium;
    mediumEdited[2] = "import sys";
    mediumEdited.insert(30, "EXTRA = 1");
    mediumEdited[mediumEdited.size() - 8] = "        return None";
    mediumEdited.removeAt(mediumEdited.size() - 20);
    measure("diffLines 1500 both ends", 10, [&] { sink += hedit::diffLines(medium, mediumEdited).size(); });
    // 結果の確かめ(計測した処理が意味のある結果を返しているか)。
    const QStringList commandNames = [&] {
        QStringList result;
        for (const auto& item : engine.complete(commandText).items) result.append(item.name);
        return result;
    }();
    const hedit::HoverInfo parameter = engine.describe(hoverText, itemEnd + 4);
    const hedit::CallContext call = hedit::findCallContext(callText);
    if (!commandNames.contains("ls") || parameter.signature != "class Widget2(Widget1)" || call.argumentIndex != 1
        || hedit::extractPythonDeclarations(source).symbols.size() < 30) {
        qWarning() << "benchmark results" << commandNames.mid(0, 5) << parameter.signature << call.argumentIndex;
        ok = false;
    }
    qInfo() << "benchmark source lines" << lines.size() << "checksum" << sink;
    return ok;
}

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
    const QByteArray config = file.readAll();
    // Maya無しで確かめられる部分。1件ずつ名前を表示し、失敗があれば画面の検査に進まずに終える。
    const int failed = runCases({
        {"history", historyPasses},
        {"moduleScan", moduleScanPasses},
        {"textSearch", textSearchPasses},
        {"sessionData", sessionDataPasses},
        {"editCommands", editCommandsPasses},
        {"lexer", lexerPasses},
        {"declarations", declarationsPasses},
        {"scriptFile", scriptFilePasses},
        {"docstrings", docstringsPasses},
        {"preferences", preferencesPasses},
        {"uiScale", uiScalePasses},
        {"completionEngine", [&config] { return completionEnginePasses(config); }},
        {"codeOutline", codeOutlinePasses},
        {"lineDiff", lineDiffPasses},
        {"signatureHelp", signatureHelpPasses},
        {"navigation", navigationPasses},
        {"outputPanel", outputPanelPasses},
        {"editorPerformance", editorPerformancePasses},
        {"corePerformance", [&config] { return corePerformancePasses(config); }},
    });
    if (failed > 0) {
        return 10;
    }
    bool outputSent=false;
    // Mayaの代わりに、決まった値を返す偽の関数を渡す。
    hedit::EditorServices services;
    QString lastRun;
    services.runPython = [&lastRun](const QString& code, const QString&) { lastRun = code; return "executed: " + code; };

    services.takeOutput = [&outputSent] {
        if (outputSent) return QList<hedit::OutputMessage>();
        outputSent=true;
        return QList<hedit::OutputMessage>{{"result_marker\n",hedit::OutputKind::Result},{"history_marker\n",hedit::OutputKind::History},{"normal_marker\n",hedit::OutputKind::Normal}};
    };
    services.complete = [](const QString&) {
        hedit::CompletionResult result;
        result.items.append({"createNode", "UI fixture", QString()});
        return result;
    };
    int definitionCalls = 0;
    services.definition = [&definitionCalls](const QString& text, int end) {
        ++definitionCalls;
        hedit::DefinitionLocation location;
        if (text.left(end).endsWith("target")) {
            location.line = 0;
            location.column = 4;
        }
        return location;
    };
    services.describe = [](const QString& text, int end) {
        hedit::HoverInfo info;
        if (text.left(end).endsWith("cmds.ls")) {
            info.signature = "def ls(*args, **kwargs)";
            info.doc = "List objects.\n\nArgs:\n    selection (bool): Only the selected objects.\n\nReturns:\n    list: ``[names]``.";
        }
        return info;
    };
    auto window = hedit::createEditor(nullptr, services);
    window->show();
    auto code = window->findChild<QPlainTextEdit*>("codeEditor");
    if (!code) return 4;
    {
        // ホバー: 名前の上でマウスが止まったとき(QEvent::ToolTip)に説明の小窓を出し、Escで閉じる。
        code->setPlainText("import maya.cmds as cmds\ncmds.ls(selection=True)");
        QApplication::processEvents();
        QTextCursor at(code->document());
        at.setPosition(QString("import maya.cmds as cmds\ncmds.l").size());
        const QPoint point = code->cursorRect(at).center();
        QHelpEvent help(QEvent::ToolTip, point, code->viewport()->mapToGlobal(point));
        QApplication::sendEvent(code->viewport(), &help);
        auto popup = code->findChild<QFrame*>("hoverPopup");
        if (!popup || !popup->isVisible()) { qWarning() << "hover popup not shown"; return 22; }
        popup->grab().save(QString::fromLocal8Bit(argv[2]) + ".hover.png");
        // 説明の無い名前(引数名)の上では出さない。
        at.setPosition(QString("import maya.cmds as cmds\ncmds.ls(sel").size());
        const QPoint keyword = code->cursorRect(at).center();
        QHelpEvent onArgument(QEvent::ToolTip, keyword, code->viewport()->mapToGlobal(keyword));
        QApplication::sendEvent(code->viewport(), &onArgument);
        if (popup->isVisible()) { qWarning() << "hover shown for an argument without a description"; return 23; }
        QApplication::sendEvent(code->viewport(), &help);
        QKeyEvent escape(QEvent::KeyPress, Qt::Key_Escape, Qt::NoModifier);
        QApplication::sendEvent(code, &escape);
        if (popup->isVisible() || code->toPlainText() != "import maya.cmds as cmds\ncmds.ls(selection=True)") {
            qWarning() << "hover escape"; return 24;
        }
    }

    {
        // コード欄の新しい機能(offscreen)。キー入力は実際のキーイベントで確かめる。
        auto editor = static_cast<hedit::CodeEditor*>(code);
        auto type = [editor](int key, const QString& text, Qt::KeyboardModifiers modifiers = Qt::NoModifier) {
            QKeyEvent press(QEvent::KeyPress, key, modifiers, text);
            QApplication::sendEvent(editor, &press);
        };
        // 括弧の自動で閉じる・閉じ括弧の上書き・空の対の削除・選択を囲む・引用符。
        editor->setPlainText("");
        type(Qt::Key_ParenLeft, "(");
        if (editor->toPlainText() != "()" || editor->textCursor().position() != 1) { qWarning() << "auto close" << editor->toPlainText(); return 30; }
        type(Qt::Key_ParenRight, ")");
        if (editor->toPlainText() != "()" || editor->textCursor().position() != 2) { qWarning() << "overtype"; return 31; }
        editor->moveCursor(QTextCursor::Left);
        type(Qt::Key_Backspace, QString());
        if (!editor->toPlainText().isEmpty()) { qWarning() << "pair delete" << editor->toPlainText(); return 32; }
        editor->setPlainText("name");
        editor->selectAll();
        type(Qt::Key_QuoteDbl, "\"");
        if (editor->toPlainText() != "\"name\"" || editor->textCursor().selectedText() != "name") { qWarning() << "surround"; return 33; }
        editor->setPlainText("x = f");
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_QuoteDbl, "\"");
        if (editor->toPlainText() != "x = f\"\"") { qWarning() << "string prefix" << editor->toPlainText(); return 34; }
        editor->setPlainText("value");
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_QuoteDbl, "\"");
        if (editor->toPlainText() != "value\"") { qWarning() << "no pair after name" << editor->toPlainText(); return 35; }
        // 自分で打った閉じ括弧は上書きしない(自動で入れたものだけ。VS Codeと同じ)。
        editor->setPlainText("f(x)");
        QTextCursor place(editor->document());
        place.setPosition(3);
        editor->setTextCursor(place);
        type(Qt::Key_ParenRight, ")");
        if (editor->toPlainText() != "f(x))") { qWarning() << "manual closer overtyped" << editor->toPlainText(); return 57; }
        // Home: 行頭の空白の後 ⇔ 行の先頭。Shift+Homeは選択する。
        editor->setPlainText("    value = 1");
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_Home, QString());
        const int firstHome = editor->textCursor().position();
        type(Qt::Key_Home, QString());
        const int secondHome = editor->textCursor().position();
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_Home, QString(), Qt::ShiftModifier);
        if (firstHome != 4 || secondHome != 0 || editor->textCursor().selectedText() != "value = 1") {
            qWarning() << "smart home" << firstHome << secondHome << editor->textCursor().selectedText(); return 58;
        }
        // Enterの規則: 「:」の後は深く、return の後は浅く、括弧の間は閉じ括弧を次の行へ、空白だけの行は空白を消す。
        // コメントの中の「:」では深くしない。
        auto enterAfter = [&](const QString& text, int position) {
            editor->setPlainText(text);
            QTextCursor at(editor->document());
            at.setPosition(position < 0 ? text.size() : position);
            editor->setTextCursor(at);
            type(Qt::Key_Return, "\r");
            return editor->toPlainText() + "|" + QString::number(editor->textCursor().position());
        };
        const QList<QPair<QStringList, QString>> enters{
            {{"def f():", "-1"}, "def f():\n    |13"},
            {{"    return x", "-1"}, "    return x\n|13"},
            {{"    pass", "-1"}, "    pass\n|9"},
            {{"foo()", "4"}, "foo(\n    \n)|9"},
            {{"    ", "-1"}, "\n    |5"},
            {{"x = 1  # note:", "-1"}, "x = 1  # note:\n|15"},
            {{"if x:  # c", "-1"}, "if x:  # c\n    |15"},
            {{"items = [", "-1"}, "items = [\n    |14"},
        };
        for (const auto& enter : enters) {
            const QString got = enterAfter(enter.first[0], enter.first[1].toInt());
            if (got != enter.second) { qWarning() << "enter rule" << enter.first << got; return 59; }
        }
        // else: などの「:」を打ったら、前のブロックの深さから1段浅くする。自分で浅くした行はそのまま。
        editor->setPlainText("if x:\n    a = 1\n    else");
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_Colon, ":");
        if (editor->toPlainText() != "if x:\n    a = 1\nelse:") { qWarning() << "dedent else" << editor->toPlainText(); return 60; }
        editor->setPlainText("if x:\n    a = 1\nelif y");
        editor->moveCursor(QTextCursor::End);
        type(Qt::Key_Colon, ":");
        if (editor->toPlainText() != "if x:\n    a = 1\nelif y:") { qWarning() << "keep dedented" << editor->toPlainText(); return 61; }
        // 選択なしのCtrl+Cでコピーした行は、カーソルの行の上へ行として貼る。カーソルは元の文字の上に残る。
        editor->setPlainText("first\nsecond");
        editor->moveCursor(QTextCursor::Start);
        type(Qt::Key_C, QString(), Qt::ControlModifier);
        place = QTextCursor(editor->document());
        place.setPosition(9);  // second の "o" の前
        editor->setTextCursor(place);
        editor->paste();
        if (editor->toPlainText() != "first\nfirst\nsecond" || editor->textCursor().position() != 15) {
            qWarning() << "line paste" << editor->toPlainText() << editor->textCursor().position(); return 62;
        }
        // 普通のコピーはカーソルの位置へ入る。
        QApplication::clipboard()->setText("XY");
        editor->paste();
        if (editor->toPlainText() != "first\nfirst\nsecXYond") { qWarning() << "normal paste" << editor->toPlainText(); return 63; }
        // Ctrl+↓・Ctrl+↑: カーソルを動かさずに1行スクロールする。
        QString lines;
        for (int i = 0; i < 300; ++i) lines += QString("line_%1\n").arg(i);
        editor->setPlainText(lines);
        editor->moveCursor(QTextCursor::Start);
        const int scrollBefore = editor->verticalScrollBar()->value();
        type(Qt::Key_Down, QString(), Qt::ControlModifier);
        if (editor->verticalScrollBar()->value() != scrollBefore + 1 || editor->textCursor().position() != 0) {
            qWarning() << "ctrl+down" << editor->verticalScrollBar()->value(); return 64;
        }
        type(Qt::Key_Up, QString(), Qt::ControlModifier);
        if (editor->verticalScrollBar()->value() != scrollBefore) { qWarning() << "ctrl+up"; return 65; }
        // 補完の一覧: 大文字小文字を区別せず絞り込み、打った名前と同じ候補だけならEnterで改行する。
        editor->setPlainText("pcu");
        editor->moveCursor(QTextCursor::End);
        editor->showCompletions({{"polyCube", "", "", "function"}, {"polySphere", "", "", "function"}, {"PCurve", "", "", "function"}});
        if (editor->isCompletionVisible()) {
            QStringList shown;
            const QAbstractItemModel* model = editor->completer()->completionModel();
            for (int row = 0; row < model->rowCount(); ++row) shown.append(model->index(row, 0).data().toString());
            if (shown != QStringList{"PCurve", "polyCube"}) { qWarning() << "fuzzy popup" << shown; return 66; }
            editor->hideCompletions();
            editor->setPlainText("value");
            editor->moveCursor(QTextCursor::End);
            editor->showCompletions({{"value", "", "", "variable"}, {"value2", "", "", "variable"}});
            type(Qt::Key_Return, "\r");
            if (editor->toPlainText() != "value\n" || editor->isCompletionVisible()) {
                qWarning() << "exact match enter" << editor->toPlainText(); return 67;
            }
        }

        // 同じ名前の強調と、対応する括弧の強調。
        editor->setPlainText("alpha = 1\nbeta = alpha + alpha\nprint(beta)\n");
        QTextCursor cursor(editor->document());
        cursor.setPosition(2);
        editor->setTextCursor(cursor);
        editor->updateWordHighlights();
        if (editor->wordHighlights() != QList<int>{0, 17, 25}) { qWarning() << "word highlight" << editor->wordHighlights(); return 36; }
        cursor.setPosition(36);
        editor->setTextCursor(cursor);
        if (editor->bracketHighlights() != QList<int>{36, 41}) { qWarning() << "bracket highlight" << editor->bracketHighlights(); return 37; }

        // 折りたたみ: 畳むと中身の行が隠れ、カーソルが中にあれば見出しへ移る。
        editor->setPlainText("def f():\n    a = 1\n    b = 2\nx = 3\ny = 4\n");
        cursor.setPosition(15);
        editor->setTextCursor(cursor);
        editor->foldAtCursor();
        const QTextBlock hiddenBlock = editor->document()->findBlockByNumber(1);
        if (!editor->isFolded(0) || hiddenBlock.isVisible() || editor->textCursor().blockNumber() != 0) {
            qWarning() << "fold" << editor->isFolded(0) << hiddenBlock.isVisible(); return 38;
        }
        editor->moveCursor(QTextCursor::Down);  // 畳んだ範囲を飛び越える。
        if (editor->textCursor().blockNumber() != 3 || !editor->isFolded(0)) { qWarning() << "skip fold" << editor->textCursor().blockNumber(); return 39; }
        editor->setTextCursor(QTextCursor(editor->document()->findBlockByNumber(4)));
        cursor = QTextCursor(editor->document()->findBlockByNumber(2));
        editor->setTextCursor(cursor);  // 検索などで隠れた行へ(隣の行以外から)移ると開く。
        if (editor->isFolded(0) || !editor->document()->findBlockByNumber(2).isVisible()) { qWarning() << "reveal"; return 40; }
        editor->foldAll();
        editor->unfoldAll();
        if (editor->isFolded(0)) { qWarning() << "unfold all"; return 41; }

        // 見出しの固定表示: クラスのメソッドの中までスクロールすると、クラスとメソッドの見出しが上端に残る。
        QString longText = "class Long:\n    def method(self):\n";
        for (int i = 0; i < 200; ++i) longText += QString("        value_%1 = %1\n").arg(i);
        editor->setPlainText(longText);
        editor->resize(600, 300);
        QApplication::processEvents();
        editor->verticalScrollBar()->setValue(50);
        QApplication::processEvents();
        if (editor->stickyLines() != QList<int>{0, 1}) { qWarning() << "sticky" << editor->stickyLines(); return 42; }
        editor->setStickyScroll(false);
        if (!editor->stickyLines().isEmpty()) { qWarning() << "sticky off"; return 43; }
        editor->setStickyScroll(true);

        // 保存前との差分の印と、スクロールバーの印。
        editor->setPlainText("a\nB\nc\nd\n");
        editor->setSavedText("a\nb\nc\n");
        editor->updateLineChanges();
        if (editor->lineChanges().size() != 2 || editor->lineChanges()[0].kind() != "modified" || editor->lineChanges()[1].kind() != "added") {
            qWarning() << "line changes" << editor->lineChanges().size(); return 44;
        }
        // 問題の波線と F8(次の問題へ移動して説明を出す)。
        editor->setDiagnostics({{"warning", 3, "\"c\" is not defined", 1, 1}});
        editor->moveCursor(QTextCursor::Start);
        if (!editor->goToProblem(1) || editor->textCursor().blockNumber() != 2) { qWarning() << "next problem"; return 45; }
        editor->updateScrollMarkers();
        bool problemMarker = false;
        for (const auto& marker : editor->markerScrollBar()->markers()) problemMarker = problemMarker || marker.lane == 2;
        if (!problemMarker) { qWarning() << "scroll markers"; return 46; }
        editor->setDiagnostics({});
        editor->clearSavedText();
        editor->hideHover();

        // 選択範囲の拡大と、元に戻す。
        editor->setPlainText("result = foo(bar.baz, 1)\n");
        cursor = QTextCursor(editor->document());
        cursor.setPosition(18);
        editor->setTextCursor(cursor);
        type(Qt::Key_Right, QString(), Qt::ShiftModifier | Qt::AltModifier);
        if (editor->textCursor().selectedText() != "baz") { qWarning() << "expand 1" << editor->textCursor().selectedText(); return 47; }
        type(Qt::Key_Right, QString(), Qt::ShiftModifier | Qt::AltModifier);
        if (editor->textCursor().selectedText() != "bar.baz") { qWarning() << "expand 2"; return 48; }
        type(Qt::Key_Right, QString(), Qt::ShiftModifier | Qt::AltModifier);
        if (editor->textCursor().selectedText() != "bar.baz, 1") { qWarning() << "expand 3"; return 49; }
        type(Qt::Key_Left, QString(), Qt::ShiftModifier | Qt::AltModifier);
        if (editor->textCursor().selectedText() != "bar.baz") { qWarning() << "shrink"; return 50; }

        // 記号へ移動(Ctrl+Shift+O): 一覧で絞り込んで Enter でその行へ移る。
        editor->setPlainText("class Alpha:\n    def first(self):\n        pass\n\ndef second():\n    pass\n");
        for (auto action : window->findChildren<QAction*>()) if (action->objectName() == "goToSymbol") action->trigger();
        // Q_OBJECTの無いクラスはfindChildに渡せない(Qt 6.8以降)ので、基底クラスで探してから変換する。
        auto pick = static_cast<hedit::QuickPick*>(window->findChild<QFrame*>("quickPick"));
        if (!pick || !pick->isVisible() || pick->list()->count() != 3) { qWarning() << "symbol picker" << (pick ? pick->list()->count() : -1); return 51; }
        pick->input()->setText("sec");
        QKeyEvent enter(QEvent::KeyPress, Qt::Key_Return, Qt::NoModifier);
        QApplication::sendEvent(pick->input(), &enter);
        if (pick->isVisible() || editor->textCursor().blockNumber() != 4) { qWarning() << "symbol accept" << editor->textCursor().blockNumber(); return 52; }
        if (hedit::QuickPick::matchScore("second", "sec") <= hedit::QuickPick::matchScore("my_second", "sec")
            || hedit::QuickPick::matchScore("abc", "xyz") != -1 || hedit::QuickPick::matchScore("build_chain", "bch") < 0) {
            qWarning() << "match score"; return 53;
        }

        // アウトライン: 表示すると構成の木ができ、項目のクリックでその行へ移る。
        for (auto action : window->findChildren<QAction*>()) if (action->objectName() == "toggleOutline") action->trigger();
        QApplication::processEvents();
        auto outlineTree = window->findChild<QTreeWidget*>("outline");
        if (!outlineTree || outlineTree->topLevelItemCount() != 2 || outlineTree->topLevelItem(0)->childCount() != 1) {
            qWarning() << "outline panel" << (outlineTree ? outlineTree->topLevelItemCount() : -1); return 54;
        }
        for (auto action : window->findChildren<QAction*>()) if (action->objectName() == "toggleOutline") action->trigger();

        // 定義へ移動(F12): 本文の中の定義なら、その行へ移る。
        definitionCalls = 0;
        editor->setPlainText("def target():\n    pass\n\ntarget()\n");
        cursor = QTextCursor(editor->document());
        cursor.setPosition(26);
        editor->setTextCursor(cursor);
        for (auto action : window->findChildren<QAction*>()) if (action->text() == "Go to definition") action->trigger();
        if (definitionCalls != 1 || editor->textCursor().blockNumber() != 0 || editor->textCursor().positionInBlock() != 4) {
            qWarning() << "go to definition" << definitionCalls << editor->textCursor().blockNumber(); return 55;
        }
        // 引数のヒント: 呼出しの中で、今の引数を強調した説明を出す。
        editor->setPlainText("import maya.cmds as cmds\ncmds.ls(1, ");
        editor->moveCursor(QTextCursor::End);
        QApplication::setActiveWindow(window);
        editor->setFocus(Qt::OtherFocusReason);
        if (editor->hasFocus() && editor->onSignatureHelpRequested) {
            editor->onSignatureHelpRequested(true);
            auto help = editor->findChild<QFrame*>("signatureHelp");
            if (!help || !help->isVisible()) { qWarning() << "signature help"; return 56; }
            editor->hideSignatureHelp();
        }
    }
    {
        // U+2028(行区切り)はPythonの構文エラーになる。Shift+Enter・貼り付け・実行のどれでも普通の改行にする。
        code->setPlainText("a = 1");
        code->moveCursor(QTextCursor::End);
        QKeyEvent shiftEnter(QEvent::KeyPress, Qt::Key_Return, Qt::ShiftModifier);
        QApplication::sendEvent(code, &shiftEnter);
        if (code->blockCount() != 2 || code->document()->toRawText().contains(QChar::LineSeparator)) {
            qWarning() << "shift+enter inserted a line separator"; return 25;
        }
        code->clear();
        QApplication::clipboard()->setText(QString("x = 1") + QChar(0x2028) +"y = 2\r\nz = 3");
        code->paste();
        if (code->blockCount() != 3 || code->document()->toRawText().contains(QChar::LineSeparator)
            || code->toPlainText() != "x = 1\ny = 2\nz = 3") {
            qWarning() << "paste kept a line separator" << code->toPlainText(); return 26;
        }
        // 以前の版で入ってしまった行区切りが残っていても、実行する文字列では改行にする。
        code->setPlainText("x = 1");
        code->moveCursor(QTextCursor::End);
        code->textCursor().insertText(QString(QChar(0x2028)) + "y = 2");
        code->selectAll();
        for (auto action : window->findChildren<QAction*>()) if (action->text() == "Run all") action->trigger();
        if (lastRun != "x = 1\ny = 2") { qWarning() << "run all" << lastRun; return 27; }
        lastRun.clear();
        for (auto action : window->findChildren<QAction*>()) if (action->text() == "Run selection / script") action->trigger();
        if (lastRun != "x = 1\ny = 2") { qWarning() << "run selection" << lastRun; return 28; }
    }
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
