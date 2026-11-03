"""選択から、作業の対象(メッシュ・skinCluster・頂点)を決める。

頂点・エッジ・フェースを選んでいれば、その頂点を対象にする。オブジェクトを選んでいれば、そのメッシュの
全体を対象にし、頂点の操作では全頂点を使う。複数のメッシュにまたがる選択は、最初のメッシュだけを使う。
"""

import mlib
from mlib.common import Selection
from mlib.components import Edges, Faces, Vertices


class Target(object):
    """作業の対象。

    Args:
        mesh (mlib.nodes.Mesh): 対象のメッシュのシェイプ。
        skin (mlib.nodes.SkinCluster | None): メッシュを変形している skinCluster。無ければNone。
        vertices (list[int] | None): 選んだ頂点の番号(重複なし)。オブジェクトの選択はNone。
    """

    def __init__(self, mesh, skin, vertices):
        self.mesh = mesh
        self.skin = skin
        self.vertices = vertices

    def hasComponents(self):
        """頂点を選んで決めた対象かを返す。

        Returns:
            bool: 頂点・エッジ・フェースを選んでいればTrue。
        """
        return self.vertices is not None

    def requireSkin(self):
        """skinCluster を返す。無ければ例外にする。

        Returns:
            mlib.nodes.SkinCluster: 対象の skinCluster。

        Raises:
            ValueError: メッシュがバインドされていない場合。
        """
        if self.skin is None:
            raise ValueError("{} has no skinCluster".format(self.mesh.getNodeName()))
        return self.skin

    def requireVertices(self):
        """選んだ頂点の番号を返す。頂点を選んでいなければ例外にする。

        Returns:
            list[int]: 頂点の番号。

        Raises:
            ValueError: 頂点・エッジ・フェースを選んでいない場合。
        """
        if not self.vertices:
            raise ValueError("Select vertices, edges or faces of a skinned mesh")
        return list(self.vertices)

    def editVertices(self):
        """頂点の操作に使う番号を返す(選んでいなければ全頂点)。

        Returns:
            list[int]: 頂点の番号。
        """
        if self.vertices:
            return list(self.vertices)
        return list(range(self.mesh.getNumVertices()))

    def label(self):
        """パネルの見出しに出す説明を返す。

        Returns:
            str: ``"body_GEO  skinCluster1  12 verts"`` のような文。
        """
        parts = [self.mesh.getTransform().getNodeName() if self.mesh.getTransform() else self.mesh.getNodeName()]
        parts.append(self.skin.getNodeName() if self.skin is not None else "(not skinned)")
        if self.vertices is not None:
            parts.append("{} verts".format(len(self.vertices)))
        return "  ".join(parts)


def _meshes_of(node):
    """ノードからメッシュのシェイプを返す(transform なら中間でないシェイプ)。

    Args:
        node (mlib.nodes.Node): 選んだノード。

    Returns:
        list[mlib.nodes.Mesh]: メッシュ。
    """
    if isinstance(node, mlib.nodes.Mesh):
        return [node]
    if isinstance(node, mlib.nodes.Transform):
        return [shape for shape in node.getShapes() if isinstance(shape, mlib.nodes.Mesh)]
    return []


def _skin_of(mesh):
    """メッシュを変形している最初の skinCluster を返す。

    Args:
        mesh (mlib.nodes.Mesh): メッシュ。

    Returns:
        mlib.nodes.SkinCluster | None: skinCluster。無ければNone。
    """
    skins = mesh.getSkinClusters()
    return skins[0] if skins else None


def resolve(selection=None):
    """選択から対象を決める。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        Target | None: 対象。メッシュを選んでいなければNone。
    """
    selection = Selection.capture() if selection is None else selection
    for components in selection.getComponents():
        if isinstance(components, (Edges, Faces)):
            components = components.getVertices()
        if not isinstance(components, Vertices) or not isinstance(components.shape, mlib.nodes.Mesh):
            continue
        mesh = components.shape
        indices = []
        seen = set()
        # 同じメッシュの頂点を重複なく集める(エッジ・フェースから変えた頂点も含める)。
        for other in selection.getComponents():
            if isinstance(other, (Edges, Faces)):
                other = other.getVertices()
            if isinstance(other, Vertices) and other.shape == mesh:
                for index in other.indices:
                    if index not in seen:
                        seen.add(index)
                        indices.append(index)
        return Target(mesh, _skin_of(mesh), indices)
    for node in selection.getNodes():
        meshes = _meshes_of(node)
        if meshes:
            return Target(meshes[0], _skin_of(meshes[0]), None)
    return None


def require(selection=None):
    """選択から対象を決める。メッシュを選んでいなければ例外にする。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        Target: 対象。

    Raises:
        ValueError: メッシュ・その頂点を選んでいない場合。
    """
    target = resolve(selection)
    if target is None:
        raise ValueError("Select a skinned mesh or its vertices")
    return target


def selectVertices(mesh, indices):
    """メッシュの頂点を選ぶ。

    Args:
        mesh (mlib.nodes.Mesh): メッシュ。
        indices (Iterable[int]): 頂点の番号。空なら選択を空にする。

    Returns:
        int: 選んだ頂点の数。
    """
    indices = list(indices)
    if not indices:
        mlib.select(clear=True)
        return 0
    Selection([mesh.getVertices(indices)]).select()
    return len(indices)
