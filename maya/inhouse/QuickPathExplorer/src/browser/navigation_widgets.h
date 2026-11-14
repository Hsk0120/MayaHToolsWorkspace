/** @file navigation_widgets.h @brief Explorer型のタブ寸法とファイルURLドロップ境界。 */
#pragma once
#include <QTabBar>
#include <QTreeWidget>
#include <QHeaderView>
#include "settled_tree.h"
#include <functional>
namespace qpe {
/** @brief 表示中の項目へ改名欄を重ねる。モデル値は実ファイル操作成功まで変えない。
 * @param view 対象ビュー。
 * @param path 固定した対象ファイル。
 * @param submit 名前の確定先。ビュー破棄時は呼び出さない。
 * @return 対象がこのビューに存在したか。
 */
bool inlineRename(QAbstractItemView* view, const QString& path, std::function<void(const QString&)> submit);
/** @brief Qtのテーマ別矢印に依存せず、昇順は上、降順は下へ描くファイル見出し。 */
class FileSortHeader final : public QHeaderView {
public:
    /** @brief 入力・リサイズ・状態保存は標準ヘッダーへ任せる。 @param parent 所有するファイルビュー。 */
    explicit FileSortHeader(QWidget* parent);
    /** @brief 見出しを文字1行と最小余白に収める。 @return フォント倍率に追従する推奨寸法。 */
    QSize sizeHint() const override;
protected:
    /** @brief 標準の背景とラベルへ、現在の順序に対応する太めの山形を重ねる。
     * @param painter 借用する描画先。 @param rect 見出しの領域。 @param logicalIndex 論理列。
     */
    void paintSection(QPainter* painter, const QRect& rect, int logicalIndex) const override;
};
/** @brief 240pxから100pxまで均等に縮み、その後は横送りするタブ。 */
class NavigationTabs final : public QTabBar {
public:
    /** @brief タブ移動はQtへ、ファイル転送だけQPEへ委譲する。 @param parent 所有者。 */
    explicit NavigationTabs(QWidget* parent = nullptr);
    std::function<void(const QStringList&, int, bool)> transfer;
    /** @brief ホスト倍率を反映する。 @param value Maya論理倍率。 */
    void setScale(qreal value);
    /** @brief 空き幅があるときは各タブ240pxを要求する。 @return 推奨寸法。 */
    QSize sizeHint() const override;
    /** @brief レイアウトの縮小下限。 @return 最小幅。 */
    QSize minimumSizeHint() const override;
protected:
    /** @brief 表題の長さによらず均等幅にする。 @param index タブ。 @return 寸法。 */
    QSize tabSizeHint(int index) const override;
    /** @brief 長い名前のタブだけを別に縮めない。 @param index タブ。 @return 寸法。 */
    QSize minimumTabSizeHint(int index) const override;
    /** @brief Qt標準の閉じるボタンを控えめな線画に置換する。 @param index 追加位置。 */
    void tabInserted(int index) override;
    /** @brief 枚数が減ったときの最大幅を更新する。 @param index 削除位置。 */
    void tabRemoved(int index) override;
    /** @brief キャッシュ済みの寸法を更新する。 @param event サイズ変更。 */
    void resizeEvent(QResizeEvent* event) override;
    /** @brief 選択面と名前を左寄せで描く。 @param event 描画要求。 */
    void paintEvent(QPaintEvent* event) override;
    /** @brief 中ボタンでタブを閉じる。 @param event 入力。 */
    void mouseReleaseEvent(QMouseEvent* event) override;
    /** @brief ローカルURLだけを受け入れる。 @param event 入力。 */
    void dragEnterEvent(QDragEnterEvent* event) override;
    /** @brief URL受入を継続する。 @param event 入力。 */
    void dragMoveEvent(QDragMoveEvent* event) override;
    /** @brief 固定したタブ番号へ転送し、Qtによる元行削除を避ける。 @param event 入力。 */
    void dropEvent(QDropEvent* event) override;
private:
    /** @brief 追加・削除・倍率変更をまとめて寸法に反映する。 */
    void refreshSizes();
    qreal scale_ = 1;
};
/** @brief ドロップをFavoritesへの登録とし、ドライブ内への誤移動を避ける。 */
class PlacesTree final : public SettledTree<QTreeWidget> {
public:
    /** @brief 所有者へ登録を通知する。 @param parent 所有者。 */
    explicit PlacesTree(QWidget* parent = nullptr);
    std::function<void(const QStringList&)> favorite;
protected:
    /** @brief ローカルファイルのURLを受け付ける。 @param event 入力。 */
    void dragEnterEvent(QDragEnterEvent* event) override;
    /** @brief 登録先を移動させず受け付ける。 @param event 入力。 */
    void dragMoveEvent(QDragMoveEvent* event) override;
    /** @brief ファイルを移動せず登録だけを依頼する。 @param event 入力。 */
    void dropEvent(QDropEvent* event) override;
};
}
