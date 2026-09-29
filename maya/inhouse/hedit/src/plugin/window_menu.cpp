/** @file window_menu.cpp
 * @brief Windowメニューの項目の追加・削除(MELで行う)。
 */
#include "plugin/window_menu.h"
#include "plugin/mel.h"
#include "plugin/user_paths.h"
#include <maya/MGlobal.h>
#include <QDir>
#include <QFile>
#include <QSaveFile>

namespace hedit {
namespace {

/// Windowメニューの緑のHアイコン(元データはicons/hedit.svg)。.mll単体で使えるよう同梱する。
constexpr const char* kMenuIconSvg =
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\">\n"
    "  <rect x=\"1\" y=\"1\" width=\"22\" height=\"22\" rx=\"4\" fill=\"#69b66c\"/>\n"
    "  <path d=\"M7 6v12M17 6v12M7 12h10\" fill=\"none\" stroke=\"#17251a\" stroke-width=\"3\"/>\n"
    "</svg>\n";

/// メニュー項目と区切り線のUI名。
constexpr const char* kMenuItemName = "heditWindowMenuItem";
constexpr const char* kDividerName = "heditWindowMenuDivider";

/** @brief 同梱のアイコンをユーザー設定フォルダーへ書き出し、そのパスを返す。
 * @return アイコンの絶対パス。書き出せない場合は空(メニューはアイコンなしで追加する)。
 * @details ``menuItem -image``はファイルのパスしか受け付けないため、メモリ上のSVGを
 * ``<userPrefDir>/hedit/hedit.svg``へ置く。内容が同じなら書き直さない。
 */
QString writeMenuIcon() {
    const QString folder = userFolder();
    if (folder.isEmpty() || !QDir().mkpath(folder)) {
        return QString();
    }
    const QString path = folder + "/hedit.svg";
    const QByteArray svg(kMenuIconSvg);
    {
        QFile current(path);
        if (current.open(QIODevice::ReadOnly) && current.readAll() == svg) {
            return path;
        }
    }
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(svg) != svg.size() || !file.commit()) {
        return QString();
    }
    return path;
}

}  // namespace

MStatus installWindowMenu() {
    const QString icon = writeMenuIcon();
    const QString imageFlag = icon.isEmpty() ? QString() : "        -image " + melQuote(icon) + "\n";
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
        "%3"
        "        \"%1\";\n"
        "}\n"
        // メインメニューがあればすぐ追加する。evalDeferredは、loadPluginの処理中にidleが回ると
        // Mayaがまだ未ロードとみなす時点で実行され得るため、メニューを作る前(起動の初期)だけに使う。
        "if (`menu -exists \"MayaWindow|mainWindowMenu\"`) hedit_installMenu();\n"
        "else evalDeferred -lowestPriority \"hedit_installMenu\";\n")
        .arg(QString(kMenuItemName), QString(kDividerName), imageFlag);
    return MGlobal::executeCommand(toMString(script), false, false);
}

MStatus uninstallWindowMenu() {
    const QString script = QString(
        "if (`menuItem -exists \"%1\"`) deleteUI \"%1\";\n"
        "if (`menuItem -exists \"%2\"`) deleteUI \"%2\";\n")
        .arg(QString(kMenuItemName), QString(kDividerName));
    return MGlobal::executeCommand(toMString(script), false, false);
}

}  // namespace hedit
