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
    /// 一覧のアイコンの種類: ``function``・``class``・``module``・``variable``・``import``・``builtin``・``keyword``。
    QString category;
};

}  // namespace hedit

// QStringだけの型。QVector・QListの中で、要素をmemcpyで移せる型として扱う。
Q_DECLARE_TYPEINFO(hedit::CompletionItem, Q_MOVABLE_TYPE);

namespace hedit {

/** @brief 補完の結果。 */
struct CompletionResult {
    QList<CompletionItem> items;  ///< 候補(入力との一致の度合いのよい順、最大250件)。
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

/** @brief 定義の場所(定義へ移動・定義をその場で見る)。 */
struct DefinitionLocation {
    QString path;     ///< 定義のあるファイル。編集中の本文の中なら空。
    int line = -1;    ///< 行(0始まり)。見つからなければ-1。
    int column = 0;   ///< 行の中の位置(0始まり)。

    /** @brief 見つかったか。 @return 行があればtrue。 */
    bool found() const { return line >= 0; }
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
    int column = 0;    ///< 1始まりの桁。0なら行全体に波線を引く。
    int length = 0;    ///< 波線を引く文字数。0なら行の終わりまで。
};

}  // namespace hedit

// QStringと整数だけの型。QVector・QListの中で、要素をmemcpyで移せる型として扱う。
Q_DECLARE_TYPEINFO(hedit::Diagnostic, Q_MOVABLE_TYPE);

namespace hedit {

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
