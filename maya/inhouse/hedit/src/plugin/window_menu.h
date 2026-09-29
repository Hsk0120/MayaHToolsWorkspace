/** @file window_menu.h
 * @brief MayaのWindowメニューの末尾に「hedit - Python / MEL」(緑のHアイコン)を追加・削除する。
 */
#pragma once
#include <maya/MStatus.h>

namespace hedit {

/** @brief Windowメニューへheditの項目を1回だけ追加する。既にあれば何もしない。
 * @return MELの実行結果。
 * @details メインメニューが既にあればすぐ追加する。Maya起動の初期(メニューを作る前)にロードされた場合だけ、
 * ``evalDeferred``でMayaが落ち着いてから追加する。
 */
MStatus installWindowMenu();

/** @brief Windowメニューからheditの項目を取り除く。 @return MELの実行結果。 */
MStatus uninstallWindowMenu();

}  // namespace hedit
