"""Maya DGのBifrostグラフをhlibのノード参照で管理する。"""

import maya.cmds as cmds

from .._binding import coreModule
# ルートCompoundへの参照。DGノードとは独立したVNN参照。
from .compound import Compound

undoTransaction = coreModule('decorators.undo').undoTransaction


class Graph:
    """DGノードをhlib参照で保持し、名前変更に追従するグラフ。"""

    def __init__(self, node):
        """既存のbifrostGraphShapeを取得する。

        Args:
            node: hlibで解決可能なDGノード。
        """
        MayaNode = coreModule('nodes').Node

        self.node = MayaNode(node)
        if self.node.getType() != "bifrostGraphShape":
            raise TypeError("Expected bifrostGraphShape")

    @classmethod
    @undoTransaction("hlib_bifrost.Graph.create")
    def create(cls, name="bifrostGraphShape"):
        """必要なプラグインをロードして親Transformとグラフを生成する。

        Args:
            name (str): グラフShapeの希望名。親名にはTransformを付加する。

        Returns:
            Graph: 作成したグラフへの参照。

        Note:
            Shapeの作成に失敗した場合は、この処理で作成した親を削除する。
        """
        MayaNode = coreModule('nodes').Node
        from ..environment.bifrost import Bifrost

        Bifrost.ensure_available()
        parent = MayaNode.create("transform", name=name + "Transform", skipSelect=True)
        try:
            return cls(
                MayaNode.create("bifrostGraphShape", name=name, parent=parent, skipSelect=True)
            )
        except Exception:
            cmds.delete(parent.getFullName())
            raise

    @property
    def root(self):
        """Compound: ルートへの参照。照会やシーン変更は行わない。"""
        return Compound(self, "/")

    def getName(self):
        """現在のDG完全名を取得する。

        Returns:
            str: 現在のDG完全名を取得する。
        """
        return self.node.getFullName()

    def getParent(self):
        """所有するDAG親を取得する。

        Returns:
            Node: グラフshapeのtransform親。
        """
        MayaNode = coreModule('nodes').Node

        names = cmds.listRelatives(self.getName(), parent=True, fullPath=True) or []
        if not names:
            raise ValueError("Graph has no DAG parent")
        return MayaNode(names[0])

    @undoTransaction("hlib_bifrost.Graph.delete")
    def delete(self):
        """グラフと現在のDAG親を削除する。親に他の子があれば拒否する。"""
        core = coreModule()

        parent = self.getParent()
        children = cmds.listRelatives(parent.getFullName(), children=True, fullPath=True) or []
        if children != [self.getName()]:
            raise ValueError("Parent contains other children; delete the graph shape explicitly")
        core.delete(parent)
