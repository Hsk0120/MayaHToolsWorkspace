"""Maya の IK ハンドルを Transform として扱う。"""

import maya.cmds as cmds

from .._core.registry import node_wrapper
from .transform import Transform


@node_wrapper("ikHandle")
class IkHandle(Transform):
    """極ベクトル拘束の作成を含む Transform 操作に対応する IK ハンドル。"""

    def get_end_joint(self):
        """IK チェーンの末端 joint を取得する。

        ikEffector ノードの translate 接続元を辿って end joint を特定する
        （``cmds.ikHandle(query=True, jointList=True)`` は end joint を含まない
        ため、別経路で解決する）。

        Returns:
            Joint | None: end joint。接続が見つからない場合は ``None``。
        """
        from .joint import Joint

        effector_plug = self.plug("endEffector").source()
        if effector_plug is None:
            return None
        source = effector_plug.node.plug("translateX").source()
        if source is None:
            return None
        return Joint(source.node.full_name)

    def get_joint_list(self, include_tip=False):
        """IK チェーンを構成する joint を start joint から順に取得する。

        Args:
            include_tip (bool): True の場合、末端 joint(``get_end_joint()``)も
                末尾に含める。``cmds.ikHandle(query=True, jointList=True)`` は
                既定では末端 joint を含まない。

        Returns:
            list[Joint]: start joint から順に並んだ joint。ハンドルが無効な場合は
                空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        from .joint import Joint

        if not self.is_valid():
            raise RuntimeError("Cannot query the joint list of an invalid IK handle")
        names = cmds.ikHandle(self.full_name, query=True, jointList=True) or []
        joints = [Joint(name) for name in names]
        if include_tip:
            tip = self.get_end_joint()
            if tip is not None:
                joints.append(tip)
        return joints
