/** @file editor_host.cpp
 * @brief 編集画面の作成と、Mayaの処理との接続。
 */
#include "plugin/editor_host.h"
#include "editor/editor.h"
#include "editor/ui_scale.h"
#include "plugin/mel.h"
#include "plugin/output_capture.h"
#include "plugin/python_bridge.h"
#include "plugin/user_paths.h"
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <QPointer>

namespace hedit {
namespace host {
namespace {

/// 編集画面。所有者はMayaのドック。破棄されると自動でnullptrになる。
QPointer<QMainWindow> window;

/** @brief Mayaの画面の拡大率とアイコンを、これから作る編集画面へ設定する。 */
void applyMayaAppearance() {
    // Maya標準のScript Editorと同じ基準で、4K等の拡大率(Interface Scaling)を寸法に掛ける。
    // MayaはQt自体の高DPI拡大を止めているため、固定のピクセル数はそのままでは大きくならない。
    setUiScale(MQtUtil::dpiScale(1.0f));
    // Qtの":/名前"は拡大率に関係なく20pxの画像しか返さない。MQtUtil::createIconは拡大率に合った
    // 高解像度の画像を返す(200%なら40px)。返されたQIconは呼出側が所有するので、写してからdeleteする。
    setIconProvider([](const QString& name) {
        QIcon* raw = MQtUtil::createIcon(toMString(name));
        if (!raw) {
            return QIcon(":/" + name);
        }
        QIcon icon(*raw);
        delete raw;
        return icon;
    });
}

/** @brief 編集画面へ渡す、Mayaの処理の一式を作る。 @return EditorServices。 */
EditorServices mayaServices() {
    EditorServices services;
    services.runPython = [](const QString& source, const QString& path) { return python::runPython(source, path); };
    services.runMel = python::runMel;
    services.refreshCompletion = python::refreshCompletion;
    services.complete = python::complete;
    services.describe = python::describe;
    services.definition = python::definition;
    services.analyze = python::analyze;
    services.takeOutput = [] { return outputCapture().take(); };
    services.sessionPath = sessionFilePath();
    return services;
}

}  // namespace

QMainWindow* editor(bool create) {
    if (window || !create) {
        return window.data();
    }
    if (MGlobal::mayaState() != MGlobal::kInteractive) {
        MGlobal::displayError("hedit UI requires interactive Maya.");
        return nullptr;
    }
    // 起動前からの出力を取り込み、以後の出力の購読を始める(2回目以降は何もしない)。
    if (!outputCapture().start()) {
        return nullptr;
    }
    applyMayaAppearance();
    window = createEditor(MQtUtil::mainWindow(), mayaServices());
    // ドックの中で探せるよう名前を付ける(テストや旧版の回収処理が使う)。
    window->setObjectName("hedit");
    outputCapture().setEditor(window.data());
    // importの補完に使うsys.pathの走査を先に始め、最初のCtrl+Spaceまでに終えておく。
    python::startModuleScan();
    return window.data();
}

bool closeEditor() {
    if (!window) {
        return true;
    }
    // closeは、MainWindow::closeEventで自動保存(または確認)をしてから閉じる。
    return window->close();
}

void destroyEditor() {
    delete window.data();
    window = nullptr;
}

}  // namespace host
}  // namespace hedit
