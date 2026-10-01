/** @file dock.cpp
 * @brief ドッキングと開閉状態の保存・復元の実装。
 * @details 注意: ここにある手順の順番には、Mayaの版ごとの落ちる不具合を避けるための理由があるものが多い。
 * 各所のコメントの理由を確かめずに順番を入れ替えないこと(tests/run_startup.pyで確認する)。
 * 編集画面の所有者はドック(MayaのUI)なので、QPointerで生存を確かめながら使う。
 */
#include "plugin/dock.h"
#include "core/json_file.h"
#include "plugin/editor_host.h"
#include "plugin/mel.h"
#include "plugin/user_paths.h"
#include "version.h"
#include <maya/MQtUtil.h>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMainWindow>
#include <QPointer>
#include <QEvent>
#include <QTimer>

namespace hedit {
namespace dock {
namespace {

/** @brief ドックの状態。プラグインで1つだけ持つ。 */
struct DockState {
    QPointer<QObject> lifetime;   ///< 遅延実行の文脈。アンロード時に破棄して、未実行の処理を取り消す。
    QPointer<QTimer> saveTimer;   ///< ドックの変化から少し待ってui.jsonを保存するタイマー(1回だけ動く)。所有者は編集画面。
    QPointer<QObject> watcher;    ///< ドックの変化(付け替え・表示・非表示)を受け取る監視役。所有者は編集画面。
    bool quitting = false;        ///< Mayaの終了処理に入ったか。以後はUIの破棄で「閉じた」に書き換えない。
    bool userOpened = false;      ///< 最後に利用者が開いた状態か。閉じていれば次回は自動表示しない。
    bool showing = false;         ///< show()/restore()の実行中か。この間のuiScriptは何もしない。
    int quitJob = -1;             ///< quitApplicationのscriptJob番号。未登録は-1。
    QJsonObject lastSaved;        ///< 前回保存した状態。変化が無ければ書かない。
};
DockState state;

/** @brief show()/restore()の実行中の印を立て、関数を抜けるときに自動で下ろす。
 * @details C++では、ローカル変数のデストラクターは関数を抜けるとき(returnの途中も含む)に必ず呼ばれる。
 * それを使って「必ず後片付けする」書き方(RAII)。
 */
struct ShowingScope {
    /** @brief 印を立てる。 */
    ShowingScope() { state.showing = true; }
    /** @brief 印を下ろす。 */
    ~ShowingScope() { state.showing = false; }
};

/** @brief ドックの中身を作るuiScript(MEL)。
 * @details Maya起動時のワークスペース復元は、プラグインのロードより前にuiScriptを実行することがある。
 * そのときはheditコマンドが無いので、ロード済みのときだけ中身を作る。未ロードなら空のドックを非表示に戻す
 * (プラグインがロードされると、restorePrevious()がドックを表示し直し、Mayaがこのスクリプトを再び実行する)。
 * 以前はここで``loadPlugin hedit``していたが、オートロードを切っていてもMayaが勝手にロードする原因になるため
 * やめた。同じ理由で``-requiredPlugin``も付けない。
 */
constexpr const char* kUiScript =
    "if (`pluginInfo -q -loaded hedit`) hedit -restore; "
    "else evalDeferred \"if (`workspaceControl -exists heditDockWorkspaceControl`) "
    "workspaceControl -e -visible false heditDockWorkspaceControl\";";

/** @brief ドックを閉じたときのcloseCommand(MEL)。
 * @details 起動時に必要なプラグインが未ロードだと、Mayaは保存済みの浮動ドックを自動で閉じ、このコマンドを
 * 実行する。そのときheditコマンドは無いので、ロード済みのときだけ呼ぶ
 * (未ロードの間に閉じられても、記録すべき開閉状態の変化は無い)。
 */
constexpr const char* kCloseCommand = "if (`pluginInfo -q -loaded hedit`) hedit -closed;";

/** @brief ドックと画面のタイトル。 @return 版を含むタイトル。 */
QString title() {
    return QStringLiteral("hedit " HEDIT_VERSION " - Python / MEL");
}

/** @brief workspaceControlの名前をMELの文字列にしたもの。 @return 引用符付きの名前。 */
QString quotedControl() {
    return melQuote(controlName());
}

/** @brief ドックがあるか。 @return workspaceControlがあればtrue。 */
bool controlExists() {
    return melBool("workspaceControl -exists " + quotedControl());
}

/** @brief ドックのQtの部品。 @return 見つからなければnullptr。所有者はMaya。 */
QWidget* controlWidget() {
    return MQtUtil::findControl(toMString(controlName()));
}

/** @brief 開閉状態の保存先。 @return tabs.jsonと同じフォルダーのui.json。 */
QString statePath() {
    return QFileInfo(sessionFilePath()).dir().filePath("ui.json");
}

/** @brief 編集画面がドックの中に入っているか。 @param editor 対象の画面。 @return 入っていればtrue。 */
bool isAttached(QMainWindow* editor) {
    QWidget* control = controlWidget();
    return editor && control && control->isAncestorOf(editor);
}

/** @brief 編集画面をMayaのレイアウトへ入れる。すでに入っていれば何もしない。
 * @param editor 編集画面。
 * @param parent ドックの部品、またはuiScript実行中の「現在の親」。
 * @return 入っている状態になればtrue。
 */
bool attach(QMainWindow* editor, QWidget* parent) {
    if (!editor || !parent) {
        return false;
    }
    if (parent->isAncestorOf(editor)) {
        return true;
    }
    // 独立したウィンドウのままではレイアウトへ入らないので、部品(Widget)にする。
    editor->setWindowFlags(Qt::Widget);
    // 戻り値の型はMayaの版で違う(MString等)ので使わず、Qtの親子関係で確かめる。
    MQtUtil::addWidgetToMayaLayout(editor, parent);
    return parent->isAncestorOf(editor);
}

/** @brief ui.jsonを読む。 @param saved 読み取った内容を入れる。 @return 読めた場合true。 */
bool readState(QJsonObject& saved) {
    return readJsonFile(statePath(), &saved);
}

/** @brief ドックと編集画面の変化を受け取り、少し後にui.jsonを保存するよう予約する監視役。
 * @details 以前は1秒ごとにMayaへ状態(浮動か・ワークスペース名)を問い合わせていた。今は、ドックの
 * 付け替え(ドッキング・浮動の切り替え・ワークスペースの切り替え)や表示・非表示が起きたときだけ保存する。
 */
class DockWatcher : public QObject {
public:
    /** @brief 監視役を作る。 @param parent 所有者(編集画面)。 */
    explicit DockWatcher(QObject* parent) : QObject(parent) {}

protected:
    /** @brief 付け替え・表示・非表示のイベントで保存を予約する。イベントは止めない。
     * @param watched 監視している部品。
     * @param event イベント。
     * @return 常にfalse(イベントはそのまま部品へ届ける)。
     */
    bool eventFilter(QObject* watched, QEvent* event) override {
        switch (event->type()) {
        case QEvent::ParentChange:
        case QEvent::Show:
        case QEvent::Hide:
        case QEvent::WindowStateChange:
            if (state.saveTimer) {
                state.saveTimer->start();  // 続けて起きても、最後の変化の後に1回だけ保存する。
            }
            break;
        default:
            break;
        }
        return QObject::eventFilter(watched, event);
    }
};

/** @brief 前回開いていたか。 @return 開いていた、または記録が無い・読めない場合はtrue(明示的な復元を許す)。 */
bool wasOpen() {
    QJsonObject saved;
    return !readState(saved) || saved.value("open").toBool(true);
}

/** @brief 閉じた状態なのにMayaがドックを出した場合、非表示に戻す。 */
void hideIfClosed() {
    // uiScriptの直後にドックを閉じ(close)ると、Qt5では浮動ウィンドウが破棄され、次のrestoreで
    // 無効なネイティブハンドルを参照し得る。閉じずに非表示に留める。
    if (!state.userOpened && controlExists()) {
        mel("workspaceControl -e -visible false " + quotedControl());
    }
}

/** @brief 表示した後の登録(閉じる通知・変化したときの保存・終了通知)を行う。何度呼んでも重複しない。 */
void afterOpened() {
    state.userOpened = true;
    mel("workspaceControl -e -closeCommand " + melQuote(kCloseCommand) + " " + quotedControl());
    // 保存済みのドックのuiScriptが古い形でも、次回の起動でプラグインをロードしてから復元できるよう、
    // 今のuiScriptへ書き換える(何度書いても同じ)。
    mel("workspaceControl -e -uiScript " + melQuote(kUiScript) + " " + quotedControl());
    QMainWindow* editor = host::editor(false);
    if (!state.saveTimer && editor) {
        // タイマーの親を編集画面にするので、画面と一緒に破棄される。
        state.saveTimer = new QTimer(editor);
        state.saveTimer->setSingleShot(true);
        state.saveTimer->setInterval(500);
        // 接続の持ち主をタイマー自身にし、タイマーの破棄と同時に接続を外す。
        QObject::connect(state.saveTimer.data(), &QTimer::timeout, state.saveTimer.data(), [] { saveState(); });
    }
    if (!state.watcher && editor) {
        state.watcher = new DockWatcher(editor);
    }
    // ドックの部品はMayaが作り直すことがあるので、開くたびに付け直す(同じ部品へは重複しない)。
    if (state.watcher) {
        for (QObject* target : {static_cast<QObject*>(controlWidget()), static_cast<QObject*>(editor)}) {
            if (target) {
                target->removeEventFilter(state.watcher);
                target->installEventFilter(state.watcher);
            }
        }
    }
    if (state.quitJob < 0) {
        state.quitJob = melInt("scriptJob -runOnce true -event \"quitApplication\" \"hedit -quitting\"");
    }
    saveState();
}

}  // namespace

void initialize() {
    if (!state.lifetime) {
        state.lifetime = new QObject;
    }
}

QObject* lifetime() {
    return state.lifetime.data();
}

QString controlName() {
    return QStringLiteral("heditDockWorkspaceControl");
}

bool show(std::optional<bool> floating) {
    if (state.showing) {
        return false;
    }
    ShowingScope scope;

    // 開いている画面は一度閉じる(closeEventでタブを保存する)。取り消されたら、今の画面をそのまま残す。
    // workspaceControl自体は削除せず、Mayaのドッキング配置を保つ。
    if (QMainWindow* existing = host::editor(false)) {
        if (!existing->close()) {
            return false;
        }
    }

    const bool existed = controlExists();
    if (existed) {
        mel("workspaceControl -e -label " + melQuote(title()) + " " + quotedControl());
        if (floating) {
            mel("workspaceControl -e -floating " + QString(*floating ? "true" : "false") + " " + quotedControl());
        }
        // 画面を入れる前に、先に表示する。保存済みの空のドック(ロード前でuiScriptが動けなかったもの)を
        // 表示すると、MayaはuiScriptで中身を作り直し、それより前に入れた画面を破棄するため。
        // Qt5では、uiScript直後の浮動ドックにrestoreを掛けるとネイティブウィンドウの作り直しで
        // 落ちる場合がある。restoreではなく表示の切り替えを使う。
        mel("workspaceControl -e -visible true " + quotedControl());
    }

    // 画面はMayaがドックを作り直すと破棄され得るので、QPointerで生存を確かめながら使う。
    QPointer<QMainWindow> editor = host::editor(true);
    if (!editor) {
        return false;
    }
    editor->setWindowTitle(title());

    if (!existed) {
        const bool floatingValue = floating.value_or(true);  // 初回は浮動で開く。
        mel("workspaceControl -label " + melQuote(title()) + " -retain true -loadImmediately true"
            " -floating " + QString(floatingValue ? "true" : "false") +
            " -initialWidth 1050 -initialHeight 740"
            " -uiScript " + melQuote(kUiScript) + " " + quotedControl());
        if (!floatingValue) {
            mel("workspaceControl -e -dockToMainWindow \"bottom\" false " + quotedControl());
        }
    }
    // 旧版で別のレイアウトへ入った画面も、明示的に開き直したときに入れ直す。
    if (!editor || !attach(editor, controlWidget())) {
        return false;
    }
    editor->show();
    afterOpened();
    return true;
}

bool restore() {
    // 明示的な表示(show)でドックを作った直後(-loadImmediately)のuiScriptでは何もしない。
    // この時点の「現在の親」はMayaが後で作り直すため、ここへ入れると画面ごと破棄される。
    // 取り付けは、作成を終えたドックへshow()が行う。
    if (state.showing) {
        return true;
    }
    // 取り付け先は、編集画面を作る前に決める。画面の作成は非表示のreporterなどMayaのUIを作り、
    // 「現在の親」を変えるため(後で読むと非表示reporterの側へ誤って入り得る)。
    QWidget* parent = controlWidget();
    if (!parent) {
        parent = MQtUtil::getCurrentParent();
    }
    if (!wasOpen()) {
        // 閉じていたドックは、必要になるまで編集画面を作らない。非表示にするのはuiScriptの処理の後。
        QTimer::singleShot(0, state.lifetime.data(), [] { hideIfClosed(); });
        return true;
    }
    ShowingScope scope;
    if (controlExists()) {
        mel("workspaceControl -e -label " + melQuote(title()) + " " + quotedControl());
    }
    QPointer<QMainWindow> editor = host::editor(true);
    if (!editor) {
        return false;
    }
    if (!parent) {
        MGlobal::displayError("hedit workspaceControl was not found");
        return false;
    }
    editor->setWindowTitle(title());
    if (!attach(editor, parent) || !editor) {
        return false;
    }
    editor->show();
    afterOpened();
    return true;
}

void restorePrevious() {
    if (MGlobal::mayaState() != MGlobal::kInteractive) {
        return;
    }
    QJsonObject saved;
    if (!readState(saved) || saved.value("version").toInt() != 1) {
        return;
    }
    const bool existing = controlExists();
    const bool visible = existing && melBool("workspaceControl -q -visible " + quotedControl());
    if (!saved.value("open").toBool()) {
        hideIfClosed();
        return;
    }
    if (visible) {
        // Mayaのワークスペース復元(uiScriptの hedit -restore)が、表示と状態の記録まで済ませている。
        // ここで開き直すと、閉じたときと同じcloseCommandが動いて「閉じた」記録が残り得る
        // (再起動のたびに開かなくなる不具合の原因だった)。記録だけ行う。
        saveState();
        return;
    }
    if (existing) {
        // 保存済みのドックが空のまま残っている(ロード前はuiScriptが動けなかった)。ここで画面を入れると、
        // 表示した瞬間にMayaがuiScriptで中身を作り直して破棄する。表示だけ行い、中身はMayaの復元に作らせる。
        mel("workspaceControl -e -visible true " + quotedControl());
        if (isAttached(host::editor(false))) {
            saveState();
            return;
        }
    }
    const bool floating = saved.value("floating").toBool(true);
    show(existing ? std::nullopt : std::optional<bool>(floating));
    if (!existing && !floating) {
        MGlobal::displayWarning("hedit: saved workspace control is unavailable; docked at the bottom. "
                                "Restore the saved Maya workspace for the original placement.");
    }
    saveState();
}

void onClosed() {
    if (!state.quitting) {
        state.userOpened = false;
        saveState();
    }
}

void onQuitting() {
    // ドックの入れ子・タブの組み合わせは、Maya自身が終了時にワークスペースへ保存する。
    // 以前はここで workspaceLayoutManager -save を呼んでいたが、プラグインがMayaの設定を書き換えるのは
    // やめた(ワークスペースの保存は利用者とMayaの設定に任せる)。
    saveState();
    state.quitting = true;
    if (state.saveTimer) {
        state.saveTimer->stop();
    }
}

void saveState() {
    if (state.quitting || !controlExists()) {
        return;
    }
    const QJsonObject current{
        {"version", 1},
        {"open", state.userOpened},
        {"floating", melBool("workspaceControl -q -floating " + quotedControl())},
        {"layout", mel("workspaceLayoutManager -q -current")},
    };
    if (current == state.lastSaved) {
        return;
    }
    QString error;
    if (!writeJsonFile(statePath(), current, &error)) {
        MGlobal::displayWarning(toMString("hedit layout could not be saved: " + error));
        return;
    }
    state.lastSaved = current;
}

void uninstall() {
    if (!state.quitting) {
        onClosed();
    }
    // deleteLaterだと、実際に破棄される前にhedit.mllがアンロードされ得る。その場で破棄する。
    delete state.saveTimer.data();
    state.saveTimer = nullptr;
    delete state.watcher.data();
    state.watcher = nullptr;
    if (state.quitJob >= 0 && melBool("scriptJob -exists " + QString::number(state.quitJob))) {
        mel("scriptJob -kill " + QString::number(state.quitJob) + " -force");
    }
    state.quitJob = -1;
}

void release() {
    if (controlExists()) {
        // deleteUIの途中のcloseCommandから配置を問い合わせると、Qt5では破棄中のworkspaceControlへ
        // 再入して落ちる。状態はuninstall()で保存済みなので、先に通知を外す。
        mel("workspaceControl -e -closeCommand \"\" " + quotedControl());
        mel("deleteUI " + quotedControl());
    }
    // 未実行の遅延処理(hedit.mll内のラムダ)を、アンロード前に取り消す。
    delete state.lifetime.data();
    state.lifetime = nullptr;
}

}  // namespace dock
}  // namespace hedit
