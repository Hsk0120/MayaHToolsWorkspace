/** @file script_lexer.h
 * @brief Python・MELの本文を、名前・数値・文字列・コメント・記号の「字句(トークン)」に分ける。
 * @details 構文強調(editor/syntax_highlighter.cpp)と、宣言の抽出(core/python_declarations.cpp)が共通で使う。
 * 1行ずつ処理し、行をまたぐもの(Pythonの三重引用符の文字列、MELのブロックコメント)は「状態」で次の行へ引き継ぐ。
 * この状態の値は、QSyntaxHighlighterのblock state(行ごとに保存される整数)にそのまま使える。
 * Mayaにも画面にも依存しない。
 */
#pragma once
#include <QString>
#include <QStringView>
#include <QVector>

namespace hedit {

/** @brief 本文の言語。 */
enum class ScriptLanguage {
    Python,  ///< Python。
    Mel,     ///< MEL。
};

/** @brief 言語の保存名(tabs.jsonやQtの動的プロパティ``language``に使う文字列)。
 * @param language 言語。
 * @return ``python``または``mel``。
 */
QString languageName(ScriptLanguage language);

/** @brief 保存名から言語を返す。 @param name ``mel``ならMEL、それ以外はPython。 @return 言語。 */
ScriptLanguage languageFromName(const QString& name);

/** @brief ファイルの拡張子から言語を返す。 @param path ファイルのパス。 @return ``.mel``ならMEL、それ以外はPython。 */
ScriptLanguage languageForPath(const QString& path);

/** @brief 字句の種類。 */
enum class TokenType {
    Name,      ///< 名前(変数・関数・予約語を含む)。予約語かどうかはisKeyword()で調べる。
    Variable,  ///< MELの変数(``$name``)。
    Number,    ///< 数値。
    String,    ///< 文字列(引用符と接頭辞を含む)。
    Comment,   ///< コメント。
    Operator,  ///< 記号(``(``・``=``・``==``・``->``など)。
};

/** @brief 1つの字句。位置は、その行の中のUTF-16の文字位置。
 * @note 整数だけの小さな型なので、直後でQ_PRIMITIVE_TYPEと宣言している(QVectorがmemcpyで移せる)。
 */
struct Token {
    TokenType type = TokenType::Name;  ///< 種類。
    int start = 0;                     ///< 行の中の開始位置。
    int length = 0;                    ///< 長さ。
};

}  // namespace hedit

// Q_DECLARE_TYPEINFOは名前空間の外に書く。QVector<Token>を使うどの箇所よりも前に宣言する必要がある。
Q_DECLARE_TYPEINFO(hedit::Token, Q_PRIMITIVE_TYPE);

namespace hedit {

/** @brief 行をまたぐ状態。0は「何も続いていない」。
 * @note 生文字列(接頭辞``r``)でも、``\``の直後の引用符では文字列は閉じない(Pythonの字句解析と同じ。
 * ``r"\""``は``\``と``"``の2文字の文字列)。生文字列かどうかは値(``\``を残すか)にだけ関わるので、
 * 閉じの判定では生文字列の状態(3・4)も通常の状態(1・2)と同じに扱う。値は保存済みのblock stateとの互換のため残す。
 */
enum LexerState : int {
    kLexerNormal = 0,                ///< 通常。
    kPythonTripleSingle = 1,         ///< ``'''``の文字列の途中。
    kPythonTripleDouble = 2,         ///< ``"""``の文字列の途中。
    kPythonRawTripleSingle = 3,      ///< ``r'''``の文字列の途中。
    kPythonRawTripleDouble = 4,      ///< ``r"""``の文字列の途中。
    kMelBlockComment = 5,            ///< MELのブロックコメント(/* から */ まで)の途中。
};

/** @brief 1行を字句に分ける。
 * @param line 1行の文字列(改行を含まない)。
 * @param language 言語。
 * @param state 前の行から引き継いだ状態(最初の行は0。QSyntaxHighlighterの-1も0として扱う)。
 * @param endState この行の終わりの状態を入れる。nullptrなら入れない。
 * @return 字句の一覧(空白は含まない)。
 * @note 戻り値はQVector。Qt5のQListは、ポインターより大きい要素(Tokenは12バイト)を1つずつ別に確保するため。
 * Qt6ではQVectorとQListは同じ型。
 */
QVector<Token> tokenizeLine(const QString& line, ScriptLanguage language, int state, int* endState);

/** @brief 1行を字句に分ける(文字列の一部をコピーせずに渡す版)。
 * @param line 1行(改行を含まない)。本文全体の中の1行をQStringViewで指せば、行ごとのQStringを作らずに済む。
 * @param language 言語。
 * @param state 前の行から引き継いだ状態。
 * @param endState この行の終わりの状態を入れる。nullptrなら入れない。
 * @return 字句の一覧。結果はtokenizeLine(const QString&, ...)と同じ。
 */
QVector<Token> tokenizeLine(QStringView line, ScriptLanguage language, int state, int* endState);

/** @brief 1行を字句に分け、呼出し元の配列へ入れる(多くの行を続けて読むときに、配列の確保を使い回す)。
 * @param line 1行(改行を含まない)。
 * @param language 言語。
 * @param state 前の行から引き継いだ状態。
 * @param endState この行の終わりの状態を入れる。nullptrなら入れない。
 * @param tokens 字句を入れる配列。最初に空にする(確保済みの容量はそのまま使う)。
 */
void tokenizeLineInto(QStringView line, ScriptLanguage language, int state, int* endState, QVector<Token>* tokens);

/** @brief 予約語か。
 * @param word 名前。
 * @param language 言語。
 * @return Pythonの``def``・``if``など、MELの``proc``・``string``などならtrue。
 * @note PythonのTrue・False・Noneは予約語ではなく、isConstant()で扱う。
 */
bool isKeyword(const QString& word, ScriptLanguage language);

/** @brief 予約語か(行の一部をコピーせずに調べる版)。
 * @param word 名前。``QStringView(line).mid(token.start, token.length)``のように渡す。
 * @param language 言語。
 * @return isKeyword(const QString&, ScriptLanguage)と同じ。
 */
bool isKeyword(QStringView word, ScriptLanguage language);

/** @brief 定数の名前か(Pythonの``True``・``False``・``None``・``self``、MELの``true``など)。
 * @param word 名前。
 * @param language 言語。
 * @return 定数ならtrue。
 */
bool isConstant(const QString& word, ScriptLanguage language);

/** @brief 定数の名前か(行の一部をコピーせずに調べる版)。
 * @param word 名前。
 * @param language 言語。
 * @return isConstant(const QString&, ScriptLanguage)と同じ。
 */
bool isConstant(QStringView word, ScriptLanguage language);

/** @brief Pythonの識別子の先頭に使える文字か。 @param character 文字。 @return 文字か``_``ならtrue。 */
bool isNameStart(QChar character);

/** @brief Pythonの識別子の2文字目以降に使える文字か。 @param character 文字。 @return 文字・数字・``_``ならtrue。 */
bool isNamePart(QChar character);

/** @brief 本文を``\n``で区切った行を、先頭から順に関数へ渡す(``text.split('\n')``と同じ区切り方)。
 * @param text 本文。
 * @param function ``function(int index, QStringView line)``の形の関数。indexは0始まりの行番号。
 * lineは本文の一部を指すので、行ごとのQStringを作らずに済む(行末の``\r``は除かない)。
 * @details 改行がN個なら、N+1行を渡す(最後が改行なら、最後の行は空)。
 */
template <typename Function>
void forEachLine(QStringView text, Function&& function) {
    qsizetype start = 0;
    for (int index = 0;; ++index) {
        const qsizetype newline = text.indexOf(QLatin1Char('\n'), start);
        const qsizetype end = newline < 0 ? text.size() : newline;
        function(index, text.mid(start, end - start));
        if (newline < 0) {
            return;
        }
        start = newline + 1;
    }
}

}  // namespace hedit
