/** @file ui_scale.cpp
 * @brief 拡大率とアイコンの取り出し方を保持する。
 */
#include "editor/ui_scale.h"
#include <QtGlobal>

namespace hedit {
namespace {

/// UIの拡大率。MayaではMQtUtil::dpiScale(1.0)。Maya無しのテストでは1.0のまま。
double uiScaleFactor = 1.0;

/// ツールバーのアイコンの取り出し方。MayaではMQtUtil::createIcon。空ならQIcon(":/名前")。
std::function<QIcon(const QString&)> iconProvider;

}  // namespace

void setUiScale(double scale) {
    uiScaleFactor = scale > 0 ? scale : 1.0;
}

int scaled(double pixels) {
    return qRound(pixels * uiScaleFactor);
}

void setIconProvider(std::function<QIcon(const QString&)> provider) {
    iconProvider = std::move(provider);
}

QIcon loadIcon(const QString& name) {
    if (iconProvider) {
        return iconProvider(name);
    }
    return QIcon(":/" + name);
}

}  // namespace hedit
