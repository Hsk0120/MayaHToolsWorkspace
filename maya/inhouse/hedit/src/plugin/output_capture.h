/** @file output_capture.h
 * @brief Mayaの出力(print・警告・エラー・結果)を受け取り、編集画面へ渡すまで貯めておく。
 * @details 取り込み方は2つある(Preferencesの「Exact Script Editor output format」で選ぶ):
 * - 速い方式(既定): MCommandMessageの通知の本文を、core/history_text.cppのformatCommandOutputで
 *   Script Editorと同じ形に整える。Pythonから呼んだcmds.warning・cmds.errorの先頭が``#``ではなく``//``になる
 *   ことだけが違う。
 * - 正確な方式: 非表示のcmdScrollFieldReporter(Script Editorの出力欄と同じ部品)をMELで作り、Mayaが整形して
 *   追記した文字列(QTextDocumentのcontentsChange)を受け取る。種類は直前の通知で知る。見た目はScript Editorと
 *   同じだが、Mayaはこの部品への追記にScript Editorを1つ開いているのと同じ時間をかける(大量のエラーで遅い)。
 *   そのため編集画面を閉じている間は速い方式で受け取り、表示したときに正確な方式へ戻す。
 * 受け取った出力はキューに貯め、キューが空から1件になったときだけ、編集画面へ取り出しを頼む
 * (出力が無いときは何も動かない。編集画面を閉じている間は頼まず、表示したときにまとめて取り出す)。
 * 標準のScript Editorの設定・履歴は変更しない。
 */
#pragma once
#include "core/output_message.h"
#include <QList>
#include <QMainWindow>
#include <QMetaObject>
#include <QMutex>
#include <QPointer>
#include <QString>
#include <QTextDocument>
#include <maya/MCommandMessage.h>
#include <maya/MMessage.h>
#include <atomic>

class QObject;
class QTimer;

namespace hedit {

/** @brief Mayaの出力の購読と、上限付きのキュー。
 * @details プラグインに1つだけ作る(outputCapture()で取り出す)。作成・破棄はメインスレッドで行う。
 */
class OutputCapture {
public:
    /** @brief 出力の取り込み方。 */
    enum class Mode {
        Fast,   ///< 通知の本文を自分で整える(既定)。
        Exact,  ///< 非表示のreporterがMayaに整形させた文字を受け取る(遅い)。
    };

    /** @brief 編集画面への通知に使うQtの部品(イベントフィルター・タイマー)を用意する。 */
    OutputCapture();

    /** @brief 通知の部品を破棄する。予約済みの通知(まだ実行していないキューの呼出し)も一緒に取り消される。 */
    ~OutputCapture();

    OutputCapture(const OutputCapture&) = delete;             ///< 複製しない(コールバックがthisを持つ)。
    OutputCapture& operator=(const OutputCapture&) = delete;  ///< 複製しない。

    /** @brief 起動前からの履歴をキューに入れ、出力の購読を始める。既に始めていれば何もしない。
     * @return 購読できた(または購読中)ならtrue。
     * @note 正確な方式のreporterは、編集画面が表示されたときに作る(閉じている間はMayaに負荷をかけない)。
     */
    bool start();

    /** @brief 取り込み方を変える。購読中なら、履歴を取り込み直さずにその場で切り替える。
     * @param mode 取り込み方。Exactでreporterが見つからないMayaでは、Fastのまま動く。
     * 編集画面が非表示の間は、Exactを選んでいてもFastで受け取る。
     */
    void setMode(Mode mode);

    /** @brief 今の取り込み方(テスト用)。 @return reporterを購読していればExact。 */
    Mode activeMode() const { return exact_.load() ? Mode::Exact : Mode::Fast; }

    /** @brief 購読をやめ、非表示のreporterを削除する。
     * @return コールバックの解除の結果。
     */
    MStatus stop();

    /** @brief Mayaの終了が始まったときに呼ぶ。以後の出力を画面へ渡さない。
     * @details 終了処理中もMayaはreporterへ追記するが、そのときの画面は解体途中で、
     * 描画するとQtのアクセシビリティ更新で落ちる。
     */
    void stopForExit();

    /** @brief プラグインのロード時に、終了の印を戻す。 */
    void resetExitState() { exiting_ = false; }

    /** @brief 出力を渡す編集画面を設定する。表示・非表示を見張り、取り込み方を合わせる。
     * @param editor 編集画面。nullptrなら描かない。
     */
    void setEditor(QMainWindow* editor);

    /** @brief 貯まっている出力を全て取り出す(キューは空になる)。
     * @return 取り出した出力。上限を超えて捨てた分があれば、先頭にその案内を入れる。
     */
    QList<OutputMessage> take();

private:
    /** @brief Mayaが保持している過去の出力(最大512Ki文字)を、行ごとの種類を付けてキューへ入れる。 */
    void importHistory();

    /** @brief 非表示のreporterを作り、その文書の追記を購読する(正確な方式)。
     * @return 購読できたらtrue。reporterの文書が見つからなければfalse(作った部品は片付ける)。
     */
    bool subscribeReporter();

    /** @brief reporterの文書の購読をやめ、非表示のreporterを削除する。 */
    void unsubscribeReporter();

    /** @brief 選ばれている取り込み方と編集画面の表示状態から、reporterを作る・消す。 */
    void applyMode();

    /** @brief 編集画面の表示・非表示が変わったときに呼ぶ(イベントフィルターから)。
     * @param visible 表示されたならtrue。
     * @details 非表示は1秒待ってから反映する(ドックの付け替えなどの一瞬の非表示で、reporterを作り直さない)。
     */
    void onEditorVisibilityChanged(bool visible);

    /** @brief 受け取った出力をキューへ入れる。メインスレッドなら画面もすぐ描き直す。
     * @param text 出力の文字列。
     * @param kind 出力の種類。
     */
    void receive(QString text, OutputKind kind);

    /** @brief キューへ追加する。呼出側でmutex_を持っていること。
     * @param text 追加する文字列。
     * @param kind 種類。直前と同じ種類なら、直前の項目へつなげる。
     * @return 編集画面へ取り出しを頼む必要があればtrue(頼んだ後、take()されるまでは1回だけ)。
     */
    bool appendLocked(const QString& text, OutputKind kind);

    /** @brief 編集画面へ取り出しを頼む。どのスレッドからでも呼べる。
     * @details notifier_のスレッド(メインスレッド)で、イベントループへ戻ったときに実行される。
     */
    void postNotification();

    /** @brief MCommandMessageのコールバック。速い方式では本文を整えてキューへ入れ、正確な方式では種類だけを覚える。
     * @param message 出力の文字列。
     * @param type 出力の種類。
     * @param clientData 登録時に渡したthis。
     * @note Mayaのコールバックは普通の関数(static)でなければならないので、clientDataでthisを受け取る。
     * Pythonの別スレッドの出力では、メインスレッド以外から呼ばれる。
     */
    static void onCommandOutput(const MString& message, MCommandMessage::MessageType type, void* clientData);

    QMutex mutex_;                          ///< pending_などを守る鍵。
    QList<OutputMessage> pending_;          ///< 画面へまだ渡していない出力。
    int pendingSize_ = 0;                   ///< pending_の文字数の合計。
    bool omitted_ = false;                  ///< 上限を超えて古い出力を捨てたか。
    bool notifyPending_ = false;            ///< 取り出しを頼んだ後、まだtake()されていないか(mutex_で守る)。
    bool running_ = false;                  ///< 購読中か。
    Mode mode_ = Mode::Fast;                ///< 選ばれている取り込み方。
    bool editorVisible_ = false;            ///< 編集画面が表示されているか。
    bool reporterWarned_ = false;           ///< reporterが見つからない警告を出したか(表示のたびに出さない)。
    MCallbackId typeCallback_ = 0;                       ///< 出力の種類の通知のコールバック。
    MCommandMessage::MessageType lastType_ = MCommandMessage::kDisplay;  ///< 直前に通知された種類。
    QString reporterWindow_;                             ///< 非表示のreporterを入れたウィンドウのUI名。
    QPointer<QTextDocument> reporterDocument_;           ///< 購読中のreporterの文書。所有者はMaya。メインスレッドだけで使う。
    QMetaObject::Connection reporterConnection_;         ///< 文書の追記の購読(解除に使う)。
    QPointer<QMainWindow> editor_;                       ///< 出力を渡す編集画面。
    /// reporterを購読しているか。別のスレッドの通知(onCommandOutput)からも読むのでatomicにする
    /// (QPointerのreporterDocument_は、メインスレッド以外から読むと切り替えの途中と競合しうる)。
    std::atomic<bool> exact_{false};
    std::atomic<bool> exiting_{false};                   ///< Mayaの終了処理中か(別のスレッドからも読む)。
    QObject* notifier_ = nullptr;                        ///< 取り出しの依頼をメインスレッドへ送る相手。所有者はこのクラス。
    QObject* watcher_ = nullptr;                         ///< 編集画面の表示・非表示を見張るフィルター。所有者はnotifier_。
    QTimer* hideTimer_ = nullptr;                        ///< 非表示を1秒待ってから反映するタイマー。所有者はnotifier_。
};

/** @brief プラグインで1つだけのOutputCaptureを返す。 @return 共有のインスタンス。 */
OutputCapture& outputCapture();

/** @brief プラグインで1つだけの出力の取り込みを作る(initializePluginから呼ぶ)。 */
void createOutputCapture();

/** @brief 出力の取り込みを壊す(uninitializePluginの最後に呼ぶ。購読はstop()で外しておく)。 */
void destroyOutputCapture();

}  // namespace hedit
