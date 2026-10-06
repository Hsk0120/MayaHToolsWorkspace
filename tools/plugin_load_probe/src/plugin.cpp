/** @file plugin.cpp
 * @brief .mllのロードがWindowsのセキュリティ機能に止められるかを切り分けるための、最小のMayaプラグイン。
 * @details ロードとアンロードの時にScript Editorへ1行出すだけで、それ以外は何もしない。
 * Qt・COM・Python・ファイルの読み書き・ネットワーク・別プロセスの起動は使わず、リンクするのも
 * OpenMaya/Foundationだけにしている。そのため、hedit.mllなどが止められて、このプラグインも同じ場所で
 * 止められるなら、原因はプラグインの中身ではなく「置き場所」か「署名がないこと」だと判断できる。
 * セキュリティ機能を迂回するためのものではない(使い方はREADME.md)。
 */
#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MString.h>

namespace {

/// Plug-in Managerなどに表示する版。
const char* const kVersion = "1.0.0";

/** @brief 読み込まれた.mllの場所を「フォルダー/プラグイン名」の形で返す。
 * @param plugin 対象のプラグイン。
 * @return 表示用の文字列。
 */
MString describe(MFnPlugin& plugin) {
    return plugin.loadPath() + "/" + plugin.name();
}

}  // namespace

/** @brief プラグインのロード時にMayaが呼ぶ。読み込まれた場所を表示するだけ。
 * @param object Mayaのプラグインオブジェクト。
 * @return 常に成功。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "PluginLoadProbe", kVersion, "Any");
    MGlobal::displayInfo(MString("pluginLoadProbe loaded: ") + describe(plugin));
    return MS::kSuccess;
}

/** @brief プラグインのアンロード時にMayaが呼ぶ。登録したものが無いので表示だけ。
 * @param object Mayaのプラグインオブジェクト。
 * @return 常に成功。
 */
MStatus uninitializePlugin(MObject object) {
    MFnPlugin plugin(object);
    MGlobal::displayInfo(MString("pluginLoadProbe unloaded: ") + describe(plugin));
    return MS::kSuccess;
}
