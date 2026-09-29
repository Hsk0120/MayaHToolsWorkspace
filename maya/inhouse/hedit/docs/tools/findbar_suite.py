"""検索バーを VS Code と同じ5つの状態で撮る GUI スイート(専用の Maya GUI 内で実行される)。

``findbar_compare.py`` から起動される。撮る状態と名前は ``vscode_capture/find_replace.json`` と同じ。
環境変数 ``HEDIT_VSCODE_CAPTURE`` に VS Code の画像のフォルダがあれば、上に VS Code、下に hedit を
並べた比較画像(``compare_<名前>.png``)も作る。VS Code の画像から切り出す範囲は ``HEDIT_VSCODE_CROP``
(``x,y,幅,高さ``)。
"""
import json
import os
from pathlib import Path
import traceback

PROJECT = Path(__file__).resolve().parents[2]

#: VS Code の手順(find_replace.json)と同じ本文。
SAMPLE = ("import maya.cmds as cmds\n\nnodes = cmds.ls(selection=True)\n"
          "for node in nodes:\n    cmds.select(node, add=True)\n")

#: 比較画像の拡大率(細部を見やすくするため、画素をそのまま拡大する)。
SCALE = 3


def main(output_dir, finished):
    """5つの状態を撮り、比較画像を作る。

    Args:
        output_dir (str): 画像と ``result.json`` の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了は呼び出し元が行う)。
    """
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtGui.QAction
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtWidgets.QAction

    directory = Path(output_dir)
    result = {"status": "error", "images": [], "info": {}}

    def wait(milliseconds):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def label(text, width):
        """比較画像の見出しの帯を作る。"""
        image = QtGui.QPixmap(width, 40)
        image.fill(QtGui.QColor("#111111"))
        painter = QtGui.QPainter(image)
        painter.setPen(QtGui.QColor("#ffffff"))
        font = QtGui.QFont("Segoe UI")
        font.setPixelSize(20)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(10, 0, width - 10, 40), QtCore.Qt.AlignVCenter, text)
        painter.end()
        return image

    def compose(name, hedit_image):
        """VS Code の画像があれば、上下に並べた比較画像を作る。"""
        vscode_dir = os.environ.get("HEDIT_VSCODE_CAPTURE")
        source = Path(vscode_dir or "") / "vscode_{}.png".format(name)
        if not vscode_dir or not source.is_file():
            return
        crop = [int(value) for value in os.environ.get("HEDIT_VSCODE_CROP", "425,88,440,76").split(",")]
        vscode_image = QtGui.QPixmap(str(source)).copy(QtCore.QRect(*crop))
        parts = [(vscode_image, "VS Code : " + name), (hedit_image, "hedit : " + name)]
        parts = [(image.scaled(image.width() * SCALE, image.height() * SCALE, QtCore.Qt.IgnoreAspectRatio,
                               QtCore.Qt.FastTransformation), text) for image, text in parts]
        width = max(image.width() for image, _ in parts)
        height = sum(image.height() + 40 for image, _ in parts)
        sheet = QtGui.QPixmap(width, height)
        sheet.fill(QtGui.QColor("#111111"))
        painter = QtGui.QPainter(sheet)
        y = 0
        for image, text in parts:
            painter.drawPixmap(0, y, label(text, width))
            painter.drawPixmap(0, y + 40, image)
            y += image.height() + 40
        painter.end()
        path = "compare_{}.png".format(name)
        assert sheet.save(str(directory / path)), path
        result["images"].append(path)

    try:
        import runpy
        import sys
        runpy.run_path(str(PROJECT / "scripts" / "userSetup.py"))
        wait(300)
        import hedit
        hedit.show(floating=True)
        sys.path.insert(0, str(PROJECT / "tests"))
        import hedit_host
        window = hedit_host.editor()
        window.window().resize(1000, 520)
        window.window().raise_()
        window.window().activateWindow()
        wait(600)
        tabs = window.findChild(QtWidgets.QTabWidget)
        code = tabs.currentWidget()
        code.setPlainText(SAMPLE)
        bar = window.findChild(QtWidgets.QWidget, "findBar")
        find = window.findChild(QtWidgets.QLineEdit, "findText")
        replace = window.findChild(QtWidgets.QLineEdit, "replaceText")
        bubble = tabs.findChild(QtWidgets.QLabel, "findError")
        count = window.findChild(QtWidgets.QLabel, "searchCount")
        button = {name: window.findChild(QtWidgets.QAbstractButton, name)
                  for name in ("searchCase", "searchWord", "searchRegex")}
        replace_action = next(a for a in window.findChildren(QAction) if a.text() == "Replace…")

        def shoot(name):
            wait(350)
            bottom = bar.geometry().bottom()
            if bubble is not None and bubble.isVisible():
                bottom = max(bottom, bubble.geometry().bottom())
            region = QtCore.QRect(bar.x() - 8, bar.y() - 8, bar.width() + 16, bottom - bar.y() + 18)
            image = tabs.grab(region)
            assert image.save(str(directory / "hedit_{}.png".format(name))), name
            result["images"].append("hedit_{}.png".format(name))
            result["info"][name] = {"bar": [bar.x(), bar.y(), bar.width(), bar.height()],
                                    "input": [find.parentWidget().width(), find.parentWidget().height()],
                                    "count": count.text()}
            compose(name, image)

        # VS Code の手順と同じく、3行目の「cmds」を選択してから置換を開く。
        cursor = code.textCursor()
        block = code.document().findBlockByNumber(2)
        cursor.setPosition(block.position() + 8)
        cursor.setPosition(block.position() + 12, QtGui.QTextCursor.KeepAnchor)
        code.setTextCursor(cursor)
        replace_action.trigger()
        replace.setText("hlib")
        find.setFocus()
        find.selectAll()
        shoot("1_find_focused")
        replace.setFocus()
        shoot("2_replace_focused")
        find.setFocus()
        button["searchCase"].setChecked(True)
        button["searchWord"].setChecked(True)
        shoot("3_toggles_on")
        button["searchCase"].setChecked(False)
        button["searchWord"].setChecked(False)
        find.setText("")
        QtTest.QTest.keyClicks(find, "zzz")
        shoot("4_no_results")
        button["searchRegex"].setChecked(True)
        find.setText("")
        QtTest.QTest.keyClicks(find, "(")
        shoot("5_invalid_regex")
        button["searchRegex"].setChecked(False)
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    finished(result)
