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

namespace mce {
namespace {

/// メニュー項目と区切り線のUI名。
constexpr const char* kMenuItemName = "mayaCodeEditorWindowMenuItem";
constexpr const char* kDividerName = "mayaCodeEditorWindowMenuDivider";

/// メニュー項目がまだ無いとき(起動の初期でevalDeferredに回したとき)に、アイコンを付け直す間隔と回数。
constexpr int kIconRetryInterval = 500;
constexpr int kIconRetryCount = 120;

/** @brief Windowメニューのアイコン(緑の角丸四角に < >)を描く(元データはicons/mayaCodeEditor.svg)。
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
    // < と > を丸い線の端・角で描く(SVGの stroke-linecap / stroke-linejoin="round" と同じ)。
    painter.setPen(QPen(QColor("#17251a"), 2.6, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    painter.setBrush(Qt::NoBrush);
    const QPointF left[] = {QPointF(9, 7), QPointF(5, 12), QPointF(9, 17)};
    const QPointF right[] = {QPointF(15, 7), QPointF(19, 12), QPointF(15, 17)};
    painter.drawPolyline(left, 3);
    painter.drawPolyline(right, 3);
    painter.end();
    return pixmap;
}

/** @brief メニュー項目にアイコンを付ける。項目がまだ無ければ、少し後にやり直す。
 * @param remaining やり直せる残りの回数。
 * @details やり直しの予約は、プラグインと同じ寿命のオブジェクト(dock::lifetime)の子のタイマーで行うので、
 * アンロードされたら取り消される(mayaCodeEditor.mllの中のコードを、アンロード後に呼ばない)。
 * ``QTimer::singleShot(時間, 文脈, ラムダ)``は、文脈が破棄されても時間が来るまでQtの中に残り、そのとき
 * mayaCodeEditor.mllの中のラムダを片付けようとする(アンロード後だと落ちる。Qt5で確認)ため使わない。
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
        auto timer = new QTimer(dock::lifetime());  // 所有者はdock::lifetime()。アンロード時に一緒に破棄される。
        timer->setSingleShot(true);
        QObject::connect(timer, &QTimer::timeout, timer, [timer, remaining] {
            timer->deleteLater();
            applyMenuIcon(remaining - 1);
        });
        timer->start(kIconRetryInterval);
    }
}

}  // namespace

MStatus installWindowMenu() {
    // MELのglobal procを定義してから呼ぶ。evalDeferredで後から呼べるように、procとして定義している。
    // buildViewMenuは、Windowメニューの中身をMayaに作らせる(未作成だと追加した項目の位置がずれる)。
    const QString script = QString(
        "global proc mayaCodeEditor_installMenu()\n"
        "{\n"
        "    if (`about -batch`) return;\n"
        "    if (`menuItem -exists \"%1\"`) return;\n"
        "    string $parent = \"MayaWindow|mainWindowMenu\";\n"
        "    if (!`menu -exists $parent`) return;\n"
        "    buildViewMenu MayaWindow|mainWindowMenu;\n"
        "    if (!`menuItem -exists \"%2\"`)\n"
        "        menuItem -parent $parent -divider true \"%2\";\n"
        "    menuItem -parent $parent -label \"Maya Code Editor\"\n"
        "        -annotation \"Open Maya Code Editor (Python / MEL script editor)\"\n"
        "        -sourceType \"mel\"\n"
        "        -command \"mayaCodeEditor -show\"\n"
        "        \"%1\";\n"
        "}\n"
        // メインメニューがあればすぐ追加する。evalDeferredは、loadPluginの処理中にidleが回ると
        // Mayaがまだ未ロードとみなす時点で実行され得るため、メニューを作る前(起動の初期)だけに使う。
        "if (`menu -exists \"MayaWindow|mainWindowMenu\"`) mayaCodeEditor_installMenu();\n"
        "else evalDeferred -lowestPriority \"mayaCodeEditor_installMenu\";\n")
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

}  // namespace mce
