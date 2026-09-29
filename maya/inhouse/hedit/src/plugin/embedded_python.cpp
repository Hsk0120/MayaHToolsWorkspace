/** @file embedded_python.cpp
 * @brief 同梱のPythonを配るimportフックの登録。
 */
#include "plugin/embedded_python.h"
#include "embedded_python_sources.h"  // ビルド時に生成される(cmake/embed_python.cmake)。
#include "version.h"
#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <string>

namespace hedit {
namespace embedded {
namespace {

/** @brief 文字列を16進数(0-9a-f)の文字列にする。
 * @param text 変換する文字列(引用符・改行・バックスラッシュを含み得る)。
 * @return 16進数の文字列。Pythonの文字列リテラルへそのまま埋め込める。
 * @details ソースの引用符や改行を1つずつエスケープする代わりに、安全な文字だけに変換して渡し、
 * Python側のbinascii.unhexlifyで元に戻す。
 */
std::string hexEncode(const char* text) {
    static const char* digits = "0123456789abcdef";
    std::string buffer;
    for (auto p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
        buffer += digits[*p >> 4];
        buffer += digits[*p & 0x0F];
    }
    return buffer;
}

/// importフックを登録するPython。__hedit_bootstrap(ソースの辞書, パッケージ名の集合, 版)として呼ぶ。
constexpr const char* kBootstrap = R"PY(
def __hedit_bootstrap(encoded, packages, version):
    import sys, binascii, importlib.abc, importlib.util
    sources = {name: binascii.unhexlify(value).decode('utf-8') for name, value in encoded.items()}

    class HeditEmbeddedImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname not in sources:
                return None
            return importlib.util.spec_from_loader(fullname, self, origin='hedit.mll',
                                                   is_package=fullname in packages)

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            if module.__name__ == 'hedit':
                module.__version__ = version
            filename = '<hedit.mll>/' + module.__name__.replace('.', '/') + '.py'
            exec(compile(sources[module.__name__], filename, 'exec'), module.__dict__)

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
        script += std::string("    '") + module.name + "': '" + hexEncode(module.source) + "',\n";
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
