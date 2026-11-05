"""メッシュの他のデフォーマー(cluster・softMod・deltaMush 等)のウェイトを、インフルエンスの値として取り込む。

塗りやすいデフォーマー(cluster 等)で範囲を作ってから、その値をそのままジョイントのウェイトにできる。
ウェイトはデフォーマーの最初の形状(weightList[0])を使い、値の無い頂点は Maya の既定どおり 1 とみなす。
"""

import mlib
from mlib.decorator import undoChunk


from . import influences as influences_module
from . import weights as weights_module

#: 取り込みの対象にしない型(スキンそのものと、内部の tweak)。
EXCLUDED_TYPES = ("skinCluster", "tweak")


def listDeformers(mesh):
    """メッシュに掛かっている、ウェイトを持つデフォーマーを返す。

    Args:
        mesh (mlib.Mesh): メッシュ。

    Returns:
        list[mlib.Node]: デフォーマー(履歴の順)。
    """
    return [node for node in mesh.getHistory(type="geometryFilter")
            if isinstance(node, mlib.GeometryFilter) and node.getType() not in EXCLUDED_TYPES
            and node.hasAttr("weightList")]


def deformerWeights(deformer, count):
    """デフォーマーの頂点ごとのウェイトを返す。

    Args:
        deformer (mlib.Node): デフォーマー。
        count (int): メッシュの頂点の数。

    Returns:
        list[float]: 頂点の順の値(値の無い頂点は1)。
    """
    values = deformer.getDeformerWeights()
    return (values + [1.0] * count)[:count]


@undoChunk("skinWeightKitDeformerToWeight")
def toInfluence(target, deformer, influence, threshold=0.0):
    """デフォーマーのウェイトを、インフルエンスの値にする(他のロックしていないインフルエンスで合計を1にする)。

    頂点を選んでいればその頂点、メッシュを選んでいれば全頂点のうち、デフォーマーの値が threshold より大きい頂点を変える。

    Args:
        target (Target): 対象。
        deformer (mlib.Node | str): ウェイトを読むデフォーマー。
        influence (mlib.Node | str): 値を設定するインフルエンス。
        threshold (float): これ以下の値の頂点は変えない。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: デフォーマーがメッシュに無い、またはインフルエンスがロックされている場合。
    """
    skin = target.requireSkin()
    found = [node for node in listDeformers(target.mesh) if node == deformer or node.getNodeName() == str(deformer)]
    if not found:
        raise ValueError("{} is not a deformer of {}".format(deformer, target.mesh.getNodeName()))
    node = influences_module.find(skin, influence)
    if influences_module.isLocked(node):
        raise ValueError("{} is locked".format(node.getNodeName()))
    values = deformerWeights(found[0], target.mesh.getNumVertices())
    vertices = [vertex for vertex in target.editVertices() if values[vertex] > threshold]
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(other) for other in influences]
    column = influences.index(node)
    rows = weights_module.readRows(skin, influences, vertices)
    written = [weights_module.fitColumn(row, column, values[vertex], locked) for vertex, row in zip(vertices, rows)]
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)
