/** @file python_bridge.h
 * @brief Maya内のPython・MELを呼ぶ処理(コードの実行・補完・構文チェック)。
 * @details 補完と構文チェックのPython側は、hedit.mllに同梱したsrc/python/hedit/*.py
 * (hedit.bridge・hedit.analysis)にある。ここではその関数を呼び、結果のJSONを受け取るだけ。
 * いずれもMayaのメインスレッドから呼ぶ。
 */
#pragma once
#include <QByteArray>
#include <QString>

namespace hedit {
namespace python {

/** @brief Pythonのコードを、Maya標準のPython実行経路で実行する。
 * @param source 実行するコード。
 * @return 常に空(結果はMayaの共通の出力へ流れ、出力欄はそれを表示する)。
 * @note Script Editorと同じ名前空間(__main__)を使い、stdoutを横取りしない。
 */
QString runPython(const QString& source);

/** @brief MELのコードを実行する。
 * @param source 実行するコード。
 * @return 常に空。
 */
QString runMel(const QString& source);

/** @brief 補完の環境(sys.pathと読み込み済みモジュール)を取り直す。
 * @return ``{"ready":true}``。
 */
QByteArray refreshCompletion();

/** @brief 補完候補を返す。``import xxx``の行はC++(module_scanner)で、それ以外はPythonで求める。
 * @param source カーソルまでの本文。
 * @return ``{"items":[{"name","detail","kind"}...],"pending":bool}``、失敗時は``{"error":"..."}``。
 */
QByteArray complete(const QString& source);

/** @brief Pythonの本文を構文チェックする(compileだけで、実行はしない)。
 * @param source 本文。
 * @return ``{"diagnostics":[...]}``または``{"diagnostics":[],"skipped":"理由"}``。
 */
QByteArray analyze(const QString& source);

/** @brief importの行の補完に使う、sys.pathの走査を始める(別スレッド)。
 * @details 編集画面の作成時に呼び、最初のCtrl+Spaceまでに走査を終えておく。
 */
void startModuleScan();

/** @brief 走査のスレッドを止めて合流する。プラグインのアンロード前に必ず呼ぶ。
 * @note スレッドのコードはhedit.mllの中にあるため、アンロード後に動くとMayaが落ちる。
 */
void stopModuleScan();

}  // namespace python
}  // namespace hedit
