/** @file python_declarations.cpp
 * @brief Pythonの宣言の抽出の実装。
 * @details 処理は2段階:
 * 1. 論理行を作る: 物理行を字句に分け、括弧の中・三重引用符の中・行末の``\``で続く行を1つにまとめる。
 *    コメントは捨てる。論理行ごとに、最初の物理行のインデント(字下げの幅)を覚える。
 * 2. ブロックを読む: 同じインデントの論理行を順に読み、それより深い行は直前の文の中身として扱う。
 *    中身を読むのは``class``と``if TYPE_CHECKING:``だけで、それ以外(関数の中など)は読み飛ばす。
 *
 * 字句は文字列(QString)を持たず、本文の中の位置だけを1つの配列に並べる。論理行・文・引数は、その配列の中の範囲
 * (Words)で表し、部分を取り出すときもコピーしない。文字列を作るのは、宣言の名前・見出し・docstringなど、
 * 結果に入れるものだけ(読み飛ばす関数の中身の字句には、文字列を作らない)。
 */
#include "core/python_declarations.h"
#include "core/docstrings.h"
#include "core/script_lexer.h"
#include <QStringList>
#include <QVarLengthArray>
#include <QVector>

namespace hedit {
namespace {

/** @brief 字句。文字列は持たず、本文の中の位置で表す(必要になったときだけ文字列を作る)。 */
struct Word {
    TokenType type = TokenType::Name;  ///< 種類。
    int start = 0;                     ///< 本文の中の開始位置。
    int end = 0;                       ///< 本文の中の終わりの位置(含まない)。行をまたぐ三重引用符の文字列は、閉じた行まで。
};

/** @brief 論理行(1つの文、または``;``で区切った複数の文)。 */
struct LogicalLine {
    int indent = 0;  ///< 最初の物理行のインデントの幅。
    int first = 0;   ///< 最初の字句の、字句の配列の中の位置。
    int count = 0;   ///< コメントを除いた字句の数。
};

/** @brief 字句の並びの一部。字句の配列の中の範囲を指すだけで、字句をコピーしない。
 * @details 指している配列(DeclarationReader::words_)は、範囲を作り始める前に完成させ、以後は変えない。
 */
class Words {
public:
    Words() = default;

    /** @brief 範囲を作る。 @param data 最初の字句。 @param size 字句の数。 */
    Words(const Word* data, int size) : data_(data), size_(size) {}

    /** @brief 字句の数。 @return 数。 */
    int size() const { return size_; }

    /** @brief 空か。 @return 字句が無ければtrue。 */
    bool isEmpty() const { return size_ == 0; }

    /** @brief i番目の字句。 @param i 位置。 @return 字句。 */
    const Word& operator[](int i) const { return data_[i]; }

    /** @brief 最初の字句。 @return 字句。 */
    const Word& first() const { return data_[0]; }

    /** @brief 最後の字句。 @return 字句。 */
    const Word& last() const { return data_[size_ - 1]; }

    /** @brief 範囲のfor文用。 @return 最初の字句。 */
    const Word* begin() const { return data_; }

    /** @brief 範囲のfor文用。 @return 最後の字句の次。 */
    const Word* end() const { return data_ + size_; }

    /** @brief 一部の範囲(QVector::midと同じ)。
     * @param position 開始位置。範囲の外なら空。
     * @param length 数。負なら最後まで。
     * @return 範囲。
     */
    Words mid(int position, int length = -1) const {
        position = qBound(0, position, size_);
        if (length < 0 || position + length > size_) {
            length = size_ - position;
        }
        return Words(data_ + position, length);
    }

    /** @brief 最初の字句を範囲から外す。 */
    void removeFirst() {
        ++data_;
        --size_;
    }

    /** @brief 最後の字句を範囲から外す。 */
    void removeLast() { --size_; }

private:
    const Word* data_ = nullptr;  ///< 最初の字句。
    int size_ = 0;                ///< 字句の数。
};

}  // namespace
}  // namespace hedit

// どれも整数とポインターだけの型。QVector・QVarLengthArrayが要素をmemcpyで移せるようにする。
Q_DECLARE_TYPEINFO(hedit::Word, Q_PRIMITIVE_TYPE);
Q_DECLARE_TYPEINFO(hedit::LogicalLine, Q_PRIMITIVE_TYPE);
Q_DECLARE_TYPEINFO(hedit::Words, Q_PRIMITIVE_TYPE);

namespace hedit {
namespace {

/// 区切った文の一覧。たいていは数個なので、8個まではヒープを使わない配列にする。
using WordsList = QVarLengthArray<Words, 8>;

/** @brief 行頭のインデントの幅。タブは次の8の倍数まで進める(Pythonと同じ)。
 * @param line 行。
 * @return 幅。
 * @note エディターの表示用のlineIndentWidth(core/code_outline.h。タブは4の倍数)とは幅の規則が違う。
 * ここではPythonの字句解析と同じ規則で、ブロックの構造をPythonと同じに読む。Python 3はタブと空白の混ぜ方で
 * 意味が変わる字下げを構文エラーにするので、実行できる本文ではどちらの規則でも構造は同じになる。
 */
int indentWidth(QStringView line) {
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

/** @brief 本文から宣言を読む。1回の抽出で1つ作って使い捨てる。 */
class DeclarationReader {
public:
    /** @brief 本文を受け取る。 @param source 本文。 @param moduleName 相対importの基準。 */
    DeclarationReader(QStringView source, const QString& moduleName) : source_(source), moduleName_(moduleName) {}

    /** @brief 宣言を取り出す。 @return 結果。 */
    DeclarationResult read() {
        DeclarationResult result;
        buildLogicalLines(&result.complete);
        int index = 0;
        if (!lines_.isEmpty() && isStringStatement(lineWords(lines_.first()))) {
            result.docstring = docstringOf(lineWords(lines_.first()));
        }
        // 最初の行が字下げされていても(選択範囲の一部など)、その深さをモジュール直下として読む。
        const int indent = lines_.isEmpty() ? 0 : lines_.first().indent;
        while (index < lines_.size()) {
            const SymbolTable block = readBlock(&index, qMin(indent, lines_[index].indent));
            for (auto it = block.begin(); it != block.end(); ++it) {
                result.symbols.insert(it.key(), it.value());
            }
        }
        return result;
    }

private:
    /** @brief 字句が指す本文の部分。 @param word 字句。 @return 本文の一部(コピーしない)。 */
    QStringView view(const Word& word) const { return source_.mid(word.start, word.end - word.start); }

    /** @brief 字句の文字列を作る。
     * @param word 字句。
     * @return 文字列。行をまたぐ文字列は、行の区切りを``\n``にする(各行の行末の``\r``は除く)。
     */
    QString text(const Word& word) const {
        QString value = view(word).toString();
        if (word.type == TokenType::String && value.contains(QLatin1Char('\r'))) {
            value.replace(QLatin1String("\r\n"), QLatin1String("\n"));
        }
        return value;
    }

    /** @brief 字句の文字列を末尾に足す。 @param out 足す先。 @param word 字句。 */
    void appendText(QString& out, const Word& word) const {
        if (word.type == TokenType::String) {
            out += text(word);
        } else {
            const QStringView part = view(word);
            out.append(part.data(), int(part.size()));
        }
    }

    /** @brief 指定の記号か。 @param word 字句。 @param op 記号。 @return 一致すればtrue。 */
    bool isOperator(const Word& word, const char* op) const {
        return word.type == TokenType::Operator && view(word) == QLatin1String(op);
    }

    /** @brief 指定の名前(予約語など)か。 @param word 字句。 @param name 名前。 @return 一致すればtrue。 */
    bool isName(const Word& word, const char* name) const {
        return word.type == TokenType::Name && view(word) == QLatin1String(name);
    }

    /** @brief 普通の名前(予約語でない)か。 @param word 字句。 @return 普通の名前ならtrue。 */
    bool isPlainName(const Word& word) const {
        return word.type == TokenType::Name && !isKeyword(view(word), ScriptLanguage::Python);
    }

    /** @brief 開き括弧なら+1、閉じ括弧なら-1。 @param word 字句。 @return 括弧の深さの変化。 */
    int bracketDelta(const Word& word) const {
        if (word.type != TokenType::Operator || word.end - word.start != 1) {
            return 0;
        }
        const QChar c = source_[word.start];
        if (c == '(' || c == '[' || c == '{') {
            return 1;
        }
        if (c == ')' || c == ']' || c == '}') {
            return -1;
        }
        return 0;
    }

    /** @brief 論理行の字句。 @param line 論理行。 @return 字句の範囲。 */
    Words lineWords(const LogicalLine& line) const { return Words(words_.constData() + line.first, line.count); }

    /** @brief 本文を論理行に分ける(words_とlines_を作る)。
     * @param complete 最後で括弧・三重引用符が閉じていればtrueを入れる。
     */
    void buildLogicalLines(bool* complete) {
        QVector<Token> tokens;  // 行ごとに使い回す。
        words_.reserve(int(source_.size() / 6) + 16);
        LogicalLine current;
        int state = kLexerNormal;
        int depth = 0;
        forEachLine(source_, [&](int, QStringView rawLine) {
            const int lineStart = int(rawLine.data() - source_.data());
            QStringView line = rawLine;
            if (line.endsWith(QLatin1Char('\r'))) {
                line.chop(1);
            }
            int endState = kLexerNormal;
            tokenizeLineInto(line, ScriptLanguage::Python, state, &endState, &tokens);
            // 三重引用符の文字列の続きの行は、前の行の文字列の字句へつなげる(1つの文字列を1つの字句にする)。
            // 続きの行の最初の字句は、必ず行頭からの文字列の字句になる(空行でも長さ0の字句)。
            const bool insideString = state != kLexerNormal && current.count > 0
                                      && words_.last().type == TokenType::String;
            bool backslash = false;
            for (int t = 0; t < tokens.size(); ++t) {
                const Token& token = tokens[t];
                if (token.type == TokenType::Comment) {
                    continue;
                }
                const Word word{token.type, lineStart + token.start, lineStart + token.start + token.length};
                if (insideString && t == 0 && token.start == 0 && token.type == TokenType::String) {
                    words_.last().end = word.end;  // 間の改行も含めた範囲にする(textで行末の\rを除く)。
                    continue;
                }
                if (isOperator(word, "\\")) {
                    backslash = true;  // 行末の \ は、次の行へ続く印。
                    continue;
                }
                backslash = false;
                if (current.count == 0) {
                    current.indent = indentWidth(line);
                    current.first = int(words_.size());
                }
                depth = qMax(0, depth + bracketDelta(word));
                words_.append(word);
                ++current.count;
            }
            state = endState;
            const bool continues = depth > 0 || state != kLexerNormal || backslash;
            if (!continues) {
                if (current.count > 0) {
                    lines_.append(current);
                }
                current = LogicalLine();
            }
        });
        if (current.count > 0) {
            lines_.append(current);
        }
        *complete = depth == 0 && state == kLexerNormal;
    }

    /** @brief 括弧の外(深さ0)にある区切り記号で分ける。
     * @param words 字句。
     * @param separator 区切り記号(``;``・``,``・``=``など)。
     * @return 区切られた部分(区切り記号は含まない)。字句はコピーせず、範囲で返す。
     */
    WordsList splitTopLevel(Words words, const char* separator) const {
        WordsList parts;
        int depth = 0;
        int partStart = 0;
        for (int i = 0; i < words.size(); ++i) {
            if (depth == 0 && isOperator(words[i], separator)) {
                parts.append(words.mid(partStart, i - partStart));
                partStart = i + 1;
                continue;
            }
            depth = qMax(0, depth + bracketDelta(words[i]));
        }
        parts.append(words.mid(partStart, words.size() - partStart));
        return parts;
    }

    /** @brief 括弧の外にある最初の``:``の位置(複合文の見出しの終わり)。 @param words 字句。 @return 位置。無ければ-1。 */
    int headerColon(Words words) const {
        int depth = 0;
        for (int i = 0; i < words.size(); ++i) {
            if (depth == 0 && isOperator(words[i], ":")) {
                return i;
            }
            depth = qMax(0, depth + bracketDelta(words[i]));
        }
        return -1;
    }

    /** @brief 字句を、ホバーに出す見出しの文字列へ戻す(``def name(a, b=1) -> int``)。
     * @param words 字句(``:``より前)。
     * @return 空白をPEP 8に近い形で入れた文字列。
     */
    QString joinWords(Words words) const {
        QString text;
        int depth = 0;
        bool annotated = false;  // 今の引数に型の注釈(a: int)があるか。あれば = の前後に空白を入れる。
        for (int i = 0; i < words.size(); ++i) {
            const Word& word = words[i];
            const Word* previous = i > 0 ? &words[i - 1] : nullptr;
            bool space = !text.isEmpty();
            if (previous && (isOperator(*previous, "(") || isOperator(*previous, "[") || isOperator(*previous, "{")
                             || isOperator(*previous, ".") || isOperator(*previous, "@"))) {
                space = false;
            }
            if (isOperator(word, ")") || isOperator(word, "]") || isOperator(word, "}") || isOperator(word, ",")
                || isOperator(word, ":") || isOperator(word, ".")) {
                space = false;
            }
            if ((isOperator(word, "(") || isOperator(word, "[")) && previous
                && (previous->type == TokenType::Name || isOperator(*previous, ")") || isOperator(*previous, "]"))) {
                space = false;  // 呼出し・添え字。
            }
            if (depth > 0 && previous && (isOperator(*previous, "*") || isOperator(*previous, "**"))
                && (i < 2 || isOperator(words[i - 2], "(") || isOperator(words[i - 2], ","))) {
                space = false;  // *args・**kwargs。
            }
            const bool keywordEquals = depth > 0 && !annotated;
            if (keywordEquals && (isOperator(word, "=") || (previous && isOperator(*previous, "=")))) {
                space = false;  // 既定値 b=1。
            }
            if (depth == 1 && isOperator(word, ":")) {
                annotated = true;
            } else if (depth == 1 && isOperator(word, ",")) {
                annotated = false;
            }
            depth = qMax(0, depth + bracketDelta(word));
            if (space) {
                text += ' ';
            }
            appendText(text, word);
        }
        return text;
    }

    /** @brief 字句が全て文字列か(docstringの文)。 @param words 字句。 @return 1つ以上あり、全て文字列ならtrue。 */
    static bool isStringStatement(Words words) {
        if (words.isEmpty()) {
            return false;
        }
        for (const Word& word : words) {
            if (word.type != TokenType::String) {
                return false;
            }
        }
        return true;
    }

    /** @brief 文字列だけの文の値を、docstringとして整えて返す。 @param words 字句。 @return docstring。 */
    QString docstringOf(Words words) const {
        QString value;
        for (const Word& word : words) {
            value += stringLiteralValue(text(word));  // stringLiteralsValueと同じく、隣り合う文字列をつなげる。
        }
        return cleanDocstring(value);
    }

    /** @brief ``def``・``class``の中身の最初の文がdocstringなら、その値を返す。
     * @param inlineBody 見出しと同じ行の``:``の後ろの字句。
     * @param index 中身の最初の論理行の位置。
     * @param indent 見出しのインデント。
     * @return docstring。無ければ空。
     */
    QString bodyDocstring(Words inlineBody, int index, int indent) const {
        if (!inlineBody.isEmpty()) {
            return isStringStatement(inlineBody) ? docstringOf(inlineBody) : QString();
        }
        if (index < lines_.size() && lines_[index].indent > indent && isStringStatement(lineWords(lines_[index]))) {
            return docstringOf(lineWords(lines_[index]));
        }
        return QString();
    }

    /** @brief ``class Name(A, pkg.B, metaclass=M):``の見出しから、親クラスの式を取り出す。
     * @param words ``class``から``:``の前までの字句。
     * @return 親クラスの式(``A``・``pkg.B``)。キーワード引数(``metaclass=``など)は含めない。
     */
    QStringList classBases(Words words) const {
        QStringList bases;
        if (words.size() < 4 || !isOperator(words[2], "(")) {
            return bases;
        }
        Words inside = words.mid(3);
        if (!inside.isEmpty() && isOperator(inside.last(), ")")) {
            inside.removeLast();
        }
        for (const Words& part : splitTopLevel(inside, ",")) {
            QString dotted;
            bool plain = !part.isEmpty();
            for (int i = 0; i < part.size() && plain; ++i) {
                const bool name = i % 2 == 0 && part[i].type == TokenType::Name;
                const bool dot = i % 2 == 1 && isOperator(part[i], ".");
                plain = name || dot;
                appendText(dotted, part[i]);
            }
            if (plain && !dotted.endsWith('.')) {
                bases.append(dotted);
            }
        }
        return bases;
    }

    /** @brief ``a.b.c``の形の名前を読む。
     * @param words 字句。
     * @param index 読み始める位置。読み終えた次の位置に進める。
     * @return 読んだ名前。名前が無ければ空。
     */
    QString readDottedName(Words words, int* index) const {
        QString name;
        while (*index < words.size() && words[*index].type == TokenType::Name) {
            appendText(name, words[*index]);
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
    void readImport(Words words, SymbolTable& table) const {
        for (const Words& part : splitTopLevel(words, ",")) {
            int index = 0;
            const QString dotted = readDottedName(part, &index);
            if (dotted.isEmpty()) {
                continue;
            }
            if (index + 1 < part.size() && isName(part[index], "as") && part[index + 1].type == TokenType::Name) {
                // import a.b as c → c は a.b を指す。
                table.insert(text(part[index + 1]), Symbol::module(dotted));
            } else {
                // import a.b → 使える名前は a で、a を指す。
                const QString top = dotted.section('.', 0, 0);
                table.insert(top, Symbol::module(top));
            }
        }
    }

    /** @brief ``from X import Y as Z``を読む。 @param words ``from``の後ろの字句。 @param table 追加先。 */
    void readFromImport(Words words, SymbolTable& table) const {
        int index = 0;
        int level = 0;  // 先頭の点の数(相対importの段数)。
        while (index < words.size() && (isOperator(words[index], ".") || isOperator(words[index], "..."))) {
            level += words[index].end - words[index].start;
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
            QStringList parts = moduleName_.split('.');
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
            const QString name = text(part[0]);
            QString alias = name;
            if (part.size() >= 3 && isName(part[1], "as") && part[2].type == TokenType::Name) {
                alias = text(part[2]);
            }
            if (level > 0 && module.isEmpty()) {
                // from . import nodes → 親パッケージの中のモジュール nodes を指す。
                table.insert(alias, Symbol::module(parent + "." + name));
            } else {
                table.insert(alias, Symbol::import(parent, name));
            }
        }
    }

    /** @brief ``def name(a, *args, b=1, **kw)``から、補完に出す説明``name(a, *args, b, **kw)``を作る。
     * @param words ``def``の後ろの字句(名前から)。
     * @param name 関数名を入れる。
     * @return 説明。関数の形でなければ空。
     */
    QString functionDetail(Words words, QString* name) const {
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
        *name = text(words[0]);
        QStringList arguments;
        int parameterStart = open + 1;  // 今の引数の最初の字句の位置。
        int depth = 0;
        int lambdas = 0;  // 既定値の中のlambdaの数(lambdaの引数の , で区切らないため)。
        // 1つの引数の字句から、名前を取り出して追加する。
        auto finish = [this, &arguments](Words part) {
            if (part.isEmpty()) {
                return;
            }
            if (part[0].type == TokenType::Name) {
                arguments.append(text(part[0]));
            } else if ((isOperator(part[0], "*") || isOperator(part[0], "**")) && part.size() >= 2
                       && part[1].type == TokenType::Name) {
                arguments.append(text(part[0]) + text(part[1]));
            }
            // 単独の * と / は区切りの印なので出さない。
        };
        for (int i = open + 1; i < words.size(); ++i) {
            const Word& word = words[i];
            if (depth == 0 && isOperator(word, ")")) {
                finish(words.mid(parameterStart, i - parameterStart));
                return *name + "(" + arguments.join(", ") + ")";
            }
            if (depth == 0 && isName(word, "lambda")) {
                ++lambdas;
            } else if (depth == 0 && lambdas > 0 && isOperator(word, ":")) {
                --lambdas;
            } else if (depth == 0 && lambdas == 0 && isOperator(word, ",")) {
                finish(words.mid(parameterStart, i - parameterStart));
                parameterStart = i + 1;
                continue;
            }
            depth = qMax(0, depth + bracketDelta(word));
        }
        // 閉じ括弧が無い(書きかけ)場合も、読めた分の引数で説明を作る。
        finish(words.mid(parameterStart));
        return *name + "(" + arguments.join(", ") + ")";
    }

    /** @brief 代入(``a = b = 1``・``a: int = 1``・``a: int``)の左辺の名前を追加する。
     * @param words 文の字句。
     * @param table 追加先。
     */
    void readAssignment(Words words, SymbolTable& table) const {
        const WordsList parts = splitTopLevel(words, "=");
        if (parts.size() == 1) {
            // = が無い: 注釈だけの宣言 a: int。
            if (words.size() >= 2 && isPlainName(words[0]) && isOperator(words[1], ":")) {
                table.insert(text(words[0]), Symbol());
            }
            return;
        }
        // 最後の = の右側は値なので、それより前が代入先。単独の名前だけを宣言として扱う(a.b や a, b は対象外)。
        for (int i = 0; i + 1 < parts.size(); ++i) {
            const Words& target = parts[i];
            if (target.size() == 1 && isPlainName(target[0])) {
                table.insert(text(target[0]), Symbol());
            } else if (i == 0 && target.size() >= 2 && isPlainName(target[0]) && isOperator(target[1], ":")) {
                table.insert(text(target[0]), Symbol());
            }
        }
    }

    /** @brief 1つの単純な文(複合文でない文)を読む。 @param words 文の字句。 @param table 追加先。 */
    void readSimpleStatement(Words words, SymbolTable& table) const {
        if (words.isEmpty()) {
            return;
        }
        if (isName(words[0], "import")) {
            readImport(words.mid(1), table);
        } else if (isName(words[0], "from")) {
            readFromImport(words.mid(1), table);
        } else if (words[0].type == TokenType::Name && isKeyword(view(words[0]), ScriptLanguage::Python)) {
            // return・pass・global などは宣言ではない。
        } else if (words[0].type == TokenType::Name) {
            readAssignment(words, table);
        }
    }

    /** @brief ``;``で区切られた単純な文を順に読む。 @param words 字句。 @param table 追加先。 */
    void readSimpleStatements(Words words, SymbolTable& table) const {
        for (const Words& statement : splitTopLevel(words, ";")) {
            readSimpleStatement(statement, table);
        }
    }

    /** @brief ``if TYPE_CHECKING:``または``if typing.TYPE_CHECKING:``の見出しか。 @param header ``:``より前の字句。 @return 該当すればtrue。 */
    bool isTypeCheckingHeader(Words header) const {
        if (header.size() == 2) {
            return isName(header[0], "if") && isName(header[1], "TYPE_CHECKING");
        }
        return header.size() == 4 && isName(header[0], "if") && isName(header[1], "typing")
               && isOperator(header[2], ".") && isName(header[3], "TYPE_CHECKING");
    }

    /** @brief 複合文の中身(見出しの``:``の後ろと、次の行からの深いブロック)を読む。
     * @param inlineBody 見出しと同じ行の``:``の後ろの字句。
     * @param index 次に読む論理行。中身を読んだ分だけ進める。
     * @param indent 見出しのインデント。
     * @return 中身の宣言。
     */
    SymbolTable readBody(Words inlineBody, int* index, int indent) const {
        SymbolTable body;
        readSimpleStatements(inlineBody, body);
        if (*index < lines_.size() && lines_[*index].indent > indent) {
            const SymbolTable block = readBlock(index, lines_[*index].indent);
            for (auto it = block.begin(); it != block.end(); ++it) {
                body.insert(it.key(), it.value());
            }
        }
        return body;
    }

    /** @brief 同じインデントの論理行を順に読む。
     * @param index 読み始める論理行。読み終えた次の位置に進める。
     * @param indent このブロックのインデント。これより浅い行でブロックは終わる。
     * @return ブロックの宣言。
     */
    SymbolTable readBlock(int* index, int indent) const {
        SymbolTable table;
        while (*index < lines_.size()) {
            const LogicalLine& line = lines_[*index];
            if (line.indent < indent) {
                break;  // ブロックの終わり。
            }
            ++*index;
            if (line.indent > indent) {
                continue;  // 読まない複合文(関数など)の中身。字句の文字列は作らない。
            }
            const Words words = lineWords(line);
            const Word& first = words[0];
            const bool asyncDef = isName(first, "async") && words.size() > 1 && isName(words[1], "def");
            if (isName(first, "def") || asyncDef) {
                QString name;
                const QString detail = functionDetail(words.mid(asyncDef ? 2 : 1), &name);
                if (!name.isEmpty()) {
                    const int colon = headerColon(words);
                    Symbol symbol;
                    symbol.type = SymbolType::Function;
                    symbol.detail = detail;
                    symbol.signature = joinWords(colon >= 0 ? words.mid(0, colon) : words);
                    symbol.doc = bodyDocstring(colon >= 0 ? words.mid(colon + 1) : Words(), *index, indent);
                    table.insert(name, symbol);
                }
                continue;  // 関数の中身は、次からの深い行として読み飛ばされる。
            }
            if (isName(first, "class")) {
                if (words.size() < 2 || !isPlainName(words[1])) {
                    continue;
                }
                const int colon = headerColon(words);
                const Words header = colon >= 0 ? words.mid(0, colon) : words;
                const Words inlineBody = colon >= 0 ? words.mid(colon + 1) : Words();
                const QString name = text(words[1]);
                Symbol symbol;
                symbol.type = SymbolType::Class;
                symbol.detail = "class " + name;
                symbol.signature = joinWords(header);
                symbol.bases = classBases(header);
                symbol.doc = bodyDocstring(inlineBody, *index, indent);
                symbol.members = std::make_shared<SymbolTable>(readBody(inlineBody, index, indent));
                table.insert(name, symbol);
                continue;
            }
            if (isName(first, "if")) {
                const int colon = headerColon(words);
                if (colon >= 0 && isTypeCheckingHeader(words.mid(0, colon))) {
                    // 型のためだけのimportも、実行せずに読む。
                    const SymbolTable body = readBody(words.mid(colon + 1), index, indent);
                    for (auto it = body.begin(); it != body.end(); ++it) {
                        table.insert(it.key(), it.value());
                    }
                }
                continue;
            }
            if (isOperator(first, "@")) {
                continue;  // デコレーター。次の行のdef・classを読む。
            }
            if (first.type == TokenType::Name && isKeyword(view(first), ScriptLanguage::Python)
                && !isName(first, "import") && !isName(first, "from")) {
                continue;  // for・while・try・with などの複合文と、return などの文。
            }
            readSimpleStatements(words, table);
        }
        return table;
    }

    QStringView source_;          ///< 本文。
    const QString& moduleName_;   ///< 相対importの基準。
    QVector<Word> words_;         ///< 全ての論理行の字句(コメントを除く)。論理行はこの中の範囲を指す。
    QVector<LogicalLine> lines_;  ///< 論理行。
};

}  // namespace

DeclarationResult extractPythonDeclarations(const QString& source, const QString& moduleName) {
    return DeclarationReader(source, moduleName).read();
}

}  // namespace hedit
