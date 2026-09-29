/** @file matrix_follow.cpp
 * @brief offset * sourceWorld * parentInverseを倍精度で評価する。
 * @note 単一入力の全行列追従。parentConstraintの複数入力補間等は実装しない。
 */
// DLL入口とAPI署名はsoft_ik.cppだけで生成する。
#define MNoPluginEntry
#define MNoVersionString
#include "matrix_follow.h"
#include <maya/MPxNode.h>
#include <maya/MFnMatrixAttribute.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>

/** @brief 保持状態を持たず親空間への追従行列を返すDGノード。 */
class HrigMatrixFollow final : public MPxNode {
public:
    static MTypeId id;
    static MObject offset, sourceWorld, parentInverse, outputMatrix;
    /** @brief Mayaへ所有権を渡すインスタンスを生成する。
     * @return Mayaが破棄するノード。
     */
    static void* creator() { return new HrigMatrixFollow; }
    /** @brief 倍精度行列属性とdirty伝播を登録する。
     * @return 初期化結果。
     */
    static MStatus initialize() {
        MFnMatrixAttribute attr;
        offset = attr.create("offset", "off", MFnMatrixAttribute::kDouble);
        addAttribute(offset);
        sourceWorld = attr.create("sourceWorld", "src", MFnMatrixAttribute::kDouble);
        addAttribute(sourceWorld);
        parentInverse = attr.create("parentInverse", "pinv", MFnMatrixAttribute::kDouble);
        addAttribute(parentInverse);
        outputMatrix = attr.create("outputMatrix", "out", MFnMatrixAttribute::kDouble);
        attr.setWritable(false);
        attr.setStorable(false);
        addAttribute(outputMatrix);
        attributeAffects(offset, outputMatrix);
        attributeAffects(sourceWorld, outputMatrix);
        attributeAffects(parentInverse, outputMatrix);
        return MS::kSuccess;
    }
    /** @brief インスタンス間の共有計算状態がないため並列実行を許可する。
     * @return 並列スケジューリング。
     */
    SchedulingType schedulingType() const override { return kParallel; }
    /** @brief Mayaの行ベクトル順で行列積を計算する。
     * @param plug 評価要求属性。
     * @param data Maya所有の現在コンテキストのデータ。
     * @return 出力以外はkUnknownParameter、評価成功時kSuccess。
     */
    MStatus compute(const MPlug& plug, MDataBlock& data) override {
        if (plug != outputMatrix) return MS::kUnknownParameter;
        const MMatrix value = data.inputValue(offset).asMatrix()
                            * data.inputValue(sourceWorld).asMatrix()
                            * data.inputValue(parentInverse).asMatrix();
        data.outputValue(outputMatrix).setMMatrix(value);
        data.setClean(plug);
        return MS::kSuccess;
    }
};

// 既存SoftIKと同様の開発用ID。組織外配布前に登録済みIDへ変更する。
MTypeId HrigMatrixFollow::id(0x0007F102);
MObject HrigMatrixFollow::offset;
MObject HrigMatrixFollow::sourceWorld;
MObject HrigMatrixFollow::parentInverse;
MObject HrigMatrixFollow::outputMatrix;

MStatus registerMatrixFollow(MFnPlugin& plugin) {
    return plugin.registerNode("hrigMatrixFollow", HrigMatrixFollow::id,
                               HrigMatrixFollow::creator, HrigMatrixFollow::initialize);
}
MStatus deregisterMatrixFollow(MFnPlugin& plugin) {
    return plugin.deregisterNode(HrigMatrixFollow::id);
}
