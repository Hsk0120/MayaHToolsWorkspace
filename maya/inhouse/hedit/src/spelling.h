/** @file spelling.h
 * @brief 外部辞書を同梱しないWindows標準スペルチェックの窓口。
 */
#pragma once
#include <QString>
#include <QList>
#include <QPair>
#include <memory>

namespace hedit {
/** @brief COMと辞書キャッシュを所有する。作成・利用・破棄はGUIスレッドに限定する。 */
class Spelling {
    struct Impl;
    std::unique_ptr<Impl> impl;
public:
    /** @brief 辞書は最初の照会まで生成しない。 */
    Spelling();
    /** @brief 自分が初期化したCOMと辞書だけを解放する。 */
    ~Spelling();
    /** @brief 英語辞書を一度初期化する。 @return 利用可能ならtrue。 */
    bool available();
    /** @brief 表示範囲の英単語を調べる。英字の大小・snake_case・camelCaseを分割する。
     * @param text 最大8,000文字の表示範囲。全文走査は行わない。
     * @return UTF-16単位の開始位置と長さ。Maya/Pythonの代表的な語は除外する。
     */
    QList<QPair<int,int>> check(const QString& text);
};
}
