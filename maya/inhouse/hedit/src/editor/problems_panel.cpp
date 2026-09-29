/** @file problems_panel.cpp
 * @brief ProblemsPanelの実装。
 */
#include "editor/problems_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

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

void ProblemsPanel::showResult(const QByteArray& response) {
    clear();
    const QJsonObject result = QJsonDocument::fromJson(response).object();
    if (result.contains("skipped")) {
        addItem(result["skipped"].toString());
        return;
    }
    if (!result.contains("diagnostics")) {
        addItem("Analysis unavailable");
        return;
    }
    for (const QJsonValue& entry : result["diagnostics"].toArray()) {
        const QJsonObject diagnostic = entry.toObject();
        const int line = diagnostic["line"].toInt(1);
        const QString severity = diagnostic["severity"].toString();
        const QString text = QString("%1 — Line %2: %3").arg(severity).arg(line).arg(diagnostic["message"].toString());
        // 親(this)を渡して作った項目は、一覧が所有する。
        auto item = new QListWidgetItem(text, this);
        item->setData(Qt::UserRole, line);
        item->setForeground(QColor(severity == "error" ? theme::kDiagnosticError : theme::kDiagnosticWarning));
    }
    if (count() == 0) {
        addItem("No syntax problems found (type checking is not performed)");
    }
}

}  // namespace hedit
