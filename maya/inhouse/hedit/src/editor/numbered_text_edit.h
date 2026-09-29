/** @file numbered_text_edit.h
 * @brief 左端に行番号を描く複数行テキスト欄。コード欄と出力欄の共通の土台。
 */
#pragma once
#include <QPlainTextEdit>

namespace hedit {

class LineNumberArea;

/** @brief 行番号付きのQPlainTextEdit。行番号は描くだけで、文書の本文には含めない。
 * @details 本文の左に余白(viewport margin)を空け、そこに行番号専用の部品(LineNumberArea)を重ねる。
 * スクロールや入力のときは、変わった範囲の行番号だけを描き直す(Qtの公式の例と同じ方法)。
 */
class NumberedTextEdit : public QPlainTextEdit {
public:
    /** @brief 行番号の部品を作り、行数・スクロールの変化に合わせて描き直すよう接続する。
     * @param parent 所有者。省略時は後でレイアウトへ追加したときに親が決まる。
     */
    explicit NumberedTextEdit(QWidget* parent = nullptr);

    /** @brief 行番号の表示を切り替える。本文や行移動には影響しない。
     * @param visible trueで行番号を表示する。
     */
    void setLineNumbersVisible(bool visible);

    /** @brief 行番号の欄の幅。 @return ピクセル数。非表示なら0。 */
    int gutterWidth() const { return gutterWidth_; }

    /** @brief 行番号を描く(LineNumberAreaのpaintEventから呼ばれる)。
     * @param event 描き直す範囲。
     */
    void paintLineNumbers(QPaintEvent* event);

protected:
    /** @brief フォントが変わったら、行番号の欄の幅を計算し直す。
     * @param event Qtのイベント。
     * @return イベントを処理した場合true。
     */
    bool event(QEvent* event) override;

    /** @brief 大きさが変わったら、行番号の部品の大きさも合わせる。 @param event 大きさの変化。 */
    void resizeEvent(QResizeEvent* event) override;

private:
    /** @brief 桁数とフォントから行番号の欄の幅を計算し、左の余白に反映する。 */
    void updateGutter();

    /** @brief 本文の描き直しに合わせて、行番号の必要な範囲だけを描き直す。
     * @param rect 描き直す本文の範囲。
     * @param dy 縦にスクロールした量(ピクセル)。
     */
    void onUpdateRequest(const QRect& rect, int dy);

    LineNumberArea* lineNumberArea_;  ///< 行番号の部品。所有者はこの欄。
    int gutterWidth_ = 54;            ///< 行番号の欄の幅(ピクセル)。非表示なら0。
    bool showLineNumbers_ = true;     ///< 行番号を表示するか。
};

}  // namespace hedit
