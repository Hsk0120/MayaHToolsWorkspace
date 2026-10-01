/**
 * @file FrameSource.h
 * @brief 動画などからコマを先頭から順に取り出す共通の窓口。
 *
 * プレイヤー本体はこの窓口だけを使う。読み込み方式(Media Foundation、連番画像、
 * 将来のProResなど)を追加するときは、このクラスの派生クラスを足して
 * openFrameSource()で選ぶようにする。
 */
#pragma once

#include <memory>
#include <string>

#include "core/Frame.h"

namespace frameplayer {

/**
 * @brief コマを先頭から順番に1つずつ返す読み込み元。
 * @note シーク(途中への移動)は意図的に用意しない。コマ番号は「何番目に返したか」で決まる。
 */
class FrameSource {
public:
    /** @brief 派生クラスの資源を解放する。 */
    virtual ~FrameSource() = default;

    /**
     * @brief 次のコマを読み込む。
     * @param out 読み込んだコマの格納先。失敗時の内容は未定義。
     * @return 読めた場合true。終端に達したか失敗した場合false(失敗ならerror()が空でない)。
     */
    virtual bool readNext(Frame& out) = 0;

    /**
     * @brief ファイルに記録されたフレームレートを返す。
     * @return 1秒あたりのコマ数。不明なら0。
     */
    virtual double frameRate() const = 0;

    /**
     * @brief 直近の失敗の説明を返す。
     * @return 失敗していなければ空文字列。
     */
    virtual const std::wstring& error() const = 0;
};

/**
 * @brief パスに合う読み込み元を開く。
 * @param path 開くファイルのパス。
 * @param error 失敗時に理由を格納する。
 * @return 開けた読み込み元。失敗時はnullptr。
 * @note 呼び出し元のスレッドでCOMが初期化済みである必要がある。
 */
std::unique_ptr<FrameSource> openFrameSource(const std::wstring& path, std::wstring& error);

}  // namespace frameplayer
