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
constexpr const char* kHoverInlineCode = "#d7ba7d";  ///< ホバーの説明の中の``code``の文字(VS Codeと同じ)。
constexpr const char* kSignatureActive = "#4fc1ff";  ///< 引数のヒントの、今の引数の文字。
constexpr const char* kCompletionDetail = "#8b8b8b";  ///< 補完の一覧の、名前の右の説明の文字。

// ---- 補完の一覧の種類のアイコン(VS Codeの記号の色) ----
constexpr const char* kSymbolFunction = "#b180d7";  ///< 関数・メソッド。
constexpr const char* kSymbolClass = "#ee9d28";     ///< クラス。
constexpr const char* kSymbolModule = "#cccccc";    ///< モジュール。
constexpr const char* kSymbolVariable = "#75beff";  ///< 変数。
constexpr const char* kSymbolKeyword = "#cccccc";   ///< 予約語・組み込みの名前。

// ---- コード欄の補助の表示 ----
constexpr const char* kIndentGuide = "#404040";        ///< インデントの縦線。
constexpr const char* kIndentGuideActive = "#707070";  ///< カーソルのあるブロックのインデントの縦線。
constexpr const char* kWordHighlight = "#3d3d3d";      ///< カーソルの名前と同じ名前の背景。
constexpr const char* kWordHighlightStrong = "#4a4a4a";  ///< 同じ名前のうち、代入している箇所の背景。
constexpr const char* kBracketMatch = "#3c4a3c";       ///< 対応する括弧の背景。
constexpr const char* kBracketMatchBorder = "#888888"; ///< 対応する括弧の枠線。
constexpr const char* kProblemError = "#f14c4c";       ///< エラーの波線とスクロールバーの印。
constexpr const char* kProblemWarning = "#cca700";     ///< 警告の波線とスクロールバーの印。
constexpr const char* kChangeAdded = "#487e02";        ///< 保存後に追加した行の印。
constexpr const char* kChangeModified = "#1b81a8";     ///< 保存後に変更した行の印。
constexpr const char* kChangeDeleted = "#f14c4c";      ///< 保存後に削除した行の印。
constexpr const char* kScrollMarkerSearch = "#d18616"; ///< スクロールバーの、検索の一致の印。
constexpr const char* kScrollMarkerWord = "#a0a0a0";   ///< スクロールバーの、同じ名前の印。
constexpr const char* kScrollMarkerCursor = "#d4d4d4"; ///< スクロールバーの、カーソルの行の印。
constexpr const char* kFoldMarker = "#c5c5c5";         ///< 折りたたみの矢印。
constexpr const char* kFoldedBackground = "#3a3d41";   ///< 畳んだ見出しの後ろの「⋯」の背景。
constexpr const char* kStickyShadow = "#000000";       ///< 見出しの固定表示の下の影。

// ---- 検索バー(VS Codeの検索ウィジェットに合わせた色) ----
constexpr const char* kFindBarBackground = "#252526";     ///< バーの背景。
constexpr const char* kFindBarBorder = "#454545";         ///< バーの枠線。
constexpr const char* kFindFieldBackground = "#3c3c3c";   ///< 入力欄の背景。
constexpr const char* kFindFieldBorder = "#4b4b4b";       ///< 入力欄の枠線(普段は背景より少し明るい細い線)。
constexpr const char* kFindFieldFocusBorder = "#007fd4";  ///< 入力中の入力欄の枠線。
constexpr const char* kFindFieldErrorBorder = "#be1100";  ///< 不正な正規表現のときの枠線と吹き出しの枠線。
constexpr const char* kFindErrorBackground = "#5a1d1d";   ///< 不正な正規表現の理由の吹き出しの背景。
constexpr const char* kFindLabel = "#cccccc";             ///< ボタンと件数の文字。
constexpr const char* kFindErrorLabel = "#f48771";        ///< 「No results」「Invalid」の文字。
constexpr const char* kFindButtonHover = "#45494e";       ///< マウスを重ねたボタンの背景。
constexpr const char* kFindToggleChecked = "#264f78";     ///< オンの切り替えボタン(Aa など)の背景。
constexpr const char* kFindToggleCheckedBorder = "#007acc";  ///< オンの切り替えボタンの枠線。
constexpr const char* kFindToggleCheckedText = "#ffffff";    ///< オンの切り替えボタンの文字。
constexpr const char* kSearchMatch = "#623315";           ///< 本文の中の、選択中以外の一致箇所の背景。

}  // namespace theme
}  // namespace hedit
