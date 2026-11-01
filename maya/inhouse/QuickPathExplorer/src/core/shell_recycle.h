/** @file shell_recycle.h @brief 内容コピーなしのごみ箱移動と正確な項目の復元。 */
#pragma once
#include "file_operations.h"
namespace qpe {
/** @brief ごみ箱以外の削除を拒否して移す。
 * @param path 対象。 @param cancel 取消し。 @return Shell識別子とファイルID。
 */
QJsonObject recyclePath(const QString& path, const CancelFlag& cancel);
/** @brief 指紋を検証して元の場所へ戻す。上書きしない。
 * @param receipt 移動時の記録。 @param path 復元先。
 */
void restoreRecycled(const QJsonObject& receipt, const QString& path);
/** @brief ごみ箱項目と復元先を変更せず検証する。 @param receipt 記録。 @param path 復元先。 */
void validateRecycled(const QJsonObject& receipt, const QString& path);
}
