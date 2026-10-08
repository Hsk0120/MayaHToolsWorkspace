"""Mayaのメインウィンドウ名を取得する。"""

from .._core.getterAlias import _getter_alias


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

    @classmethod
    @_getter_alias(getName, static=True)
    def name(cls, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return cls.getName(*args, **kwargs)
