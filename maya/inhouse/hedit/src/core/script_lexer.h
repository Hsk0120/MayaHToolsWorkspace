/** @file script_lexer.h
 * @brief Python・MELの本文を、名前・数値・文字列・コメント・記号の「字句(トークン)」に分ける。
 * @details 構文強調(editor/syntax_highlighter.cpp)と、宣言の抽出(core/python_declarations.cpp)が共通で使う。
 * 1行ずつ処理し、行をまたぐもの(Pythonの三重引用符の文字列、MELのブロックコメント)は「状態」で次の行へ引き継ぐ。
 * この状態の値は、QSyntaxHighlighterのblock state(行ごとに保存される整数)にそのまま使える。
 * Mayaにも画面にも依存しない。
 */
#pragma once
#include <QList>
#include <QString>

namespace hedit {

/** @brief 本文の言語。 */
enum class ScriptLanguage {
    Python,  ///< Python。
    Mel,     ///< MEL。
};

/** @brief 字句の種類。 */
enum class TokenType {
    Name,      ///< 名前(変数・関数・予約語を含む)。予約語かどうかはisKeyword()で調べる。
    Variable,  ///< MELの変数(``$name``)。
    Number,    ///< 数値。
    String,    ///< 文字列(引用符と接頭辞を含む)。
    Comment,   ///< コメント。
    Operator,  ///< 記号(``(``・``=``・``==``・``->``など)。
};

/** @brief 1つの字句。位置は、その行の中のUTF-16の文字位置。 */
struct Token {
    TokenType type = TokenType::Name;  ///< 種類。
    int start = 0;                     ///< 行の中の開始位置。
    int length = 0;                    ///< 長さ。
};

/** @brief 行をまたぐ状態。0は「何も続いていない」。 */
enum LexerState : int {
    kLexerNormal = 0,                ///< 通常。
    kPythonTripleSingle = 1,         ///< ``'''``の文字列の途中。
    kPythonTripleDouble = 2,         ///< ``"""``の文字列の途中。
    kPythonRawTripleSingle = 3,      ///< ``r'''``の文字列の途中(``\``を特別扱いしない)。
    kPythonRawTripleDouble = 4,      ///< ``r"""``の文字列の途中。
    kMelBlockComment = 5,            ///< MELのブロックコメント(/* から */ まで)の途中。
};

/** @brief 1行を字句に分ける。
 * @param line 1行の文字列(改行を含まない)。
 * @param language 言語。
 * @param state 前の行から引き継いだ状態(最初の行は0。QSyntaxHighlighterの-1も0として扱う)。
 * @param endState この行の終わりの状態を入れる。nullptrなら入れない。
 * @return 字句の一覧(空白は含まない)。
 */
QList<Token> tokenizeLine(const QString& line, ScriptLanguage language, int state, int* endState);

/** @brief 予約語か。
 * @param word 名前。
 * @param language 言語。
 * @return Pythonの``def``・``if``など、MELの``proc``・``string``などならtrue。
 * @note PythonのTrue・False・Noneは予約語ではなく、isConstant()で扱う。
 */
bool isKeyword(const QString& word, ScriptLanguage language);

/** @brief 定数の名前か(Pythonの``True``・``False``・``None``・``self``、MELの``true``など)。
 * @param word 名前。
 * @param language 言語。
 * @return 定数ならtrue。
 */
bool isConstant(const QString& word, ScriptLanguage language);

/** @brief Pythonの識別子の先頭に使える文字か。 @param character 文字。 @return 文字か``_``ならtrue。 */
bool isNameStart(QChar character);

/** @brief Pythonの識別子の2文字目以降に使える文字か。 @param character 文字。 @return 文字・数字・``_``ならtrue。 */
bool isNamePart(QChar character);

}  // namespace hedit
