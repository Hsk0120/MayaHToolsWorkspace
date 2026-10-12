"""尻尾1軸回避の UE RBF が MetaHuman の Pose Editor で編集できることを検証する。

demo_joint_chain_rbf のシーン(既定は case="mixed"、回転ベースは case="rotation"・prefix="rot")を組み、Pose Editor の Python API(mh_pose_editor)で
次を確かめる。

1. ソルバー・ドライバージョイント・ドリブンジョイントを認識し、全ポーズが名前付きで並ぶ。
2. 編集モード → ポーズへ移動 → ドリブンを回す → Update → 編集終了 で、ポーズの値が保存され、
   そのポーズの近くのフレームで尻尾の出力が変わる。編集を終えるとドリブンへの接続が戻る。
3. Pose Editor の画面(Inputs・Poses)を開いて画像に残す。

検証用の Maya は起動バッチを通さないことがあるので、metahuman_for_maya.mod の
PYTHONPATH・PATH をここで追加する。結果は .maya-output/verification/<実行ID>/ に
pose-editor-check.json と画像で保存し、1つでも満たさなければ例外にする。
専用の Maya GUI で実行する(シーンを作り直す)。
"""

import json
import math
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
import demo_interactive
import demo_joint_chain_rbf as chain

ROOT = Path(__file__).resolve().parents[1]
METAHUMAN = ROOT/"maya/external/MetaHumanForMaya"
MODULE_FILE = ROOT/"maya/modules/metahuman_for_maya.mod"
EDIT_FRAME = 200
EDIT_DELTA = -15.0


def addMetaHumanPaths():
    """metahuman_for_maya.mod の、今のMayaバージョン向けの PYTHONPATH と PATH を追加する。

    Returns:
        list[str]: 追加した PYTHONPATH。
    """
    text = MODULE_FILE.read_text(encoding="utf-8")
    marker = "MAYAVERSION:{}".format(cmds.about(majorVersion=True))
    if marker not in text:
        raise RuntimeError("metahuman_for_maya.mod has no section for " + marker)
    section = text.split(marker, 1)[1].split("\n+", 1)[0]
    added = []
    for relative in re.findall(r"^PYTHONPATH \+:= (\S+)", section, re.M):
        path = str(METAHUMAN/relative)
        if path not in sys.path:
            sys.path.append(path)
            added.append(path)
    for relative in re.findall(r"^PATH \+:= (\S+)", section, re.M):
        path = os.path.normpath(str(METAHUMAN/relative))
        if os.path.isdir(path):
            # Python 3.8以降は PATH だけでは依存DLLを探さないため、明示的に登録する。
            os.add_dll_directory(path)
            if path not in os.environ["PATH"]:
                os.environ["PATH"] = path+os.pathsep+os.environ["PATH"]
    return added


def _rotationX(matrix):
    """ローカル行列のX軸まわりの回転。度。"""
    return math.degrees(om.MTransformationMatrix(om.MMatrix(matrix)).rotation().x)


def _grabPoseEditor(folder, solver_name):
    """Pose Editor を開き、ソルバーを選んだ状態の Inputs・Poses タブを画像に残す。

    Returns:
        list[str]: 保存した画像。
    """
    import mh_pose_editor
    from mh_pose_editor import app as pose_editor_app
    from qtpy import QtWidgets
    # 同じセッションで開き直すと Utilities の表示が重なるので、前のウィンドウを閉じてから開く。
    if getattr(pose_editor_app.module, "window", None) is not None:
        pose_editor_app.module.window.view.close()
        pose_editor_app.module.window = None
    window = mh_pose_editor.show()
    view = window.view
    application = QtWidgets.QApplication.instance()
    view.resize(1300, 820)
    application.processEvents()
    lists = [w for w in view.findChildren(QtWidgets.QAbstractItemView) if w.model()]
    solver_view = next(w for w in lists if w.model().rowCount() >= 1)
    rows = [solver_view.model().index(r, 0) for r in range(solver_view.model().rowCount())]
    index = next((i for i in rows if i.data() == solver_name), rows[0])
    solver_view.setCurrentIndex(index)
    solver_view.clicked.emit(index)
    application.processEvents()
    images = []
    for tab_name in ("Inputs", "Poses"):
        for tabs in view.findChildren(QtWidgets.QTabWidget):
            for i in range(tabs.count()):
                if tabs.tabText(i) == tab_name:
                    tabs.setCurrentIndex(i)
        application.processEvents()
        path = folder/"pose-editor-{}.png".format(tab_name.lower())
        view.grab().save(str(path))
        images.append(str(path))
    return images


def main(case="mixed", prefix="rbf"):
    """シーンを組んで Pose Editor との互換性を検証し、結果フォルダを返す。

    Args:
        case (str): demo_joint_chain_rbf のケース。
        prefix (str): 確かめる RBF 列の名前。"rotation" ケースの回転ベースは "rot"。

    Returns:
        Path: 結果フォルダ。
    """
    solver_name, driver, driven = prefix+"PoseSolver", prefix+"RbfDriver_JNT", prefix+"TailDriven_JNT"
    output = prefix+"TailOutput_JNT"
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    folder = ROOT/".maya-output"/"verification"/(datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    result = {"title": "MetaHuman Pose Editor との互換性（尻尾1軸回避のUE RBF）", "case": case, "column": prefix,
              "checks": {}}
    checks = result["checks"]

    addMetaHumanPaths()
    demo_interactive.closeDemoWindows()
    chain.main(record=False, case=case)
    from mh_pose_editor.model.rbf_node import RBFNode
    from mh_pose_editor.model import pose_blender

    solvers = [str(node) for node in RBFNode.find_all()]
    solver = RBFNode(solver_name)
    poses = solver.poses()
    result["solvers"] = solvers
    result["num_poses"] = solver.num_poses()
    result["named_poses"] = len(poses)
    result["drivers"] = solver.drivers()
    result["driven"] = solver.driven_joints()
    checks["solver_found"] = solver_name in solvers
    checks["driver_recognized"] = result["drivers"] == [driver]
    checks["driven_recognized"] = result["driven"] == [driven]
    checks["all_poses_named"] = result["num_poses"] > 0 and result["named_poses"] == result["num_poses"]

    # 編集の流れ。EDIT_FRAME の rel・H に最も近いポーズを、Pose Editor の手順で直す。
    # ドライバーが位置・回転のどちらでも同じになるよう、ドライバーの元の rel・H から選ぶ。
    cmds.currentTime(EDIT_FRAME)
    rel = cmds.getAttr(prefix+"Relative.output1D")
    half = min(max(cmds.getAttr(prefix+"H.output"), 0), chain.H_RANGE*chain.H_STEP)
    name = "rel{:+04d}_H{:03d}".format(int(round(rel/chain.REL_STEP)*chain.REL_STEP),
                                       int(round(half/chain.H_STEP)*chain.H_STEP))
    blender = pose_blender.UEPoseBlenderNode.find_by_transform(driven)
    index = solver.pose_index(name)
    result["edit"] = {"frame": EDIT_FRAME, "pose": name, "delta_degrees": EDIT_DELTA,
                      "stored_before_degrees": _rotationX(blender.get_pose(index=index)),
                      "output_before_degrees": cmds.getAttr(output+".rx")}
    driver_before = cmds.getAttr(driver+".matrix")
    solver.edit_solver(True)
    checks["edit_mode_on"] = solver.get_solver_edit_status()
    solver.go_to_pose(name)
    at_pose = cmds.getAttr(driven+".rx")
    checks["go_to_pose_moves_driven"] = abs(at_pose-result["edit"]["stored_before_degrees"]) < 1e-3
    result["edit"]["driver_moved_by_go_to_pose"] = cmds.getAttr(driver+".matrix") != driver_before
    cmds.setAttr(driven+".rx", at_pose+EDIT_DELTA)
    solver.update_pose(name)
    solver.edit_solver(False)
    checks["edit_mode_off"] = not solver.get_solver_edit_status()
    checks["driven_reconnected"] = bool(cmds.listConnections(blender.out_matrix_attr, type="decomposeMatrix"))
    result["edit"]["stored_after_degrees"] = _rotationX(blender.get_pose(index=index))
    checks["pose_value_saved"] = abs(result["edit"]["stored_after_degrees"]
                                     - (result["edit"]["stored_before_degrees"]+EDIT_DELTA)) < 1e-3
    cmds.currentTime(EDIT_FRAME+1)
    cmds.currentTime(EDIT_FRAME)
    result["edit"]["output_after_degrees"] = cmds.getAttr(output+".rx")
    checks["output_changed"] = abs(result["edit"]["output_after_degrees"]-result["edit"]["output_before_degrees"]) > 1

    try:
        result["images"] = _grabPoseEditor(folder, solver_name)
        checks["ui_opened"] = True
    except Exception as error:
        result["ui_error"] = "{}: {}".format(type(error).__name__, error)
        checks["ui_opened"] = False

    result["ok"] = all(checks.values())
    (folder/"pose-editor-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT/".maya-output/verification/latest-pose-editor-rbf.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not result["ok"]:
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError("Pose Editorとの互換性の検証に失敗: {} ({})".format(", ".join(failed), folder))
    logger.info("Pose Editorとの互換性を確認しました: {}".format(folder))
    return folder


if __name__ == "__main__":
    main()
