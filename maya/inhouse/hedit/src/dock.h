/** @file dock.h
 * @brief hedit画面をMayaのworkspaceControlへドッキングし、開閉状態を保存・復元する。
 * @details 旧docking.py(MayaQWidgetDockableMixin)とstartup.pyをC++へ移したもの。
 * MELのworkspaceControlとMQtUtil::addWidgetToMayaLayoutで、編集画面(QMainWindow)を
 * 直接ドックへ入れる。開閉状態はhedit専用のui.json、ドックの配置はMayaのワークスペースへ保存する。
 * ユーザーのSecurity設定・プラグインのautoload設定は変更しない。
 */
#pragma once
#include <QMainWindow>
#include <functional>
#include <optional>

namespace hedit {
namespace dock {
/** @brief 編集画面の取得・作成とタブ復元先を、plugin.cppから受け取る。
 * @param editor 編集画面を返す関数。引数trueなら未作成時に作る。falseなら既存だけ返し、無ければnullptr。
 * @param sessionPath tabs.jsonの絶対パスを返す関数。ui.jsonは同じフォルダーに置く。
 */
void configure(std::function<QMainWindow*(bool)> editor, std::function<QString()> sessionPath);
/** @brief プラグインと同じ寿命のQObject。遅延実行(QTimer::singleShot等)の文脈に使う。
 * @return configure()で作り、release()で破棄するオブジェクト。
 * @note ラムダの実体はhedit.mllの中にあるため、実行前にプラグインがアンロードされると
 * 解放済みのコードを呼んで落ちる。この文脈に結び付けた遅延処理は、破棄時に取り消される。
 */
QObject* lifetime();
/** @brief ドックの名前を返す。旧名のドックが保存済みならそれを使い、配置を引き継ぐ。
 * @return workspaceControlのUI名。
 */
QString controlName();
/** @brief 画面を開く。開いていれば一度閉じて(タブを保存して)同じ画面を開き直す。
 * @param floating 指定時だけフローティング状態を変更する。未指定なら既存の配置を保つ。
 * @return 開けた場合true。未保存の確認で取り消された場合などはfalse。
 */
bool show(std::optional<bool> floating = std::nullopt);
/** @brief workspaceControlのuiScript(hedit -restore)から呼ばれ、ドックの中身を作る。
 * @return 成功ならtrue。前回閉じていた場合は中身を作らず、ドックを非表示に保つ。
 */
bool restore();
/** @brief プラグインのロード後に、前回開いていた場合だけ画面を表示する。 */
void restorePrevious();
/** @brief ユーザーがドックを閉じたときに呼ぶ(closeCommand)。次回の自動表示を止める。 */
void closed();
/** @brief Maya終了の直前に呼ぶ(quitApplicationのscriptJob)。最終状態を保存して以後の変更を凍結する。 */
void quitting();
/** @brief 現在のドック状態をui.jsonへ保存する。終了処理中は上書きしない。 */
void record();
/** @brief プラグイン解除時に、閉じた状態を記録してタイマー・終了通知を取り除く。 */
void uninstall();
/** @brief プラグイン解除時に空のドックを残さないよう、workspaceControlを削除する。 */
void release();
}
}
