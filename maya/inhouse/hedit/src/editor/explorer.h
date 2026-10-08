/** @file explorer.h
 * @brief スクリプト用の読み取り専用ファイルツリー(View > Explorer)。
 */
#pragma once
#include <QIcon>
#include <QMultiHash>
#include <QStringList>
#include <QWidget>
#include <functional>
#include <memory>

class QTreeWidget;
class QTreeWidgetItem;

namespace hedit {

class DirectoryLister;

/** @brief 開いているファイル(OPEN EDITORS)と、複数のルートフォルダーを表示する。
 * @details ファイルの削除・移動は行わない。フォルダーの中身は展開したときに初めて、別スレッドで読む
 * (ネットワークドライブなどの遅いフォルダーでも画面を止めない)。読み終わるまでは「Loading…」を出す。
 * Explorerが隠れている間は読まず(読み込みのスレッドも作らない)、初めて見えたときに展開済みのフォルダーを読む。
 * ツリーの項目はQtの親子関係で破棄される。
 */
class Explorer : public QWidget {
public:
    /** @brief ツリーと操作ボタンを作る。
     * @param parent 所有者となるQtの部品。
     */
    explicit Explorer(QWidget* parent = nullptr);

    /** @brief 読み込み用のスレッドを止めて合流する。 */
    ~Explorer() override;

    /// ファイルをダブルクリックしたときに呼ぶ関数(引数は絶対パス)。MainWindowがファイルを開く。
    std::function<void(const QString& path)> onFileActivated;
    /// ルートフォルダーが追加・削除されたときに呼ぶ関数(タブの自動保存の印に使う)。
    std::function<void()> onRootsChanged;

    /** @brief ルートフォルダーを追加する。
     * @param path 既存のフォルダー。空や存在しないパスは無視する。
     * @param replace trueなら既存のルートを全て置き換える。
     */
    void addFolder(const QString& path, bool replace = false);

    /** @brief ルートフォルダーの一覧を返す。 @return 正規化済みの絶対パス。 */
    QStringList roots() const { return folders_; }

    /** @brief ルートフォルダーを復元する。 @param paths 存在しないフォルダーは読み飛ばす。 */
    void setRoots(const QStringList& paths);

    /** @brief OPEN EDITORSの一覧を更新する。 @param paths 保存先を持つタブの絶対パス。 */
    void setOpenFiles(const QStringList& paths);

protected:
    /** @brief 初めて見えたとき、隠れている間に展開したルートフォルダーの中身を読む。 @param event 表示のイベント。 */
    void showEvent(QShowEvent* event) override;

private:
    /** @brief 展開されたフォルダーの中身の読み込みを、別スレッドへ頼む。隠れている間は何もしない(showEventで読む)。
     * @param item 展開されたフォルダーの項目。パスをQt::UserRoleに持つ。
     */
    void populate(QTreeWidgetItem* item);

    /** @brief 別スレッドで読んだフォルダーの中身を、ツリーへ反映する(画面のスレッドで呼ぶ)。
     * @param path 読んだフォルダー。
     * @param names 項目の名前。
     * @param directories 各項目がフォルダーならtrue(namesと同じ順)。
     */
    void applyListing(const QString& path, const QStringList& names, const QList<bool>& directories);

    /** @brief 消す項目とその子孫を、読んでいる途中の項目の表から取り除く。 @param item 消す項目。 */
    void forgetLoading(QTreeWidgetItem* item);

    /** @brief ルートフォルダーの項目を、OPEN EDITORS以外すべて取り除く。 */
    void removeRootItems();

    /** @brief ルートフォルダーの変化を知らせる。 */
    void notifyRootsChanged();

    QTreeWidget* tree_;                          ///< ツリー本体。
    QTreeWidgetItem* openEditors_;               ///< 先頭の「OPEN EDITORS」の項目。
    QStringList folders_;                        ///< ルートフォルダー。
    QMultiHash<QString, QTreeWidgetItem*> loading_;  ///< 読んでいる途中のフォルダーのパス → 項目(同じパスが複数あり得る)。
    QIcon folderIcon_;                           ///< フォルダーの項目のアイコン(最初に1回だけ受け取る)。
    QIcon fileIcon_;                             ///< ファイルの項目のアイコン(最初に1回だけ受け取る)。
    std::unique_ptr<DirectoryLister> lister_;    ///< フォルダーを読む別スレッド。初めて読むときに作る。
};

}  // namespace hedit
