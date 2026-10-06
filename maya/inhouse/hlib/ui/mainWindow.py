"""Mayaのメインウィンドウ名を取得する。"""


class MainWindow:
    """Maya標準UIの名前を照会する。ウィジェットへの変換は利用側で行う。"""

    @staticmethod
    def getName():
        """Mayaメニューの親に指定するメインウィンドウ名を取得する。

        Returns:
            str | None: MayaのUI名。バッチ実行時はNone。
        """
        from maya import cmds, mel

        if cmds.about(batch=True):
            return None
        return mel.eval("$hlibMainWindow = $gMainWindow")
