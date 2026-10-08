/** @file output_message.h
 * @brief 出力欄に表示する1件のメッセージの型。
 * @details Mayaから受け取った出力(plugin/output_capture.cpp)を、画面(editor/output_panel.cpp)へ
 * 渡すときの共通の形。Mayaにも画面にも依存しないため、両方から読み込める。
 */
#pragma once
#include <QString>

namespace hedit {

/** @brief 出力の種類。Mayaが通知した種別をそのまま使い、文字列の中身から推測しない。 */
enum class OutputKind {
    Normal,   ///< 通常の出力(printなど)。
    Warning,  ///< 警告。黄色で表示する。
    Error,    ///< エラー。赤で表示する。
    Result,   ///< コマンドの結果(``// Result:``)。緑で表示する。
    Info,     ///< hedit自身の案内。水色で表示する。
    History,  ///< 実行したコマンドの履歴(エコー)。灰色で表示する。
};

/** @brief 出力欄へ追加する文字列と、その種類。 */
struct OutputMessage {
    QString text;                          ///< 表示する文字列。改行を含んでよい。
    OutputKind kind = OutputKind::Normal;  ///< 色分けと絞り込みに使う種類。
};

}  // namespace hedit

// QStringと列挙だけの型。QVector・QListの中で、要素をmemcpyで移せる型として扱う。
Q_DECLARE_TYPEINFO(hedit::OutputMessage, Q_MOVABLE_TYPE);
