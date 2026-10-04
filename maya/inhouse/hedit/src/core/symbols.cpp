/** @file symbols.cpp
 * @brief SymbolとJSONの変換。
 */
#include "core/symbols.h"

namespace hedit {

Symbol Symbol::module(const QString& name) {
    Symbol symbol;
    symbol.type = SymbolType::Module;
    symbol.target = name;
    return symbol;
}

Symbol Symbol::import(const QString& module, const QString& name) {
    Symbol symbol;
    symbol.type = SymbolType::Import;
    symbol.fromModule = module;
    symbol.fromName = name;
    return symbol;
}

Symbol Symbol::category(SymbolType type) {
    Symbol symbol;
    symbol.type = type;
    return symbol;
}

QString Symbol::kindName() const {
    if (type == SymbolType::Builtin) {
        return QStringLiteral("builtin");
    }
    if (type == SymbolType::Keyword) {
        return QStringLiteral("keyword");
    }
    return QString();
}

QString Symbol::categoryName() const {
    switch (type) {
    case SymbolType::Function:
        return QStringLiteral("function");
    case SymbolType::Class:
        return QStringLiteral("class");
    case SymbolType::Module:
        return QStringLiteral("module");
    case SymbolType::Import:
        return QStringLiteral("import");
    case SymbolType::Builtin:
        return QStringLiteral("builtin");
    case SymbolType::Keyword:
        return QStringLiteral("keyword");
    default:
        return QStringLiteral("variable");
    }
}

bool Symbol::operator==(const Symbol& other) const {
    if (type != other.type || detail != other.detail || target != other.target || fromModule != other.fromModule
        || fromName != other.fromName || signature != other.signature || doc != other.doc || bases != other.bases) {
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
        if (!symbol.kindName().isEmpty()) {
            entry.insert("kind", symbol.kindName());
        }
        if (symbol.type == SymbolType::Module) {
            entry.insert("target", symbol.target);
        }
        if (symbol.type == SymbolType::Import) {
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
        const QString kind = entry.value("kind").toString();
        if (entry.contains("target")) {
            symbol = Symbol::module(entry.value("target").toString());
        } else if (entry.contains("name")) {
            symbol = Symbol::import(entry.value("from").toString(), entry.value("name").toString());
        } else if (entry.contains("members")) {
            symbol.type = SymbolType::Class;
            symbol.members = std::make_shared<SymbolTable>(symbolTableFromJson(entry.value("members").toObject()));
        } else if (kind == "builtin") {
            symbol.type = SymbolType::Builtin;
        } else if (kind == "keyword") {
            symbol.type = SymbolType::Keyword;
        } else if (!entry.value("detail").toString().isEmpty()) {
            symbol.type = SymbolType::Function;
        }
        symbol.detail = entry.value("detail").toString();
        table.insert(it.key(), symbol);
    }
    return table;
}

}  // namespace hedit
