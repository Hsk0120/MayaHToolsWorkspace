/** @file editor.h
 * @brief 編集画面の入口。Maya側(plugin/)が画面を作るときに使うのはこのファイルだけ。
 * @details 編集画面はMayaのAPIを直接呼ばない。コードの実行・補完・出力の取得など、Mayaが必要な処理は
 * EditorServicesに関数として入れて渡す(std::functionは「関数やラムダを入れておける変数」)。
 * こうしておくと、Mayaの代わりに偽の関数を渡して、Maya無しで画面をテストできる(tests/ui_smoke.cpp)。
 */
#pragma once
#include "core/completion_types.h"
#include "core/output_message.h"
#include <QByteArray>
#include <QList>
#include <QMainWindow>
#include <QString>
#include <functional>

namespace hedit {

/** @brief 編集画面が使う、Maya側の処理の一式。空の関数は「その機能は使えない」として扱う。 */
struct EditorServices {
    /// Pythonのコードを実行する(本文, 保存先のパス)。保存先があれば、実行中だけ``__file__``をそのパスにする。
    /// 戻り値は出力欄へ追加する補足(通常は空)。
    std::function<QString(const QString& source, const QString& path)> runPython;
    /// MELのコードを実行する。戻り値はrunPythonと同じ。
    std::function<QString(const QString& source)> runMel;
    /// 補完の情報(組み込みの名前・ファイルから読んだ宣言のキャッシュ)を取り直す(Refresh completion)。
    std::function<void()> refreshCompletion;
    /// カーソルまでの本文から、補完候補を返す。
    std::function<CompletionResult(const QString& source)> complete;
    /// マウスを重ねた名前の説明(本文全体, 名前の終わりの位置)。importも実行もしない。
    std::function<HoverInfo(const QString& text, int end)> describe;
    /// 名前の定義の場所(本文全体, 名前の終わりの位置)。編集中の本文の中ならpathが空。importも実行もしない。
    std::function<DefinitionLocation(const QString& text, int end)> definition;
    /// Pythonの本文を構文チェックする。実行はしない。
    std::function<AnalysisResult(const QString& source)> analyze;
    /// 出力の取り込み方を選ぶ(trueでScript Editorのreporterの整形をそのまま使う。遅い)。Preferencesの切り替えで呼ぶ。
    std::function<void(bool exact)> setExactOutput;
    /// Mayaの出力のうち、まだ画面へ渡していないものを取り出す(1回取り出したものは消える)。
    std::function<QList<OutputMessage>()> takeOutput;
    /// 未保存タブの復元ファイル(tabs.json)の絶対パス。空なら復元・設定の保存をしない。
    QString sessionPath;
};

/** @brief 編集画面を作成する。表示とドッキングは呼出側で行う。
 * @param parent Qtの親。親が破棄されると画面も一緒に破棄される。nullptrなら独立したウィンドウ。
 * @param services Maya側の処理の一式。
 * @return 作成した画面。parentがあれば親が所有する(呼出側でdeleteしなくてよい)。
 */
QMainWindow* createEditor(QWidget* parent, const EditorServices& services);

/** @brief Mayaの出力通知を受けたときに、出力欄をすぐ描き直す。
 * @param editor createEditorで作成した画面。nullptrや非表示の画面は何もしない。
 * @note Mayaのメインスレッドからだけ呼ぶ。長い処理の途中でも出力が見えるようにするためのもの。
 */
void refreshEditorOutput(QMainWindow* editor);

}  // namespace hedit
