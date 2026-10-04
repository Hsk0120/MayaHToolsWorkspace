/** @file completion_types.cpp
 * @brief 補完・構文チェックの結果とJSONの変換。
 */
#include "core/completion_types.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

namespace hedit {

QByteArray completionResultToJson(const CompletionResult& result) {
    QJsonArray items;
    for (const CompletionItem& item : result.items) {
        QJsonObject entry{{"name", item.name}, {"detail", item.detail}};
        if (!item.kind.isEmpty()) {
            entry.insert("kind", item.kind);
        }
        items.append(entry);
    }
    QJsonObject root{{"items", items}, {"pending", result.pending}};
    if (!result.error.isEmpty()) {
        root.insert("error", result.error);
    }
    return QJsonDocument(root).toJson(QJsonDocument::Compact);
}

QByteArray hoverInfoToJson(const HoverInfo& info) {
    return QJsonDocument(QJsonObject{{"signature", info.signature}, {"doc", info.doc}}).toJson(QJsonDocument::Compact);
}

AnalysisResult analysisResultFromJson(const QByteArray& json) {
    AnalysisResult result;
    const QJsonObject root = QJsonDocument::fromJson(json).object();
    if (root.contains("skipped")) {
        result.skipped = root["skipped"].toString();
        return result;
    }
    if (!root.contains("diagnostics")) {
        result.available = false;
        return result;
    }
    for (const QJsonValue& value : root["diagnostics"].toArray()) {
        const QJsonObject entry = value.toObject();
        result.diagnostics.append({entry["severity"].toString(), entry["line"].toInt(1), entry["message"].toString(),
                                   entry["column"].toInt(0), entry["length"].toInt(0)});
    }
    return result;
}

}  // namespace hedit
