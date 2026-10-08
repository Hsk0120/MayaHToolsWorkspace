/** @file output_panel.h
 * @brief 出力欄。Mayaの出力を取り出して保持し、表示モードで絞り込んで色付きで表示する。
 */
#pragma once
#include "core/output_message.h"
#include "editor/numbered_text_edit.h"
#include <QElapsedTimer>
#include <QList>
#include <QTimer>
#include <QWidget>
#include <functional>

class QComboBox;
class QShowEvent;

namespace hedit {

/** @brief 選択・コピーができる読み取り専用のテキスト欄(objectNameは``output``)。 */
class OutputView : public NumberedTextEdit {
public:
    /** @brief 読み取り専用で、マウスとキーボードで選択できる欄を作る。行番号は初期状態で隠す。 */
    OutputView();

protected:
    /** @brief Ctrl+C・Ctrl+Aを、Mayaのショートカットより先にこの欄で受け取る。
     * @param event Qtのイベント。
     * @return 処理した場合true。
     */
    bool event(QEvent* event) override;

    /** @brief Ctrl+C(コピー)とCtrl+A(全選択)を処理し、残りは基底クラスへ渡す。
     * @param event キー入力。
     */
    void keyPressEvent(QKeyEvent* event) override;
};

/** @brief 出力の表示モード。ツールバーの選択肢と同じ順番。 */
enum class OutputFilter {
    Normal = 0,              ///< 全て表示する。
    OutputOnly = 1,          ///< 実行したコマンドの履歴(History)を隠す。
    WarningsAndErrors = 2,   ///< 警告とエラーだけ。
    ErrorsOnly = 3,          ///< エラーだけ。
};

/** @brief 出力欄の全体(objectNameは``outputPanel``)。
 * @details Mayaの出力は、コンストラクターで受け取ったtakeOutput関数で取り出す。取り出すのは、
 * 出力が貯まったと知らされたとき(scheduleFlushの25ms後)・表示されたとき・Mayaの処理の途中(refreshNowで、
 * 出力が続くほど間隔を広げる)だけで、出力が無い間や非表示の間は何もしない。
 * 取り出したものは表示モードを切り替えても出し直せるよう、最大1Mi文字まで保持する。
 */
class OutputPanel : public QWidget {
public:
    /** @brief 出力欄と表示モードの選択欄を作る。
     * @param takeOutput Mayaの出力を取り出す関数。空なら出力を購読しない。
     * @param parent Qtの親。
     */
    explicit OutputPanel(std::function<QList<OutputMessage>()> takeOutput, QWidget* parent = nullptr);

    /** @brief テキスト欄を返す。 @return この部品が所有する欄。 */
    OutputView* view() const { return view_; }

    /** @brief 表示モードの選択欄を返す。
     * @return 選択欄。MainWindowがツールバーへ置き、置いた時点でツールバーが所有者になる。
     */
    QComboBox* filterSelector() const { return filterSelector_; }

    /** @brief 待機中のMayaの出力を取り出し、保持して表示する。 */
    void flush();

    /** @brief 出力が貯まったことを受けて取り出す。非表示なら何もしない(表示したときに取り出す)。
     * @details 前回の取り出しから25ms以上経っていればすぐ、そうでなければ残りの時間の後に取り出す
     * (続けて届く出力を1回の描画にまとめるため)。
     */
    void scheduleFlush();

    /** @brief 長いMayaの処理の途中でも出力を描き直す。再入はしない。
     * @details 間隔は、出力が続いた時間で広げる(1秒未満は100ms、3秒未満は500ms、それ以上は1秒)。
     * 描き直しは同期で重く、大量のエラーが続くときに全体を遅くするため。イベントループへ戻ったら100msへ戻す。
     */
    void refreshNow();

    /** @brief 今のその場での描き直しの間隔を返し、出力が続いている時間を更新する(refreshNowから呼ぶ)。
     * @return ミリ秒。
     */
    int immediateRefreshInterval();

    /** @brief heditの表示と保持している出力を消す。Mayaや他のエディタの出力は変えない。 */
    void clear();

    /** @brief heditからの案内を、保持せずに1行追加する。
     * @param text 追加する文字列。
     */
    void appendNote(const QString& text);

    /** @brief 長い行を欄の幅で折り返すかを切り替える。
     * @param wrap trueで折り返す。
     */
    void setWrap(bool wrap);

protected:
    /** @brief 表示されたら、閉じている間に貯まった出力をまとめて取り出す。 @param event 表示のイベント。 */
    void showEvent(QShowEvent* event) override;

private:
    /** @brief 表示モードで絞り込んで、文字色を付けて末尾へ追加する。
     * @param messages 追加する出力。
     * @details 利用者の選択範囲は保ち、新しい出力があれば最下部へスクロールする。
     * 新しい出力だけで表示の上限(5000行)を超える場合は、今の表示を空にしてから末尾の5000行だけを入れる。
     */
    void append(const QList<OutputMessage>& messages);

    /** @brief 表示する出力(表示モードで隠す種類を除く)のうち、表示の上限の行数に入る末尾の部分を返す。
     * @param messages 出力。
     * @param replaces 新しい出力だけで上限を超え、今の表示が全て押し出される場合にtrueを入れる。
     * @return 追加する出力。
     */
    QList<OutputMessage> shownTail(const QList<OutputMessage>& messages, bool* replaces) const;

    /** @brief 今の表示モードで、その出力を表示するか。
     * @param kind 出力の種類。
     * @return 表示するならtrue。
     */
    bool accepts(OutputKind kind) const;

    /** @brief 右クリックメニュー(標準のコピー等と「Clear output」)を出す。
     * @param point 右クリックした位置(欄の中の座標)。
     */
    void showContextMenu(const QPoint& point);

    std::function<QList<OutputMessage>()> takeOutput_;  ///< Mayaの出力を取り出す関数。
    OutputView* view_;                ///< テキスト欄。所有者はこの部品。
    QComboBox* filterSelector_;       ///< 表示モードの選択欄。
    QList<OutputMessage> history_;    ///< 表示モードの切り替え用に保持している出力。
    int historySize_ = 0;             ///< history_の文字数の合計。
    QTimer flushTimer_;               ///< 出力が貯まったと知らされてから25ms後にflush()を呼ぶ(1回だけ)。
    QElapsedTimer lastRefresh_;       ///< refreshNow()の前回の描画からの時間。
    QElapsedTimer lastFlush_;         ///< 前回、出力を取り出して描いてからの時間(続けて届く出力をまとめる判断)。
    QElapsedTimer lastRequest_;       ///< refreshNow()が前回呼ばれてからの時間(出力が続いているかの判断)。
    QElapsedTimer burst_;             ///< 出力が続き始めてからの時間。
    bool refreshing_ = false;         ///< refreshNow()の実行中か(再入の防止)。
};

}  // namespace hedit
