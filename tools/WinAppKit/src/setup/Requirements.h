/**
 * @file Requirements.h
 * @brief 関連付けの前提条件(その拡張子を開くのに要るWindowsの拡張機能が入っているか)を調べる。
 *
 * 設定ファイルの [FileTypes] に、拡張子ごとの条件を書く:
 * @code
 * Require.heic=wic+mfvideo:HEVC
 * Require.webm=mfvideo:VP90|mfvideo:AV01
 * @endcode
 * 「+」は「すべて満たす」、「|」は「どれかを満たす」(「|」の方が強く結び付く)。条件は次のとおり。
 * - wic: その拡張子を読めるWindowsの画像コーデック(WIC)がある。WebP・HEIF・JPEG XLなどの画像拡張機能で増える。
 * - wic:.ext: 指定した拡張子を読めるWICのコーデックがある。
 * - mfvideo:FOURCC: その形式(HEVC・AV01・VP90など)のMedia Foundationの動画デコーダーがある。動画拡張機能で増える。
 */
#pragma once

#include <string>

namespace wak {

/**
 * @brief 関連付けの前提条件を満たしているかを調べる。
 * @param extension 対象の拡張子(「.heic」の形。条件「wic」で使う)。
 * @param expression 条件の式(空なら常に満たす)。
 * @param missing 満たしていないとき、足りないもの(条件の式の、満たしていない項)を格納する。
 * @return 満たしていればtrue。書き方が正しくない条件は、満たしていないとして扱う。
 * @note 呼び出したスレッドでCOMとMedia Foundationを使う(初期化はこの中で行い、終わりに戻す)。
 */
bool meetsRequirement(const std::wstring& extension, const std::wstring& expression, std::wstring& missing);

/**
 * @brief 条件の式の書き方が正しいかを調べる(セットアップを作るときの確認用)。
 * @param expression 条件の式。
 * @return 正しければtrue。
 */
bool isValidRequirement(const std::wstring& expression);

}  // namespace wak
