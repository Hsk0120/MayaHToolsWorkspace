/** @file file_queries.h @brief 内容検索・集計・比較をUIの外で行う。 */
#pragma once
#include "file_operations.h"
namespace qpe {
/** @brief 読取専用問い合わせを実行。 @param request 条件。 @param cancel 取消し。 @param progress 進捗。 @param partial 世代付きの途中結果。 @return 値の一覧。 */
FileResult runFileQuery(const FileRequest& request, const CancelFlag& cancel, const FileProgress& progress, const FilePartial& partial = {});
}
