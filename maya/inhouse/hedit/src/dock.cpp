/** @file dock.cpp
 * @brief hedit画面のworkspaceControlへのドッキングと、開閉状態の保存・復元。
 * @details 旧docking.py/startup.pyをC++へ移したもの。Mayaのドックは、MELのworkspaceControlが
 * 作るUIへ、MQtUtil::addWidgetToMayaLayoutで編集画面(QMainWindow)を直接入れて使う。
 * ドックのuiScript・closeCommand・終了通知のscriptJobはMEL(hedit -restore等)で登録し、Pythonを介さない。
 * 編集画面の所有者はドック(MayaのUI)で、QPointerで参照して破棄後の使用を防ぐ。
 */
#include "dock.h"
#include "mayautil.h"
#include "version.h"
#include <maya/MQtUtil.h>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPointer>
#include <QSaveFile>
#include <QTimer>

namespace hedit {
namespace dock {
namespace {
std::function<QMainWindow*(bool)> editorFactory;
std::function<QString()> sessionPathFunction;
/// 遅延実行の文脈。プラグイン解除時に破棄し、未実行の遅延処理を取り消す。
QPointer<QObject> guard;
/// 表示中の配置を1秒ごとに保存するタイマー。所有者は編集画面。
QPointer<QTimer> timer;
/// Mayaの終了処理に入った後は、UIの破棄で「閉じた」扱いに書き換えない。
bool quittingState=false;
/// 最後にユーザーが開いた状態か。閉じた場合は次回の自動表示をしない。
bool openedState=false;
/// 明示的な表示の最中。この間のuiScript(ドック作成時)は中身の取り付けだけ行う。
bool opening=false;
/// quitApplicationのscriptJob番号。未登録は-1。
int quitJob=-1;
/// 直前に保存した状態。変化がなければ書き込まない。
QJsonObject lastState;
QString cachedControl;

/** @brief ドックと画面のタイトル。 @return 版を含むタイトル。 */
QString title() { return QStringLiteral("hedit " HEDIT_VERSION " - Python / MEL"); }
/** @brief ドックが存在するか。 @return workspaceControlがあればtrue。 */
bool exists() { return melBool("workspaceControl -exists "+melQuote(controlName())); }
/** @brief ドックのQtウィジェット。 @return 見つからなければnullptr。所有者はMaya。 */
QWidget* controlWidget() { return MQtUtil::findControl(toMString(controlName())); }
/** @brief 開閉状態の保存先。 @return tabs.jsonと同じフォルダーのui.json。 */
QString statePath() { return QFileInfo(sessionPathFunction()).dir().filePath("ui.json"); }
/** @brief 既存の編集画面を返す。作成はしない。 @return 未作成ならnullptr。 */
QMainWindow* existingEditor() { return editorFactory ? editorFactory(false) : nullptr; }
/** @brief 編集画面がドックの中に入っているか。 @param editor 対象の画面。 @return 入っていればtrue。 */
bool attached(QMainWindow* editor) {
    QWidget* control=controlWidget();
    return editor && control && control->isAncestorOf(editor);
}
/** @brief 編集画面をMayaのレイアウトへ入れる。すでに入っていれば何もしない。
 * @param editor 編集画面。
 * @param parent ドックのウィジェット、またはuiScript実行中の現在の親。
 * @return 入っている状態になればtrue。
 */
bool attach(QMainWindow* editor, QWidget* parent) {
    if (!editor || !parent) return false;
    if (parent->isAncestorOf(editor)) return true;
    // 独立ウィンドウのフラグのままだとレイアウトへ入らないため、子ウィジェットにする。
    editor->setWindowFlags(Qt::Widget);
    // 戻り値の型はMayaの版で異なる(MString等)ため、結果はQtの親子関係で確かめる。
    MQtUtil::addWidgetToMayaLayout(editor,parent);
    return parent->isAncestorOf(editor);
}
/** @brief 開閉状態の変化を追記する調査用ログ。挙動には影響しない。
 * @param event 出来事の名前。
 * @param fields 追加で記録する値。
 * @details 「再起動時に復元されない」不具合の原因を次回の発生時に確認するための仕組み。
 * 書き込めなくても他の処理は続ける。
 */
void debugLog(const QString& event, QJsonObject fields={}) {
    fields.insert("time",QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
    fields.insert("event",event);
    QFile file(QFileInfo(statePath()).dir().filePath("startup-debug.log"));
    if (file.open(QIODevice::Append|QIODevice::Text))
        file.write(QJsonDocument(fields).toJson(QJsonDocument::Compact)+"\n");
}
/** @brief ui.jsonを読む。 @param state 読み取った内容。 @return 読めた場合true。 */
bool readState(QJsonObject& state) {
    QFile file(statePath());
    if (!file.open(QIODevice::ReadOnly)) return false;
    const auto document=QJsonDocument::fromJson(file.readAll());
    if (!document.isObject()) return false;
    state=document.object();
    return true;
}
/** @brief 保存済みの開閉状態。 @return 未保存・読めない場合は明示的な復元を許可してtrue。 */
bool previousOpen() {
    QJsonObject state;
    return !readState(state) || state.value("open").toBool(true);
}
/** @brief Mayaが非表示のドックのuiScriptを呼んだ場合も、閉じた状態を保つ。 */
void hideIfClosed() {
    // uiScript直後のcloseはQt5の浮動ウィンドウを破棄し、次のrestoreで無効な
    // ネイティブハンドルを参照し得る。閉じずに非表示に留める。
    if (!openedState && exists()) mel("workspaceControl -e -visible false "+melQuote(controlName()));
}
/** @brief 表示後に、閉じる操作の通知・配置の監視・終了通知を登録する。重複はさせない。 */
void opened() {
    openedState=true;
    mel("workspaceControl -e -closeCommand \"hedit -closed\" "+melQuote(controlName()));
    if (!timer) {
        timer=new QTimer(existingEditor());
        timer->setInterval(1000);
        // 文脈をタイマー自身にし、タイマーの破棄と同時に接続を外す。
        QObject::connect(timer.data(),&QTimer::timeout,timer.data(),[] { record(); });
    }
    timer->start();
    if (quitJob<0) quitJob=melInt("scriptJob -runOnce true -event \"quitApplication\" \"hedit -quitting\"");
    debugLog("opened");
    record();
}
}

void configure(std::function<QMainWindow*(bool)> editor, std::function<QString()> sessionPath) {
    editorFactory=std::move(editor);
    sessionPathFunction=std::move(sessionPath);
    if (!guard) guard=new QObject;
}

QObject* lifetime() { return guard.data(); }

QString controlName() {
    if (cachedControl.isEmpty()) {
        cachedControl="heditDockWorkspaceControl";
        // 保存済みの旧ドックがある場合はその配置を再利用する。画面名はheditに更新する。
        if (melBool("workspaceControl -exists \"HEditorDockWorkspaceControl\"")
            && !melBool("workspaceControl -exists \"heditDockWorkspaceControl\""))
            cachedControl="HEditorDockWorkspaceControl";
    }
    return cachedControl;
}

bool show(std::optional<bool> floating) {
    if (opening) return false;
    opening=true;
    struct Reset { ~Reset() { opening=false; } } reset;
    // 本体のcloseEventでタブを保存する。取り消されたら現在の画面をそのまま残す。
    // workspaceControlは破棄せず、Mayaのドッキング配置を保つ。
    if (QMainWindow* existing=existingEditor()) { if (!existing->close()) return false; }
    QMainWindow* editor=editorFactory ? editorFactory(true) : nullptr;
    if (!editor) return false;
    editor->setWindowTitle(title());
    const QString control=melQuote(controlName());
    if (exists()) {
        mel("workspaceControl -e -label "+melQuote(title())+" "+control);
        if (floating) mel("workspaceControl -e -floating "+QString(*floating ? "true" : "false")+" "+control);
        // 旧版で別レイアウトへ入った画面も、明示的な再表示のときに修復する。
        attach(editor,controlWidget());
        // Qt5ではuiScript直後の浮動ドックにrestoreを掛けるとネイティブウィンドウの
        // 再生成で落ちる場合がある。保持中のドックを表示する。
        mel("workspaceControl -e -visible true "+control);
    } else {
        const bool floatingValue=floating.value_or(true);
        mel("workspaceControl -label "+melQuote(title())+" -retain true -loadImmediately true"
            " -floating "+QString(floatingValue ? "true" : "false")+
            " -initialWidth 1050 -initialHeight 740 -requiredPlugin \"hedit\""
            " -uiScript \"hedit -restore\" "+control);
        if (!floatingValue) mel("workspaceControl -e -dockToMainWindow \"bottom\" false "+control);
        attach(editor,controlWidget());
    }
    editor->show();
    opened();
    return true;
}

bool restore() {
    // 編集画面の作成は非表示のreporterなどMayaのUIを作り、現在の親を変える。
    // 取り付け先は作成前に決める(後で読むと非表示reporter側へ誤って入り得る)。
    // 明示的な表示でドックを作った直後(-loadImmediately)のuiScriptでは何もしない。この時点の
    // 現在の親はMayaが後で作り直すため、ここへ入れると画面ごと破棄される。取り付けは作成を
    // 終えたドックへshow()が行う。
    if (opening) return true;
    QWidget* parent=controlWidget();
    if (!parent) parent=MQtUtil::getCurrentParent();
    if (!previousOpen()) {
        // 閉じていたドックは、必要になるまで編集画面を作らない。
        QTimer::singleShot(0,guard.data(),[] { hideIfClosed(); });
        return true;
    }
    opening=true;
    struct Reset { ~Reset() { opening=false; } } reset;
    if (exists()) mel("workspaceControl -e -label "+melQuote(title())+" "+melQuote(controlName()));
    QMainWindow* editor=editorFactory(true);
    if (!editor) return false;
    if (!parent) { MGlobal::displayError("hedit workspaceControl was not found"); return false; }
    editor->setWindowTitle(title());
    attach(editor,parent);
    editor->show();
    opened();
    return true;
}

void restorePrevious() {
    if (MGlobal::mayaState()!=MGlobal::kInteractive) return;
    QJsonObject state;
    if (!readState(state) || state.value("version").toInt()!=1) return;
    const QString control=melQuote(controlName());
    const bool existing=exists();
    const bool visible=existing && melBool("workspaceControl -q -visible "+control);
    debugLog("restore_previous",{{"state",state},{"existing",existing},{"visible",visible}});
    if (!state.value("open").toBool()) { hideIfClosed(); return; }
    if (visible) {
        // Mayaのワークスペース復元(uiScriptのhedit -restore)が、表示と状態の記録まで
        // 済ませている。ここで開き直すと、閉じたときと同じcloseCommandが発火し「閉じた」
        // 記録が残り得る(再起動のたびに開かなくなる不具合の原因だった)。記録だけ行う。
        record();
        return;
    }
    if (existing) {
        // 保存済みのドックが空のまま残っている(ロード前はuiScriptが動けなかった)。ここで
        // 本体を差し込むと、表示した瞬間にMayaがuiScriptで中身を作り直して破棄する。
        // 表示だけ行い、中身はMaya自身の復元経路に作らせる。
        mel("workspaceControl -e -visible true "+control);
        if (attached(existingEditor())) { record(); return; }
    }
    const bool floating=state.value("floating").toBool(true);
    show(existing ? std::nullopt : std::optional<bool>(floating));
    if (!existing && !floating)
        MGlobal::displayWarning("hedit: saved workspace control is unavailable; docked at the bottom. Restore the saved Maya workspace for the original placement.");
    record();
}

void closed() {
    debugLog("closed",{{"quitting",quittingState},{"control_exists",exists()}});
    if (!quittingState) { openedState=false; record(); }
}

void quitting() {
    debugLog("quitting",{{"opened",openedState}});
    // ドックの入れ子・タブグループはMaya自身のワークスペースに保存する。
    // workspaceControl -stateStringは版によって空を返し、配置の復元には使えない。
    mel("workspaceLayoutManager -save");
    record();
    quittingState=true;
    if (timer) timer->stop();
}

void record() {
    if (quittingState || !exists()) return;
    const QString control=melQuote(controlName());
    const QJsonObject state{{"version",1},{"open",openedState},
        {"floating",melBool("workspaceControl -q -floating "+control)},
        {"layout",mel("workspaceLayoutManager -q -current")}};
    if (state==lastState) return;
    const QString path=statePath();
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(state).toJson(QJsonDocument::Compact))<0 || !file.commit()) {
        MGlobal::displayWarning(toMString("hedit layout could not be saved: "+file.errorString()));
        return;
    }
    lastState=state;
}

void uninstall() {
    if (!quittingState) closed();
    // deleteLaterだと、処理される前にhedit.mllがアンロードされ得る。その場で破棄する。
    delete timer.data();
    timer=nullptr;
    if (quitJob>=0 && melBool("scriptJob -exists "+QString::number(quitJob)))
        mel("scriptJob -kill "+QString::number(quitJob)+" -force");
    quitJob=-1;
}

void release() {
    if (exists()) {
        // deleteUI中のcloseCommandから配置を照会すると、Qt5では破棄中のworkspaceControlへ
        // 再入して落ちる。状態はuninstallで保存済みなので、先に通知を外す。
        const QString control=melQuote(controlName());
        mel("workspaceControl -e -closeCommand \"\" "+control);
        mel("deleteUI "+control);
    }
    // 未実行の遅延処理(hedit.mll内のラムダ)をアンロード前に取り消す。
    delete guard.data();
    guard=nullptr;
}
}
}
