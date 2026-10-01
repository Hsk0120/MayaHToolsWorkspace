/**
 * @file MediaFoundationSource.h
 * @brief Windows標準のMedia Foundationで動画を読む読み込み元。
 */
#pragma once

#include <windows.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wrl/client.h>

#include <memory>
#include <string>

#include "core/FrameSource.h"

namespace frameplayer {

/**
 * @brief Media FoundationのSource Readerで動画を先頭から順に読む。
 * @note Windowsが標準で読める形式(H.264のmp4など)に対応する。
 *       色変換はSource Readerの映像処理機能に任せ、BGRA(RGB32)で受け取る。
 */
class MediaFoundationSource : public FrameSource {
public:
    /**
     * @brief 動画ファイルを開く。
     * @param path 動画ファイルのパス。
     * @param error 失敗時に理由を格納する。
     * @return 開けた読み込み元。失敗時はnullptr。
     */
    static std::unique_ptr<MediaFoundationSource> open(const std::wstring& path, std::wstring& error);

    /** @brief Media Foundationの利用を終了する(open()で開始した分と対になる)。 */
    ~MediaFoundationSource() override;

    MediaFoundationSource(const MediaFoundationSource&) = delete;
    MediaFoundationSource& operator=(const MediaFoundationSource&) = delete;

    /** @copydoc FrameSource::readNext */
    bool readNext(Frame& out) override;
    /** @copydoc FrameSource::frameRate */
    double frameRate() const override { return frameRate_; }
    /** @copydoc FrameSource::error */
    const std::wstring& error() const override { return error_; }

private:
    /** @brief open()以外から作らせないための非公開コンストラクター。 */
    MediaFoundationSource() = default;

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

    Microsoft::WRL::ComPtr<IMFSourceReader> reader_;  ///< 読み込み本体。所有する。
    bool started_ = false;  ///< MFStartup()に成功したか(デストラクターでMFShutdown()するため)。
    UINT32 bufferWidth_ = 0;   ///< デコード結果の幅(余白を含む)。
    UINT32 bufferHeight_ = 0;  ///< デコード結果の高さ(余白を含む)。
    LONG defaultStride_ = 0;   ///< 1行のバイト数。負なら下の行から並ぶ。
    RECT visible_{};           ///< 表示すべき範囲(1080pの動画が1088行で届く場合などに切り出す)。
    double frameRate_ = 0.0;
    std::wstring error_;
};

}  // namespace frameplayer
