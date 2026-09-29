/** @file matrix_follow.h
 * @brief 単一入力の親空間行列追従ノードの登録入口。
 */
#pragma once
#include <maya/MFnPlugin.h>
/** @brief 行列追従型をプラグインへ登録する。
 * @param plugin Mayaが管理するプラグイン参照。
 * @return 型登録の結果。
 */
MStatus registerMatrixFollow(MFnPlugin& plugin);
/** @brief 行列追従型の登録を解除する。
 * @param plugin Mayaが管理するプラグイン参照。
 * @return 登録解除の結果。
 */
MStatus deregisterMatrixFollow(MFnPlugin& plugin);
