"""ドキュメント用のスクリーンショットを撮る GUI スイート(専用の Maya GUI 内で実行される)。

``run_capture.py`` から ``run_hlib_gui_versions.run_version`` 経由で起動する。単体では実行しない。
"""
import json
from pathlib import Path
import traceback


def main(output_dir, finished):
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtGui.QAction
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtWidgets.QAction

    directory = Path(output_dir)
    result = {"status": "error", "images": []}

    def wait(milliseconds):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def save(pixmap, name):
        assert pixmap.save(str(directory / name)), name
        result["images"].append(name)

    def find_menu(window, title):
        for menu in window.findChildren(QtWidgets.QMenu):
            if menu.title().replace("&", "") == title:
                return menu
        raise LookupError(title)

    def find_action(menu, text):
        for action in menu.actions():
            if action.text().replace("&", "") == text:
                return action
        raise LookupError(text)

    try:
        from maya.api import OpenMaya as om
        import runpy
        # GUIランナーは全userSetupを抑止するので、.modの起動入口(loadPluginだけ)を明示実行する。
        # hedit.*はhedit.mllに同梱されており、プラグインのロード後にimportできる。
        runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "userSetup.py"))
        wait(300)
        import hedit
        hedit.show(floating=True)
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
        import hedit_host
        window = hedit_host.editor()
        # 編集画面はworkspaceControlに直接入る。浮動ウィンドウ本体は window.window()。
        host = window
        try:
            host.window().resize(1280, 860)
        except Exception:
            host.resize(1280, 860)
        host.window().raise_()
        host.window().activateWindow()
        wait(600)
        tabs = window.findChild(QtWidgets.QTabWidget)
        splitter = window.findChild(QtWidgets.QSplitter, "editorSplitter")

        # Maya の起動処理の出力が落ち着くのを待ち、履歴を消してから、種別ごとの色が出る内容を流す。
        wait(3500)
        find_action(find_menu(window, "History"), "Clear output").trigger()
        wait(200)
        output = window.findChild(QtWidgets.QPlainTextEdit, "output")
        om.MGlobal.displayInfo("scene loaded: sample_rig.ma")
        print("print() の出力は通常の色です")
        om.MGlobal.displayWarning("joint 'arm_L' has no skin weights")
        om.MGlobal.displayError("cmds.setAttr: attribute 'foo.bar' was not found")
        cmds.polyCube(name="hedit_doc_cube")
        cmds.warning("cmds.warning() の警告も黄色で表示されます")
        wait(300)
        output.verticalScrollBar().setValue(output.verticalScrollBar().maximum())
        tabs.setCurrentIndex(0)
        code = tabs.currentWidget()
        code.setFocus()

        # トップページ用: タイトルバーごと、少し横長の小さなウィンドウで撮り、周囲に余白を付ける。
        top = host.window()
        top.resize(940, 470)
        splitter.setSizes([150, 170])
        # 他のウィンドウに隠れないよう、撮影の間だけ最前面に固定する(画面上の実際の見た目を撮るため)。
        top.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        top.show()
        top.raise_()
        top.activateWindow()
        wait(1200)
        def save_framed(name):
            screen = top.screen()
            frame = top.frameGeometry()
            origin = screen.geometry().topLeft()
            shot = screen.grabWindow(0, frame.x() - origin.x(), frame.y() - origin.y(), frame.width(), frame.height())
            # 枠の外側の1〜2pxには背後のウィンドウが写り込むため、上端を切り落とす。
            shot = shot.copy(0, 2, shot.width(), shot.height() - 2)
            margin = 28
            canvas = QtGui.QPixmap(shot.width() + margin * 2, shot.height() + margin * 2)
            canvas.fill(QtGui.QColor("#1b1e22"))
            painter = QtGui.QPainter(canvas)
            painter.drawPixmap(margin, margin, shot)
            painter.end()
            save(canvas, name)

        save_framed("main.png")
        # トップページ用: Explorer を隠した版。
        explorer = find_action(find_menu(window, "View"), "Explorer")
        explorer.trigger()
        wait(900)
        save_framed("top.png")
        explorer.trigger()
        wait(400)
        top.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
        top.show()
        top.resize(1280, 860)
        splitter.setSizes([260, 560])
        wait(500)
        code.setFocus()

        # 補完: cmds. の後の候補一覧。ポップアップは別ウィンドウなので、本体の画像へ重ねて保存する。
        code.setPlainText("import maya.cmds as cmds\n\ncmds.")
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        completer = code.findChild(QtWidgets.QCompleter)
        popup = completer.popup()
        # 初回は補完の索引を作る非同期の走査があるため、候補が出るまで繰り返す。
        for _attempt in range(10):
            host.window().activateWindow()
            code.setFocus()
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
            wait(900)
            if popup.isVisible():
                break
        assert popup.isVisible(), "completion popup was not shown"
        base = window.grab()
        painter = QtGui.QPainter(base)
        origin = window.mapFromGlobal(popup.mapToGlobal(QtCore.QPoint(0, 0)))
        painter.drawPixmap(origin, popup.grab())
        painter.end()
        save(base, "completion.png")
        popup.hide()

        # Preferences メニュー(全 13 項目)。
        code.setPlainText("import maya.cmds as cmds\n")
        menu = find_menu(window, "Preferences")
        menu.popup(window.mapToGlobal(QtCore.QPoint(80, 40)))
        wait(300)
        save(menu.grab(), "preferences-menu.png")
        menu.hide()
        wait(100)

        # 検索と置換。
        code.setPlainText("import maya.cmds as cmds\n\nfor name in cmds.ls(type='joint'):\n    cmds.setAttr(name + '.radius', 1.0)\n")
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_H, QtCore.Qt.ControlModifier)
        wait(300)
        find = None
        for line in window.findChildren(QtWidgets.QLineEdit):
            if line.isVisible():
                find = line
                break
        assert find is not None, "find bar was not shown"
        find.setText("cmds")
        wait(300)
        save(window.grab(), "find-replace.png")
        QtTest.QTest.keyClick(find, QtCore.Qt.Key_Escape)
        wait(200)

        # 静的解析(オンにして、構文エラーのあるコードを置く)。
        static = window.findChild(QAction, "option_staticAnalysis")
        static.setChecked(True)
        code = tabs.currentWidget()
        code.setPlainText("def build_rig(:\n    return 1\n\nprint('done')\n")
        code.setFocus()
        wait(1600)
        save(window.grab(), "static-analysis.png")
        static.setChecked(False)
        wait(200)

        # スペルチェック(既定でオン。つづりの誤りに波線が付く)。
        code.setPlainText("# recieve the selectd joints and rename them\nsecond_joint_name = 'arm_joint'\n")
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        wait(1400)
        save(window.grab(), "spell-check.png")

        # 空白とタブの表示。
        whitespace = window.findChild(QAction, "option_whitespace")
        whitespace.setChecked(True)
        code.setPlainText("def move(node):\n\tcmds.xform(node, t=(0, 1, 0))  \n    return node\n")
        wait(400)
        save(window.grab(), "whitespace.png")
        whitespace.setChecked(False)

        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    finished(result)
