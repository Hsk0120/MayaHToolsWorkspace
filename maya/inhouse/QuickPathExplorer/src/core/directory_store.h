/** @file directory_store.h
 * @brief Pythonに依存しない世代付きディレクトリ列挙と表示キャッシュ。
 */
#pragma once
#include <QObject>
#include <QDateTime>
#include <QFileSystemWatcher>
#include <QHash>
#include <QSet>
#include <QVector>
#include <atomic>
#include <memory>

namespace qpe {
/** @brief ワーカーからGUIへ渡す値。QtウィジェットやOSハンドルを所有しない。 */
struct DirectoryEntry {
    QString name;
    bool directory = false;
    qint64 size = 0;
    QDateTime modified;
    quint32 attributes = 0;
};
using DirectoryEntries = QVector<DirectoryEntry>;
/** @brief 一覧の完了状態。読込失敗を空フォルダーと区別する。 */
struct DirectorySnapshot {
    DirectoryEntries entries;
    QString error;
    quint64 generation = 0;
    bool complete = true;
};

/** @brief アクティブ経路と要求世代の照合、監視、有限キャッシュをGUIスレッドで所有する。 */
class DirectoryStore final : public QObject {
    Q_OBJECT
public:
    /** @brief QFileSystemWatcherもこのオブジェクトが所有する。
     * @param parent Qt所有者。
     */
    explicit DirectoryStore(QObject* parent = nullptr);
    /** @brief 待機せず全要求を失効させる。ワーカーは自己完了し結果は配送されない。 */
    ~DirectoryStore() override;
    /** @brief 絶対パスの区切りを揃える。存在確認やネットワーク照会を行わない。
     * @param path 入力パス。
     * @return 正規化パス。
     */
    static QString normalized(const QString& path);
    /** @brief 表示対象を置換して対象外の要求を失効させる。
     * @param paths 現在の経路。空集合は全要求を中止する。
     */
    void activate(const QStringList& paths);
    /** @brief 同じパスでも新しい要求番号で列挙する。
     * @param path アクティブなディレクトリ。
     * @return 発行世代。対象外なら0。
     */
    quint64 request(const QString& path);
    /** @brief 採用済みスナップショットを返す。未取得時はnullptr。
     * @param path ディレクトリ。
     * @return 次の変更まで有効な借用ポインター。
     */
    const DirectorySnapshot* snapshot(const QString& path) const;
    /** @brief 未使用Storeへ完成済みの値キャッシュだけを複製する。要求・監視・選択は共有しない。
     * @param source 同じGUIスレッドに属する既存Store。
     * @note 初回activateで改めて列挙し、複製後の外部変更も検出する。
     */
    void primeCache(const DirectoryStore& source);
    /** @brief 古い成功/失敗を捨て、現行要求だけを反映する。
     * @param path 対象。
     * @param generation 要求番号。
     * @param entries 列挙値。
     * @param error 空なら成功。
     * @param complete 最終結果か。初回の部分表示は要求を継続する。
     * @return 結果を採用したか。
     * @note ワーカー配送と順序逆転テストで共通の採用境界。
     */
    bool deliver(const QString& path, quint64 generation, const DirectoryEntries& entries, const QString& error, bool complete = true);
    /** @brief 隠しファイル表示を変更してアクティブ経路を更新する。
     * @param enabled 表示するか。
     */
    void setShowHidden(bool enabled);
    /** @brief DLL解除を拒否するためのワーカー数。
     * @return 全Storeを合わせた実行/待機ワーカー数。
     */
    static int liveWorkers();
    /** @brief 自分のスレッドをコード解放より先にjoinする。 @param wait exe終了時だけ実行中も待つ。 @return 安全に解放できたか。 */
    static bool releaseWorkers(bool wait = false);
signals:
    /** @brief スナップショット採用後にGUIへ通知する。
     * @param path 更新されたディレクトリ。
     */
    void changed(const QString& path);
private:
    /** @brief 古い未使用キャッシュを上限まで削る。アクティブ経路は保持する。 */
    void trimCache();
    QSet<QString> active_;
    QHash<QString, quint64> generations_;
    QHash<QString, std::shared_ptr<std::atomic_bool>> cancellations_;
    QHash<QString, DirectorySnapshot> cache_;
    QStringList recency_;
    QFileSystemWatcher watcher_;
    quint64 serial_ = 0;
    bool hidden_ = false;
};
}
