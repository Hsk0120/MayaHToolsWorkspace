"""
Synopsis
--------

.. code-block:: python

    hlib.ls(*args, **kwargs)

名前や条件で Maya ノードを検索し、検索結果を hlib ラッパーへ変換します。

コンポーネント範囲は単体の参照へ展開します。型名などシーン参照以外を返すフラグには対応しません。

Return value
------------

``list[Node | Plug | Component] | Joints | SkinClusters``
    コンポーネント型指定時は該当する単体コンポーネントのリスト。ノード型のtype="joint" は Joints、type="skinCluster" は SkinClusters。それ以外は参照のリスト。未検出時は空。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`constraint <../addConstraint/index>`

Flags
-----

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``*args``
     - ``str | Node | Plug | Component | Components | MObject | MDagPath | MPlug | Iterable``
     - 省略可
     - 名前やワイルドカードなど、maya.cmds.ls の位置引数。文字列以外は一意な名前に変換して渡します（:doc:`/cmds_interop`）。空の列と ``None`` は空の結果になります。
   * - ``type (typ)``
     - ``str``
     - 省略可
     - Mayaのノード型、またはvertex / edge / face / uv / controlVertex。コンポーネントは単一の正式名称で指定し、vtx/e/f/map/cv等の別名は追加しません。種類の変換は行いません。
   * - ``selection (sl)``
     - ``bool``
     - False
     - 選択中のノード・アトリビュート・コンポーネントを取得。
   * - ``long (l)``
     - ``bool``
     - False
     - Maya から完全な DAG パスを取得。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の ls フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    nodes = hlib.ls(type="transform")
    joints = hlib.ls(type="joint")
    selected = hlib.ls(selection=True)
    vertices = hlib.ls(sl=True, type="vertex")
    faces = hlib.ls(sl=True, type="face")
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases


@flag_aliases("ls")
def ls(*args, **kwargs):
    """Mayaの参照を検索し、対応するラッパーとして返す。

    Args:
        *args (object): maya.cmds.lsへ渡す名前・名前列・パターン。文字列はそのまま渡し、
            Node・Plug・Component・MObject・MDagPath・MPlug とその列は一意な名前へ変換する。
            空の列だけを渡した場合は maya.cmds.ls([]) と同じく空の結果を返す。None は
            maya.cmds.ls(None) と同じく空の列として扱う(``cmds.listRelatives`` などが
            結果なしのときに返す None をそのまま渡せる)。
        **kwargs (object): type/typはノード型またはvertex/edge/face/uv/controlVertex。
            省略時は全種類。範囲はflatten指定によらず単体へ展開する。
            複数シェイプもリストで返す。オブジェクトや他種類からの変換は行わない。
            その他はmaya.cmds.lsへ渡す検索フラグ。
    Returns:
        list[Node | Plug | Component] | Joints | SkinClusters: コンポーネント型指定時は単体要素のリスト。
            ノード型のtypeまたはtypがjoint/skinClusterの場合は従来の専用コレクション。
    Raises:
        TypeError: 位置引数に対応しない型が含まれる場合。
        ValueError: 位置引数に削除済みの対象が含まれる場合。
        RuntimeError: 検索結果をノードとして解決できない場合。

    型名等を返すMayaフラグは非対応。検索結果が空なら空コレクションまたは空リスト。"""
    from ..nodes.node import Nodes as _InputNodes
    from ..object import Object as _InputObject
    from ..nodes import Joints, SkinClusters
    from ..components import Vertex, Edge, Face, UV, CV
    from ..scene.selection import Selection

    component_types = {"vertex": Vertex, "edge": Edge, "face": Face,
                       "uv": UV, "controlVertex": CV}
    node_type = kwargs.get("type")
    component = node_type if isinstance(node_type, str) and node_type in component_types else None
    if component is not None:
        kwargs.pop("type")

    targets = []
    for arg in _InputNodes._resolve_inputs([arg for arg in args if arg is not None]):
        if arg is None:
            continue
        if isinstance(arg, str):
            targets.append(arg)
        else:
            targets.extend(_InputObject._input_names(arg))
    # 空の列だけを渡した場合に maya.cmds.ls() の全ノード検索へ変わらないようにする。
    names = (cmds.ls(*targets, **kwargs) or []) if targets or not args else []
    node_type = kwargs.get("type")
    if component is None and node_type == "joint":
        return Joints(names)
    if component is None and node_type == "skinCluster":
        return SkinClusters(names)
    # Mayaの検索・並び順を維持し、解決だけを既存のOpenMaya経路へ任せる。
    # 全件を単一Selectionにすると重複が除かれるため、結果ごとに解決する。
    from .._core.commandResult import CommandResult
    from ..components import Component

    result = []
    for name in names:
        if "." not in name:
            if component is None:
                result.append(CommandResult.reference(name))
            continue
        resolved = Selection(name).items
        if resolved and isinstance(resolved[0], Component):
            result.extend(resolved)
        elif component is None:
            result.append(CommandResult.reference(name))
    if component is not None:
        return [item for item in result if isinstance(item, component_types[component])]
    return result
