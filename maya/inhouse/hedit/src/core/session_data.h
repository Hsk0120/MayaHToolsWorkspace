/** @file session_data.h
 * @brief 未保存タブの自動復元ファイル(tabs.json)の内容と、JSONとの変換。
 * @details ファイルの読み書き・ロック・画面への反映はeditor/session_store.cppとeditor/main_window.cppが行う。
 * ここは「JSONの形」だけを扱うので、Mayaも画面も無い状態でテストできる。
 *
 * tabs.jsonの形(version 2)。本文はタブごとの``tabs/<id>.txt``に分けて置く:
 * @code
 * {"version": 2, "active": 0, "explorerVisible": false, "folders": ["C:/scripts"],
 *  "tabs": [{"id": "3f2a…", "path": "", "language": "python", "modified": true, "position": 0, "anchor": 0}]}
 * @endcode
 * 本文を分けたのは、カーソルの移動などの小さな変化のたびに全タブの本文を書き直さないため
 * (本文のファイルは、そのタブの本文が変わったときだけ書く)。
 * 0.2.x の version 1(本文を tabs.json に含む形)も読める。次の保存で version 2 になる。
 */
#pragma once
#include <QByteArray>
#include <QList>
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 1つのタブの保存内容。 */
struct TabState {
    QString id;                  ///< タブの識別子(本文のファイル名に使う)。英数字だけ。
    QString text;                ///< 本文。textLoadedがfalseなら入っていない。
    bool textLoaded = true;      ///< textに本文が入っているか(保存時、本文が変わっていないタブはfalse)。
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

/** @brief 保存内容をJSONにする(version 2。本文は含まない)。
 * @param data 保存する内容。
 * @return tabs.jsonへ書く文字列(UTF-8)。同じ内容なら常に同じ文字列になる。
 */
QByteArray sessionToJson(const SessionData& data);

/** @brief JSONを読んで保存内容に戻す。
 * @param bytes tabs.jsonの中身。
 * @param data 読み取った内容を入れる。失敗時は変更しない。version 2では本文を読まない(textLoadedがfalse)。
 * @return 形式が正しく、タブが1つ以上あればtrue。壊れたファイルならfalse。
 */
bool sessionFromJson(const QByteArray& bytes, SessionData* data);

/** @brief タブの識別子として使える文字列か(ファイル名にするので英数字だけ)。 @param id 識別子。 @return 使えればtrue。 */
bool isValidTabId(const QString& id);

/** @brief 新しいタブの識別子を作る。 @return 32文字の16進数。 */
QString newTabId();

}  // namespace hedit
