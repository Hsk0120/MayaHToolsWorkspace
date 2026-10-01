/** @file output_capture.h
 * @brief Mayaの出力(print・警告・エラー・結果)を受け取り、編集画面へ渡すまで貯めておく。
 * @details 仕組み:
 * 1. 非表示のcmdScrollFieldReporter(Maya標準のScript Editorの出力欄と同じ部品)をMELで作る。
 *    Mayaはこの部品へ、Script Editorと同じ記号・改行で整形した出力を追記する。
 * 2. その部品の文書(QTextDocument)の追記(contentsChange)を購読して、追記された文字列を受け取る。
 * 3. 出力の種類(警告・エラーなど)は、MCommandMessageのコールバックで直前に通知された種類を使う。
 * 4. 受け取った出力はキューに貯め、編集画面がtake()で取り出す(25msごと、またはすぐ)。
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

namespace hedit {

/** @brief Mayaの出力の購読と、上限付きのキュー。
 * @details プラグインに1つだけ作る(outputCapture()で取り出す)。
 */
class OutputCapture {
public:
    /** @brief 起動前からの履歴をキューに入れ、出力の購読を始める。既に始めていれば何もしない。
     * @return 購読できた(または購読中)ならtrue。reporterを作れなかったらfalse。
     */
    bool start();

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

    /** @brief 出力を追記したときにすぐ描き直す画面を設定する。 @param editor 編集画面。nullptrなら描かない。 */
    void setEditor(QMainWindow* editor) { editor_ = editor; }

    /** @brief 貯まっている出力を全て取り出す(キューは空になる)。
     * @return 取り出した出力。上限を超えて捨てた分があれば、先頭にその案内を入れる。
     */
    QList<OutputMessage> take();

private:
    /** @brief Mayaが保持している過去の出力(最大512Ki文字)を、行ごとの種類を付けてキューへ入れる。 */
    void importHistory();

    /** @brief 出力の種類の通知と、reporterの文書の追記を購読する。 @return 購読できたらtrue。 */
    bool subscribe();

    /** @brief 受け取った出力をキューへ入れる。メインスレッドなら画面もすぐ描き直す。
     * @param text 出力の文字列。
     * @param kind 出力の種類。
     */
    void receive(QString text, OutputKind kind);

    /** @brief キューへ追加する。呼出側でmutex_を持っていること。
     * @param text 追加する文字列。
     * @param kind 種類。直前と同じ種類なら、直前の項目へつなげる。
     */
    void appendLocked(const QString& text, OutputKind kind);

    /** @brief MCommandMessageのコールバック。直前の出力の種類を覚える(文字列は使わない)。
     * @param message 出力の文字列(未使用)。
     * @param type 出力の種類。
     * @param clientData 登録時に渡したthis。
     * @note Mayaのコールバックは普通の関数(static)でなければならないので、clientDataでthisを受け取る。
     */
    static void onCommandOutput(const MString& message, MCommandMessage::MessageType type, void* clientData);

    QMutex mutex_;                          ///< pending_などを守る鍵。
    QList<OutputMessage> pending_;          ///< 画面へまだ渡していない出力。
    int pendingSize_ = 0;                   ///< pending_の文字数の合計。
    bool omitted_ = false;                  ///< 上限を超えて古い出力を捨てたか。
    bool fallback_ = false;                 ///< reporterが見つからず、通知の本文を自分で整えて取り込んでいるか。

    MCallbackId typeCallback_ = 0;                       ///< 出力の種類の通知のコールバック。
    MCommandMessage::MessageType lastType_ = MCommandMessage::kDisplay;  ///< 直前に通知された種類。
    QString reporterWindow_;                             ///< 非表示のreporterを入れたウィンドウのUI名。
    QPointer<QTextDocument> reporterDocument_;           ///< 購読中のreporterの文書。所有者はMaya。
    QMetaObject::Connection reporterConnection_;         ///< 文書の追記の購読(解除に使う)。
    QPointer<QMainWindow> editor_;                       ///< すぐ描き直す画面。
    bool exiting_ = false;                               ///< Mayaの終了処理中か。
};

/** @brief プラグインで1つだけのOutputCaptureを返す。 @return 共有のインスタンス。 */
OutputCapture& outputCapture();

/** @brief プラグインで1つだけの出力の取り込みを作る(initializePluginから呼ぶ)。 */
void createOutputCapture();

/** @brief 出力の取り込みを壊す(uninitializePluginの最後に呼ぶ。購読はstop()で外しておく)。 */
void destroyOutputCapture();

}  // namespace hedit
