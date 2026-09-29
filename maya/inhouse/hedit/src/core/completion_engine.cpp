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
        items.append({it.key(), it.value().detail, it.value().kind});
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

QStringList CompletionEngine::searchPaths() {
    if (!requestPaths_) {
        requestPaths_ = source_.searchPaths ? source_.searchPaths() : QStringList();
    }
    return *requestPaths_;
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
    files_.insert(path, {modified, info.size(), result.symbols});
    return result.symbols;
}

SymbolTable CompletionEngine::moduleMembers(const QString& name) {
    const auto known = requestModules_.find(name);
    if (known != requestModules_.end()) {
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
        requestModules_.insert(name, result);
        return result;
    }
    // 2. まだ読み込まれていなければ、sys.pathからファイルを探す(importも実行もしない)。
    const QStringList parts = name.split('.');
    for (const QString& part : parts) {
        if (!isIdentifier(part)) {
            return result;
        }
    }
    for (const QString& root : searchPaths()) {
        const QString base = QDir(root).filePath(parts.join('/'));
        QString filename = base + ".py";
        QString moduleName = name;
        if (QFileInfo(base).isDir()) {
            // パッケージ: 中のモジュールとサブパッケージも候補にする。
            filename = QDir(base).filePath("__init__.py");
            moduleName = name + ".__init__";
            const auto entries = QDir(base).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
            for (const QFileInfo& entry : entries) {
                const QString entryName = entry.fileName();
                const bool python = entryName.endsWith(".py");
                const QString stem = python ? entryName.left(entryName.size() - 3) : entryName;
                if (isIdentifier(stem) && !stem.startsWith('_') && (entry.isDir() || python) && !result.contains(stem)) {
                    Symbol symbol;
                    symbol.target = name + "." + stem;
                    result.insert(stem, symbol);
                }
            }
        }
        if (!QFileInfo(filename).isFile()) {
            continue;  // __init__.pyの無いフォルダー(名前空間パッケージ)は、次の場所も探す。
        }
        const SymbolTable declared = fileDeclarations(filename, moduleName);
        for (auto it = declared.begin(); it != declared.end(); ++it) {
            result.insert(it.key(), it.value());
        }
        break;
    }
    requestModules_.insert(name, result);
    return result;
}

SymbolTable CompletionEngine::resolve(const Symbol& item, int depth) {
    if (depth > kMaximumResolveDepth) {
        return SymbolTable();
    }
    if (!item.fromName.isEmpty()) {
        // from X import Y: XモジュールのYを探す。見つからなければ、X.Yというモジュールとして扱う。
        const QString qualified = item.fromModule + "." + item.fromName;
        const SymbolTable parent = moduleMembers(item.fromModule);
        Symbol value;
        value.target = qualified;
        const auto found = parent.find(item.fromName);
        if (found != parent.end()) {
            value = found.value();
        }
        if (value == item) {
            return moduleMembers(qualified);  // 自分自身を指している(循環)なら、モジュールとして読む。
        }
        return resolve(value, depth + 1);
    }
    if (!item.target.isEmpty()) {
        return moduleMembers(item.target);
    }
    return item.members ? *item.members : SymbolTable();
}

CompletionResult CompletionEngine::complete(const QString& source) {
    CompletionResult result;
    if (source.size() > kMaximumSourceLength) {
        return result;
    }
    // sys.pathとモジュールの中身は、この1回の補完の中だけ使い回す(次の補完では取り直す)。
    requestPaths_.reset();
    requestModules_.clear();

    const QString token = trailingDottedName(source);
    const int lastNewline = source.lastIndexOf('\n');
    const QString line = source.mid(lastNewline + 1);
    SymbolTable symbols;
    QString prefix;

    if (isImportLine(line)) {
        if (token.contains('.')) {
            // import maya.cm → mayaパッケージの中の名前。
            prefix = token.section('.', -1);
            symbols = moduleMembers(token.section('.', 0, -2));
        } else {
            prefix = token;
            const QStringList names = source_.topLevelNames ? source_.topLevelNames() : QStringList();
            for (const QString& name : names) {
                symbols.insert(name.section('.', 0, 0), Symbol());
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
        symbols = moduleMembers(fromMatch.captured(1));
        prefix = fromMatch.captured(2);
    } else if (token.contains('.')) {
        // a.b.c → aの中のbの中の、cで始まる名前。
        const QStringList parts = token.split('.');
        Symbol item;
        item.target = parts.first();
        const auto local = locals.find(parts.first());
        if (local != locals.end()) {
            item = local.value();
        }
        for (int i = 1; i + 1 < parts.size(); ++i) {
            const SymbolTable members = resolve(item);
            item = members.value(parts[i]);
        }
        symbols = resolve(item);
        prefix = parts.last();
    } else {
        // 名前だけ: 組み込みの名前・予約語・この本文の宣言(同じ名前なら後のものが優先)。
        prefix = token;
        for (const QString& name : environment_.builtins) {
            Symbol symbol;
            symbol.kind = "builtin";
            symbols.insert(name, symbol);
        }
        for (const QString& name : environment_.keywords) {
            Symbol symbol;
            symbol.kind = "keyword";
            symbols.insert(name, symbol);
        }
        for (auto it = locals.begin(); it != locals.end(); ++it) {
            symbols.insert(it.key(), it.value());
        }
    }
    result.items = itemsFor(symbols, prefix);
    return result;
}

}  // namespace hedit
