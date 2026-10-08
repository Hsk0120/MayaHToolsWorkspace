/** @file quick_pick.h
 * @brief 名前の一部を入力して項目を選ぶ小窓(VS Codeのクイックピック)。記号へ移動(Ctrl+Shift+O)と
 * ファイル名で開く(Ctrl+P)が使う。
 */
#pragma once
#include <QFrame>
#include <QList>
#include <QString>
#include <QVariant>
#include <functional>

class QLineEdit;
class QListWidget;

namespace hedit {

/** @brief クイックピックの1項目。 */
struct QuickPickItem {
    QString label;        ///< 名前(絞り込みの対象)。
    QString description;  ///< 名前の右に薄く出す補足(親のクラス・フォルダーなど)。
    QString category;     ///< アイコンの種類(``class``・``function``・``variable``・``file``など)。
    QVariant data;        ///< 選んだときに渡す値(行番号・パスなど)。
};

/** @brief 入力欄と一覧を持つ小窓(objectNameは``quickPick``)。
 * @details 親(編集画面)の上部の中央に重ねて表示する。Enterで選んだ項目を確定、Escか外のクリックで閉じる。
 * 絞り込みは、入力した文字が順に含まれるか(あいまい検索)で行い、先頭一致・連続一致を上に並べる。
 */
class QuickPick : public QFrame {
public:
    /** @brief 小窓を作る。作成直後は非表示。 @param parent 所有者(編集画面)。 */
    explicit QuickPick(QWidget* parent);

    /** @brief 項目を設定して開く。
     * @param placeholder 入力欄の案内の文字。
     * @param items 項目(並びはこのまま。絞り込むと一致の良い順)。
     * @param current 最初に選んでおく項目の位置。-1なら先頭。
     */
    void open(const QString& placeholder, const QList<QuickPickItem>& items, int current = -1);

    /** @brief 開いたまま項目を差し替える(別スレッドで集め終えた一覧など)。
     * @param items 新しい項目。
     * @details 入力中の文字はそのままで絞り込み直し、選んでいた項目が新しい一覧にもあれば選び直す。
     * 一覧の行の数に合わせて小窓の高さも直す。差し替えると、setLoadingText()の文字は消える。
     */
    void setItems(const QList<QuickPickItem>& items);

    /** @brief 絞り込んだ結果が空のときに、一覧へ選べない1行として出す文字を設定する(``Loading…``など)。
     * @param text 出す文字。空なら出さない。open()で空に戻る。
     */
    void setLoadingText(const QString& text);

    /** @brief 開いているか、閉じる処理の最中でないか。 @return 開いて操作できる状態ならtrue。 */
    bool isOpen() const { return isVisible() && !closing_; }

    /** @brief 閉じる(確定しない)。 */
    void cancel();

    /** @brief 入力欄(テスト用)。 @return 入力欄。所有者はこの小窓。 */
    QLineEdit* input() const { return input_; }

    /** @brief 一覧(テスト用)。 @return 一覧。所有者はこの小窓。 */
    QListWidget* list() const { return list_; }

    /** @brief 文字列が絞り込みの文字に一致するかと、その点数(大きいほど良い)。
     * @param text 項目の名前。
     * @param filter 入力した文字(大文字・小文字は区別しない)。
     * @return 一致しなければ-1。先頭一致・連続一致・単語の先頭での一致ほど大きい。
     */
    static int matchScore(const QString& text, const QString& filter);

    std::function<void(const QVariant& data)> onAccepted;  ///< Enterで確定した。
    std::function<void(const QVariant& data)> onPreview;   ///< 選んでいる項目が変わった(記号へ移動の下見)。
    std::function<void()> onCanceled;                      ///< 確定せずに閉じた。

protected:
    /** @brief 入力欄の上下キー・Enter・Escを処理する。 @param watched 対象。 @param event イベント。 @return 処理したらtrue。 */
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    /** @brief 入力に合わせて一覧を絞り込む。 */
    void refilter();

    /** @brief 選んでいる項目を確定して閉じる。選べない行(setLoadingTextの行)では何もしない。 */
    void accept();

    /** @brief 一覧の行の数に合わせて、親の上部の中央に置き直す。 */
    void placeInParent();

    QLineEdit* input_;            ///< 入力欄。所有者はこの小窓。
    QListWidget* list_;           ///< 一覧。所有者はこの小窓。
    QList<QuickPickItem> items_;  ///< 全ての項目。
    QString loadingText_;         ///< 絞り込んだ結果が空のときに出す、選べない行の文字。
    bool closing_ = false;        ///< 閉じる処理の最中か(フォーカスが外れたときの二重処理を防ぐ)。
};

}  // namespace hedit
