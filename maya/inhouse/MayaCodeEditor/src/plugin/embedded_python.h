/** @file embedded_python.h
 * @brief mayaCodeEditor.mllに同梱したPython(src/python/)を、Maya内のPythonからimportできるようにする。
 * @details 補完と構文チェックは、Python言語そのものの解析(ast・compile)が必要なので、Maya同梱の
 * Pythonで行う。そのPythonのコードは普通の.pyファイル(src/python/maya_code_editor/*.py)として書き、
 * ビルド時にcmake/embed_python.cmakeがC++の配列(embedded_python_sources.h)に変換してmayaCodeEditor.mllへ入れる。
 * プラグインのロード時にinstallModules()が、配列からモジュールを配るimportフックをPythonへ登録する。
 * ディスク上の.pyやPYTHONPATHには依存しない。
 */
#pragma once
#include <maya/MStatus.h>

namespace mce {
namespace embedded {

/** @brief 同梱する1つのPythonモジュール。 */
struct PythonModule {
    const char* name;    ///< モジュール名(例: ``maya_code_editor.bridge``)。
    bool isPackage;      ///< __init__.pyならtrue(パッケージ)。
    const char* source;  ///< ソースの本文(UTF-8、末尾は0)。
};

/** @brief 同梱のモジュールを配るimportフックを、Pythonのsys.meta_pathへ登録する。
 * @return 登録の結果。失敗時はPythonの例外の内容がScript Editorへ出る。
 * @details ``import maya_code_editor``などは、通常の.pyと同じくimportした時点で初めて実行される。
 * 標準のPathFinder(sys.pathの.pyを探す仕組み)の直前へ置く。PYTHONPATH上に同名のフォルダー
 * (旧版の``__pycache__``だけが残った``scripts/hedit``(旧名)等)があっても、それを先に見つけさせないため。
 * 組み込みモジュールなどの仕組みより後ろなので、Maya Code Editor以外のimportには影響しない。
 * 同梱以外から読まれた同名のモジュール(Maya Code Editorとmaya_code_editor.*だけ)は取り除く。
 * 同梱から読み込み済みのモジュールは、アンロード/ロードをまたいで残す(補完のキャッシュを保つため)。
 * ただし、同梱のソースか版が違うビルド(同じMayaのまま作り直したmayaCodeEditor.mll)から読み込んだものは取り除き、
 * 次のimportで新しいソースから読み直させる(古いコードが動き続けないように)。
 */
MStatus installModules();

}  // namespace embedded
}  // namespace mce
