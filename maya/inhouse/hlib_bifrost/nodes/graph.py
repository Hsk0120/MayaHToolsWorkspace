"""Maya DGのBifrostグラフをhlibのノード参照で管理する。"""

from maya import cmds
from hlib.decorators.undo import undoTransaction


class Graph:
    """DGノードをhlib参照で保持し、名前変更に追従するグラフ。"""

    def __init__(self, node):
        """既存のbifrostGraphShapeを取得する。

        Args:
            node: hlibで解決可能なDGノード。
        """
        from hlib.nodes import Node as MayaNode

        self.node = MayaNode(node)
        if self.node.type() != "bifrostGraphShape":
            raise TypeError("Expected bifrostGraphShape")

    @classmethod
    @undoTransaction("hlib_bifrost.Graph.create")
    def create(cls, name="bifrostGraphShape"):
        """必要なプラグインをロードしてグラフを生成する。"""
        from hlib.nodes import Node as MayaNode
        from hlib_bifrost.environment.bifrost import Bifrost

        Bifrost.ensure_available()
        parent = MayaNode.create("transform", name=name + "Transform", skipSelect=True)
        try:
            return cls(
                MayaNode.create("bifrostGraphShape", name=name, parent=parent, skipSelect=True)
            )
        except Exception:
            cmds.delete(parent.fullName())
            raise

    @property
    def root(self):
        """Compound: ルートへの参照。照会やシーン変更は行わない。"""
        return Compound(self, "/")

    def name(self):
        """str: 現在のDG完全名を取得する。"""
        return self.node.fullName()

    def parent(self):
        """所有するDAG親を取得する。

        Returns:
            Node: グラフshapeのtransform親。
        """
        from hlib.nodes import Node as MayaNode

        names = cmds.listRelatives(self.name(), parent=True, fullPath=True) or []
        if not names:
            raise ValueError("Graph has no DAG parent")
        return MayaNode(names[0])

    @undoTransaction("hlib_bifrost.Graph.delete")
    def delete(self):
        """グラフと現在のDAG親を削除する。親に他の子があれば拒否する。"""
        import hlib

        parent = self.parent()
        children = cmds.listRelatives(parent.fullName(), children=True, fullPath=True) or []
        if children != [self.name()]:
            raise ValueError("Parent contains other children; delete the graph shape explicitly")
        hlib.delete(parent)


# ルートCompoundへの参照。DGノードとは独立したVNN参照。
from .compound import Compound
