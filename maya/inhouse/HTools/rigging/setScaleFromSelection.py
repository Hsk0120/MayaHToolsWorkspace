from maya.api import OpenMaya as om2
from maya import cmds


def getScale(dag_path):
    """DAGパスのワールド行列を分解してスケールを取得する。

    Args:
        dag_path: 操作対象のMaya API DAGパス。

    Returns:
        tuple[float, float, float]: ワールド行列から分解したXYZスケール。
    """
    return om2.MTransformationMatrix(
        dag_path.inclusiveMatrix()
    ).scale(om2.MSpace.kTransform)


def _setScalePlug(dag_path, scale):
    """XYZのscaleアトリビュートへ個別に値を設定する。

    Args:
        dag_path: 操作対象のMaya API DAGパス。
        scale: 設定するXYZスケール。
    """
    node = dag_path.fullPathName()
    for attribute, value in zip(
        ("scaleX", "scaleY", "scaleZ"),
        scale
    ):
        cmds.setAttr("{}.{}".format(node, attribute), float(value))


def setScale(dag_path, scale):
    """ワールドスケールを親空間へ変換し、ローカルscaleへ設定する。

    Args:
        dag_path: 操作対象のMaya API DAGパス。
        scale: 設定するXYZスケール。
    """
    matrix = om2.MTransformationMatrix(dag_path.inclusiveMatrix())
    matrix.setScale(scale, om2.MSpace.kTransform)
    matrix = om2.MTransformationMatrix(
        matrix.asMatrix() * dag_path.exclusiveMatrixInverse()
    )
    _setScalePlug(dag_path, matrix.scale(om2.MSpace.kTransform))


def setScaleFromSelection():
    """先頭の選択から2番目の選択へワールドスケールを一回のUndoでコピーする。
    """
    cmds.undoInfo(openChunk=True)
    try:
        selection = om2.MGlobal.getActiveSelectionList()
        source = selection.getDagPath(0)
        target = selection.getDagPath(1)
        setScale(target, getScale(source))
    finally:
        cmds.undoInfo(closeChunk=True)

if __name__ == "__main__":
    setScaleFromSelection()
