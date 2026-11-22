/** @file external_file_gui.cpp
 * @brief 実ファイル通知で外部変更、未保存保護、削除・再作成、復元を検証する。専用一時領域のみ使う。
 */
#include "core/script_file.h"
#include "editor/code_editor.h"
#include "editor/editor.h"
#include "editor/editor_tabs.h"
#include "editor/session_store.h"
#include <QAction>
#include <QAbstractButton>
#include <QApplication>
#include <QDebug>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QInputMethodEvent>
#include <QMessageBox>
#include <QPushButton>
#include <QScrollBar>
#include <QTemporaryDir>
#include <QTimer>
#include <memory>

namespace {
/** @brief Qtの実通知を処理する。 @param ms 待機ミリ秒。 */
void settle(int ms = 800) {
    QEventLoop loop;
    QTimer::singleShot(ms, &loop, &QEventLoop::quit);
    loop.exec();
}
/** @brief 失敗箇所を表示する。 @param ok 判定。 @param name 観点。 @return 判定。 */
bool check(bool ok, const char* name) {
    if (ok) qInfo() << "PASS external" << name;
    else qCritical() << "FAIL external" << name;
    return ok;
}
/** @brief 指定した標準ボタンで専用ダイアログに応答する。 @param button 選択するボタン。 */
void answer(QMessageBox::StandardButton button) {
    QTimer::singleShot(80, qApp, [button] {
        for (auto* widget : QApplication::topLevelWidgets()) {
            if (auto* box = qobject_cast<QMessageBox*>(widget)) {
                if (auto* target = box->button(button)) target->click();
            }
        }
    });
}
}

/** @brief 画面と実ファイル監視を接続して検証する。 @return 全観点の成功。 */
bool externalFileGuiPasses() {
    QTemporaryDir temporary;
    if (!temporary.isValid()) return false;
    const QDir root(temporary.path());
    const QString path = root.filePath("sample.py"), second = root.filePath("inactive.py");
    QString error;
    const QString initial = "# external file test\nvalue = 'initial'\n";
    if (!mce::writeScriptFile(path, initial, &error) || !mce::writeScriptFile(second, initial, &error)) return false;
    mce::EditorServices services; services.sessionPath = root.filePath("session/tabs.json");
    mce::SessionStore seed(services.sessionPath);
    mce::SessionData data, unused; seed.open(&unused);
    for (const auto& name : {path, second}) {
        mce::TabState tab; tab.id = mce::newTabId(); tab.path = name; tab.text = initial;
        data.tabs.append(tab);
    }
    if (!seed.save(data, &error)) return false;
    auto window = std::unique_ptr<QMainWindow>(mce::createEditor(nullptr, services));
    window->show();
    auto* tabs = static_cast<mce::EditorTabs*>(window->findChild<QTabWidget*>());
    auto* editor = tabs->editorAt(0);
    auto* inactive = tabs->editorAt(1);
    settle();
    if (!check(inactive->property("textPending").toBool(), "inactive restore stays lazy")) return false;
    const auto cursor = editor->textCursor();
    // QSaveFileによる原子的差し替えを繰り返しても監視が外れない。
    for (const auto& value : {"one", "two", "three"}) {
        const QString text = QString("# external file test\nvalue = '%1'\n").arg(value);
        if (!mce::writeScriptFile(path, text, &error)) return false;
        settle();
        if (!check(editor->toPlainText() == text && !editor->document()->isModified()
            && editor->textCursor().position() == cursor.position(), "atomic save, clean state, cursor")) return false;
    }
    QApplication::setActiveWindow(window.get()); editor->setFocus();
    QWidget* focus = QApplication::focusWidget();
    if (!mce::writeScriptFile(second, "inactive = 42\n", &error)) return false;
    settle();
    if (!check(inactive->toPlainText() == "inactive = 42\n" && tabs->currentIndex() == 0
        && QApplication::focusWidget() == focus, "inactive update preserves active tab and focus")) return false;
    editor->moveCursor(QTextCursor::End); editor->insertPlainText("local = True\n");
    const QString local = editor->toPlainText();
    if (!mce::writeScriptFile(path, "external = 99\n", &error)) return false;
    settle();
    if (!check(editor->toPlainText() == local && editor->document()->isModified()
        && !editor->property("externalFileNotice").toString().isEmpty(), "unsaved edits protected")) return false;
    QAction* save = nullptr;
    for (auto* action : window->findChildren<QAction*>()) if (action->text() == "Save") save = action;
    if (!save) return false;
    answer(QMessageBox::Cancel); save->trigger();
    QString disk;
    if (!mce::readScriptFile(path, &disk, &error)
        || !check(disk == "external = 99\n" && editor->toPlainText() == local, "save conflict cancel preserves both")) return false;
    auto* reload = window->findChild<QPushButton*>("reloadExternalFile");
    answer(QMessageBox::Cancel); reload->click();
    if (!check(editor->toPlainText() == local, "reload cancel")) return false;
    answer(QMessageBox::Discard); reload->click(); settle();
    if (!check(editor->toPlainText() == disk && !editor->document()->isModified(), "explicit reload")) return false;
    if (!QFile::remove(path)) return false;
    settle();
    if (!check(editor->toPlainText() == disk && !editor->property("externalFileNotice").toString().isEmpty(), "deleted file preserves text")) return false;
    if (!mce::writeScriptFile(path, "recreated = True\n", &error)) return false;
    settle();
    if (!check(editor->toPlainText() == "recreated = True\n" && editor->property("externalFileNotice").toString().isEmpty(), "recreated file resumes watch")) return false;
    QFile direct(path);
    if (!direct.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    direct.write("value = '\xe6\x97\xa5\xe6\x9c\xac'\r\n"); direct.close(); settle();
    if (!check(editor->toPlainText() == QString::fromUtf8("value = '日本'\n"), "in-place UTF-8 CRLF save")) return false;
    // IMEの未確定文字を外部保存で消さない。
    QInputMethodEvent preedit(QString::fromUtf8("変換"), {});
    QApplication::sendEvent(editor, &preedit);
    const QString beforeIme = editor->toPlainText();
    if (!mce::writeScriptFile(path, "after_ime = 1\n", &error)) return false;
    settle();
    if (!check(editor->toPlainText() == beforeIme && editor->isInputMethodComposing(), "IME preedit protected")) return false;
    QInputMethodEvent cancel;
    QApplication::sendEvent(editor, &cancel);
    reload->click(); settle();
    // 自分の保存通知はUndoとカーソルを変えない。
    editor->moveCursor(QTextCursor::End); editor->insertPlainText("self_save = 1\n");
    save->trigger();
    const int revision = editor->document()->revision();
    settle();
    if (!check(editor->document()->revision() == revision && editor->document()->isUndoAvailable()
        && !editor->document()->isModified(), "self save does not reload")) return false;
    // 読めない符号化も既存本文を保持する。
    const QString good = editor->toPlainText();
    if (!direct.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    direct.write("\xff\xfe", 2); direct.close(); settle();
    if (!check(editor->toPlainText() == good && !editor->property("externalFileNotice").toString().isEmpty(), "invalid encoding preserves text")) return false;
    if (!mce::writeScriptFile(path, good, &error)) return false;
    settle(); window.reset();
    if (!mce::writeScriptFile(path, "changed_while_closed = True\n", &error)) return false;
    window.reset(mce::createEditor(nullptr, services));
    tabs = static_cast<mce::EditorTabs*>(window->findChild<QTabWidget*>());
    if (!check(tabs->editorAt(0)->toPlainText() == "changed_while_closed = True\n"
        && !tabs->editorAt(0)->document()->isModified(), "clean tab follows changes while closed")) return false;
    editor = tabs->editorAt(0);
    editor->moveCursor(QTextCursor::End);
    editor->insertPlainText("unsaved_before_close = True\n");
    const QString recovered = editor->toPlainText();
    window.reset();
    if (!mce::writeScriptFile(path, "another_external_change = True\n", &error)) return false;
    window.reset(mce::createEditor(nullptr, services));
    tabs = static_cast<mce::EditorTabs*>(window->findChild<QTabWidget*>());
    settle();
    if (!check(tabs->editorAt(0)->toPlainText() == recovered && tabs->editorAt(0)->document()->isModified(),
               "dirty tab survives external update across restart")) return false;
    // 未配送の通知を残して破棄しても、コールバックは破棄済み画面に触れない。
    mce::writeScriptFile(path, "last = 1\n", &error);
    window.reset(); settle();
    qInfo() << "External file GUI checks passed";
    return true;
}
