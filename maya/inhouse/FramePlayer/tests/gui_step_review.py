"""専用Maya GUIで通常版とmlib版のコマ打ち表示を検査する。"""

import json
import shutil
import sys
from pathlib import Path

import maya.cmds as cmds
import maya.OpenMayaUI as omui
from PySide6 import QtWidgets
from shiboken6 import wrapInstance


def main(output_dir, finished):
    """時刻・キーを保持したままステップ区間と番号を表示することを確かめる。"""
    product = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(product.parent))
    transform = cmds.createNode("transform")
    for frame in (-2, 2, 5):
        cmds.setKeyframe(transform, attribute="tx", time=frame, value=frame, outTangentType="step")
    overlay = output_dir / "byMlib"
    shutil.copytree(product / "python/frameplayer", overlay / "frameplayer", ignore=shutil.ignore_patterns("__pycache__"))
    for module_path in (product / "byMlib/python/frameplayer").glob("*.py"):
        shutil.copy2(module_path, overlay / "frameplayer")
    for variant in (product / "python", overlay):
        sys.path.insert(0, str(variant))
        from frameplayer import ui
        window = ui.show()
        widget = wrapInstance(int(omui.MQtUtil.findWindow(window)), QtWidgets.QWidget)
        button, = [b for b in widget.findChildren(QtWidgets.QPushButton) if b.text() == "Inspect stepped keys at current frame"]
        cmds.intField(ui._controls["offset"], edit=True, value=7)
        cmds.floatField(ui._controls["multiplier"], edit=True, value=2)
        cmds.currentTime(-0.5)
        cmds.select(transform)
        button.click()
        report = cmds.scrollField(ui._controls["review"], query=True, text=True)
        assert "Mapped player frame 6" in report and "step [-2, 2)  +1.5f" in report, report
        assert cmds.currentTime(query=True) == -0.5
        cmds.currentTime(5)
        button.click()
        assert "No stepped interval" in cmds.scrollField(ui._controls["review"], query=True, text=True)
        assert cmds.keyframe(transform, query=True, timeChange=True) == [-2, 2, 5]
        cmds.deleteUI(window)
        sys.path.pop(0)
        for module in list(sys.modules):
            if module == "frameplayer" or module.startswith("frameplayer."):
                del sys.modules[module]
    result = {"status": "passed", "variants": ["standard", "byMlib"]}
    (output_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    finished(result)

