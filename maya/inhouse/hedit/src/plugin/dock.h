/** @file dock.h
 * @brief 編集画面をMayaのドック(workspaceControl)に入れ、開閉状態を保存・復元する。
 * @details 流れ:
 * - 開く: Windowメニュー → ``hedit -show`` → show()。workspaceControlを作り(または表示し)、
 *   MQtUtil::addWidgetToMayaLayoutで編集画面を入れる。
 * - Maya再起動時: Mayaがワークスペースを復元し、ドックのuiScript(``hedit -restore``)→ restore()。
 *   プラグインのロード後にもrestorePrevious()で、前回開いていたのに開いていなければ開く。
 * - 閉じる: ドックの×ボタン → closeCommand(``hedit -closed``)→ onClosed()。次回は自動で開かない。
 * - Maya終了: quitApplicationのscriptJob(``hedit -quitting``)→ onQuitting()。最後の状態を保存する。
 *
 * 開閉状態はhedit専用のui.json、ドックの位置・大きさはMayaのワークスペースに保存される。
 * Mayaのセキュリティ設定・プラグインのautoload設定は変更しない。
 */
#pragma once
#include <QObject>
#include <QString>
#include <optional>

namespace hedit {
namespace dock {

/** @brief プラグインのロード時に呼ぶ。遅延実行の文脈(lifetime())を作る。 */
void initialize();

/** @brief プラグインと同じ寿命のQObject。遅延実行(QTimer::singleShot等)の文脈に使う。
 * @return initialize()で作り、release()で破棄するオブジェクト。
 * @note 遅延実行するラムダのコードはhedit.mllの中にある。実行前にプラグインがアンロードされると
 * 解放済みのコードを呼んで落ちる。この文脈に結び付けた遅延処理は、破棄時に取り消される。
 */
QObject* lifetime();

/** @brief ドックの名前を返す。 @return workspaceControlのUI名(``heditDockWorkspaceControl``)。 */
QString controlName();

/** @brief 画面を開く。開いていれば一度閉じて(タブを保存して)同じ画面を開き直す。
 * @param floating 指定したときだけ浮動状態を変える。std::nullopt(指定なし)なら既存の配置を保つ。
 * @return 開けた場合true。未保存の確認で取り消された場合などはfalse。
 */
bool show(std::optional<bool> floating = std::nullopt);

/** @brief workspaceControlのuiScript(``hedit -restore``)から呼ばれ、ドックの中身を作る。
 * @return 成功ならtrue。前回閉じていた場合は中身を作らず、ドックを非表示に保つ。
 */
bool restore();

/** @brief プラグインのロード後に、前回開いていた場合だけ画面を表示する。 */
void restorePrevious();

/** @brief 利用者がドックを閉じたときに呼ぶ(closeCommand)。次回の自動表示を止める。 */
void onClosed();

/** @brief Maya終了の直前に呼ぶ(quitApplicationのscriptJob)。最後の状態を保存して、以後は書き換えない。 */
void onQuitting();

/** @brief 現在のドックの状態をui.jsonへ保存する。変化が無ければ書かない。終了処理中は何もしない。 */
void saveState();

/** @brief プラグインのアンロード時に、閉じた状態を記録して、タイマーと終了通知を取り除く。 */
void uninstall();

/** @brief プラグインのアンロード時に、空のドックを残さないようworkspaceControlを削除する。 */
void release();

}  // namespace dock
}  // namespace hedit
