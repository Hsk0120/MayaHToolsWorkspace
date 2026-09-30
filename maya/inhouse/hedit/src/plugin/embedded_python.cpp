/** @file embedded_python.cpp
 * @brief 同梱のPythonを配るimportフックの登録。
 * @details 同梱のソースは、Pythonの普通の文字列リテラルとしてそのまま渡す(符号化や難読化はしない)。
 * 実行も、標準のimportlibの仕組み(InspectLoaderのget_source → exec_module)に任せ、
 * ``exec``・``compile``を自前で呼ばない。ウイルス対策ソフトが「符号化した文字列を戻して実行する」
 * マルウェアの形と誤認しないようにするため。
 */
#include "plugin/embedded_python.h"
#include "embedded_python_sources.h"  // ビルド時に生成される(cmake/embed_python.cmake)。
#include "version.h"
#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <cstdio>
#include <string>

namespace hedit {
namespace embedded {
namespace {

/** @brief 文字列を、Pythonの文字列リテラル(``'...'``)にする。
 * @param text UTF-8の文字列(引用符・改行・バックスラッシュを含み得る)。
 * @return 引用符で囲んだリテラル。日本語などはUTF-8のまま入れる。
 * @details ``\``・``'``・改行・タブ・その他の制御文字だけをエスケープする。
 */
std::string pythonLiteral(const char* text) {
    std::string literal = "'";
    for (auto p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
        switch (*p) {
        case '\\': literal += "\\\\"; break;
        case '\'': literal += "\\'"; break;
        case '\n': literal += "\\n"; break;
        case '\r': literal += "\\r"; break;
        case '\t': literal += "\\t"; break;
        default:
            if (*p < 0x20 || *p == 0x7F) {
                char escaped[5];
                std::snprintf(escaped, sizeof(escaped), "\\x%02x", *p);
                literal += escaped;
            } else {
                literal += static_cast<char>(*p);
            }
        }
    }
    literal += "'";
    return literal;
}

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

    # 前回のロードで登録したフックを外してから、新しいフックを先頭へ入れる。
    sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__name__ != 'HeditEmbeddedImporter']
    # 同梱以外(ディスク上の古いフォルダーなど)から読まれた同名のモジュールを取り除く。
    for name in [name for name in sys.modules if name in sources or name.startswith('hedit.')]:
        if getattr(getattr(sys.modules[name], '__spec__', None), 'origin', None) != 'hedit.mll':
            del sys.modules[name]
    sys.meta_path.insert(0, HeditEmbeddedImporter())
)PY";

}  // namespace

MStatus installModules() {
    std::string script = kBootstrap;
    script += "__hedit_bootstrap({\n";
    for (const PythonModule& module : kPythonModules) {
        script += std::string("    '") + module.name + "': " + pythonLiteral(module.source) + ",\n";
    }
    script += "}, {";
    for (const PythonModule& module : kPythonModules) {
        if (module.isPackage) {
            script += std::string("'") + module.name + "', ";
        }
    }
    script += "}, '" HEDIT_VERSION "')\n";
    // 一時関数を、Script Editorの名前空間(__main__)に残さない。
    script += "del __hedit_bootstrap\n";
    MString command;
    command.setUTF8(script.c_str());
    return MGlobal::executePythonCommand(command, false, false);
}

}  // namespace embedded
}  // namespace hedit
