/** @file native_plugin.cpp @brief Pythonを内蔵しないMayaプラグインの寿命境界。 */
#include "maya_host.h"
#include "../browser/browser_window.h"
#include "../core/directory_store.h"
#include "../core/file_operations.h"
#include "../core/settings_store.h"
#include "../native_browser.h"
#include "../product.h"
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <maya/MSceneMessage.h>
#include <maya/MMessage.h>
#include <maya/MCallbackIdArray.h>
#include <QApplication>
#include <QAction>
#include <QIcon>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonArray>
#include <QPointer>
#include <QScreen>
#include <QScrollArea>
#include <QTimer>
#include <stdexcept>
namespace {
const char* control = QPE_CONTROL;
QPointer<qpe::BrowserWindow> browser;
QPointer<QScrollArea> viewport;
MCallbackIdArray callbacks;
bool building = false;
bool quitting = false;
bool removing = false;
bool userOpened = false;
int closeGeneration = 0;
QPointer<QObject> lifetime;
QPointer<QTimer> dockTimer;
QJsonObject lastDock;
/** @brief UTF-8を保持する。 @param text 値。 @return Maya文字列。 */
MString ms(const QString& text) { MString result; result.setUTF8(text.toUtf8().constData()); return result; }
/** @brief workspaceの有無。 @return 存在するか。 */
bool exists() { int result = 0; MGlobal::executeCommand(MString("workspaceControl -exists ") + control, result); return result != 0; }
/** @brief 版ごとの保存キー。旧Pythonの設定を直接引き継ぐ。 @return 設定名。 */
QString dockKey() { return "mayaDock" + QString::fromUtf8(MGlobal::mayaVersion().asUTF8()).left(4); }
/** @brief 明示開閉と浮動位置を保存し、ドックの入れ子はMaya自身に任せる。 */
void saveDock() {
    if (quitting || removing || building || !browser || !exists()) return;
    try {
        int floating = 1; MGlobal::executeCommand(MString("workspaceControl -q -floating ") + control, floating);
        auto value = qpe::readSettings()[dockKey()].toObject(); value.remove("state");
        value["open"] = userOpened; value["floating"] = bool(floating);
        if (floating) {
            auto* parent = MQtUtil::findControl(control);
            if (parent && parent->window() != MQtUtil::mainWindow()) {
                const auto rect = parent->window()->normalGeometry();
                if (rect.isValid()) value["geometry"] = QJsonArray{rect.x(), rect.y(), rect.width(), rect.height()};
            }
        }
        if (value != lastDock) { qpe::writeSettings({{dockKey(), value}}); lastDock = value; }
    } catch (const std::exception& e) { MGlobal::displayWarning(ms("QPE layout not saved: " + QString::fromUtf8(e.what()))); }
}
/** @brief 浮動ウィンドウだけに前回位置を適用。画面外なら見える領域へ戻す。 @param value 保存状態。 */
void restoreGeometry(const QJsonObject& value) {
    if (!browser || !exists()) return;
    int floating = 1; MGlobal::executeCommand(MString("workspaceControl -q -floating ") + control, floating);
    if (!floating) return;
    const auto geometry = value["geometry"].toArray(); if (geometry.size() != 4) return;
    QRect rect(geometry[0].toInt(), geometry[1].toInt(), geometry[2].toInt(), geometry[3].toInt());
    if (!rect.isValid()) return;
    QScreen* screen = nullptr;
    for (auto* candidate : QApplication::screens()) if (candidate->availableGeometry().intersects(rect)) { screen = candidate; break; }
    if (!screen) { screen = QApplication::primaryScreen(); if (screen) rect.moveTopLeft(screen->availableGeometry().topLeft() + QPoint(40, 40)); }
    if (!screen) return;
    const auto area = screen->availableGeometry(); rect.setSize(rect.size().boundedTo(area.size()).expandedTo(QSize(240, 160)));
    rect.moveLeft(qBound(area.left(), rect.left(), qMax(area.left(), area.right() - rect.width() + 1)));
    rect.moveTop(qBound(area.top(), rect.top(), qMax(area.top(), area.bottom() - rect.height() + 1)));
    auto* parent = MQtUtil::findControl(control);
    if (parent && parent->window() != MQtUtil::mainWindow()) parent->window()->setGeometry(rect);
}
/** @brief Maya所有のドックへ自分の画面だけを取り付ける。 @param restore uiScriptからの復元か。 */
void show(bool restore = false) {
    if (building) return;
    building = true;
    try {
        const auto previous = qpe::readSettings()[dockKey()].toObject();
        if (restore && !previous["open"].toBool(true)) {
            QTimer::singleShot(0, lifetime, [] { try { if (!userOpened && exists()) qpe::mayaCommand(QString("workspaceControl -e -visible false ") + control); } catch (const std::exception& e) { MGlobal::displayWarning(e.what()); } });
            building = false; return;
        }
        const bool existed = exists();
        const QString script = "if (`exists " QPE_COMMAND "`) " QPE_COMMAND " -restore; else evalDeferred \"if (!`exists " QPE_COMMAND "` && `workspaceControl -exists " + QString(control) + "`) workspaceControl -e -visible false " + control + "\";";
        if (!existed) {
            qpe::mayaCommand(QString("workspaceControl -label \"" QPE_LABEL "\" -floating true -retain true -loadImmediately true -initialWidth 1200 -initialHeight 800 -uiScript ") + qpe::melQuote(script) + ' ' + control);
            if (!previous["floating"].toBool(true)) qpe::mayaCommand(QString("workspaceControl -e -dockToMainWindow right false ") + control);
        } else if (!restore) {
            // Qt5ではrestore直後にフロート親が再生成される。表示を先に済ませてから中身を付ける。
            qpe::mayaCommand(QString("workspaceControl -e -visible true ") + control);
        }
        auto* parent = MQtUtil::findControl(control);
        if (!parent) throw std::runtime_error("Maya workspaceControl is unavailable");
        if (!browser || !parent->isAncestorOf(browser)) {
            if (viewport) delete viewport.data();
            viewport = new QScrollArea; viewport->setObjectName("qpeNativeDockViewport"); viewport->setWidgetResizable(true);
            viewport->setMinimumSize(240, 160); viewport->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
            browser = new qpe::BrowserWindow(viewport, qpe::mayaServices());
            browser->setMinimumSize(360, 260); viewport->setWidget(browser);
            MQtUtil::addWidgetToMayaLayout(viewport, parent);
            browser->restoreSession(qpe::mayaServices().projectPath());
            browser->show();
        }
        userOpened = true;
        ++closeGeneration;
        qpe::mayaCommand(QString("workspaceControl -e -closeCommand ") + qpe::melQuote(QString("if (`exists " QPE_COMMAND "`) " QPE_COMMAND " -closed %1;").arg(closeGeneration)) + " -uiScript " + qpe::melQuote(script) + ' ' + control);
        if (!dockTimer) { dockTimer = new QTimer(lifetime); dockTimer->setInterval(750); QObject::connect(dockTimer.data(), &QTimer::timeout, dockTimer.data(), [] { saveDock(); }); }
        dockTimer->start();
        if (!existed) QTimer::singleShot(0, browser, [previous] { restoreGeometry(previous); saveDock(); });
        building = false;
        saveDock();
    } catch (...) { building = false; throw; }
}
/** @brief 終了時のQt破棄より前に状態を固定する。 @param data 未使用。 */
void beforeQuit(void* data) {
    saveDock(); quitting = true; if (dockTimer) dockTimer->stop();
    if (browser) browser->prepareHostShutdown();
    // MayaがQtを破棄する前に、自分の内容だけを破棄する。workspaceControlは配置保存のため残す。
    if (viewport) delete viewport.data();
}
/** @brief シーン完了後だけ現在シーンのフォルダーへ追従する。 @param data 未使用。 */
void afterOpen(void* data) {
    if (!browser) return;
    QTimer::singleShot(0, browser, [] {
        try { if (browser) { const auto scene = qpe::mayaServices().scenePath(); if (!scene.isEmpty()) browser->navigate(QFileInfo(scene).absolutePath()); } }
        catch (const std::exception& e) { MGlobal::displayWarning(ms("QuickPathExplorer: " + QString::fromUtf8(e.what()))); }
    });
}
/** @brief テスト可能な起動入口。MayaのUndoへファイル履歴を混ぜない。 */
class Command final : public MPxCommand {
public:
    /** @brief Mayaへ所有権を渡す。 @return 新規コマンド。 */
    static void* creator() { return new Command; }
    /** @brief 起動/復元/専用検証コマンド。 @param args 引数。 @return Maya結果。 */
    MStatus doIt(const MArgList& args) override {
        try {
            const QString option = args.length() ? QString::fromUtf8(args.asString(0).asUTF8()) : QString();
            if (option == "-closed") {
                if (!quitting && !removing && args.length() == 2 && args.asInt(1) == closeGeneration) {
                    // deleteUI中のMaya/Qtへ再入しない。直前に保持した値の開閉だけを書き換える。
                    userOpened = false; auto value = lastDock; value["open"] = false;
                    qpe::writeSettings({{dockKey(), value}}); lastDock = value;
                }
                return MS::kSuccess;
            }
            if (option == "-saveLayout") { saveDock(); return MS::kSuccess; }
            if (option == "-startup") {
                if (qpe::readSettings()[dockKey()].toObject()["open"].toBool(false)) show();
                return MS::kSuccess;
            }
            if (option == "-status") { setResult(browser ? browser->currentPath().toUtf8().constData() : ""); return MS::kSuccess; }
            if (option == "-invoke" && args.length() == 4) {
                qpe::mayaPerform(QString::fromUtf8(args.asString(1).asUTF8()), {QString::fromUtf8(args.asString(2).asUTF8())}, QJsonDocument::fromJson(args.asString(3).asUTF8()).object()); return MS::kSuccess;
            }
            show(option == "-restore");
            if (option == "-path" && args.length() == 2) browser->navigate(QString::fromUtf8(args.asString(1).asUTF8()));
            if (option == "-refresh") browser->refresh();
            return MS::kSuccess;
        } catch (const std::exception& error) { MGlobal::displayError(error.what()); return MS::kFailure; }
    }
};
}
/** @brief ホストコールバックとMELコマンドを登録。 @param object プラグイン。 @return 結果。 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "HTools", QPE_VERSION, "Any");
    auto status = plugin.registerCommand(QPE_COMMAND, Command::creator); if (!status) return status;
    quitting = false; removing = false; userOpened = false; building = false; lastDock = {}; lifetime = new QObject;
    callbacks.append(MSceneMessage::addCallback(MSceneMessage::kAfterOpen, afterOpen));
    callbacks.append(MSceneMessage::addCallback(MSceneMessage::kMayaExiting, beforeQuit));
    // Mayaの起動途中のQtイベント処理より後に復元する。解除後はコマンドの存在確認だけで終わる。
    if (MGlobal::mayaState() == MGlobal::kInteractive)
        MGlobal::executeCommandOnIdle("if (`exists " QPE_COMMAND "`) " QPE_COMMAND " -startup;", false);
    // Maya起動中は標準メニューがまだ無い場合がある。所有タイマーで再試行し、解除時に必ず破棄する。
    auto* menuTimer = new QTimer(lifetime); menuTimer->setInterval(500);
    QObject::connect(menuTimer, &QTimer::timeout, menuTimer, [menuTimer, attempts = 0]() mutable {
        if (quitting || removing) { menuTimer->stop(); return; }
        try {
            int ready = 0; MGlobal::executeCommand("menu -exists \"MayaWindow|mainWindowMenu\"", ready);
            if (!ready) { if (++attempts >= 120) menuTimer->stop(); return; }
            qpe::mayaCommand("if (!`menuItem -exists " QPE_MENU "`) { buildViewMenu MayaWindow|mainWindowMenu; menuItem -parent \"MayaWindow|mainWindowMenu\" -label \"" QPE_LABEL "\" -sourceType mel -command \"" QPE_COMMAND "\" " QPE_MENU "; }");
            if (auto* action = MQtUtil::findMenuItem(QPE_MENU)) { action->setIcon(QIcon(":/qpe/icons/quickPathExplorer.png")); menuTimer->stop(); }
        } catch (const std::exception& e) { menuTimer->stop(); MGlobal::displayWarning(e.what()); }
    });
    menuTimer->start();
    return MS::kSuccess;
}
/** @brief 生存ワーカーがない場合だけ自分のUI/コールバックを破棄。 @param object プラグイン。 @return 結果。 */
MStatus uninitializePlugin(MObject object) {
    if ((browser && browser->busy()) || qpe::FileJobs::liveWorkers()) {
        MGlobal::displayWarning("QuickPathExplorer workers are still alive. Close QPE and retry after they finish."); return MS::kFailure;
    }
    saveDock(); removing = true;
    if (dockTimer) dockTimer->stop();
    try { if (exists()) qpe::mayaCommand(QString("workspaceControl -e -closeCommand \"\" ") + control); } catch (...) {}
    if (browser) browser->close();
    if (viewport) delete viewport.data();
    // 画面の破棄で列挙要求を失効させる。ワーカーの終了前はDLLを解放しない。
    if (!qpe::DirectoryStore::releaseWorkers() || !qpe::FileJobs::releaseWorkers() || !qpe::nativeObjectsReleased()) { removing = false; return MS::kFailure; }
    MMessage::removeCallbacks(callbacks); callbacks.clear();
    try { if (exists()) qpe::mayaCommand(QString("deleteUI ") + control); qpe::mayaCommand("if (`menuItem -exists " QPE_MENU "`) deleteUI " QPE_MENU); } catch (...) {}
    if (!qpe::nativeObjectsReleased()) return MS::kFailure;
    delete lifetime.data(); lifetime = nullptr;
    MFnPlugin plugin(object); return plugin.deregisterCommand(QPE_COMMAND);
}
