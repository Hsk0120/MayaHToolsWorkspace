/** @file explorer.h
 * @brief スクリプト用の読み取り専用ファイルツリー。
 */
#pragma once
#include <QWidget>
#include <QStringList>
#include <functional>
class QTreeWidget;
class QTreeWidgetItem;

namespace hedit {
/** @brief 開いたファイルと複数のルートフォルダーを表示する。
 * Qtの親子関係が子ウィジェットを破棄する。ファイルの削除・移動は行わない。
 * ディレクトリの中身は展開時だけ読むので、起動時の再帰走査は不要。
 */
class Explorer : public QWidget {
    QTreeWidget* tree;
    QTreeWidgetItem* opened;
    QStringList folders;
    /** @brief ディレクトリ直下を列挙する。シンボリックリンク先へは降りない。
     * @param item 展開されたツリー項目。パスをQt::UserRoleに保持する。
     */
    void populate(QTreeWidgetItem* item);
public:
    /// ファイルをダブルクリックした時に呼ぶ。ウィンドウ側がファイルを開く。
    std::function<void(const QString&)> openFile;
    /** @brief ツリーと操作ボタンを作る。 @param parent 所有者となるQtウィジェット。 */
    explicit Explorer(QWidget* parent=nullptr);
    /** @brief ルートを追加する。 @param path 既存フォルダー。 @param replace trueなら既存ルートを置き換える。 */
    void addFolder(const QString& path, bool replace=false);
    /** @brief ルート一覧を返す。 @return 正規化済みの絶対パス。 */
    QStringList roots() const;
    /** @brief 復元用ルート一覧を設定する。 @param paths 既存でないフォルダーは読み飛ばす。 */
    void setRoots(const QStringList& paths);
    /** @brief 開いているファイル一覧を更新する。 @param paths 保存先を持つタブの絶対パス。 */
    void setOpenFiles(const QStringList& paths);
};
}
