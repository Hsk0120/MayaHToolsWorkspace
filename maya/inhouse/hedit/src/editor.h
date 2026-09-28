/** @file editor.h
 * @brief Qt編集画面とMayaをつなぐコールバック定義。
 * @details std::functionは関数やラムダを保持する型。Maya APIから画面を分離し、
 * テストでは実行関数を差し替える。Qt部品は原則としてparentが所有する。
 */
#pragma once
#include <QMainWindow>
#include <QIcon>
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
/** @brief UIの拡大率を設定する。以後に作る編集画面の文字・アイコン・幅・余白に掛ける。
 * @param scale 100%を1.0とする拡大率。MayaではMQtUtil::dpiScale(1.0)を渡す(Maya標準の
 * Script Editorと同じ基準)。0以下は1.0として扱う。
 * @note MayaはQt自体の高DPI拡大を無効にし、各部品の寸法に拡大率を掛けて4K等へ対応している。
 * Mayaの全体の文字(メニュー・ステータスバー等)は拡大済みなので、ここでは掛けない。
 */
void setUiScale(double scale);
/** @brief ツールバーのアイコンを取り出す関数を設定する。以後に作る編集画面で使う。
 * @param provider アイコンの画像名(例: ``openScript.png``)から取り出す関数。空なら``QIcon(":/名前")``。
 * @note MayaではMQtUtil::createIconを渡す。Qtの``:/名前``は拡大率に関係なく小さな画像しか返さないが、
 * createIconは拡大率に合った高解像度の画像を返す(Maya標準のScript Editorと同じ見た目になる)。
 */
void setIconProvider(std::function<QIcon(const QString&)> provider);
/** @brief 100%時のピクセル数を、現在の拡大率で換算する。
 * @param pixels 100%時のピクセル数。
 * @return 拡大率を掛けて丸めたピクセル数。
 */
int scaled(double pixels);
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
/** @brief Mayaのreporterに残っている過去の履歴を、初回表示用に詰めて返す。
 * @param text reporterの表示文書の全文。
 * @return 空行を省き、空白だけの行を前後の断片へつないだ文字列。
 * @note 過去の通知の区切りはMayaが改行に変換済みで復元できないため、この整形は
 * 初回の取り込みだけに使い、以後のライブ出力には適用しない。
 */
QString compactHistory(QString text);
}
