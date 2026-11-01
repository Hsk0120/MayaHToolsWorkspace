/** @file plugin.cpp
 * @brief 単一mllの入口。既存Python機能はメモリーから読み込み、外部展開しない。
 */
#include "native_browser.h"
#include "sources.h"
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MGlobal.h>
#include <QApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QWidget>

namespace {
/** @brief UTF-8をMaya Pythonへ実行する。 @param code Python式。 @return 実行結果。 */
MStatus python(const QByteArray& code) {
    MString text;
    text.setUTF8(code.constData());
    return MGlobal::executePythonCommand(text, false, false);
}
/** @brief このプラグインが所有するメモリーimporterだけを解除する。 @return 実行結果。 */
MStatus releaseImporter() {
    return python("import sys\n_qpe_names = [n for f in sys.meta_path if getattr(f, 'qpe_embedded', False) for n in f.sources]\nsys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, 'qpe_embedded', False)]\nfor _qpe_name in _qpe_names: sys.modules.pop(_qpe_name, None)");
}
/** @brief 唯一の公開起動コマンド。 */
class ShowCommand final : public MPxCommand {
public:
    /** @brief Mayaへ所有権を渡す。 @return コマンド。 */
    static void* creator() { return new ShowCommand; }
    /** @brief 保存済み位置で開く。 @param args 未使用。 @return 実行結果。 */
    MStatus doIt(const MArgList& args) override {
        if (args.length()) return MS::kInvalidParameter;
        return python("import qpeHost; qpeHost.show()");
    }
};
/** @brief 内部部品を、Mayaの同一Qtランタイム上で生成する。 */
class NativeCommand final : public MPxCommand {
public:
    /** @brief Mayaへ所有権を渡す。 @return コマンド。 */
    static void* creator() { return new NativeCommand; }
    /** @brief 生存するウィジェットだけを親として受理する。
     * @param args 種類、親ポインターの10進文字列。 @return 生成結果。
     */
    MStatus doIt(const MArgList& args) override {
        if (args.length() != 2) return MS::kInvalidParameter;
        bool valid = false;
        const auto address = QString::fromUtf8(args.asString(1).asUTF8()).toULongLong(&valid);
        QWidget* parent = nullptr;
        if (valid) for (auto widget : QApplication::allWidgets())
            if (reinterpret_cast<quintptr>(widget) == address) { parent = widget; break; }
        if (!parent) return MS::kInvalidParameter;
        auto object = qpe::createNative(QString::fromUtf8(args.asString(0).asUTF8()), parent);
        if (!object) return MS::kInvalidParameter;
        setResult(QString::number(reinterpret_cast<quintptr>(object)).toLatin1().constData());
        return MS::kSuccess;
    }
};
}

/** @brief メモリーimporterとコマンドを登録する。
 * @param object Mayaのプラグイン。 @return 初期化結果。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "HTools", "0.3.0", "Any");
    QJsonObject modules;
    for (const auto& source : sources) modules.insert(source.name, QString::fromUtf8(source.text));
    // JSONをPythonのraw文字列に渡す。JSON中の改行・引用符はエスケープ済み。
    QByteArray code = "import json\n_qpe_sources = json.loads(r'''";
    code += QJsonDocument(modules).toJson(QJsonDocument::Compact).replace("'", "\\u0027");
    code += "''')\n";
    code += R"PY(
import importlib.abc, importlib.util, sys
if 'qpeHost' in sys.modules:
    # 開いた旧Python版を黙って差し替えるとQt所有権が二重になるため拒否する。
    import qpeHost
    if not getattr(qpeHost.__loader__, 'qpe_embedded', False):
        raise RuntimeError('The Python QPE is already initialized. Restart Maya without the Python QPE module before loading this plugin.')
    if qpeHost._window is not None and qpeHost.shiboken.isValid(qpeHost._window):
        raise RuntimeError('Close the existing QPE and restart Maya before loading the native plugin.')
class QpeEmbeddedImporter(importlib.abc.MetaPathFinder, importlib.abc.InspectLoader):
    qpe_embedded = True
    def __init__(self, sources):
        self.sources = sources
    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname, self, origin='quickPathExplorer.mll')
    def get_source(self, fullname):
        return self.sources[fullname]
    def is_package(self, fullname):
        return False
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        module.__file__ = 'quickPathExplorer.mll/python/' + module.__name__ + '.py'
        exec(compile(self.sources[module.__name__], module.__file__, 'exec'), module.__dict__)
for _qpe_name in _qpe_sources:
    sys.modules.pop(_qpe_name, None)
sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, 'qpe_embedded', False)]
sys.meta_path.insert(0, QpeEmbeddedImporter(_qpe_sources))
del _qpe_sources
)PY";
    auto status = plugin.registerCommand("quickPathExplorerNative", NativeCommand::creator);
    if (!status) return status;
    status = plugin.registerCommand("quickPathExplorer", ShowCommand::creator);
    if (!status) { plugin.deregisterCommand("quickPathExplorerNative"); return status; }
    status = python(code);
    if (!status) {
        plugin.deregisterCommand("quickPathExplorer");
        plugin.deregisterCommand("quickPathExplorerNative");
        return status;
    }
    // idle時にはロードが完了している。アンロード後の遅延実行は起動しない。
    status = python("from maya import utils, cmds\nutils.executeDeferred(lambda: __import__('qpeHost').installMenu() if cmds.pluginInfo('quickPathExplorer', query=True, loaded=True) else None)");
    if (!status) {
        releaseImporter();
        plugin.deregisterCommand("quickPathExplorer");
        plugin.deregisterCommand("quickPathExplorerNative");
    }
    return status;
}

/** @brief QPE所有のUIだけを破棄し、他Qtツールへ影響を与えず解除する。
 * @param object Mayaのプラグイン。 @return 解除結果。使用中は拒否。
 */
MStatus uninitializePlugin(MObject object) {
    if (!python("import qpeNative; qpeNative.shutdown()")) return MS::kFailure;
    if (!qpe::nativeObjectsReleased()) {
        MGlobal::displayError("QPE native views are still alive. Close them before unloading.");
        return MS::kFailure;
    }
    MFnPlugin plugin(object);
    auto status = plugin.deregisterCommand("quickPathExplorer");
    if (!status) return status;
    status = plugin.deregisterCommand("quickPathExplorerNative");
    if (!status) return status;
    return releaseImporter();
}
