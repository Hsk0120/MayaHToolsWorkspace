/** @file test_command.h
 * @brief テスト専用のMayaコマンド``heditTest``。環境変数``HEDIT_TEST_COMMANDS=1``のときだけ登録する。
 * @details 製品のコマンド(``hedit``)にテスト用の入口を混ぜないよう、別のコマンドに分けている。
 * 普段のMayaでは登録されないので、利用者からは見えない。
 * | フラグ(短い名前) | 動作 |
 * |---|---|
 * | ``-editor``(``-ed``) | 編集画面を(未作成なら作って)そのアドレスを返す。GUIテストがPySideから画面を参照する |
 * | ``-complete``(``-cp``) 本文 | 補完の結果をJSONで返す(画面は作らない) |
 * | ``-declarations``(``-dc``) 本文 | 本文から取り出した宣言をJSONで返す |
 * | ``-describe``(``-ds``) 本文 | 本文の末尾の名前のホバーの説明をJSONで返す |
 */
#pragma once
#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace hedit {

/** @brief テスト専用のコマンド``heditTest``。 */
class HeditTestCommand : public MPxCommand {
public:
    /// Mayaに登録するコマンド名。
    static constexpr const char* kName = "heditTest";

    /** @brief テスト用のコマンドを登録してよいか。 @return 環境変数``HEDIT_TEST_COMMANDS``が``1``ならtrue。 */
    static bool enabled();

    /** @brief Mayaがコマンドを作るときに呼ぶ関数。 @return 新しいコマンド。所有者はMaya。 */
    static void* creator();

    /** @brief コマンドのフラグを定義する。 @return フラグの定義。 */
    static MSyntax newSyntax();

    /** @brief フラグに応じた結果を返す。
     * @param args コマンドの引数。
     * @return 成功ならkSuccess。
     */
    MStatus doIt(const MArgList& args) override;
};

}  // namespace hedit
