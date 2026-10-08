/** @file editor_host.cpp
 * @brief 編集画面の作成と、Mayaの処理との接続。
 */
#include "plugin/editor_host.h"
#include "core/json_file.h"
#include "editor/editor.h"
#include "editor/editor_preferences.h"
#include "editor/ui_scale.h"
#include "plugin/mel.h"
#include "plugin/output_capture.h"
#include "plugin/python_bridge.h"
#include "plugin/user_paths.h"
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <QFileInfo>
#include <QJsonObject>
#include <QPointer>
#include <QTimer>

namespace hedit {
namespace host {
namespace {

/// 編集画面。所有者はMayaのドック。破棄されると自動でnullptrになる。
QPointer<QMainWindow> window;

/// 編集画面を作ってから、importの補完に使うsys.pathの走査を始めるまでの時間(ミリ秒)。
/// 画面の表示・ドッキング(同じイベントの処理の中で続けて行われる)を先に終えるための待ち時間。
constexpr int kModuleScanDelay = 1000;

/** @brief 出力の取り込みを正確な方式(Exact Script Editor output format)にする設定か。
 * @return 編集画面と同じpreferences.jsonで、その設定がオンならtrue。保存先が無い・読めない場合はfalse(初期値)。
 * @details 保存先は1回だけ求め、preferences.jsonはその1項目だけを読む(EditorPreferencesを作ると、
 * 設定の表の組み立てと旧形式の移行の確認も行うため)。
 */
bool exactOutputPreferred() {
    const QString sessionPath = sessionFilePath();
    QJsonObject saved;
    return !sessionPath.isEmpty() && readJsonFile(QFileInfo(sessionPath).absolutePath() + "/preferences.json", &saved)
           && saved.value(option::kExactOutput).toBool(false);
}

/** @brief importの補完に使うsys.pathの走査を、画面を開き終えてから始めるよう予約する。
 * @details 開く処理の中でPythonへの問い合わせとスレッドの開始をしない。閉じた画面(アンロードの最初に閉じる)
 * では始めない。走査を始めていなければ、最初のimportの補完が自分で始める(python::complete)。
 * @note 予約は画面の子のタイマーで行い、画面と一緒に破棄されるようにする。``QTimer::singleShot(時間, 文脈, ラムダ)``
 * は、文脈が破棄されても時間が来るまでQtの中に残り、そのときhedit.mllの中のラムダを片付けようとするため、
 * 先にアンロードされると落ちる(Maya 2024のQt5で確認)。
 */
void scheduleModuleScan() {
    auto timer = new QTimer(window.data());  // 所有者は画面。
    timer->setSingleShot(true);
    // 接続の持ち主をタイマー自身にするので、画面(とタイマー)の破棄と同時に接続も外れる。
    QObject::connect(timer, &QTimer::timeout, timer, [] {
        if (window && window->isVisible()) {
            python::startModuleScan();
        }
    });
    timer->start(kModuleScanDelay);
}

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
    services.setExactOutput = [](bool exact) {
        outputCapture().setMode(exact ? OutputCapture::Mode::Exact : OutputCapture::Mode::Fast);
    };
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
    // 取り込み方は、編集画面と同じpreferences.jsonの設定(Exact Script Editor output format)に従う。
    const bool exact = exactOutputPreferred();
    outputCapture().setMode(exact ? OutputCapture::Mode::Exact : OutputCapture::Mode::Fast);
    if (!outputCapture().start()) {
        return nullptr;
    }
    applyMayaAppearance();
    window = createEditor(MQtUtil::mainWindow(), mayaServices());
    // ドックの中で探せるよう名前を付ける(テストや旧版の回収処理が使う)。
    window->setObjectName("hedit");
    outputCapture().setEditor(window.data());
    // importの補完に使うsys.pathの走査を、画面を開き終えてから始め、最初のCtrl+Spaceまでに終えておく。
    scheduleModuleScan();
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
