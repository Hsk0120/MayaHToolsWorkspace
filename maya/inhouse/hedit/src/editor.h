/** @file editor.h
 * @brief Qt編集画面とMayaをつなぐコールバック定義。
 * @details std::functionは関数やラムダを保持する型。Maya APIから画面を分離し、
 * テストでは実行関数を差し替える。Qt部品は原則としてparentが所有する。
 */
#pragma once
#include <QMainWindow>
#include <functional>
#include <QList>

namespace hedit {
/// 本文を実行し、補足メッセージ（通常は空）を返す。
using Execute = std::function<QString(const QString&)>;
/// 補完環境を更新してUTF-8 JSONを返す。
using Configuration = std::function<QByteArray()>;
/// Mayaが通知する出力種別。文字列から推測しない。
enum class OutputKind { Normal, Warning, Error, Result, Info, History };
/** @brief 表示文字列と分類を保持するデータ。 */
struct OutputMessage { QString text; OutputKind kind = OutputKind::Normal; };
/// 待機中のログを一度だけ取り出す。
using OutputReader = std::function<QList<OutputMessage>()>;
/// ソース文字列から補完候補または診断のJSONを返す。
using Completion = std::function<QByteArray(const QString&)>;
/** @brief 編集画面を作成する。表示とドッキングは呼出側で行う。
 * @param parent Qtの所有者。nullptrなら独立ウィンドウ。
 * @param execute Pythonを実行する関数。
 * @param configuration 補完環境を更新する関数。
 * @param outputReader Maya出力を取り出す関数。省略時は購読しない。
 * @param completion Python補完関数。省略時は候補なし。
 * @param sessionPath 復元JSONの絶対パス。空なら保存しない。
 * @param analyzer Python構文解析関数。設定オン時だけ呼ぶ。
 * @param melExecute MEL実行関数。省略時は実行不可を表示する。
 * @return 作成したウィンドウ。parentがあれば親が所有する。
 */
QMainWindow* createEditor(QWidget* parent, Execute execute, Configuration configuration, OutputReader outputReader = {}, Completion completion = {}, QString sessionPath = {}, Completion analyzer = {}, Execute melExecute = {});
/** @brief Mayaメインスレッドの出力通知からログを描画する。イベントループは回さない。
 * @param editor createEditorで作成した画面。nullptrは無視する。
 */
void refreshEditorOutput(QMainWindow* editor);
}
