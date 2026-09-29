/** @file python_declarations.cpp
 * @brief Pythonの宣言の抽出の実装。
 * @details 処理は2段階:
 * 1. 論理行を作る: 物理行を字句に分け、括弧の中・三重引用符の中・行末の``\``で続く行を1つにまとめる。
 *    コメントは捨てる。論理行ごとに、最初の物理行のインデント(字下げの幅)を覚える。
 * 2. ブロックを読む: 同じインデントの論理行を順に読み、それより深い行は直前の文の中身として扱う。
 *    中身を読むのは``class``と``if TYPE_CHECKING:``だけで、それ以外(関数の中など)は読み飛ばす。
 */
#include "core/python_declarations.h"
#include "core/script_lexer.h"
#include <QStringList>
#include <QVector>

namespace hedit {
namespace {

/** @brief 字句と、その文字列。 */
struct Word {
    TokenType type = TokenType::Name;  ///< 種類。
    QString text;                      ///< 文字列。
};
using Words = QVector<Word>;

/** @brief 論理行(1つの文、または``;``で区切った複数の文)。 */
struct LogicalLine {
    int indent = 0;  ///< 最初の物理行のインデントの幅。
    Words words;     ///< コメントを除いた字句。
};

/** @brief 文字列の位置のWordが、指定の記号か。 @param word 字句。 @param text 記号。 @return 一致すればtrue。 */
bool isOperator(const Word& word, const char* text) {
    return word.type == TokenType::Operator && word.text == QLatin1String(text);
}

/** @brief 字句が指定の名前(予約語など)か。 @param word 字句。 @param text 名前。 @return 一致すればtrue。 */
bool isName(const Word& word, const char* text) {
    return word.type == TokenType::Name && word.text == QLatin1String(text);
}

/** @brief 字句が普通の名前(予約語でない)か。 @param word 字句。 @return 普通の名前ならtrue。 */
bool isPlainName(const Word& word) {
    return word.type == TokenType::Name && !isKeyword(word.text, ScriptLanguage::Python);
}

/** @brief 開き括弧なら+1、閉じ括弧なら-1。 @param word 字句。 @return 括弧の深さの変化。 */
int bracketDelta(const Word& word) {
    if (word.type != TokenType::Operator || word.text.size() != 1) {
        return 0;
    }
    const QChar c = word.text[0];
    if (c == '(' || c == '[' || c == '{') {
        return 1;
    }
    if (c == ')' || c == ']' || c == '}') {
        return -1;
    }
    return 0;
}

/** @brief 行頭のインデントの幅。タブは次の8の倍数まで進める(Pythonと同じ)。 @param line 行。 @return 幅。 */
int indentWidth(const QString& line) {
    int width = 0;
    for (const QChar c : line) {
        if (c == ' ') {
            ++width;
        } else if (c == '\t') {
            width = (width / 8 + 1) * 8;
        } else if (c == '\f') {
            width = 0;
        } else {
            break;
        }
    }
    return width;
}

/** @brief 本文を論理行に分ける。
 * @param source 本文。
 * @param complete 最後で括弧・三重引用符が閉じていればtrueを入れる。
 * @return 論理行の一覧。
 */
QVector<LogicalLine> logicalLines(const QString& source, bool* complete) {
    QVector<LogicalLine> result;
    LogicalLine current;
    int state = kLexerNormal;
    int depth = 0;
    const QStringList physicalLines = source.split('\n');
    for (QString line : physicalLines) {
        if (line.endsWith('\r')) {
            line.chop(1);
        }
        int endState = kLexerNormal;
        const QList<Token> tokens = tokenizeLine(line, ScriptLanguage::Python, state, &endState);
        bool backslash = false;
        for (const Token& token : tokens) {
            if (token.type == TokenType::Comment) {
                continue;
            }
            Word word{token.type, line.mid(token.start, token.length)};
            if (isOperator(word, "\\")) {
                backslash = true;  // 行末の \ は、次の行へ続く印。
                continue;
            }
            backslash = false;
            if (current.words.isEmpty()) {
                current.indent = indentWidth(line);
            }
            depth = qMax(0, depth + bracketDelta(word));
            current.words.append(word);
        }
        state = endState;
        const bool continues = depth > 0 || state != kLexerNormal || backslash;
        if (!continues) {
            if (!current.words.isEmpty()) {
                result.append(current);
            }
            current = LogicalLine();
        }
    }
    if (!current.words.isEmpty()) {
        result.append(current);
    }
    *complete = depth == 0 && state == kLexerNormal;
    return result;
}

/** @brief 括弧の外(深さ0)にある区切り記号で分ける。
 * @param words 字句。
 * @param separator 区切り記号(``;``・``,``・``=``など)。
 * @return 区切られた部分(区切り記号は含まない)。
 */
QVector<Words> splitTopLevel(const Words& words, const char* separator) {
    QVector<Words> parts(1);
    int depth = 0;
    for (const Word& word : words) {
        if (depth == 0 && isOperator(word, separator)) {
            parts.append(Words());
            continue;
        }
        depth = qMax(0, depth + bracketDelta(word));
        parts.last().append(word);
    }
    return parts;
}

/** @brief 括弧の外にある最初の``:``の位置(複合文の見出しの終わり)。 @param words 字句。 @return 位置。無ければ-1。 */
int headerColon(const Words& words) {
    int depth = 0;
    for (int i = 0; i < words.size(); ++i) {
        if (depth == 0 && isOperator(words[i], ":")) {
            return i;
        }
        depth = qMax(0, depth + bracketDelta(words[i]));
    }
    return -1;
}

/** @brief ``a.b.c``の形の名前を読む。
 * @param words 字句。
 * @param index 読み始める位置。読み終えた次の位置に進める。
 * @return 読んだ名前。名前が無ければ空。
 */
QString readDottedName(const Words& words, int* index) {
    QString name;
    while (*index < words.size() && words[*index].type == TokenType::Name) {
        name += words[*index].text;
        ++*index;
        if (*index < words.size() && isOperator(words[*index], ".")) {
            name += '.';
            ++*index;
        } else {
            break;
        }
    }
    return name;
}

/** @brief ``import a.b as c, d``を読む。 @param words ``import``の後ろの字句。 @param table 追加先。 */
void readImport(const Words& words, SymbolTable& table) {
    for (const Words& part : splitTopLevel(words, ",")) {
        int index = 0;
        const QString dotted = readDottedName(part, &index);
        if (dotted.isEmpty()) {
            continue;
        }
        Symbol symbol;
        if (index + 1 < part.size() && isName(part[index], "as") && part[index + 1].type == TokenType::Name) {
            // import a.b as c → c は a.b を指す。
            symbol.target = dotted;
            table.insert(part[index + 1].text, symbol);
        } else {
            // import a.b → 使える名前は a で、a を指す。
            const QString top = dotted.section('.', 0, 0);
            symbol.target = top;
            table.insert(top, symbol);
        }
    }
}

/** @brief ``from X import Y as Z``を読む。
 * @param words ``from``の後ろの字句。
 * @param moduleName 相対importの基準になるモジュール名。
 * @param table 追加先。
 */
void readFromImport(const Words& words, const QString& moduleName, SymbolTable& table) {
    int index = 0;
    int level = 0;  // 先頭の点の数(相対importの段数)。
    while (index < words.size() && words[index].type == TokenType::Operator
           && (words[index].text == "." || words[index].text == "...")) {
        level += words[index].text.size();
        ++index;
    }
    // from . import x のように点の直後がimportなら、モジュール名は無い。
    QString module;
    if (index < words.size() && !isName(words[index], "import")) {
        module = readDottedName(words, &index);
    }
    if (index >= words.size() || !isName(words[index], "import")) {
        return;
    }
    ++index;
    // 相対importの親: pkg.sub の中の from .x import y は pkg.x。
    QString parent = module;
    if (level > 0) {
        QStringList parts = moduleName.split('.');
        parts = parts.mid(0, qMax(0, int(parts.size()) - level));
        if (!module.isEmpty()) {
            parts.append(module);
        }
        parent = parts.join('.');
    }
    Words names = words.mid(index);
    if (!names.isEmpty() && isOperator(names.first(), "(")) {
        names.removeFirst();
        if (!names.isEmpty() && isOperator(names.last(), ")")) {
            names.removeLast();
        }
    }
    for (const Words& part : splitTopLevel(names, ",")) {
        if (part.isEmpty() || part[0].type != TokenType::Name) {
            continue;  // * は読まない。
        }
        const QString name = part[0].text;
        QString alias = name;
        if (part.size() >= 3 && isName(part[1], "as") && part[2].type == TokenType::Name) {
            alias = part[2].text;
        }
        Symbol symbol;
        if (level > 0 && module.isEmpty()) {
            // from . import nodes → 親パッケージの中のモジュール nodes を指す。
            symbol.target = parent + "." + name;
        } else {
            symbol.fromModule = parent;
            symbol.fromName = name;
        }
        table.insert(alias, symbol);
    }
}

/** @brief ``def name(a, *args, b=1, **kw)``から、補完に出す説明``name(a, *args, b, **kw)``を作る。
 * @param words ``def``の後ろの字句(名前から)。
 * @param name 関数名を入れる。
 * @return 説明。関数の形でなければ空。
 */
QString functionDetail(const Words& words, QString* name) {
    if (words.size() < 2 || !isPlainName(words[0])) {
        return QString();
    }
    // Python 3.12の型引数 def name[T](...) は、[ ] を読み飛ばす。
    int open = 1;
    if (isOperator(words[1], "[")) {
        int depth = 0;
        for (; open < words.size(); ++open) {
            depth += bracketDelta(words[open]);
            if (depth == 0) {
                ++open;
                break;
            }
        }
    }
    if (open >= words.size() || !isOperator(words[open], "(")) {
        return QString();
    }
    *name = words[0].text;
    QStringList arguments;
    Words parameter;
    int depth = 0;
    int lambdas = 0;  // 既定値の中のlambdaの数(lambdaの引数の , で区切らないため)。
    // 1つの引数の字句から、名前を取り出して追加する。
    auto finish = [&arguments](const Words& part) {
        if (part.isEmpty()) {
            return;
        }
        if (part[0].type == TokenType::Name) {
            arguments.append(part[0].text);
        } else if ((isOperator(part[0], "*") || isOperator(part[0], "**")) && part.size() >= 2
                   && part[1].type == TokenType::Name) {
            arguments.append(part[0].text + part[1].text);
        }
        // 単独の * と / は区切りの印なので出さない。
    };
    for (int i = open + 1; i < words.size(); ++i) {
        const Word& word = words[i];
        if (depth == 0 && isOperator(word, ")")) {
            finish(parameter);
            return *name + "(" + arguments.join(", ") + ")";
        }
        if (depth == 0 && isName(word, "lambda")) {
            ++lambdas;
        } else if (depth == 0 && lambdas > 0 && isOperator(word, ":")) {
            --lambdas;
        } else if (depth == 0 && lambdas == 0 && isOperator(word, ",")) {
            finish(parameter);
            parameter.clear();
            continue;
        }
        depth = qMax(0, depth + bracketDelta(word));
        parameter.append(word);
    }
    // 閉じ括弧が無い(書きかけ)場合も、読めた分の引数で説明を作る。
    finish(parameter);
    return *name + "(" + arguments.join(", ") + ")";
}

/** @brief 代入(``a = b = 1``・``a: int = 1``・``a: int``)の左辺の名前を追加する。
 * @param words 文の字句。
 * @param table 追加先。
 */
void readAssignment(const Words& words, SymbolTable& table) {
    const QVector<Words> parts = splitTopLevel(words, "=");
    if (parts.size() == 1) {
        // = が無い: 注釈だけの宣言 a: int。
        if (words.size() >= 2 && isPlainName(words[0]) && isOperator(words[1], ":")) {
            table.insert(words[0].text, Symbol());
        }
        return;
    }
    // 最後の = の右側は値なので、それより前が代入先。単独の名前だけを宣言として扱う(a.b や a, b は対象外)。
    for (int i = 0; i + 1 < parts.size(); ++i) {
        const Words& target = parts[i];
        if (target.size() == 1 && isPlainName(target[0])) {
            table.insert(target[0].text, Symbol());
        } else if (i == 0 && target.size() >= 2 && isPlainName(target[0]) && isOperator(target[1], ":")) {
            table.insert(target[0].text, Symbol());
        }
    }
}

/** @brief 1つの単純な文(複合文でない文)を読む。
 * @param words 文の字句。
 * @param moduleName 相対importの基準。
 * @param table 追加先。
 */
void readSimpleStatement(const Words& words, const QString& moduleName, SymbolTable& table) {
    if (words.isEmpty()) {
        return;
    }
    if (isName(words[0], "import")) {
        readImport(words.mid(1), table);
    } else if (isName(words[0], "from")) {
        readFromImport(words.mid(1), moduleName, table);
    } else if (words[0].type == TokenType::Name && isKeyword(words[0].text, ScriptLanguage::Python)) {
        // return・pass・global などは宣言ではない。
    } else if (words[0].type == TokenType::Name) {
        readAssignment(words, table);
    }
}

/** @brief ``;``で区切られた単純な文を順に読む。 @param words 字句。 @param moduleName 相対importの基準。 @param table 追加先。 */
void readSimpleStatements(const Words& words, const QString& moduleName, SymbolTable& table) {
    for (const Words& statement : splitTopLevel(words, ";")) {
        readSimpleStatement(statement, moduleName, table);
    }
}

/** @brief ``if TYPE_CHECKING:``または``if typing.TYPE_CHECKING:``の見出しか。 @param header ``:``より前の字句。 @return 該当すればtrue。 */
bool isTypeCheckingHeader(const Words& header) {
    if (header.size() == 2) {
        return isName(header[0], "if") && isName(header[1], "TYPE_CHECKING");
    }
    return header.size() == 4 && isName(header[0], "if") && isName(header[1], "typing") && isOperator(header[2], ".")
           && isName(header[3], "TYPE_CHECKING");
}

SymbolTable readBlock(const QVector<LogicalLine>& lines, int* index, int indent, const QString& moduleName);

/** @brief 複合文の中身(見出しの``:``の後ろと、次の行からの深いブロック)を読む。
 * @param inlineBody 見出しと同じ行の``:``の後ろの字句。
 * @param lines 論理行。
 * @param index 次に読む論理行。中身を読んだ分だけ進める。
 * @param indent 見出しのインデント。
 * @param moduleName 相対importの基準。
 * @return 中身の宣言。
 */
SymbolTable readBody(const Words& inlineBody, const QVector<LogicalLine>& lines, int* index, int indent,
                     const QString& moduleName) {
    SymbolTable body;
    readSimpleStatements(inlineBody, moduleName, body);
    if (*index < lines.size() && lines[*index].indent > indent) {
        const SymbolTable block = readBlock(lines, index, lines[*index].indent, moduleName);
        for (auto it = block.begin(); it != block.end(); ++it) {
            body.insert(it.key(), it.value());
        }
    }
    return body;
}

/** @brief 同じインデントの論理行を順に読む。
 * @param lines 論理行。
 * @param index 読み始める論理行。読み終えた次の位置に進める。
 * @param indent このブロックのインデント。これより浅い行でブロックは終わる。
 * @param moduleName 相対importの基準。
 * @return ブロックの宣言。
 */
SymbolTable readBlock(const QVector<LogicalLine>& lines, int* index, int indent, const QString& moduleName) {
    SymbolTable table;
    while (*index < lines.size()) {
        const LogicalLine& line = lines[*index];
        if (line.indent < indent) {
            break;  // ブロックの終わり。
        }
        ++*index;
        if (line.indent > indent) {
            continue;  // 読まない複合文(関数など)の中身。
        }
        const Words& words = line.words;
        const Word& first = words[0];
        const bool asyncDef = isName(first, "async") && words.size() > 1 && isName(words[1], "def");
        if (isName(first, "def") || asyncDef) {
            QString name;
            const QString detail = functionDetail(words.mid(asyncDef ? 2 : 1), &name);
            if (!name.isEmpty()) {
                Symbol symbol;
                symbol.detail = detail;
                table.insert(name, symbol);
            }
            continue;  // 関数の中身は、次からの深い行として読み飛ばされる。
        }
        if (isName(first, "class")) {
            if (words.size() < 2 || !isPlainName(words[1])) {
                continue;
            }
            const int colon = headerColon(words);
            const Words inlineBody = colon >= 0 ? words.mid(colon + 1) : Words();
            Symbol symbol;
            symbol.detail = "class " + words[1].text;
            symbol.members = std::make_shared<SymbolTable>(readBody(inlineBody, lines, index, indent, moduleName));
            table.insert(words[1].text, symbol);
            continue;
        }
        if (isName(first, "if")) {
            const int colon = headerColon(words);
            if (colon >= 0 && isTypeCheckingHeader(words.mid(0, colon))) {
                // 型のためだけのimportも、実行せずに読む。
                const SymbolTable body = readBody(words.mid(colon + 1), lines, index, indent, moduleName);
                for (auto it = body.begin(); it != body.end(); ++it) {
                    table.insert(it.key(), it.value());
                }
            }
            continue;
        }
        if (isOperator(first, "@")) {
            continue;  // デコレーター。次の行のdef・classを読む。
        }
        if (first.type == TokenType::Name && isKeyword(first.text, ScriptLanguage::Python)
            && !isName(first, "import") && !isName(first, "from")) {
            continue;  // for・while・try・with などの複合文と、return などの文。
        }
        readSimpleStatements(words, moduleName, table);
    }
    return table;
}

}  // namespace

DeclarationResult extractPythonDeclarations(const QString& source, const QString& moduleName) {
    DeclarationResult result;
    const QVector<LogicalLine> lines = logicalLines(source, &result.complete);
    int index = 0;
    // 最初の行が字下げされていても(選択範囲の一部など)、その深さをモジュール直下として読む。
    const int indent = lines.isEmpty() ? 0 : lines.first().indent;
    while (index < lines.size()) {
        const SymbolTable block = readBlock(lines, &index, qMin(indent, lines[index].indent), moduleName);
        for (auto it = block.begin(); it != block.end(); ++it) {
            result.symbols.insert(it.key(), it.value());
        }
    }
    return result;
}

}  // namespace hedit
