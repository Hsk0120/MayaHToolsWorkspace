/** @file mel.h
 * @brief C++からMELを実行するための小さな補助関数と、QString・MStringの変換。
 * @details MayaのUIコマンド(workspaceControl・menuItemなど)を、Pythonを介さずに呼ぶための窓口。
 * inline関数なので、ヘッダーだけで使える(.cppは無い)。
 */
#pragma once
#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <QString>

namespace hedit {

/** @brief QStringをMayaのMStringへ変換する(UTF-8)。
 * @param text 変換する文字列。
 * @return 同じ内容のMString。
 */
inline MString toMString(const QString& text) {
    MString result;
    result.setUTF8(text.toUtf8().constData());
    return result;
}

/** @brief MayaのMStringをQStringへ変換する(UTF-8)。
 * @param text 変換する文字列。
 * @return 同じ内容のQString。
 */
inline QString fromMString(const MString& text) {
    return QString::fromUtf8(text.asUTF8());
}

/** @brief 文字列を返すMELを実行し、結果を返す。
 * @param script 実行するMEL。heditが組み立てた固定の文だけを渡す。
 * @return MELの結果。失敗時は空。
 * @note executeCommandStringResultは、整数・真偽値を返すコマンド(``-exists``等)では失敗して
 * 空を返す。それらにはmelInt/melBoolを使う。
 */
inline QString mel(const QString& script) {
    // 第2引数false: Script Editorへコマンドを表示しない。第3引数false: Undoの記録に残さない。
    return fromMString(MGlobal::executeCommandStringResult(toMString(script), false, false));
}

/** @brief 整数を返すMEL(scriptJobの番号等)を実行する。
 * @param script 実行するMEL。
 * @return MELの結果。失敗時は0。
 */
inline int melInt(const QString& script) {
    int result = 0;
    MGlobal::executeCommand(toMString(script), result, false, false);
    return result;
}

/** @brief 真偽値を返すMEL(``-exists``・``-q -visible``等)を実行する。
 * @param script 実行するMEL。
 * @return MELの結果。失敗時はfalse。
 */
inline bool melBool(const QString& script) {
    return melInt(script) != 0;
}

/** @brief MELの文字列リテラルとして埋め込めるよう、二重引用符で囲む。
 * @param text 埋め込む値(UI名やパス)。
 * @return バックスラッシュ・引用符・改行をエスケープし、``"``で囲んだ文字列。
 */
inline QString melQuote(QString text) {
    text.replace("\\", "\\\\");
    text.replace("\"", "\\\"");
    text.replace("\n", "\\n");
    return "\"" + text + "\"";
}

}  // namespace hedit
