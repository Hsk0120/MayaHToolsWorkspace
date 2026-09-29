/** @file numbered_text_edit.h
 * @brief 左端に行番号を描く複数行テキスト欄。コード欄と出力欄の共通の土台。
 */
#pragma once
#include <QPlainTextEdit>

namespace hedit {

/** @brief 行番号付きのQPlainTextEdit。行番号は描くだけで、文書の本文には含めない。
 * @details 行番号の分だけ左に余白(viewport margin)を空け、その余白に番号を描く。
 */
class NumberedTextEdit : public QPlainTextEdit {
public:
    /** @brief 行数・フォント・スクロールの変化に合わせて、行番号の欄を描き直すよう接続する。
     * @param parent 所有者。省略時は後でレイアウトへ追加したときに親が決まる。
     */
    explicit NumberedTextEdit(QWidget* parent = nullptr);

    /** @brief 行番号の表示を切り替える。本文や行移動には影響しない。
     * @param visible trueで行番号を表示する。
     */
    void setLineNumbersVisible(bool visible);

protected:
    /** @brief フォント変更時の幅の再計算と、行番号の描画を行う。それ以外は基底クラスへ渡す。
     * @param event Qtのイベント。Qtが所有する。
     * @return イベントを処理した場合true。
     */
    bool event(QEvent* event) override;

private:
    /** @brief 桁数とフォントから行番号の欄の幅を計算し、左の余白に反映する。 */
    void updateGutter();

    /** @brief 表示中の行の番号を、左の余白に描く。 */
    void paintLineNumbers();

    int gutterWidth_ = 54;         ///< 行番号の欄の幅(ピクセル)。非表示なら0。
    bool showLineNumbers_ = true;  ///< 行番号を表示するか。
};

}  // namespace hedit
