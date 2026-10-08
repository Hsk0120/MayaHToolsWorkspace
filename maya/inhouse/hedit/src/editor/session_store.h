/** @file session_store.h
 * @brief 未保存タブの復元ファイル(tabs.jsonとtabs/<id>.txt)の読み書きとロック。
 * @details JSONの形はcore/session_data.h。ここはファイルの操作だけを行う。
 * - tabs.json: タブの並び・保存先・言語・カーソルなどの小さな情報。
 * - tabs/<id>.txt: タブごとの本文。そのタブの本文が変わったときだけ書く。
 * 同じ復元ファイルを複数のMayaが使う場合、最初に開いたMayaだけがロック(tabs.json.lock)を取って保存する。
 */
#pragma once
#include "core/session_data.h"
#include <QByteArray>
#include <QSet>
#include <QString>
#include <memory>

class QLockFile;

namespace hedit {

/** @brief tabs.jsonと本文のファイルを読み書きする。 */
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

    /** @brief ロックを取り、tabs.jsonと本文のファイルを読む。
     * @param data 読み込めた場合に内容を入れる(全てのタブの本文が入る)。
     * @return 結果。LoadedとNoFileの場合だけ、以後save()で保存できる。
     */
    OpenResult open(SessionData* data);

    /** @brief 保存できる状態か(ロックを持っているか)。 @return 保存できるならtrue。 */
    bool canSave() const;

    /** @brief 内容を保存する。
     * @param data 保存する内容。textLoadedがtrueのタブだけ本文のファイルを書く(本文が変わったタブだけ入れる)。
     * @param error 失敗したときの理由を入れる。nullptrなら入れない。
     * @return 保存した(または変更が無かった)ならtrue。ロックが無い・書けない場合はfalse。
     * @details 本文のファイルを先に書き、最後にtabs.jsonを書く(途中で落ちても、tabs.jsonが指す本文は揃っている)。
     * もう無いタブの本文のファイルは消す。どれもQSaveFileで一時ファイルへ書いてから置き換える。
     * tabs/フォルダーの一覧を読むのは最初の保存の1回だけ(前回のMayaが残したファイルの片付け)。
     * 以後は、前回の保存から無くなったタブの本文のファイルだけを消す(保存のたびにフォルダーを一覧しない)。
     */
    bool save(const SessionData& data, QString* error);

    /** @brief タブの本文のファイルのパス。 @param id タブの識別子。 @return ``tabs/<id>.txt``の絶対パス。 */
    QString textPath(const QString& id) const;

    /** @brief open()で、本文を``tabs/<id>.txt``から読んだタブか。
     * @param id タブの識別子。
     * @return 本文のファイルから読んだならtrue。古い形式(本文をtabs.jsonに含む0.2.x)のタブはfalse。
     */
    bool hasTextFile(const QString& id) const { return textFiles_.contains(id); }

    /** @brief tabs.jsonを書いた回数(計測用)。 @return 回数。 */
    int jsonWrites() const { return jsonWrites_; }
    /** @brief 本文のファイルを書いた回数(計測用)。 @return 回数。 */
    int textWrites() const { return textWrites_; }
    /** @brief tabs/フォルダーの一覧を読んだ回数(計測用)。 @return 回数。 */
    int listings() const { return listings_; }

private:
    QString path_;                     ///< tabs.jsonの絶対パス。
    std::unique_ptr<QLockFile> lock_;  ///< tabs.json.lock。保存できるのはロックを持つ間だけ。
    QByteArray lastSaved_;             ///< 前回保存したtabs.jsonの内容(同じなら書かない)。
    QSet<QString> textFiles_;          ///< open()で本文のファイルから読んだタブの識別子。
    QSet<QString> savedIds_;           ///< 前回保存したタブの識別子(無くなったタブの本文のファイルを消すのに使う)。
    bool cleaned_ = false;             ///< tabs/フォルダーの残りのファイルを片付けたか(最初の保存で1回だけ行う)。
    int jsonWrites_ = 0;               ///< tabs.jsonを書いた回数。
    int textWrites_ = 0;               ///< 本文のファイルを書いた回数。
    int listings_ = 0;                 ///< tabs/フォルダーの一覧を読んだ回数。
};

}  // namespace hedit
