"""
Synopsis
--------

.. code-block:: python

    hlib.ls(*args, **kwargs)

名前や条件で Maya ノードを検索し、検索結果を hlib ラッパーへ変換します。

シーンの検索操作です。戻り値はノードとしてラップするため、型名やコンポーネントなどノード名以外を返すフラグの組み合わせには対応しません。

Return value
------------

``list[Node | Plug] | Joints | SkinClusters``
    type="joint" は Joints、type="skinCluster" は SkinClusters。それ以外は Node のリスト。検索結果がない場合は空のリストまたは空の専用コレクション。

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
     - Maya のノード型で絞り込み。type / typ のどちらも同じ専用コレクションへ変換します。
   * - ``selection (sl)``
     - ``bool``
     - False
     - 選択中のノードを取得。
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
"""

from .._core.flags import flag_aliases

import maya.cmds as cmds


@flag_aliases("ls")
def ls(*args, **kwargs):
    """Mayaノードを検索し、対応するラッパーとして返す。

    Args:
        *args (object): maya.cmds.lsへ渡す名前・名前列・パターン。文字列はそのまま渡し、
            Node・Plug・Component・MObject・MDagPath・MPlug とその列は一意な名前へ変換する。
            空の列だけを渡した場合は maya.cmds.ls([]) と同じく空の結果を返す。None は
            maya.cmds.ls(None) と同じく空の列として扱う(``cmds.listRelatives`` などが
            結果なしのときに返す None をそのまま渡せる)。
        **kwargs (object): maya.cmds.lsへ渡す検索フラグ。
    Returns:
        list[Node | Plug] | Joints | SkinClusters: アトリビュートはPlug。typeまたはtypがjoint/skinClusterの場合は専用コレクション。それ以外はリスト。
    Raises:
        TypeError: 位置引数に対応しない型が含まれる場合。
        ValueError: 位置引数に削除済みの対象が含まれる場合。
        RuntimeError: 検索結果をノードとして解決できない場合。

    ノード・アトリビュート名を返す検索用（アトリビュートはPlug）。コンポーネント・型名等を返すMayaフラグは
    ラッパー化できない場合がある。検索結果が空なら空コレクションまたは空リスト。"""
    from ..nodes.node import Nodes as _InputNodes
    from ..object import Object as _InputObject
    from ..nodes import Joints, Node, SkinClusters

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
    if node_type == "joint":
        return Joints(names)
    if node_type == "skinCluster":
        return SkinClusters(names)
    from .._core.commandResult import CommandResult
    return CommandResult.references(names)
