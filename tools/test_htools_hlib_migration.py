"""専用MayaでHToolsの結果を検証し、指定時は変更前コードとも比較する。"""

import argparse
import ast
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya/inhouse"))
sys.path.insert(0, str(ROOT / "maya/external/cymel/python"))


def loadFunctions(path):
    """import時実行ツールを操作前に走らせず、関数定義を読み込む。

    Args:
        path (Path): テストする元のPythonファイル。

    Returns:
        dict: 定義された関数とimport。
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    tree.body = [node for node in tree.body if isinstance(
        node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))]
    namespace = {"__file__": str(path), "__name__": "migration_test"}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace


def runScenario(name, baseline=None):
    """新規の使い捨てシーンで操作結果を記録する。

    Args:
        name (str): テストケース。
        baseline (Path | None): 旧コードのローカル保存先。

    Returns:
        dict: 戻り値・選択・ノード・直接接続・代表値。
    """
    import maya.cmds as cmds
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg")
    cases = {
        "segment": ("allSegmentScaleOf.py", "main"),
        "constraint": ("parentScaleConstraintOffset0.py", "parent_scale_constraint_offset0"),
        "skin": ("selectSkinningJoints.py", "select_skinning_joints_from_selection"),
        "influences": ("getMaxInfluencesFromSelection.py", "get_max_influences_from_selection"),
        "connections": ("copyIncomingConnectionsFromFirstToSecond.py", "copy_incoming_connections_from_first_to_second"),
        "locked": ("copyIncomingConnectionsFromFirstToSecond.py", "copy_incoming_connections_from_first_to_second"),
        "duplicateInputs": ("duplicateInputsFromFirstToSecond.py", "duplicate_all_inputs_from_first_to_second"),
        "animation": ("duplicateAnimCurve.py", "duplicate_anim_only_and_rewire_selected_v2"),
        "shader": ("create_preview_sharder.py", "main"),
        "curve": ("createCurveFromSelectedClusters.py", "create_curve_from_selected_clusters"),
        "curveMeters": ("createCurveFromSelectedClusters.py", "create_curve_from_selected_clusters"),
        "curveParent": ("createCurveFromSelectedClusters.py", "create_curve_from_selected_clusters"),
    }
    file_name, function = cases[name]
    path = (baseline / file_name if baseline else ROOT / "maya/inhouse/HTools" /
            ("material" if name == "shader" else "rigging") / file_name)
    namespace = loadFunctions(path)
    initial = set(cmds.ls())
    values = {}
    options = {}
    if name in ("skin", "influences"):
        mesh = cmds.polyCube(name="mesh")[0]
        cmds.select(clear=True)
        joint = cmds.joint(name="influence")
        cmds.skinCluster(joint, mesh, toSelectedBones=True, maximumInfluences=2)
        cmds.select(mesh)
    elif name == "segment":
        cmds.select(clear=True)
        cmds.joint(name="j1")
        cmds.joint(name="j2")
    elif name == "shader":
        shader = cmds.shadingNode("lambert", asShader=True, name="sourceShader")
        cmds.addAttr(shader, longName="emissive", attributeType="double3")
        for axis in "RGB":
            cmds.addAttr(shader, longName="emissive" + axis, attributeType="double", parent="emissive")
        texture = cmds.shadingNode("file", asTexture=True, name="sourceTexture")
        cmds.connectAttr(texture + ".outColor", shader + ".color")
        cmds.connectAttr(texture + ".outColor", shader + ".emissive")
        cmds.select(shader)
    elif name.startswith("curve"):
        if name == "curveMeters":
            cmds.currentUnit(linear="m")
        mesh = cmds.polyCube(name="clusterMesh")[0]
        handles = []
        for index in range(3):
            _, handle = cmds.cluster(mesh + ".vtx[{}]".format(index), name="testCluster{}".format(index))
            cmds.setAttr(handle + ".translate", index + 1, index * 2, -index)
            handles.append(handle)
        if name == "curveParent":
            parent = cmds.createNode("transform", name="handleParent")
            cmds.setAttr(parent + ".translate", 7, 8, 9)
            cmds.setAttr(parent + ".rotate", 10, 20, 30)
            cmds.setAttr(parent + ".scale", 2, 3, 4)
            cmds.parent(handles, parent, relative=True)
            cmds.setAttr(handles[0] + ".rotatePivotTranslate", 1, 2, 3)
            cmds.setAttr(handles[0] + ".offsetParentMatrix", 1, 0, 0, 0, 0, 1, 0, 0,
                         0, 0, 1, 0, 3, 4, 5, 1, type="matrix")
        cmds.select(handles)
    else:
        first = cmds.createNode("transform", name="source")
        second = cmds.createNode("transform", name="destination")
        if name == "constraint":
            cmds.setAttr(first + ".translate", 3, 4, 5)
            cmds.setAttr(first + ".rotate", 15, 25, 35)
            cmds.setAttr(first + ".scale", 2, 3, 4)
        elif name == "animation":
            cmds.setKeyframe(first, attribute="translateX", time=1, value=2)
            cmds.setKeyframe(first, attribute="translateX", time=10, value=8)
        else:
            upstream = cmds.createNode("multiplyDivide", name="upstream")
            cmds.connectAttr(upstream + ".outputX", first + ".translateX")
            if name == "locked":
                cmds.setAttr(second + ".translateX", lock=True)
                options["force"] = True
        cmds.select([first, second] if name != "animation" else first)
    result = namespace[function](**options)
    if name == "segment":
        values["segment"] = [cmds.getAttr(joint + ".segmentScaleCompensate") for joint in ("j1", "j2")]
        assert values["segment"] == [False, False]
    elif name == "constraint":
        values["translate"] = cmds.getAttr("destination.translate")
        values["rotate"] = cmds.getAttr("destination.rotate")
        values["scale"] = cmds.getAttr("destination.scale")
        assert values["translate"][0] == (3, 4, 5)
    elif name == "locked":
        assert not result["copied"] and result["errors"]
        assert cmds.getAttr("destination.translateX", lock=True)
        # hlibはPlugをフルパス化するため、Mayaのエラー内の対象表記だけ正規化する。
        result["errors"] = [(plug, bool(message)) for plug, message in result["errors"]]
    elif name == "animation":
        values["keys"] = cmds.keyframe(first + "_translateX_bak", query=True, valueChange=True)
        assert values["keys"] == [2, 8]
    elif name.startswith("curve"):
        values["cvs"] = cmds.xform(result + ".cv[*]", query=True, worldSpace=True, translation=True)
        assert len(values["cvs"]) == 9
    elif name == "shader":
        values["eccentricity"] = cmds.getAttr("prv_sourceShader.eccentricity")
        assert values["eccentricity"] == 0
    nodes = sorted(set(cmds.ls()) - initial)
    connections = set()
    for node in nodes:
        pairs = cmds.listConnections(node, source=True, destination=False, plugs=True, connections=True) or []
        connections.update(zip(pairs[::2], pairs[1::2]))
    return dict(result=result, selection=cmds.ls(selection=True, long=True),
                nodes=[(node, cmds.nodeType(node)) for node in nodes],
                connections=sorted(connections), values=values)


def equivalent(left, right):
    """計算順序による浮動小数点誤差だけを許容して結果を比較する。

    Args:
        left (object): 変更前の結果。
        right (object): 変更後の結果。

    Returns:
        bool: 文字列・接続・構造は一致、数値は誤差内ならTrue。
    """
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return left == right


def main():
    """専用standaloneを起動し、現行検証と任意の旧実装比較を実行する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path)
    args = parser.parse_args()
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        for name in ("segment", "constraint", "skin", "influences", "connections", "locked",
                     "duplicateInputs", "animation", "shader", "curve", "curveMeters", "curveParent"):
            before = runScenario(name, args.baseline_dir) if args.baseline_dir else None
            after = runScenario(name)
            if before is not None:
                assert equivalent(before, after), "{} differs:\n{}\n{}".format(
                    name, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False))
            print("PASS", name)
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main()
