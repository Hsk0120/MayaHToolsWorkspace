/** @file hover_popup.h
 * @brief 名前にマウスを重ねたときに出す説明(ホバー)。VS Codeのホバーと同じく、上に定義の見出し、下にdocstringを出す。
 * @details 見出しはエディターのフォントで色分けし(core/script_lexer.cppの字句解析を使う)、docstringは
 * Google形式の見出し(``Args:``など)を太字、``code``の部分をコードの色にする。長いdocstringはスクロールできる。
 * 閉じる条件: 名前とこの説明の外へマウスを動かしたとき・キー入力・スクロール・Esc。
 */
#pragma once
#include "core/completion_types.h"
#include "core/signature_help.h"
#include <QFrame>
#include <QStringList>
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

    /** @brief 表示する位置。 */
    enum class Placement {
        Above,  ///< 対象の上(入らなければ下)。ホバー・引数のヒント。
        Below,  ///< 対象の下(入らなければ上)。問題の説明・定義をその場で見る。
        Right,  ///< 対象の右(入らなければ左)。補完の一覧の横の説明。
    };

    /** @brief 説明を表示する。
     * @param info 見出しとdocstring。
     * @param anchor 説明の対象の名前の範囲(画面全体の座標)。この上に出し、上に入らなければ下に出す。
     * @param codeFont 見出しとコードに使うフォント(エディターと同じもの)。
     * @param problems 同じ位置の問題(構文チェック)の説明。見出しより上に出す。
     */
    void showInfo(const HoverInfo& info, const QRect& anchor, const QFont& codeFont,
                  const QStringList& problems = QStringList());

    /** @brief 作ったHTMLを表示する(引数のヒント・定義をその場で見る・補完の説明)。
     * @details 表示中と同じ内容なら、HTMLの読み込みと大きさの計算を省いて位置だけを合わせる
     * (引数のヒントは入力のたびに出し直すため)。
     * @param html 表示するHTML。
     * @param anchor 対象の範囲(画面全体の座標)。
     * @param codeFont エディターのフォント。docstringの文字の大きさもこれに合わせる。
     * @param placement 表示する位置。
     * @param maximumWidth 最大の幅(拡大率100%のピクセル数)。0なら既定(560)。
     * @param maximumHeight 最大の高さ(拡大率100%のピクセル数)。0なら既定(320)。
     */
    void showHtml(const QString& html, const QRect& anchor, const QFont& codeFont, Placement placement = Placement::Above,
                  int maximumWidth = 0, int maximumHeight = 0);

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

    /** @brief 問題の説明をHTMLにする。 @param problems 説明。 @return HTMLの断片。 */
    static QString problemsHtml(const QStringList& problems);

    /** @brief 引数のヒントをHTMLにする(今の引数を太字と下線で示す)。
     * @param parts 引数ごとに分けた見出し。
     * @param active 今の引数の番号。-1なら強調しない。
     * @param doc docstring。空なら出さない。
     * @param codeFamily コードのフォント名。
     * @return HTML。
     */
    static QString signatureHelpHtml(const SignatureParts& parts, int active, const QString& doc,
                                     const QString& codeFamily);

    /** @brief 定義の周りのコードをHTMLにする(定義をその場で見る)。
     * @param title 見出し(``rig.py:13``)。
     * @param lines 表示する行。
     * @param firstLine linesの最初の行番号(1始まり)。
     * @param highlight 強調する行の番号(1始まり)。
     * @param codeFamily コードのフォント名。
     * @return HTML。
     */
    static QString snippetHtml(const QString& title, const QStringList& lines, int firstLine, int highlight,
                               const QString& codeFamily);

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
    QString contentKey_;  ///< 表示中の内容(HTML・文字の大きさ・最大の大きさ)。同じなら並べ直さない。
    QTimer hideTimer_;    ///< 閉じる予約。
};

}  // namespace hedit
