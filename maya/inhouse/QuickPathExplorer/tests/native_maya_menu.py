"""専用Maya GUIでWindowsメニュー起動と自動復元の違いを確認する。"""
import json
from pathlib import Path


def run(output, fixture):
    """ロード済み製品と専用prefsで実行し、結果とQt描画の証拠を返す。

    Args:
        output: 専用の証拠フォルダー。
        fixture: 専用の参照フォルダー。

    Returns:
        dict: 実行したケースとウィンドウ寸法。
    """
    from maya import cmds, mel, OpenMayaUI
    try:
        from PySide6 import QtCore, QtWidgets, QtGui
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtWidgets, QtGui
        from shiboken2 import wrapInstance

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    control = "QuickPathExplorerWorkspaceControl"
    menu = "quickPathExplorerWindowMenuItem"
    main = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
    main.showNormal()
    main.move(40, 40)
    main.resize(1500, 1000)
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    frame_number = [0]
    # 検証用PySideラッパーのGCで子ラッパーが無効にならないよう、テスト終了まで保持する。
    wrappers = []
    timer = QtCore.QTimer(main)

    def record():
        """ホストのQt描画を記録する。実OS入力の録画とは区別する。"""
        image = main.grab()
        if cmds.workspaceControl(control, exists=True) and cmds.workspaceControl(control, query=True, floating=True):
            floating = shell()
            painter = QtGui.QPainter(image)
            painter.drawPixmap(floating.mapToGlobal(QtCore.QPoint()) - main.mapToGlobal(QtCore.QPoint()), floating.grab())
            painter.end()
        image.save(str(frames / ("frame-%05d.png" % frame_number[0])))
        frame_number[0] += 1

    timer.timeout.connect(record)
    timer.start(200)

    def settle():
        """Mayaの親変更とQPEの遅延配置を完了させる。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(1000, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def shell():
        """Mayaによる親の再生成後も、現在のフロートを取得する。"""
        parent = wrapInstance(int(OpenMayaUI.MQtUtil.findControl(control)), QtWidgets.QWidget)
        window = parent.window()
        wrappers.extend((parent, window))
        return window

    rows = []

    def open_menu(label):
        """登録された実際のメニューコマンドを実行し、位置と内容保持を確認する。"""
        command = cmds.menuItem(menu, query=True, command=True)
        assert "-menu" in command, command
        mel.eval(command)
        settle()
        assert cmds.workspaceControl(control, query=True, floating=True)
        frame = shell().frameGeometry()
        area = main.screen().availableGeometry().adjusted(20, 20, -20, -20)
        expected = QtCore.QRect(frame)
        expected.moveCenter(main.frameGeometry().center())
        expected.moveLeft(max(area.left(), min(expected.left(), area.right() - frame.width() + 1)))
        expected.moveTop(max(area.top(), min(expected.top(), area.bottom() - frame.height() + 1)))
        assert (frame.topLeft() - expected.topLeft()).manhattanLength() <= 3, (frame, expected)
        assert abs(shell().width() - min(1200, area.width())) <= 2
        assert abs(shell().height() - min(800, area.height())) <= 2
        assert cmds.quickPathExplorer("-status").replace("\\", "/") == Path(fixture).as_posix()
        widget = shell().findChild(QtWidgets.QWidget, "qpeNativeWindow")
        split = widget.findChild(QtWidgets.QSplitter, "browserVertical")
        assert abs(split.sizes()[0] - split.sizes()[1]) <= 2
        rows.append({"case": label, "pass": True, "frame": [frame.x(), frame.y(), frame.width(), frame.height()], "areas": split.sizes()})
        shell().grab().save(str(output / (label + ".png")))

    try:
        # 先に通常入口を予約し、中央表示より後に古い位置復元が適用されないことも確認する。
        settle()
        cmds.quickPathExplorer("-path", Path(fixture).as_posix())
        open_menu("initial-pending-restore")
        shell().resize(500, 300)
        shell().move(10, 10)
        open_menu("moved-floating")
        cmds.workspaceControl(control, edit=True, dockToControl=("TimeSlider", "top"))
        settle()
        assert not cmds.workspaceControl(control, query=True, floating=True)
        cmds.quickPathExplorer("-saveLayout")
        cmds.quickPathExplorer("-startup")
        settle()
        assert not cmds.workspaceControl(control, query=True, floating=True)
        rows.append({"case": "startup-preserves-dock", "pass": True})
        open_menu("visible-docked")
        cmds.workspaceControl(control, edit=True, dockToControl=("TimeSlider", "top"))
        cmds.workspaceControl(control, edit=True, close=True)
        open_menu("closed-docked")
        for _ in range(3):
            mel.eval(cmds.menuItem(menu, query=True, command=True))
        open_menu("repeated-menu")
    finally:
        timer.stop()
    result = {"maya": cmds.about(version=True), "qt": QtCore.qVersion(), "evidence": "Maya GUI, programmatic actual menu command", "checks": rows}
    (output / "menu-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
