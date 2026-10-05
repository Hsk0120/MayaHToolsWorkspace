"""大型ツールを専用standaloneで検証し、任意の変更前コードと比較する。"""

import argparse
import ast
import importlib.util
import sys
from pathlib import Path

from test_htools_hlib_migration import equivalent

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya/inhouse"))


def loadTool(name, baseline=None):
    """起動用のトップレベル呼び出しを除外してツールを読み込む。"""
    path = (baseline / (name + ".py") if baseline else
            ROOT / "maya/inhouse/HTools" / ("animation" if name == "create_pbd_overlap_rotation_bake" else "rigging") / ("lib_/" if name == "controllerShapeManager" else "") / (name + ".py"))
    key = "large_migration_" + name + ("_old" if baseline else "_new")
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    source = path.read_text(encoding="utf-8-sig")
    if baseline and name == "simpleCollisionFromSelection":
        # 旧コードの配列解放後参照は不定値になるため、数値比較では所有権だけ補正する。
        # 計算手順・入力の選別・生成処理は旧実装のまま比較する。
        source = source.replace("points.append(mesh_points[vertex_id])", "points.append(om.MPoint(mesh_points[vertex_id]))")
        source = source.replace("points.extend(mesh_fn.getPoints(om.MSpace.kWorld))",
                                "points.extend(om.MPoint(point) for point in mesh_fn.getPoints(om.MSpace.kWorld))")
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if isinstance(node, (
        ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))]
    exec(compile(tree, str(path), "exec"), module.__dict__)
    if name == "obbJointFromSelection" and baseline:
        module.simple_collision = loadTool("simpleCollisionFromSelection", baseline)
    return module


def snapshot(result=None):
    """生成名・選択・接続・形状・姿勢・ウェイトをMaya標準APIで記録する。"""
    import maya.cmds as cmds
    nodes = cmds.ls(long=True) or []
    data = dict(result=result, selection=cmds.ls(selection=True, long=True), nodes={})
    for node in nodes:
        kind = cmds.nodeType(node)
        if kind not in ("transform", "joint", "nurbsCurve", "mesh", "skinCluster"):
            continue
        item = dict(type=kind)
        if kind in ("transform", "joint"):
            item["matrix"] = cmds.xform(node, query=True, worldSpace=True, matrix=True)
            item["trs"] = [cmds.getAttr(node + "." + attr) for attr in ("translate", "rotate", "scale")]
            if kind == "joint":
                item["orientation"] = [cmds.getAttr(node + "." + attr) for attr in ("jointOrient", "rotateAxis", "rotateOrder")]
        elif kind == "nurbsCurve":
            item["cvs"] = cmds.xform(node + ".cv[*]", query=True, objectSpace=True, translation=True)
            item["degree"] = cmds.getAttr(node + ".degree")
            item["form"] = cmds.getAttr(node + ".form")
        elif kind == "mesh":
            item["points"] = cmds.xform(node + ".vtx[*]", query=True, worldSpace=True, translation=True)
        elif kind == "skinCluster":
            item["influences"] = cmds.skinCluster(node, query=True, influence=True)
            item["settings"] = [cmds.getAttr(node + "." + attr) for attr in
                                ("normalizeWeights", "maintainMaxInfluences", "maxInfluences")]
            item["weights"] = [cmds.skinPercent(node, v, query=True, value=True) for geo in
                               cmds.skinCluster(node, query=True, geometry=True) for v in cmds.ls(geo + ".vtx[*]", flatten=True)]
        pairs = cmds.listConnections(node, source=True, destination=False, plugs=True, connections=True) or []
        item["connections"] = sorted(zip(pairs[::2], pairs[1::2]))
        data["nodes"][node] = item
    return data


def reset(unit="cm", angle="deg"):
    """専用プロセス内で空シーンを作る。"""
    import maya.cmds as cmds
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear=unit, angle=angle)
    cmds.undoInfo(state=True)


def runScenario(name, baseline=None):
    """代表的な操作を実行し、比較用スナップショットを返す。"""
    import maya.cmds as cmds
    reset("m" if name.endswith("Meters") else "cm")
    if name.startswith("pbd"):
        tool = loadTool("create_pbd_overlap_rotation_bake", baseline)
        cmds.select(clear=True)
        root = cmds.joint(name="root", position=(0, 0, 0))
        child = cmds.joint(name="child", position=(0, 4, 0))
        tip = cmds.joint(name="tip", position=(0, 4 if name == "pbdZero" else 8, 0))
        cmds.setKeyframe(root, attribute="rotateZ", time=1, value=0)
        cmds.setKeyframe(root, attribute="rotateZ", time=5, value=25)
        cmds.select([root, child, tip])
        result = tool.create_pbd_overlap_rotation_bake(start_frame=1, end_frame=5)
        keys = {node: cmds.keyframe(node, query=True, valueChange=True) for node in (root, child, tip)}
        return snapshot((result, keys))
    if name.startswith("obb"):
        mesh = cmds.polyCube(name="source", width=2, height=5, depth=3, subdivisionsHeight=2)[0]
        cmds.xform(mesh, translation=(3, 4, 5), rotation=(21, -32, 17))
        cmds.select(mesh + ".vtx[0:7]" if "Vertices" in name else mesh)
        if "Joint" in name:
            tool = loadTool("obbJointFromSelection", baseline)
            result = tool.create_obb_joint_and_bind_from_selection(delete_collision=False)
            assert result["joints"]
        else:
            tool = loadTool("simpleCollisionFromSelection", baseline)
            result = tool.create_obb_collision_from_selection(use_hull_points="Raw" not in name)
            assert cmds.objExists(result)
        return snapshot(result)
    if name.startswith("orient"):
        tool = loadTool("advancedOrientJointUI", baseline)
        cmds.select(clear=True)
        root = cmds.joint(name="root", position=(1, 2, 3))
        child = cmds.joint(name="child", position=(4, 8, 6))
        cmds.joint(name="tip", position=(7, 11, 4))
        cmds.setAttr(root + ".scale", -1, 2, 1)
        cmds.setAttr(child + ".rotateAxis", 11, 7, -5)
        values = []
        for order in range(6):
            cmds.setAttr(child + ".rotateOrder", order)
            values.append(tool._compute_joint_orient_degrees(child, "x", "world", "x", "+", "y", "y", "+", "world"))
        assert all(value is not None for value in values)
        return snapshot(values)
    mesh = cmds.polyPlane(name="source", width=2, height=6, subdivisionsX=2, subdivisionsY=4, axis=(0, 0, 1))[0]
    cmds.select(clear=True)
    root = cmds.joint(name="root", position=(0, -3, 0))
    child = cmds.joint(name="child", position=(0, 3, 0))
    skin = cmds.skinCluster([root, child], mesh, toSelectedBones=True, maximumInfluences=2)[0]
    cmds.skinPercent(skin, mesh + ".vtx[*]", transformValue=[(root, 0.3), (child, 0.7)])
    cmds.select(mesh)
    if name.startswith("band"):
        tool = loadTool("autoTwoInfluenceBandSmooth", baseline)
        graph = tool._build_vertex_graph(mesh)
        band = tool.auto_two_influence_band_smooth(mesh=mesh, verbose=False)
        result = (graph, band)
        assert result
    elif name == "copy":
        tool = loadTool("duplicateAndCopySkinWeights", baseline)
        result = tool.duplicate_and_copy_skin_weights()
        assert cmds.objExists("prv_source")
    else:
        tool = loadTool("collapseJointWeightsToParent", baseline)
        cmds.select(child)
        result = tool.lod_like_collapse_selected_joints()
        assert not cmds.objExists(child)
    return snapshot(result)


def shapeScenario(section, name, replace, baseline=None):
    """プリセットの生成と既存形状差し替えを検証する。"""
    import maya.cmds as cmds
    reset()
    tool = loadTool("controllerShapeManager", baseline)
    if replace:
        target = cmds.curve(name="existing", degree=1, point=[(0, 0, 0), (1, 0, 0)])
        cmds.setAttr(target + ".translate", 3, 4, 5)
        cmds.setAttr(target + ".rotate", 13, -17, 21)
        cmds.select(target)
    function = getattr(getattr(tool, section), name)
    result = function(tx=1, ty=2, tz=-1, rx=12, ry=24, rz=35, sx=2, sy=0.5, sz=1.5)
    assert result
    return snapshot(result)


def verifySharedApis():
    """汎用化した処理の退化点群・インスタンス・Undoを検証する。"""
    import maya.cmds as cmds
    from hlib.maths import MSpace
    from hlib.nodes import Mesh
    from hlib.utils.orientedBounds import computeOrientedBounds
    from hrig.setups import ControlShape
    reset()
    for points in ([], [(0, 0, 0)] * 2, [(float("nan"), 0, 0)] * 3):
        try:
            computeOrientedBounds(points)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid bounds input accepted")
    bounds = computeOrientedBounds([(1, 2, 3)] * 3)
    assert equivalent(list(bounds["center"]), [1.0, 2.0, 3.0])
    assert bounds["size"] == (1e-6, 1e-6, 1e-6)
    mesh = cmds.polyPlane(width=2, height=2, subdivisionsX=1, subdivisionsY=1)[0]
    instance = cmds.instance(mesh)[0]
    cmds.setAttr(instance + ".scale", 2, 2, 2)
    first = Mesh(cmds.listRelatives(mesh, shapes=True, fullPath=True)[0])
    second = Mesh(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
    local = first.getVertexAdjacency()
    world = second.getVertexAdjacency(ws=True)
    assert len(local) == 4 and all(len(neighbors) == 2 for neighbors in local)
    assert equivalent(world, [[(index, length * 2) for index, length in neighbors] for neighbors in local])
    target = cmds.curve(name="control", degree=1, point=[(0, 0, 0), (1, 0, 0)])
    old_points = cmds.xform(target + ".cv[*]", query=True, objectSpace=True, translation=True)
    cmds.createNode("locator", parent=target, name="keepShape")
    ControlShape.replaceCurves(target, [(0, 0, 0), (2, 3, 4)], [0, 1])
    assert cmds.objExists("keepShape")
    cmds.undo()
    assert cmds.xform(target + ".cv[*]", query=True, objectSpace=True, translation=True) == old_points
    print("PASS shared APIs", flush=True)


def main():
    """専用Mayaで変更前との比較を実行する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path)
    args = parser.parse_args()
    import maya.standalone
    maya.standalone.initialize(name="python")
    count = 0
    try:
        verifySharedApis()
        for name in ("obb", "obbRaw", "obbVertices", "obbMeters", "obbJoint", "orient", "orientMeters", "band", "bandMeters", "copy", "collapse", "pbd", "pbdZero"):
            before = runScenario(name, args.baseline_dir) if args.baseline_dir else None
            after = runScenario(name)
            assert before is None or equivalent(before, after), name + " differs: " + repr((before, after))
            count += 1
            print("PASS", name, flush=True)
        tool = loadTool("controllerShapeManager")
        for section in tool.get_shape_classes().values():
            for name, _ in tool.get_shape_functions(section):
                for replace in (False, True):
                    before = shapeScenario(section.__name__, name, replace, args.baseline_dir) if args.baseline_dir else None
                    after = shapeScenario(section.__name__, name, replace)
                    assert before is None or equivalent(before, after), "shape differs: " + section.__name__ + "." + name
                    count += 1
                    print("PASS", section.__name__, name, replace, flush=True)
        print("PASSED", count, flush=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main()
