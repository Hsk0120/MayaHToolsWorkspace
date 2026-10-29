/** @file language_client.h
 * @brief 所有する解析プロセスと非同期JSON-RPCで通信する。MayaのAPIは呼ばない。
 */
#pragma once
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <functional>

namespace mce {
/** @brief 1画面が所有するLSP接続。応答待ちでGUIを停止せず、破棄時に子プロセスを回収する。 */
class LanguageClient : public QObject {
public:
    using Reply = std::function<void(const QJsonValue&, const QString&)>;
    /** @brief 通信と期限管理を初期化する。 @param parent 所有者。 */
    explicit LanguageClient(QObject* parent = nullptr);
    /** @brief この接続だけを停止し、DLLのコールバックを残さない。 */
    ~LanguageClient() override;
    /** @brief 固定版の設定を読み起動する。 @param configuration Python環境と解析設定。 @return 起動を開始したか。 */
    bool start(const QJsonObject& configuration);
    /** @brief 初期化済みか。 @return 要求を受け付けられるならtrue。 */
    bool ready() const { return ready_; }
    /** @brief 要求を送る。 @param method LSPメソッド。 @param params 引数。 @param reply 応答。 @return 要求番号。 */
    int request(const QString& method, const QJsonObject& params, Reply reply);
    /** @brief 通知を送る。 @param method メソッド。 @param params 引数。 */
    void notify(const QString& method, const QJsonObject& params);
    /** @brief 要求を取消す。 @param id requestの番号。 */
    void cancel(int id);
    /** @brief 解析設定を再送する。 @param settings 設定。 */
    void configure(const QJsonObject& settings);
    /** @brief サーバーが提供する機能。 @return initialize応答。 */
    QJsonObject capabilities() const { return capabilities_; }
    std::function<void()> onReady;  ///< 初期化完了。フォーカスは変更しない。
    std::function<void(const QString&)> onStatus;  ///< 起動/終了/失敗の通知。
    std::function<void(const QString&, const QJsonObject&)> onNotification;  ///< サーバー通知。

private:
    /** @brief 完全なJSONフレームを取り出す。 */
    void read();
    /** @brief 1メッセージを処理する。 @param object 受信JSON。 */
    void dispatch(const QJsonObject& object);
    /** @brief Content-Length付きで送信する。 @param object 送信JSON。 */
    void send(const QJsonObject& object);
    /** @brief 失敗を表示して要求を破棄する。 @param reason 理由。 */
    void fail(const QString& reason);
    struct Pending { Reply reply; qint64 expires; };  ///< 有限時間だけ保持する要求。
    QProcess process_;
    QTimer timeout_;
    QByteArray buffer_;
    QHash<int, Pending> pending_;
    QJsonObject settings_;
    QJsonObject capabilities_;
    int nextId_ = 0;
    bool ready_ = false;
};
}  // namespace mce
