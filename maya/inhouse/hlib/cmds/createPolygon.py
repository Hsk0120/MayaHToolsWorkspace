"""ポリゴンプリミティブを種類フラグで生成する。

Synopsis
--------

.. code-block:: python

    mesh = hlib.createPolygon(type="cube", width=2, constructionHistory=False)
    sphere = hlib.createPolygon(type="sphere", radius=3)
    mesh.getTransform().getPlug("translateX").set(5)

``type`` (短名 ``typ``) は cube、sphere、cylinder、cone、plane、torus、
pipe、pyramid、prism、helix、platonicSolid。対応するMayaコマンド名
（``polyCube`` 等）でも指定できます。既定はcubeです。

寸法・分割数・名前・履歴などは各Mayaコマンドの長名と短名を使用できます。
``name`` は親Transformの名前です。戻り値は履歴設定に関係なく単一のMeshです。
親は ``mesh.getTransform()``、履歴は ``maya.cmds.listHistory(mesh)`` で取得できます。
作成は1回のUndoで戻せます。query/editとobject=Falseは受け付けません。
押し出し・結合など既存メッシュを編集するpolyコマンドは対象外です。
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases, normalize_flags
from ..decorator import undoChunk

_PRIMITIVES = {
    "cube": "polyCube",
    "sphere": "polySphere",
    "cylinder": "polyCylinder",
    "cone": "polyCone",
    "plane": "polyPlane",
    "torus": "polyTorus",
    "pipe": "polyPipe",
    "pyramid": "polyPyramid",
    "prism": "polyPrism",
    "helix": "polyHelix",
    "platonicSolid": "polyPlatonicSolid",
}


@flag_aliases(typ="type")
@undoChunk("hlib.cmds.createPolygon")
def createPolygon(type="cube", **kwargs):
    """種類を指定してプリミティブを生成し、Meshを返す。

    Args:
        type (str): プリミティブの種類またはMayaコマンド名。既定cube。短縮typ。
        **kwargs (object): 選択したコマンドの生成フラグ。長短名の重複は拒否する。
            nameは親Transform名。constructionHistoryは履歴の有無を指定する。

    Returns:
        Mesh: 生成したポリゴンシェイプ。Transformや履歴ノードは含まない。

    Raises:
        TypeError: typeが文字列でない場合、または長短フラグが重複する場合。
        ValueError: 未対応の種類、query/edit、object=Falseを指定した場合。
        RuntimeError: Mayaが生成を拒否する、またはMeshを取得できない場合。
    """
    from ..nodes.node import Node
    from ..nodes.mesh import Mesh

    if not isinstance(type, str):
        raise TypeError("type must be a string")
    command = _PRIMITIVES.get(type, type)
    if command not in _PRIMITIVES.values():
        raise ValueError("Unsupported polygon primitive: " + type)
    options = normalize_flags(command, kwargs)
    if options.get("query") or options.get("edit"):
        raise ValueError("createPolygon supports creation only")
    if not options.get("object", True):
        raise ValueError("createPolygon requires object=True to return a Mesh")
    result = getattr(cmds, command)(**options)
    mesh = Node(result[0]).getShape()
    if not isinstance(mesh, Mesh):
        raise RuntimeError("Polygon primitive did not produce a Mesh: " + command)
    return mesh
