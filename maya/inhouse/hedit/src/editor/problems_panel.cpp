/** @file problems_panel.cpp
 * @brief ProblemsPanelの実装。
 */
#include "editor/problems_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"

namespace hedit {

ProblemsPanel::ProblemsPanel(QWidget* parent) : QListWidget(parent) {
    setObjectName("analysisProblems");
    setMaximumHeight(scaled(140));
    hide();
    connect(this, &QListWidget::itemClicked, this, [this](QListWidgetItem* item) {
        // 行番号はQt::UserRoleに入れてある。案内の行(番号なし)は0になる。
        const int line = item->data(Qt::UserRole).toInt();
        if (line >= 1 && onLineClicked) {
            onLineClicked(line);
        }
    });
}

void ProblemsPanel::showWaiting() {
    clear();
    addItem("Checking after typing stops…");
}

void ProblemsPanel::showResult(const AnalysisResult& result) {
    clear();
    if (!result.skipped.isEmpty()) {
        addItem(result.skipped);
        return;
    }
    if (!result.available) {
        addItem("Analysis unavailable");
        return;
    }
    for (const Diagnostic& diagnostic : result.diagnostics) {
        const QString text = QString("%1 — Line %2: %3").arg(diagnostic.severity).arg(diagnostic.line).arg(diagnostic.message);
        // 親(this)を渡して作った項目は、一覧が所有する。
        auto item = new QListWidgetItem(text, this);
        item->setData(Qt::UserRole, diagnostic.line);
        item->setForeground(QColor(diagnostic.severity == "error" ? theme::kDiagnosticError : theme::kDiagnosticWarning));
    }
    if (count() == 0) {
        addItem("No problems found (syntax and undefined names only; type checking is not performed)");
    }
}

}  // namespace hedit
