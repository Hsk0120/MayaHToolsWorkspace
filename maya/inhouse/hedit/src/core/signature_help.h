/** @file signature_help.h
 * @brief 引数のヒント(関数の呼出しを入力中に、引数の一覧と今の引数を出す)のための解析。
 * @details 1. カーソルより前の本文から、入力中の呼出し(``builder.build(1, ``)と、今が何番目の引数かを求める。
 * 2. ホバーと同じ方法で得た見出し(``def build(self, radius=1.0)``)を、引数ごとに分ける。
 * どちらも実行・importはしない。Mayaにも画面にも依存しない。
 */
#pragma once
#include <QString>
#include <QStringList>

namespace hedit {

/** @brief 入力中の呼出し。 */
struct CallContext {
    int nameEnd = -1;        ///< 呼び出している名前の終わりの位置(``build(``なら``d``の直後)。呼出しの中でなければ-1。
    int openParen = -1;      ///< 呼出しの``(``の位置。
    int argumentIndex = 0;   ///< 今の引数の番号(0始まり。括弧の外の``,``の数)。
    QString keyword;         ///< 今の引数が``name=``の形なら、その名前。
    bool attribute = false;  ///< ``obj.method(``のように点の後ろの名前を呼んでいるか(先頭の``self``を省く判断に使う)。
};

/** @brief カーソルより前の本文から、入力中の呼出しを求める。
 * @param before 文書の先頭からカーソルまでの本文(Python)。後ろの約4,000文字だけを読む。
 * @return 呼出し。``(``の中でなければnameEndが-1。
 */
CallContext findCallContext(const QString& before);

/** @brief 関数の見出しを分けたもの。 */
struct SignatureParts {
    QString head;            ///< ``(``まで(``def build(``)。
    QStringList parameters;  ///< 引数(``self``・``radius=1.0``)。
    QString tail;            ///< ``)``から後ろ(``) -> list``)。
    bool valid = false;      ///< 括弧を含む見出しだったか。
};

/** @brief 見出しを引数ごとに分ける(括弧・文字列の中の``,``では分けない)。
 * @param signature ホバーの見出し(``def build(self, radius=1.0) -> list``・``ls(*args, **kwargs)``)。
 * @return 分けた結果。括弧が無ければvalidがfalse。
 */
SignatureParts splitSignature(const QString& signature);

/** @brief 先頭の``self``・``cls``を省く(``obj.method(``の呼出しでは渡さないため)。
 * @param parts 分けた見出し。
 */
void dropBoundParameter(SignatureParts* parts);

/** @brief 今の引数が、見出しの何番目の引数にあたるかを返す。
 * @param parameters 引数の一覧。
 * @param argumentIndex 呼出しでの引数の番号。
 * @param keyword ``name=``の形ならその名前。
 * @return 引数の番号。``*args``より後ろの位置引数は``*args``、名前の一致が無い``name=``は``**kwargs``。
 * 当てはまる引数が無ければ-1。
 */
int activeParameterIndex(const QStringList& parameters, int argumentIndex, const QString& keyword);

}  // namespace hedit
