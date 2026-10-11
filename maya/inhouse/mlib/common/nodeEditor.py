"""Maya標準のノードエディターを開く。"""


class NodeEditor:
    """標準エディターの起動を共通の入口で提供する。"""

    @staticmethod
    def show():
        """Maya標準のノードエディターを開く。

        ウィンドウの所有権と既存パネルの再利用はMaya側で管理する。
        UI操作なのでシーンのUndo対象にはならない。

        Raises:
            RuntimeError: バッチ実行中、またはMayaが起動を拒否した場合。
        """
        from maya import cmds, mel

        if cmds.about(batch=True):
            raise RuntimeError("NodeEditor requires Maya GUI")
        mel.eval("NodeEditorWindow;")
