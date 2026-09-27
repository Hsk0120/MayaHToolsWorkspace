"""MayaのメインウィンドウをQtの親として取得する。"""


class MainWindow:
    """Qtの版とOpenMayaUIのポインター変換を共通化する。"""

    @staticmethod
    def widget():
        """現在のMayaメインウィンドウを取得する。

        Qtは呼出時だけ読み込み、PySide6を優先してPySide2へフォールバックする。
        ウィンドウの所有権はMayaにあり、呼出側で削除しない。

        Returns:
            QWidget | None: Maya所有のウィンドウ。バッチや未作成時はNone。
        """
        from maya import cmds, OpenMayaUI

        if cmds.about(batch=True):
            return None
        pointer = OpenMayaUI.MQtUtil.mainWindow()
        if not pointer:
            return None
        try:
            from PySide6 import QtWidgets
            from shiboken6 import wrapInstance
        except ImportError:
            from PySide2 import QtWidgets
            from shiboken2 import wrapInstance
        return wrapInstance(int(pointer), QtWidgets.QWidget)

    @staticmethod
    def name():
        """Mayaメニューの親に指定するメインウィンドウ名を取得する。

        Returns:
            str | None: MayaのUI名。バッチ実行時はNone。
        """
        from maya import cmds, mel

        if cmds.about(batch=True):
            return None
        return mel.eval("$hlibMainWindow = $gMainWindow")
