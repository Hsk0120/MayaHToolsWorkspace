/** @file embedded_python.h
 * @brief hedit.mllに同梱したPython(src/python/)を、Maya内のPythonからimportできるようにする。
 * @details 補完と構文チェックは、Python言語そのものの解析(ast・compile)が必要なので、Maya同梱の
 * Pythonで行う。そのPythonのコードは普通の.pyファイル(src/python/hedit/*.py)として書き、
 * ビルド時にcmake/embed_python.cmakeがC++の配列(embedded_python_sources.h)に変換してhedit.mllへ入れる。
 * プラグインのロード時にinstallModules()が、配列からモジュールを配るimportフックをPythonへ登録する。
 * ディスク上の.pyやPYTHONPATHには依存しない。
 */
#pragma once
#include <maya/MStatus.h>

namespace hedit {
namespace embedded {

/** @brief 同梱する1つのPythonモジュール。 */
struct PythonModule {
    const char* name;    ///< モジュール名(例: ``hedit.bridge``)。
    bool isPackage;      ///< __init__.pyならtrue(パッケージ)。
    const char* source;  ///< ソースの本文(UTF-8、末尾は0)。
};

/** @brief 同梱のモジュールを配るimportフックを、Pythonのsys.meta_pathへ登録する。
 * @return 登録の結果。失敗時はPythonの例外の内容がScript Editorへ出る。
 * @details ``import hedit``などは、通常の.pyと同じくimportした時点で初めて実行される。
 * 標準のPathFinder(sys.pathの.pyを探す仕組み)の直前へ置く。PYTHONPATH上に同名のフォルダー
 * (旧版の``__pycache__``だけが残った``scripts/hedit``等)があっても、それを先に見つけさせないため。
 * 組み込みモジュールなどの仕組みより後ろなので、hedit以外のimportには影響しない。
 * 同梱以外から読まれた同名のモジュール(heditとhedit.*だけ)は取り除く。
 * 同梱から読み込み済みのモジュールは、アンロード/ロードをまたいで残す(補完のキャッシュを保つため)。
 */
MStatus installModules();

}  // namespace embedded
}  // namespace hedit
