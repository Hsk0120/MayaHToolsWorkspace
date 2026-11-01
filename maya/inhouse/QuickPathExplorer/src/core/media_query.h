/** @file media_query.h @brief 選択によるシーン読込を行わないメタデータ取得。 */
#pragma once
#include "file_operations.h"
namespace qpe {
/** @brief 内容を開かず取得した表示名と、自動読込を避ける判定。 */
struct Availability { QString text; bool avoidRead = false; };
/** @brief Windows属性とCloud Filesの結果を解釈する。 @param attributes 属性ビット。 @param cloud Cloud Filesの状態、0は不明。 @return 表示と読込可否。 */
Availability availabilityFromFlags(quint32 attributes, quint32 cloud = 0);
/** @brief 属性だけを照会し、クラウドのダウンロードを開始しない。 @param path 対象。 @return 表示と読込可否。 */
Availability inspectAvailability(const QString& path);
/** @brief ワーカーで静止画と情報を生成する。 @param request 固定対象。 @param cancel 取消し。 @return PNGとメタデータ。 */
FileResult queryMedia(const FileRequest& request, const CancelFlag& cancel);
/** @brief クラウドの暗黙取得を避ける属性照会。 @param path 対象。 @return 属性の表示名。 */
QString fileAvailability(const QString& path);
}
