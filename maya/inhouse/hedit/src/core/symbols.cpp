/** @file symbols.cpp
 * @brief SymbolとJSONの変換。
 */
#include "core/symbols.h"

namespace hedit {

bool Symbol::operator==(const Symbol& other) const {
    if (detail != other.detail || kind != other.kind || target != other.target || fromModule != other.fromModule
        || fromName != other.fromName || signature != other.signature || doc != other.doc) {
        return false;
    }
    if (!members || !other.members) {
        return !members && !other.members;
    }
    return *members == *other.members;
}

QJsonObject symbolTableToJson(const SymbolTable& table) {
    QJsonObject result;
    for (auto it = table.begin(); it != table.end(); ++it) {
        const Symbol& symbol = it.value();
        QJsonObject entry;
        if (!symbol.detail.isEmpty()) {
            entry.insert("detail", symbol.detail);
        }
        if (!symbol.kind.isEmpty()) {
            entry.insert("kind", symbol.kind);
        }
        if (!symbol.target.isEmpty()) {
            entry.insert("target", symbol.target);
        }
        if (!symbol.fromName.isEmpty()) {
            entry.insert("from", symbol.fromModule);
            entry.insert("name", symbol.fromName);
        }
        if (symbol.members) {
            entry.insert("members", symbolTableToJson(*symbol.members));
        }
        result.insert(it.key(), entry);
    }
    return result;
}

SymbolTable symbolTableFromJson(const QJsonObject& object) {
    SymbolTable table;
    for (auto it = object.begin(); it != object.end(); ++it) {
        const QJsonObject entry = it.value().toObject();
        Symbol symbol;
        symbol.detail = entry.value("detail").toString();
        symbol.kind = entry.value("kind").toString();
        symbol.target = entry.value("target").toString();
        if (entry.contains("name")) {
            symbol.fromModule = entry.value("from").toString();
            symbol.fromName = entry.value("name").toString();
        }
        if (entry.contains("members")) {
            symbol.members = std::make_shared<SymbolTable>(symbolTableFromJson(entry.value("members").toObject()));
        }
        table.insert(it.key(), symbol);
    }
    return table;
}

}  // namespace hedit
