/** @file code_assist.h
 * @brief 入力の補助(補完・名前の説明(ホバー)・構文チェック・スペルチェック)をまとめたもの。
 * @details 以前はMainWindowの中にあった。MainWindowは画面の組み立て・タブ・ファイル・保存を担当し、
 * 「入力が止まったら何をするか」はこのクラスが担当する。
 * どれもMayaの処理(EditorServicesの関数)を呼ぶが、Maya の API は直接呼ばない。
 */
#pragma once
#include "core/completion_types.h"
#include "editor/editor.h"
#include "editor/spelling.h"
#include <QObject>
#include <QPointer>
#include <QTimer>
#include <functional>

class QLabel;

namespace hedit {

class CodeEditor;
class EditorPreferences;
class ProblemsPanel;

/** @brief 入力の補助。MainWindowが1つ持つ。 */
class CodeAssist : public QObject {
public:
    /** @brief MainWindowから受け取る、画面の状態を調べる関数の一式。 */
    struct Context {
        std::function<CodeEditor*()> currentEditor;          ///< 選択中のタブのコード欄。
        std::function<QList<CodeEditor*>()> editors;         ///< 全てのタブのコード欄。
        std::function<void(const QString&, int)> showStatus; ///< ステータスバーへ文字を出す(文字, ミリ秒)。
    };

    /** @brief タイマーを用意する。
     * @param services Mayaの処理の一式(補完・ホバー・構文チェック)。呼出側がこのオブジェクトより長く持つ。
     * @param preferences 設定。呼出側がこのオブジェクトより長く持つ。
     * @param problems 構文チェックの一覧。所有者はMainWindow。
     * @param completionStatus ステータスバーの補完の状態。所有者はMainWindow。
     * @param context 画面の状態を調べる関数。
     */
    CodeAssist(const EditorServices& services, const EditorPreferences& preferences, ProblemsPanel* problems,
               QLabel* completionStatus, Context context);

    /** @brief コード欄に、Ctrl+Spaceとホバーの問い合わせ先を設定する(新しいタブを作ったときに呼ぶ)。
     * @param editor コード欄。
     */
    void attach(CodeEditor* editor);

    /** @brief 本文が変わったときに呼ぶ。補完・構文チェック・スペルチェックを予約し直す。
     * @param editor 本文が変わったコード欄。
     */
    void onTextChanged(CodeEditor* editor);

    /** @brief 選択中のタブが変わったときに呼ぶ。予約中の補完をやめ、構文チェックとスペルチェックをやり直す。 */
    void onCurrentChanged();

    /** @brief 補完の情報を取り直す(Command → Refresh completion)。 */
    void refreshCompletion();

    /** @brief 入力が止まってから構文チェックするよう予約する。設定がオフなら一覧を隠す。 */
    void scheduleAnalysis();

    /** @brief 入力が止まってからスペルチェックするよう予約する。オフなら全タブの波線を消す。 */
    void scheduleSpelling();

    /** @brief 現在の位置の補完候補を求めて表示する。 @param force Ctrl+Spaceからならtrue(自動補完の設定を無視する)。 */
    void requestCompletion(bool force);

    /** @brief カーソルが関数の呼出しの中なら、引数のヒントを出す。中でなければ閉じる。
     * @param editor コード欄。
     */
    void updateSignatureHelp(CodeEditor* editor);

    /** @brief 補完の一覧で選んでいる候補の説明を、一覧の横に出す。 @param editor コード欄。 */
    void updateCompletionDetail(CodeEditor* editor);

private:
    /** @brief 名前の説明を求める。同じ本文・同じ位置なら前回の結果を使う(Pythonへ問い合わせ直さない)。
     * @param editor コード欄。
     * @param end 名前の終わりの位置。
     * @return 見出しとdocstring。MELのタブ・大きすぎる本文・説明が無い名前は空。
     */
    HoverInfo describe(CodeEditor* editor, int end);

    /** @brief 選択中のPythonタブを構文チェックする(実行はしない)。 */
    void runAnalysis();

    /** @brief 補完の問い合わせの失敗をステータスバーに出す。 @param error 理由。 */
    void showCompletionError(const QString& error);

    const EditorServices& services_;        ///< Mayaの処理の一式。
    const EditorPreferences& preferences_;  ///< 設定。
    ProblemsPanel* problems_;               ///< 構文チェックの一覧。
    QLabel* completionStatus_;              ///< ステータスバーの補完の状態。
    Context context_;                       ///< 画面の状態を調べる関数。
    Spelling spelling_;                     ///< Windowsの英語辞書。
    QTimer completionTimer_;                ///< 入力が止まって250ms後に自動補完する。
    QTimer analysisTimer_;                  ///< 入力が止まって800ms後に構文チェックする。
    QTimer spellingTimer_;                  ///< 入力が止まって450ms後にスペルチェックする。
    QTimer signatureTimer_;                 ///< 入力・カーソル移動が止まって60ms後に引数のヒントを出し直す。
    QTimer detailTimer_;                    ///< 候補の選択が止まって120ms後に候補の説明を出す。
    QPointer<CodeEditor> signatureEditor_;  ///< 引数のヒントを求めたコード欄。
    QPointer<CodeEditor> detailEditor_;     ///< 候補の説明を求めたコード欄。

    /** @brief 前回のホバーの結果(同じ名前の上で何度もQEvent::ToolTipが来ても問い合わせ直さない)。 */
    struct HoverCache {
        QPointer<CodeEditor> editor;  ///< コード欄。
        int revision = -1;            ///< 文書の版(QTextDocument::revision)。本文が変わると変わる。
        int end = -1;                 ///< 名前の終わりの位置。
        HoverInfo info;               ///< 結果。
    } hoverCache_;
};

}  // namespace hedit
