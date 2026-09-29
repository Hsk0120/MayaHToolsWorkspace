/** @file history_text.h
 * @brief 起動前からMayaに残っている出力履歴を、出力欄へ取り込める形に整える。
 * @details 初回表示のときに一度だけ使う。以後のライブ出力(plugin/output_capture.cpp)には使わない。
 */
#pragma once
#include "core/output_message.h"
#include <QString>

namespace hedit {

/** @brief Mayaのreporterに残っている過去の履歴を、初回表示用に詰める。
 * @param text reporterの表示文書の全文。
 * @return 空行を省き、空白だけの行を前後の断片へつないだ文字列。空の入力なら空文字列。
 * @note 過去の通知の区切りはMayaが改行に変換済みで復元できない。そのためこの整形は
 * 初回の取り込みだけに使う。
 */
QString compactHistory(QString text);

/** @brief 履歴の1行を、先頭の記号から出力の種類に分ける。
 * @param line 履歴の1行(改行を含まない)。
 * @return ``// Result:``や``# Result:``ならResult、Warning・Errorも同様。それ以外はNormal。
 * @note ライブ出力はMayaが種類を通知するが、過去の履歴には種類が残っていないため、
 * ここだけは記号で判定する。
 */
OutputKind classifyHistoryLine(const QString& line);

}  // namespace hedit
