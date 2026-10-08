/** @file text_search.h
 * @brief 検索・置換の一致箇所を求める処理。画面(editor/find_bar.cpp)から切り離してある。
 * @details 本文の文字列と検索条件だけを受け取り、一致の位置と置換後の文字列を返す。
 * 本文は変更しないため、Mayaも画面も無い状態でテストできる。
 */
#pragma once
#include <QList>
#include <QRegularExpressionMatch>
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 検索条件。検索バーのチェックボックスに対応する。 */
struct SearchOptions {
    QString text;            ///< 検索する文字列(正規表現モードではパターン)。
    bool matchCase = false;     ///< 大文字と小文字を区別する(``Aa``)。
    bool wholeWord = false;     ///< 単語全体だけに一致させる(``ab``)。
    bool regex = false;         ///< 正規表現として扱う(``.*``)。
    bool preserveCase = false;  ///< 置換後の文字列の大文字小文字を、一致した文字列に合わせる(置換欄の``AB``)。
    int rangeStart = -1;        ///< 選択範囲内で検索するときの範囲の先頭。-1なら全体(``≡``)。照合はこの位置から始める。
    int rangeEnd = -1;          ///< 選択範囲内で検索するときの範囲の末尾(この位置の文字は含まない)。
};

/** @brief 1つの一致箇所。位置はUTF-16の文字単位(QStringの添字と同じ)。 */
struct TextMatch {
    int start = 0;   ///< 一致の先頭位置。
    int length = 0;  ///< 一致の長さ。

    /** @brief 位置と長さが同じか。
     * @param other 比べる相手。
     * @return 同じならtrue。
     */
    bool operator==(const TextMatch& other) const { return start == other.start && length == other.length; }
};

}  // namespace hedit

// 整数2つの型。Qt5のQListでも、要素を1つずつ確保せずに配列へ直接入る(ポインター以下の大きさのため)。
Q_DECLARE_TYPEINFO(hedit::TextMatch, Q_MOVABLE_TYPE);

namespace hedit {

/** @brief 検索の結果。errorが空なら成功。 */
struct SearchResult {
    QList<TextMatch> matches;  ///< 一致箇所(先頭から順)。
    QStringList replacements;  ///< 置換を求めた場合だけ、matchesと同じ順で置換後の文字列。
    QString error;             ///< 失敗の理由(不正な正規表現など)。成功なら空。

    /** @brief 成功したか。 @return errorが空ならtrue。 */
    bool ok() const { return error.isEmpty(); }
};

/** @brief 本文から一致箇所を全て求める。本文は変更しない。
 * @param document 検索する本文。
 * @param options 検索条件。
 * @param replacementTemplate 置換の文字列。nullptrなら置換後の文字列は作らない。
 * @return 一致箇所と置換後の文字列。不正な正規表現・長さ0の一致・10万件を超える一致はerrorを設定する。
 */
SearchResult findMatches(const QString& document, const SearchOptions& options,
                         const QString* replacementTemplate = nullptr);

/** @brief 正規表現の置換文字列の``$1``〜``$99``・``$&``・``$$``を展開する(VS Codeと同じ記法)。
 * @param replacementTemplate 置換の文字列。
 * @param match 一致の情報(キャプチャーの中身を取り出す)。
 * @param captureCount 正規表現のキャプチャーの数。これを超える番号は``$番号``のまま残す。
 * @return 展開した文字列。
 */
QString expandReplacement(const QString& replacementTemplate, const QRegularExpressionMatch& match, int captureCount);

/** @brief 置換後の文字列の大文字小文字を、一致した文字列に合わせる(VS Codeの「Preserve Case」と同じ規則)。
 * @param replacement 置換後の文字列。
 * @param matched 一致した文字列。
 * @return 一致がすべて大文字なら大文字、すべて小文字なら小文字、先頭だけ大文字なら先頭を大文字にした文字列。
 * それ以外(英字を含まない等)はそのまま。
 */
QString preserveCase(const QString& replacement, const QString& matched);

}  // namespace hedit
