/** @file editor_host.h
 * @brief 編集画面を1つだけ作り、Mayaの処理(実行・補完・出力)とつなぐ。
 * @details 画面そのものはeditor/(Maya非依存)にある。ここでMayaの関数をEditorServicesに詰めて渡す。
 * 作った画面の所有者はMayaのドック(workspaceControl)。Mayaがドックを作り直すと画面が破棄されることがあるので、
 * QPointer(対象が破棄されると自動でnullptrになるポインター)で参照する。
 */
#pragma once
#include <QMainWindow>

namespace hedit {
namespace host {

/** @brief 編集画面を返す。
 * @param create trueなら、未作成のときに作る(初回はMayaの過去の出力も取り込む)。
 * @return 編集画面。作れない・未作成(create=false)ならnullptr。
 */
QMainWindow* editor(bool create);

/** @brief 編集画面を閉じる(タブを自動保存する)。
 * @return 閉じた(または画面が無い)ならtrue。保存できずに利用者がキャンセルしたらfalse。
 */
bool closeEditor();

/** @brief 編集画面を破棄する。プラグインのアンロード時に使う。 */
void destroyEditor();

}  // namespace host
}  // namespace hedit
