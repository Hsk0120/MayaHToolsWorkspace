from maya.api import OpenMaya as om2
from maya import cmds


def getScale(dag_path):
    return om2.MTransformationMatrix(
        dag_path.inclusiveMatrix()
    ).scale(om2.MSpace.kTransform)


def _setScalePlug(dag_path, scale):
    node = dag_path.fullPathName()
    for attribute, value in zip(
        ("scaleX", "scaleY", "scaleZ"),
        scale
    ):
        cmds.setAttr("{}.{}".format(node, attribute), float(value))


def setScale(dag_path, scale):
    matrix = om2.MTransformationMatrix(dag_path.inclusiveMatrix())
    matrix.setScale(scale, om2.MSpace.kTransform)
    matrix = om2.MTransformationMatrix(
        matrix.asMatrix() * dag_path.exclusiveMatrixInverse()
    )
    _setScalePlug(dag_path, matrix.scale(om2.MSpace.kTransform))


def setScaleFromSelection():
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
