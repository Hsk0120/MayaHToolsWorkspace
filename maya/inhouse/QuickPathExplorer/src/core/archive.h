/** @file archive.h @brief 外部実行環境を使わないZIPの作成・検査・限定展開。 */
#pragma once
#include "file_operations.h"
#include <QJsonArray>
namespace qpe {
/** @brief 全項目を検証して展開前の一覧を返す。 @param path ZIP。 @param cancel 取消し。 @return 安全な項目一覧。 */
QJsonArray inspectArchive(const QString& path, const CancelFlag& cancel = {});
/** @brief 未作成の作業出力へZIPを生成/展開する。呼出側がUndo記録と公開を行う。
 * @param request createZip/extractZip要求。 @param output 未作成作業パス。
 * @param cancel 取消し。 @param progress 進捗。 */
void writeArchive(const FileRequest& request, const QString& output, const CancelFlag& cancel, const FileProgress& progress);
}
