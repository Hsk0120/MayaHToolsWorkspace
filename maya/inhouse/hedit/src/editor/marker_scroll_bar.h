/** @file marker_scroll_bar.h
 * @brief 印を描く縦のスクロールバー。検索の一致・問題・同じ名前・変更した行・カーソルの行の位置を、
 * 文書全体に対する割合でスクロールバーの上に示す(VS Codeの「概要ルーラー」)。
 */
#pragma once
#include <QColor>
#include <QList>
#include <QPixmap>
#include <QScrollBar>

namespace hedit {

/** @brief 印を描くスクロールバー(objectNameは``markerScrollBar``)。
 * @details 印は描くだけで、スクロールの動作はQScrollBarと同じ。コード欄が所有する
 * (QAbstractScrollArea::setVerticalScrollBarで渡すと、コード欄が親になる)。
 * スクロールのたびに描き直すので、カーソル以外の印(最大で数千個)は1枚の画像にまとめておき、
 * 印か大きさが変わったときだけ描き直す。カーソルの行は別に持ち、動いても画像は作り直さない。
 */
class MarkerScrollBar : public QScrollBar {
public:
    /** @brief 印の1つ。 */
    struct Marker {
        int line = 0;       ///< 行(0始まり)。
        QColor color;       ///< 色。
        int lane = 1;       ///< 横の位置。0=左(変更した行)・1=中央(検索・同じ名前)・2=右(問題)・3=全幅(カーソル)。
    };

    /** @brief スクロールバーを作る。 @param parent 所有者。 */
    explicit MarkerScrollBar(QWidget* parent = nullptr);

    /** @brief カーソル以外の印を置き換えて描き直す。 @param markers 印。 @param lineCount 文書の行数。 */
    void setMarkers(const QList<Marker>& markers, int lineCount);

    /** @brief カーソルの行の印を動かす(他の印の画像は作り直さない)。 @param line 行(0始まり)。 */
    void setCursorLine(int line);

    /** @brief 今の印(テスト用)。 @return カーソル以外の印。 */
    const QList<Marker>& markers() const { return markers_; }

    /** @brief 今のカーソルの行(テスト用)。 @return 行(0始まり)。 */
    int cursorLine() const { return cursorLine_; }

protected:
    /** @brief スクロールバーを描いてから、印を重ねる。 @param event 描き直す範囲。 */
    void paintEvent(QPaintEvent* event) override;

    /** @brief 大きさが変わったら、印の画像を作り直す。 @param event 大きさの変化。 */
    void resizeEvent(QResizeEvent* event) override;

private:
    /** @brief 溝(つまみが動く範囲)を返す。 @return 溝の範囲。求められなければ部品全体。 */
    QRect groove() const;

    /** @brief 行から、溝の中の縦の位置を求める。 @param line 行。 @param area 溝。 @param height 印の高さ。 @return y座標。 */
    int markerY(int line, const QRect& area, int height) const;

    QList<Marker> markers_;  ///< カーソル以外の印。
    int lineCount_ = 1;      ///< 文書の行数。
    int cursorLine_ = -1;    ///< カーソルの行。-1なら描かない。
    QPixmap cache_;          ///< カーソル以外の印を描いた画像。空なら次の描画で作る。
};

}  // namespace hedit
