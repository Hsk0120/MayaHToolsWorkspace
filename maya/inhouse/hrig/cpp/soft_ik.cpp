/** @file soft_ik.cpp
 * @brief Soft IKのスカラー距離計算を一つのDGノードへまとめる。
 * @note 距離は呼出側が統一した部位空間の単位。静的属性以外の可変状態を持たない。
 */
#include <maya/MPxNode.h>
#include <maya/MFnPlugin.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MPlug.h>
#include <algorithm>
#include <cmath>

/** @brief Bifrost版と同じ距離・softnessを入力し目標位置の倍率を出力する。 */
class HrigSoftIK final : public MPxNode {
public:
    // 開発用ID。配布前に組織の登録済みIDへ置き換える。
    static MTypeId id;
    static MObject distance;
    static MObject length;
    static MObject softness;
    static MObject ratio;

    /** @brief Mayaが所有して破棄するノードを生成する。
     * @return Mayaへ所有権を渡すインスタンス。
     */
    static void* creator() { return new HrigSoftIK; }

    /** @brief 入出力属性とdirty伝播の関係を登録する。
     * @return 属性登録の成功状態。
     */
    static MStatus initialize() {
        MFnNumericAttribute attribute;
        distance = attribute.create("distance", "dst", MFnNumericData::kDouble, 0.0);
        attribute.setMin(0.0); attribute.setKeyable(true); addAttribute(distance);
        length = attribute.create("length", "len", MFnNumericData::kDouble, 10.0);
        attribute.setMin(0.000001); attribute.setKeyable(true); addAttribute(length);
        softness = attribute.create("softness", "sft", MFnNumericData::kDouble, 1.0);
        attribute.setMin(0.0); attribute.setKeyable(true); addAttribute(softness);
        ratio = attribute.create("ratio", "rat", MFnNumericData::kDouble, 1.0);
        attribute.setWritable(false); attribute.setStorable(false); addAttribute(ratio);
        attributeAffects(distance, ratio); attributeAffects(length, ratio);
        attributeAffects(softness, ratio);
        return MS::kSuccess;
    }

    /** @brief 入力だけに依存するため複数インスタンスを並列評価できる。
     * @return 並列実行を許可するスケジューリング種別。
     */
    SchedulingType schedulingType() const override { return kParallel; }

    /** @brief Soft IKの倍率を計算し出力をcleanにする。
     * @param plug Mayaから評価要求された出力。
     * @param data 現在コンテキストの入力と出力。Mayaが所有する。
     * @return 対象外の属性はkUnknownParameter、非有限入力はkFailure。
     */
    MStatus compute(const MPlug& plug, MDataBlock& data) override {
        if (plug != ratio) return MS::kUnknownParameter;
        const double d = data.inputValue(distance).asDouble();
        const double l = data.inputValue(length).asDouble();
        const double s = data.inputValue(softness).asDouble();
        if (!std::isfinite(d) || !std::isfinite(l) || !std::isfinite(s) || l <= 0.0)
            return MS::kFailure;
        // Bifrost版のゼロ除算回避と同じ下限を使う。
        const double safeDistance = std::max(d, 0.000001);
        const double soft = std::clamp(s, 0.000001, l);
        const double threshold = l - soft;
        const double excess = std::max(safeDistance - threshold, 0.0);
        const double softened = threshold + soft * (1.0 - std::exp(-excess / soft));
        data.outputValue(ratio).setDouble(std::min(safeDistance, softened) / safeDistance);
        data.setClean(plug);
        return MS::kSuccess;
    }
};

MTypeId HrigSoftIK::id(0x0007F101);
MObject HrigSoftIK::distance;
MObject HrigSoftIK::length;
MObject HrigSoftIK::softness;
MObject HrigSoftIK::ratio;

/** @brief Mayaへ開発用Soft IKノードを登録する。
 * @param object Mayaが所有するプラグインオブジェクト。
 * @return ノード登録結果。ID衝突などのエラーはMayaへ返す。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "inhouse", "0.1.0", "Any");
    return plugin.registerNode("hrigSoftIK", HrigSoftIK::id,
                               HrigSoftIK::creator, HrigSoftIK::initialize);
}

/** @brief プラグイン解除時に登録を外す。
 * @param object Mayaが所有するプラグインオブジェクト。
 * @return 登録解除結果。
 */
MStatus uninitializePlugin(MObject object) {
    MFnPlugin plugin(object);
    return plugin.deregisterNode(HrigSoftIK::id);
}
