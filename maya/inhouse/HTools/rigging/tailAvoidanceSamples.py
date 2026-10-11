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
    ("demo_joint_chain_rbf", "Spine/arm chain: cone driver approximation",
     "Spheres vs cones from the elbow (fixed angle / angle scaled by distance), all feeding the same UE RBF.",
     {"case": "cone_c"}),
    ("demo_cone_rbf", "ConeReader weights (0-1) as RBF drivers",
     "Three ConeReader outputs drive UE RBF, compared with the geometry-driven RBF. Shows where it fails.", {}),
    ("demo_joint_sweep_compare", "Method comparison (5 columns)",
     "Input / nearest tangent / outside sweep / early turn / cone push, side by side.", {}),
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


def show():
    """サンプル一覧のウィンドウを開く。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.window(WINDOW, title="Tail Avoidance Samples", widthHeight=(520, 10), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    cmds.text(label="One-axis (rotateX) tail avoidance samples", align="left", font="boldLabelFont", height=24)
    cmds.text(label="Each button replaces the current scene. Save your work first.", align="left")
    for module_name, title, description, options in SAMPLES:
        cmds.separator(style="in", height=10)
        cmds.text(label=title, align="left", font="boldLabelFont")
        cmds.text(label=description, align="left", wordWrap=True)
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(250, 250), adjustableColumn=1)
        cmds.button(label="Build (play / scrub)", height=28,
                    command=lambda *_, m=module_name, o=options: run(m, record=False, options=o))
        cmds.button(label="Record video", height=28,
                    command=lambda *_, m=module_name, o=options: run(m, record=True, options=o))
        cmds.setParent("..")
    cmds.separator(style="none", height=6)
    cmds.showWindow(WINDOW)
    cmds.window(WINDOW, edit=True, resizeToFitChildren=True)


if __name__ == "__main__":
    show()
