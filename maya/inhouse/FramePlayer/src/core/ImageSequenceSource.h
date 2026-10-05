/**
 * @file ImageSequenceSource.h
 * @brief 連番画像(shot.0001.png〜など)を、動画と同じようにコマとして返す読み込み元。
 */
#pragma once

#include <ppltasks.h>

#include <atomic>

#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "core/FrameSource.h"

namespace frameplayer {

/**
 * @brief 連番画像の読み込み元。
 * @note 1枚の画像のパスから、同じ名前の並び(番号の部分だけが違うファイル)を同じフォルダから探す。
 *       コマ番号は最初の番号のファイルを0とし、番号の抜けたファイルは「欠け」として扱う(番号を詰めない)。
 *       画像はWindows標準のWIC(png・jpg・tif・bmp・gif・webp・heif・avif・jxl・jxrなど。拡張機能があればその形式も)と、
 *       自前のEXRの読み込みで読む。全コマがキーフレームなので、どのコマへも直接移れる。
 *       デコードは裏の作業スレッドで先のコマまで並行して行う(CPUの複数のコアを使う)。
 *       値は8bitの画像はBGRAのまま、16bitの画像は16bitのまま、EXRとWICの浮動小数点の画像は半精度のまま返し、
 *       描画のときに色を変換する(EXRはリニア、それ以外はsRGBとして扱う)。
 */
class ImageSequenceSource : public FrameSource {
public:
    static constexpr double kDefaultFrameRate = 60.0;  ///< 連番画像の既定のフレームレート。
    /// 画像として開く拡張子(小文字)。
    static constexpr const wchar_t* kExtensions[] = {L"png",  L"jpg", L"jpeg", L"jpe",  L"jfif", L"tif", L"tiff",
                                                     L"bmp",  L"dib", L"gif",  L"webp", L"heic", L"heif", L"hif",
                                                     L"avif", L"jxl", L"jxr",  L"wdp",  L"exr"};

    /**
     * @brief 画像のパスから連番を探して開く。
     * @param path 連番の中の1枚(番号の無い画像なら1枚だけの連番)。
     * @param frameRate フレームレート。
     * @param maxWidth 返すコマの最大幅(超える画像は縮小する)。0なら縮小しない。
     * @param error 失敗時に理由を格納する。
     * @param purpose 使い道。Thumbnailsなら1枚ずつ読み、BGRAで返す。
     * @return 開けた読み込み元。失敗時はnullptr。
     * @note 最初のファイルを試しに読み、読めない形式なら失敗にする。
     */
    static std::unique_ptr<ImageSequenceSource> open(const std::wstring& path, double frameRate, int maxWidth,
                                                     std::wstring& error, SourcePurpose purpose);

    /** @copydoc FrameSource::frameCount */
    int frameCount() const override { return static_cast<int>(files_.size()); }
    /** @copydoc FrameSource::frameRate */
    double frameRate() const override { return frameRate_; }
    /** @copydoc FrameSource::frameTime */
    long long frameTime(int index) const override;
    /** @copydoc FrameSource::keyFrameAtOrBefore */
    int keyFrameAtOrBefore(int index) const override { return index; }
    /** @copydoc FrameSource::seekToKeyFrame */
    bool seekToKeyFrame(int keyIndex) override;
    /** @copydoc FrameSource::readNext */
    bool readNext(Frame& out, int& index) override;
    /** @brief 裏で動いているデコードが全て終わるまで待ってから片付ける。 */
    ~ImageSequenceSource() override;

    /** @copydoc FrameSource::releaseDecoder
     *  @note 先読み中のデコードは止めずに、結果を捨てる(終わるのを待つのは片付けるときだけ)。 */
    void releaseDecoder() override;
    /** @copydoc FrameSource::error */
    const std::wstring& error() const override { return error_; }
    /** @copydoc FrameSource::description */
    std::wstring description() const override;
    /** @copydoc FrameSource::firstFrameNumber */
    std::optional<int> firstFrameNumber() const override { return numbered_ ? std::optional<int>(first_) : std::nullopt; }
    /** @copydoc FrameSource::isMissing */
    bool isMissing(int index) const override;

    /** @brief 1枚の画像のデコードの結果。 */
    struct Decoded {
        Frame frame;          ///< コマ。
        std::wstring error;   ///< 失敗の説明(成功なら空)。
        std::wstring format;  ///< 形式の説明(「PNG 16bit」など)。
    };

private:
    ImageSequenceSource() = default;

    /**
     * @brief 先読みの作業を、indexから先のコマについて始める(始めていないものだけ)。
     * @param index 最初のコマ番号。
     */
    void schedule(int index);

    /**
     * @brief 結果を使わなくなったデコードを、終わるまで覚えておく(終わったものは忘れる)。
     * @param task デコードの作業。
     */
    void retire(concurrency::task<std::shared_ptr<Decoded>> task);

    /** @brief 先読み中のデコード1つ。 */
    struct Pending {
        concurrency::task<std::shared_ptr<Decoded>> task;  ///< デコードの作業。
        std::shared_ptr<std::atomic<bool>> cancel;          ///< trueにすると、途中で打ち切る(EXRのみ)。
    };

    std::vector<std::wstring> files_;  ///< コマ番号ごとのファイルのパス(欠けは空)。
    int first_ = 0;                    ///< 最初のファイルの番号。
    bool numbered_ = false;            ///< 番号の付いた連番か(番号の無い1枚ならfalse)。
    int missing_ = 0;                  ///< 欠けているコマの数。
    double frameRate_ = kDefaultFrameRate;
    int maxWidth_ = 0;
    SourcePurpose purpose_ = SourcePurpose::Playback;
    int depth_ = 1;                    ///< 並行して先にデコードするコマの数(最大)。
    int ramp_ = 1;                     ///< いま先読みするコマの数。飛んだ直後は1で、順に読むと倍ずつdepth_まで増やす。
    int next_ = 0;                     ///< 次に返すコマ番号。
    std::map<int, Pending> pending_;  ///< 先読み中のデコード。
    std::vector<concurrency::task<std::shared_ptr<Decoded>>> retired_;   ///< 結果を捨てた、まだ動いているかもしれないデコード。
    std::wstring format_;              ///< 最初の画像の形式の説明。
    std::wstring error_;
};

/**
 * @brief 画像のファイルを1枚デコードする(連番画像の読み込みで使う。確認用にも使える)。
 * @param path パス。
 * @param maxWidth 最大幅(超えれば縮小する)。0なら縮小しない。
 * @param bgra trueならBGRAの8bitにして返す(縮小画像用)。
 * @param cancel trueになったら途中で打ち切る印(EXRだけが見る)。nullptrなら打ち切らない。
 * @return 結果。
 * @note 呼び出したスレッドでCOMを初期化する。
 */
ImageSequenceSource::Decoded decodeImageFile(const std::wstring& path, int maxWidth, bool bgra,
                                             const std::atomic<bool>* cancel = nullptr);

/**
 * @brief 1画素64bitのRGBAのコマを、BGRAの8bitにする(縮小画像・確認用)。
 * @param frame コマ(書き換える)。Rgba16は上位8bitへ丸め、RgbaHalfはsRGBの値にする(伝達関数もSDRにする)。
 *              それ以外の並びなら何もしない。
 */
void convertToBgra8(Frame& frame);

}  // namespace frameplayer
