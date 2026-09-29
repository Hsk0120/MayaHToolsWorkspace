/** @file python_bridge.h
 * @brief Maya内のPython・MELを呼ぶ処理(コードの実行・補完・構文チェック)。
 * @details 補完の判断はC++の補完エンジン(core/completion_engine.cpp)が行い、ここはその補完エンジンに
 * 「Pythonでしか分からない情報」(読み込み済みのモジュールの公開名・sys.path・組み込みの名前)を渡す。
 * それらは、hedit.mllに同梱したsrc/python/hedit/bridge.pyの関数を呼んでJSONで受け取る。
 * 構文チェックだけはPythonのcompile()が必要なので、src/python/hedit/analysis.pyを呼ぶ。
 * いずれもMayaのメインスレッドから呼ぶ。
 */
#pragma once
#include "core/completion_types.h"
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

/** @brief 組み込みの名前と予約語を取り直し、ファイルから読んだ宣言のキャッシュを捨てる(Refresh completion)。 */
void refreshCompletion();

/** @brief 補完候補を返す。``import xxx``の行のトップレベル名は別スレッドの走査(module_scanner)から、
 * それ以外は補完エンジンから求める。
 * @param source カーソルまでの本文。
 * @return 補完の結果。
 */
CompletionResult complete(const QString& source);

/** @brief 本文の宣言をJSONで返す(テスト用の``hedit -declarations``。Pythonのastとの突き合わせに使う)。
 * @param source 本文。
 * @return ``{"名前": {...}}``の形のJSON。
 */
QByteArray declarationsJson(const QString& source);

/** @brief Pythonの本文を構文チェックする(compileだけで、実行はしない)。
 * @param source 本文。
 * @return 結果。
 */
AnalysisResult analyze(const QString& source);

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
