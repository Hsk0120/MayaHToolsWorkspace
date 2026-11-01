/** @file media_decoder.h @brief 配布ファイル内のC製デコーダーを必要時だけ準備する。 */
#pragma once
#include "file_operations.h"
namespace qpe {
/** @brief 明示した外部デコーダーか、検証した内蔵デコーダーを返す。
 * @param cancel サムネイル要求の取り消し。
 * @return 実行パス。デコーダー未収録時は空。
 * @note exe/mll内のヘルパーをユーザーキャッシュへ展開する。Pythonは使わない。
 */
QString mediaDecoder(const CancelFlag& cancel = {});
}
