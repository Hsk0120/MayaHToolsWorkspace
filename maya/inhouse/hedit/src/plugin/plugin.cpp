/** @file plugin.cpp
 * @brief プラグインの入口。Mayaがロード時にinitializePlugin、アンロード時にuninitializePluginを呼ぶ。
 * @details ロードの流れ:
 * 1. ``hedit``コマンドを登録する(hedit_command.cpp)。
 * 2. 同梱のPython(補完・構文チェック用)をimportできるようにする(embedded_python.cpp)。
 * 3. GUIのMayaなら: 終了の通知を登録し、Windowメニューに項目を足し(window_menu.cpp)、
 *    前回開いていた画面を復元する(dock.cpp)。
 * ``scripts/userSetup.py``(起動時にloadPluginを呼ぶだけ)・Plug-in Managerでのロード・autoloadの
 * どれでもここが呼ばれるので、プラグインのロードだけで準備が終わる。
 */
#include "plugin/dock.h"
#include "plugin/editor_host.h"
#include "plugin/embedded_python.h"
#include "plugin/hedit_command.h"
#include "plugin/output_capture.h"
#include "plugin/python_bridge.h"
#include "plugin/window_menu.h"
#include "version.h"
#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MSceneMessage.h>
#include <QTimer>

namespace {

/// Maya終了の通知(kMayaExiting)のコールバック。未登録は0。
MCallbackId exitCallback = 0;

/** @brief GUIのMayaか(バッチやmayapyではない)。 @return GUIならtrue。 */
bool isInteractive() {
    return MGlobal::mayaState() == MGlobal::kInteractive;
}

/** @brief Mayaの終了が始まったときに呼ばれる。以後の出力を画面へ渡さない。
 * @param clientData 未使用。
 */
void onMayaExiting(void* clientData) {
    Q_UNUSED(clientData);
    hedit::outputCapture().stopForExit();
}

}  // namespace

/** @brief プラグインのロード時にMayaが呼ぶ。
 * @param object Mayaのプラグインオブジェクト。
 * @return コマンドの登録と、同梱Pythonの準備の結果。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "hedit", HEDIT_VERSION, "Any");
    MStatus status = plugin.registerCommand(hedit::HeditCommand::kName, hedit::HeditCommand::creator,
                                            hedit::HeditCommand::newSyntax);
    if (!status) {
        return status;
    }
    // importフックはmayapy(GUIなし)でも登録する。補完などのPython APIはGUIに依存しないため。
    status = hedit::embedded::installModules();
    if (!status) {
        MGlobal::displayError("hedit: failed to install embedded Python modules.");
        plugin.deregisterCommand(hedit::HeditCommand::kName);
        return status;
    }
    if (isInteractive()) {
        hedit::outputCapture().resetExitState();
        exitCallback = MSceneMessage::addCallback(MSceneMessage::kMayaExiting, onMayaExiting);
        hedit::dock::initialize();
        hedit::installWindowMenu();
        // ロードの処理中に画面を作り始めないよう、前回の画面の復元は次のイベントループへ送る。
        QTimer::singleShot(0, hedit::dock::lifetime(), [] { hedit::dock::restorePrevious(); });
    }
    return status;
}

/** @brief プラグインのアンロード時にMayaが呼ぶ。タブを保存し、通知・UI・コマンドを解除する。
 * @param object Mayaのプラグインオブジェクト。
 * @return 解除の結果。未保存の確認でキャンセルされたらkFailure(アンロードしない)。
 * @note 順番に意味がある。コールバックを先に外し、破棄済みの画面へ通知が届かないようにする。
 * 別スレッド・遅延実行のコードもhedit.mllの中にあるので、アンロード前に必ず止める。
 */
MStatus uninitializePlugin(MObject object) {
    // 1. タブを保存して画面を閉じる。保存できず確認でキャンセルされたら、アンロードをやめる。
    if (!hedit::host::closeEditor()) {
        return MS::kFailure;
    }
    // 2. メニュー項目・1秒ごとの保存・終了通知のscriptJobを外す。
    if (isInteractive()) {
        hedit::uninstallWindowMenu();
        hedit::dock::uninstall();
    }
    // 3. 出力の購読と非表示のreporterを外す。
    MStatus status = hedit::outputCapture().stop();
    if (!status) {
        return status;
    }
    if (exitCallback) {
        MMessage::removeCallback(exitCallback);
        exitCallback = 0;
    }
    // 4. importの補完の走査スレッドを止める。
    hedit::python::stopModuleScan();
    // 5. ドックを削除し、未実行の遅延処理を取り消す。
    if (isInteractive()) {
        hedit::dock::release();
    }
    // 6. 画面を破棄し、残った出力を捨てる。
    hedit::host::destroyEditor();
    hedit::outputCapture().take();

    MFnPlugin plugin(object);
    return plugin.deregisterCommand(hedit::HeditCommand::kName);
}
