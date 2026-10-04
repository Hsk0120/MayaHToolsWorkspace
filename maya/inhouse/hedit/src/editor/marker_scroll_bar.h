/** @file marker_scroll_bar.h
 * @brief 印を描く縦のスクロールバー。検索の一致・問題・同じ名前・変更した行・カーソルの行の位置を、
 * 文書全体に対する割合でスクロールバーの上に示す(VS Codeの「概要ルーラー」)。
 */
#pragma once
#include <QColor>
#include <QList>
#include <QScrollBar>

namespace hedit {

/** @brief 印を描くスクロールバー(objectNameは``markerScrollBar``)。
 * @details 印は描くだけで、スクロールの動作はQScrollBarと同じ。コード欄が所有する
 * (QAbstractScrollArea::setVerticalScrollBarで渡すと、コード欄が親になる)。
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

    /** @brief 印を置き換えて描き直す。 @param markers 印。 @param lineCount 文書の行数。 */
    void setMarkers(const QList<Marker>& markers, int lineCount);

    /** @brief 今の印(テスト用)。 @return 印。 */
    const QList<Marker>& markers() const { return markers_; }

protected:
    /** @brief スクロールバーを描いてから、印を重ねる。 @param event 描き直す範囲。 */
    void paintEvent(QPaintEvent* event) override;

private:
    QList<Marker> markers_;  ///< 印。
    int lineCount_ = 1;      ///< 文書の行数。
};

}  // namespace hedit
