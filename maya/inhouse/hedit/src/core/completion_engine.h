/** @file completion_engine.h
 * @brief Pythonの補完候補を求める。以前Python(hedit.completion)で行っていた処理をC++にしたもの。
 * @details 補完の流れ:
 * 1. カーソルの行から、何を補完するかを決める(``cmds.l``なら``cmds``の中の``l``で始まる名前)。
 * 2. 編集中の本文の宣言は、core/python_declarations.cppで取り出す(Pythonを呼ばない)。
 * 3. ``cmds``のようなモジュールの中身は、読み込み済みならPythonに公開名を問い合わせ(ModuleSource)、
 *    まだ読み込まれていなければsys.pathからファイルを探して宣言を取り出す(実行はしない)。
 * Pythonに問い合わせる部分はModuleSourceの関数として外から渡すので、Maya無しでもテストできる。
 */
#pragma once
#include "core/completion_types.h"
#include "core/symbols.h"
#include <QDateTime>
#include <QHash>
#include <QString>
#include <QStringList>
#include <functional>
#include <optional>

namespace hedit {

/** @brief 読み込み済みのモジュールの情報(Pythonから受け取る)。 */
struct LoadedModule {
    SymbolTable members;  ///< 公開名(``_``で始まる名前は含まない)。
    QString file;         ///< モジュールのファイル(``__file__``)。無ければ空。
};

/** @brief Pythonでしか分からない情報を取り出す関数の一式。空の関数は「情報なし」として扱う。 */
struct ModuleSource {
    /// 読み込み済みならtrueを返して情報を入れる。読み込まれていなければfalse。
    std::function<bool(const QString& name, LoadedModule* module)> loadedModule;
    /// sys.pathの各フォルダー(絶対パス)。
    std::function<QStringList()> searchPaths;
    /// 組み込みモジュールと読み込み済みモジュールのトップレベル名(``import``の行で使う)。
    std::function<QStringList()> topLevelNames;
    /// 読み込み済みのモジュールの中の名前(pathが空ならモジュール自身)の見出しとdocstringを入れる。
    /// 見つかればtrue。ホバーで、ソースの無い名前(Cの拡張やmaya.cmdsなど)の説明に使う。
    std::function<bool(const QString& module, const QStringList& path, QString* signature, QString* doc)> describe;
};

/** @brief 名前の補完に使う、Pythonの組み込みの名前と予約語。 */
struct CompletionEnvironment {
    QStringList builtins;  ///< ``print``などの組み込みの名前。
    QStringList keywords;  ///< ``return``などの予約語。
};

/** @brief Pythonの補完候補を求める。1つの編集画面(Mayaのセッション)で1つ使う。 */
class CompletionEngine {
public:
    /** @brief Pythonへの問い合わせ方を受け取る。 @param source 問い合わせの関数。 */
    explicit CompletionEngine(ModuleSource source);

    /** @brief 組み込みの名前と予約語を設定する。 @param environment Pythonから受け取った一覧。 */
    void setEnvironment(const CompletionEnvironment& environment);

    /** @brief ファイルから取り出した宣言のキャッシュを捨てる(Refresh completion)。 */
    void clearCaches();

    /** @brief カーソルまでの本文から、補完候補を求める。
     * @param source 文書の先頭からカーソルまでの本文。
     * @return 名前順で最大250件の候補。20万文字を超える本文は空。
     */
    CompletionResult complete(const QString& source);

    /** @brief マウスを重ねた名前の説明(ホバー)を求める。
     * @param text 本文全体。
     * @param end 名前の終わりの位置(``cmds.ls``の``ls``に重ねたなら``ls``の直後)。
     * @return 見出しとdocstring。分からなければ空。
     * @details 補完と同じ手順で名前をたどる(``import``も実行もしない)。編集中の本文・まだ読み込んでいない``.py``は
     * 字句解析で取り出したdocstringを使い、ソースの無い名前だけPythonに問い合わせる(ModuleSource::describe)。
     */
    HoverInfo describe(const QString& text, int end);

    /** @brief 編集中の本文の宣言を返す。同じ本文なら前回の結果を使う。
     * @param text 本文(カーソルの行を除いた部分)。
     * @return 宣言。
     */
    SymbolTable localDeclarations(const QString& text);

private:
    /** @brief 1回の問い合わせ(補完・ホバー)の中だけ使い回す情報。
     * @details complete()・describe()の中で作り、関数を抜けると捨てる。次の問い合わせでは
     * sys.pathとモジュールの中身を取り直すので、Python側の変化(import・reload)にすぐ追従する。
     */
    struct Request {
        std::optional<QStringList> paths;         ///< sys.path(最初に必要になったときに1回だけ受け取る)。
        QHash<QString, SymbolTable> modules;      ///< モジュール名 → 求めた中身。
    };

    /** @brief 名前をたどった結果。 */
    struct Located {
        Symbol item;         ///< 行き着いた名前の情報。変数からクラスを推論した場合は、そのクラス。
        QString module;      ///< itemがあるモジュール(本文の中なら空)。
        QStringList path;    ///< モジュールの中でのitemの位置(``Class.method``なら``[Class, method]``)。
        bool found = true;   ///< 最後までたどれたか。
    };

    /** @brief 最初の名前を探す: 本文の宣言 → 変数ならクラスの推論 → 組み込みの名前 → モジュール名。
     * @param request 今の問い合わせ。
     * @param scope 名前を探す表(本文の宣言、またはモジュールの中身)。
     * @param text 型を推論する本文(カーソルより前)。空なら推論しない。
     * @param name 名前。
     * @param depth 推論の深さ(循環を止める)。
     * @return たどった結果。
     */
    Located resolveName(Request& request, const SymbolTable& scope, const QString& text, const QString& name, int depth);

    /** @brief ``a.b.c``をたどる(補完とホバーで共通)。 @param request 今の問い合わせ。 @param scope 最初の名前を探す表。
     * @param text 型を推論する本文。 @param parts 名前を点で分けたもの。 @param depth 推論の深さ。
     * @return たどった結果。途中で見つからなければfoundがfalse。
     */
    Located walk(Request& request, const SymbolTable& scope, const QString& text, const QStringList& parts, int depth);

    /** @brief たどった名前の中身(モジュールの公開名・クラスのメンバー)を返す。
     * @param request 今の問い合わせ。 @param located たどった結果。 @param scope 本文の宣言。 @param depth 推論の深さ。
     * @return 名前の表。クラスなら、親クラスから受け継いだ名前も含む。
     */
    SymbolTable membersOf(Request& request, const Located& located, const SymbolTable& scope, int depth);

    /** @brief クラスのメンバーを、親クラス(Symbol::bases)から受け継いだものも含めて返す。
     * @param request 今の問い合わせ。 @param item クラス。 @param home クラスが定義された場所の名前の表。
     * @param module クラスが定義されたモジュール(本文の中なら空)。 @param depth たどる深さ。
     * @return メンバーの表。同じ名前は、子クラス・先に書いた親クラスを優先する。
     */
    SymbolTable classMembers(Request& request, const Symbol& item, const SymbolTable& home, const QString& module,
                             int depth);

    /** @brief sys.pathの中で見つかったモジュールの場所。 */
    struct ModuleLocation {
        QString packageFolder;  ///< パッケージ(フォルダー)なら、そのフォルダー。
        QString file;           ///< 読む.py(パッケージなら__init__.py)。名前空間パッケージなら空。
        QString moduleName;     ///< 相対importの基準(``__init__.py``なら``name.__init__``)。
    };

    /** @brief sys.pathからモジュールの場所を探す(補完とホバーで共通)。
     * @param request 今の問い合わせ。
     * @param name モジュール名(``a.b``)。
     * @return 見つかった場所の一覧。名前空間パッケージは複数の場所にまたがるため一覧にする。
     * ファイルが見つかったところで探すのをやめる(Pythonのimportと同じ)。
     */
    QList<ModuleLocation> locateModule(Request& request, const QString& name);

    /** @brief モジュールの中の名前を返す。読み込み済みならPythonから、無ければsys.pathのファイルから。
     * @param request 今の問い合わせ。
     * @param name モジュール名(``a.b``)。
     * @return 名前の表。見つからなければ空。
     */
    SymbolTable moduleMembers(Request& request, const QString& name);

    /** @brief 名前が指す先(モジュール・クラス・from importの元)の中身を返す。
     * @param request 今の問い合わせ。
     * @param item 名前の情報。
     * @param depth 循環を止めるための深さ。
     * @return 中身の名前の表。
     */
    SymbolTable resolve(Request& request, const Symbol& item, int depth = 0);

    /** @brief ファイルの宣言を返す。更新日時と大きさが変わっていなければ前回の結果を使う。
     * @param path .pyファイル。
     * @param moduleName 相対importの基準(``__init__.py``なら``pkg.__init__``)。
     * @return 宣言。読めなければ前回の結果か空。
     * @note 書きかけ(括弧が閉じていない等)のファイルは、前回の正しい結果があればそれを使う。
     */
    SymbolTable fileDeclarations(const QString& path, const QString& moduleName);

    /** @brief ``from X import Y``をたどり、Yの定義そのものにする(ホバー用)。
     * @param request 今の問い合わせ。
     * @param item たどる名前。定義に置き換える。
     * @param module itemがあるモジュール名。たどった先のモジュールに置き換える(本文の中なら空)。
     * @param path モジュールの中でのitemの位置(``Class.method``なら``[Class, method]``)。
     */
    void followImports(Request& request, Symbol* item, QString* module, QStringList* path);

    /** @brief モジュールのdocstringを返す(ホバー用)。
     * @param request 今の問い合わせ。
     * @param name モジュール名。
     * @param found 見つかったかを入れる。
     * @return docstring。
     */
    QString moduleDocstring(Request& request, const QString& name, bool* found);

    /** @brief sys.pathを返す。1回の問い合わせの中では、最初に受け取ったものを使い回す。
     * @param request 今の問い合わせ。
     * @return フォルダーの一覧。
     */
    QStringList searchPaths(Request& request);

    /** @brief ファイルの宣言のキャッシュ。 */
    struct CachedFile {
        QDateTime modified;   ///< 読んだときの更新日時。
        qint64 size = 0;      ///< 読んだときの大きさ。
        SymbolTable symbols;  ///< 宣言。
        QString docstring;    ///< モジュールのdocstring。
    };

    ModuleSource source_;                ///< Pythonへの問い合わせ。
    CompletionEnvironment environment_;  ///< 組み込みの名前と予約語。
    QHash<QString, CachedFile> files_;   ///< パス → ファイルの宣言(問い合わせをまたいで使う)。
    QString localsText_;                 ///< 前回の編集中の本文。
    SymbolTable localsSymbols_;          ///< 前回の編集中の本文の宣言。
};

/** @brief 本文から、変数の型(クラスの式)を推論する。実行はしない。
 * @param text カーソルより前の本文。
 * @param name 変数名。
 * @return 次のうち、カーソルに近い(後ろの)ものの式。``x: pkg.A``(型ヒント。``"pkg.A"``も可)・
 * ``x = pkg.A(...)``(呼出しの結果)・``def f(x: pkg.A)``(引数の型ヒント)。推論できなければ空。
 * 推論できない代入(``x = 1``・``x = A().b``)の方が近ければ空を返す(古い型を使わない)。
 */
QString inferredTypeExpression(const QString& text, const QString& name);

/** @brief 本文の末尾の``a.b.c``の形の名前を返す(補完する位置の判定)。
 * @param source カーソルまでの本文。
 * @return 末尾の名前。英字か``_``で始まる部分から。無ければ空(``cmds.``のように点で終わる場合も空)。
 */
QString trailingDottedName(const QString& source);

}  // namespace hedit
