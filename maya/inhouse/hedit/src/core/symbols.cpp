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
    // 項目の名前はQLatin1Stringで渡す(項目ごとにconst char*からQStringを作らない)。
    // maya.cmdsのような数千件の表を、公開名が変わるたびに読むため。
    const QLatin1String kindKey("kind");
    const QLatin1String targetKey("target");
    const QLatin1String nameKey("name");
    const QLatin1String fromKey("from");
    const QLatin1String membersKey("members");
    const QLatin1String detailKey("detail");
    SymbolTable table;
    for (auto it = object.begin(); it != object.end(); ++it) {
        const QJsonObject entry = it.value().toObject();
        Symbol symbol;
        const QString kind = entry.value(kindKey).toString();
        const QString detail = entry.value(detailKey).toString();
        if (entry.contains(targetKey)) {
            symbol = Symbol::module(entry.value(targetKey).toString());
        } else if (entry.contains(nameKey)) {
            symbol = Symbol::import(entry.value(fromKey).toString(), entry.value(nameKey).toString());
        } else if (entry.contains(membersKey)) {
            symbol.type = SymbolType::Class;
            symbol.members = std::make_shared<SymbolTable>(symbolTableFromJson(entry.value(membersKey).toObject()));
        } else if (kind == QLatin1String("builtin")) {
            symbol.type = SymbolType::Builtin;
        } else if (kind == QLatin1String("keyword")) {
            symbol.type = SymbolType::Keyword;
        } else if (!detail.isEmpty()) {
            symbol.type = SymbolType::Function;
        }
        symbol.detail = detail;
        // JSONの項目は名前順に並ぶので、表の最後へ足す(挿入位置を探さない)。
        table.insert(table.constEnd(), it.key(), symbol);
    }
    return table;
}

}  // namespace hedit
