/** @file legacy_history.h @brief Python版の履歴を原本を変更せず読み継ぐ。 */
#pragma once
#include "file_operations.h"
#include <QJsonObject>
#include <QFileInfo>
namespace qpe {
/** @brief 旧版のmsvcrt先頭1バイトロックと共有する排他。 */
class LegacyHistoryLease final {
public:
    /** @brief 旧領域が存在するときだけロックする。 @param directory 旧undo領域。 */
    explicit LegacyHistoryLease(const QString& directory);
    /** @brief 自分のハンドルを閉じ、バイトロックを解放する。 */
    ~LegacyHistoryLease();
    LegacyHistoryLease(const LegacyHistoryLease&) = delete;
    LegacyHistoryLease& operator=(const LegacyHistoryLease&) = delete;
private:
    void* handle_ = nullptr;
};
/** @brief 最新の復旧コピーを含め、旧履歴を初回だけnative journalへ追加する。
 * @param directory 旧undo領域。 @param journal 現在のnative記録。
 * @return 原本digestと旧形式を保持した統合記録。
 */
QJsonObject migrateLegacyHistory(const QString& directory, QJsonObject journal);
/** @brief Python版と同じ名前順・階層SHA256を計算する。
 * @param path 対象。 @param cancel 取消し。 @return 旧内容指紋。
 */
QString legacyFingerprint(const QString& path, const CancelFlag& cancel = {});
/** @brief 旧版のごみ箱Redo用stat指紋をWin32で再現する。 @param path 対象。 @param cancel 取消し。 @return 指紋。 */
QString legacyMetadataFingerprint(const QString& path, const CancelFlag& cancel = {});
/** @brief 列挙エラーを空ディレクトリと混同しない。 @param path 親。 @return 名前順の子。 */
QFileInfoList checkedChildren(const QString& path);
/** @brief 旧32桁転送IDをnativeの36桁に写す。 @param id 旧ID。 @return 決定的UUID表記。 */
QString legacyTransferId(const QString& id);
}
