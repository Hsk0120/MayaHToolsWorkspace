/**
 * @file Clip.h
 * @brief 1本の動画の全コマをメモリに保持するクラス。
 */
#pragma once

#include <functional>
#include <string>
#include <vector>

#include "core/Frame.h"

namespace frameplayer {

/**
 * @brief 動画を先頭から最後まで読み込み、全コマを縮小してメモリに保持する。
 * @note 正確なコマ送りのため、表示時にデコードやシークは行わない。
 *       コマ番号(0始まり)は読み込まれた順番そのもの。
 */
class Clip {
public:
    /// 読み込み中の進み具合を受け取る関数。引数は読み込み済みのコマ数。
    using ProgressCallback = std::function<void(int loadedFrames)>;

    /**
     * @brief 動画を読み込む。既に保持しているコマは破棄する。
     * @param path 動画ファイルのパス。
     * @param maxWidth 保持する画像の最大幅(ピクセル)。これより大きい動画は縦横比を保って縮小する。
     * @param progress 進み具合の通知先。不要なら空でよい。
     * @param error 失敗時に理由を格納する。
     * @return 1コマ以上読めた場合true。
     * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。読み終わるまで戻らない。
     */
    bool load(const std::wstring& path, int maxWidth, const ProgressCallback& progress, std::wstring& error);

    /**
     * @brief 保持しているコマ数を返す。
     * @return コマ数。未読み込みなら0。
     */
    int frameCount() const { return static_cast<int>(frames_.size()); }

    /**
     * @brief コマを返す。
     * @param index 0始まりのコマ番号。0以上frameCount()未満であること。
     * @return 保持しているコマ。
     */
    const Frame& frame(int index) const { return frames_[static_cast<size_t>(index)]; }

    /**
     * @brief ファイルに記録されたフレームレートを返す。
     * @return 1秒あたりのコマ数。不明なら0。
     */
    double frameRate() const { return frameRate_; }

    /**
     * @brief 読み込んだファイルのパスを返す。
     * @return パス。未読み込みなら空。
     */
    const std::wstring& path() const { return path_; }

private:
    std::vector<Frame> frames_;
    double frameRate_ = 0.0;
    std::wstring path_;
};

/**
 * @brief 画像を縦横比を保って縮小する。
 * @param source 元の画像。
 * @param maxWidth 縮小後の最大幅。元の幅がこれ以下ならそのまま返す。
 * @return 縮小した画像。
 * @note 縮小先の1画素に対応する元の範囲を平均する(面積平均)。
 */
Frame shrinkToWidth(const Frame& source, int maxWidth);

}  // namespace frameplayer
