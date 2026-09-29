/** @file script_file.h
 * @brief スクリプトファイル(.py・.mel)の読み書き。UTF-8だけを扱う。
 * @details 画面(MainWindow)から切り離し、Maya無しでテストできるようにしてある。
 */
#pragma once
#include <QString>

namespace hedit {

/** @brief UTF-8のスクリプトを読む。先頭のBOM(UTF-8の印)は取り除く。
 * @param path ファイルのパス。
 * @param text 読んだ本文を入れる。
 * @param error 失敗したときの理由を入れる。
 * @return 読めたらtrue。開けない、またはUTF-8でなければfalse。
 */
bool readScriptFile(const QString& path, QString* text, QString* error);

/** @brief 保存の前に本文を整える(Preferencesの「保存時の整形」)。
 * @param text 本文。
 * @param trimTrailingSpaces trueなら行末の空白とタブを消す。
 * @param ensureFinalNewline trueなら末尾に改行が無いときに足す。
 * @return 整えた本文。
 */
QString formatForSave(QString text, bool trimTrailingSpaces, bool ensureFinalNewline);

/** @brief 本文をUTF-8で保存する。一時ファイルへ書いてから置き換えるので、途中で失敗しても元のファイルは壊れない。
 * @param path 保存先。
 * @param text 本文。
 * @param error 失敗したときの理由を入れる。
 * @return 保存できたらtrue。
 */
bool writeScriptFile(const QString& path, const QString& text, QString* error);

}  // namespace hedit
