/** @file maya_host.h @brief Maya SDKだけでシーン操作を実行する。 */
#pragma once
#include "../browser/host_services.h"
class QWidget;
namespace qpe {
/** @brief UIに渡すホスト関数を生成する。 @return 所有UIの寿命内で使う関数群。 */
HostServices mayaServices();
/** @brief 例外つきMEL呼出。 @param code 実行するMEL。 */
void mayaCommand(const QString& code);
/** @brief UTF-8文字列のMEL引用。 @param value 入力。 @return 引用済み。 */
QString melQuote(const QString& value);
/** @brief シーン操作本体。 @param action 操作。 @param paths パス。 @param options 固定設定。 @return 実行完了ならtrue、利用者による取消しならfalse。 */
bool mayaPerform(const QString& action, const QStringList& paths, const QJsonObject& options);
}
