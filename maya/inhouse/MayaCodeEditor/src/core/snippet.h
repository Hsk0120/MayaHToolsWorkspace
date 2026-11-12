/** @file snippet.h
 * @brief LSPスニペットを実行せず展開し、入力箇所と同一番号の参照を保持する。
 */
#pragma once
#include <QMap>
#include <QRegularExpression>
#include <QSet>
#include <QString>
#include <QVector>
#include <algorithm>

namespace mce {
/** @brief UTF-16入力範囲。mirrorは同じ番号の参照、0は終了位置。 */
struct SnippetStop { int number; int start; int length; bool mirror = false; QString pattern, format, options; };
/** @brief スニペットの本文と入力箇所。 */
struct SnippetExpansion { QString text; QVector<SnippetStop> stops; };

/** @brief 対応しない置換命令を確定前に拒否する。
 * @param format 置換書式。 @return 対応する構文だけか。
 */
inline bool validSnippetFormat(const QString& format) {
    for (int i = 0; i < format.size();) {
        const QChar ch = format[i++];
        if (ch == '\\') { if (i < format.size()) ++i; continue; }
        if (ch != '$') continue;
        const bool brace = i < format.size() && format[i] == '{';
        if (brace) ++i;
        const int start = i;
        while (i < format.size() && format[i].isDigit()) ++i;
        if (start == i) return false;
        if (brace) {
            const int end = format.indexOf('}', i);
            if (end < 0) return false;
            const auto operation = format.mid(i, end - i);
            if (!operation.isEmpty() && operation != ":/upcase" && operation != ":/downcase" && operation != ":/capitalize"
                && !operation.startsWith(":+") && !operation.startsWith(":-")
                && !(operation.startsWith(":?") && operation.indexOf(':', 2) >= 0)) return false;
            i = end + 1;
        }
    }
    return true;
}

/** @brief キャプチャの置換書式を展開する。任意コードは評価しない。
 * @param format 検証済みの書式。 @param match 一致したキャプチャ。 @return 置換する文字列。
 */
inline QString snippetFormat(const QString& format, const QRegularExpressionMatch& match) {
    QString out;
    for (int i = 0; i < format.size();) {
        QChar c = format[i++];
        if (c == '\\' && i < format.size()) { out += format[i++]; continue; }
        if (c != '$') { out += c; continue; }
        const bool brace = i < format.size() && format[i] == '{';
        if (brace) ++i;
        int start = i;
        while (i < format.size() && format[i].isDigit()) ++i;
        QString value = match.captured(format.mid(start, i - start).toInt());
        if (brace) {
            const int end = format.indexOf('}', i);
            if (end < 0) return out;
            const QString operation = format.mid(i, end - i);
            if (operation == ":/upcase") value = value.toUpper();
            else if (operation == ":/downcase") value = value.toLower();
            else if (operation == ":/capitalize" && !value.isEmpty()) value[0] = value[0].toUpper();
            else if (operation.startsWith(":+")) value = value.isEmpty() ? QString() : operation.mid(2);
            else if (operation.startsWith(":-")) { if (value.isEmpty()) value = operation.mid(2); }
            else if (operation.startsWith(":?")) {
                const int colon = operation.indexOf(':', 2);
                value = value.isEmpty() ? operation.mid(colon + 1) : operation.mid(2, colon - 2);
            }
            i = end + 1;
        }
        out += value;
    }
    return out;
}

/** @brief 参照変換を適用する。入力上限を超える場合は元の値を保持する。
 * @param value 入力欄の本文。 @param stop 変換を持つ参照欄。 @return 変換後の本文。
 */
inline QString transformSnippet(const QString& value, const SnippetStop& stop) {
    if (stop.pattern.isEmpty() || value.size() > 4096) return value;
    QRegularExpression expression(stop.pattern, stop.options.contains('i') ? QRegularExpression::CaseInsensitiveOption : QRegularExpression::NoPatternOption);
    if (!expression.isValid()) return value;
    QString out;
    int last = 0;
    auto matches = expression.globalMatch(value);
    while (matches.hasNext()) {
        const auto match = matches.next();
        out += value.mid(last, match.capturedStart() - last) + snippetFormat(stop.format, match);
        last = match.capturedEnd();
        if (!stop.options.contains('g')) break;
    }
    return out + value.mid(last);
}

/** @brief 深さと本文量を制限するスニペット構文解析。 */
class SnippetParser {
public:
    /** @brief 呼出元の文書変数だけを参照する。
     * @param source 解析中だけ借用するスニペット。 @param variables 同期間借用する文書変数。
     */
    SnippetParser(const QString& source, const QMap<QString, QString>& variables) : source_(source), variables_(variables) {}
    /** @brief 全体を展開し、同じ番号の参照を同期可能な範囲へ変換する。
     * @param result 成功時だけ更新する出力。 @return 構文が妥当か。
     */
    bool expand(SnippetExpansion* result) {
        if (!result || source_.size() > 65536) return false;
        static const QRegularExpression definitions("(?<!\\\\)\\$\\{([0-9]+)(?=[:|])");
        auto matches = definitions.globalMatch(source_);
        while (matches.hasNext()) definitions_.insert(matches.next().captured(1).toInt());
        if (!parse(false, 0)) return false;
        QMap<int, QString> values;
        for (const auto& stop : out_.stops) if (!stop.mirror) values.insert(stop.number, out_.text.mid(stop.start, stop.length));
        for (int i = out_.stops.size() - 1; i >= 0; --i) {
            auto& stop = out_.stops[i];
            if (!stop.mirror) continue;
            const QString value = transformSnippet(values.value(stop.number), stop);
            const int delta = value.size() - stop.length;
            out_.text.replace(stop.start, stop.length, value);
            for (int j = 0; j < out_.stops.size(); ++j) if (j != i) {
                auto& other = out_.stops[j];
                if (other.start >= stop.start + stop.length) other.start += delta;
                else if (other.start <= stop.start && other.start + other.length >= stop.start + stop.length) other.length += delta;
            }
            stop.length = value.size();
        }
        std::stable_sort(out_.stops.begin(), out_.stops.end(), [](const SnippetStop& a, const SnippetStop& b) {
            if (a.number != b.number) return b.number == 0 || (a.number != 0 && a.number < b.number);
            return !a.mirror && b.mirror;
        });
        if (!numbers_.contains(0)) out_.stops.append({0, int(out_.text.size()), 0});
        *result = out_; return true;
    }
private:
    /** @brief 区切りまでを読み、入れ子内のスラッシュを保持する。
     * @param value 読み取った本文の出力。 @param format 置換書式の入れ子を扱うか。 @return 区切りが見つかったか。
     */
    bool segment(QString* value, bool format) {
        int braces = 0;
        while (at_ < source_.size()) {
            const QChar c = source_[at_++];
            if (c == '\\' && at_ < source_.size()) {
                const QChar next = source_[at_++];
                if (next != '/') *value += '\\';
                *value += next;
            } else if (c == '/' && braces == 0) return true;
            else { *value += c; if (format && c == '{') ++braces; if (format && c == '}') --braces; }
        }
        return false;
    }
    /** @brief 入れ子の既定値を含む本文を解析する。
     * @param nested 閉じ括弧で終了するか。 @param depth 再帰の深さ。 @return 対応範囲の妥当な構文か。
     */
    bool parse(bool nested, int depth) {
        if (depth > 16) return false;
        while (at_ < source_.size()) {
            QChar c = source_[at_++];
            if (nested && c == '}') return true;
            if (c == '\\') {
                if (at_ < source_.size() && QString("\\$}").contains(source_[at_])) c = source_[at_++];
                out_.text += c; continue;
            }
            if (c != '$') { out_.text += c; continue; }
            const bool brace = at_ < source_.size() && source_[at_] == '{';
            if (brace) ++at_;
            const int begin = at_;
            const bool numeric = at_ < source_.size() && source_[at_].isDigit();
            while (at_ < source_.size() && (numeric ? source_[at_].isDigit() : source_[at_].isLetterOrNumber() || source_[at_] == '_')) ++at_;
            if (begin == at_) return false;
            const QString key = source_.mid(begin, at_ - begin);
            bool valid = true;
            const int number = numeric ? key.toInt(&valid) : -1;
            if (!valid) return false;
            SnippetStop stop{number, int(out_.text.size()), 0};
            const int slot = out_.stops.size();
            if (numeric) {
                const bool defining = brace && at_ < source_.size() && (source_[at_] == ':' || source_[at_] == '|');
                stop.mirror = numbers_.contains(number) || (!defining && definitions_.contains(number));
                if (!stop.mirror) numbers_.insert(number);
                out_.stops.append(stop);
            }
            if (brace && at_ < source_.size() && source_[at_] == ':') {
                ++at_;
                if (!parse(true, depth + 1)) return false;
                if (!numeric && variables_.contains(key)) {
                    if (out_.stops.size() != slot) return false;
                    out_.text.replace(stop.start, out_.text.size() - stop.start, variables_.value(key));
                }
            } else if (brace && at_ < source_.size() && source_[at_] == '|') {
                ++at_; bool first = true, closed = false;
                while (at_ < source_.size()) {
                    c = source_[at_++];
                    if (c == '\\' && at_ < source_.size()) c = source_[at_++];
                    else if (c == ',') { first = false; continue; }
                    else if (c == '|') { closed = at_ < source_.size() && source_[at_++] == '}'; break; }
                    if (first) out_.text += c;
                }
                if (!closed) return false;
            } else if (brace && at_ < source_.size() && source_[at_] == '/') {
                ++at_; stop.mirror = true;
                if (!segment(&stop.pattern, false) || !segment(&stop.format, true)) return false;
                const int end = source_.indexOf('}', at_);
                if (end < 0) return false;
                stop.options = source_.mid(at_, end - at_); at_ = end + 1;
                if (!QRegularExpression(stop.pattern).isValid() || stop.pattern.size() > 512 || !validSnippetFormat(stop.format)) return false;
                for (QChar option : stop.options) if (option != 'g' && option != 'i') return false;
                if (!numeric) out_.text += transformSnippet(variables_.value(key), stop);
            } else {
                if (brace && (at_ >= source_.size() || source_[at_++] != '}')) return false;
                if (!numeric) out_.text += variables_.value(key, key);
            }
            stop.length = out_.text.size() - stop.start;
            if (numeric) out_.stops[slot] = stop;
        }
        return !nested;
    }
    const QString& source_; ///< 呼出中だけ参照する入力。
    const QMap<QString, QString>& variables_; ///< 呼出元の文書変数。
    int at_ = 0; ///< 読み取り位置。
    QSet<int> numbers_; ///< 入力箇所の重複を避ける集合。
    QSet<int> definitions_; ///< 先行する$1も後続の既定値を参照できるようにする。
    SnippetExpansion out_; ///< 構文が妥当な場合だけ渡す結果。
};
/** @brief スニペットを展開する。不正構文ではresultを変更しない。
 * @param source LSPのスニペット。 @param result 展開先。 @param variables 文書由来の変数。
 * @return 対応する構文を展開できたか。
 */
inline bool expandSnippet(const QString& source, SnippetExpansion* result, const QMap<QString, QString>& variables = {}) {
    return SnippetParser(source, variables).expand(result);
}
}  // namespace mce
