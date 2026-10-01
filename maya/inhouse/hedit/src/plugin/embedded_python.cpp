/** @file embedded_python.cpp
 * @brief 同梱のPythonを配るimportフックの登録。
 * @details 同梱のソースは、Pythonの普通の文字列リテラルとしてそのまま渡す(符号化や難読化はしない)。
 * 実行も、標準のimportlibの仕組み(InspectLoaderのget_source → exec_module)に任せ、
 * ``exec``・``compile``を自前で呼ばない。ウイルス対策ソフトが「符号化した文字列を戻して実行する」
 * マルウェアの形と誤認しないようにするため。
 */
#include "plugin/embedded_python.h"
#include "core/python_literal.h"
#include "embedded_python_sources.h"  // ビルド時に生成される(cmake/embed_python.cmake)。
#include "version.h"
#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <string>

namespace hedit {
namespace embedded {
namespace {

/// importフックを登録するPython。__hedit_bootstrap(ソースの辞書, パッケージ名の集合, 版)として呼ぶ。
constexpr const char* kBootstrap = R"PY(
def __hedit_bootstrap(sources, packages, version):
    import sys, importlib.abc, importlib.util

    class HeditEmbeddedImporter(importlib.abc.MetaPathFinder, importlib.abc.InspectLoader):
        """hedit.mll に同梱したソースを、通常の .py と同じ手順で import させる。"""

        def find_spec(self, fullname, path=None, target=None):
            if fullname not in sources:
                return None
            return importlib.util.spec_from_loader(fullname, self, origin='hedit.mll',
                                                   is_package=fullname in packages)

        def is_package(self, fullname):
            return fullname in packages

        def get_source(self, fullname):
            return sources[fullname]

        def get_code(self, fullname):
            # トレースバックに、どの同梱ファイルかが分かる名前を出す。
            path = '<hedit.mll>/' + fullname.replace('.', '/') + ('/__init__.py' if fullname in packages else '.py')
            return self.source_to_code(sources[fullname], path)

        def exec_module(self, module):
            if module.__name__ == 'hedit':
                module.__version__ = version
            super().exec_module(module)

    # 前回のロードで登録したフックを外してから、標準のPathFinder(sys.pathの.pyを探す仕組み)の直前へ入れる。
    # 組み込み・凍結モジュールの仕組みより後ろなので、hedit以外のimportの順番は変えない。
    sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__name__ != 'HeditEmbeddedImporter']
    # 同梱以外(ディスク上の古いフォルダーなど)から読まれた同名のモジュールを取り除く。
    for name in [name for name in sys.modules if name in sources or name.startswith('hedit.')]:
        if getattr(getattr(sys.modules[name], '__spec__', None), 'origin', None) != 'hedit.mll':
            del sys.modules[name]
    import importlib.machinery
    position = next((index for index, finder in enumerate(sys.meta_path)
                     if finder is importlib.machinery.PathFinder), len(sys.meta_path))
    sys.meta_path.insert(position, HeditEmbeddedImporter())
)PY";

}  // namespace

MStatus installModules() {
    QString script = QString::fromUtf8(kBootstrap);
    script += "__hedit_bootstrap({\n";
    for (const PythonModule& module : kPythonModules) {
        script += "    " + pythonStringLiteral(QString::fromUtf8(module.name)) + ": "
                  + pythonStringLiteral(QString::fromUtf8(module.source)) + ",\n";
    }
    script += "}, {";
    for (const PythonModule& module : kPythonModules) {
        if (module.isPackage) {
            script += pythonStringLiteral(QString::fromUtf8(module.name)) + ", ";
        }
    }
    script += "}, " + pythonStringLiteral(QStringLiteral(HEDIT_VERSION)) + ")\n";
    // 一時関数を、Script Editorの名前空間(__main__)に残さない。
    script += "del __hedit_bootstrap\n";
    MString command;
    command.setUTF8(script.toUtf8().constData());
    return MGlobal::executePythonCommand(command, false, false);
}

}  // namespace embedded
}  // namespace hedit
