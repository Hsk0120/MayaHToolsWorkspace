/** @file explorer.h
 * @brief スクリプト用の読み取り専用ファイルツリー(View > Explorer)。
 */
#pragma once
#include <QStringList>
#include <QWidget>
#include <functional>

class QTreeWidget;
class QTreeWidgetItem;

namespace hedit {

/** @brief 開いているファイル(OPEN EDITORS)と、複数のルートフォルダーを表示する。
 * @details ファイルの削除・移動は行わない。フォルダーの中身は展開したときに初めて読むので、
 * 起動時に全体を走査しない。ツリーの項目はQtの親子関係で破棄される。
 */
class Explorer : public QWidget {
public:
    /** @brief ツリーと操作ボタンを作る。
     * @param parent 所有者となるQtの部品。
     */
    explicit Explorer(QWidget* parent = nullptr);

    /// ファイルをダブルクリックしたときに呼ぶ関数(引数は絶対パス)。MainWindowがファイルを開く。
    std::function<void(const QString& path)> onFileActivated;

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

private:
    /** @brief フォルダーの直下を列挙して子の項目を作る。シンボリックリンク先へは降りない。
     * @param item 展開されたフォルダーの項目。パスをQt::UserRoleに持つ。
     */
    void populate(QTreeWidgetItem* item);

    /** @brief ルートフォルダーの項目を、OPEN EDITORS以外すべて取り除く。 */
    void removeRootItems();

    QTreeWidget* tree_;               ///< ツリー本体。
    QTreeWidgetItem* openEditors_;    ///< 先頭の「OPEN EDITORS」の項目。
    QStringList folders_;             ///< ルートフォルダー。
};

}  // namespace hedit
