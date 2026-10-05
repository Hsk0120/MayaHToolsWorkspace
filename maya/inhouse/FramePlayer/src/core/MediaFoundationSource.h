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

#include <array>
#include <deque>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "core/ColorInfo.h"
#include "core/FrameRenderer.h"
#include "core/FrameSource.h"
#include "core/GpuDevice.h"

namespace frameplayer {

namespace detail {
class ReadCallback;  // 非同期の読み込みの結果を受け取る窓口(MediaFoundationSource.cppで定義)。
}

/**
 * @brief Media FoundationのSource Readerで動画を読む。
 * @note Windowsが標準で読める形式(H.264のmp4など)に対応する。
 *       開いたときに、デコードせずに圧縮されたままのコマを最後まで読み、表示時刻を並べ替えて
 *       「コマ番号→表示時刻」の目次とキーフレームの一覧を作る。デコードしたコマは表示時刻を
 *       目次と照合して番号を決めるので、途中から読んでも番号がずれない。
 *       コマはデコーダーが出すYUV(NV12・P010)のまま受け取り、Windowsの映像処理(色の変換・縮小)は通さない。
 *       RGBへの変換は描画のときにFrameRendererが色の解釈(color_)に従って行う。
 */
class MediaFoundationSource : public FrameSource {
public:
    /**
     * @brief 動画ファイルを開き、目次を作る。
     * @param path 動画ファイルのパス。
     * @param maxWidth 返すコマの最大幅。GPUのメモリに置く方式なら、自前のシェーダーでこの幅まで縮小して返す。
     * @param gpu 共有のGPUデバイス。nullptrならCPUでデコードする。
     * @param error 失敗時に理由を格納する。
     * @param purpose 使い道。Thumbnailsのときは主メモリへ写す方式とCPUの方式だけを試し、先読みはしない。
     * @return 開けた読み込み元。失敗時はnullptr。
     * @note GPUでNV12のままGPUのメモリに置く方式、GPUでデコードして主メモリへ写す方式、CPUでデコードする方式の順に試す。
     *       主メモリへ写す方式とCPUの方式では縮小しない。
     */
    static std::unique_ptr<MediaFoundationSource> open(const std::wstring& path, int maxWidth,
                                                       std::shared_ptr<GpuDevice> gpu, std::wstring& error,
                                                       SourcePurpose purpose = SourcePurpose::Playback);

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
    /** @copydoc FrameSource::releaseDecoder */
    void releaseDecoder() override;
    /** @copydoc FrameSource::error */
    const std::wstring& error() const override { return error_; }
    /** @copydoc FrameSource::description */
    std::wstring description() const override;

private:
    /** @brief デコードの方式。 */
    enum class Mode {
        Cpu,          ///< CPUでデコードし、YUVのまま主メモリに返す。
        GpuReadback,  ///< GPUでデコードし、YUVのまま主メモリへ写して返す。
        GpuTexture,   ///< GPUでデコード(必要なら自前で縮小)し、YUVのままGPUのメモリのテクスチャで返す。
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
     * @brief 全コマをデコードして、デコードしたコマの表示時刻で目次を作る。
     * @param path 動画ファイルのパス。
     * @return 作れた場合true。失敗時はerror_を設定してfalse。
     * @note 圧縮されたコマの一部に時刻が無い形式(MPEG-2のtsなど)のためのもの。時間がかかる。
     *       キーフレームは分からないので、全コマを候補にしてシークのときに確かめる。
     */
    bool buildIndexByDecoding(const std::wstring& path);

    /**
     * @brief デコード用の読み込み本体を作る。
     * @param path 動画ファイルのパス。
     * @param maxWidth GPUのときに縮小する最大幅。
     * @param mode デコードの方式。
     * @return 作れた場合true。失敗時はerror_を設定してfalse。
     */
    bool createReader(const std::wstring& path, int maxWidth, Mode mode);

    /**
     * @brief GPU上のデコード結果(NV12・P010)の表示範囲を、キャッシュ用の新しいテクスチャへ写してoutに入れる。
     *        キャッシュの最大幅より大きければ自前のシェーダーで縮小する。完了は待たない。
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
     * @brief 1つ読む(非同期で頼み、時間の上限まで待つ)。
     * @param flags 状態の印の格納先。
     * @param timestamp 時刻の格納先。
     * @param sample コマの格納先。
     * @param stalled 時間切れ(Windowsの読み込みが止まった)ならtrueを入れる。
     * @return 読み込みの結果。
     */
    HRESULT readSampleWithTimeout(DWORD& flags, LONGLONG& timestamp, Microsoft::WRL::ComPtr<IMFSample>& sample,
                                  bool& stalled);

    /**
     * @brief 止まった読み込み本体を見捨てて作り直し、最後に返したコマの続きから読めるようにする。
     * @return 作り直せたらtrue。回数の上限を超えた・作り直せない場合はerror_を設定してfalse。
     */
    bool recoverFromStall();

    /**
     * @brief readNext()の本体。
     * @param out 格納先。
     * @param index コマ番号の格納先。
     * @return 読めた場合true。
     */
    bool readNextFrame(Frame& out, int& index);

    /**
     * @brief GPU上のコマを主メモリから読めるテクスチャへ写す命令を出し、先読みの列に加える。完了は待たない。
     * @param sample GPU上にあるコマ。
     * @param index コマ番号。
     * @return 命令を出せた場合true。GPU上のコマでない、NV12・P010でないなどの場合false。
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
     * @brief YUVの明るさの面と色の面から表示範囲を切り出し、主メモリのコマとしてoutへ写す。
     * @param luma 明るさの面の先頭行の位置。
     * @param chroma 色の面の先頭行の位置。
     * @param pitch 1行のバイト数(明るさの面と色の面で同じ)。
     * @param visible 切り出す範囲(明るさの画素の単位。位置と大きさは偶数)。
     * @param out 格納先。
     */
    void copyPlanes(const BYTE* luma, const BYTE* chroma, LONG pitch, const RECT& visible, Frame& out) const;

    /**
     * @brief 色の解釈(color_)を決め直す。
     * @param outputType デコーダーの出力の形式。最初のコマをデコードした後は、動画の中の色の情報が入っている。
     * @note 優先順(後のものほど優先): 大きさからの推定、デコーダーの出力の形式、動画の形式、mp4/movのcolrボックス。
     */
    void updateColor(IMFMediaType* outputType);

    /** @brief 先読みしていたコマを捨てる(シーク時など)。 */
    void clearPending();

    /**
     * @brief 出力形式(大きさ・行の間隔・表示範囲・色の解釈)を読み直す。
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
    Microsoft::WRL::ComPtr<detail::ReadCallback> callback_;  ///< reader_の非同期の読み込みの結果を受け取る窓口。
    int lastDelivered_ = -1;                          ///< 最後にreadNext()で返したコマ番号(止まったときの再開位置)。
    int stallRecoveries_ = 0;                         ///< 今のreadNext()の中で作り直した回数。
    Frame heldFrame_;                                 ///< 開いたときに試しに読んだ先頭のコマ(最初のreadNext()で返す)。
    int heldIndex_ = -1;                              ///< heldFrame_のコマ番号。
    bool hasHeldFrame_ = false;                       ///< heldFrame_を持っているか。
    std::deque<PendingFrame> pending_;                ///< 先読み中のコマ(古い順)。
    std::vector<Microsoft::WRL::ComPtr<ID3D11Texture2D>> stagingPool_;  ///< 使い回すステージングテクスチャ。
    bool endOfStream_ = false;                        ///< 先読み中に終端へ達したか。
    Mode mode_ = Mode::Cpu;                           ///< 使っているデコードの方式。
    PixelLayout layout_ = PixelLayout::Nv12;          ///< デコーダーから受け取る並び(NV12かP010)。
    ColorInfo color_;                                 ///< 色の解釈(返すコマに付ける)。
    ColorInfo nativeColor_;                           ///< 動画の形式(圧縮されたまま)に付いていた色の情報。
    bool nativeDescribed_ = false;                    ///< nativeColor_に行列・色域・伝達関数のどれかがあるか。
    bool colorChecked_ = false;                       ///< 最初のコマの後で色の情報を読み直したか。
    GUID codec_ = GUID_NULL;                          ///< 動画の圧縮形式(MJPEGの色の位置の判断に使う)。
    std::array<int, 4> mp4Color_{-1, -1, -1, -1};     ///< mp4/movのcolr(色域・伝達関数・行列・全範囲)。無ければ負。
    int sourceBitDepth_ = 0;                          ///< mp4/movの設定ボックスから分かったビット数。不明なら0。
    float pixelAspect_ = 1.0f;                        ///< 1画素の横÷縦(返すコマに付ける)。
    bool orderBased_ = false;                         ///< 表示時刻が無い入れ物(avi)なので、出た順番でコマ番号を決めるか。
    int nextOrderIndex_ = 0;                          ///< orderBased_のとき、次に出るコマの番号。
    bool keyFramesUncertain_ = false;                 ///< キーフレームの印が当てにならない(シークのときに確かめる)か。
    std::map<int, int> seekStarts_;                   ///< 確かめたシーク位置(最初に出るコマ → シークしたコマ)。
    /// 先に読んで取っておいたコマと番号(シークを確かめたとき・番号の基準を決めたときに読んだもの。次から順に返す)。
    std::deque<std::pair<Microsoft::WRL::ComPtr<IMFSample>, int>> queued_;
    bool timestampsUnreliable_ = false;               ///< シーク直後のデコーダーの時刻が当てにならない(MPEG-1/2)か。
    bool anchored_ = false;                           ///< timestampsUnreliable_のとき、番号の基準が決まったか。
    Microsoft::WRL::ComPtr<IMFSample> anchorCandidate_;  ///< 基準の候補(直前に読んだコマ)。
    int anchorCandidateIndex_ = -1;                   ///< anchorCandidate_の時刻から求めたコマ番号。
    Microsoft::WRL::ComPtr<ID3D11Texture2D> copyTexture_;  ///< 縮小する前に写す先(使い回す)。
    std::unique_ptr<FrameRenderer> scaler_;           ///< GPUのメモリに置くコマを縮小するシェーダー。
    std::wstring indexMethod_;                        ///< 目次の作り方(説明表示用)。
    std::wstring path_;                               ///< 開いたファイル(デコーダーを作り直すときに使う)。
    int maxWidth_ = 0;                                ///< 縮小する最大幅(デコーダーを作り直すときに使う)。
    std::size_t pipelineDepth_ = 1;                   ///< GPUから主メモリへ写すときに先に命令しておくコマ数。
    bool started_ = false;  ///< MFStartup()に成功したか(デストラクターでMFShutdown()するため)。

    std::vector<LONGLONG> timestamps_;  ///< 目次。コマ番号順の表示時刻(100ns単位、昇順)。
    std::vector<int> keyFrames_;        ///< キーフレームのコマ番号(昇順。必ず0を含む)。
    LONGLONG tolerance_ = 1;            ///< 時刻の照合で許す誤差(隣のコマとの間隔の半分未満)。
    int minimumIndex_ = 0;              ///< この番号より前のコマは返さない(シーク直後の壊れたコマ対策)。

    UINT32 bufferWidth_ = 0;   ///< デコード結果の幅(余白を含む)。
    UINT32 bufferHeight_ = 0;  ///< デコード結果の高さ(余白を含む)。
    LONG defaultStride_ = 0;   ///< 明るさの面の1行のバイト数(2Dバッファで読めないときに使う)。
    RECT visible_{};           ///< 表示すべき範囲(1080pの動画が1088行で届く場合などに切り出す。偶数に揃える)。
    double frameRate_ = 0.0;
    std::wstring error_;
};

}  // namespace frameplayer
