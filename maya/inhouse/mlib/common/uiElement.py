"""Mayaのmenu/menuItemを保持するUI参照。"""


class UiElement:
    """Maya所有のUI名を保持する。Nodeとは区別し、シーンUndo対象外。"""

    def __init__(self, name, kind):
        """名前とUI種別を保持する。

        Args:
            name (str): MayaのUIパス。
            kind (str): menuまたはmenuItem。
        """
        if kind not in ("menu", "menuItem") or not name:
            raise ValueError("Expected a menu or menuItem name")
        self._name, self._kind = str(name), kind

    def __str__(self):
        """Maya UI名を返す。

        Returns:
            str: Maya UI名を返す。
        """
        return self._name

    @property
    def name(self):
        """str: 保持しているMaya UI名を返す。"""
        return self._name

    def exists(self):
        """Maya上にUIが存在するか照会する。

        Returns:
            bool: Maya上にUIが存在するか照会する。
        """
        import maya.cmds as cmds

        return bool(getattr(cmds, self._kind)(self._name, exists=True))

    def delete(self):
        """自身のUIを削除する。シーンUndoは作らない。

        Returns:
            None: 値を返さない。
        """
        import maya.cmds as cmds

        cmds.deleteUI(self._name, **{self._kind: True})
