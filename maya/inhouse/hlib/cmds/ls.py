"""
Synopsis
--------

.. code-block:: python

    hlib.cmds.ls(*args, **kwargs)

名前や条件で Maya ノードを検索し、検索結果を hlib ラッパーへ変換します。

シーンの検索操作です。戻り値はノードとしてラップするため、型名やコンポーネントなどノード名以外を返すフラグの組み合わせには対応しません。

Return value
------------

``list[Node] | Joints | SkinClusters``
    type="joint" は Joints、type="skinCluster" は SkinClusters。それ以外は Node のリスト。検索結果がない場合は空のリストまたは空の専用コレクション。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`constraint <../constraint/index>`

Flags
-----

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``*args``
     - ``str``
     - 省略可
     - 名前やワイルドカードなど、maya.cmds.ls の位置引数。
   * - ``type (typ)``
     - ``str``
     - 省略可
     - Maya のノード型で絞り込み。専用コレクションへの変換判定は長名 type のみ。
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

    nodes = hlib.cmds.ls(type="transform")
    joints = hlib.cmds.ls(type="joint")
    selected = hlib.cmds.ls(selection=True)
"""

import maya.cmds as cmds


def ls(*args, **kwargs):
    """Mayaノードを検索し、対応するhlib wrapperとして返す。"""
    from ..nodes import Joints, Node, SkinClusters

    names = cmds.ls(*args, **kwargs) or []
    node_type = kwargs.get("type")
    if node_type == "joint":
        return Joints(names)
    if node_type == "skinCluster":
        return SkinClusters(names)
    return [Node(name) for name in names]
