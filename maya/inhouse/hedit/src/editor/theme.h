/** @file theme.h
 * @brief heditの配色(VS CodeのDark+を参考にした色)を1か所にまとめたもの。
 * @details 色を変えるときはこのファイルだけを直す。QColor(theme::kText)のように使う。
 * スタイルシートへは``QString(...).arg(theme::kText)``のように埋め込む。
 */
#pragma once

namespace hedit {
namespace theme {

// ---- コード欄と出力欄 ----
constexpr const char* kBackground = "#1e1e1e";          ///< 本文の背景。
constexpr const char* kText = "#d4d4d4";                ///< 本文の文字。
constexpr const char* kSelection = "#264f78";           ///< 選択範囲の背景。
constexpr const char* kCurrentLine = "#282828";         ///< カーソル行の背景。
constexpr const char* kLineNumber = "#858585";          ///< 行番号の文字。
constexpr const char* kSpellingUnderline = "#4fc1ff";   ///< スペルミスの波線。

// ---- 構文の色分け ----
constexpr const char* kSyntaxIdentifier = "#9cdcfe";    ///< 変数などの名前。
constexpr const char* kSyntaxNumber = "#b5cea8";        ///< 数値。
constexpr const char* kSyntaxFunction = "#dcdcaa";      ///< 関数呼出しの名前。
constexpr const char* kSyntaxKeyword = "#c586c0";       ///< def・ifなどの予約語。
constexpr const char* kSyntaxConstant = "#569cd6";      ///< True・False・None・self。
constexpr const char* kSyntaxString = "#ce9178";        ///< 文字列。
constexpr const char* kSyntaxClassName = "#4ec9b0";     ///< classの後のクラス名。
constexpr const char* kSyntaxComment = "#6a9955";       ///< コメント。

// ---- 出力の種類ごとの色 ----
constexpr const char* kOutputNormal = "#d4d4d4";        ///< 通常の出力。
constexpr const char* kOutputWarning = "#ffff00";       ///< 警告。
constexpr const char* kOutputError = "#ff0000";         ///< エラー。
constexpr const char* kOutputResult = "#b5cea8";        ///< コマンドの結果。
constexpr const char* kOutputInfo = "#9cdcfe";          ///< heditの案内。
constexpr const char* kOutputHistory = "#a0a0a0";       ///< 実行したコマンドの履歴。

// ---- 構文チェックの一覧 ----
constexpr const char* kDiagnosticError = "#f48771";     ///< 構文エラー。
constexpr const char* kDiagnosticWarning = "#dcdcaa";   ///< 警告。

// ---- 補完候補の一覧(ポップアップ) ----
constexpr const char* kPopupBackground = "#252526";
constexpr const char* kPopupBorder = "#454545";
constexpr const char* kPopupSelection = "#094771";
constexpr const char* kPopupSelectedText = "#ffffff";

// ---- 検索バー ----
constexpr const char* kFindBarBackground = "#252526";
constexpr const char* kFindFieldBackground = "#3c3c3c";
constexpr const char* kFindFieldBorder = "#555";
constexpr const char* kFindFieldFocusBorder = "#6b93b0";
constexpr const char* kFindLabel = "#bdbdbd";
constexpr const char* kFindToggleChecked = "#515151";
constexpr const char* kFindToggleCheckedText = "#ffffff";
constexpr const char* kFindButtonHover = "#505050";

}  // namespace theme
}  // namespace hedit
