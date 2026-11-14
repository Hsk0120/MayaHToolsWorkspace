/** @file inspector.h @brief ファイル詳細とMaya読込/保存設定を右ペインで所有する。 */
#pragma once
#include <QWidget>
#include <QJsonObject>
#include <QHash>
#include <QPixmap>
class QLabel;
class QLineEdit;
class QComboBox;
class QTabWidget;
namespace qpe {
class FileJobs;
/** @brief 親が所有する右ペイン。設定は実行時に値として固定する。 */
class Inspector final : public QWidget {
    Q_OBJECT
public:
    /** @brief ホストに合う操作欄を生成。 @param maya Maya内か。 @param parent 所有者。 */
    Inspector(bool maya, QWidget* parent);
    /** @brief 選択を表示。 @param path ファイル。 */
    void setPath(const QString& path);
    /** @brief 保存先フォルダーを更新。 @param path フォルダー。 */
    void setDirectory(const QString& path);
    /** @brief 実行する設定を取得。 @return JSON値。 */
    QJsonObject options() const;
    /** @brief 前回設定を復元。 @param state 設定。 */
    void restore(const QJsonObject& state);
    /** @brief 操作に対応するページを表示。 @param action Open/Import/Reference/Save操作名。 */
    void showAction(const QString& action);
protected:
    /** @brief 狭幅時は横送りタブを操作選択欄へ切り替える。 @param event リサイズ。 */
    void resizeEvent(QResizeEvent* event) override;
    /** @brief フォント変更後も操作名が隠れないようにする。 @param event Qt通知。 */
    void changeEvent(QEvent* event) override;
signals:
    /** @brief 明示操作。 @param action コマンド名。 */
    void requested(QString action);
    /** @brief 設定が変わった通知。 */
    void changed();
    /** @brief Maya内の既存ネームスペースを選ぶ。 @param action Import/Reference。 */
    void namespaceRequested(QString action);
private:
    /** @brief 保存では選択ファイルを対象と誤認させず、読込では選択名を表示する。 */
    void updateTitle();
    /** @brief 4操作すべてへ到達できる表示形式を幅から選ぶ。 */
    void updateActionSelector();
    /** @brief 詳細の画像をスクロール領域の有効幅に合わせる。 */
    void fitPreview();
    QLabel* information_;
    QLabel* title_ = nullptr;
    QTabWidget* tabs_ = nullptr;
    QComboBox* operation_ = nullptr;
    QWidget* fbx_ = nullptr;
    QLabel* preview_ = nullptr;
    QPixmap previewSource_;
    QWidget* detailsBody_ = nullptr;
    FileJobs* media_ = nullptr;
    QString path_;
    QString token_;
    /** @brief 展開時だけ現在選択の情報を非同期取得する。 */
    void requestDetails();
    QLineEdit* name_ = nullptr;
    QComboBox* type_ = nullptr;
    QHash<QString, QWidget*> controls_;
    QString directory_;
};
}
