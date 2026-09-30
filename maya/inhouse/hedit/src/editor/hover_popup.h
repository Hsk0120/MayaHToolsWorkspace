/** @file hover_popup.h
 * @brief 名前にマウスを重ねたときに出す説明(ホバー)。VS Codeのホバーと同じく、上に定義の見出し、下にdocstringを出す。
 * @details 見出しはエディターのフォントで色分けし(core/script_lexer.cppの字句解析を使う)、docstringは
 * Google形式の見出し(``Args:``など)を太字、``code``の部分をコードの色にする。長いdocstringはスクロールできる。
 * 閉じる条件: 名前とこの説明の外へマウスを動かしたとき・キー入力・スクロール・Esc。
 */
#pragma once
#include "core/completion_types.h"
#include <QFrame>
#include <QRect>
#include <QTimer>

class QTextBrowser;

namespace hedit {

/** @brief ホバーの説明の小窓(objectNameは``hoverPopup``)。
 * @details Qt::ToolTipの窓なので、表示してもコード欄からフォーカスを奪わない。
 * 親(コード欄)が所有し、コード欄と一緒に破棄される。
 */
class HoverPopup : public QFrame {
public:
    /** @brief 小窓を作る。作成直後は非表示。 @param parent 所有者(コード欄)。 */
    explicit HoverPopup(QWidget* parent);

    /** @brief 説明を表示する。
     * @param info 見出しとdocstring。
     * @param anchor 説明の対象の名前の範囲(画面全体の座標)。この上に出し、上に入らなければ下に出す。
     * @param codeFont 見出しとコードに使うフォント(エディターと同じもの)。
     */
    void showInfo(const HoverInfo& info, const QRect& anchor, const QFont& codeFont);

    /** @brief 名前の範囲(画面全体の座標)を返す。 @return 表示中の説明の対象。非表示なら空。 */
    QRect anchor() const { return isVisible() ? anchor_ : QRect(); }

    /** @brief 少し待ってから閉じる。待つ間にマウスが小窓へ入れば閉じない(小窓の中をスクロールできるように)。 */
    void scheduleHide();

    /** @brief 閉じる予約を取り消す。 */
    void cancelHide() { hideTimer_.stop(); }

    /** @brief 説明をHTMLにする(テスト用にも使う)。
     * @param info 見出しとdocstring。
     * @param codeFamily 見出しとコードのフォント名。
     * @return QTextDocumentで表示できるHTML。
     */
    static QString toHtml(const HoverInfo& info, const QString& codeFamily);

protected:
    /** @brief マウスが小窓へ入ったら閉じる予約を取り消し、出たら閉じる予約をする。
     * @param event イベント。
     * @return 基底クラスの結果。
     * @note enterEventは引数の型がQt5とQt6で違うため、event()でEnter・Leaveを受け取る。
     */
    bool event(QEvent* event) override;

private:
    QTextBrowser* view_;  ///< 説明の本文(スクロールできる)。所有者はこの小窓。
    QRect anchor_;        ///< 説明の対象の名前の範囲(画面全体の座標)。
    QTimer hideTimer_;    ///< 閉じる予約。
};

}  // namespace hedit
