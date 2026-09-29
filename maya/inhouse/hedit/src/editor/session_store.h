/** @file session_store.h
 * @brief 未保存タブの復元ファイル(tabs.json)の読み書きとロック。
 * @details JSONの形はcore/session_data.h。ここはファイルの操作だけを行う。
 * 同じ復元ファイルを複数のMayaが使う場合、最初に開いたMayaだけがロックを取って保存する。
 */
#pragma once
#include "core/session_data.h"
#include <QByteArray>
#include <QString>
#include <memory>

class QLockFile;

namespace hedit {

/** @brief tabs.jsonを読み書きする。 */
class SessionStore {
public:
    /** @brief open()の結果。 */
    enum class OpenResult {
        Disabled,              ///< 保存先が空(復元を使わない)。
        Loaded,                ///< 読み込めた。dataに内容が入る。
        NoFile,                ///< まだファイルが無い(初回)。保存はできる。
        CannotCreateDirectory, ///< 保存先のフォルダーを作れない。保存もしない。
        Locked,                ///< 別のMayaが使っている。保存もしない。
        Unreadable,            ///< ファイルが壊れている。元のファイルを残し、保存もしない。
    };

    /** @brief 保存先を決める。ファイルにはまだ触れない。
     * @param path tabs.jsonの絶対パス。空なら復元を使わない。
     */
    explicit SessionStore(const QString& path);

    /** @brief ロックを外す。 */
    ~SessionStore();

    /** @brief 保存先のパスを返す。 @return tabs.jsonの絶対パス。 */
    QString path() const { return path_; }

    /** @brief ロックを取り、tabs.jsonを読む。
     * @param data 読み込めた場合に内容を入れる。
     * @return 結果。LoadedとNoFileの場合だけ、以後save()で保存できる。
     */
    OpenResult open(SessionData* data);

    /** @brief 保存できる状態か(ロックを持っているか)。 @return 保存できるならtrue。 */
    bool canSave() const;

    /** @brief 内容を保存する。前回と同じ内容なら書かない。
     * @param data 保存する内容。
     * @param error 失敗したときの理由を入れる。nullptrなら入れない。
     * @return 保存した(または変更が無かった)ならtrue。ロックが無い・書けない場合はfalse。
     * @note QSaveFileで一時ファイルへ書いてから置き換えるので、途中で落ちても元のファイルは壊れない。
     */
    bool save(const SessionData& data, QString* error);

private:
    QString path_;                     ///< tabs.jsonの絶対パス。
    std::unique_ptr<QLockFile> lock_;  ///< tabs.json.lock。保存できるのはロックを持つ間だけ。
    QByteArray lastSaved_;             ///< 前回保存した内容(同じなら書かない)。
};

}  // namespace hedit
