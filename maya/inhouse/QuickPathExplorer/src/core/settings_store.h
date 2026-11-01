/** @file settings_store.h
 * @brief 既存JSON設定を読み、他プロセスの別キーを保持して更新する。
 */
#pragma once
#include <QJsonObject>
#include <QString>
namespace qpe {
/** @brief フォルダー改名/移動でJSON中の絶対パスだけを追従させる。 @param value 状態。 @param from 旧パス。 @param to 新パス。 @return 新しい値。 */
QJsonValue remapPaths(const QJsonValue& value, const QString& from, const QString& to);
/** @brief 設定ファイルの場所。 @return テスト環境変数または利用者領域のパス。 */
QString settingsPath();
/** @brief UTF-8設定を読む。 @return 未作成なら空、破損は例外。 */
QJsonObject readSettings();
/** @brief Python版の読込設定を値形式へ統合する。元設定は変更しない。
 * @param state 読み取った設定。 @return Import/Reference/FBX設定。
 */
QJsonObject readOptionsFromSettings(const QJsonObject& state);
/** @brief 旧プリセットを操作別に読み、移行版の同名値を優先する。
 * @param state 読み取った設定。 @param action 操作名。 @return 名前と設定。
 */
QJsonObject readPresetsFromSettings(const QJsonObject& state, const QString& action);
/** @brief ロックと原子的置換で指定キーだけ保存する。
 * @param changes 更新値。 @note 失敗時は例外で通知し既存ファイルを保持する。
 */
void writeSettings(const QJsonObject& changes);
/** @brief オブジェクト内の変更項目を同じロック内で統合する。 @param key 設定名。 @param changes 変更した下位項目。 */
void mergeSettingsMap(const QString& key, const QJsonObject& changes);
/** @brief 任意JSONを原子的に保存する。 @param path 出力先。 @param value オブジェクト。 */
void saveJson(const QString& path, const QJsonObject& value);
/** @brief ファイルからJSONを読む。 @param path 入力。 @return オブジェクト。 */
QJsonObject loadJson(const QString& path);
/** @brief 移植可能な設定を旧版互換形式で書き出す。 @param path 保存先。 @param includeLocal このPC固有のパスも含めるか。 */
void exportPreferences(const QString& path, bool includeLocal = false);
/** @brief 設定形式と値を全件検証してから原子的に反映する。 @param path 取込元。 */
void importPreferences(const QString& path);
/** @brief 固定操作との競合・重複・無効なカスタムキーを拒否する。 @param keys コマンド名とキー文字列。 */
void validateCommandKeys(const QJsonObject& keys);
}
