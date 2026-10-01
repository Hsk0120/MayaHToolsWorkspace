/** @file json_file.h
 * @brief heditの状態ファイル(tabs.json・ui.json・preferences.json)の読み書きをまとめたもの。
 * @details 3つのファイルを同じ書き方で扱う:
 * - 書くときはQSaveFileで一時ファイルへ書いてから置き換える(途中で落ちても元のファイルは壊れない)。
 * - 1項目だけ変えるときは、読み直してからその項目だけを書き換える(updateJsonFile)。
 *   同じユーザーの複数のMayaが別々の項目を変えても、互いの変更を消さない。
 * Mayaにも画面にも依存しない。
 */
#pragma once
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

namespace hedit {

/** @brief JSONのファイルを読む。
 * @param path ファイルのパス。
 * @param object 読み取った内容を入れる。失敗時は変更しない。
 * @param error 失敗の理由を入れる。nullptrなら入れない。ファイルが無い場合は空のまま。
 * @return 読めて、中身がJSONのオブジェクトならtrue。
 */
bool readJsonFile(const QString& path, QJsonObject* object, QString* error = nullptr);

/** @brief JSONのファイルを書く。フォルダーが無ければ作る。
 * @param path ファイルのパス。
 * @param object 書く内容。
 * @param error 失敗の理由を入れる。nullptrなら入れない。
 * @return 書けたらtrue。
 */
bool writeJsonFile(const QString& path, const QJsonObject& object, QString* error = nullptr);

/** @brief JSONのファイルの1項目だけを書き換える(他の項目は、今ファイルにある値を残す)。
 * @param path ファイルのパス。無ければ作る。
 * @param key 項目の名前。
 * @param value 新しい値。QJsonValue::Undefinedなら項目を消す。
 * @param error 失敗の理由を入れる。nullptrなら入れない。
 * @return 書けたらtrue。
 */
bool updateJsonFile(const QString& path, const QString& key, const QJsonValue& value, QString* error = nullptr);

}  // namespace hedit
