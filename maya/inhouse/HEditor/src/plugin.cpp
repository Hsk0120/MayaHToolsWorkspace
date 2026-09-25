#include "editor.h"
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <maya/MCommandMessage.h>
#include <maya/MMessage.h>
#include <QMutex>
#include <QMutexLocker>
#include <QJsonDocument>
#include <QJsonArray>
#include <QPointer>

namespace {
QPointer<QMainWindow> window;
MCallbackId outputCallback = 0;
QMutex outputMutex;
QString pendingOutput;
void onOutput(const MString& message, MCommandMessage::MessageType type, void*) {
    QString text = QString::fromUtf8(message.asUTF8());
    if (type == MCommandMessage::kWarning) text.prepend("// Warning: ");
    if (type == MCommandMessage::kError) text.prepend("// Error: ");
    if (type != MCommandMessage::kDisplay && !text.endsWith('\n')) text += '\n';
    QMutexLocker lock(&outputMutex);
    pendingOutput += text;
    if (pendingOutput.size() > 1024 * 1024)
        pendingOutput = "[HEditor: older buffered output omitted]\n" + pendingOutput.right(512 * 1024);
}
QString takeOutput() {
    QMutexLocker lock(&outputMutex);
    QString result; result.swap(pendingOutput); return result;
}
QString python(const QString& expression) {
    MString result;
    auto utf8 = expression.toUtf8();
    MStatus status = MGlobal::executePythonCommand(MString(utf8.constData()), result);
    return status ? QString::fromUtf8(result.asUTF8()) : QString("HEditor: Python bridge failed; see Script Editor.");
}
class Command : public MPxCommand {
public:
    static void* creator() { return new Command; }
    MStatus doIt(const MArgList&) override {
        if (MGlobal::mayaState() != MGlobal::kInteractive) {
            MGlobal::displayError("HEditor UI requires interactive Maya."); return MS::kFailure;
        }
        if (!window) {
            if (!outputCallback) {
                MStatus callbackStatus;
                outputCallback = MCommandMessage::addCommandOutputCallback(onOutput, nullptr, &callbackStatus);
                if (!callbackStatus) return callbackStatus;
            }
            window = heditor::createEditor(MQtUtil::mainWindow(), [](const QString& source) {
                // MayaのPython実行・履歴・共通出力を使用する。stdoutを横取りしない。
                auto utf8 = source.toUtf8();
                MString script;
                script.setUTF8(utf8.constData());
                MGlobal::executePythonCommand(script, true, false);
                return QString();
            }, [] { return python("__import__('heditor.bridge', fromlist=['configuration']).configuration()").toUtf8(); }, takeOutput);
        }
        window->show(); window->raise(); window->activateWindow(); return MS::kSuccess;
    }
};
}
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "HEditor", "0.1.2", "Any");
    return plugin.registerCommand("heditor", Command::creator);
}
MStatus uninitializePlugin(MObject object) {
    // 編集中タブは閉じる確認を通す。キャンセル時はアンロードを拒否する。
    if (window && !window->close()) return MS::kFailure;
    if (outputCallback) {
        MStatus status = MMessage::removeCallback(outputCallback);
        if (!status) return status;
        outputCallback = 0;
    }
    delete window.data(); window = nullptr;
    takeOutput();
    MFnPlugin plugin(object); return plugin.deregisterCommand("heditor");
}
