/** @file ui_scale.h
 * @brief 画面の拡大率(4K画面などのInterface Scaling)とアイコンの取り出し方。
 * @details MayaはQt自体の高DPI拡大を無効にし、各部品の寸法に拡大率を掛けて大きな画面へ対応している。
 * そのためhedit側でも、文字のピクセル数・余白・幅・アイコンの大きさを、全てscaled()を通して決める。
 * Mayaのメニューやステータスバーの文字はMayaが拡大済みなので、ここでは扱わない。
 *
 * どちらの設定も「以後に作る編集画面」に効く。plugin/editor_host.cppが画面の作成前に設定する。
 */
#pragma once
#include <QIcon>
#include <QString>
#include <functional>

namespace hedit {

/** @brief UIの拡大率を設定する。
 * @param scale 100%を1.0とする拡大率。MayaではMQtUtil::dpiScale(1.0)を渡す
 * (Maya標準のScript Editorと同じ基準)。0以下は1.0として扱う。
 */
void setUiScale(double scale);

/** @brief 100%のときのピクセル数を、現在の拡大率で換算する。
 * @param pixels 100%のときのピクセル数。
 * @return 拡大率を掛けて四捨五入したピクセル数。
 */
int scaled(double pixels);

/** @brief ツールバーのアイコンを取り出す関数を設定する。
 * @param provider アイコンの画像名(例: ``openScript.png``)からアイコンを返す関数。空なら``QIcon(":/名前")``を使う。
 * @note MayaではMQtUtil::createIconを渡す。Qtの``:/名前``は拡大率に関係なく小さな画像しか返さないが、
 * createIconは拡大率に合った高解像度の画像を返す。
 */
void setIconProvider(std::function<QIcon(const QString&)> provider);

/** @brief 画像名からアイコンを取り出す。
 * @param name Mayaのリソースの画像名(例: ``openScript.png``)。
 * @return 見つからなければ空のQIcon(isNull()がtrue)。
 */
QIcon loadIcon(const QString& name);

}  // namespace hedit
