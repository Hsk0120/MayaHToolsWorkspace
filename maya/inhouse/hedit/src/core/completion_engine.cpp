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

/// 型の推論で、たどる深さの上限(x = A() の A がまた推論…と循環しないように)。
constexpr int kMaximumInferDepth = 4;

}  // namespace

QString inferredTypeExpression(const QString& text, const QString& name) {
    if (!isIdentifier(name)) {
        return QString();
    }
    const QString escaped = QRegularExpression::escape(name);
    // 1. 型ヒント付きの変数(x: pkg.A / x: "pkg.A" = ...)。引用符で囲んだ前方参照も読む。
    const QRegularExpression annotation("^\\s*" + escaped + "\\s*:\\s*(['\"]?)([A-Za-z_][\\w.]*)\\1(?![\\w.\\[])");
    // 2. 呼出しの結果の代入(x = pkg.A(...))。呼出しの後ろに続きがある(x = A().b)ものは対象外。
    const QRegularExpression call("^\\s*" + escaped + "\\s*=\\s*([A-Za-z_][\\w.]*)\\s*\\(");
    // 3. 関数の引数の型ヒント(def f(x: pkg.A) / 複数行の引数の , x: pkg.A)。
    const QRegularExpression parameter("[(,]\\s*" + escaped + "\\s*:\\s*(['\"]?)([A-Za-z_][\\w.]*)\\1(?![\\w.\\[])");
    const QStringList lines = text.split('\n');
    // カーソルに近い(後ろの)行の宣言を優先する。
    for (int i = lines.size() - 1; i >= 0; --i) {
        const QString& line = lines[i];
        QRegularExpressionMatch match = annotation.match(line);
        if (match.hasMatch()) {
            return match.captured(2);
        }
        match = call.match(line);
        if (match.hasMatch()) {
            // 呼出しが行の最後まで(括弧が閉じて終わる)かを確かめる。
            const QString rest = line.mid(match.capturedEnd() - 1).trimmed();
            int depth = 0;
            int closing = -1;
            for (int c = 0; c < rest.size(); ++c) {
                if (rest[c] == '(') {
                    ++depth;
                } else if (rest[c] == ')' && --depth == 0) {
                    closing = c;
                    break;
                }
            }
            const QString after = closing >= 0 ? rest.mid(closing + 1).trimmed() : QString();
            if (closing < 0 || after.isEmpty() || after.startsWith('#')) {
                return match.captured(1);
            }
            return QString();  // x = A().b など。最後の代入が推論できない形なら、それより前は見ない。
        }
        if (QRegularExpression("^\\s*" + escaped + "\\s*(=|\\+=)").match(line).hasMatch()) {
            return QString();  // 推論できない代入(x = 1 など)。それより前の宣言は使わない。
        }
        match = parameter.match(line);
        if (match.hasMatch()) {
            return match.captured(2);
        }
    }
    return QString();
}

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
                const auto existing = result.find(it.key());
                if (existing != result.end() && existing->members && it.value().members) {
                    // クラス: Pythonから受け取った中身(親クラスから受け継いだ名前を含む)に、
                    // ファイルの宣言(引数・docstring)を重ねる。
                    Symbol merged = it.value();
                    auto members = std::make_shared<SymbolTable>(*existing->members);
                    for (auto member = merged.members->begin(); member != merged.members->end(); ++member) {
                        members->insert(member.key(), member.value());
                    }
                    merged.members = members;
                    result.insert(it.key(), merged);
                } else {
                    result.insert(it.key(), it.value());
                }
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

CompletionEngine::Located CompletionEngine::resolveName(Request& request, const SymbolTable& scope,
                                                       const QString& text, const QString& name, int depth) {
    Located located;
    const auto local = scope.find(name);
    if (local != scope.end() && local.value().type != SymbolType::Value) {
        located.item = local.value();
        return located;
    }
    // 変数なら、代入・型ヒントからクラスを推論する(インスタンスはクラスの中身で補完する)。
    if (depth < kMaximumInferDepth) {
        const QString expression = inferredTypeExpression(text, name);
        if (!expression.isEmpty() && expression != name) {
            const Located type = walk(request, scope, text, expression.split('.'), depth + 1);
            if (type.found && type.item.type == SymbolType::Class) {
                return type;
            }
        }
    }
    if (local != scope.end()) {
        located.item = local.value();
    } else if (environment_.builtins.contains(name)) {
        located.item = Symbol::category(SymbolType::Builtin);
        located.module = "builtins";
        located.path = QStringList{name};
    } else {
        located.item = Symbol::module(name);
    }
    return located;
}

CompletionEngine::Located CompletionEngine::walk(Request& request, const SymbolTable& scope, const QString& text,
                                                const QStringList& parts, int depth) {
    Located located = resolveName(request, scope, text, parts.first(), depth);
    followImports(request, &located.item, &located.module, &located.path);
    for (int i = 1; i < parts.size(); ++i) {
        const SymbolTable members = membersOf(request, located, scope, depth);
        const auto found = members.find(parts[i]);
        if (found == members.end()) {
            located.found = false;
            return located;
        }
        if (located.item.type == SymbolType::Module) {
            located.module = located.item.target;
            located.path = QStringList{parts[i]};
        } else {
            located.path.append(parts[i]);
        }
        located.item = found.value();
        followImports(request, &located.item, &located.module, &located.path);
    }
    return located;
}

SymbolTable CompletionEngine::membersOf(Request& request, const Located& located, const SymbolTable& scope,
                                        int depth) {
    if (located.item.type == SymbolType::Class) {
        // クラスが見つかった場所(本文の中か、どのモジュールか)で、親クラスの名前を探す。
        const SymbolTable home = located.module.isEmpty() ? scope : moduleMembers(request, located.module);
        return classMembers(request, located.item, home, located.module, depth);
    }
    return resolve(request, located.item);
}

SymbolTable CompletionEngine::classMembers(Request& request, const Symbol& item, const SymbolTable& home,
                                           const QString& module, int depth) {
    SymbolTable members = item.members ? *item.members : SymbolTable();
    if (depth >= kMaximumInferDepth) {
        return members;
    }
    // 親クラスから受け継いだ名前を足す(Pythonと同じく、先に書いた親・子クラス自身の名前を優先する)。
    for (const QString& base : item.bases) {
        Located parent = walk(request, home, QString(), base.split('.'), depth + 1);
        if (!parent.found || parent.item.type != SymbolType::Class) {
            continue;
        }
        if (parent.module.isEmpty()) {
            parent.module = module;  // 同じ場所で見つかった親クラス。
        }
        const SymbolTable parentHome = parent.module.isEmpty() ? home : moduleMembers(request, parent.module);
        const SymbolTable inherited = classMembers(request, parent.item, parentHome, parent.module, depth + 1);
        for (auto it = inherited.begin(); it != inherited.end(); ++it) {
            if (!members.contains(it.key())) {
                members.insert(it.key(), it.value());
            }
        }
    }
    return members;
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
    if (parts.size() == 1 && environment_.keywords.contains(parts.first())) {
        return info;
    }
    const SymbolTable locals = localDeclarations(text);
    // 名前をたどる(変数は代入・型ヒントからクラスを推論する)。推論はカーソルより前の本文で行う。
    const Located located = walk(request, locals, text.left(end), parts, 0);
    if (!located.found) {
        return info;
    }
    const Symbol& item = located.item;
    // モジュールなら、モジュールのdocstring。
    if (item.type == SymbolType::Module) {
        bool found = false;
        info.doc = moduleDocstring(request, item.target, &found);
        if (found) {
            info.signature = "module " + item.target;
        }
        return info;
    }
    // 関数・クラス。ソースから読めなかった説明は、読み込み済みのモジュールならPythonに問い合わせる。
    info.signature = item.signature;
    info.doc = item.doc;
    if (info.doc.isEmpty() && !located.module.isEmpty() && source_.describe) {
        QString signature;
        QString doc;
        if (source_.describe(located.module, located.path, &signature, &doc)) {
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
        // a.b.c → aの中のbの中の、cで始まる名前。変数(x = pkg.A() / x: pkg.A)はクラスを推論する。
        const QStringList parts = token.split('.');
        const Located located = walk(request, locals, source, parts.mid(0, parts.size() - 1), 0);
        if (located.found) {
            symbols = membersOf(request, located, locals, 0);
        }
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
