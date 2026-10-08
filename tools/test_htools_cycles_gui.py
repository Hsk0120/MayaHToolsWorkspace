"""起動中Mayaへ送信し、シーンを変更せずサイクル調査UIを検証する。"""

from pathlib import Path
from unittest import mock

import maya.cmds as cmds

from HTools.rigging import inspectCycles
from hlib import logger


def main():
    """画面・空結果・エラー表示を検証し、未調査の画面を残す。"""
    ui = inspectCycles.run()
    result = dict(targets=None, includeDag=True, seconds=10, elapsed=0,
                  firstOnly=False, groups=[])
    with mock.patch.object(inspectCycles, "inspectCycles", return_value=result):
        ui.scan()
        assert "0" in cmds.text(ui.status, query=True, label=True)
        assert "Maya" in cmds.scrollField(ui.details, query=True, text=True)
        assert cmds.button(ui.scan_button, query=True, enable=True)
    output_dir = Path(__file__).resolve().parents[1] / ".maya-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "cycle-inspector-test.txt"
    with mock.patch.object(cmds, "fileDialog2", return_value=[str(report)]):
        ui.saveReport()
    assert report.read_text(encoding="utf-8") == inspectCycles.formatReport(result)
    with mock.patch.object(inspectCycles, "inspectCycles", side_effect=ValueError("入力エラーテスト")):
        ui.scan()
        assert ui.result is None
        assert cmds.button(ui.scan_button, query=True, enable=True)
        assert cmds.text(ui.status, query=True, label=True) == "Inspection failed"
    # QtはHTools側の検証でだけ使用し、hlibには持ち込まない。
    import maya.OpenMayaUI as omui
    try:
        from PySide6 import QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtWidgets
        from shiboken2 import wrapInstance
    ui = inspectCycles.run()
    QtWidgets.QApplication.processEvents()
    widget = wrapInstance(int(omui.MQtUtil.findWindow(ui.window)), QtWidgets.QWidget)
    output = Path(__file__).resolve().parents[1] / ".maya-output/cycle-inspector.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    assert widget.grab().save(str(output))
    logger.info("サイクル調査GUI: 空結果・保存・失敗後の復帰・画面生成 passed")


if __name__ == "__main__":
    main()
