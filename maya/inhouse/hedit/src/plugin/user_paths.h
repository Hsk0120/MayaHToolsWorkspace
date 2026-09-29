/** @file user_paths.h
 * @brief heditがファイルを置く場所(Mayaのユーザー設定フォルダーの下のhedit/)。
 * @details 置くファイル: tabs.json(未保存タブ)・ui.json(開閉状態)・preferences.ini(設定)・hedit.svg(メニューのアイコン)。
 * Mayaのバージョンごとに別のフォルダーになる(internalVar -userPrefDirがバージョン別のため)。
 */
#pragma once
#include <QString>

namespace hedit {

/** @brief heditのフォルダー。 @return ``<userPrefDir>/hedit``。Mayaから取れなければ空。
 * @note Mayaへの問い合わせは最初の1回だけ行う。
 */
QString userFolder();

/** @brief 未保存タブの復元先(tabs.json)を決める。
 * @return tabs.jsonの絶対パス(Windowsの区切り文字)。
 * @details 環境変数HEDIT_SESSION_FILEがあればそれを使う(テストで専用の場所にするため)。
 * 無ければ``<userPrefDir>/hedit/tabs.json``。Mayaへの問い合わせは最初の1回だけ行い、以後は覚えた値を使う
 * (ドックの状態を1秒ごとに保存するときにも呼ばれるため)。
 */
QString sessionFilePath();

}  // namespace hedit
