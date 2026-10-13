/** @file version.h
 * @brief Maya Code Editorの版。ここが版の唯一の定義。
 * @details 次の場所がこの値を読む:
 * - プラグインの登録(plugin/plugin.cpp)とドックのタイトル(plugin/dock.cpp)
 * - Pythonの``maya_code_editor.__version__``(plugin/embedded_python.cppがロード時に設定する)
 * - mayaCodeEditor.mllのファイル情報(CMakeLists.txtがcmake/version.rc.inから作る)
 * - ドキュメントの版(docs/conf.py)
 * @note 版を上げるときは、この値と、親リポジトリの``maya/modules/MayaCodeEditor.mod``・``docs/changelog.rst``を更新する。
 */
#pragma once
#define MCE_VERSION "0.7.2"
