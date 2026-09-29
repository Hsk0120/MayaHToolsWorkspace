/** @file hedit_command.h
 * @brief Mayaのコマンド``hedit``(MEL・Pythonのどちらからも呼べる)。
 * @details フラグ一覧:
 * | フラグ(短い名前) | 動作 |
 * |---|---|
 * | (なし) | 編集画面を(未作成なら作って)そのアドレスを返す。GUIテストがPySideから画面を参照するときに使う |
 * | ``-show``(``-sh``) | 画面を開く。``-floating``(``-f``)を付けたときだけ浮動状態を変える |
 * | ``-restore``(``-r``) | workspaceControlのuiScriptから呼ぶ。前回閉じていれば非表示のまま |
 * | ``-saveState``(``-ss``) | 開閉状態をすぐにui.jsonへ保存する |
 * | ``-sessionPath``(``-sp``) | tabs.jsonのパスを返す。画面を作らないのでmayapyでも使える |
 * | ``-closed``(``-cl``) | 内部用。ドックのcloseCommandから呼ばれる |
 * | ``-quitting``(``-qt``) | 内部用。Maya終了時のscriptJobから呼ばれる |
 * | ``-complete``(``-cp``) 本文 | テスト用。補完の結果をJSONで返す(画面は作らない) |
 * | ``-declarations``(``-dc``) 本文 | テスト用。本文から取り出した宣言をJSONで返す |
 */
#pragma once
#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace hedit {

/** @brief ``hedit``コマンド。Mayaが実行のたびに作り、実行後に破棄する。 */
class HeditCommand : public MPxCommand {
public:
    /// Mayaに登録するコマンド名。
    static constexpr const char* kName = "hedit";

    /** @brief Mayaがコマンドを作るときに呼ぶ関数。 @return 新しいコマンド。所有者はMaya。 */
    static void* creator();

    /** @brief コマンドのフラグを定義する。 @return フラグの定義。 */
    static MSyntax newSyntax();

    /** @brief フラグに応じて、画面を開く・復元する・状態を保存する・復元先を返す。
     * @param args コマンドの引数。
     * @return 成功ならkSuccess。GUIの無いMayaで画面が必要な操作をしたらkFailure。
     */
    MStatus doIt(const MArgList& args) override;
};

}  // namespace hedit
