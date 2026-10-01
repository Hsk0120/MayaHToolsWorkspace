/** @file completion_engine.cpp
 * @brief CompletionEngineの実装。
 */
#include "core/completion_engine.h"
#include "core/module_scanner.h"
#include "core/python_declarations.h"
#include "core/script_lexer.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>

namespace hedit {
namespace {

/// 補完を行う本文の上限(文字数)。
constexpr int kMaximumSourceLength = 200000;

/// 返す候補の上限。
constexpr int kMaximumItems = 250;

/// 名前の解決をたどる深さの上限(循環するimportで止まらなくなるのを防ぐ)。
constexpr int kMaximumResolveDepth = 8;

/** @brief ASCIIの英字か``_``か(Pythonの正規表現``[A-Za-z_]``と同じ)。 @param c 文字。 @return 該当すればtrue。 */
bool isAsciiNameStart(QChar c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}

/** @brief ``import``か``from``の後ろでモジュール名を書いている行か。 @param line 行。 @return 該当すればtrue。 */
bool isImportLine(const QString& line) {
    static const QRegularExpression pattern("^\\s*(import|from)\\s+[\\w.]*$",
                                            QRegularExpression::UseUnicodePropertiesOption);
    return pattern.match(line).hasMatch();
}

/** @brief 表の中の名前を、候補の一覧にする。
 * @param symbols 名前の表(名前順)。
 * @param prefix 入力途中の名前。``_``で始まらなければ、``_``で始まる名前を除く。
 * @return 候補(最大250件)。
 */
QList<CompletionItem> itemsFor(const SymbolTable& symbols, const QString& prefix) {
    QList<CompletionItem> items;
    const bool wantsPrivate = prefix.startsWith('_');
    for (auto it = symbols.begin(); it != symbols.end() && items.size() < kMaximumItems; ++it) {
        if (!it.key().startsWith(prefix) || (!wantsPrivate && it.key().startsWith('_'))) {
            continue;
        }
        items.append({it.key(), it.value().detail, it.value().kindName()});
    }
    return items;
}

}  // namespace

QString trailingDottedName(const QString& source) {
    int start = source.size();
    while (start > 0 && (isNamePart(source[start - 1]) || source[start - 1] == '.')) {
        --start;
    }
    for (int i = start; i < source.size(); ++i) {
        if (isAsciiNameStart(source[i])) {
            return source.mid(i);
        }
    }
    return QString();
}

CompletionEngine::CompletionEngine(ModuleSource source) : source_(std::move(source)) {}

void CompletionEngine::setEnvironment(const CompletionEnvironment& environment) {
    environment_ = environment;
}

void CompletionEngine::clearCaches() {
    files_.clear();
    localsText_.clear();
    localsSymbols_.clear();
}

SymbolTable CompletionEngine::localDeclarations(const QString& text) {
    // 候補を出すたびに最後の行だけが変わる。それより前が同じなら、前回の結果を使う。
    if (text != localsText_ || localsText_.isNull()) {
        localsText_ = text.isNull() ? QString("") : text;
        localsSymbols_ = extractPythonDeclarations(text).symbols;
    }
    return localsSymbols_;
}

QStringList CompletionEngine::searchPaths(Request& request) {
    if (!request.paths) {
        request.paths = source_.searchPaths ? source_.searchPaths() : QStringList();
    }
    return *request.paths;
}

SymbolTable CompletionEngine::fileDeclarations(const QString& path, const QString& moduleName) {
    const QFileInfo info(path);
    auto cached = files_.find(path);
    if (!info.isFile()) {
        return cached != files_.end() ? cached->symbols : SymbolTable();
    }
    const QDateTime modified = info.lastModified();
    if (cached != files_.end() && cached->modified == modified && cached->size == info.size()) {
        return cached->symbols;
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        return cached != files_.end() ? cached->symbols : SymbolTable();
    }
    QByteArray bytes = file.readAll();
    if (bytes.startsWith("\xef\xbb\xbf")) {
        bytes.remove(0, 3);
    }
    const DeclarationResult result = extractPythonDeclarations(QString::fromUtf8(bytes), moduleName);
    if (!result.complete && cached != files_.end()) {
        // 保存途中などで書きかけのファイルは、前回の正しい結果を使い続ける。
        return cached->symbols;
    }
    files_.insert(path, {modified, info.size(), result.symbols, result.docstring});
    return result.symbols;
}

QList<CompletionEngine::ModuleLocation> CompletionEngine::locateModule(Request& request, const QString& name) {
    QList<ModuleLocation> locations;
    const QStringList parts = name.split('.');
    for (const QString& part : parts) {
        if (!isIdentifier(part)) {
            return locations;
        }
    }
    for (const QString& root : searchPaths(request)) {
        const QString base = QDir(root).filePath(parts.join('/'));
        ModuleLocation location;
        if (QFileInfo(base).isDir()) {
            // パッケージ。__init__.pyの無いフォルダー(名前空間パッケージ)なら、次の場所も探す。
            location.packageFolder = base;
            const QString init = QDir(base).filePath("__init__.py");
            if (QFileInfo(init).isFile()) {
                location.file = init;
                location.moduleName = name + ".__init__";
            }
        } else if (QFileInfo(base + ".py").isFile()) {
            location.file = base + ".py";
            location.moduleName = name;
        } else {
            continue;
        }
        locations.append(location);
        if (!location.file.isEmpty()) {
            break;  // Pythonと同じく、最初に見つかったファイルを使う。
        }
    }
    return locations;
}

SymbolTable CompletionEngine::moduleMembers(Request& request, const QString& name) {
    const auto known = request.modules.find(name);
    if (known != request.modules.end()) {
        return *known;
    }
    SymbolTable result;
    // 1. 読み込み済みなら、今の公開名をPythonから受け取り、ファイルの宣言(関数の引数など)で補う。
    LoadedModule loaded;
    if (source_.loadedModule && source_.loadedModule(name, &loaded)) {
        result = loaded.members;
        if (loaded.file.endsWith(".py")) {
            const QString moduleName = QFileInfo(loaded.file).fileName() == "__init__.py" ? name + ".__init__" : name;
            const SymbolTable declared = fileDeclarations(loaded.file, moduleName);
            for (auto it = declared.begin(); it != declared.end(); ++it) {
                result.insert(it.key(), it.value());
            }
        }
        request.modules.insert(name, result);
        return result;
    }
    // 2. まだ読み込まれていなければ、sys.pathからファイルを探す(importも実行もしない)。
    for (const ModuleLocation& location : locateModule(request, name)) {
        if (!location.packageFolder.isEmpty()) {
            // パッケージ: 中のモジュールとサブパッケージも候補にする。
            const auto entries = QDir(location.packageFolder).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot);
            for (const QFileInfo& entry : entries) {
                const QString entryName = entry.fileName();
                const bool python = entryName.endsWith(".py");
                const QString stem = python ? entryName.left(entryName.size() - 3) : entryName;
                if (isIdentifier(stem) && !stem.startsWith('_') && (entry.isDir() || python) && !result.contains(stem)) {
                    result.insert(stem, Symbol::module(name + "." + stem));
                }
            }
        }
        if (!location.file.isEmpty()) {
            const SymbolTable declared = fileDeclarations(location.file, location.moduleName);
            for (auto it = declared.begin(); it != declared.end(); ++it) {
                result.insert(it.key(), it.value());
            }
        }
    }
    request.modules.insert(name, result);
    return result;
}

SymbolTable CompletionEngine::resolve(Request& request, const Symbol& item, int depth) {
    if (depth > kMaximumResolveDepth) {
        return SymbolTable();
    }
    switch (item.type) {
    case SymbolType::Import: {
        // from X import Y: XモジュールのYを探す。見つからなければ、X.Yというモジュールとして扱う。
        const QString qualified = item.fromModule + "." + item.fromName;
        const SymbolTable parent = moduleMembers(request, item.fromModule);
        const auto found = parent.find(item.fromName);
        const Symbol value = found != parent.end() ? found.value() : Symbol::module(qualified);
        if (value == item) {
            return moduleMembers(request, qualified);  // 自分自身を指している(循環)なら、モジュールとして読む。
        }
        return resolve(request, value, depth + 1);
    }
    case SymbolType::Module:
        return moduleMembers(request, item.target);
    default:
        return item.members ? *item.members : SymbolTable();
    }
}

QString CompletionEngine::moduleDocstring(Request& request, const QString& name, bool* found) {
    *found = false;
    // 読み込み済みなら、今のモジュールの__doc__を使う。
    QString signature;
    QString doc;
    if (source_.describe && source_.describe(name, QStringList(), &signature, &doc)) {
        *found = true;
        return doc;
    }
    // まだ読み込まれていなければ、ファイルの先頭の文字列を読む(実行はしない)。
    for (const ModuleLocation& location : locateModule(request, name)) {
        *found = true;
        if (location.file.isEmpty()) {
            continue;  // 名前空間パッケージにはdocstringが無い。
        }
        fileDeclarations(location.file, location.moduleName);
        const auto cached = files_.constFind(location.file);
        return cached != files_.constEnd() ? cached->docstring : QString();
    }
    return QString();
}

void CompletionEngine::followImports(Request& request, Symbol* item, QString* module, QStringList* path) {
    for (int depth = 0; depth < kMaximumResolveDepth && item->type == SymbolType::Import; ++depth) {
        const QString fromModule = item->fromModule;
        const QString fromName = item->fromName;
        const SymbolTable parent = moduleMembers(request, fromModule);
        const auto found = parent.find(fromName);
        if (found != parent.end() && found.value() != *item) {
            *item = found.value();
            *module = fromModule;
            *path = QStringList{fromName};
        } else {
            // Xの中に見つからなければ、X.Yというモジュールとして扱う。
            *item = Symbol::module(fromModule + "." + fromName);
            module->clear();
            path->clear();
        }
    }
}

HoverInfo CompletionEngine::describe(const QString& text, int end) {
    HoverInfo info;
    if (text.size() > kMaximumSourceLength || end < 0 || end > text.size()) {
        return info;
    }
    // sys.pathとモジュールの中身は、この1回の問い合わせの中だけ使い回す。
    Request request;
    const QString token = trailingDottedName(text.left(end));
    if (token.isEmpty() || token.endsWith('.')) {
        return info;
    }
    const QStringList parts = token.split('.');
    const SymbolTable locals = localDeclarations(text);

    // 1. 最初の名前: この本文の宣言 → 組み込みの名前 → モジュール名。
    Symbol item;
    QString module;    // itemがあるモジュール(本文の中なら空)。
    QStringList path;  // モジュールの中でのitemの位置。
    const auto local = locals.find(parts.first());
    if (local != locals.end()) {
        item = local.value();
    } else if (environment_.keywords.contains(parts.first())) {
        return info;
    } else if (environment_.builtins.contains(parts.first())) {
        item = Symbol::category(SymbolType::Builtin);
        module = "builtins";
        path = QStringList{parts.first()};
    } else {
        item = Symbol::module(parts.first());
    }
    followImports(request, &item, &module, &path);

    // 2. 点の後ろの名前を順にたどる。
    for (int i = 1; i < parts.size(); ++i) {
        if (item.type == SymbolType::Module) {
            module = item.target;
            const SymbolTable members = moduleMembers(request, module);
            const auto found = members.find(parts[i]);
            if (found == members.end()) {
                return info;
            }
            item = found.value();
            path = QStringList{parts[i]};
        } else if (item.members) {
            const auto found = item.members->find(parts[i]);
            if (found == item.members->end()) {
                return info;
            }
            item = found.value();
            path.append(parts[i]);
        } else {
            return info;  // 変数の型は推論しないので、その先はたどれない。
        }
        followImports(request, &item, &module, &path);
    }

    // 3. モジュールなら、モジュールのdocstring。
    if (item.type == SymbolType::Module) {
        bool found = false;
        info.doc = moduleDocstring(request, item.target, &found);
        if (found) {
            info.signature = "module " + item.target;
        }
        return info;
    }
    // 4. 関数・クラス。ソースから読めなかった説明は、読み込み済みのモジュールならPythonに問い合わせる。
    info.signature = item.signature;
    info.doc = item.doc;
    if (info.doc.isEmpty() && !module.isEmpty() && source_.describe) {
        QString signature;
        QString doc;
        if (source_.describe(module, path, &signature, &doc)) {
            info.doc = doc;
            if (info.signature.isEmpty()) {
                info.signature = signature;
            }
        }
    }
    return info;
}

CompletionResult CompletionEngine::complete(const QString& source) {
    CompletionResult result;
    if (source.size() > kMaximumSourceLength) {
        return result;
    }
    // sys.pathとモジュールの中身は、この1回の補完の中だけ使い回す(次の補完では取り直す)。
    Request request;

    const QString token = trailingDottedName(source);
    const int lastNewline = source.lastIndexOf('\n');
    const QString line = source.mid(lastNewline + 1);
    SymbolTable symbols;
    QString prefix;

    if (isImportLine(line)) {
        if (token.contains('.')) {
            // import maya.cm → mayaパッケージの中の名前。
            prefix = token.section('.', -1);
            symbols = moduleMembers(request, token.section('.', 0, -2));
        } else {
            prefix = token;
            const QStringList names = source_.topLevelNames ? source_.topLevelNames() : QStringList();
            for (const QString& name : names) {
                symbols.insert(name.section('.', 0, 0), Symbol::module(name.section('.', 0, 0)));
            }
        }
        result.items = itemsFor(symbols, prefix);
        return result;
    }

    // カーソルの行より前の宣言。最後の行は入力途中なので含めない。
    const SymbolTable locals = localDeclarations(lastNewline >= 0 ? source.left(lastNewline) : QString(""));
    static const QRegularExpression fromImport("^\\s*from\\s+([\\w.]+)\\s+import\\s+(\\w*)$",
                                               QRegularExpression::UseUnicodePropertiesOption);
    const QRegularExpressionMatch fromMatch = fromImport.match(line);
    if (fromMatch.hasMatch()) {
        // from maya import cm → mayaの中の名前。
        symbols = moduleMembers(request, fromMatch.captured(1));
        prefix = fromMatch.captured(2);
    } else if (token.contains('.')) {
        // a.b.c → aの中のbの中の、cで始まる名前。
        const QStringList parts = token.split('.');
        Symbol item = Symbol::module(parts.first());
        const auto local = locals.find(parts.first());
        if (local != locals.end()) {
            item = local.value();
        }
        for (int i = 1; i + 1 < parts.size(); ++i) {
            const SymbolTable members = resolve(request, item);
            item = members.value(parts[i]);
        }
        symbols = resolve(request, item);
        prefix = parts.last();
    } else {
        // 名前だけ: 組み込みの名前・予約語・この本文の宣言(同じ名前なら後のものが優先)。
        prefix = token;
        for (const QString& name : environment_.builtins) {
            symbols.insert(name, Symbol::category(SymbolType::Builtin));
        }
        for (const QString& name : environment_.keywords) {
            symbols.insert(name, Symbol::category(SymbolType::Keyword));
        }
        for (auto it = locals.begin(); it != locals.end(); ++it) {
            symbols.insert(it.key(), it.value());
        }
    }
    result.items = itemsFor(symbols, prefix);
    return result;
}

}  // namespace hedit
