/** @file session_store.h
 * @brief 複数Mayaの現行タブだけを保管する復元ストア。
 * @details 新しい状態の確定後に過去世代と未参照本文を整理する。
 * 並行した編集は次回起動で別タブとして回収し、通常の編集履歴は保持しない。
 */
#pragma once
#include "core/session_data.h"
#include <QHash>
#include <QSet>
#include <QStringList>

namespace mce {

/** @brief 本文の保全・世代の確定・並行セッションの復元を担当する。 */
class SessionStore {
public:
    /** @brief open()の結果。Unreadableでも別世代への保存は可能。 */
    enum class OpenResult { Disabled, Loaded, NoFile, CannotCreateDirectory, Unreadable };
    /** @brief 保存先を決める。 @param path 旧tabs.jsonのパス。空なら無効。 */
    explicit SessionStore(const QString& path);
    /** @brief 保存先の基準を返す。 @return 旧tabs.jsonのパス。 */
    QString path() const { return path_; }
    /** @brief 復元フォルダーを返す。 @return 世代と本文を保管するフォルダー。 */
    QString recoveryPath() const { return path_ + ".recovery"; }
    /** @brief 最新の分岐を統合して読む。 @param data 復元結果。 @return 読込状態。 */
    OpenResult open(SessionData* data);
    /** @brief 初期化済みかを返す。書込の成否はsave()で確認する。 @return 保存を試行可能ならtrue。 */
    bool canSave() const { return enabled_; }
    /** @brief 変更した本文と新しい状態を確定し、過去世代を整理する。
     * @param data 本文未変更のタブはtextLoaded=falseで渡せる。
     * @param error 失敗理由の格納先。
     * @param prune trueならその場で整理する。GUIでは確定後の短い後処理へまとめる。
     * @return 世代の確定が完了したらtrue。
     */
    bool save(const SessionData& data, QString* error, bool prune = true);
    /** @brief 最新状態の検証後に未参照データを整理する。GUIの後処理・終了時から呼ぶ。
     * @return ロック中ならfalse。別Mayaを待ってGUIを止めず、後で再試行する。
     */
    bool discardHistory();
    /** @brief 保持する本文のパスを返す。 @param id タブID。 @return 圧縮本文または旧本文のパス。 */
    QString textPath(const QString& id) const;
    /** @brief 本文を保持しているか返す。 @param id タブID。 @return 保持済みならtrue。 */
    bool hasTextFile(const QString& id) const { return bodies_.contains(id); }
    /** @brief 指定世代を読込む。壊れた本文を除いた結果もdataに返す。
     * @param id 世代ID。 @param data 読込結果。 @return 全本文が検証できたらtrue。
     */
    bool readSnapshot(const QString& id, SessionData* data) const;
    /** @brief 読込時の注意事項。 @return 本文を含まない通知文。 */
    QString notice() const { return notice_; }
    /** @brief 確定した世代数。 @return 回数。 */
    int jsonWrites() const { return jsonWrites_; }
    /** @brief 新規本文の書込数。 @return 回数。 */
    int textWrites() const { return textWrites_; }
    /** @brief 起動時の世代一覧取得数。 @return 回数。 */
    int listings() const { return listings_; }

private:
    /** @brief ロック内で現行状態を検証し、祖先世代・未参照本文・移行済み旧形式を整理する。
     * @param verifiedBodies この保存トランザクションで検証・確定済みの本文SHA256。
     */
    void pruneHistory(const QSet<QString>& verifiedBodies);
    QString path_;                   ///< 旧復元ファイル。現行状態の確定後に整理する。
    QStringList parents_;            ///< この画面で読み込んだ確定世代のみ。他のMayaの後続世代は含めない。
    QHash<QString, QString> bodies_; ///< タブIDからSHA256への対応。変更のない本文を再利用する。
    QHash<QString, QString> cachedText_; ///< 開いたタブの本文。別Mayaによる整理後も未表示タブを再保存できる。
    QHash<QString, QPair<qint64, qint64>> bodyStamps_; ///< この画面で検証済みの不変本文のサイズ・更新時刻。起動時は必ず再検証。
    QByteArray lastSaved_;           ///< 直前の本文参照付きメタデータ。同一なら新世代不要。
    QString notice_;                ///< 部分復元・並行編集についての通知。
    bool enabled_ = false;           ///< 保存フォルダーの準備が済んだか。
    int jsonWrites_ = 0;             ///< 世代の確定数。
    int textWrites_ = 0;             ///< 本文の新規保存数。
    int listings_ = 0;               ///< 一覧の取得数。
};

}  // namespace mce
