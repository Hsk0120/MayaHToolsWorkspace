/** @file completion_types.h
 * @brief 補完と構文チェックの結果の型。編集画面(editor/)とMaya側(plugin/)の間で受け渡す。
 * @details C++の中ではこの構造体のまま渡し、JSONにするのはPythonとの境目とテスト用のコマンドだけ。
 */
#pragma once
#include <QByteArray>
#include <QList>
#include <QString>

namespace hedit {

/** @brief 補完候補の1件。 */
struct CompletionItem {
    QString name;    ///< 挿入する名前。
    QString detail;  ///< マウスを重ねたときの説明(関数の引数など)。
    QString kind;    ///< ``builtin``・``keyword``、または空。Preferencesでの絞り込みに使う。
};

/** @brief 補完の結果。 */
struct CompletionResult {
    QList<CompletionItem> items;  ///< 候補(名前順、最大250件)。
    bool pending = false;         ///< import文の候補を集めている途中ならtrue(少し後に問い合わせ直す)。
    QString error;                ///< 失敗の理由。成功なら空。
};

/** @brief マウスを重ねた名前の説明(ホバー)。VS Codeのホバーと同じく、定義の見出しとdocstringを出す。 */
struct HoverInfo {
    QString signature;  ///< 定義の見出し(``def show(floating=None)``・``class Joint(Transform)``・``module maya.cmds``)。
    QString doc;        ///< docstring(字下げを整えたもの)。無ければ空。

    /** @brief 表示するものがあるか。 @return 見出しかdocstringがあればtrue。 */
    bool isEmpty() const { return signature.isEmpty() && doc.isEmpty(); }
};

/** @brief ホバーの説明をJSONにする(テスト用の``hedit -describe``の戻り値)。
 * @param info 説明。
 * @return ``{"signature": ..., "doc": ...}``。
 */
QByteArray hoverInfoToJson(const HoverInfo& info);

/** @brief 補完の結果をJSONにする(テスト用の``hedit -complete``の戻り値)。
 * @param result 結果。
 * @return ``{"items":[{"name","detail","kind"?}...],"pending":bool,"error"?:...}``。
 */
QByteArray completionResultToJson(const CompletionResult& result);

/** @brief 構文チェックの1件の指摘。 */
struct Diagnostic {
    QString severity;  ///< ``error``か``warning``。
    int line = 1;      ///< 1始まりの行番号。
    QString message;   ///< 内容。
};

/** @brief 構文チェックの結果。 */
struct AnalysisResult {
    bool available = true;          ///< チェックできたか。falseならPython側で失敗した。
    QString skipped;                ///< 大きすぎるなどでチェックしなかった理由。チェックしたなら空。
    QList<Diagnostic> diagnostics;  ///< 指摘(最大100件)。
};

/** @brief Python(hedit.analysis)が返すJSONを結果にする。
 * @param json ``{"diagnostics":[...]}``または``{"diagnostics":[],"skipped":"..."}``。
 * @return 結果。JSONとして読めなければavailable=false。
 */
AnalysisResult analysisResultFromJson(const QByteArray& json);

}  // namespace hedit
