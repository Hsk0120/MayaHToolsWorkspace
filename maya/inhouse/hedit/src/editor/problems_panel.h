/** @file problems_panel.h
 * @brief 構文チェック(Preferencesの「Static analysis」)の結果の一覧。
 */
#pragma once
#include "core/completion_types.h"
#include <QByteArray>
#include <QListWidget>
#include <functional>

namespace hedit {

/** @brief 構文チェックの結果の一覧(objectNameは``analysisProblems``)。
 * @details 項目をクリックすると、onLineClickedでその行番号(1始まり)を知らせる。
 */
class ProblemsPanel : public QListWidget {
public:
    /** @brief 一覧を作る。作成直後は非表示。
     * @param parent Qtの親。
     */
    explicit ProblemsPanel(QWidget* parent = nullptr);

    /// 項目がクリックされたときに呼ぶ関数(引数は1始まりの行番号)。
    std::function<void(int line)> onLineClicked;

    /** @brief 入力が止まるまで待っていることを表示する。 */
    void showWaiting();

    /** @brief 構文チェックの結果を一覧にする。
     * @param result 結果。
     */
    void showResult(const AnalysisResult& result);
};

}  // namespace hedit
