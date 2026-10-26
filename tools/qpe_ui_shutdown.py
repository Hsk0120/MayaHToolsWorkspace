"""専用MayaでQPEを再生成し、プロセス終了まで検証するためのスイート。"""
import json
import os
from pathlib import Path
import sys


def main(output_dir, finished):
    """専用ランナーのPIDを確認し、通常終了またはDLL終了経路を試す。

    Args:
        output_dir (Path): ランナーが作成した専用証拠フォルダー。
        finished (callable): 通常のMaya終了を予約するランナーの通知先。
    """
    out = Path(output_dir)
    launch = json.loads((out / "launch.json").read_text(encoding="utf-8"))
    if launch["pid"] != os.getpid() or os.environ.get("QPE_SHUTDOWN_TEST") != "1":
        raise RuntimeError("Run only through qpe_shutdown_runner.py in its disposable Maya")
    mode = os.environ["QPE_SHUTDOWN_MODE"]
    if mode not in ("normal", "abrupt"):
        raise ValueError("Unknown shutdown mode")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    # 通常PythonからMaya/PySideを読み込まないため、専用GUI内でimportする。
    from maya import cmds
    from qpeQt import QtCore, QtGui, QtWidgets, shiboken
    from qpe_ui_maya import pause, waitFor
    import qpeHost

    os.environ["QPE_SETTINGS_FILE"] = str(out / "qpe-settings.json")
    fixtures = out / "fixtures"
    fixtures.mkdir()
    for name in ("Assets", "Scenes", "Textures"):
        (fixtures / name).mkdir()
    peer = QtWidgets.QLineEdit("Independent Qt text")
    peer.show()
    application = QtWidgets.QApplication.instance()
    host_style = application.style()
    host_font = application.font().toString()
    rows = []
    frames = out / "frames"
    frames.mkdir()
    for cycle in range(8):
        widget = qpeHost.show(str(fixtures))
        widget.folderTabs.add()
        widget.setInspectorVisible(cycle % 2 == 0)
        pause(250)
        waitFor(lambda: QtCore.QThreadPool.globalInstance().activeThreadCount() == 0)
        folder_index = widget.folderModel.index(str(fixtures))
        # ワーカー終了直後でもqueued signalの反映はまだの場合がある。
        # 実際に項目を描画した後の参照を検査し、読込中だけの合格を防ぐ。
        waitFor(lambda: widget.folderModel.rowCount(folder_index) == 3)
        pause(100)
        # 全アプリのstyleを置き換えず、QPE専用スタイルだけを所有していること。
        assert widget._columnStyle.parent() is widget.columns
        assert application.style() is host_style
        assert application.font().toString() == host_font
        assert shiboken.isValid(peer) and peer.text() == "Independent Qt text"
        canvas = QtGui.QPixmap(1280, 860)
        canvas.fill(QtGui.QColor("#202124"))
        painter = QtGui.QPainter(canvas)
        painter.setPen(QtGui.QColor("white"))
        font = painter.font()
        font.setPixelSize(24)
        painter.setFont(font)
        painter.drawText(20, 35, "Maya %s | Qt automated recreation %d / 8" % (launch["version"], cycle + 1))
        painter.drawPixmap(20, 70, widget.grab().scaled(1240, 770, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        painter.end()
        canvas.save(str(frames / ("%03d.png" % cycle)))
        # 再現ダンプの原因は、QWidget.style()が残す共有QStyleSheetStyle参照。
        # 既にあるラッパーの情報だけを読み、style()/metaObject()で新規参照を作らない。
        native_style_references = []
        for view in [widget, widget.columns] + widget.columns.findChildren(QtWidgets.QListView):
            dump = shiboken.dump(view)
            if any('"__style__"' in line and "QCommonStyle" in line for line in dump.splitlines()):
                native_style_references.append({"class": type(view).__name__, "dump": dump})
        assert not native_style_references, native_style_references
        rows.append({"cycle": cycle + 1, "other_qt_text_preserved": True,
                     "global_style_and_font_preserved": True, "native_style_references": native_style_references})
        if cycle != 7:
            cmds.deleteUI(qpeHost.CONTROL)
            pause(100)
            # 入れ子のイベントループだけではDeferredDeleteが未処理のことがある。
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            assert not shiboken.isValid(widget)
    result = {"status": "passed", "mode": mode, "cycles": rows,
              "expected_exit": 23 if mode == "abrupt" else 0,
              "input_kind": "Qt programmatic GUI; exit result is evaluated by parent process"}
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if mode == "abrupt":
        # このランナー所有プロセスだけ。DLLデストラクターは通るがMayaのquitは通らない。
        # TerminateProcessによる外部強制終了とは別の厳しい破棄順序を再現する。
        os._exit(23)
    finished(result)
