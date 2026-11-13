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
#include "core/signature_help.h"
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QVector>
#include <algorithm>

namespace mce {
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

/** @brief 関数・クラス・importの別名を新しく宣言している位置か。
 * @param line カーソルまでの現在行。
 * @return 新しい名前の入力中ならtrue。引数の既定値や基底クラスの式は含めない。
 */
bool isDeclaringName(const QString& line) {
    static const QRegularExpression definition("^\\s*(?:async\\s+)?(?:def|class)\\s+\\w*$",
                                               QRegularExpression::UseUnicodePropertiesOption);
    static const QRegularExpression alias("^\\s*(?:import|from\\s+[\\w.]+\\s+import)\\s+.+\\s+as\\s+\\w*$",
                                          QRegularExpression::UseUnicodePropertiesOption);
    return definition.match(line).hasMatch() || alias.match(line).hasMatch();
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
constexpr int kMaximumInferDepth = 16;

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

/** @brief 単一行のリテラルを実行せず、組み込み型として判定する。
 * @param expression 代入の右辺。 @return 対応する完全修飾型名。式の続きや未対応の形は空。
 * @note 字句解析を共有し、文字列内の括弧やコメントを構造と取り違えない。
 */
QString literalType(QStringView expression) {
    int state = kLexerNormal;
    auto tokens = tokenizeLine(expression, ScriptLanguage::Python, kLexerNormal, &state);
    if (!tokens.isEmpty() && tokens.last().type == TokenType::Comment) tokens.removeLast();
    if (tokens.isEmpty() || state != kLexerNormal) return {};
    const auto& first = tokens.first();
    if (first.type == TokenType::String) {
        // 連続する文字列リテラルもPythonでは1つの値になる。
        QString type;
        for (const auto& token : tokens) {
            if (token.type != TokenType::String) return {};
            const auto word = expression.mid(token.start, token.length);
            const int quote = int(word.indexOf(QLatin1Char('\'')));
            const int doubleQuote = int(word.indexOf(QLatin1Char('"')));
            const int start = quote < 0 ? doubleQuote : doubleQuote < 0 ? quote : qMin(quote, doubleQuote);
            if (start < 0 || word.size() < start + 2 || word.back() != word[start]) return {};
            const QString current = word.left(start).toString().contains('b', Qt::CaseInsensitive)
                ? QStringLiteral("builtins.bytes") : QStringLiteral("builtins.str");
            if (!type.isEmpty() && type != current) return {};
            type = current;
        }
        return type;
    }
    if (first.type != TokenType::Operator || expression[first.start] != '[') return {};
    QString brackets;
    for (int i = 0; i < tokens.size(); ++i) {
        const auto& token = tokens[i];
        if (token.type != TokenType::Operator || token.length != 1) continue;
        const QChar c = expression[token.start];
        if (c == '[' || c == '(' || c == '{') brackets.append(c);
        else if (c == ']' || c == ')' || c == '}') {
            const QChar opening = c == ']' ? '[' : c == ')' ? '(' : '{';
            if (brackets.isEmpty() || brackets.back() != opening) return {};
            brackets.chop(1);
            if (brackets.isEmpty()) return i == tokens.size() - 1 ? QStringLiteral("builtins.list") : QString();
        }
    }
    return {};
}

/** @brief inferredTypeExpressionの本体。
 * @param text 本文。 @param name 変数名。 @param arguments 呼出しなら括弧を含む引数を返す。
 * @return 型名か呼出し名。
 */
QString inferExpression(QStringView text, const QString& name, QString* arguments = nullptr) {
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
                            if (arguments) *arguments = closing < 0 ? QStringLiteral("()") : rest.left(closing + 1);
                            return match.captured(1);
                        }
                        return QString();  // x = A().b など。最後の代入が推論できない形なら、それより前は見ない。
                    }
                    match = assignment.match(line);
                    if (match.hasMatch()) {
                        if (line.mid(match.capturedStart(), match.capturedLength()).trimmed().endsWith("=")
                            && !line.left(match.capturedEnd()).trimmed().endsWith("+=")) {
                            return literalType(QStringView(line).mid(match.capturedEnd()));
                        }
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

/** @brief 括弧・文字列の内側を避け、式を指定した最上位の記号で分ける。
 * @param expression 対象。 @param separator 区切り。 @return 元の文字列を指す部分式。
 */
QVector<QStringView> splitExpression(QStringView expression, QChar separator) {
    QVector<QStringView> result;
    int depth = 0;
    int start = 0;
    const auto tokens = tokenizeLine(expression, ScriptLanguage::Python, kLexerNormal, nullptr);
    for (const auto& token : tokens) {
        if (token.type != TokenType::Operator || token.length != 1) continue;
        const auto c = expression[token.start];
        if (depth == 0 && c == separator) {
            result.append(expression.mid(start, token.start - start).trimmed());
            start = token.start + 1;
        }
        if (c == '(' || c == '[' || c == '{') ++depth;
        else if (c == ')' || c == ']' || c == '}') --depth;
    }
    result.append(expression.mid(start).trimmed());
    return result;
}

/** @brief 末尾の閉じ括弧と対応する開始位置を求める。文字列中の括弧は無視する。
 * @param expression 式。 @return 対応する位置。閉じていない・不整合なら-1。
 */
int finalOpening(QStringView expression) {
    QVector<int> stack;
    const auto tokens = tokenizeLine(expression, ScriptLanguage::Python, kLexerNormal, nullptr);
    for (int i = 0; i < tokens.size(); ++i) {
        const auto& token = tokens[i];
        if (token.type != TokenType::Operator || token.length != 1) continue;
        const auto c = expression[token.start];
        if (c == '(' || c == '[' || c == '{') stack.append(token.start);
        else if (c == ')' || c == ']' || c == '}') {
            if (stack.isEmpty()) return -1;
            const int open = stack.takeLast();
            if (expression[open] != (c == ')' ? '(' : c == ']' ? '[' : '{')) return -1;
            if (i == tokens.size() - 1 && stack.isEmpty()) return open;
        }
    }
    return -1;
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

/** @brief ``a().b().prefix`` の受け手を、呼出しと属性名の列にする。
 * @param line カーソルまでの行。 @param token 末尾の名前。 @return 呼出しを含む受け手。該当しなければ空。
 */
QStringList callReceiver(QStringView line, const QString& token) {
    const qsizetype dot = line.size() - token.size() - 1;
    if (dot < 1 || line[dot] != '.' || !line.left(dot).trimmed().endsWith(QLatin1Char(')'))) return {};

    const auto words = tokenizeLine(line.left(dot), ScriptLanguage::Python, kLexerNormal, nullptr);
    const auto symbolAt = [&](int index, QChar c) {
        return index >= 0 && words[index].type == TokenType::Operator && words[index].length == 1
               && line[words[index].start] == c;
    };
    QStringList parts;
    int index = int(words.size()) - 1;
    int calls = 0;
    while (index >= 0) {
        const bool call = symbolAt(index, ')');
        QStringView arguments;
        if (call) {
            if (++calls > kMaximumInferDepth) return {};
            const auto end = words[index].start + words[index].length;
            int depth = 1;
            for (--index; index >= 0 && depth; --index) {
                if (symbolAt(index, ')')) ++depth;
                else if (symbolAt(index, '(')) --depth;
            }
            if (depth) return {};
            const auto start = words[index + 1].start;
            arguments = line.mid(start, end - start);
        }
        if (index < 0 || words[index].type != TokenType::Name) return {};
        const auto& word = words[index--];
        QString name = line.mid(word.start, word.length).toString();
        if (!isIdentifier(name) || isKeyword(QStringView(name), ScriptLanguage::Python)) return {};
        if (call) name += arguments;
        parts.prepend(name);
        if (!symbolAt(index, '.')) break;
        --index;
    }
    if (calls == 0 || parts.isEmpty()) return {};
    if (!token.isEmpty()) parts.append(token.split('.'));
    else parts.append(QString());
    return parts;
}

/** @brief 補完直前の受け手を後ろから読む。添字・呼出し・リテラルを保持する。
 * @param line カーソル行。 @param prefix 入力中のメンバー名。 @return 受け手の式。該当しなければ空。
 */
QString memberReceiver(QStringView line, const QString& prefix) {
    const int dot = int(line.size()) - prefix.size() - 1;
    if (dot <= 0 || line[dot] != '.') return {};
    const auto before = line.left(dot);
    const auto tokens = tokenizeLine(before, ScriptLanguage::Python, kLexerNormal, nullptr);
    int index = int(tokens.size()) - 1;
    int start = dot;
    while (index >= 0) {
        const auto& word = tokens[index];
        const auto spelling = before.mid(word.start, word.length);
        if (word.type == TokenType::Operator && (spelling == QLatin1String(")") || spelling == QLatin1String("]") || spelling == QLatin1String("}"))) {
            const int opening = finalOpening(before.left(word.start + word.length));
            if (opening < 0) return {};
            start = opening;
            while (index >= 0 && tokens[index].start >= opening) --index;
            if (index >= 0 && before[opening] != '{') {
                const auto& previous = tokens[index];
                const auto c = before[previous.start];
                if (previous.type == TokenType::Name && !isKeyword(before.mid(previous.start, previous.length), ScriptLanguage::Python)) continue;
                if (c == ')' || c == ']') continue;
            }
        } else if (word.type == TokenType::Name || word.type == TokenType::String || word.type == TokenType::Number) {
            if (word.type == TokenType::Name && isKeyword(spelling, ScriptLanguage::Python)) return {};
            start = word.start;
            --index;
        } else return {};
        if (index >= 0 && before.mid(tokens[index].start, tokens[index].length) == QLatin1String(".")) { --index; continue; }
        return before.mid(start).trimmed().toString();
    }
    return before.mid(start).trimmed().toString();
}

/** @brief 戻り値の注釈から候補の型名を取り出す。
 * @param annotation 注釈。 @param depth 入れ子の深さ。 @return Noneを除いて型が1種類なら、その名前。
 */
QString returnTypeName(QString annotation, int depth = 0) {
    if (depth >= kMaximumInferDepth) return {};
    annotation = annotation.trimmed();
    if (annotation.size() >= 2 && (annotation.front() == '\'' || annotation.front() == '"')
        && annotation.back() == annotation.front()) annotation = annotation.mid(1, annotation.size() - 2).trimmed();

    static const QRegularExpression dotted("^[A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*$");
    if (dotted.match(annotation).hasMatch()) return annotation == "None" ? QString() : annotation;
    const int bracket = annotation.indexOf('[');
    const QString container = bracket < 0 ? QString() : annotation.left(bracket).trimmed().section('.', -1);
    if (container == "Optional" && annotation.endsWith(']')) {
        return returnTypeName(annotation.mid(bracket + 1, annotation.size() - bracket - 2), depth + 1);
    }
    if ((container == "list" || container == "List") && annotation.endsWith(']')) {
        // リストそのものには要素の属性を出さない。単一要素型のリストを標準listとして補完する。
        const auto element = annotation.mid(bracket + 1, annotation.size() - bracket - 2).trimmed();
        if (element != "None" && dotted.match(element).hasMatch()) return QStringLiteral("builtins.list");
        return {};
    }
    const bool unionType = container == "Union" && annotation.endsWith(']');
    if (unionType) annotation = annotation.mid(bracket + 1, annotation.size() - bracket - 2);
    else if (!annotation.contains('|')) return {};
    const auto alternatives = annotation.split(unionType ? ',' : '|');
    QString result;
    for (const auto& alternative : alternatives) {
        if (alternative.trimmed() == "None") continue;
        const auto name = returnTypeName(alternative, depth + 1);
        if (name.isEmpty() || (!result.isEmpty() && name != result)) return {};
        result = name;
    }
    return result;
}

/** @brief 既知の必須文字列Literalと一致する呼出しに限って戻り値の注釈を選ぶ。
 * @param function 呼出し先。 @param arguments 外側の括弧を除いた引数。 @return 選んだ注釈。
 */
QString callReturnAnnotation(const Symbol& function, QStringView arguments) {
    if (function.literalReturns.isEmpty() || arguments.isEmpty()) return function.returnAnnotation;
    const auto tokens = tokenizeLine(arguments, ScriptLanguage::Python, kLexerNormal, nullptr);
    const auto word = [&](int i) { return arguments.mid(tokens[i].start, tokens[i].length); };
    QString annotation;
    int begin = 0;
    int depth = 0;
    for (int i = 0; i <= tokens.size(); ++i) {
        if (i == tokens.size() || (depth == 0 && tokens[i].type == TokenType::Operator && word(i) == QLatin1String(","))) {
            if (i == begin + 3 && tokens[begin].type == TokenType::Name && word(begin + 1) == QLatin1String("=")
                && tokens[begin + 2].type == TokenType::String) {
                const auto literal = word(begin + 2);
                if (literal.size() >= 2 && (literal.front() == '\'' || literal.front() == '"')
                    && literal.back() == literal.front() && !literal.contains(QLatin1Char('\\'))) {
                    const auto key = word(begin).toString() + '\n' + literal.mid(1, literal.size() - 2).toString();
                    const auto found = function.literalReturns.constFind(key);
                    if (found != function.literalReturns.constEnd()) {
                        if (found->isEmpty() || (!annotation.isEmpty() && annotation != *found)) return function.returnAnnotation;
                        annotation = *found;
                    }
                }
            }
            begin = i + 1;
        } else if (tokens[i].type == TokenType::Operator && tokens[i].length == 1) {
            const auto bracket = word(i).front();
            if (bracket == '(' || bracket == '[' || bracket == '{') ++depth;
            else if (bracket == ')' || bracket == ']' || bracket == '}') --depth;
        }
    }
    return annotation.isEmpty() ? function.returnAnnotation : annotation;
}

/** @brief typingのSelfを普通の同名クラスと区別する。
 * @param name 注釈の型名。 @param home 定義元の名前表。 @return 標準のSelfを指すか。
 */
bool isSelfAnnotation(const QString& name, const SymbolTable& home) {
    const auto isTyping = [](const QString& module) { return module == "typing" || module == "typing_extensions"; };
    const int dot = name.indexOf('.');
    if (dot < 0) {
        const auto item = home.constFind(name);
        return item != home.constEnd() && item->type == SymbolType::Import
            && item->fromName == "Self" && isTyping(item->fromModule);
    }
    if (name.mid(dot + 1) != "Self") return false;
    const auto module = name.left(dot);
    const auto item = home.constFind(module);
    return item == home.constEnd() ? isTyping(module) : item->type == SymbolType::Module && isTyping(item->target);
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

const CompletionEngine::CachedLocals* CompletionEngine::findLocals(QStringView text, int cursorIndent) {
    for (CachedLocals& entry : locals_) {
        if (entry.cursorIndent == cursorIndent && entry.text.size() == text.size() && QStringView(entry.text) == text) {
            entry.used = ++localsClock_;
            return &entry;
        }
    }
    return nullptr;
}

const CompletionEngine::CachedLocals& CompletionEngine::declarationsFor(QStringView text, const QString* whole, int cursorIndent) {
    if (const CachedLocals* cached = findLocals(text, cursorIndent)) {
        return *cached;
    }
    CachedLocals entry;
    entry.text = whole ? *whole : text.toString();
    const DeclarationResult result = cursorIndent < 0 ? extractPythonDeclarations(entry.text)
                                                     : extractPythonCompletionDeclarations(entry.text, cursorIndent);
    entry.cursorIndent = cursorIndent;
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
    const QString moduleStubKey = keys.last() + ".pyi";
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
            const auto contents = folderEntries(base);
            if (contents.value("__init__.py").file) location.sourceFile = QDir(base).filePath("__init__.py");
            location.file = contents.value("__init__.pyi").file ? QDir(base).filePath("__init__.pyi") : location.sourceFile;
            if (!location.file.isEmpty()) {
                location.moduleName = name + ".__init__";
            }
        } else if (entries.value(moduleFileKey).file || entries.value(moduleStubKey).file) {
            if (entries.value(moduleFileKey).file) location.sourceFile = base + ".py";
            location.file = entries.value(moduleStubKey).file ? base + ".pyi" : location.sourceFile;
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
            const QFileInfo source(loaded.file);
            const QString fileName = source.fileName();
            const bool hasStub = folderEntries(source.absolutePath()).value(folderKey(fileName + "i")).file;
            const QString file = hasStub ? loaded.file + "i" : loaded.file;
            const QString moduleName = fileName == "__init__.py" ? name + ".__init__" : name;
            const SymbolTable declared = fileDeclarations(file, moduleName);
            // 公開名(maya_code_editor.bridgeは変わっていなければ同じ表を返す)とファイルの宣言が前回と同じ表なら、重ねた結果を使い回す。
            // maya.cmdsのような数千件の表を、問い合わせのたびにコピーして重ねないため。
            const auto merged = merged_.constFind(name);
            if (merged != merged_.constEnd() && merged->members.isSharedWith(loaded.members)
                && merged->declared.isSharedWith(declared) && merged->file == file) {
                result = merged->result;
            } else {
                for (auto it = declared.begin(); it != declared.end(); ++it) {
                    const auto existing = result.find(it.key());
                    if (!hasStub && existing != result.end() && existing->members && it.value().members) {
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
                merged_.insert(name, {loaded.members, file, declared, result});
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
                const bool stub = entry.name.endsWith(".pyi");
                const bool python = stub || entry.name.endsWith(".py");
                const QString stem = python ? entry.name.left(entry.name.size() - (stub ? 4 : 3)) : entry.name;
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
        const auto& file = location.sourceFile.isEmpty() ? location.file : location.sourceFile;
        fileDeclarations(file, location.moduleName);
        const auto cached = files_.constFind(file);
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

bool CompletionEngine::sameType(const Located& left, const Located& right, int depth) {
    if (&left == &right) return left.found;
    if (depth >= kMaximumInferDepth || !left.found || !right.found || left.module != right.module
        || left.path != right.path || left.item.type != right.item.type || left.item.signature != right.item.signature
        || bool(left.element) != bool(right.element) || bool(left.iterationElement) != bool(right.iterationElement)
        || left.positions.size() != right.positions.size()) return false;
    if (left.element && !sameType(*left.element, *right.element, depth + 1)) return false;
    if (left.iterationElement && !sameType(*left.iterationElement, *right.iterationElement, depth + 1)) return false;
    for (int i = 0; i < left.positions.size(); ++i) {
        if (bool(left.positions[i]) != bool(right.positions[i])) return false;
        if (left.positions[i] && !sameType(*left.positions[i], *right.positions[i], depth + 1)) return false;
    }
    return true;
}

CompletionEngine::Located CompletionEngine::iterationType(Request& request, const Located& source,
                                                          const SymbolTable& scope, int depth) {
    if (source.iterationElement) return *source.iterationElement;
    if (source.module == "builtins" && source.path == QStringList{"str"}) return source;
    Located unknown;
    unknown.found = false;
    if (!source.found || depth >= kMaximumInferDepth) return unknown;
    const auto members = membersOf(request, source, scope, depth);
    const auto method = members.constFind("__iter__");
    if (method == members.constEnd()) return unknown;
    const QString annotation = method->returnAnnotation.trimmed();
    const int opening = finalOpening(annotation);
    if (opening <= 0 || annotation[opening] != '[') return unknown;
    const auto home = method->returnModule.isEmpty() ? scope : moduleMembers(request, method->returnModule);
    const QString name = annotation.left(opening).trimmed();
    QString canonical = name;
    const auto imported = home.constFind(name.section('.', 0, 0));
    if (imported != home.constEnd()) {
        if (imported->type == SymbolType::Import) canonical = imported->fromModule + "." + imported->fromName;
        else if (imported->type == SymbolType::Module && name.contains('.')) canonical = imported->target + "." + name.section('.', 1);
    }
    if (canonical != "typing.Iterator" && canonical != "collections.abc.Iterator"
        && canonical != "typing.Generator" && canonical != "collections.abc.Generator") return unknown;
    const auto arguments = splitExpression(QStringView(annotation).mid(opening + 1, annotation.size() - opening - 2), ',');
    return annotationType(request, home, arguments.first().toString(), depth + 1);
}

CompletionEngine::Located CompletionEngine::annotationType(Request& request, const SymbolTable& scope,
                                                           QString annotation, int depth) {
    Located unknown;
    unknown.found = false;
    if (depth >= kMaximumInferDepth || ++request.inferenceSteps > 256) return unknown;
    annotation = annotation.trimmed();
    if (annotation.size() >= 2 && (annotation.front() == '\'' || annotation.front() == '"')
        && annotation.back() == annotation.front()) annotation = annotation.mid(1, annotation.size() - 2).trimmed();
    const QStringView view(annotation);
    auto unionParts = splitExpression(view, '|');
    const int bracket = finalOpening(view);
    QString name = bracket > 0 && view[bracket] == '[' ? view.left(bracket).trimmed().toString() : annotation;
    QString canonical = name;
    const auto imported = scope.constFind(name.section('.', 0, 0));
    if (imported != scope.constEnd()) {
        if (imported->type == SymbolType::Import) canonical = imported->fromModule + "." + imported->fromName;
        else if (imported->type == SymbolType::Module && name.contains('.')) canonical = imported->target + "." + name.section('.', 1);
    }
    const bool typing = canonical.startsWith("typing.") || canonical.startsWith("typing_extensions.");
    const QString shortName = canonical.section('.', -1);
    const QStringView inside = bracket > 0 ? view.mid(bracket + 1, view.size() - bracket - 2) : QStringView();
    // Annotatedのメタデータは評価せず、先頭の型だけを使う。
    if (typing && shortName == "Annotated") {
        const auto parts = splitExpression(inside, ',');
        return parts.isEmpty() ? unknown : annotationType(request, scope, parts.first().toString(), depth + 1);
    }
    // 同型のLiteralだけを扱う。混在値を先頭の型へ決めつけない。
    if (typing && shortName == "Literal") {
        const auto parts = splitExpression(inside, ',');
        if (parts.size() > 32) return unknown;
        Located result = unknown;
        for (const auto& part : parts) {
            const auto type = valueType(request, scope, QStringView(), part, depth + 1);
            if (!type.found || (result.found && !sameType(type, result))) return unknown;
            result = type;
        }
        return result;
    }
    if (typing && shortName == "Optional") return annotationType(request, scope, inside.toString(), depth + 1);
    if (typing && shortName == "Union") unionParts = splitExpression(inside, ',');
    if (unionParts.size() > 1) {
        Located result = unknown;
        for (const auto& part : unionParts) {
            if (part == QLatin1String("None")) continue;
            const auto type = annotationType(request, scope, part.toString(), depth + 1);
            if (!type.found || (result.found && !sameType(type, result))) return unknown;
            result = type;
        }
        return result;
    }
    QString container;
    if ((typing && (shortName == "List" || shortName == "Dict" || shortName == "Set" || shortName == "Tuple"))
        || ((name == "list" || name == "dict" || name == "set" || name == "tuple") && imported == scope.constEnd())
        || (canonical.startsWith("builtins.") && (shortName == "list" || shortName == "dict" || shortName == "set" || shortName == "tuple"))) {
        container = shortName.toLower();
        name = "builtins." + container;
    }
    auto result = walk(request, scope, QStringView(), name.split('.'), depth + 1);
    if (!result.found || result.item.type != SymbolType::Class) return unknown;
    if (!container.isEmpty() && bracket > 0) {
        const auto arguments = splitExpression(inside, ',');
        const auto element = [&](int index) -> std::shared_ptr<Located> {
            if (index >= arguments.size()) return {};
            auto type = annotationType(request, scope, arguments[index].toString(), depth + 1);
            return type.found ? std::make_shared<Located>(type) : nullptr;
        };
        result.element = element(container == "dict" ? 1 : 0);
        result.iterationElement = container == "dict" ? element(0) : result.element;
        if (container == "tuple" && !(arguments.size() == 2 && arguments[1] == QLatin1String("...")))
            for (int i = 0; i < arguments.size(); ++i) result.positions.append(element(i));
        // 異種タプルを単一要素型に縮めない。tuple[T, ...]は同型。
        if (container == "tuple" && arguments.size() > 1 && arguments[1] != QLatin1String("...")) {
            for (int i = 1; i < arguments.size(); ++i) {
                const auto next = element(i);
                if (!next || !result.element || !sameType(*next, *result.element)) {
                    result.element.reset(); result.iterationElement.reset(); break;
                }
            }
        }
    }
    return result;
}

CompletionEngine::Located CompletionEngine::valueType(Request& request, const SymbolTable& scope, QStringView text,
                                                      QStringView expression, int depth) {
    Located unknown;
    unknown.found = false;
    if (depth >= kMaximumInferDepth || ++request.inferenceSteps > 256) return unknown;
    expression = expression.trimmed();
    if (expression.isEmpty()) return unknown;
    const auto builtin = [&](const QString& name) {
        Located result;
        result.module = "builtins";
        result.path = QStringList{name};
        const auto members = moduleMembers(request, "builtins");
        const auto found = members.constFind(name);
        result.found = found != members.constEnd() && found->type == SymbolType::Class;
        if (result.found) result.item = found.value();
        return result;
    };
    const QString primitive = literalType(expression);
    if (primitive == "builtins.str" || primitive == "builtins.bytes") return builtin(primitive.mid(9));
    if (expression == QLatin1String("True") || expression == QLatin1String("False")) return builtin("bool");
    static const QRegularExpression integer("^[+-]?\\s*(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|[0-9][0-9_]*)$");
    static const QRegularExpression real("^[+-]?\\s*(?:[0-9][0-9_]*(?:\\.[0-9_]*)?|\\.[0-9][0-9_]*)(?:[eE][+-]?[0-9][0-9_]*)?[jJ]?$");
    const QString owned = expression.toString();
    const auto tupleItems = splitExpression(expression, ',');
    if (tupleItems.size() > 1) {
        const QString wrapped = "(" + owned + ")";
        return valueType(request, scope, text, wrapped, depth + 1);
    }
    if (integer.match(owned).hasMatch()) return builtin("int");
    if (real.match(owned).hasMatch()) return builtin(owned.endsWith('j', Qt::CaseInsensitive) ? "complex" : "float");
    const int open = finalOpening(expression);
    if (open > 0 && expression.back() == ')') {
        const auto callable = expression.left(open).trimmed();
        const QString function = callable.toString();
        if ((function == "sorted" || function == "reversed" || function == "iter" || function == "zip")
            && !scope.contains(function)) {
            const auto arguments = splitExpression(expression.mid(open + 1, expression.size() - open - 2), ',');
            if (arguments.isEmpty() || arguments.first().isEmpty() || arguments.size() > 32) return unknown;
            auto element = iterationType(request, valueType(request, scope, text, arguments.first(), depth + 1), scope, depth + 1);
            if (function == "zip") {
                element = builtin("tuple");
                for (const auto& argument : arguments) {
                    if (argument.startsWith(QLatin1String("strict="))) continue;
                    const auto item = iterationType(request, valueType(request, scope, text, argument, depth + 1), scope, depth + 1);
                    element.positions.append(item.found ? std::make_shared<Located>(item) : nullptr);
                }
            }
            auto result = builtin(function == "sorted" ? "list" : function == "zip" ? "zip" : "reversed");
            if (element.found) {
                result.iterationElement = std::make_shared<Located>(element);
                if (function == "sorted") result.element = result.iterationElement;
            }
            return result;
        }
        // nextは保持している反復要素の型だけを参照し、入力を実行しない。
        if (function == "next" && !scope.contains(function)) {
            const auto arguments = splitExpression(expression.mid(open + 1, expression.size() - open - 2), ',');
            if (arguments.isEmpty() || arguments.size() > 2) return unknown;
            const auto source = valueType(request, scope, text, arguments.first(), depth + 1);
            // list等のiterableにnextを直接呼ぶ誤りを補完で隠さない。
            const bool iterator = source.module == "builtins"
                && (source.path == QStringList{"reversed"} || source.path == QStringList{"zip"}
                    || source.path == QStringList{"enumerate"});
            if (!iterator) return unknown;
            const auto element = iterationType(request, source, scope, depth + 1);
            if (arguments.size() == 2 && arguments[1].trimmed() != QLatin1String("None")) {
                const auto fallback = valueType(request, scope, text, arguments[1], depth + 1);
                if (!fallback.found || !sameType(element, fallback)) return unknown;
            }
            return element;
        }
        if (callable == QLatin1String("enumerate") && !scope.contains("enumerate")) {
            const auto arguments = splitExpression(expression.mid(open + 1, expression.size() - open - 2), ',');
            const auto source = valueType(request, scope, text, arguments.first(), depth + 1);
            auto pair = builtin("tuple");
            const auto element = iterationType(request, source, scope, depth + 1);
            pair.positions = {std::make_shared<Located>(builtin("int")), element.found ? std::make_shared<Located>(element) : nullptr};
            auto result = builtin("enumerate");
            result.iterationElement = std::make_shared<Located>(pair);
            return result;
        }
        auto callee = valueType(request, scope, text, callable, depth + 1);
        const auto parts = splitExpression(callable, '.');
        Located receiver = unknown;
        if (parts.size() > 1) receiver = valueType(request, scope, text, callable.left(parts.last().data() - callable.data() - 1), depth + 1);
        return callee.found ? callResult(request, callee, scope, depth,
            expression.mid(open + 1, expression.size() - open - 2), receiver.found ? &receiver : nullptr) : unknown;
    }
    if (open > 0 && expression.back() == ']') {
        const auto container = valueType(request, scope, text, expression.left(open), depth + 1);
        const auto index = expression.mid(open + 1, expression.size() - open - 2);
        if (splitExpression(index, ':').size() > 1) {
            return container.path == QStringList{"list"} || container.path == QStringList{"tuple"}
                || container.path == QStringList{"str"} || container.path == QStringList{"bytes"} ? container : unknown;
        }
        if (container.module == "builtins" && container.path == QStringList{"str"}) return container;
        bool valid = false;
        int position = index.toString().toInt(&valid);
        if (valid && !container.positions.isEmpty()) {
            if (position < 0) position += container.positions.size();
            return position >= 0 && position < container.positions.size() && container.positions[position]
                ? *container.positions[position] : unknown;
        }
        if (container.element) return *container.element;
        if (container.found && container.module != "builtins") {
            const auto members = membersOf(request, container, scope, depth);
            const auto item = members.constFind("__getitem__");
            if (item != members.constEnd()) {
                auto method = container;
                method.item = item.value();
                return callResult(request, method, scope, depth + 1, index, &container);
            }
        }
        return unknown;
    }
    if (open == 0) {
        const auto inside = expression.mid(1, expression.size() - 2);
        const auto values = splitExpression(inside, ',');
        if (expression.front() == '(' && values.size() == 1 && !inside.trimmed().isEmpty())
            return valueType(request, scope, text, inside, depth + 1);
        const bool dictionary = expression.front() == '{' && (inside.isEmpty() || splitExpression(values.first(), ':').size() == 2);
        const auto name = expression.front() == '[' ? "list" : expression.front() == '(' ? "tuple" : dictionary ? "dict" : "set";
        auto result = builtin(name);
        if (values.size() > 32) return result;  // 入力1回あたりの推論量を制限する。
        bool first = true;
        for (const auto& value : values) {
            if (value.isEmpty()) continue;
            const auto pair = splitExpression(value, ':');
            const auto member = valueType(request, scope, text, dictionary && pair.size() == 2 ? pair[1] : value, depth + 1);
            const auto key = dictionary && pair.size() == 2 ? valueType(request, scope, text, pair[0], depth + 1) : member;
            if (expression.front() == '(') result.positions.append(member.found ? std::make_shared<Located>(member) : nullptr);
            const auto merge = [&](std::shared_ptr<Located>& saved, const Located& incoming) {
                if (first) saved = incoming.found ? std::make_shared<Located>(incoming) : nullptr;
                else if (!incoming.found || !saved || !sameType(incoming, *saved)) saved.reset();
            };
            merge(result.element, member);
            merge(result.iterationElement, key);
            first = false;
        }
        return result;
    }
    const auto parts = splitExpression(expression, '.');
    if (parts.size() > 1 && isIdentifier(parts.last().toString())) {
        const auto prefix = expression.left(parts.last().data() - expression.data() - 1).trimmed();
        auto owner = valueType(request, scope, text, prefix, depth + 1);
        if (!owner.found) return unknown;
        const auto members = membersOf(request, owner, scope, depth);
        const QString name = parts.last().toString();
        const auto found = members.constFind(name);
        if (found == members.constEnd()) return unknown;
        if (owner.item.type == SymbolType::Class && found->type == SymbolType::Value
            && (!found->valueAnnotation.isEmpty() || !found->valueExpression.isEmpty())) {
            const QString home = found->returnModule.isEmpty() ? owner.module : found->returnModule;
            SymbolTable context = home.isEmpty() ? scope : moduleMembers(request, home);
            if (found->valueScope) {
                for (auto it = found->valueScope->cbegin(); it != found->valueScope->cend(); ++it) context.insert(it.key(), it.value());
            }
            if (!found->receiverName.isEmpty()) context.insert(found->receiverName, owner.item);
            if (!found->valueAnnotation.isEmpty()) return annotationType(request, context, found->valueAnnotation, depth + 1);
            return valueType(request, context, QStringView(), found->valueExpression, depth + 1);
        }
        if (owner.item.type == SymbolType::Module) { owner.module = owner.item.target; owner.path.clear(); }
        owner.path.append(name);
        owner.item = found.value();
        owner.element.reset(); owner.iterationElement.reset();
        followImports(request, &owner.item, &owner.module, &owner.path);
        return owner;
    }
    if (isIdentifier(owned)) {
        auto result = resolveName(request, scope, text, owned, depth, false);
        followImports(request, &result.item, &result.module, &result.path);
        return result;
    }
    return unknown;
}

CompletionEngine::Located CompletionEngine::resolveName(Request& request, const SymbolTable& scope, QStringView text,
                                                       const QString& name, int depth, bool allowImplicitModule) {
    Located located;
    const auto local = scope.find(name);
    if (local != scope.end() && local.value().type != SymbolType::Value) {
        located.item = local.value();
        located.path = QStringList{name};  // 本文の中での位置(定義へ移動で使う。moduleが空なら本文の中)。
        return located;
    }
    if (local != scope.end() && local->valueOffset != -1) {
        Located type;
        type.found = false;
        if (!local->valueAnnotation.isEmpty()) {
            type = annotationType(request, scope, local->valueAnnotation, depth + 1);
        } else if (depth < kMaximumInferDepth && !local->valueExpression.isEmpty()) {
            // 代入時点のスコープを再利用する。後で元変数を再代入してもコピー先の型は変えない。
            // 未対応の二項算術式では、数千行の代入前スコープを読み直さない。
            // 分割は引用符・括弧を尊重するため、文字列や呼出し引数内の演算は対象外。
            const QStringView expression(local->valueExpression);
            for (const QChar op : {QChar('+'), QChar('-'), QChar('*'), QChar('/'), QChar('%')}) {
                const auto operands = splitExpression(expression, op);
                if (operands.size() > 1 && !operands.first().isEmpty()) {
                    located.item = local.value();
                    located.path = QStringList{name};
                    return located;
                }
            }
            const int offset = local->valueOffset;
            if (offset >= 0 && offset <= text.size()) {
                const auto before = text.left(offset);
                const int lineStart = int(before.lastIndexOf(QLatin1Char('\n'))) + 1;
                int indent = 0;
                for (const auto c : before.mid(lineStart)) {
                    if (c == ' ') ++indent;
                    else if (c == '\t') indent = (indent / 8 + 1) * 8;
                    else break;
                }
                const auto previous = declarationsFor(before, nullptr, indent).symbols;
                type = valueType(request, previous, before, local->valueExpression, depth + 1);
                if (local->iterated) {
                    // 返された値を先に保持し、shared_ptrの所有者との自己参照代入を避ける。
                    const Located element = iterationType(request, type, previous, depth + 1);
                    type = element;
                }
                if (local->unpackIndex >= 0) {
                    const int index = local->unpackIndex;
                    if (type.positions.size() == local->unpackCount && type.positions[index]) {
                        const Located element = *type.positions[index];
                        type = element;
                    }
                    else type.found = false;
                }
            }
        }
        if (type.found) return type;
        located.item = local.value();
        located.path = QStringList{name};
        return located;  // 不明な再代入から過去の別スコープへ逆戻りしない。
    }
    // 変数なら、代入・型ヒントからクラスを推論する(インスタンスはクラスの中身で補完する)。本文が空なら推論しない。
    if (local != scope.end() && depth < kMaximumInferDepth && !text.isEmpty()) {
        QString arguments;
        const QString expression = inferExpression(text, name, &arguments);
        if (!expression.isEmpty() && expression != name) {
            if (expression.startsWith("builtins.") && arguments.isEmpty()) {
                // リテラルはimport不要。暗黙のモジュール補完が無効でも実型を参照する。
                const QString typeName = expression.mid(9);
                const SymbolTable members = moduleMembers(request, "builtins");
                const auto type = members.constFind(typeName);
                if (type != members.constEnd() && type->type == SymbolType::Class) {
                    located.item = type.value();
                    located.module = "builtins";
                    located.path = QStringList{typeName};
                    return located;
                }
            }
            QStringList parts = expression.split('.');
            parts.last() += arguments;
            const Located type = walk(request, scope, text, parts, depth + 1, allowImplicitModule);
            if (type.found && type.item.type == SymbolType::Class) {
                return type;
            }
        }
    }
    if (local != scope.end()) {
        located.item = local.value();
        located.path = QStringList{name};
    } else if (builtins_.contains(name)) {
        // list()/str()と型注釈でも、名前の分類だけでなく実際のクラスを使う。
        const SymbolTable members = moduleMembers(request, "builtins");
        located.item = members.value(name, Symbol::category(SymbolType::Builtin));
        located.module = "builtins";
        located.path = QStringList{name};
    } else if (allowImplicitModule) {
        located.item = Symbol::module(name);
    } else {
        located.found = false;
    }
    return located;
}

CompletionEngine::Located CompletionEngine::builtinMethodResult(Request& request, const Located& receiver,
                                                               const QString& method, const SymbolTable& scope, int depth) {
    Located unknown;
    unknown.found = false;
    if (receiver.module != "builtins" || receiver.path.size() != 1 || depth >= kMaximumInferDepth) return unknown;
    const QString& type = receiver.path.first();
    // 実型と実在メンバーを確認した後で適用する。任意の同名メソッド・派生型へ契約を押し付けない。
    static const QSet<QString> textResults = {"capitalize", "casefold", "center", "expandtabs", "join", "ljust", "lower",
        "lstrip", "removeprefix", "removesuffix", "replace", "rjust", "rstrip", "strip", "swapcase", "title", "translate", "upper", "zfill"};
    static const QSet<QString> textIntegers = {"count", "find", "index", "rfind", "rindex"};
    static const QSet<QString> textBooleans = {"endswith", "startswith", "isalnum", "isalpha", "isascii", "isdecimal",
        "isdigit", "isidentifier", "islower", "isnumeric", "isprintable", "isspace", "istitle", "isupper"};
    QString annotation;
    if (type == "str" || type == "bytes") {
        if (textResults.contains(method) || (type == "str" && (method == "format" || method == "format_map"))) annotation = type;
        else if (textIntegers.contains(method)) annotation = "int";
        else if (textBooleans.contains(method)) annotation = "bool";
        else if (method == "split" || method == "rsplit" || method == "splitlines") annotation = "list[" + type + "]";
        else if (method == "partition" || method == "rpartition") annotation = "tuple[" + type + ", " + type + ", " + type + "]";
        else if (type == "str" && method == "encode") annotation = "bytes";
        else if (type == "bytes" && (method == "decode" || method == "hex")) annotation = "str";
    } else if (type == "list" || type == "tuple" || type == "dict" || type == "set") {
        if (method == "copy") return receiver;
        if (type == "dict" && (method == "keys" || method == "values" || method == "items" || method == "popitem")) {
            auto pair = annotationType(request, SymbolTable(), "tuple", depth + 1);
            pair.positions = {receiver.iterationElement, receiver.element};
            if (method == "popitem") return pair;
            // dictのビューはlistではない。添字やappendを誤って提示せず、反復する要素だけを保持する。
            Located view;
            view.item.type = SymbolType::Class;
            view.module = "builtins";
            view.path = QStringList{"dict_" + method};
            view.iterationElement = method == "keys" ? receiver.iterationElement : method == "values" ? receiver.element
                : std::make_shared<Located>(pair);
            return view;
        }
        if (type == "set" && (method == "difference" || method == "intersection")) return receiver;
        if (type == "set" && (method == "union" || method == "symmetric_difference")) {
            auto result = receiver;
            result.element.reset(); result.iterationElement.reset();
            return result;  // 引数から別型が加わり得るため、要素型は決めつけない。
        }
        if (method == "count" || method == "index") annotation = "int";
        else if (method == "pop" || (type == "dict" && method == "get")) {
            return receiver.element ? *receiver.element : unknown;
        } else if (type == "set" && (method == "issubset" || method == "issuperset" || method == "isdisjoint")) annotation = "bool";
        // 更新操作(append/sort/update等)のNoneを元オブジェクトに誤変換しない。
    } else if (type == "int" || type == "float") {
        if (method == "bit_length" || method == "bit_count") annotation = "int";
        else if (method == "is_integer") annotation = "bool";
        else if (method == "as_integer_ratio") annotation = "tuple[int, int]";
        else if (method == "hex") annotation = "str";
        else if (method == "to_bytes") annotation = "bytes";
    }
    // builtinsの契約はローカルでstr/list等を隠していても組み込み型を指す。
    return annotation.isEmpty() ? unknown : annotationType(request, SymbolTable(), annotation, depth + 1);
}

CompletionEngine::Located CompletionEngine::callResult(Request& request, Located callee, const SymbolTable& scope, int depth,
                                                       QStringView arguments, const Located* receiver) {
    if (callee.item.type == SymbolType::Class) return callee;
    if (receiver && callee.module == "builtins" && !callee.path.isEmpty()) {
        const auto type = builtinMethodResult(request, *receiver, callee.path.last(), scope, depth);
        if (type.found) return type;
    }
    if (depth <= kMaximumInferDepth && callee.item.type == SymbolType::Function) {
        if (callee.item.returnAnnotation.isEmpty() && !callee.item.returnExpression.isEmpty()) {
            const auto home = callee.item.returnModule.isEmpty() ? scope : moduleMembers(request, callee.item.returnModule);
            return valueType(request, home, QStringView(), callee.item.returnExpression, depth + 1);
        }
        const QString name = returnTypeName(callReturnAnnotation(callee.item, arguments));
        if (!callee.item.returnAnnotation.isEmpty()) {
            const QString& module = callee.item.returnModule;
            const SymbolTable home = module.isEmpty() ? scope : moduleMembers(request, module);
            if (receiver && callee.item.binding != Symbol::StaticMethod && isSelfAnnotation(name, home)) return *receiver;
            Located type = annotationType(request, home, callReturnAnnotation(callee.item, arguments), depth + 1);
            if (!type.found && name.contains('.')) {
                // 完全修飾名でも、読み込み済みのパッケージのvars()に子モジュールがまだ無い場合がある。
                type = walk(request, home, QStringView(), {name.section('.', 0, -2), name.section('.', -1)}, depth + 1);
            }
            if (type.found && type.item.type == SymbolType::Class) {
                if (type.module.isEmpty()) type.module = module;
                return type;
            }
        }
    }
    callee.found = false;
    return callee;
}

CompletionEngine::Located CompletionEngine::walk(Request& request, const SymbolTable& scope, QStringView text,
                                                const QStringList& parts, int depth, bool allowImplicitModule) {
    const int firstCall = parts.first().indexOf('(');
    const QString first = firstCall >= 0 ? parts.first().left(firstCall) : parts.first();
    Located located = resolveName(request, scope, text, first, depth, allowImplicitModule);
    if (!located.found) {
        return located;
    }
    followImports(request, &located.item, &located.module, &located.path);
    if (firstCall >= 0) located = callResult(request, located, scope, depth, QStringView(parts.first()).mid(firstCall + 1, parts.first().size() - firstCall - 2));
    for (int i = 1; i < parts.size(); ++i) {
        if (!located.found) break;
        const int call = parts[i].indexOf('(');
        const QString name = call >= 0 ? parts[i].left(call) : parts[i];
        const SymbolTable members = membersOf(request, located, scope, depth);
        const auto found = members.find(name);
        if (found == members.end()) {
            located.found = false;
            return located;
        }
        Located receiver;
        if (call >= 0 && located.item.type == SymbolType::Class) receiver = located;
        if (located.item.type == SymbolType::Module) {
            located.module = located.item.target;
            located.path = QStringList{name};
        } else {
            located.path.append(name);
        }
        located.item = found.value();
        followImports(request, &located.item, &located.module, &located.path);
        if (call >= 0) located = callResult(request, located, scope, depth,
            QStringView(parts[i]).mid(call + 1, parts[i].size() - call - 2),
            receiver.item.type == SymbolType::Class ? &receiver : nullptr);
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
    if (item.instanceAttributes) {
        for (auto it = item.instanceAttributes->cbegin(); it != item.instanceAttributes->cend(); ++it) {
            if (!members.contains(it.key())) members.insert(it.key(), it.value());
        }
    }
    for (auto it = members.begin(); it != members.end(); ++it) {
        if (it->type == SymbolType::Function && it->displayCategory.isEmpty()) it->displayCategory = "method";
    }
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

bool CompletionEngine::isBoundMethod(Request& request, const SymbolTable& scope, QStringView text,
                                     const QStringList& parts, const Located& located) {
    if (parts.size() < 2 || located.item.binding == Symbol::StaticMethod) return false;
    if (located.item.binding == Symbol::ClassMethod) return true;
    const auto owner = walk(request, scope, text, parts.mid(0, parts.size() - 1), 0, false);
    const auto declared = scope.constFind(parts.first());
    return owner.found && owner.item.type == SymbolType::Class
           && declared != scope.constEnd() && declared->type == SymbolType::Value;
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
    SymbolTable locals = documentDeclarations(text);
    const int lineStart = int(before.lastIndexOf(QLatin1Char('\n'))) + 1;
    int indent = 0;
    for (const QChar c : before.mid(lineStart)) {
        if (c == ' ') ++indent;
        else if (c == '\t') indent = (indent / 8 + 1) * 8;
        else break;
    }
    const auto visible = declarationsFor(before, nullptr, indent).symbols;
    for (auto it = visible.constBegin(); it != visible.constEnd(); ++it) locals.insert(it.key(), it.value());
    // 名前をたどる(変数は代入・型ヒントからクラスを推論する)。推論はカーソルより前の本文で行う。
    const Located located = walk(request, locals, before, parts, 0);
    if (!located.found) {
        return info;
    }
    const Symbol& item = located.item;
    info.bindingKnown = true;
    info.boundMethod = isBoundMethod(request, locals, before, parts, located);
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
            return location.sourceFile.isEmpty() ? location.file : location.sourceFile;
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
    SymbolTable locals = documentDeclarations(text);
    const int lineStart = int(before.lastIndexOf(QLatin1Char('\n'))) + 1;
    int indent = 0;
    for (const auto c : before.mid(lineStart)) {
        if (c == ' ') ++indent;
        else if (c == '\t') indent = (indent / 8 + 1) * 8;
        else break;
    }
    // 補完・ホバーと同じ可視スコープを使い、関数ローカルの型からも定義へ移動する。
    const auto visible = declarationsFor(before, nullptr, indent).symbols;
    for (auto it = visible.constBegin(); it != visible.constEnd(); ++it) locals.insert(it.key(), it.value());
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
    const QString fullLine = source.mid(lastNewline + 1);
    int statementStart = lastNewline + 1;
    if (fullLine.contains(';')) {
        int state = 0;
        int offset = 0;
        int depth = 0;
        for (const auto& part : source.split('\n')) {
            for (const auto& word : tokenizeLine(part, ScriptLanguage::Python, state, &state)) {
                if (word.type != TokenType::Operator || word.length != 1) continue;
                const QChar c = part[word.start];
                if (c == '(' || c == '[' || c == '{') ++depth;
                else if (c == ')' || c == ']' || c == '}') --depth;
                else if (c == ';' && depth == 0 && offset >= lastNewline + 1) statementStart = offset + word.start + 1;
            }
            offset += int(part.size()) + 1;
        }
    }
    const QString line = source.mid(statementStart);
    SymbolTable symbols;
    QString prefix;

    if (isDeclaringName(line)) {
        return result;
    }

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

    // 最後の行は入力途中なので宣言に含めず、字下げだけを現在のスコープ判定へ渡す。
    // 本文が同じでも字下げで関数の内外が変わるので、控えのキーにも含める。
    int cursorIndent = 0;
    for (const QChar character : fullLine) {
        if (character == ' ') ++cursorIndent;
        else if (character == '\t') cursorIndent = (cursorIndent / 8 + 1) * 8;
        else if (character == '\f') cursorIndent = 0;
        else break;
    }
    const SymbolTable locals =
        declarationsFor(QStringView(source).left(statementStart), nullptr, cursorIndent).symbols;
    static const QRegularExpression fromImport("^\\s*from\\s+([\\w.]+)\\s+import\\s+(\\w*)$",
                                               QRegularExpression::UseUnicodePropertiesOption);
    const QRegularExpressionMatch fromMatch = fromImport.match(line);
    const QStringList receiver = callReceiver(line, token);
    const QString valueReceiver = memberReceiver(line, token.section('.', -1));
    if (fromMatch.hasMatch()) {
        // from maya import cm → mayaの中の名前。
        symbols = moduleMembers(request, fromMatch.captured(1));
        prefix = fromMatch.captured(2);
    } else if (!valueReceiver.isEmpty()) {
        const auto located = valueType(request, locals, source, valueReceiver, 0);
        if (located.found) symbols = membersOf(request, located, locals, 0);
        prefix = token.section('.', -1);
    } else if (token.contains('.') || !receiver.isEmpty()) {
        // a.b.c → aの中のbの中の、cで始まる名前。変数(x = pkg.A() / x: pkg.A)はクラスを推論する。
        const QStringList parts = receiver.isEmpty() ? token.split('.') : receiver;
        // 本文で使える名前だけを起点にする。Mayaがロード済みでも、未importの外部名は混ぜない。
        const Located located = walk(request, locals, source, parts.mid(0, parts.size() - 1), 0, false);
        if (located.found) {
            symbols = membersOf(request, located, locals, 0);
        }
        prefix = parts.last();
    } else {
        // 名前だけ: 組み込みの名前・予約語・この本文の宣言(同じ名前なら本文の宣言が優先)。
        // 表を重ねてコピーせず、名前順に並べて読む。
        result.items = mergedItemsFor(baseNames_, locals, token);
        const CallContext call = findCallContext(source);
        if (call.nameEnd >= 0) {
            const QString callee = trailingDottedName(source.left(call.nameEnd));
            const QStringList parts = callee.split('.');
            auto located = walk(request, locals, source, parts, 0, false);
            bool bound = false;
            if (located.found && located.item.type == SymbolType::Class) {
                located = walk(request, locals, source, parts + QStringList{"__init__"}, 0, false);
                bound = true;
            } else {
                bound = isBoundMethod(request, locals, source, parts, located);
            }
            if (located.found) {
                QString signature = located.item.signature;
                if (signature.isEmpty() && source_.describe && !located.module.isEmpty()) {
                    QString doc;
                    source_.describe(located.module, located.path, &signature, &doc);
                }
                auto signatureParts = splitSignature(signature);
                if (bound) dropBoundParameter(&signatureParts);
                const auto parameters = keywordParameterNames(source.mid(call.openParen + 1), signatureParts.parameters);
                for (auto it = parameters.crbegin(); it != parameters.crend(); ++it) {
                    result.items.prepend({*it + "=", signature, QString(), "variable"});
                }
                while (result.items.size() > kMaximumItems) result.items.removeLast();
            }
        }
        return result;
    }
    result.items = itemsFor(symbols, prefix);
    return result;
}

}  // namespace mce
