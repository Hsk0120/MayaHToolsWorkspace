/** @file completion_engine.cpp
 * @brief CompletionEngineの実装。
 * @details 入力のたびに呼ばれるので、次の点で時間とメモリーの確保を抑えている。
 * - 本文(最大20万文字)は、必要なときだけコピーする。部分はQStringViewで指す。
 * - 編集中の本文の宣言は、最近の数件の本文ごとに控える(補完・ホバー・候補の説明が違う本文で問い合わせるため)。
 * - sys.pathのフォルダーの中身は、フォルダーの更新日時が変わるまで一覧を使い回す(Pythonのimportと同じ考え方)。
 * - 読み込み済みのモジュールの公開名とファイルの宣言を重ねた結果は、どちらも変わっていなければ使い回す。
 */
#include "core/completion_engine.h"
#include "core/fuzzy_match.h"
#include "core/code_outline.h"
#include "core/module_scanner.h"
#include "core/script_file.h"
#include "core/python_declarations.h"
#include "core/script_lexer.h"
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QVector>
#include <algorithm>

namespace hedit {
namespace {

/// 補完を行う本文の上限(文字数)。
constexpr int kMaximumSourceLength = 200000;

/// 返す候補の上限。
constexpr int kMaximumItems = 250;

/// 名前の解決をたどる深さの上限(循環するimportで止まらなくなるのを防ぐ)。
constexpr int kMaximumResolveDepth = 8;

/// 編集中の本文の宣言を控える件数(補完・ホバー・候補の説明・クラスの__init__の分)。
constexpr int kMaximumCachedLocals = 4;

/// ファイルの宣言を控える件数の上限。超えたら、いちばん長く使っていないものを捨てる。
constexpr int kMaximumCachedFiles = 256;

/// フォルダーの一覧を控える件数の上限。超えたら全て捨てて作り直す。
constexpr int kMaximumCachedFolders = 1024;

/// 公開名とファイルの宣言を重ねた結果を控える件数の上限。超えたら全て捨てる。
constexpr int kMaximumMergedModules = 64;

/// フォルダーの更新日時を確かめ直すまでの時間(ミリ秒)。入力のたびにsys.pathの全フォルダーを調べないため。
constexpr int kFolderRecheckInterval = 1000;

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

/** @brief 候補にする名前の1件と、入力との一致の度合い。 */
struct RankedSymbol {
    int score;              ///< fuzzyScoreの値。
    const QString* name;    ///< 名前(表の中の文字列を指す)。
    const Symbol* symbol;   ///< 名前の情報(表の中を指す)。
};

/** @brief 度合いのよい順に並べ、上限までを候補にする。
 * @param ranked 一致した名前。並べ替える。
 * @return 候補(最大250件)。
 */
QList<CompletionItem> topItems(QVector<RankedSymbol>& ranked) {
    const int count = qMin(int(ranked.size()), kMaximumItems);
    // 使うのは上位の250件だけなので、全体を並べ替えずに上位だけを並べる(partial_sort)。
    std::partial_sort(ranked.begin(), ranked.begin() + count, ranked.end(),
                      [](const RankedSymbol& a, const RankedSymbol& b) {
                          return rankedBefore(a.score, *a.name, b.score, *b.name);
                      });
    QList<CompletionItem> items;
    items.reserve(count);
    for (int i = 0; i < count; ++i) {
        const Symbol& symbol = *ranked[i].symbol;
        items.append({*ranked[i].name, symbol.detail, symbol.kindName(), symbol.categoryName()});
    }
    return items;
}

/** @brief 表の中の名前を、入力との一致の度合いで選んで候補にする。
 * @param symbols 名前の表。
 * @param prefix 入力途中の名前。大文字小文字を区別せず、単語の頭からの飛び飛びの一致も含める(fuzzyScore)。
 *        ``_``で始まらなければ、``_``で始まる名前を除く。
 * @param skip この表にある名前は除く(nullptrなら除かない)。
 * @param ranked 一致した名前を足す先。
 */
void collectRanked(const SymbolTable& symbols, const QString& prefix, const SymbolTable* skip,
                   QVector<RankedSymbol>* ranked) {
    const bool wantsPrivate = prefix.startsWith('_');
    for (auto it = symbols.constBegin(); it != symbols.constEnd(); ++it) {
        if (!wantsPrivate && it.key().startsWith('_')) {
            continue;
        }
        if (skip && skip->contains(it.key())) {
            continue;
        }
        const int score = fuzzyScore(prefix, it.key());
        if (score >= 0) {
            ranked->append({score, &it.key(), &it.value()});
        }
    }
}

/** @brief 表の中の名前を、候補の一覧にする。
 * @param symbols 名前の表。
 * @param prefix 入力途中の名前。
 * @return 候補(一致の度合いのよい順、最大250件)。
 */
QList<CompletionItem> itemsFor(const SymbolTable& symbols, const QString& prefix) {
    QVector<RankedSymbol> ranked;
    collectRanked(symbols, prefix, nullptr, &ranked);
    return topItems(ranked);
}

/** @brief 2つの表を重ねた候補の一覧(同じ名前はlocalsを優先する)。表を実際に重ねる(コピーする)代わりに、両方から選ぶ。
 * @param base 組み込みの名前と予約語の表。
 * @param locals 本文の宣言。
 * @param prefix 入力途中の名前。
 * @return itemsFor(baseにlocalsを上書きした表, prefix)と同じ候補。
 */
QList<CompletionItem> mergedItemsFor(const SymbolTable& base, const SymbolTable& locals, const QString& prefix) {
    QVector<RankedSymbol> ranked;
    collectRanked(locals, prefix, nullptr, &ranked);
    collectRanked(base, prefix, &locals, &ranked);
    return topItems(ranked);
}

/// 型の推論で、たどる深さの上限(x = A() の A がまた推論…と循環しないように)。
constexpr int kMaximumInferDepth = 4;

/** @brief 行頭の空白の後ろが名前で、その後ろ(空白を除く)が指定の文字のどれかか。
 * @param line 行。
 * @param name 名前。
 * @param followers 名前の後ろに来てよい文字(``":=+"``など)。
 * @return 該当すればtrue。
 * @details 推論の正規表現(``^\s*name\s*:``など)が一致するための必要条件。空白はQChar::isSpaceで判断する
 * (正規表現の``\s``より広いので、一致し得る行を飛ばすことはない)。
 */
bool startsWithName(QStringView line, QStringView name, const char* followers) {
    qsizetype i = 0;
    while (i < line.size() && line[i].isSpace()) {
        ++i;
    }
    if (!line.mid(i).startsWith(name)) {
        return false;
    }
    i += name.size();
    while (i < line.size() && line[i].isSpace()) {
        ++i;
    }
    if (i >= line.size()) {
        return false;
    }
    for (const char* follower = followers; *follower; ++follower) {
        if (line[i] == QLatin1Char(*follower)) {
            return true;
        }
    }
    return false;
}

/** @brief ``(``か``,``の後ろに名前があり、その後ろが``:``の箇所があるか(引数の型ヒントの正規表現の必要条件)。
 * @param line 行。
 * @param name 名前。
 * @return あればtrue。
 */
bool hasParameterAnnotation(QStringView line, QStringView name) {
    for (qsizetype at = line.indexOf(name); at >= 0; at = line.indexOf(name, at + 1)) {
        qsizetype before = at;
        while (before > 0 && line[before - 1].isSpace()) {
            --before;
        }
        if (before == 0 || (line[before - 1] != '(' && line[before - 1] != ',')) {
            continue;
        }
        qsizetype after = at + name.size();
        while (after < line.size() && line[after].isSpace()) {
            ++after;
        }
        if (after < line.size() && line[after] == ':') {
            return true;
        }
    }
    return false;
}

/** @brief inferredTypeExpressionの本体(本文の一部をコピーせずに受け取る)。 @param text 本文。 @param name 変数名。 @return 式。 */
QString inferExpression(QStringView text, const QString& name) {
    if (text.isEmpty() || !isIdentifier(name)) {
        return QString();
    }
    const QString escaped = QRegularExpression::escape(name);
    // 正規表現は最初に照合するときに作られる。候補の行が無ければ作らない。
    // 1. 型ヒント付きの変数(x: pkg.A / x: "pkg.A" = ...)。引用符で囲んだ前方参照も読む。
    const QRegularExpression annotation("^\\s*" + escaped + "\\s*:\\s*(['\"]?)([A-Za-z_][\\w.]*)\\1(?![\\w.\\[])");
    // 2. 呼出しの結果の代入(x = pkg.A(...))。呼出しの後ろに続きがある(x = A().b)ものは対象外。
    const QRegularExpression call("^\\s*" + escaped + "\\s*=\\s*([A-Za-z_][\\w.]*)\\s*\\(");
    // 3. 推論できない代入(x = 1・x += 1)。比較の x == y は代入ではない。
    const QRegularExpression assignment("^\\s*" + escaped + "\\s*(?:=(?!=)|\\+=)");
    // 4. 関数の引数の型ヒント(def f(x: pkg.A) / 複数行の引数の , x: pkg.A)。
    const QRegularExpression parameter("[(,]\\s*" + escaped + "\\s*:\\s*(['\"]?)([A-Za-z_][\\w.]*)\\1(?![\\w.\\[])");
    const QStringView key(name);
    // カーソルに近い(後ろの)行の宣言を優先する。本文を行に分けず(split)、後ろから改行を探して1行ずつ見る。
    qsizetype lineEnd = text.size();
    for (;;) {
        const qsizetype newline = lineEnd > 0 ? text.lastIndexOf(QLatin1Char('\n'), lineEnd - 1) : -1;
        const QStringView view = text.mid(newline + 1, lineEnd - newline - 1);
        if (view.contains(key)) {
            const bool statement = startsWithName(view, key, ":=+");
            const bool annotated = hasParameterAnnotation(view, key);
            if (statement || annotated) {
                const QString line = view.toString();
                QRegularExpressionMatch match;
                if (statement) {
                    match = annotation.match(line);
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
                    if (assignment.match(line).hasMatch()) {
                        return QString();  // 推論できない代入(x = 1 など)。それより前の宣言は使わない。
                    }
                }
                if (annotated) {
                    match = parameter.match(line);
                    if (match.hasMatch()) {
                        return match.captured(2);
                    }
                }
            }
        }
        if (newline < 0) {
            break;
        }
        lineEnd = newline;
    }
    return QString();
}

/** @brief trailingDottedNameの本体。 @param source カーソルまでの本文。 @return 末尾の名前。 */
QString trailingName(QStringView source) {
    qsizetype start = source.size();
    while (start > 0 && (isNamePart(source[start - 1]) || source[start - 1] == '.')) {
        --start;
    }
    for (qsizetype i = start; i < source.size(); ++i) {
        if (isAsciiNameStart(source[i])) {
            return source.mid(i).toString();
        }
    }
    return QString();
}

/** @brief 本文の最後の行が、宣言を含み得る行か(含み得なければ、最後の行を除いた本文と宣言は同じ)。
 * @param line 最後の行(前の行の文字列・括弧は閉じている前提)。
 * @return 代入(``=``)・注釈(``:``)・def・class・import・fromを含むか、文字列で始まる(前の行の見出しの
 * docstringになり得る)ならtrue。
 */
bool lastLineMayDeclare(QStringView line) {
    if (line.endsWith(QLatin1Char('\r'))) {
        line.chop(1);
    }
    const QVector<Token> tokens = tokenizeLine(line, ScriptLanguage::Python, kLexerNormal, nullptr);
    for (int i = 0; i < tokens.size(); ++i) {
        const Token& token = tokens[i];
        const QStringView word = line.mid(token.start, token.length);
        if (i == 0 && token.type == TokenType::String) {
            return true;
        }
        if (token.type == TokenType::Name
            && (word == QLatin1String("def") || word == QLatin1String("class") || word == QLatin1String("import")
                || word == QLatin1String("from"))) {
            return true;
        }
        if (token.type == TokenType::Operator && (word == QLatin1String("=") || word == QLatin1String(":"))) {
            return true;
        }
    }
    return false;
}

/** @brief フォルダーの項目の名前を、比べるための形にする。
 * @param name 名前。
 * @return WindowsではQFileInfoと同じく大文字小文字を区別しないよう、大文字小文字をそろえた名前。それ以外はそのまま。
 */
QString folderKey(const QString& name) {
#ifdef Q_OS_WIN
    return name.toCaseFolded();
#else
    return name;
#endif
}

}  // namespace

QString inferredTypeExpression(const QString& text, const QString& name) {
    return inferExpression(text, name);
}

QString trailingDottedName(const QString& source) {
    return trailingName(source);
}

CompletionEngine::CompletionEngine(ModuleSource source) : source_(std::move(source)) {}

void CompletionEngine::setEnvironment(const CompletionEnvironment& environment) {
    // 名前だけの補完のたびに組み込みの名前・予約語を表へ入れ直さないよう、ここで1回だけ作る。
    // 同じ名前は予約語を優先する(以前の、組み込みの名前・予約語の順に入れていた処理と同じ)。
    baseNames_.clear();
    for (const QString& name : environment.builtins) {
        baseNames_.insert(name, Symbol::category(SymbolType::Builtin));
    }
    for (const QString& name : environment.keywords) {
        baseNames_.insert(name, Symbol::category(SymbolType::Keyword));
    }
    builtins_ = QSet<QString>(environment.builtins.begin(), environment.builtins.end());
    keywords_ = QSet<QString>(environment.keywords.begin(), environment.keywords.end());
}

void CompletionEngine::clearCaches() {
    files_.clear();
    locals_.clear();
    folders_.clear();
    merged_.clear();
}

const CompletionEngine::CachedLocals* CompletionEngine::findLocals(QStringView text) {
    for (CachedLocals& entry : locals_) {
        if (entry.text.size() == text.size() && QStringView(entry.text) == text) {
            entry.used = ++localsClock_;
            return &entry;
        }
    }
    return nullptr;
}

const CompletionEngine::CachedLocals& CompletionEngine::declarationsFor(QStringView text, const QString* whole) {
    if (const CachedLocals* cached = findLocals(text)) {
        return *cached;
    }
    CachedLocals entry;
    entry.text = whole ? *whole : text.toString();
    const DeclarationResult result = extractPythonDeclarations(entry.text);
    entry.symbols = result.symbols;
    entry.complete = result.complete;
    entry.used = ++localsClock_;
    if (locals_.size() < kMaximumCachedLocals) {
        locals_.append(entry);
        return locals_.last();
    }
    int oldest = 0;
    for (int i = 1; i < locals_.size(); ++i) {
        if (locals_[i].used < locals_[oldest].used) {
            oldest = i;
        }
    }
    locals_[oldest] = entry;
    return locals_[oldest];
}

SymbolTable CompletionEngine::localDeclarations(const QString& text) {
    return declarationsFor(text, &text).symbols;
}

SymbolTable CompletionEngine::documentDeclarations(const QString& text) {
    const qsizetype lastNewline = text.lastIndexOf(QLatin1Char('\n'));
    if (lastNewline >= 0) {
        const QStringView prefix = QStringView(text).left(lastNewline);
        // 前の行の続き(行末の \)なら、最後の行も前の文の一部になるので使わない(コメントの中の \ も念のため除く)。
        const bool continued = prefix.endsWith(QLatin1Char('\\')) || prefix.endsWith(QLatin1String("\\\r"));
        if (!continued && !lastLineMayDeclare(QStringView(text).mid(lastNewline + 1))) {
            const CachedLocals* cached = findLocals(prefix);
            if (cached && cached->complete) {
                return cached->symbols;
            }
        }
    }
    return declarationsFor(text, &text).symbols;
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
    if (cached != files_.end()) {
        cached->used = ++filesClock_;
    }
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
    if (cached == files_.end() && files_.size() >= kMaximumCachedFiles) {
        // 上限に達したら、いちばん長く使っていないファイルを捨てる。
        auto oldest = files_.begin();
        for (auto it = files_.begin(); it != files_.end(); ++it) {
            if (it->used < oldest->used) {
                oldest = it;
            }
        }
        files_.erase(oldest);
    }
    files_.insert(path, {modified, info.size(), result.symbols, result.docstring, ++filesClock_});
    return result.symbols;
}

CompletionEngine::FolderListing& CompletionEngine::folderListing(const QString& folder) {
    auto it = folders_.find(folder);
    if (it != folders_.end() && it->checked.isValid() && it->checked.elapsed() < kFolderRecheckInterval) {
        return *it;
    }
    const QFileInfo info(folder);
    const bool exists = info.isDir();
    const QDateTime modified = exists ? info.lastModified() : QDateTime();
    if (it != folders_.end() && it->exists == exists && it->modified == modified) {
        it->checked.restart();
        return *it;
    }
    if (it == folders_.end()) {
        if (folders_.size() >= kMaximumCachedFolders) {
            folders_.clear();
        }
        it = folders_.insert(folder, FolderListing());
    }
    FolderListing& listing = *it;
    listing = FolderListing();
    listing.exists = exists;
    listing.modified = modified;
    listing.checked.start();
    if (exists) {
        // QFileInfo::isDir・isFileと同じく、隠し項目・システムの項目も含めて調べる。
        QDirIterator entries(folder, QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
        while (entries.hasNext()) {
            entries.next();
            const QFileInfo entry = entries.fileInfo();
            listing.entries.insert(folderKey(entries.fileName()), {entry.isDir(), entry.isFile()});
        }
    }
    return listing;
}

QHash<QString, CompletionEngine::FolderEntry> CompletionEngine::folderEntries(const QString& folder) {
    return folderListing(folder).entries;
}

QVector<CompletionEngine::PackageEntry> CompletionEngine::packageEntries(const QString& folder) {
    FolderListing& listing = folderListing(folder);
    if (!listing.packageListed) {
        // 以前と同じQDirの既定の一覧(隠し項目を含まない)から作る。
        listing.packageListed = true;
        const auto entries = QDir(folder).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot);
        for (const QFileInfo& entry : entries) {
            listing.packageEntries.append({entry.fileName(), entry.isDir()});
        }
    }
    return listing.packageEntries;
}

QList<CompletionEngine::ModuleLocation> CompletionEngine::locateModule(Request& request, const QString& name) {
    QList<ModuleLocation> locations;
    const QStringList parts = name.split('.');
    QStringList keys;
    for (const QString& part : parts) {
        if (!isIdentifier(part)) {
            return locations;
        }
        keys.append(folderKey(part));
    }
    const QString relative = parts.join('/');
    const QString moduleFileKey = keys.last() + ".py";
    const QString initKey = folderKey(QStringLiteral("__init__.py"));
    for (const QString& root : searchPaths(request)) {
        // フォルダーを直接調べる代わりに、親のフォルダーの一覧で、途中のフォルダー(a.b.cのa・b)から順に確かめる。
        QString folder = root;
        bool found = true;
        for (int i = 0; i + 1 < parts.size() && found; ++i) {
            const auto entry = folderEntries(folder).value(keys[i]);
            found = entry.directory;
            folder = QDir(folder).filePath(parts[i]);
        }
        if (!found) {
            continue;
        }
        const QHash<QString, FolderEntry> entries = folderEntries(folder);
        const QString base = QDir(root).filePath(relative);
        ModuleLocation location;
        if (entries.value(keys.last()).directory) {
            // パッケージ。__init__.pyの無いフォルダー(名前空間パッケージ)なら、次の場所も探す。
            location.packageFolder = base;
            if (folderEntries(base).value(initKey).file) {
                location.file = QDir(base).filePath("__init__.py");
                location.moduleName = name + ".__init__";
            }
        } else if (entries.value(moduleFileKey).file) {
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
            // 公開名(hedit.bridgeは変わっていなければ同じ表を返す)とファイルの宣言が前回と同じ表なら、重ねた結果を使い回す。
            // maya.cmdsのような数千件の表を、問い合わせのたびにコピーして重ねないため。
            const auto merged = merged_.constFind(name);
            if (merged != merged_.constEnd() && merged->members.isSharedWith(loaded.members)
                && merged->declared.isSharedWith(declared) && merged->file == loaded.file) {
                result = merged->result;
            } else {
                for (auto it = declared.begin(); it != declared.end(); ++it) {
                    const auto existing = result.find(it.key());
                    if (existing != result.end() && existing->members && it.value().members) {
                        // クラス: Pythonから受け取った中身(親クラスから受け継いだ名前を含む)に、
                        // ファイルの宣言(引数・docstring)を重ねる。
                        Symbol combined = it.value();
                        auto members = std::make_shared<SymbolTable>(*existing->members);
                        for (auto member = combined.members->begin(); member != combined.members->end(); ++member) {
                            members->insert(member.key(), member.value());
                        }
                        combined.members = members;
                        result.insert(it.key(), combined);
                    } else {
                        result.insert(it.key(), it.value());
                    }
                }
                if (merged_.size() >= kMaximumMergedModules) {
                    merged_.clear();
                }
                merged_.insert(name, {loaded.members, loaded.file, declared, result});
            }
        }
        request.modules.insert(name, result);
        return result;
    }
    // 2. まだ読み込まれていなければ、sys.pathからファイルを探す(importも実行もしない)。
    for (const ModuleLocation& location : locateModule(request, name)) {
        if (!location.packageFolder.isEmpty()) {
            // パッケージ: 中のモジュールとサブパッケージも候補にする。
            for (const PackageEntry& entry : packageEntries(location.packageFolder)) {
                const bool python = entry.name.endsWith(".py");
                const QString stem = python ? entry.name.left(entry.name.size() - 3) : entry.name;
                if (isIdentifier(stem) && !stem.startsWith('_') && (entry.directory || python) && !result.contains(stem)) {
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

CompletionEngine::Located CompletionEngine::resolveName(Request& request, const SymbolTable& scope, QStringView text,
                                                       const QString& name, int depth) {
    Located located;
    const auto local = scope.find(name);
    if (local != scope.end() && local.value().type != SymbolType::Value) {
        located.item = local.value();
        located.path = QStringList{name};  // 本文の中での位置(定義へ移動で使う。moduleが空なら本文の中)。
        return located;
    }
    // 変数なら、代入・型ヒントからクラスを推論する(インスタンスはクラスの中身で補完する)。本文が空なら推論しない。
    if (depth < kMaximumInferDepth && !text.isEmpty()) {
        const QString expression = inferExpression(text, name);
        if (!expression.isEmpty() && expression != name) {
            const Located type = walk(request, scope, text, expression.split('.'), depth + 1);
            if (type.found && type.item.type == SymbolType::Class) {
                return type;
            }
        }
    }
    if (local != scope.end()) {
        located.item = local.value();
        located.path = QStringList{name};
    } else if (builtins_.contains(name)) {
        located.item = Symbol::category(SymbolType::Builtin);
        located.module = "builtins";
        located.path = QStringList{name};
    } else {
        located.item = Symbol::module(name);
    }
    return located;
}

CompletionEngine::Located CompletionEngine::walk(Request& request, const SymbolTable& scope, QStringView text,
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
        Located parent = walk(request, home, QStringView(), base.split('.'), depth + 1);
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
    // カーソルより前の本文は、コピーせずに指す(推論もこの範囲で行う)。
    const QStringView before = QStringView(text).left(end);
    const QString token = trailingName(before);
    if (token.isEmpty() || token.endsWith('.')) {
        return info;
    }
    const QStringList parts = token.split('.');
    if (parts.size() == 1 && keywords_.contains(parts.first())) {
        return info;
    }
    const SymbolTable locals = documentDeclarations(text);
    // 名前をたどる(変数は代入・型ヒントからクラスを推論する)。推論はカーソルより前の本文で行う。
    const Located located = walk(request, locals, before, parts, 0);
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

QString CompletionEngine::moduleFile(Request& request, const QString& name) {
    for (const ModuleLocation& location : locateModule(request, name)) {
        if (!location.file.isEmpty()) {
            return location.file;
        }
    }
    LoadedModule loaded;
    if (source_.loadedModule && source_.loadedModule(name, &loaded) && loaded.file.endsWith(".py")) {
        return loaded.file;
    }
    return QString();
}

DefinitionLocation CompletionEngine::definition(const QString& text, int end) {
    DefinitionLocation location;
    if (text.size() > kMaximumSourceLength || end < 0 || end > text.size()) {
        return location;
    }
    Request request;
    const QStringView before = QStringView(text).left(end);
    const QString token = trailingName(before);
    if (token.isEmpty() || token.endsWith('.')) {
        return location;
    }
    const QStringList parts = token.split('.');
    if (parts.size() == 1 && keywords_.contains(parts.first())) {
        return location;
    }
    const int cursorLine = int(before.count(QLatin1Char('\n')));
    // 本文の中で、構成(クラス・関数・トップレベルの変数)から位置を探す。無ければ関数の中の変数・引数を探す。
    auto findInText = [](const QString& source, const QStringList& path, int beforeLine, DefinitionLocation* found) {
        const QList<OutlineEntry> outline = buildOutline(source, ScriptLanguage::Python);
        int index = findOutlinePath(outline, path);
        if (index < 0 && !path.isEmpty()) {
            // 親クラスから受け継いだメソッドなど: 同じ名前の定義を探す。
            for (int i = 0; i < outline.size() && index < 0; ++i) {
                if (outline[i].name == path.last() && outline[i].kind != "variable") {
                    index = i;
                }
            }
        }
        if (index >= 0) {
            found->line = outline[index].line;
            found->column = outline[index].column;
            return;
        }
        if (path.size() == 1 && beforeLine >= 0) {
            int column = 0;
            found->line = localDefinitionLine(source, path.first(), beforeLine + 1, &column);
            found->column = column;
        }
    };
    const SymbolTable locals = documentDeclarations(text);
    if (parts.size() == 1) {
        // 変数(関数の中の変数・引数・for の変数・型を推論した変数)は、クラスではなく変数自身の定義
        // (カーソルより前の代入など)へ移る。def・class・importの名前は、下でたどる。
        const auto local = locals.find(parts.first());
        if (local == locals.end() || local.value().type == SymbolType::Value) {
            int column = 0;
            location.line = localDefinitionLine(text, parts.first(), cursorLine + 1, &column);
            location.column = column;
            if (location.found()) {
                return location;
            }
        }
    }
    const Located located = walk(request, locals, before, parts, 0);
    if (!located.found) {
        return location;
    }
    const Symbol& item = located.item;
    if (item.type == SymbolType::Module) {
        location.path = moduleFile(request, item.target);
        location.line = location.path.isEmpty() ? -1 : 0;
        return location;
    }
    if (located.module.isEmpty()) {
        findInText(text, located.path, parts.size() == 1 ? cursorLine : -1, &location);
        return location;
    }
    if (located.module == "builtins") {
        return location;
    }
    const QString file = moduleFile(request, located.module);
    QString source;
    QString error;
    if (file.isEmpty() || !readScriptFile(file, &source, &error)) {
        return location;
    }
    findInText(source, located.path, -1, &location);
    if (location.found()) {
        location.path = file;
    }
    return location;
}

CompletionResult CompletionEngine::complete(const QString& source) {
    CompletionResult result;
    if (source.size() > kMaximumSourceLength) {
        return result;
    }
    // sys.pathとモジュールの中身は、この1回の補完の中だけ使い回す(次の補完では取り直す)。
    Request request;

    const QString token = trailingDottedName(source);
    const int lastNewline = int(source.lastIndexOf('\n'));
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

    // カーソルの行より前の宣言。最後の行は入力途中なので含めない。前の行が同じなら控えを使う(本文はコピーしない)。
    const SymbolTable locals =
        declarationsFor(lastNewline >= 0 ? QStringView(source).left(lastNewline) : QStringView()).symbols;
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
        // 名前だけ: 組み込みの名前・予約語・この本文の宣言(同じ名前なら本文の宣言が優先)。
        // 表を重ねてコピーせず、名前順に並べて読む。
        result.items = mergedItemsFor(baseNames_, locals, token);
        return result;
    }
    result.items = itemsFor(symbols, prefix);
    return result;
}

}  // namespace hedit
