/** @file symbols.h
 * @brief 補完に使う「名前とその情報」の表。
 * @details 1つの名前(Symbol)は、次のどれかを表す:
 * - 関数: detailに``name(arg1, arg2)``。
 * - クラス: membersにクラスの中の名前の表、detailに``class Name``。
 * - モジュール(``import a.b``など): targetにモジュール名。
 * - ``from X import Y``: fromModuleにX、fromNameにY(どのモジュールのどの名前か)。
 * - それ以外(変数など): どれも空。
 */
#pragma once
#include <QByteArray>
#include <QJsonObject>
#include <QMap>
#include <QString>
#include <memory>

namespace hedit {

struct Symbol;
/// 名前 → 情報の表。QMapは名前順に並ぶので、候補を名前順に出すのにそのまま使える。
using SymbolTable = QMap<QString, Symbol>;

/** @brief 1つの名前の情報。 */
struct Symbol {
    QString detail;      ///< 候補の一覧に出す説明(関数の引数など)。
    QString kind;        ///< ``builtin``・``keyword``、または空(候補の絞り込みに使う)。
    QString target;      ///< モジュールを指す場合のモジュール名。
    QString fromModule;  ///< ``from X import Y``のX。
    QString fromName;    ///< ``from X import Y``のY。
    std::shared_ptr<SymbolTable> members;  ///< クラスの中の名前。クラスでなければnullptr。

    /** @brief 内容が同じか(membersは中身で比べる)。 @param other 比べる相手。 @return 同じならtrue。 */
    bool operator==(const Symbol& other) const;
    /** @brief 内容が違うか。 @param other 比べる相手。 @return 違うならtrue。 */
    bool operator!=(const Symbol& other) const { return !(*this == other); }
};

/** @brief 表をJSONにする(テストとPythonの結果との突き合わせ用)。
 * @param table 表。
 * @return ``{"名前": {"detail":..., "members":{...}, "target":..., "from":..., "name":...}}``。空の項目は出さない。
 */
QJsonObject symbolTableToJson(const SymbolTable& table);

/** @brief Pythonから受け取ったJSONを表にする。
 * @param object ``symbolTableToJson``と同じ形のJSON。
 * @return 表。
 */
SymbolTable symbolTableFromJson(const QJsonObject& object);

}  // namespace hedit
