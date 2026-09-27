/** @file version.h
 * @brief heditの版。プラグイン登録(MFnPlugin)とドックのタイトルで共有する。
 * @note 版を上げるときは、embedded_python.hの__version__・CMakeLists.txtの出力先・
 * hedit.modもそろえて更新する(docs/development.rst参照)。
 */
#pragma once
#define HEDIT_VERSION "0.2.10"
