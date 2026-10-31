"""コントローラーのオフセット階層と編集チャンネルを構成する。"""

import mlib
from mlib.decorator import undoChunk


class ControlHierarchy:
    """リグで使用するTransform階層の複合セットアップ。"""

    @staticmethod
    @undoChunk("mlrigControlHierarchyCreateOffsetGroups")
    def createOffsetGroups(target, *names, fast=False):
        """現在のワールド姿勢に一致するオフセットグループで対象を包む。

        Args:
            target (Transform | str): 包む対象。
            *names (str): 外側から内側へのグループ名。省略時は対象名+_offset。
            fast (bool): Trueは対応するmlibのOpenMaya操作を使い、Undoなし。
                Joint・インスタンスの再親付けは未対応。

        Returns:
            list[Transform]: 外側から内側への作成したグループ。

        Raises:
            TypeError: targetがTransformでない、またはfastがboolでない場合。
            NotImplementedError: fastで未対応の再親付けの場合。

        通常は一回のUndoで戻せる。途中の失敗は自動で巻き戻さない。
        """
        target = target if isinstance(target, mlib.nodes.Node) else mlib.nodes.Node(target)
        if not isinstance(target, mlib.nodes.Transform):
            raise TypeError("target must be a transform")
        if type(fast) is not bool:
            raise TypeError("fast must be a bool")
        parent = target.getParent()
        if fast and (isinstance(target, mlib.nodes.Joint) or len(target.getInstances()) > 1
                     or (parent is not None and len(parent.getInstances()) > 1)):
            raise NotImplementedError("fast offset groups do not support joints or instances")
        if not names:
            names = (target.getName() + "_offset",)
        matrix = target.getMatrix(worldSpace=True)
        groups = []
        for name in names:
            options = {"name": name, "skipSelect": True, "fast": fast}
            if parent is not None:
                options["parent"] = parent
            group = mlib.createNode("transform", **options)
            group.setMatrix(matrix, worldSpace=True, fast=fast)
            groups.append(group)
            parent = group
        target.setParent(groups[-1], fast=fast)
        return groups

    @staticmethod
    @undoChunk("mlrigControlHierarchyReleaseTransformChannels")
    def unlockAndDisconnectTransformChannels(target, *, fast=False):
        """TRS・shearと子チャンネルをアンロックし、入出力接続を解除する。

        Args:
            target (Transform | str): 編集対象。
            fast (bool): TrueはmlibのOpenMaya直接更新を使い、Undoなし。

        Returns:
            Transform: 編集した対象。

        Raises:
            TypeError: targetがTransformでない、またはfastがboolでない場合。

        通常は一回のUndoで戻せる。接続を保持する処理ではないため明示的に呼び出す。
        """
        target = target if isinstance(target, mlib.nodes.Node) else mlib.nodes.Node(target)
        if not isinstance(target, mlib.nodes.Transform):
            raise TypeError("target must be a transform")
        if type(fast) is not bool:
            raise TypeError("fast must be a bool")
        for name in ("translate", "rotate", "scale", "shear"):
            plug = target.getPlug(name)
            plug.setFlags(locked=False, fast=fast)
            plug.disconnectAll(fast=fast)
            for child in plug.getChildren():
                child.setFlags(locked=False, fast=fast)
                child.disconnectAll(fast=fast)
        return target
