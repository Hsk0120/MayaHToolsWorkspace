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

/** @brief Mayaの出力の通知(MCommandMessage)の本文を、Script Editorのreporterと同じ形に整える。
 * @param message 通知の本文。
 * @param kind 種類。
 * @param legacy Maya 2022の書き方にするならtrue。2022のreporterは、1行目にだけ記号を付け、最後に`` // ``
 * (Pythonは`` # ``)を付けて改行する(例: ``// Warning: a\nsecond // \n``)。2023以降は下の書き方。
 * @return Script Editorと同じ形の文字(2023以降):
 * - 警告・エラー: ``// Warning: 1行目``、2行目以降は``// ``を付ける。改行で終える。
 * - 情報(displayInfo): 各行に``// ``を付ける(空行は``// ``だけ)。改行で終える。
 * - 結果: ``// Result: 値``。改行で終える。
 * - それ以外(printなど): 本文のまま。
 * @details Pythonの例外(``ValueError: file <maya console> line 1: …``の形を含むエラー。MELのファイルの中で
 * 起きたものも含む)は、Script Editorと同じく先頭を``# Error: ``にする。
 * @note Script Editorは、Pythonから呼んだ``cmds.warning``・``cmds.error``の先頭も``#``にするが、通知の本文と状態
 * からはMELの``warning``と区別できない(どちらもGILを手放した状態で通知される)ため、``//``になる。
 */
QString formatCommandOutput(const QString& message, OutputKind kind, bool legacy = false);

}  // namespace hedit
