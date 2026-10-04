/** @file symbols.h
 * @brief 補完に使う「名前とその情報」の表。
 * @details 1つの名前(Symbol)の種類はtype(SymbolType)で表す。種類ごとに使う欄:
 * | type | 使う欄 |
 * |---|---|
 * | Function | detail(``name(arg1, arg2)``)・signature・doc |
 * | Class | members(クラスの中の名前の表)・bases(親クラスの式)・detail(``class Name``)・signature・doc |
 * | Module(``import a.b``など) | target(モジュール名) |
 * | Import(``from X import Y``) | fromModule(X)・fromName(Y) |
 * | Builtin・Keyword | なし(組み込みの名前・予約語。Preferencesでの絞り込みに使う) |
 * | Value(変数など) | なし |
 * 種類を作るときは、Symbol::module()などの関数を使う(欄の組合せの誤りを防ぐため)。
 * signatureとdocはマウスを重ねたときの説明(ホバー)用で、JSON(symbolTableToJson)には出さない
 * (以前のPythonの結果との突き合わせを変えないため)。typeもJSONには出さず、読むときは欄から決める。
 */
#pragma once
#include <QByteArray>
#include <QJsonObject>
#include <QMap>
#include <QString>
#include <QStringList>
#include <memory>

namespace hedit {

struct Symbol;
/// 名前 → 情報の表。QMapは名前順に並ぶので、候補を名前順に出すのにそのまま使える。
using SymbolTable = QMap<QString, Symbol>;

/** @brief 名前の種類。 */
enum class SymbolType {
    Value,     ///< 変数など(説明の無い名前)。
    Function,  ///< 関数(``def``)。
    Class,     ///< クラス(``class``)。membersに中身を持つ。
    Module,    ///< モジュール(``import a.b``)。targetにモジュール名を持つ。
    Import,    ///< ``from X import Y``。どのモジュールのどの名前かを持つ。
    Builtin,   ///< Pythonの組み込みの名前(``print``など)。
    Keyword,   ///< Pythonの予約語(``return``など)。
};

/** @brief 1つの名前の情報。 */
struct Symbol {
    SymbolType type = SymbolType::Value;   ///< 種類。
    QString detail;                        ///< 候補の一覧に出す説明(関数の引数など)。
    QString target;                        ///< Module: モジュール名。
    QString fromModule;                    ///< Import: ``from X import Y``のX。
    QString fromName;                      ///< Import: ``from X import Y``のY。
    std::shared_ptr<SymbolTable> members;  ///< Class: クラスの中の名前。それ以外はnullptr。
    QStringList bases;                     ///< Class: 親クラスの式(``class B(pkg.A)``なら``pkg.A``)。ソースから読んだときだけ。
    QString signature;                     ///< ホバーに出す定義(``def name(a, b=1) -> int``)。無ければ空。
    QString doc;                           ///< docstring(字下げを整えたもの)。無ければ空。

    /** @brief モジュールを指す名前を作る。 @param name モジュール名。 @return Moduleの名前。 */
    static Symbol module(const QString& name);
    /** @brief ``from X import Y``の名前を作る。 @param module X。 @param name Y。 @return Importの名前。 */
    static Symbol import(const QString& module, const QString& name);
    /** @brief 組み込みの名前か予約語を作る。 @param type BuiltinかKeyword。 @return その種類の名前。 */
    static Symbol category(SymbolType type);

    /** @brief 補完候補の種類の名前(Preferencesの絞り込みとJSONに使う)。 @return ``builtin``・``keyword``、または空。 */
    QString kindName() const;

    /** @brief 補完の一覧のアイコンの種類。
     * @return ``function``・``class``・``module``・``variable``・``import``・``builtin``・``keyword``。
     */
    QString categoryName() const;

    /** @brief 内容が同じか(membersは中身で比べる)。 @param other 比べる相手。 @return 同じならtrue。 */
    bool operator==(const Symbol& other) const;
    /** @brief 内容が違うか。 @param other 比べる相手。 @return 違うならtrue。 */
    bool operator!=(const Symbol& other) const { return !(*this == other); }
};

/** @brief 表をJSONにする(テストとPythonの結果との突き合わせ用)。
 * @param table 表。
 * @return ``{"名前": {"detail":..., "kind":..., "members":{...}, "target":..., "from":..., "name":...}}``。空の項目は出さない。
 */
QJsonObject symbolTableToJson(const SymbolTable& table);

/** @brief Pythonから受け取ったJSONを表にする。種類は欄から決める(targetならModule、membersならClassなど)。
 * @param object ``symbolTableToJson``と同じ形のJSON。
 * @return 表。
 */
SymbolTable symbolTableFromJson(const QJsonObject& object);

}  // namespace hedit
