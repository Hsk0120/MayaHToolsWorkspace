/** @file version.h
 * @brief heditの版。ここが版の唯一の定義。
 * @details 次の場所がこの値を読む:
 * - プラグインの登録(plugin/plugin.cpp)とドックのタイトル(plugin/dock.cpp)
 * - Pythonの``hedit.__version__``(plugin/embedded_python.cppがロード時に設定する)
 * - CMakeLists.txtの出力先``release/plug-ins/windows/<Mayaの年>/<版>/``
 * - ドキュメントの版(docs/conf.py)
 * @note 版を上げるときは、この値と、親リポジトリの``maya/modules/hedit.mod``・``docs/changelog.rst``を更新する。
 */
#pragma once
#define HEDIT_VERSION "0.2.10"
