"""尻尾1軸回避の検証サンプルを一覧から作成・録画するウィンドウ。

サンプル本体はワークスペースの ``tools/demo_joint_*.py`` にあり、ここではパスを通して
呼び出すだけにする。Build は録画せずにシーンを作り、タイムラインの再生・スクラブで
HUDの式と数値を確認できる。Record は従来どおり録画して数値検証し、結果を
``.maya-output/verification/`` に保存する。

いずれも File > New 相当でシーンを作り直すので、作業中のシーンは保存してから使う。
"""

import importlib
import os
import sys
from pathlib import Path

from maya import cmds

WINDOW = "tailAvoidanceSamplesWindow"
WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE/"tools"

# (モジュール名, 見出し, 説明, main へ渡す追加引数)。表示文字は英語。
SAMPLES = [
    ("demo_joint_side_keep", "Tangent stop (keep entry side)",
     "Stops at the sphere tangent. The side you entered from is kept, so it never flips.", {}),
    ("demo_joint_cone_soft", "Body cone soft avoid",
     "A cone fixed to the body. The deeper the tail enters, the more rotateX slows down before the edge.", {}),
    ("demo_joint_rbf_pose", "UE RBF pose interpolation",
     "Poses blended by UERBFSolverNode (MetaHuman for Maya). First load asks to trust the plug-in.", {}),
    ("demo_joint_chain_rbf", "Spine/arm chain with 3 body spheres",
     "hip, spine0-2, shoulder, upperArm, lowerArm moving together. Tangent stop vs UE RBF.", {}),
    ("demo_joint_chain_rbf", "Spine/arm chain: a ball enters the twist plane",
     "A thigh ball starts cutting the twist plane while the tail rests on a tangent. Shows the jump.",
     {"case": "activation"}),
    ("demo_joint_chain_rbf", "Spine/arm chain: soft ball entry (before / after)",
     "Blends a ball in by how deep the twist plane cuts it, so the tail no longer jumps when it enters.",
     {"case": "soft_entry"}),
    ("demo_joint_chain_rbf", "Spine/arm chain: position vs rotation RBF driver",
     "Same poses driven by a translated joint (rel/20, H/10) or a rotated joint (rel/3, 0, H*0.667).",
     {"case": "rotation"}),
    ("demo_simple_cone_rbf", "Simple: 2 ConeReaders + RBF (crosses the body center)",
     "A simpler setup with two cones and 23 poses, compared with the current one. Shows flips at the center.", {}),
    ("demo_simple_cone_rbf", "Simple: 2 ConeReaders + RBF (does not cross the center)",
     "Same simple setup with an input that stays on one side of the body.", {"inputs": "no_cross"}),
    ("demo_space_target", "Plan 1 (control in body space) and plan 2 (aim at a target)",
     "Plan 1 clamps a control that lives in a body-facing space. Plan 2 aims at a target locator.", {}),
    ("demo_runtime_avoid", "Plan 1 at runtime: tail fixed to the forearm avoids the body automatically",
     "The tail is never animated. Arm and forearm twist move the body toward it; aim + driven keys + clamp.", {}),
    ("demo_humanoid_tail_avoid", "Humanoid A-pose: only the upper arm moves, elbow is a 1-axis hinge",
     "Plan 1 at runtime on mlrig.examples.humanoid (A-pose). A 45 cm tail points back and down from the elbow.",
     {"case": "apose"}),
    ("demo_humanoid_tail_avoid", "Humanoid T-pose: arm, elbow, forearm twist and spine move",
     "Same tail and plan 1 on the T-pose skeleton, including forearm twist.", {"case": "tpose_twist"}),
    ("demo_humanoid_tail_avoid", "Humanoid A-pose: raised arm, plan 1 with a ConeReader switch",
     "One ConeReader per body ball tells whether the body cuts the tail's twist plane. "
     "If not, the tail keeps its rest angle. Keep-side and near-side variants.", {"case": "raise"}),
    ("demo_joint_chain_rbf", "Spine/arm chain: cone driver approximation",
     "Spheres vs cones from the elbow (fixed angle / angle scaled by distance), all feeding the same UE RBF.",
     {"case": "cone_c"}),
    ("demo_cone_rbf", "ConeReader weights (0-1) as RBF drivers",
     "Three ConeReader outputs drive UE RBF, compared with the geometry-driven RBF. Shows where it fails.", {}),
    ("demo_joint_sweep_compare", "Method comparison (5 columns)",
     "Input / nearest tangent / outside sweep / early turn / cone push, side by side.", {}),
]

# 自動で確かめる検証。(モジュール名, 見出し, 説明, main へ渡す引数)。main() が結果フォルダを返し、失敗なら例外にする。
CHECKS = [
    ("verify_pose_editor_rbf", "MetaHuman Pose Editor compatibility",
     "Builds the chain sample, edits one pose through the Pose Editor API and checks the tail follows. "
     "Saves a JSON report and Pose Editor screenshots.", {}),
    ("verify_pose_editor_rbf", "MetaHuman Pose Editor compatibility (rotation driver)",
     "Same check for the rotation-driven RBF (rotation sample, rot column).", {"case": "rotation", "prefix": "rot"}),
]


def _findFfmpeg():
    """録画に使うFFmpegを探す。環境変数、PATH、ワークスペース内の imageio_ffmpeg の順。"""
    if os.environ.get("MAYA_VERIFICATION_FFMPEG"):
        return os.environ["MAYA_VERIFICATION_FFMPEG"]
    for candidate in sorted((WORKSPACE/".maya-output").glob("*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe")):
        return str(candidate)
    return None


def _load(module_name):
    """サンプルのモジュールを最新の内容で読み込む。"""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _confirmNewScene():
    """未保存の変更があれば、シーンを作り直してよいか確認する。"""
    if not cmds.file(query=True, modified=True):
        return True
    answer = cmds.confirmDialog(title="Tail Avoidance Samples",
                                message="The current scene has unsaved changes.\n"
                                        "The sample replaces it with a new scene. Continue?",
                                button=["Continue", "Cancel"], defaultButton="Cancel",
                                cancelButton="Cancel", dismissString="Cancel")
    return answer == "Continue"


def run(module_name, record=False, options=None):
    """サンプルを作成する。

    Args:
        module_name (str): ``tools`` 内のサンプルのモジュール名。
        record (bool): True なら録画して検証し、False ならシーンを作るだけにする。
        options (dict | None): サンプルの main へ渡す追加の引数。
    """
    if not _confirmNewScene():
        return
    if record:
        ffmpeg = _findFfmpeg()
        if not ffmpeg:
            cmds.warning("FFmpeg was not found. Set MAYA_VERIFICATION_FFMPEG to ffmpeg.exe to record.")
            return
        os.environ["MAYA_VERIFICATION_FFMPEG"] = ffmpeg
    module = _load(module_name)
    # 別のサンプルのウィンドウを閉じ、そのサンプルが退避したHUDを先に元へ戻す。
    _load("demo_interactive").closeDemoWindows()
    module.main(record=record, **(options or {}))
    if record:
        print("Recorded. See .maya-output/verification/ in the workspace.")
    else:
        print("Sample built. Play or scrub the timeline to see the HUD update.")


def check(module_name, options=None):
    """検証を実行する。

    Args:
        module_name (str): ``tools`` 内の検証のモジュール名。
        options (dict | None): 検証の main へ渡す引数。
    """
    if not _confirmNewScene():
        return
    module = _load(module_name)
    _load("demo_interactive").closeDemoWindows()
    try:
        folder = module.main(**(options or {}))
    except Exception as error:
        cmds.warning("Check failed: {}".format(error))
        raise
    print("Check passed. Report: {}".format(folder))


def show():
    """サンプル一覧のウィンドウを開く。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    # サンプルが多いので、高さを決めてスクロールできるようにする。前回の大きさは使わない。
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    cmds.window(WINDOW, title="Tail Avoidance Samples", widthHeight=(560, 720), sizeable=True)
    cmds.scrollLayout(childResizable=True, horizontalScrollBarThickness=0, verticalScrollBarThickness=14)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    cmds.text(label="One-axis (rotateX) tail avoidance samples", align="left", font="boldLabelFont", height=24)
    cmds.text(label="Each button replaces the current scene. Save your work first.", align="left")
    for module_name, title, description, options in SAMPLES:
        cmds.separator(style="in", height=10)
        cmds.text(label=title, align="left", font="boldLabelFont")
        # 折り返した説明文は Maya が1行分の高さで数え、スクロールの範囲が足りなくなるので高さを決める。
        cmds.text(label=description, align="left", wordWrap=True, height=36)
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(250, 250), adjustableColumn=1)
        cmds.button(label="Build (play / scrub)", height=28,
                    command=lambda *_, m=module_name, o=options: run(m, record=False, options=o))
        cmds.button(label="Record video", height=28,
                    command=lambda *_, m=module_name, o=options: run(m, record=True, options=o))
        cmds.setParent("..")
    cmds.separator(style="in", height=14)
    cmds.text(label="Checks", align="left", font="boldLabelFont", height=24)
    for module_name, title, description, options in CHECKS:
        cmds.text(label=title, align="left", font="boldLabelFont")
        # 折り返した説明文は Maya が1行分の高さで数え、スクロールの範囲が足りなくなるので高さを決める。
        cmds.text(label=description, align="left", wordWrap=True, height=36)
        cmds.button(label="Run check", height=28, command=lambda *_, m=module_name, o=options: check(m, o))
    cmds.separator(style="none", height=6)
    cmds.showWindow(WINDOW)
    cmds.window(WINDOW, edit=True, widthHeight=(560, 720))


if __name__ == "__main__":
    show()
