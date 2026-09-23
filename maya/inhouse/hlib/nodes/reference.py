"""Maya の reference ノードを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.registry import node_wrapper
from ..decorators.undo import undoable
from .node import Node


@node_wrapper("reference")
class Reference(Node):
    """Maya の reference ノードラッパー。参照ファイルの照会・ロード制御を提供する。"""

    def reference_fn(self):
        """MFnReference を取得する。

        Returns:
            om2.MFnReference: この reference ノードの function set。
        """
        return om2.MFnReference(self.mobject())

    def filename(self, resolved=True, with_copy_number=False):
        """参照ファイルのパスを取得する。

        Args:
            resolved (bool): True の場合、パス変数などを解決した実際のパスを返す。
                False の場合はシーンに保存されている未解決のパスを返す。
            with_copy_number (bool): True の場合、同じファイルを複数回参照した
                際のコピー番号(``{1}`` 等)を含める。

        Returns:
            str: 参照ファイルのパス。
        """
        return self.reference_fn().fileName(resolved, with_copy_number, False)

    def namespace(self):
        """参照内容が読み込まれている Namespace を取得する。

        Returns:
            Namespace: 参照の名前空間。
        """
        # scenes.namespace が ..nodes を逆方向 import しないため単純な import で足りるが、
        # hlib 内の他の相互依存箇所と合わせて遅延 import で統一する。
        from ..scenes import Namespace

        return Namespace(self.reference_fn().associatedNamespace(False))

    def is_loaded(self):
        """参照が現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。
        """
        return self.reference_fn().isLoaded()

    def nodes(self):
        """この参照が持ち込んだノードを取得する。

        Returns:
            list[Node]: 参照内のノードラッパー。

        Raises:
            RuntimeError: 参照が現在アンロードされている場合。
        """
        if not self.is_loaded():
            raise RuntimeError("Cannot enumerate nodes of an unloaded reference")
        return [Node(mobject) for mobject in self.reference_fn().nodes()]

    def parent_reference(self):
        """親の Reference を取得する(ネストした参照の場合)。

        Returns:
            Reference | None: 親参照。トップレベルの参照では None。
        """
        parent = self.reference_fn().parentReference()
        if parent.isNull():
            return None
        return Reference(parent)

    @undoable("hlibReferenceLoad")
    def load(self):
        """参照をロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        cmds.file(loadReference=self.name())
        return self

    @undoable("hlibReferenceUnload")
    def unload(self):
        """参照をアンロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        cmds.file(unloadReference=self.name())
        return self

    @undoable("hlibReferenceRemove")
    def remove(self):
        """参照を削除する(参照ノードとその内容をシーンから除去する)。

        呼び出し後、このオブジェクトが参照していたノードはシーン上に存在しなくなる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が削除を拒否した場合。
        """
        cmds.file(removeReference=True, referenceNode=self.name())
