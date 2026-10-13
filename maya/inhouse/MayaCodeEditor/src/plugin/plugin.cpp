/** @file plugin.cpp
 * @brief プラグインの入口。Mayaがロード時にinitializePlugin、アンロード時にuninitializePluginを呼ぶ。
 * @details ロードの流れ:
 * 1. ``mayaCodeEditor``コマンドを登録する(editor_command.cpp)。テスト用の環境変数があれば``mayaCodeEditorTest``も(test_command.cpp)。
 * 2. プラグイン全体で1つの状態を作る: 出力の取り込み(output_capture.cpp)→ Pythonとの受け渡し(python_bridge.cpp)。
 * 3. 同梱のPython(補完・構文チェック用)をimportできるようにする(embedded_python.cpp)。
 * 4. GUIのMayaなら: 終了の通知を登録し、ドックの状態を作り(dock.cpp)、Windowメニューに項目を足し(window_menu.cpp)、
 *    前回開いていた画面を復元する(dock.cpp)。
 * アンロードでは逆の順番で壊す(uninitializePluginの番号付きのコメント)。
 * ``scripts/userSetup.py``(起動時にloadPluginを呼ぶだけ)・Plug-in Managerでのロード・autoloadの
 * どれでもここが呼ばれるので、プラグインのロードだけで準備が終わる。
 */
#include "plugin/dock.h"
#include "plugin/editor_host.h"
#include "plugin/embedded_python.h"
#include "plugin/editor_command.h"
#include "plugin/mel.h"
#include "plugin/output_capture.h"
#include "plugin/python_bridge.h"
#include "plugin/test_command.h"
#include "plugin/window_menu.h"
#include "version.h"
#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MSceneMessage.h>

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
    mce::outputCapture().stopForExit();
}

}  // namespace

/** @brief プラグインのロード時にMayaが呼ぶ。
 * @param object Mayaのプラグインオブジェクト。
 * @return コマンドの登録と、同梱Pythonの準備の結果。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "mayaCodeEditor", MCE_VERSION, "Any");
    MStatus status = plugin.registerCommand(mce::EditorCommand::kName, mce::EditorCommand::creator,
                                            mce::EditorCommand::newSyntax);
    if (!status) {
        return status;
    }
    // テスト専用のコマンドは、テスト用の環境変数があるときだけ登録する(普段のMayaには出さない)。
    if (mce::EditorTestCommand::enabled()) {
        plugin.registerCommand(mce::EditorTestCommand::kName, mce::EditorTestCommand::creator,
                               mce::EditorTestCommand::newSyntax);
    }
    // プラグインで1つだけの状態を、決まった順番で作る(壊すのはuninitializePluginで逆の順番)。
    mce::createOutputCapture();
    mce::python::initialize();
    // importフックはmayapy(GUIなし)でも登録する。補完などのPython APIはGUIに依存しないため。
    status = mce::embedded::installModules();
    if (!status) {
        MGlobal::displayError("Maya Code Editor: failed to install embedded Python modules.");
        plugin.deregisterCommand(mce::EditorCommand::kName);
        if (mce::EditorTestCommand::enabled()) {
            plugin.deregisterCommand(mce::EditorTestCommand::kName);
        }
        mce::python::shutdown();
        mce::destroyOutputCapture();
        return status;
    }
    if (isInteractive()) {
        mce::outputCapture().resetExitState();
        exitCallback = MSceneMessage::addCallback(MSceneMessage::kMayaExiting, onMayaExiting);
        mce::dock::initialize();
        mce::installWindowMenu();
        // ロードの処理中に画面を作り始めないよう、前回の画面の復元は後へ送る。起動時は、ワークスペースの復元で
        // プラグインより先に動いたuiScriptが「空のドックを隠す」をevalDeferredで予約していることがある。
        // 次のイベントループ(QTimer)ではその前に動いて、復元した画面が後から隠されることがあった。
        // Mayaの遅延実行の最後(-lowestPriority)へ回し、予約済みの処理の後に復元する。
        // 実行までにアンロードされた場合に備え、ロード済みのときだけ呼ぶ。
        mce::mel("evalDeferred -lowestPriority "
                 "\"if (`pluginInfo -q -loaded mayaCodeEditor`) mayaCodeEditor -restorePrevious\"");
    }
    return status;
}

/** @brief プラグインのアンロード時にMayaが呼ぶ。タブを保存し、通知・UI・コマンドを解除する。
 * @param object Mayaのプラグインオブジェクト。
 * @return 解除の結果。未保存の確認でキャンセルされたらkFailure(アンロードしない)。
 * @note 順番に意味がある。コールバックを先に外し、破棄済みの画面へ通知が届かないようにする。
 * 別スレッド・遅延実行のコードもmayaCodeEditor.mllの中にあるので、アンロード前に必ず止める。
 */
MStatus uninitializePlugin(MObject object) {
    // 1. タブを保存して画面を閉じる。保存できず確認でキャンセルされたら、アンロードをやめる。
    if (!mce::host::closeEditor()) {
        return MS::kFailure;
    }
    // 2. メニュー項目・1秒ごとの保存・終了通知のscriptJobを外す。
    if (isInteractive()) {
        mce::uninstallWindowMenu();
        mce::dock::uninstall();
    }
    // 3. 出力の購読と非表示のreporterを外す。
    MStatus status = mce::outputCapture().stop();
    if (!status) {
        return status;
    }
    if (exitCallback) {
        MMessage::removeCallback(exitCallback);
        exitCallback = 0;
    }
    // 4. 補完の状態を壊す(importの補完の走査スレッドを止めて合流する)。
    mce::python::shutdown();
    // 5. ドックを削除し、未実行の遅延処理を取り消す。
    if (isInteractive()) {
        mce::dock::release();
    }
    // 6. 画面を破棄し、残った出力を捨てる。
    mce::host::destroyEditor();
    mce::outputCapture().take();
    // 7. 出力の取り込みを壊す(購読は3.で外してある)。
    mce::destroyOutputCapture();

    MFnPlugin plugin(object);
    if (mce::EditorTestCommand::enabled()) {
        plugin.deregisterCommand(mce::EditorTestCommand::kName);
    }
    return plugin.deregisterCommand(mce::EditorCommand::kName);
}
