/** @file language_assist.h
 * @brief 編集中の全文をLSPへ共有し、応答を文書の世代と照合して表示する。
 */
#pragma once
#include "core/language_client.h"
#include "core/completion_types.h"
#include <QJsonArray>
#include <QPointer>
#include <QSet>
#include <QFileSystemWatcher>
#include <QTextDocument>
#include <functional>

namespace mce {
class CodeEditor;
class EditorPreferences;
class ProblemsPanel;
/** @brief 型解析を画面へ接続する。Pythonソースをimport/実行しない。 */
class LanguageAssist : public QObject {
public:
    /** @brief 画面から必要な操作だけを受け取る。 */
    struct Context {
        std::function<CodeEditor*()> current;
        std::function<QList<CodeEditor*>()> editors;
        std::function<CodeEditor*(const QString&)> open;
        std::function<void(CodeEditor*)> activate;
        std::function<void(const QString&)> status;
        std::function<CompletionResult(const QString&)> fallbackComplete;
        std::function<void(CodeEditor*)> ensureLoaded;
    };
    /** @brief 接続を作る。 @param config Mayaの解析環境。 @param preferences 表示設定。 @param problems 問題一覧。 @param context 操作。 @param parent 所有者。 */
    LanguageAssist(QJsonObject config, const EditorPreferences& preferences, ProblemsPanel* problems, Context context, QObject* parent);
    /** @brief 自身のプロセスを終了する。 */
    ~LanguageAssist() override;
    /** @brief 新しいタブを登録する。 @param editor 対象。 */
    void attach(CodeEditor* editor);
    /** @brief 全タブの本文と保存先を同期する。 */
    void sync();
    /** @brief 応答受付可能か。 @return 初期化済みならtrue。 */
    bool ready() const { return client_.ready(); }
    /** @brief 設定を反映し解析表示を更新する。 */
    void refresh();
    /** @brief 補完を非同期要求する。 @param editor 対象。 @return 受付したか。 */
    bool complete(CodeEditor* editor);
    /** @brief 現在の候補の型と説明を非同期で表示する。 @param editor 対象。 */
    void detail(CodeEditor* editor);
    /** @brief 引数ヒントを非同期要求する。 @param editor 対象。 @return 受付したか。 */
    bool signature(CodeEditor* editor);
    /** @brief ホバーを非同期要求する。 @param editor 対象。 @param end 名前の末尾。 @return 受付したか。 */
    bool hover(CodeEditor* editor, int end);
    /** @brief 定義または参照を選んで移動する。 @param editor 対象。 @param references 参照検索か。 @param peek 下見か。 */
    void navigate(CodeEditor* editor, bool references, bool peek = false);
    /** @brief 名前変更案を取得して下見する。 @param editor 対象。 */
    void rename(CodeEditor* editor);
    /** @brief 選択範囲への修正案を取得する。 @param editor 対象。 */
    void actions(CodeEditor* editor);
    /** @brief 抽出/移動/import整理の案を別プロセスで計算する。 @param editor 対象。 @param action variable/function/move/imports。 */
    void refactor(CodeEditor* editor, const QString& action);
    /** @brief プロジェクトを解析対象に追加する。 @param root ローカルディレクトリ。 */
    void addRoot(const QString& root);
    /** @brief 外部スタブ・設定を再読込する。未導入/停止後は再起動を試す。 */
    void restart();
    /** @brief 文書URIを返す。 @param editor 対象。 @return LSPのURI。 */
    QString uri(CodeEditor* editor) const;
    /** @brief LSP位置とQtのUTF-16位置を相互変換する。 @param document 文書。 @param offset Qt位置。 @return LSP位置。 */
    static QJsonObject position(QTextDocument* document, int offset);
    /** @brief LSP位置をQt位置へ変換する。 @param text 本文。 @param position LSP位置。 @return 無効なら-1。 */
    static int offset(const QString& text, const QJsonObject& position);
    /** @brief 重複/不正範囲を拒否して編集を計算する。 @param text 元文書。 @param edits LSP編集。 @param result 結果。 @return 有効か。 */
    static bool editedText(const QString& text, const QJsonArray& edits, QString* result);

private:
    struct Document { QPointer<CodeEditor> editor; QString uri; QString text; int version = 0; };
    /** @brief 文書要求と位置を作る。 @param editor 対象。 @param at Qt位置。 @return 引数。 */
    QJsonObject params(CodeEditor* editor, int at) const;
    /** @brief 取消可能な要求を送る。 @param editor 対象。 @param method メソッド。 @param arguments 引数。 @param caret カーソル一致も要求するか。 @param reply 最新応答への処理。 */
    void request(CodeEditor* editor, const QString& method, QJsonObject arguments, bool caret, LanguageClient::Reply reply);
    /** @brief サーバーの通知を現在の文書へ適用する。 @param method メソッド。 @param arguments 引数。 */
    void notification(const QString& method, const QJsonObject& arguments);
    /** @brief 色とヒントを更新する。 */
    void decorate();
    /** @brief 補完確定を適用する。 @param editor 対象。 @param name 候補名。 @return 処理したか。 */
    bool accept(CodeEditor* editor, const QString& name);
    /** @brief 編集の下見後、全対象を再検証して未保存タブへ適用する。 @param edit WorkspaceEdit。 */
    void preview(const QJsonObject& edit);
    /** @brief 候補を選び移動する。 @param editor 元タブ。 @param locations 位置一覧。 @param peek 下見。 */
    void locations(CodeEditor* editor, const QJsonArray& locations, bool peek);
    LanguageClient client_;
    QJsonObject config_;
    const EditorPreferences& preferences_;
    ProblemsPanel* problems_;
    Context context_;
    QHash<CodeEditor*, Document> documents_;
    QHash<QString, int> requests_;
    QHash<CodeEditor*, QHash<QString, QJsonObject>> completions_;
    QHash<CodeEditor*, int> completionVersions_;
    QHash<CodeEditor*, QJsonArray> diagnostics_;
    QHash<CodeEditor*, int> diagnosticVersions_;
    QTimer timer_;
    quint64 epoch_ = 0;
    QProcess refactorProcess_;
    QTimer refactorTimeout_;
    QSet<QString> roots_;
    QFileSystemWatcher watcher_;
    QHash<QString, QHash<QString, QString>> watchedEntries_;
    /** @brief 編集中の文書と同じフォルダーの追加/削除を監視する。 @param path フォルダー。 */
    void watch(const QString& path);
};
}  // namespace mce
