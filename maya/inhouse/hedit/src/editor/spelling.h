/** @file spelling.h
 * @brief Windows標準の英語辞書を使ったスペルチェック。外部の辞書は同梱しない。
 */
#pragma once
#include <QList>
#include <QPair>
#include <QString>
#include <memory>

namespace hedit {

/** @brief Windowsのスペルチェッカー(COM)と、単語ごとの結果のキャッシュを持つ。
 * @details COMはWindowsの部品を呼び出す仕組みで、スレッドごとに初期化が必要。
 * 作成・利用・破棄は画面のスレッド(Mayaのメインスレッド)だけで行う。
 * Windowsのヘッダーを他のファイルへ広げないよう、中身はImpl(pImplという書き方)に隠している。
 */
class Spelling {
public:
    /** @brief 辞書は最初の照会まで作らない。 */
    Spelling();

    /** @brief 自分が初期化したCOMと辞書だけを解放する。 */
    ~Spelling();

    /** @brief 英語辞書を1回だけ初期化する。 @return 使えるならtrue。 */
    bool available();

    /** @brief 表示範囲の英単語を調べる。大文字小文字・snake_case・camelCaseを単語に分ける。
     * @param text 最大8,000文字の表示範囲。全文は調べない。
     * @return 知らない単語の(開始位置, 長さ)の一覧。位置はUTF-16単位。Maya/Pythonの代表的な語は除く。
     */
    QList<QPair<int, int>> check(const QString& text);

private:
    struct Impl;                  ///< Windows固有の中身(spelling.cppで定義)。
    std::unique_ptr<Impl> impl_;  ///< 中身。
};

}  // namespace hedit
