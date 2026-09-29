/** @file session_data.h
 * @brief 未保存タブの自動復元ファイル(tabs.json)の内容と、JSONとの変換。
 * @details ファイルの読み書き・ロック・画面への反映はeditor/session_store.cppとeditor/main_window.cppが行う。
 * ここは「JSONの形」だけを扱うので、Mayaも画面も無い状態でテストできる。
 *
 * tabs.jsonの形(version 1):
 * @code
 * {"version": 1, "active": 0, "explorerVisible": false, "folders": ["C:/scripts"],
 *  "tabs": [{"text": "...", "path": "", "language": "python", "modified": true, "position": 0, "anchor": 0}]}
 * @endcode
 */
#pragma once
#include <QByteArray>
#include <QList>
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 1つのタブの保存内容。 */
struct TabState {
    QString text;                ///< 本文。
    QString path;                ///< 保存先のファイル。未保存の新規タブは空。
    QString language = "python"; ///< ``python``または``mel``。
    bool modified = false;       ///< ファイルへ保存していない変更があるか。
    int position = 0;            ///< カーソルの位置。
    int anchor = 0;              ///< 選択の起点。選択がなければpositionと同じ。
};

/** @brief tabs.json全体の内容。 */
struct SessionData {
    int activeTab = 0;             ///< 選択していたタブの番号(0始まり)。
    QList<TabState> tabs;          ///< タブの一覧(表示順)。
    QStringList folders;           ///< Explorerのルートフォルダー。
    bool explorerVisible = false;  ///< Explorerを表示していたか。
};

/** @brief 保存内容をJSONにする。
 * @param data 保存する内容。
 * @return tabs.jsonへ書く文字列(UTF-8)。同じ内容なら常に同じ文字列になる。
 */
QByteArray sessionToJson(const SessionData& data);

/** @brief JSONを読んで保存内容に戻す。
 * @param bytes tabs.jsonの中身。
 * @param data 読み取った内容を入れる。失敗時は変更しない。
 * @return 形式が正しく、タブが1つ以上あればtrue。壊れたファイルならfalse。
 */
bool sessionFromJson(const QByteArray& bytes, SessionData* data);

}  // namespace hedit
