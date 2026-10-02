/**
 * @file Mp4SampleTable.h
 * @brief mp4/movファイルの目次(サンプルテーブル)を、映像データを読まずに取り出す処理。
 */
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace frameplayer {

/**
 * @brief 映像トラックの全コマの表示時刻とキーフレームかどうか(デコード順)。
 * @note mp4/movは、ファイル内のmoovボックスに全コマの時刻とキーフレームの一覧を持っている。
 *       ここだけを読めば、数十GBの動画でも映像データを読まずに目次を作れる。
 */
struct Mp4SampleTable {
    std::vector<std::int64_t> presentationTimes;  ///< 表示時刻(100ns単位)。デコード順。編集リストによるずれは含まない。
    std::vector<std::uint8_t> isKeyFrame;          ///< キーフレームなら1。デコード順。
};

/**
 * @brief mp4/movファイルの最初の映像トラックからサンプルテーブルを読む。
 * @param path ファイルのパス。
 * @param table 読み取った結果の格納先。
 * @return 読めた場合true。mp4/movでない、断片化mp4(moofを使う形式)、テーブルが壊れているなどの場合false。
 * @note 失敗しても例外は出さない。呼び出し元は別の方法(全体を読む)で目次を作ること。
 */
bool readMp4SampleTable(const std::wstring& path, Mp4SampleTable& table);

}  // namespace frameplayer
