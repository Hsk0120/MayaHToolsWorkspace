"""使い捨てGUIで大型ツールの操作と変更前の結果を比較する。"""

import json
import os
from pathlib import Path
import traceback


def main(output_dir, finished):
    """方向調整UIの適用とコントローラUIの生成を検証する。"""
    if os.environ.get("HLIB_DISPOSABLE_GUI") != "1":
        raise RuntimeError("検証用GUIだけで実行してください。")
    import maya.cmds as cmds
    from test_htools_large_migration import ROOT, loadTool, reset, snapshot, equivalent
    result = dict(status="running", checks=[])
    try:
        baseline = ROOT / "docs/research/htoolsLargeBaseline"
        for angle in ("deg", "rad"):
            outputs = []
            sources = [baseline, None] if baseline.is_dir() else [None]
            for source in sources:
                reset(angle=angle)
                cmds.select(clear=True)
                root = cmds.joint(name="root", position=(0, 0, 0))
                child = cmds.joint(name="child", position=(3, 5, 1))
                cmds.joint(name="tip", position=(7, 8, 4))
                cmds.setAttr(child + ".rotateAxis", 0.1, 0.2, 0.3)
                mesh = cmds.polyCube(name="skinMesh")[0]
                cmds.skinCluster([root, child], mesh, toSelectedBones=True)
                tool = loadTool("advancedOrientJointUI", source)
                tool.show_orient_joint_like_window()
                cmds.select(child)
                tool._apply_orient_from_ui()
                outputs.append(snapshot())
            assert len(outputs) == 1 or equivalent(*outputs), "Orient UI differs: " + angle
            result["checks"].append("orient_apply_skin_" + angle)
        reset()
        from HTools.rigging import controllerShapeManagerUI
        window = controllerShapeManagerUI.show_controller_shape_manager_ui()
        assert window.isVisible()
        controllerShapeManagerUI.controllerShapeManager.Planar.circle()
        assert cmds.ls(type="nurbsCurve")
        window.close()
        result["checks"].append("controller_ui")
        result["status"] = "passed"
    except Exception:
        result.update(status="failed", error=traceback.format_exc())
    (Path(output_dir) / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    finished(result)
