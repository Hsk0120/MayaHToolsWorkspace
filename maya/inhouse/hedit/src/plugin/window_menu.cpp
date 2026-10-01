/** @file window_menu.cpp
 * @brief Windowメニューの項目の追加・削除(MELで行う)。
 */
#include "plugin/window_menu.h"
#include "plugin/dock.h"
#include "plugin/mel.h"
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <QAction>
#include <QIcon>
#include <QPainter>
#include <QPixmap>
#include <QTimer>

namespace hedit {
namespace {

/// メニュー項目と区切り線のUI名。
constexpr const char* kMenuItemName = "heditWindowMenuItem";
constexpr const char* kDividerName = "heditWindowMenuDivider";

/// メニュー項目がまだ無いとき(起動の初期でevalDeferredに回したとき)に、アイコンを付け直す間隔と回数。
constexpr int kIconRetryInterval = 500;
constexpr int kIconRetryCount = 120;

/** @brief Windowメニューの緑のHアイコンを描く(元データはicons/hedit.svg)。
 * @param size 1辺のピクセル数。
 * @return アイコンの画像。
 * @details ``menuItem -image``はファイルのパスしか受け付けないため、以前はSVGをユーザー設定フォルダーへ
 * 書き出していた。DLLが埋め込みのデータをディスクへ書き出す形はウイルス対策ソフトに怪しまれやすいので、
 * 今はメモリ上で描いて、メニュー項目のQActionへ直接付ける。
 */
QPixmap drawMenuIcon(int size) {
    QPixmap pixmap(size, size);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.scale(size / 24.0, size / 24.0);  // 24×24の方眼に描く(SVGと同じ座標)。
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor("#69b66c"));
    painter.drawRoundedRect(QRectF(1, 1, 22, 22), 4, 4);
    painter.setPen(QPen(QColor("#17251a"), 3, Qt::SolidLine, Qt::FlatCap));
    painter.drawLine(QPointF(7, 6), QPointF(7, 18));
    painter.drawLine(QPointF(17, 6), QPointF(17, 18));
    painter.drawLine(QPointF(7, 12), QPointF(17, 12));
    painter.end();
    return pixmap;
}

/** @brief メニュー項目にアイコンを付ける。項目がまだ無ければ、少し後にやり直す。
 * @param remaining やり直せる残りの回数。
 * @details やり直しの予約はプラグインと同じ寿命のオブジェクト(dock::lifetime)に持たせるので、
 * アンロードされたら取り消される(hedit.mllの中のコードを、アンロード後に呼ばない)。
 */
void applyMenuIcon(int remaining) {
    QAction* action = MQtUtil::findMenuItem(toMString(kMenuItemName));
    if (action) {
        QIcon icon;
        for (int size : {16, 20, 24, 32, 48}) {
            icon.addPixmap(drawMenuIcon(size));
        }
        action->setIcon(icon);
        return;
    }
    if (remaining > 0 && dock::lifetime()) {
        QTimer::singleShot(kIconRetryInterval, dock::lifetime(), [remaining] { applyMenuIcon(remaining - 1); });
    }
}

}  // namespace

MStatus installWindowMenu() {
    // MELのglobal procを定義してから呼ぶ。evalDeferredで後から呼べるように、procとして定義している。
    // buildViewMenuは、Windowメニューの中身をMayaに作らせる(未作成だと追加した項目の位置がずれる)。
    const QString script = QString(
        "global proc hedit_installMenu()\n"
        "{\n"
        "    if (`about -batch`) return;\n"
        "    if (`menuItem -exists \"%1\"`) return;\n"
        "    string $parent = \"MayaWindow|mainWindowMenu\";\n"
        "    if (!`menu -exists $parent`) return;\n"
        "    buildViewMenu MayaWindow|mainWindowMenu;\n"
        "    if (!`menuItem -exists \"%2\"`)\n"
        "        menuItem -parent $parent -divider true \"%2\";\n"
        "    menuItem -parent $parent -label \"hedit - Python / MEL\"\n"
        "        -annotation \"Open hedit (additional script editor)\"\n"
        "        -sourceType \"mel\"\n"
        "        -command \"hedit -show\"\n"
        "        \"%1\";\n"
        "}\n"
        // メインメニューがあればすぐ追加する。evalDeferredは、loadPluginの処理中にidleが回ると
        // Mayaがまだ未ロードとみなす時点で実行され得るため、メニューを作る前(起動の初期)だけに使う。
        "if (`menu -exists \"MayaWindow|mainWindowMenu\"`) hedit_installMenu();\n"
        "else evalDeferred -lowestPriority \"hedit_installMenu\";\n")
        .arg(QString(kMenuItemName), QString(kDividerName));
    const MStatus status = MGlobal::executeCommand(toMString(script), false, false);
    applyMenuIcon(kIconRetryCount);
    return status;
}

MStatus uninstallWindowMenu() {
    const QString script = QString(
        "if (`menuItem -exists \"%1\"`) deleteUI \"%1\";\n"
        "if (`menuItem -exists \"%2\"`) deleteUI \"%2\";\n")
        .arg(QString(kMenuItemName), QString(kDividerName));
    return MGlobal::executeCommand(toMString(script), false, false);
}

}  // namespace hedit
