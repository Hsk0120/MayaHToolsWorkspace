"""Maya の IK ハンドルを Transform として扱う。"""

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias
from .transform import Transform


class IkHandle(Transform):
    """極ベクトル拘束の作成を含む Transform 操作に対応する IK ハンドル。"""

    def getEndJoint(self):
        """IK チェーンの末端 joint を取得する。

        ikEffector ノードの translate 接続元を辿って end joint を特定する
        （``cmds.ikHandle(query=True, jointList=True)`` は end joint を含まない
        ため、別経路で解決する）。

        Returns:
            Joint | None: end joint。接続が見つからない場合は ``None``。
        """
        from .joint import Joint

        effector_plug = self.getPlug("endEffector").getSourceWithConversion()
        if effector_plug is None:
            return None
        source = effector_plug.getNode().getPlug("translateX").getSourceWithConversion()
        if source is None:
            return None
        return Joint(source.getNode().getFullName())

    def getJoints(self, include_tip=False):
        """IK チェーンを構成する joint を start joint から順に取得する。

        Args:
            include_tip (bool): True の場合、末端 joint(``getEndJoint()``)も
                末尾に含める。``cmds.ikHandle(query=True, jointList=True)`` は
                既定では末端 joint を含まない。

        Returns:
            list[Joint]: start joint から順に並んだ joint。ハンドルが無効な場合は
                空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        from .joint import Joint

        if not self.isValid():
            raise RuntimeError("Cannot query the joint list of an invalid IK handle")
        names = cmds.ikHandle(self.getFullName(), query=True, jointList=True) or []
        joints = [Joint(name) for name in names]
        if include_tip:
            tip = self.getEndJoint()
            if tip is not None:
                joints.append(tip)
        return joints

    @_getter_alias(getEndJoint)
    def endJoint(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getEndJoint(*args, **kwargs)

    @_getter_alias(getJoints)
    def joints(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getJoints(*args, **kwargs)
