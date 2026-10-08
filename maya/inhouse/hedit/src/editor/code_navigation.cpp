/** @file code_navigation.cpp
 * @brief 括弧の対応・同じ名前の位置・選択範囲の拡大の実装。
 */
#include "editor/code_navigation.h"
#include "core/code_outline.h"
#include <QTextBlock>
#include <QTextDocument>
#include <QVector>

namespace hedit {
namespace {

/// 括弧の対応を探す行数の上限(大きな文書で止まらないため)。
constexpr int kBracketSearchBlocks = 3000;

/// 同じ名前を探す文書の上限(文字数)。
constexpr int kOccurrenceDocumentLimit = 500000;

/** @brief 括弧の種類。 @param c 文字。 @return 開き括弧なら1、閉じ括弧なら-1、それ以外は0。 */
int bracketKind(QChar c) {
    if (c == '(' || c == '[' || c == '{') {
        return 1;
    }
    if (c == ')' || c == ']' || c == '}') {
        return -1;
    }
    return 0;
}

/** @brief 対になる括弧。 @param c 括弧。 @return 対の括弧。 */
QChar partner(QChar c) {
    switch (c.unicode()) {
    case '(': return ')';
    case ')': return '(';
    case '[': return ']';
    case ']': return '[';
    case '{': return '}';
    default: return '{';
    }
}

/// 文書の中の括弧の字句(位置と括弧の文字)。
using BracketToken = BracketCache::Bracket;

/// 括弧の控えに入れる行の数の上限(上限を超えたら、それ以上は控えずに毎回読む)。
constexpr int kBracketCacheBlocks = 20000;

/** @brief 行の中の括弧の字句を返す(文字列・コメントの中は含まない)。
 * @param block 行。
 * @param language 言語。
 * @param cache 行ごとの括弧の控え。nullptrなら控えを使わない。
 * @return 括弧の一覧(行の中の順)。
 * @details 控えがあれば、同じ文書の版・同じ言語の間は、一度読んだ行を字句解析し直さない。
 */
QVector<BracketToken> blockBrackets(const QTextBlock& block, ScriptLanguage language, BracketCache* cache = nullptr) {
    int number = -1;
    if (cache) {
        const int revision = block.document()->revision();
        if (cache->revision != revision || cache->language != language) {
            cache->blocks.clear();  // 本文か言語が変わった: 控えを捨てる。
            cache->revision = revision;
            cache->language = language;
        }
        number = block.blockNumber();
        const auto found = cache->blocks.constFind(number);
        if (found != cache->blocks.constEnd()) {
            return *found;
        }
    }
    QVector<BracketToken> brackets;
    const QString text = block.text();
    for (const Token& token : blockTokens(block, language)) {
        if (token.type == TokenType::Operator && token.length == 1 && bracketKind(text[token.start]) != 0) {
            brackets.append({block.position() + token.start, text[token.start]});
        }
    }
    if (cache && cache->blocks.size() < kBracketCacheBlocks) {
        cache->blocks.insert(number, brackets);
    }
    return brackets;
}

/** @brief 開き括弧に対応する閉じ括弧を、後ろへ探す。
 * @param document 文書。 @param language 言語。 @param open 開き括弧の位置。 @param bracket 開き括弧。
 * @param cache 行ごとの括弧の控え。nullptrなら控えを使わない。
 * @return 閉じ括弧の位置。無ければ-1。
 */
int findForward(const QTextDocument* document, ScriptLanguage language, int open, QChar bracket,
                BracketCache* cache = nullptr) {
    const QChar closing = partner(bracket);
    int depth = 0;
    QTextBlock block = document->findBlock(open);
    for (int count = 0; block.isValid() && count < kBracketSearchBlocks; ++count, block = block.next()) {
        for (const BracketToken& token : blockBrackets(block, language, cache)) {
            if (token.position <= open) {
                continue;
            }
            if (token.bracket == bracket) {
                ++depth;
            } else if (token.bracket == closing) {
                if (depth == 0) {
                    return token.position;
                }
                --depth;
            }
        }
    }
    return -1;
}

/** @brief 閉じ括弧に対応する開き括弧を、前へ探す。
 * @param document 文書。 @param language 言語。 @param close 閉じ括弧の位置。 @param bracket 閉じ括弧。
 * @param cache 行ごとの括弧の控え。nullptrなら控えを使わない。
 * @return 開き括弧の位置。無ければ-1。
 */
int findBackward(const QTextDocument* document, ScriptLanguage language, int close, QChar bracket,
                 BracketCache* cache = nullptr) {
    const QChar opening = partner(bracket);
    int depth = 0;
    QTextBlock block = document->findBlock(close);
    for (int count = 0; block.isValid() && count < kBracketSearchBlocks; ++count, block = block.previous()) {
        const QVector<BracketToken> brackets = blockBrackets(block, language, cache);
        for (int i = brackets.size() - 1; i >= 0; --i) {
            const BracketToken& token = brackets[i];
            if (token.position >= close) {
                continue;
            }
            if (token.bracket == bracket) {
                ++depth;
            } else if (token.bracket == opening) {
                if (depth == 0) {
                    return token.position;
                }
                --depth;
            }
        }
    }
    return -1;
}

/** @brief 位置の字句を返す。 @param block 行。 @param language 言語。 @param column 行の中の位置。
 * @param found 字句を入れる。 @return 位置を含む字句があればtrue(字句の終わりの位置も含む)。
 */
bool tokenAt(const QTextBlock& block, ScriptLanguage language, int column, Token* found) {
    for (const Token& token : blockTokens(block, language)) {
        if (column >= token.start && column <= token.start + token.length) {
            *found = token;
            if (token.type != TokenType::Operator || column < token.start + token.length) {
                return true;  // 記号の直後より、名前・文字列を優先する(``a.b``の``.``の直前など)。
            }
        }
    }
    return found->length > 0;
}

/** @brief 範囲の候補。 */
struct Range {
    int start = 0;  ///< 先頭。
    int end = 0;    ///< 終わり。
};

}  // namespace

QVector<Token> blockTokens(const QTextBlock& block, ScriptLanguage language) {
    const QTextBlock previous = block.previous();
    const int state = qMax(0, previous.isValid() ? previous.userState() : 0);
    return tokenizeLine(block.text(), language, state, nullptr);
}

bool isInsideStringOrComment(const QTextDocument* document, ScriptLanguage language, int position) {
    const QTextBlock block = document->findBlock(position);
    if (!block.isValid()) {
        return false;
    }
    const int column = position - block.position();
    const QString text = block.text();
    for (const Token& token : blockTokens(block, language)) {
        if (token.type == TokenType::Comment && column > token.start) {
            return true;
        }
        if (token.type != TokenType::String || column <= token.start || column > token.start + token.length) {
            continue;
        }
        if (column < token.start + token.length) {
            return true;
        }
        // 字句の終わりの位置: 閉じていない文字列(入力中)なら中。
        const QString value = text.mid(token.start, token.length);
        int prefix = 0;
        while (prefix < value.size() && value[prefix].isLetter()) {
            ++prefix;
        }
        if (prefix >= value.size()) {
            continue;
        }
        const QChar quote = value[prefix];
        const bool triple = value.mid(prefix, 3) == QString(3, quote);
        const int quoteLength = triple ? 3 : 1;
        const bool closed = value.size() >= prefix + quoteLength * 2 && value.endsWith(QString(quoteLength, quote))
                            && !(value.size() >= 2 && value[value.size() - 2] == '\\' && !triple);
        if (!closed) {
            return true;
        }
    }
    return false;
}

bool findMatchingBracket(const QTextDocument* document, ScriptLanguage language, int position, int* first,
                         int* second, BracketCache* cache) {
    for (const int candidate : {position, position - 1}) {
        if (candidate < 0 || candidate >= document->characterCount() - 1) {
            continue;
        }
        const QTextBlock block = document->findBlock(candidate);
        for (const BracketToken& token : blockBrackets(block, language, cache)) {
            if (token.position != candidate) {
                continue;
            }
            const int match = bracketKind(token.bracket) > 0
                                  ? findForward(document, language, candidate, token.bracket, cache)
                                  : findBackward(document, language, candidate, token.bracket, cache);
            if (match >= 0) {
                *first = candidate;
                *second = match;
                return true;
            }
        }
    }
    return false;
}

QList<int> nameOccurrences(const QTextDocument* document, ScriptLanguage language, const QString& name, int limit) {
    QList<int> positions;
    if (name.isEmpty() || document->characterCount() > kOccurrenceDocumentLimit) {
        return positions;
    }
    for (QTextBlock block = document->begin(); block.isValid() && positions.size() < limit; block = block.next()) {
        const QString text = block.text();
        if (!text.contains(name)) {
            continue;
        }
        for (const Token& token : blockTokens(block, language)) {
            if ((token.type == TokenType::Name || token.type == TokenType::Variable) && token.length == name.size()
                && text.mid(token.start, token.length) == name) {
                positions.append(block.position() + token.start);
            }
        }
    }
    return positions;
}

bool expandedSelection(const QTextDocument* document, ScriptLanguage language, int start, int end, int* newStart,
                       int* newEnd) {
    QList<Range> candidates;
    const QTextBlock firstBlock = document->findBlock(start);
    const QTextBlock lastBlock = document->findBlock(end);
    if (!firstBlock.isValid()) {
        return false;
    }
    const QString text = firstBlock.text();
    const int column = start - firstBlock.position();

    // 1. 名前(a.b.c をまとめる)と文字列。
    Token token;
    if (tokenAt(firstBlock, language, column, &token)) {
        const int tokenStart = firstBlock.position() + token.start;
        const int tokenEnd = tokenStart + token.length;
        if (token.type == TokenType::Name || token.type == TokenType::Variable) {
            candidates.append({tokenStart, tokenEnd});
            int dottedStart = token.start;
            while (dottedStart > 1 && text[dottedStart - 1] == '.' && isNamePart(text[dottedStart - 2])) {
                dottedStart -= 2;
                while (dottedStart > 0 && isNamePart(text[dottedStart - 1])) {
                    --dottedStart;
                }
            }
            int dottedEnd = token.start + token.length;
            while (dottedEnd + 1 < text.size() && text[dottedEnd] == '.' && isNameStart(text[dottedEnd + 1])) {
                dottedEnd += 1;
                while (dottedEnd < text.size() && isNamePart(text[dottedEnd])) {
                    ++dottedEnd;
                }
            }
            candidates.append({firstBlock.position() + dottedStart, firstBlock.position() + dottedEnd});
        } else if (token.type == TokenType::String) {
            const QString value = text.mid(token.start, token.length);
            int prefix = 0;
            while (prefix < value.size() && value[prefix].isLetter()) {
                ++prefix;
            }
            const QChar quote = prefix < value.size() ? value[prefix] : QChar('"');
            const int quoteLength = value.mid(prefix, 3) == QString(3, quote) ? 3 : 1;
            const int innerStart = tokenStart + prefix + quoteLength;
            const int innerEnd = qMax(innerStart, tokenEnd - (value.endsWith(quote) ? quoteLength : 0));
            candidates.append({innerStart, innerEnd});
            candidates.append({tokenStart, tokenEnd});
        }
    }

    // 2. 囲んでいる括弧(内側から最大10段)。
    {
        QVector<QChar> pendingClosers;  // 前へ探す途中で見つけた閉じ括弧(その対の開き括弧は飛ばす)。
        int levels = 0;
        QTextBlock block = firstBlock;
        for (int count = 0; block.isValid() && count < kBracketSearchBlocks && levels < 10;
             ++count, block = block.previous()) {
            const QVector<BracketToken> brackets = blockBrackets(block, language);
            for (int i = brackets.size() - 1; i >= 0 && levels < 10; --i) {
                const BracketToken& bracket = brackets[i];
                if (bracket.position >= start) {
                    continue;
                }
                if (bracketKind(bracket.bracket) < 0) {
                    pendingClosers.append(bracket.bracket);
                    continue;
                }
                if (!pendingClosers.isEmpty()) {
                    pendingClosers.removeLast();
                    continue;
                }
                const int close = findForward(document, language, bracket.position, bracket.bracket);
                if (close >= end) {
                    candidates.append({bracket.position + 1, close});
                    candidates.append({bracket.position, close + 1});
                    ++levels;
                }
            }
        }
    }

    // 3. 行の中身と行全体(選択が複数行なら、その行全体)。
    {
        const QString firstText = firstBlock.text();
        int contentStart = 0;
        while (contentStart < firstText.size() && firstText[contentStart].isSpace()) {
            ++contentStart;
        }
        const int lineEnd = lastBlock.position() + lastBlock.length() - 1;
        candidates.append({firstBlock.position() + contentStart, lineEnd});
        candidates.append({firstBlock.position(), lineEnd});
    }

    // 4. インデントのブロックと、その見出しを含むブロック。
    {
        auto indentOf = [](const QTextBlock& block) { return lineIndentWidth(block.text()); };
        auto blank = [](const QTextBlock& block) { return block.text().trimmed().isEmpty(); };
        QTextBlock reference = firstBlock;
        while (reference.isValid() && blank(reference)) {
            reference = reference.next();
        }
        if (reference.isValid()) {
            const int indent = indentOf(reference);
            QTextBlock top = firstBlock;
            while (top.previous().isValid() && (blank(top.previous()) || indentOf(top.previous()) >= indent)) {
                top = top.previous();
            }
            while (top != firstBlock && blank(top)) {
                top = top.next();
            }
            QTextBlock bottom = lastBlock;
            while (bottom.next().isValid() && (blank(bottom.next()) || indentOf(bottom.next()) >= indent)) {
                bottom = bottom.next();
            }
            while (bottom != lastBlock && blank(bottom)) {
                bottom = bottom.previous();
            }
            const int blockEnd = bottom.position() + bottom.length() - 1;
            candidates.append({top.position(), blockEnd});
            if (indent > 0 && top.previous().isValid()) {
                QTextBlock header = top.previous();
                while (header.previous().isValid() && blank(header)) {
                    header = header.previous();
                }
                candidates.append({header.position(), blockEnd});
            }
        }
    }

    // 5. 文書全体。
    candidates.append({0, document->characterCount() - 1});

    // 今の選択を含み、それより大きい中で最も小さい範囲。
    int best = -1;
    for (int i = 0; i < candidates.size(); ++i) {
        const Range& range = candidates[i];
        if (range.start > start || range.end < end || (range.start == start && range.end == end)) {
            continue;
        }
        if (best < 0 || range.end - range.start < candidates[best].end - candidates[best].start) {
            best = i;
        }
    }
    if (best < 0) {
        return false;
    }
    *newStart = candidates[best].start;
    *newEnd = candidates[best].end;
    return true;
}

}  // namespace hedit
