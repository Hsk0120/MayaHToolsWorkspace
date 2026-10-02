/**
 * @file FrameSource.h
 * @brief 動画などからコマを取り出す共通の窓口。
 *
 * プレイヤー本体(Clip)はこの窓口だけを使う。読み込み方式(Media Foundation、連番画像、
 * 将来のProResなど)を追加するときは、このクラスの派生クラスを足して
 * openFrameSource()で選ぶようにする。
 */
#pragma once

#include <memory>
#include <string>

#include "core/Frame.h"
#include "core/GpuDevice.h"

namespace frameplayer {

/** @brief 読み込み元の使い道。デコードのやり方(先読みの深さ・返す形式)を変える。 */
enum class SourcePurpose {
    Playback,    ///< 再生用。続けて読む速さを優先し、GPUのテクスチャで返せるならそうする。
    Thumbnails,  ///< キーフレームの縮小画像用。1コマずつ読み、主メモリのBGRA画像で返す。
};

/**
 * @brief コマ番号の目次を持ち、キーフレームから順にデコードしてコマを返す読み込み元。
 * @note コマ番号(0始まり)は開いたときに作る目次で決まり、どこから読み始めても同じ番号になる。
 *       目次と照合できないコマは返さない(番号を推測しない)。
 *       1つの読み込み元を同時に複数のスレッドから使ってはならない。
 */
class FrameSource {
public:
    /** @brief 派生クラスの資源を解放する。 */
    virtual ~FrameSource() = default;

    /**
     * @brief 目次にあるコマ数を返す。
     * @return コマ数。
     */
    virtual int frameCount() const = 0;

    /**
     * @brief ファイルに記録されたフレームレートを返す。
     * @return 1秒あたりのコマ数。不明なら0。
     */
    virtual double frameRate() const = 0;

    /**
     * @brief コマの表示時刻を返す。
     * @param index 0始まりのコマ番号。0以上frameCount()未満であること。
     * @return 表示時刻(100ns単位)。音声と同じ時間軸。
     * @note 目次は開いた後に変わらないので、どのスレッドから呼んでもよい。
     */
    virtual long long frameTime(int index) const = 0;

    /**
     * @brief 指定したコマ以前で最も近いキーフレーム(単独でデコードできるコマ)を返す。
     * @param index 0始まりのコマ番号。
     * @return キーフレームのコマ番号。
     */
    virtual int keyFrameAtOrBefore(int index) const = 0;

    /**
     * @brief 次のreadNext()がキーフレームkeyIndexから返すように読み込み位置を移す。
     * @param keyIndex keyFrameAtOrBefore()で得たキーフレームのコマ番号。
     * @return 移せた場合true。失敗時はerror()が空でない。
     * @note keyIndexより前の番号のコマは、移動後に届いても返さない(壊れている可能性があるため)。
     */
    virtual bool seekToKeyFrame(int keyIndex) = 0;

    /**
     * @brief 現在の読み込み位置から次のコマをデコードする。
     * @param out デコードしたコマの格納先。
     * @param index outのコマ番号。
     * @return 読めた場合true。終端に達したか失敗した場合false(失敗ならerror()が空でない)。
     */
    virtual bool readNext(Frame& out, int& index) = 0;

    /**
     * @brief デコーダーを閉じ、デコーダーが持つメモリ(GPUのメモリを含む)を返す。
     * @note 次のseekToKeyFrame()で作り直す。閉じた後はseekToKeyFrame()を呼ぶまでreadNext()は失敗する。
     *       しばらく使わないとき(最小化中など)に呼ぶ。
     */
    virtual void releaseDecoder() {}

    /**
     * @brief 直近の失敗の説明を返す。
     * @return 失敗していなければ空文字列。
     */
    virtual const std::wstring& error() const = 0;

    /**
     * @brief 読み込み方式の説明を返す(確認用の表示に使う)。
     * @return 例: 「デコード: GPU / 目次: mp4/movの目次」。
     */
    virtual std::wstring description() const = 0;
};

/**
 * @brief パスに合う読み込み元を開き、目次を作る。
 * @param path 開くファイルのパス。
 * @param maxWidth 返すコマの最大幅の希望。読み込み元が縮小できる場合(GPUでのデコードなど)に使う。
 *                 読み込み元が縮小しない場合もあるので、呼び出し元は幅を確かめて必要なら縮小すること。
 * @param gpu 共有のGPUデバイス。nullptrならGPUを使わない。使える場合、コマはGPUのテクスチャで返ることがある。
 * @param error 失敗時に理由を格納する。
 * @param purpose 使い道。Thumbnailsのときは主メモリのBGRA画像で返す(縮小できない方式では縮小しない)。
 * @return 開けた読み込み元。失敗時はnullptr。
 * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。
 */
std::unique_ptr<FrameSource> openFrameSource(const std::wstring& path, int maxWidth, std::shared_ptr<GpuDevice> gpu,
                                             std::wstring& error, SourcePurpose purpose = SourcePurpose::Playback);

}  // namespace frameplayer
