/** @file numbered_text_edit.h
 * @brief 左端に行番号を描く複数行テキスト欄。コード欄と出力欄の共通の土台。
 */
#pragma once
#include <QPlainTextEdit>

class QPainter;

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

    /** @brief 行番号の欄の幅(行番号の右の追加の欄を含む)。 @return ピクセル数。非表示なら0。 */
    int gutterWidth() const { return gutterWidth_; }

    /** @brief 行番号の数字を描く部分の幅。 @return ピクセル数。これより右がextraGutterWidth()の欄。 */
    int numberWidth() const { return numberWidth_; }

    /** @brief 行番号の部品(テストと、追加の欄の描き直しに使う)。 @return 部品。所有者はこの欄。 */
    QWidget* gutter() const;

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

    /** @brief 行番号の右に足す欄の幅(コード欄の折りたたみの矢印など)。 @return ピクセル数。既定は0。 */
    virtual int extraGutterWidth() const { return 0; }

    /** @brief 1行分の、行番号の欄の追加の描画(変更の印・折りたたみの矢印)。既定は何もしない。
     * @param painter 行番号の部品の描画。
     * @param block 行。
     * @param rect その行の、行番号の部品の中での範囲。
     */
    virtual void paintGutterBlock(QPainter& painter, const QTextBlock& block, const QRectF& rect);

    /** @brief 全ての行を描いた後の、行番号の欄の上に重ねる描画(見出しの固定表示の行番号)。既定は何もしない。
     * @param painter 行番号の部品の描画。
     * @param rect 描き直す範囲。
     */
    virtual void paintGutterOverlay(QPainter& painter, const QRect& rect);

    /** @brief 行番号の欄がクリックされた(折りたたみの矢印など)。既定は何もしない。 @param position 部品の中の位置。 */
    virtual void gutterPressed(const QPoint& position);

    /** @brief 表示部分の中の、行の上端の位置を返す(行の縦の位置の起点)。
     * @param block 行。通常はfirstVisibleBlock()。
     * @return 表示部分の座標のy。
     * @note 続く行の位置は、この値に各行の高さ(blockBoundingRect(行).height()、隠した行は0)を足して求める。
     * Qtの blockBoundingGeometry は、表示中の最初の行からその行までの高さを毎回足し直すため、行ごとに呼ぶと
     * 行数の2乗に比例する(畳んで隠した行が多いと特に重い)。
     */
    qreal blockTop(const QTextBlock& block) const;

    /** @brief 桁数とフォントから行番号の欄の幅を計算し、左の余白に反映する。
     * @param force falseなら、幅が変わらないときは何もしない(行数が変わるたびに呼ぶため)。
     * フォントや表示の切り替えではtrue(タブ幅も設定し直す)。
     */
    void updateGutter(bool force = true);

private:
    friend class LineNumberArea;

    /** @brief 本文の描き直しに合わせて、行番号の必要な範囲だけを描き直す。
     * @param rect 描き直す本文の範囲。
     * @param dy 縦にスクロールした量(ピクセル)。
     */
    void onUpdateRequest(const QRect& rect, int dy);

    LineNumberArea* lineNumberArea_;  ///< 行番号の部品。所有者はこの欄。
    int gutterWidth_ = 54;            ///< 行番号の欄の幅(ピクセル)。非表示なら0。
    int numberWidth_ = 54;            ///< 行番号の数字を描く部分の幅(ピクセル)。
    bool showLineNumbers_ = true;     ///< 行番号を表示するか。
};

}  // namespace hedit
