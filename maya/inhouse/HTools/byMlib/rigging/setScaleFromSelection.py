import mlib
from mlib.decorator import undoChunk


def getScale(node):
    """ノードのワールドマトリクスを分解してスケールを取得する。

    Args:
        node (mlib.Transform): 操作対象のノード。

    Returns:
        mlib.Scale: ワールドマトリクスから分解したXYZスケール。
    """
    return node.getMatrix(ws=True).scale


def _setScalePlug(node, scale):
    """XYZのscaleアトリビュートへ個別に値を設定する。

    Args:
        node (mlib.Transform): 操作対象のノード。
        scale: 設定するXYZスケール。
    """
    for attribute, value in zip(
        ("scaleX", "scaleY", "scaleZ"),
        scale
    ):
        node.getPlug(attribute).set(float(value))


def setScale(node, scale):
    """ワールドスケールを親空間へ変換し、ローカルscaleへ設定する。

    Args:
        node (mlib.Transform): 操作対象のノード。
        scale: 設定するXYZスケール。
    """
    matrix = node.getMatrix(ws=True)
    matrix.scale = scale
    matrix = matrix * node.getMatrix(ws=True, parent=True, inverse=True)
    _setScalePlug(node, matrix.scale)


def setScaleFromSelection():
    """先頭の選択から2番目の選択へワールドスケールを一回のUndoでコピーする。
    """
    with undoChunk():
        selection = mlib.ls(sl=True)
        source = selection[0]
        target = selection[1]
        setScale(target, getScale(source))

if __name__ == "__main__":
    setScaleFromSelection()
