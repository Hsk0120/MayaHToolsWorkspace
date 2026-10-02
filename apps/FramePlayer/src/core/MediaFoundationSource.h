/**
 * @file MediaFoundationSource.h
 * @brief Windows標準のMedia Foundationで動画を読む読み込み元。
 */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wrl/client.h>

#include <deque>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "core/FrameSource.h"
#include "core/GpuDevice.h"

namespace frameplayer {

/**
 * @brief Media FoundationのSource Readerで動画を読む。
 * @note Windowsが標準で読める形式(H.264のmp4など)に対応する。
 *       開いたときに、デコードせずに圧縮されたままのコマを最後まで読み、表示時刻を並べ替えて
 *       「コマ番号→表示時刻」の目次とキーフレームの一覧を作る。デコードしたコマは表示時刻を
 *       目次と照合して番号を決めるので、途中から読んでも番号がずれない。
 *       色変換はSource Readerの映像処理機能に任せ、BGRA(RGB32)で受け取る。
 */
class MediaFoundationSource : public FrameSource {
public:
    /**
     * @brief 動画ファイルを開き、目次を作る。
     * @param path 動画ファイルのパス。
     * @param maxWidth 返すコマの最大幅。GPUでデコードできる場合は、GPUでこの幅まで縮小して返す。
     * @param gpu 共有のGPUデバイス。nullptrならCPUでデコードする。
     * @param error 失敗時に理由を格納する。
     * @return 開けた読み込み元。失敗時はnullptr。
     * @note GPUでNV12のままGPUのメモリに置く方式、GPUでデコードして主メモリへ写す方式、CPUでデコードする方式の順に試す。
     *       CPUのときは縮小しない(呼び出し元で縮小する)。
     */
    static std::unique_ptr<MediaFoundationSource> open(const std::wstring& path, int maxWidth,
                                                       std::shared_ptr<GpuDevice> gpu, std::wstring& error);

    /** @brief Media Foundationの利用を終了する(open()で開始した分と対になる)。 */
    ~MediaFoundationSource() override;

    MediaFoundationSource(const MediaFoundationSource&) = delete;
    MediaFoundationSource& operator=(const MediaFoundationSource&) = delete;

    /** @copydoc FrameSource::frameCount */
    int frameCount() const override { return static_cast<int>(timestamps_.size()); }
    /** @copydoc FrameSource::frameRate */
    double frameRate() const override { return frameRate_; }
    /** @copydoc FrameSource::frameTime */
    long long frameTime(int index) const override { return timestamps_[static_cast<std::size_t>(index)]; }
    /** @copydoc FrameSource::keyFrameAtOrBefore */
    int keyFrameAtOrBefore(int index) const override;
    /** @copydoc FrameSource::seekToKeyFrame */
    bool seekToKeyFrame(int keyIndex) override;
    /** @copydoc FrameSource::readNext */
    bool readNext(Frame& out, int& index) override;
    /** @copydoc FrameSource::error */
    const std::wstring& error() const override { return error_; }
    /** @copydoc FrameSource::description */
    std::wstring description() const override;

private:
    /** @brief デコードの方式。 */
    enum class Mode {
        Cpu,          ///< CPUでデコードし、RGBで主メモリに返す。
        GpuReadback,  ///< GPUでデコード・RGBへの変換・縮小し、主メモリへ写して返す。
        GpuTexture,   ///< GPUでデコード・縮小し、NV12のままGPUのメモリのテクスチャで返す。
    };

    /** @brief open()以外から作らせないための非公開コンストラクター。 */
    MediaFoundationSource() = default;

    /**
     * @brief デコードせずに全コマの表示時刻とキーフレームかどうかを読み、目次を作る。
     * @param path 動画ファイルのパス。
     * @return 作れた場合true。失敗時はerror_を設定してfalse。
     * @note mp4/movはファイル内の目次を直接読み、先頭の一部を実際に読んで時刻が合うか確かめる。
     *       それ以外の形式や照合が合わない場合は、圧縮されたままのコマを最後まで読む。
     */
    bool buildIndex(const std::wstring& path);

    /**
     * @brief 集めた表示時刻を並べ替えて目次とキーフレームの一覧を作る。
     * @param samples 表示時刻(100ns単位)とキーフレームかどうかの組。順不同。
     * @param anyKeyFlag キーフレームの情報を持つ形式か。falseなら常に先頭から読む。
     * @return 1コマ以上あればtrue。
     */
    bool setIndex(std::vector<std::pair<LONGLONG, bool>> samples, bool anyKeyFlag);

    /**
     * @brief デコード用の読み込み本体を作る。
     * @param path 動画ファイルのパス。
     * @param maxWidth GPUのときに縮小する最大幅。
     * @param mode デコードの方式。
     * @return 作れた場合true。失敗時はerror_を設定してfalse。
     */
    bool createReader(const std::wstring& path, int maxWidth, Mode mode);

    /**
     * @brief GPU上のデコード結果(NV12)を、キャッシュ用の新しいテクスチャへ写してoutに入れる。完了は待たない。
     * @param sample GPU上にあるコマ。
     * @param out 格納先。
     * @return 写す命令を出せた場合true。
     * @note 呼び出し元がGPUの鍵をかけておくこと。
     */
    bool copyToTexture(IMFSample* sample, Frame& out);

    /**
     * @brief デコードしたコマの表示時刻から、目次のコマ番号を求める。
     * @param timestamp 表示時刻(100ns単位)。
     * @return コマ番号。目次に近い時刻が無ければ-1。
     */
    int indexOfTimestamp(LONGLONG timestamp) const;

    /** @brief 先読み中の1コマ。GPUならステージングテクスチャ、CPUならサンプルを持つ。 */
    struct PendingFrame {
        int index = -1;  ///< コマ番号。
        RECT visible{};  ///< 切り出す範囲(先読みした時点の出力形式による)。
        Microsoft::WRL::ComPtr<ID3D11Texture2D> staging;  ///< GPUから写している先。CPUのときはnullptr。
        Microsoft::WRL::ComPtr<IMFSample> sample;         ///< CPUでデコードしたコマ。GPUのときはnullptr。
    };

    /**
     * @brief デコード済みのコマを1つ受け取り、目次と照合して番号を決める。
     * @param sample 受け取ったコマ。
     * @param index コマ番号。
     * @return 1=受け取れた、0=終端、-1=失敗(error_を設定)。
     * @note 照合できないコマとシーク位置より前のコマは読み飛ばす。
     */
    int readDecodedSample(Microsoft::WRL::ComPtr<IMFSample>& sample, int& index);

    /**
     * @brief GPU上のコマを主メモリから読めるテクスチャへ写す命令を出し、先読みの列に加える。完了は待たない。
     * @param sample GPU上にあるコマ。
     * @param index コマ番号。
     * @return 命令を出せた場合true。GPU上のコマでない、RGBでないなどの場合false。
     */
    bool enqueueGpuCopy(IMFSample* sample, int index);

    /**
     * @brief GPUから写したコマを受け取る。写し終わっていなければ待つ。
     * @param pending 先読みの列から取り出した1コマ。使い終わったテクスチャは使い回しへ戻す。
     * @param out 格納先。
     * @return 受け取れた場合true。
     */
    bool copyFromStaging(PendingFrame& pending, Frame& out);

    /**
     * @brief 主メモリ上のコマ(CPUでデコードしたもの)を受け取る。
     * @param sample デコードしたコマ。
     * @param visible 切り出す範囲。
     * @param out 格納先。
     * @return 受け取れた場合true。
     */
    bool copyFromSample(IMFSample* sample, const RECT& visible, Frame& out);

    /**
     * @brief 画像の行を切り出してoutへ写し、不透明にする。
     * @param scan0 先頭行の位置。
     * @param pitch 1行のバイト数。負なら下の行から並ぶ。
     * @param visible 切り出す範囲。
     * @param out 格納先。
     */
    static void copyRows(const BYTE* scan0, LONG pitch, const RECT& visible, Frame& out);

    /** @brief 先読みしていたコマを捨てる(シーク時など)。 */
    void clearPending();

    /**
     * @brief 出力形式(大きさ・行の間隔・表示範囲)を読み直す。
     * @return 取得できた場合true。失敗時はerror_を設定してfalse。
     * @note 開いた直後と、デコーダーが形式の変更を通知したときに呼ぶ。
     */
    bool updateFormat();

    /**
     * @brief 失敗内容を記録する。
     * @param message 失敗の説明。
     * @param hr 失敗したHRESULT。
     */
    void setError(const wchar_t* message, HRESULT hr);

    std::shared_ptr<GpuDevice> gpu_;                       ///< 共有のGPUデバイス。無ければnullptr。
    Microsoft::WRL::ComPtr<ID3D11DeviceContext> context_;  ///< GPU上での写しに使う。
    Microsoft::WRL::ComPtr<IMFSourceReader> reader_;  ///< デコード用の読み込み本体。所有する。
    std::deque<PendingFrame> pending_;                ///< 先読み中のコマ(古い順)。
    std::vector<Microsoft::WRL::ComPtr<ID3D11Texture2D>> stagingPool_;  ///< 使い回すステージングテクスチャ。
    bool endOfStream_ = false;                        ///< 先読み中に終端へ達したか。
    Mode mode_ = Mode::Cpu;                           ///< 使っているデコードの方式。
    DXGI_COLOR_SPACE_TYPE colorSpace_ = DXGI_COLOR_SPACE_YCBCR_STUDIO_G22_LEFT_P709;  ///< NV12の色の解釈。
    std::wstring indexMethod_;                        ///< 目次の作り方(説明表示用)。
    bool started_ = false;  ///< MFStartup()に成功したか(デストラクターでMFShutdown()するため)。

    std::vector<LONGLONG> timestamps_;  ///< 目次。コマ番号順の表示時刻(100ns単位、昇順)。
    std::vector<int> keyFrames_;        ///< キーフレームのコマ番号(昇順。必ず0を含む)。
    LONGLONG tolerance_ = 1;            ///< 時刻の照合で許す誤差(隣のコマとの間隔の半分未満)。
    int minimumIndex_ = 0;              ///< この番号より前のコマは返さない(シーク直後の壊れたコマ対策)。

    UINT32 bufferWidth_ = 0;   ///< デコード結果の幅(余白を含む)。
    UINT32 bufferHeight_ = 0;  ///< デコード結果の高さ(余白を含む)。
    LONG defaultStride_ = 0;   ///< 1行のバイト数。負なら下の行から並ぶ。
    RECT visible_{};           ///< 表示すべき範囲(1080pの動画が1088行で届く場合などに切り出す)。
    double frameRate_ = 0.0;
    std::wstring error_;
};

}  // namespace frameplayer
