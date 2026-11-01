/** @file host_services.h @brief UIをMaya APIから分離する値と呼出境界。 */
#pragma once
#include <QStringList>
#include <QJsonObject>
#include <functional>
namespace qpe {
/** @brief GUIスレッドのみで呼ぶホスト契約。Maya側がプラグイン寿命内の関数を渡す。 */
struct HostServices {
    bool maya = false;
    double dpi = 1.0;
    std::function<bool(const QString&, const QStringList&, const QJsonObject&)> perform;
    std::function<QString()> scenePath;
    std::function<QString()> projectPath;
    std::function<QStringList()> namespaces;
};
}
